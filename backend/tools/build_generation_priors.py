"""Build high-frequency object, room-graph, co-occurrence and Office priors.

External and hand-authored sources are kept separate in the output metadata.
This command never mutates ``backend/core``.
"""

from __future__ import annotations

import argparse
import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from backend.core.assets.object_library import OBJECT_LIBRARY, resolve_object_key


NON_OBJECTS = {"floor", "room", "human", "robot"}
ROOM_RELATIONS = {"connected", "next_to", "neighbour"}


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def scene_objects(scene: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    nodes = {str(node.get("id")): node for node in scene.get("nodes", []) if node.get("id")}
    rooms = {node_id for node_id, node in nodes.items() if node.get("node_type") == "room"}
    room_of: dict[str, str] = {}
    for node_id, node in nodes.items():
        if node.get("semantic_type") in NON_OBJECTS or node.get("node_type") == "room":
            continue
        current = node_id
        visited = set()
        while current not in visited:
            visited.add(current)
            parent = nodes.get(current, {}).get("parent")
            if parent in rooms:
                room_of[node_id] = str(parent)
                break
            if not parent or parent not in nodes:
                break
            current = str(parent)
    return nodes, room_of


def build(scene_dir: Path, external_dir: Path) -> dict[str, Any]:
    room_graph: Counter[tuple[str, str]] = Counter()
    object_pairs: Counter[tuple[str, str]] = Counter()
    object_room_counts: Counter[tuple[str, str]] = Counter()
    room_counts: Counter[str] = Counter()
    office_scene_rows = []
    scene_count = 0
    for path in sorted(scene_dir.glob("*.json")):
        scene = read(path)
        scene_count += 1
        nodes, room_of = scene_objects(scene)
        room_ids = sorted(node_id for node_id, node in nodes.items() if node.get("node_type") == "room")
        room_counts.update(room_ids)
        for edge in scene.get("edges", []):
            source = str(edge.get("source_id") or "")
            target = str(edge.get("target_id") or "")
            if edge.get("relation") in ROOM_RELATIONS and source in room_ids and target in room_ids:
                room_graph[tuple(sorted((source, target)))] += 1
        by_room: dict[str, set[str]] = defaultdict(set)
        for node_id, room_id in room_of.items():
            semantic = str(nodes[node_id].get("semantic_type") or "")
            if semantic and semantic not in NON_OBJECTS:
                by_room[room_id].add(resolve_object_key(semantic))
                object_room_counts[(room_id, resolve_object_key(semantic))] += 1
        for values in by_room.values():
            for pair in itertools.combinations(sorted(values), 2):
                object_pairs[pair] += 1
        if path.stem.startswith("simple_office_1f"):
            office_scene_rows.append({
                "scene": path.stem,
                "rooms": room_ids,
                "object_counts": dict(Counter(resolve_object_key(str(node.get("semantic_type"))) for node in nodes.values() if node.get("semantic_type") not in NON_OBJECTS)),
            })

    external_rows = []
    for filename in ("ai2thor_room_object_counts.json", "procthor_room_object_counts.json"):
        path = external_dir / filename
        if path.exists():
            external_rows.extend(read(path))
    ext_counts: Counter[str] = Counter()
    ext_rooms: dict[str, set[str]] = defaultdict(set)
    for row in external_rows:
        obj = resolve_object_key(str(row.get("object_type") or ""))
        ext_counts[obj] += int(row.get("count", 0) or 0)
        ext_rooms[obj].add(str(row.get("room_type") or ""))
    top_objects = []
    for obj, count in ext_counts.most_common(40):
        if obj in NON_OBJECTS:
            continue
        top_objects.append({
            "object_type": obj,
            "external_count": count,
            "allowed_rooms_observed": sorted(ext_rooms[obj]),
            "core_template_exists": obj in OBJECT_LIBRARY,
            "status": "candidate_for_merge" if obj in OBJECT_LIBRARY else "requires_ontology_or_template",
        })
    return {
        "schema_version": "0.1",
        "core_mutated": False,
        "sources": {
            "external": "ProcTHOR/AI2-THOR aggregate statistics",
            "room_graph": "GraphWorld hand-authored simple_graph scenes",
            "object_cooccurrence": "GraphWorld hand-authored simple_graph scenes",
            "office": "GraphWorld hand-authored simple_office_1f scenes",
        },
        "high_frequency_object_templates": top_objects,
        "room_graph": {
            "scene_count": scene_count,
            "room_counts": dict(room_counts),
            "edge_counts": {"|".join(pair): count for pair, count in sorted(room_graph.items())},
            "note": "内部手工场景基线；不是 ProcTHOR/3D-FRONT 外部先验。",
        },
        "object_cooccurrence": {
            "scene_count": scene_count,
            "pair_counts": {"|".join(pair): count for pair, count in object_pairs.most_common()},
            "room_object_counts": {f"{room}|{obj}": count for (room, obj), count in sorted(object_room_counts.items())},
            "note": "对象共现按同一 GraphWorld 房间实例计算，不能等同于真实世界频率。",
        },
        "office": {
            "scene_count": len(office_scene_rows),
            "scenes": office_scene_rows,
            "note": "当前 Office 统计来自手工 scene JSON，用于核对模板覆盖；外部 Office 数据仍需 3D-FRONT/3D-FUTURE。",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-dir", type=Path, default=Path("backend/data/sg_output/simple_graph"))
    parser.add_argument("--external-dir", type=Path, default=Path("backend/data/external_stats"))
    parser.add_argument("--output-dir", type=Path, default=Path("backend/data/generation_priors"))
    args = parser.parse_args()
    result = build(args.scene_dir, args.external_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "high_frequency_object_templates.json": result["high_frequency_object_templates"],
        "room_graph.json": result["room_graph"],
        "object_cooccurrence.json": result["object_cooccurrence"],
        "office_priors.json": result["office"],
    }
    for name, payload in outputs.items():
        (args.output_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = [
        "# Generation Priors Audit",
        "",
        f"- high-frequency objects: `{len(result['high_frequency_object_templates'])}`",
        f"- room graph scenes: `{result['room_graph']['scene_count']}`",
        f"- office scenes: `{result['office']['scene_count']}`",
        "- core mutated: `false`",
        "",
        "数据来源和外部/手工边界见各 JSON 的 `sources`/`note` 字段。",
        "",
    ]
    (args.output_dir / "README.md").write_text("\n".join(report), encoding="utf-8")
    print(f"objects={len(result['high_frequency_object_templates'])} scenes={result['room_graph']['scene_count']} office={result['office']['scene_count']}")


if __name__ == "__main__":
    main()
