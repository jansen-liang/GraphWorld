from __future__ import annotations

import copy
from typing import Any


def action_conflict_key(action: dict[str, Any]) -> tuple[str, str]:
    action_name = str(action.get("action") or "")
    target_id = str(action.get("target") or "")
    object_id = str(action.get("object") or "")
    if action_name == "pick" and object_id:
        return ("object", object_id)
    if action_name == "place" and object_id:
        return ("object", object_id)
    if action_name in {"brush", "fold", "dump", "open", "close", "press"} and target_id:
        return ("target", target_id)
    return ("", "")


def choose_non_conflicting_action(
    candidates: list[dict[str, Any]],
    blocked_keys: set[tuple[str, str]],
) -> dict[str, Any] | None:
    for preferred_action in ("move", "open", "close"):
        for candidate in candidates:
            if str(candidate.get("action") or "") != preferred_action:
                continue
            key = action_conflict_key(candidate)
            if not key[0] or key not in blocked_keys:
                replacement = copy.deepcopy(candidate)
                replacement["reason"] = f"conflict fallback: choose non-conflicting {preferred_action}"
                return replacement
    for candidate in candidates:
        key = action_conflict_key(candidate)
        if not key[0] or key not in blocked_keys:
            replacement = copy.deepcopy(candidate)
            replacement["reason"] = "conflict fallback: choose non-conflicting action"
            return replacement
    return None


def resolve_robot_action_conflicts(
    actions: list[dict[str, Any]],
    candidates_by_robot: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    used_keys: set[tuple[str, str]] = set()
    resolved: list[dict[str, Any]] = []
    for action in actions:
        robot_id = str(action.get("agent") or "")
        key = action_conflict_key(action)
        if key[0] and key in used_keys:
            replacement = choose_non_conflicting_action(candidates_by_robot.get(robot_id) or [], used_keys)
            if replacement:
                action = replacement
                key = action_conflict_key(action)
        resolved.append(action)
        if key[0]:
            used_keys.add(key)
    return resolved
