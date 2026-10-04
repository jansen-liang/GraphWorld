from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


TRANSITION_SCHEMA_VERSION = 1


def transition_id(event: dict[str, Any], index: int) -> str:
    """Derive a deterministic id without mutating legacy event payloads."""
    stable = {
        "index": int(index),
        "step": int(event.get("step") or 0),
        "type": str(event.get("type") or "event"),
        "payload": {str(key): value for key, value in sorted(event.items()) if key not in {"detail", "transition_id"}},
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str)
    return f"tr_{hashlib.sha1(encoded.encode('utf-8')).hexdigest()[:16]}"


def envelope_for_event(event: dict[str, Any], index: int) -> dict[str, Any]:
    event_type = str(event.get("type") or "event")
    step = int(event.get("step") or 0)
    return {
        "schema_version": TRANSITION_SCHEMA_VERSION,
        "transition_id": transition_id(event, index),
        "kind": "world_transition",
        "source": _source_for_event(event_type),
        "event_type": event_type,
        "step_before": max(0, step - 1),
        "step_after": step,
        "detail": str(event.get("detail") or ""),
        "effects": _effects_for_event(event),
        "event": copy.deepcopy(event),
    }


def transition_log(event_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [envelope_for_event(event, index) for index, event in enumerate(event_log) if isinstance(event, dict)]


def _source_for_event(event_type: str) -> str:
    if event_type.startswith("process_"):
        return "process"
    if event_type in {"timed_transition", "drying_completed", "water_depleted", "flower_wilted", "food_spoiled", "dirt_accumulated", "temperature_relaxed", "object_settled"}:
        return "timed_transition"
    if event_type.startswith("robot_action") or event_type in {"object_placed", "object_released", "object_consumed", "resource_loaded", "resource_dispensed", "resource_consumed", "tool_used"}:
        return "action"
    if event_type.startswith("human_"):
        return "human_event"
    return "rule"


def _effects_for_event(event: dict[str, Any]) -> dict[str, Any]:
    state_updates = event.get("state_updates") or event.get("updates") or {}
    resource_updates = event.get("resource_updates") or {}
    spawned = event.get("spawned_ids") or event.get("output_id")
    removed = event.get("removed_ids") or event.get("input_ids")
    effects: dict[str, Any] = {
        "state_updates": copy.deepcopy(state_updates) if isinstance(state_updates, dict) else {},
        "resource_updates": copy.deepcopy(resource_updates) if isinstance(resource_updates, dict) else {},
    }
    if spawned:
        effects["spawned"] = copy.deepcopy(spawned)
    if removed:
        effects["removed"] = copy.deepcopy(removed)
    for relation_key in ("parent", "target", "object_id", "item_id", "instance_id"):
        if relation_key in event:
            effects[relation_key] = copy.deepcopy(event[relation_key])
    return effects


__all__ = ["TRANSITION_SCHEMA_VERSION", "envelope_for_event", "transition_id", "transition_log"]
