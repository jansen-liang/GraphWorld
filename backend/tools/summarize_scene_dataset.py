from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.core.actions import ActionType
from backend.core.assets.npc_library import NPC_EVENT_LIBRARY, ROLE_SCHEDULES
from backend.core.assets.object_library import OBJECT_LIBRARY, resolve_object_key
from backend.core.assets.room_library import ROOM_LIBRARY
from backend.core.edges import RELATION_SPECS, SpatialRelation
from backend.core.states import DISCRETE_STATE_SPACE


DEFAULT_SCENE_DIR = ROOT / "backend" / "data" / "sg_output" / "simple_graph"
NON_OBJECT_SEMANTICS = {"floor", "human", "robot", "room"}


def _sorted_counter(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items()))


def _scene_profile(path: Path, scene: dict[str, Any]) -> str:
    if scene.get("variant_profile"):
        return str(scene["variant_profile"])
    return path.stem.split("__", 1)[1] if "__" in path.stem else "base"


def _event_statistics() -> dict[str, Any]:
    precondition_kinds: Counter[str] = Counter()
    effect_kinds: Counter[str] = Counter()
    event_state_keys: set[str] = set()
    for event in NPC_EVENT_LIBRARY.values():
        for precondition in event.preconditions:
            precondition_kinds[str(precondition.kind)] += 1
            event_state_keys.update(str(key) for key in (precondition.states or {}))
        for effect in (*event.effects_on_success, *event.effects_on_failure):
            effect_kinds[str(effect.kind)] += 1
            event_state_keys.update(str(key) for key in (effect.states or {}))
            if effect.state:
                event_state_keys.add(str(effect.state))
    return {
        "event_types": len(NPC_EVENT_LIBRARY),
        "role_schedules": len(ROLE_SCHEDULES),
        "schedule_entries": sum(len(schedule) for schedule in ROLE_SCHEDULES.values()),
        "preconditions": sum(precondition_kinds.values()),
        "precondition_kinds": _sorted_counter(precondition_kinds),
        "effects": sum(effect_kinds.values()),
        "effect_kinds": _sorted_counter(effect_kinds),
        "event_state_keys": sorted(event_state_keys),
    }


def summarize(scene_dir: Path) -> dict[str, Any]:
    paths = sorted(scene_dir.glob("*.json"))
    if not paths:
        raise RuntimeError(f"no scene JSON files found under {scene_dir}")

    node_types: Counter[str] = Counter()
    semantic_classes: Counter[str] = Counter()
    semantic_types: Counter[str] = Counter()
    state_keys: Counter[str] = Counter()
    actions: Counter[str] = Counter()
    relations: Counter[str] = Counter()
    edge_types: Counter[str] = Counter()
    profiles: Counter[str] = Counter()
    unique_node_ids: set[str] = set()
    unique_room_ids: set[str] = set()
    per_scene: list[dict[str, Any]] = []
    integrity = {"duplicate_node_ids": 0, "missing_parent_refs": 0, "broken_edge_refs": 0}

    for path in paths:
        scene = json.loads(path.read_text(encoding="utf-8"))
        nodes = list(scene.get("nodes") or [])
        edges = list(scene.get("edges") or [])
        ids = [str(node.get("id") or "") for node in nodes]
        id_set = {node_id for node_id in ids if node_id}
        profile = _scene_profile(path, scene)
        profiles[profile] += 1

        scene_node_types = Counter(str(node.get("node_type") or "") for node in nodes)
        scene_semantics = {
            str(node.get("semantic_type")) for node in nodes if node.get("semantic_type")
        }
        scene_states = {str(key) for node in nodes for key in (node.get("states") or {})}
        scene_actions = {str(action) for node in nodes for action in (node.get("interactive_actions") or [])}
        scene_relations = {str(edge.get("relation")) for edge in edges if edge.get("relation")}
        state_assignments = sum(len(node.get("states") or {}) for node in nodes)

        node_types.update(scene_node_types)
        semantic_classes.update(
            str(node.get("semantic_class")) for node in nodes if node.get("semantic_class")
        )
        semantic_types.update(
            str(node.get("semantic_type")) for node in nodes if node.get("semantic_type")
        )
        state_keys.update(str(key) for node in nodes for key in (node.get("states") or {}))
        actions.update(str(action) for node in nodes for action in (node.get("interactive_actions") or []))
        relations.update(str(edge.get("relation")) for edge in edges if edge.get("relation"))
        edge_types.update(str(edge.get("edge_type")) for edge in edges if edge.get("edge_type"))
        unique_node_ids.update(id_set)
        unique_room_ids.update(
            str(node.get("id")) for node in nodes if node.get("node_type") == "room" and node.get("id")
        )

        integrity["duplicate_node_ids"] += len(ids) - len(id_set)
        integrity["missing_parent_refs"] += sum(
            1 for node in nodes if node.get("parent") and str(node["parent"]) not in id_set
        )
        integrity["broken_edge_refs"] += sum(
            1
            for edge in edges
            if str(edge.get("source_id") or "") not in id_set
            or str(edge.get("target_id") or "") not in id_set
        )

        per_scene.append(
            {
                "scene": str(scene.get("scene_name") or path.stem),
                "domain": path.stem.split("__", 1)[0],
                "profile": profile,
                "nodes": len(nodes),
                "edges": len(edges),
                "rooms": scene_node_types.get("room", 0),
                "semantic_types": len(scene_semantics),
                "state_keys": len(scene_states),
                "state_assignments": state_assignments,
                "declared_actions": len(scene_actions),
                "relations": len(scene_relations),
            }
        )

    observed_states = set(state_keys)
    declared_actions = set(actions)
    observed_relations = set(relations)
    object_semantics = set(semantic_types) - NON_OBJECT_SEMANTICS
    resolved_object_semantics = {resolve_object_key(semantic) for semantic in object_semantics}
    runtime_actions = {action.value for action in ActionType}
    relation_schema = {relation.value for relation in SpatialRelation}

    return {
        "dataset": {
            "scene_instances": len(paths),
            "base_domains": len({item["domain"] for item in per_scene}),
            "profiles": _sorted_counter(profiles),
            "node_records": sum(item["nodes"] for item in per_scene),
            "edge_records": sum(item["edges"] for item in per_scene),
            "room_records": sum(item["rooms"] for item in per_scene),
            "unique_node_ids": len(unique_node_ids),
            "unique_room_ids": len(unique_room_ids),
            "semantic_types": len(semantic_types),
            "object_semantic_types": len(object_semantics),
            "observed_state_keys": len(observed_states),
            "state_assignments": sum(item["state_assignments"] for item in per_scene),
            "declared_interactive_actions": len(declared_actions),
            "observed_relations": len(observed_relations),
        },
        "distributions": {
            "node_types": _sorted_counter(node_types),
            "semantic_classes": _sorted_counter(semantic_classes),
            "state_keys": _sorted_counter(state_keys),
            "declared_actions": _sorted_counter(actions),
            "relations": _sorted_counter(relations),
            "edge_types": _sorted_counter(edge_types),
        },
        "schema": {
            "state_dimensions": len(DISCRETE_STATE_SPACE),
            "runtime_actions": len(runtime_actions),
            "relation_enum": len(relation_schema),
            "scored_relation_specs": len(RELATION_SPECS),
            "object_templates": len(OBJECT_LIBRARY),
            "room_templates": len(ROOM_LIBRARY),
            **_event_statistics(),
        },
        "coverage_gaps": {
            "schema_states_not_instantiated": sorted(set(DISCRETE_STATE_SPACE) - observed_states),
            "declared_actions_not_executable": sorted(declared_actions - runtime_actions),
            "relations_outside_enum": sorted(observed_relations - relation_schema),
            "scene_semantics_without_object_template": sorted(
                semantic for semantic in object_semantics if resolve_object_key(semantic) not in OBJECT_LIBRARY
            ),
            "object_templates_not_instantiated": sorted(set(OBJECT_LIBRARY) - resolved_object_semantics),
        },
        "integrity": integrity,
        "scenes": per_scene,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    dataset = summary["dataset"]
    schema = summary["schema"]
    lines = [
        "# GraphWorld Dataset Statistics",
        "",
        "## Overview",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Scene instances | {dataset['scene_instances']} |",
        f"| Base domains | {dataset['base_domains']} |",
        f"| Node records | {dataset['node_records']} |",
        f"| Edge records | {dataset['edge_records']} |",
        f"| Unique room IDs | {dataset['unique_room_ids']} |",
        f"| Object semantic types | {dataset['object_semantic_types']} |",
        f"| Observed/schema state dimensions | {dataset['observed_state_keys']} / {schema['state_dimensions']} |",
        f"| Declared/runtime actions | {dataset['declared_interactive_actions']} / {schema['runtime_actions']} |",
        f"| Observed/schema relations | {dataset['observed_relations']} / {schema['relation_enum']} |",
        f"| NPC event types | {schema['event_types']} |",
        f"| Role schedules | {schema['role_schedules']} |",
        "",
        "## Scenes",
        "",
        "| Scene | Profile | Nodes | Edges | Rooms | Semantics | States |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for scene in summary["scenes"]:
        lines.append(
            f"| {scene['scene']} | {scene['profile']} | {scene['nodes']} | {scene['edges']} | "
            f"{scene['rooms']} | {scene['semantic_types']} | {scene['state_keys']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize the GraphWorld static scene dataset and runtime schema.")
    parser.add_argument("--scene-dir", type=Path, default=DEFAULT_SCENE_DIR)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    summary = summarize(args.scene_dir)
    if args.format == "markdown":
        print(render_markdown(summary), end="")
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
