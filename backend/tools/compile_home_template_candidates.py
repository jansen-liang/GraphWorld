"""Compile external room/object statistics into reviewable Home candidates.

This command does not mutate ``backend/core``.  Core remains the canonical
runtime registry; this output is an auditable proposal for a later merge.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from backend.core.assets.object_library import OBJECT_LIBRARY
from backend.core.assets.room_library import ROOM_LIBRARY
from backend.generation.ontology import load_ontology


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def compile_candidates(stats_dir: Path, *, min_probability: float) -> dict[str, Any]:
    ontology = load_ontology()
    procthor = read(stats_dir / "procthor_stats.json")
    ai2thor = read(stats_dir / "ai2thor_stats.json")
    rooms: dict[str, dict[str, Any]] = {}
    object_rooms: dict[str, set[str]] = defaultdict(set)
    object_parents: dict[str, set[str]] = defaultdict(set)
    capabilities: dict[str, set[str]] = defaultdict(set)

    # AI2-THOR reports actual room-instance frequencies; use it for selection
    # and ProcTHOR as a complementary placement prior.
    for row in ai2thor.get("room_object_stats", []):
        if row["room_type"] not in ROOM_LIBRARY:
            continue
        if row.get("frequency_per_scene", 0.0) < min_probability:
            continue
        room = rooms.setdefault(row["room_type"], {"objects": {}, "source": []})
        object_type = ontology.normalize("objects", row["object_type"]) or row["object_type"]
        room["objects"][object_type] = {
            "frequency_per_scene": row.get("frequency_per_scene", 0.0),
            "count": row.get("count", 0),
        }
        object_rooms[object_type].add(row["room_type"])
    for row in procthor.get("room_object_stats", []):
        if row["room_type"] in ROOM_LIBRARY:
            rooms.setdefault(row["room_type"], {"objects": {}, "source": []})["source"].append("procthor")
            object_rooms[ontology.normalize("objects", row["object_type"]) or row["object_type"]].add(row["room_type"])
    for row in ai2thor.get("object_parent_stats", []) + procthor.get("object_parent_stats", []):
        child = ontology.normalize("objects", row["object_type"]) or row["object_type"]
        parent = ontology.normalize("objects", row["parent_type"]) or row["parent_type"]
        object_parents[child].add(parent)
    for row in ai2thor.get("object_capability_stats", []):
        for field, value in row.items():
            if isinstance(value, dict) and value.get("true", 0) > value.get("false", 0):
                capabilities[ontology.normalize("objects", row["object_type"]) or row["object_type"]].add(field)
    for row in procthor.get("object_capability_stats", []):
        for field in ("pickupable", "receptacle", "openable", "toggleable", "moveable"):
            if row.get(field) is True:
                capabilities[ontology.normalize("objects", row["object_type"]) or row["object_type"]].add(field)

    object_candidates = []
    for object_type in sorted(object_rooms):
        object_candidates.append({
            "object_type": object_type,
            "core_template_exists": object_type in OBJECT_LIBRARY,
            "status": "ready_for_core_merge" if object_type in OBJECT_LIBRARY else "requires_object_template",
            "allowed_rooms": sorted(object_rooms[object_type]),
            "allowed_parents": sorted(object_parents.get(object_type, set())),
            "functional_class_candidates": sorted(capabilities.get(object_type, set())),
        })
    room_candidates = []
    for room_type in sorted(ROOM_LIBRARY):
        spec = ROOM_LIBRARY[room_type]
        proposal = rooms.get(room_type, {"objects": {}, "source": []})
        room_candidates.append({
            "room_type": room_type,
            "core_template_exists": True,
            "existing_default_fixture_templates": list(spec.default_fixture_templates),
            "existing_default_movable_templates": list(spec.default_movable_templates),
            "observed_objects": proposal["objects"],
            "source": sorted(set(proposal.get("source", [])) | {"ai2thor"}),
        })
    return {
        "schema_version": "0.1",
        "status": "candidate_only",
        "core_mutated": False,
        "thresholds": {"min_probability": min_probability},
        "rooms": room_candidates,
        "objects": object_candidates,
        "merge_policy": "Only candidates with a reviewed ontology mapping and a core ObjectTemplate may be merged automatically.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stats-dir", type=Path, default=Path("backend/data/external_stats"))
    parser.add_argument("--output", type=Path, default=Path("backend/data/template_candidates/home_candidates.json"))
    parser.add_argument("--min-probability", type=float, default=0.02)
    args = parser.parse_args()
    result = compile_candidates(args.stats_dir, min_probability=args.min_probability)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = args.output.with_name("home_candidates.md")
    ready = sum(item["core_template_exists"] for item in result["objects"])
    report.write_text("\n".join([
        "# Home 模板候选审计",
        "",
        "本文件由统计结果生成，不会自动修改 `backend/core`。",
        "",
        f"- 房间候选：{len(result['rooms'])}",
        f"- 对象候选：{len(result['objects'])}",
        f"- 已有 core ObjectTemplate：{ready}",
        f"- 仍需补模板：{len(result['objects']) - ready}",
        "",
        "## 合并原则",
        "",
        "只有完成 ontology 映射、动作/状态审计和任务可解性验证的候选，才能合并到 `backend/core/assets`。",
        "",
    ]), encoding="utf-8")
    print(f"rooms={len(result['rooms'])} objects={len(result['objects'])} output={args.output}")


if __name__ == "__main__":
    main()
