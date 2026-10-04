#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from backend.app.db.session import SessionLocal
from backend.app.repositories.scene_repo import SceneRepository
from backend.app.runtime.scene_importer import infer_scene_id
from backend.app.schemas.scene import SceneImportRequest
from backend.app.services.scene_service import SceneService
from backend.generation.assets.npc_library import get_default_npcs

BASE_SCENES = (
    "simple_factory_1f.json",
    "simple_home_1f.json",
    "simple_hospital_1f.json",
    "simple_office_1f.json",
    "simple_supermarket_1f.json",
)


def scene_type(scene: dict[str, Any]) -> str:
    name = str(scene.get("scene_name") or "")
    for candidate in ("hospital", "supermarket", "office", "factory"):
        if candidate in name:
            return candidate
    return "home"


def add_child(scene: dict[str, Any], parent_id: str, child_id: str) -> None:
    for node in scene.setdefault("nodes", []):
        if not isinstance(node, dict) or str(node.get("id") or "") != parent_id:
            continue
        children = node.setdefault("child", [])
        if isinstance(children, list) and child_id not in children:
            children.append(child_id)
        return


def ensure_node(scene: dict[str, Any], item: dict[str, Any]) -> None:
    node_id = str(item.get("id") or "")
    for node in scene.setdefault("nodes", []):
        if isinstance(node, dict) and str(node.get("id") or "") == node_id:
            node.update({key: value for key, value in item.items() if value not in ("", None, [], {})})
            break
    else:
        scene.setdefault("nodes", []).append(item)
    parent_id = str(item.get("parent") or "")
    if parent_id:
        add_child(scene, parent_id, node_id)


def ensure_edge(scene: dict[str, Any], source_id: str, target_id: str, relation: str) -> None:
    for edge in scene.setdefault("edges", []):
        if (
            isinstance(edge, dict)
            and str(edge.get("source_id") or edge.get("source") or "") == source_id
            and str(edge.get("target_id") or edge.get("target") or "") == target_id
            and str(edge.get("relation") or edge.get("edge_type") or "") == relation
        ):
            return
    scene.setdefault("edges", []).append(
        {
            "source_id": source_id,
            "target_id": target_id,
            "edge_type": "web_seed_edge",
            "relation": relation,
            "category": "web_seed",
            "properties": {},
        }
    )


def with_default_npcs(source: dict[str, Any]) -> dict[str, Any]:
    scene = copy.deepcopy(source)
    npc_specs = get_default_npcs(scene_type(scene))
    for spec in npc_specs:
        npc_id = str(spec.get("id") or "")
        parent_id = str(spec.get("parent") or "")
        if not npc_id or not parent_id:
            continue
        ensure_node(
            scene,
            {
                "id": npc_id,
                "name": spec.get("name", "human"),
                "name_cn": spec.get("name_cn", spec.get("name", "human")),
                "node_type": "human",
                "semantic_type": "human",
                "role": spec.get("role", ""),
                "persona": spec.get("persona", ""),
                "current_activity": spec.get("activity", ""),
                "states": {},
                "parent": parent_id,
                "child": [],
                "interactive_actions": [],
            },
        )
        ensure_edge(scene, parent_id, npc_id, "at")
    scene["web_seed"] = {
        "profile": "base_scene_with_default_npcs",
        "npc_count": len(npc_specs),
        "npc_ids": [str(spec.get("id") or "") for spec in npc_specs if spec.get("id")],
    }
    return scene


def seed_scene(path: Path, *, force: bool) -> str:
    source = json.loads(path.read_text(encoding="utf-8"))
    scene_id = infer_scene_id(source, fallback=path.stem)
    seeded = with_default_npcs(source)
    with SessionLocal() as db:
        repo = SceneRepository(db)
        latest = repo.list_versions(scene_id)[0] if repo.get_scene(scene_id) else None
        if latest and not force:
            web_seed = (latest.graph_summary or {}).get("web_seed") or {}
            if web_seed.get("profile") == "base_scene_with_default_npcs":
                return f"skip {scene_id}: latest snapshot already has default NPCs ({latest.id})"
        imported = SceneService(db).import_scene(
            SceneImportRequest(
                source_json=seeded,
                description="Base scene seeded for the web UI with default NPC profiles.",
            )
        )
        return f"import {scene_id}: {imported.id} ({imported.graph_summary.get('npc_count', 0)} NPCs)"


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the web scene registry with the five base GraphWorld scenes.")
    parser.add_argument(
        "--scene-dir",
        type=Path,
        default=ROOT_DIR / "backend" / "data" / "sg_output" / "simple_graph",
    )
    parser.add_argument("--force", action="store_true", help="Import a new snapshot even if the latest one is already seeded.")
    args = parser.parse_args()

    for filename in BASE_SCENES:
        print(seed_scene(args.scene_dir / filename, force=args.force))


if __name__ == "__main__":
    main()
