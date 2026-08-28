"""Small data-driven process layer for production appliances.

Processes are intentionally stored in world state so they survive replay and
can be inspected by planners.  Object placement remains the source of truth
for recipe inputs; this module only schedules and commits the transition.
"""
from __future__ import annotations

from typing import Any

from .assets.object_library import build_object_node
from .predicates import children_of, mutable_states, node, semantic

RECIPE_SPECS = {
    "coffeemachine": {"duration": 2, "inputs": ("coffee_beans", "cup"), "output": "coffee"},
    "coffee_machine": {"duration": 2, "inputs": ("coffee_beans", "cup"), "output": "coffee"},
}


def _children_semantics(state: dict[str, Any], parent_id: str) -> list[tuple[str, str]]:
    return [(child_id, semantic(node(state, child_id))) for child_id in children_of(state, parent_id)]


def start_process(state: dict[str, Any], device_id: str) -> bool:
    device = node(state, device_id)
    device_semantic = semantic(device)
    if any(str(p.get("device_id")) == str(device_id) for p in state.get("processes", [])):
        return False
    states = mutable_states(device)
    if device_semantic == "printer":
        if float(states.get("count", 0) or 0) < 1 or float(states.get("amount", 0) or 0) < 1:
            return False
        states["count"] = max(0, int(float(states["count"]) - 1))
        states["amount"] = max(0, int(float(states["amount"]) - 1))
        output = "receipt"
        duration = 2
    elif device_semantic in RECIPE_SPECS:
        spec = RECIPE_SPECS[device_semantic]
        if not bool(states.get("has_water", False)):
            return False
        child_pairs = _children_semantics(state, device_id)
        available = [sem for _, sem in child_pairs]
        if not all(required in available for required in spec["inputs"]):
            return False
        states["has_water"] = False
        output = spec["output"]
        duration = int(spec["duration"])
    else:
        return False
    states["is_on"] = True
    states["is_running"] = True
    states["cycle_remaining"] = duration
    state.setdefault("processes", []).append({"device_id": str(device_id), "remaining": duration, "output": output})
    return True


def process_ready(state: dict[str, Any], device_id: str) -> bool:
    device = node(state, device_id)
    device_semantic = semantic(device)
    if device_semantic == "printer":
        states = device.get("states") or {}
        return float(states.get("count", 0) or 0) >= 1 and float(states.get("amount", 0) or 0) >= 1
    if device_semantic in RECIPE_SPECS:
        if not bool((device.get("states") or {}).get("has_water", False)):
            return False
        available = [sem for _, sem in _children_semantics(state, device_id)]
        return all(required in available for required in RECIPE_SPECS[device_semantic]["inputs"])
    return True


def advance_processes(state: dict[str, Any]) -> list[str]:
    completed: list[str] = []
    remaining_processes = []
    for process in state.get("processes", []):
        device_id = str(process.get("device_id") or "")
        device = node(state, device_id)
        if not device:
            continue
        left = max(0, int(process.get("remaining") or 0) - 1)
        process["remaining"] = left
        mutable_states(device)["cycle_remaining"] = left
        if left > 0:
            remaining_processes.append(process)
            continue
        device_states = mutable_states(device)
        device_states["is_on"] = False
        device_states["is_running"] = False
        output_type = str(process.get("output") or "receipt")
        if output_type == "coffee":
            # Consume recipe inputs except the reusable cup, then spawn output.
            for child_id, child_semantic in _children_semantics(state, device_id):
                if child_semantic == "coffee_beans":
                    state.get("nodes", {}).pop(child_id, None)
                    state.get("parent_of", {}).pop(child_id, None)
                    state.get("relation_of", {}).pop(child_id, None)
            cup_id = next((child_id for child_id, sem in _children_semantics(state, device_id) if sem == "cup"), device_id)
            output_id = f"coffee_{int(state.setdefault('world_state', {}).get('step', 0))}_{len(state.get('nodes', {}))}"
            output = build_object_node(output_id, output_type, parent=cup_id)
            state.setdefault("nodes", {})[output_id] = output
            state.setdefault("parent_of", {})[output_id] = cup_id
            state.setdefault("relation_of", {})[output_id] = "in"
        else:
            output_id = f"receipt_{int(state.setdefault('world_state', {}).get('step', 0))}_{len(state.get('nodes', {}))}"
            output = build_object_node(output_id, output_type, parent=device_id)
            state.setdefault("nodes", {})[output_id] = output
            state.setdefault("parent_of", {})[output_id] = device_id
            state.setdefault("relation_of", {})[output_id] = "on"
        completed.append(device_id)
    # Keep the world-state list identity intact; SceneGraph exposes it as the
    # rule-state process registry and replacing it would leave a stale alias.
    processes = state.setdefault("processes", [])
    processes[:] = remaining_processes
    return completed


__all__ = ["RECIPE_SPECS", "advance_processes", "process_ready", "start_process"]
