from __future__ import annotations

import copy
from typing import Any

from backend.runtime.scene_utils import parent_of, relation_of, room_of

def _blocking_targets_satisfied(case: dict[str, Any], scene: dict[str, Any]) -> bool:
    nodes = {str(node.get("id") or ""): node for node in scene.get("nodes") or [] if node.get("id")}
    target = str(case.get("target") or "")
    parent = str(case.get("parent") or "")
    states = dict(case.get("states") or {})
    room = str(case.get("room") or "")
    relation_not = str(case.get("relation_not") or "")
    semantic_type = str(case.get("semantic_type") or "")
    semantic_types = {str(item) for item in case.get("semantic_types") or [] if str(item)}

    def node_matches(node_id: str) -> bool:
        node = nodes.get(node_id) or {}
        if not node:
            return False
        if target and node_id != target:
            return False
        if semantic_type and str(node.get("semantic_type") or "") != semantic_type:
            return False
        if semantic_types and str(node.get("semantic_type") or "") not in semantic_types:
            return False
        if parent and parent_of(scene, node_id) != parent:
            return False
        if room and room_of(scene, node_id) != room:
            return False
        if relation_not and relation_of(scene, node_id) == relation_not:
            return False
        node_states = node.get("states") or {}
        return all(node_states.get(key) == value for key, value in states.items())

    target_ids = [str(item) for item in case.get("blocking_target_ids") or [] if str(item)]
    if target_ids:
        return any(node_matches(node_id) for node_id in target_ids)

    if semantic_types:
        available = {
            str(node.get("semantic_type") or "")
            for node_id, node in nodes.items()
            if not room or room_of(scene, node_id) == room
        }
        return semantic_types.issubset(available)

    return any(node_matches(node_id) for node_id in nodes)


def update_blocking_cases(
    cases: list[dict[str, Any]],
    current_scene: dict[str, Any],
    actions: list[dict[str, Any]],
    step: int,
) -> None:
    primary_action = actions[0] if actions else {}
    resolution_action = f"{primary_action.get('action', '')}:{primary_action.get('target', '')}"
    for case in cases:
        if str(case.get("status") or "") != "open":
            continue
        if not bool(case.get("recoverable", False)):
            continue
        if _blocking_targets_satisfied(case, current_scene):
            case["status"] = "resolved"
            case["resolved_step"] = step
            case["resolved_by_robot"] = bool(actions)
            case["resolution_action"] = resolution_action


def finalize_blocking_case_outcomes(
    cases: list[dict[str, Any]],
    human_events: list[dict[str, Any]],
) -> None:
    event_outcomes = {str(item.get("event") or ""): bool(item.get("ok", False)) for item in human_events if item.get("event")}
    for case in cases:
        if str(case.get("status") or "") != "resolved":
            continue
        event_id = str(case.get("event_id") or "")
        if event_id in event_outcomes and event_outcomes[event_id]:
            case["status"] = "closed_success"
