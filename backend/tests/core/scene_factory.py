"""Small builder for canonical scenes used by tests."""

from copy import deepcopy
from typing import Any


def scene_v2(value: dict[str, Any]) -> dict[str, Any]:
    scene = deepcopy(value)
    nodes = scene.setdefault("nodes", [])
    edges = scene.setdefault("edges", [])
    known_ids = {str(item.get("id") or "") for item in nodes if isinstance(item, dict)}
    for item in nodes:
        if not isinstance(item, dict):
            continue
        item["editor_id"] = str(item.get("id") or "")
        item.setdefault("node_type", "object")
        parent_id = str(item.pop("host_id", "") or item.pop("parent", "") or item.pop("floor_id", "") or "")
        relation = str(item.pop("runtime_relation", "") or ("at" if item.get("node_type") == "agent" else "inside"))
        if parent_id and parent_id in known_ids and not any(
            edge.get("source_id") == parent_id and edge.get("target_id") == item["id"]
            for edge in edges
        ):
            edges.append({"source_id": parent_id, "target_id": item["id"], "relation": relation})
    scene["schema_version"] = 2
    scene["id_namespace"] = "editor"
    return scene
