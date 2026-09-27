from __future__ import annotations

from typing import Any

from backend.core.model import POSITION_RELATIONS

def node(scene: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    for item in scene.get("nodes") or []:
        if item.get("id") == node_id:
            return item
    return None


def parent_of(scene: dict[str, Any], node_id: str) -> str:
    wanted = str(node_id or "")
    for edge in reversed(scene.get("edges") or []):
        if str(edge.get("target_id") or "") != wanted:
            continue
        if str(edge.get("relation") or "").lower() in POSITION_RELATIONS:
            return str(edge.get("source_id") or "")
    return ""


def room_of(scene: dict[str, Any], node_id: str) -> str:
    current_id = str(node_id or "")
    visited: set[str] = set()
    while current_id and current_id not in visited:
        visited.add(current_id)
        item = node(scene, current_id)
        if not item:
            return ""
        node_type = str(item.get("node_type") or "")
        if node_type == "room":
            return current_id
        current_id = parent_of(scene, current_id)
    return ""


def relation_of(scene: dict[str, Any], node_id: str) -> str:
    for edge in reversed(scene.get("edges") or []):
        if str(edge.get("target_id") or "") != str(node_id or ""):
            continue
        relation = str(edge.get("relation") or "").lower()
        if relation in POSITION_RELATIONS:
            return relation
    return ""


def scene_type(scene: dict[str, Any]) -> str:
    name = str(scene.get("scene_name") or "")
    if "hospital" in name:
        return "hospital"
    if "supermarket" in name:
        return "supermarket"
    if "office" in name:
        return "office"
    if "factory" in name:
        return "factory"
    return "home"
