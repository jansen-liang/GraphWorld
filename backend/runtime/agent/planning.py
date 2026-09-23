from __future__ import annotations

from typing import Any

from backend.core.actions import ActionType, action_spec
from backend.core.resources import can_dispense
from backend.runtime.engine import Orchestrator


ACTION_ORDER = tuple(action.value for action in ActionType if action != ActionType.WAIT) + (ActionType.WAIT.value,)


def held_object(orchestrator: Orchestrator, agent_id: str = "robot_01") -> str:
    return orchestrator.graph.held_by(agent_id)


def candidate_payload(
    orchestrator: Orchestrator,
    action: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    validation = orchestrator.robot_actions.validate(action)
    result = {
        **action,
        "reason": reason,
        "legal": validation.ok,
        "validation_failures": list(validation.failures),
    }
    try:
        spec = action_spec(str(action.get("action") or ""))
        result["action_contract"] = {
            "category": spec.category,
            "parameters": list(spec.params),
            "description": spec.description,
            "mutates_edges": spec.mutates_edges,
            "mutates_states": spec.mutates_states,
            "effect_summary": list(spec.effect_summary),
        }
    except ValueError:
        result["action_contract"] = {}
    return result


def candidate_actions(orchestrator: Orchestrator, observation: dict[str, Any], agent_id: str = "robot_01") -> list[dict[str, Any]]:
    graph = orchestrator.graph
    candidates: list[dict[str, Any]] = []
    wait_candidate = candidate_payload(
        orchestrator,
        {"agent": agent_id, "action": "wait"},
        reason="advance time for a running process or natural transition",
    )
    if wait_candidate["legal"]:
        candidates.append(wait_candidate)
    visible_nodes = [graph.nodes.get(str(item.get("id") or "")) or {} for item in observation.get("nodes") or []]
    visible_ids = {str(node.get("id") or "") for node in visible_nodes if node.get("id")}
    holding = held_object(orchestrator, agent_id)
    if holding:
        consume_candidate = candidate_payload(
            orchestrator,
            {"agent": agent_id, "action": "consume", "object": holding},
            reason="consume held food or drink item",
        )
        if consume_candidate["legal"]:
            candidates.append(consume_candidate)
        candidate = candidate_payload(
            orchestrator,
            {"agent": agent_id, "action": "release", "object": holding},
            reason="release held object onto the floor",
        )
        if candidate["legal"]:
            candidates.append(candidate)
    for room_id in sorted((observation.get("world_state") or {}).get("visible_rooms") or []):
        if room_id and room_id != graph.room_of.get(agent_id):
            candidate = candidate_payload(
                orchestrator,
                {"agent": agent_id, "action": "move", "target": room_id},
                reason="move to visible room",
            )
            if candidate["legal"]:
                candidates.append(candidate)
    for node_id in sorted(visible_ids):
        item = graph.nodes.get(node_id) or {}
        if not item or node_id == agent_id:
            continue
        states = item.get("states") or {}
        actions = {str(action).lower() for action in item.get("interactive_actions") or []}
        if str(item.get("node_type") or "") in {"fixed_object", "control_object"}:
            candidate = candidate_payload(
                orchestrator,
                {"agent": agent_id, "action": "move", "target": node_id},
                reason="move near visible object",
            )
            if candidate["legal"]:
                candidates.append(candidate)
        for action_name in ACTION_ORDER:
            if action_name in {"move", "consume"}:
                continue
            if action_name == "place":
                if not holding:
                    continue
                action = {"agent": agent_id, "action": "place", "target": node_id, "object": holding}
            elif action_name == "pick":
                action = {"agent": agent_id, "action": "pick", "target": node_id, "object": node_id}
            else:
                action = {"agent": agent_id, "action": action_name, "target": node_id}
            if action_name == "press" and str(item.get("semantic_type") or "").lower() in {"elevator", "lift"}:
                for destination in item.get("served_rooms") or item.get("transport_rooms") or []:
                    elevator_action = {**action, "destination_room": str(destination)}
                    candidate = candidate_payload(orchestrator, elevator_action, reason=f"select elevator floor {destination}")
                    if candidate["legal"]:
                        candidates.append(candidate)
                continue
            if action_name == "dispense" and can_dispense(item):
                action = {"agent": agent_id, "action": "dispense", "target": node_id}
                candidate = candidate_payload(orchestrator, action, reason="dispense one resource instance")
                if candidate["legal"]:
                    candidates.append(candidate)
                continue
            if action_name == "place":
                volume_size = item.get("interior_size_cm") or item.get("container_size_cm") or item.get("placement_volume_cm")
                surface_size = item.get("surface_size_cm") or item.get("support_surface_cm")
                if volume_size:
                    action["placement_hint"] = "volume"
                    action["interior_size_cm"] = list(volume_size) if isinstance(volume_size, (list, tuple)) else volume_size
                else:
                    action["placement_hint"] = "surface"
                    if surface_size:
                        action["surface_size_cm"] = list(surface_size) if isinstance(surface_size, (list, tuple)) else surface_size
            reason = f"{action_name} visible object"
            if action_name in actions or action_name in {"move", "place"}:
                if states.get("is_dirty") is True and action_name == "brush":
                    reason = "restore dirty object"
                elif states.get("is_open") is True and action_name == "close":
                    reason = "close open object"
                candidate = candidate_payload(orchestrator, action, reason=reason)
                if candidate["legal"]:
                    candidates.append(candidate)
    deduped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for candidate in candidates:
        key = (
            str(candidate.get("action") or ""),
            str(candidate.get("target") or ""),
            str(candidate.get("object") or ""),
            str(candidate.get("destination_room") or candidate.get("target_room") or ""),
        )
        deduped[key] = candidate
    return sorted(
        deduped.values(),
        key=lambda item: (
            not bool(item.get("legal")),
            ACTION_ORDER.index(str(item.get("action") or "")) if str(item.get("action") or "") in ACTION_ORDER else 99,
            str(item.get("target") or ""),
        ),
    )


def plan(memory: dict[str, Any], task: str = "maintain_order") -> list[dict[str, Any]]:
    nodes = memory.get("nodes") or {}
    candidates: list[dict[str, Any]] = []
    for node_id, node in sorted(nodes.items()):
        states = node.get("states") or {}
        if str(node.get("door_kind") or "") in {"structural", "device"} and bool(states.get("is_open", False)):
            candidates.append(
                {
                    "action": "close",
                    "target": node_id,
                    "reason": "close open door",
                    "priority": 10,
                }
            )
    for node_id, node in sorted(nodes.items()):
        if bool((node.get("states") or {}).get("is_dirty", False)):
            candidates.append(
                {
                    "action": "brush",
                    "target": node_id,
                    "reason": "clean dirty object",
                    "priority": 8,
                }
            )
    return candidates


__all__ = ["ACTION_ORDER", "candidate_actions", "candidate_payload", "held_object", "plan"]
