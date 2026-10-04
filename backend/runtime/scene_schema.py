"""Validation for canonical editor-scene payloads."""

from __future__ import annotations

import copy
from typing import Any

from backend.core.node import NodeType
from backend.core.articulation import JOINT_TYPES


def validate_canonical_scene(scene: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(scene, dict) or scene.get("schema_version") != 2 or scene.get("id_namespace") != "editor":
        raise ValueError("scene must use schema_version=2 and id_namespace=editor")
    nodes = scene.get("nodes")
    edges = scene.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("canonical scene must contain nodes and edges lists")
    node_ids: set[str] = set()
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for item in nodes:
        if not isinstance(item, dict):
            raise ValueError("scene node must be an object")
        node_id = str(item.get("id") or "")
        if not node_id or node_id in node_ids:
            raise ValueError(f"duplicate or missing node id: {node_id}")
        if str(item.get("editor_id") or node_id) != node_id:
            raise ValueError(f"node editor_id must match id: {node_id}")
        if str(item.get("node_type") or "") not in {value.value for value in NodeType}:
            raise ValueError(f"unsupported canonical node type: {item.get('node_type')}")
        if any(key in item for key in ("parent", "child", "inventory", "floor_id", "runtime_relation")):
            raise ValueError(f"legacy relationship field on node: {node_id}")
        node_ids.add(node_id)
        nodes_by_id[node_id] = item
    room_ids = {node_id for node_id, item in nodes_by_id.items() if str(item.get("node_type") or "") == "room"}
    layout_doors = (scene.get("layout") or {}).get("doors") or {}
    if isinstance(layout_doors, dict):
        for door_id, layout_door in layout_doors.items():
            door_node = nodes_by_id.get(str(door_id))
            if door_node is None or str(door_node.get("semantic_type") or "").lower() != "door":
                raise ValueError(f"layout door must have a corresponding door node: {door_id}")
            if not isinstance(layout_door, dict):
                raise ValueError(f"layout door definition must be an object: {door_id}")
    for node_id, item in nodes_by_id.items():
        if str(item.get("semantic_type") or "").lower() != "door":
            continue
        if str(item.get("door_kind") or "structural").lower() != "structural":
            continue
        connected_rooms = item.get("connected_rooms")
        if node_id not in layout_doors and not connected_rooms:
            # Device/component doors are local structure, not room portals.
            continue
        if not isinstance(connected_rooms, list) or len(connected_rooms) != 2:
            raise ValueError(f"structural door node must declare connected_rooms[2]: {node_id}")
        if any(str(room_id) not in room_ids for room_id in connected_rooms):
            raise ValueError(f"structural door connected_rooms must reference room nodes: {node_id}")
    structure_parent: dict[str, str] = {}
    for edge in edges:
        if not isinstance(edge, dict) or str(edge.get("source_id") or "") not in node_ids or str(edge.get("target_id") or "") not in node_ids:
            raise ValueError("canonical edge references an unknown node")
        relation = str(edge.get("relation") or "").lower()
        if not relation:
            raise ValueError("canonical edge relation is required")
        if relation != "structure":
            continue
        properties = edge.get("properties")
        if not isinstance(properties, dict):
            raise ValueError("structure edge properties are required")
        parent = str(properties.get("parent") or edge.get("parent") or "")
        child = str(properties.get("child") or edge.get("child") or "")
        if parent not in node_ids or child not in node_ids:
            raise ValueError("structure edge parent and child must reference nodes")
        if parent == child:
            raise ValueError(f"structure edge cannot self-link: {parent}")
        parent_type = str(nodes_by_id[parent].get("node_type") or "")
        child_type = str(nodes_by_id[child].get("node_type") or "")
        if parent_type not in {"object", "agent"} or child_type not in {"object", "agent"}:
            raise ValueError("structure edges may only connect object or agent nodes")
        parent_owner = _structure_owner(parent, nodes_by_id)
        child_owner = _structure_owner(child, nodes_by_id)
        if parent_owner != child_owner:
            raise ValueError("structure edge cannot cross object assets or agent assets")
        if str(nodes_by_id[child].get("role") or "root") != "component":
            raise ValueError("structure edge child must have role=component")
        joint_type = str(properties.get("joint_type") or "fixed").lower()
        if joint_type not in JOINT_TYPES:
            raise ValueError(f"unsupported structure joint type: {joint_type}")
        if child in structure_parent and structure_parent[child] != parent:
            raise ValueError("component has multiple structure parents")
        structure_parent[child] = parent
    for child in structure_parent:
        seen: set[str] = set()
        current = child
        while current in structure_parent:
            if current in seen:
                raise ValueError(f"structure graph contains a cycle at: {current}")
            seen.add(current)
            current = structure_parent[current]
    return copy.deepcopy(scene)


def _structure_owner(node_id: str, nodes_by_id: dict[str, dict[str, Any]]) -> str:
    """Resolve the root object owner for a component without mutating nodes."""
    current = node_id
    seen: set[str] = set()
    while current not in seen:
        seen.add(current)
        node = nodes_by_id[current]
        owner = str(node.get("owner_id") or node.get("object_id") or "")
        if owner and owner in nodes_by_id and owner != current:
            current = owner
            continue
        return current
    return current


__all__ = ["validate_canonical_scene"]
