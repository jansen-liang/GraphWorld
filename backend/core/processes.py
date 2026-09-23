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
    "printer": {"duration": 2, "inputs": (), "output": "receipt", "output_states": {}, "requires_water": False, "preserve": (), "resource_costs": {"count": 1, "amount": 1}},
    "coffeemachine": {"duration": 2, "inputs": ("coffee_beans", "cup"), "output": "coffee", "output_states": {"temperature": "hot"}, "requires_water": True, "preserve": ("cup",)},
    "coffee_machine": {"duration": 2, "inputs": ("coffee_beans", "cup"), "output": "coffee", "output_states": {"temperature": "hot"}, "requires_water": True, "preserve": ("cup",)},
    "workbench": {"duration": 3, "inputs": ("bread", "tomato"), "output": "sandwich", "output_states": {"is_cooked": False, "temperature": "room"}, "requires_water": False, "preserve": ()},
    # A multi-station-friendly production primitive. Inputs may be delivered
    # by another station and placed inside the line before starting it.
    "assembly_line": {"duration": 4, "inputs": ("component_a", "component_b"), "output": "finished_product", "output_states": {}, "requires_water": False, "preserve": ()},
    "stove": {"duration": 3, "inputs": ("egg",), "output": "cooked_egg", "output_states": {"is_cooked": True, "temperature": "hot"}, "requires_water": False, "preserve": ()},
}

PROCESS_WATER_COST = 25.0


def _water_level(states: dict[str, Any]) -> float:
    if "water_level" in states:
        try:
            return max(0.0, float(states.get("water_level") or 0.0))
        except (TypeError, ValueError):
            return 0.0
    return 100.0 if bool(states.get("has_water", False)) else 0.0


def _children_semantics(state: dict[str, Any], parent_id: str) -> list[tuple[str, str]]:
    return [(child_id, semantic(node(state, child_id))) for child_id in children_of(state, parent_id)]


def start_process(state: dict[str, Any], device_id: str) -> bool:
    device = node(state, device_id)
    device_semantic = semantic(device)
    if any(str(p.get("device_id")) == str(device_id) for p in state.get("processes", [])):
        return False
    states = mutable_states(device)
    if device_semantic in RECIPE_SPECS:
        spec = RECIPE_SPECS[device_semantic]
        if spec.get("requires_water") and _water_level(states) < PROCESS_WATER_COST:
            return False
        for resource_key, cost in (spec.get("resource_costs") or {}).items():
            if float(states.get(resource_key, 0) or 0) < float(cost):
                return False
        child_pairs = _children_semantics(state, device_id)
        available = [sem for _, sem in child_pairs]
        if not all(required in available for required in spec["inputs"]):
            return False
        if spec.get("requires_water"):
            remaining_water = max(0.0, _water_level(states) - PROCESS_WATER_COST)
            states["water_level"] = remaining_water
            states["has_water"] = remaining_water > 0.0
        for resource_key, cost in (spec.get("resource_costs") or {}).items():
            remaining = max(0.0, float(states.get(resource_key, 0) or 0) - float(cost))
            states[resource_key] = int(remaining) if remaining.is_integer() else round(remaining, 4)
        output = spec["output"]
        duration = int(spec["duration"])
    else:
        return False
    states["is_on"] = True
    states["is_running"] = True
    states["cycle_remaining"] = duration
    process = {
        "device_id": str(device_id),
        "remaining": duration,
        "output": output,
        "recipe": str(device_semantic),
        "started_step": int(state.setdefault("world_state", {}).get("step", 0) or 0),
    }
    state.setdefault("processes", []).append(process)
    state.setdefault("world_state", {}).setdefault("event_log", []).append({
        "type": "process_started",
        "device_id": str(device_id),
        "output": output,
        "recipe": str(device_semantic),
        "duration": duration,
        "input_ids": [child_id for child_id, child_sem in _children_semantics(state, device_id) if child_sem in spec.get("inputs", ())],
    })
    return True


def process_ready(state: dict[str, Any], device_id: str) -> bool:
    device = node(state, device_id)
    device_semantic = semantic(device)
    if device_semantic in RECIPE_SPECS:
        spec = RECIPE_SPECS[device_semantic]
        if spec.get("requires_water") and _water_level(device.get("states") or {}) < PROCESS_WATER_COST:
            return False
        states = device.get("states") or {}
        if any(float(states.get(key, 0) or 0) < float(cost) for key, cost in (spec.get("resource_costs") or {}).items()):
            return False
        available = [sem for _, sem in _children_semantics(state, device_id)]
        return all(required in available for required in spec["inputs"])
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
        spec = RECIPE_SPECS.get(semantic(device), {})
        preserve = set(spec.get("preserve", ()))
        for child_id, child_semantic in _children_semantics(state, device_id):
            if child_semantic in spec.get("inputs", ()) and child_semantic not in preserve:
                state.setdefault("world_state", {}).setdefault("event_log", []).append({
                    "type": "process_consumed",
                    "device_id": device_id,
                    "item_id": child_id,
                    "semantic_type": child_semantic,
                })
                state.get("nodes", {}).pop(child_id, None)
                state.get("parent_of", {}).pop(child_id, None)
                state.get("relation_of", {}).pop(child_id, None)
        output_parent = device_id
        output_relation = "on"
        if output_type == "coffee":
            output_parent = next((child_id for child_id, sem in _children_semantics(state, device_id) if sem == "cup"), device_id)
            output_relation = "in"
        output_id = f"{output_type}_{int(state.setdefault('world_state', {}).get('step', 0))}_{len(state.get('nodes', {}))}"
        output = build_object_node(output_id, output_type, parent=output_parent)
        output["produced_by_device"] = device_id
        output["produced_by_recipe"] = str(process.get("recipe") or semantic(device))
        output["produced_at_step"] = int(state.setdefault("world_state", {}).get("step", 0) or 0)
        output["output_relation"] = output_relation
        output_states = output.setdefault("states", {})
        output_states.update(dict(spec.get("output_states") or {}))
        state.setdefault("nodes", {})[output_id] = output
        state.setdefault("parent_of", {})[output_id] = output_parent
        state.setdefault("relation_of", {})[output_id] = output_relation
        state.setdefault("world_state", {}).setdefault("event_log", []).append({
            "type": "process_completed",
            "device_id": device_id,
            "output_id": output_id,
            "output": output_type,
            "recipe": str(process.get("recipe") or semantic(device)),
            "produced_at_step": output["produced_at_step"],
        })
        completed.append(device_id)
    # Keep the world-state list identity intact; SceneGraph exposes it as the
    # rule-state process registry and replacing it would leave a stale alias.
    processes = state.setdefault("processes", [])
    processes[:] = remaining_processes
    return completed


__all__ = ["RECIPE_SPECS", "advance_processes", "process_ready", "start_process"]
