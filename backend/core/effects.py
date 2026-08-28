from __future__ import annotations

from typing import Any

from .domain_rules import APPLIANCE_CYCLE_STEPS, CLOTH_SEMANTICS, DUMP_RULES, SURFACE_SEMANTICS
from .predicates import (
    children_of,
    controlled_targets,
    holding,
    is_container_door,
    mutable_states,
    node,
    node_type,
    parent_of,
    semantic,
)
from .states import DiscreteState
from .processes import start_process


def move_node(state: dict[str, Any], node_id: str, parent_id: str, relation: str) -> None:
    item = node(state, node_id)
    if not item:
        return
    item["parent"] = parent_id
    item["runtime_relation"] = relation
    state.setdefault("parent_of", {})[node_id] = parent_id
    state.setdefault("relation_of", {})[node_id] = relation
    parent = node(state, parent_id)
    state.setdefault("room_of", {})[node_id] = parent_id if node_type(parent) == "room" else str(state.get("room_of", {}).get(parent_id) or "")


def open_target(state: dict[str, Any], target_id: str) -> None:
    target = node(state, target_id)
    target_states = mutable_states(target)
    if semantic(target) == "faucet":
        target_states[DiscreteState.IS_ON.value] = True
        _set_controlled_sink_water(state, target_id, True)
        return
    target_states[DiscreteState.IS_OPEN.value] = True
    parent = node(state, parent_of(state, target_id))
    if parent and (str(target.get("door_kind") or "").lower() == "device" or is_container_door(state, target_id)):
        mutable_states(parent)[DiscreteState.IS_OPEN.value] = True
    for child_id, child_parent in state.get("parent_of", {}).items():
        if child_parent != target_id:
            continue
        child = node(state, child_id)
        if str(child.get("door_kind") or "") == "device":
            mutable_states(child)[DiscreteState.IS_OPEN.value] = True


def close_target(state: dict[str, Any], target_id: str) -> None:
    target = node(state, target_id)
    target_states = mutable_states(target)
    if semantic(target) == "faucet":
        target_states[DiscreteState.IS_ON.value] = False
        _set_controlled_sink_water(state, target_id, False)
        return
    target_states[DiscreteState.IS_OPEN.value] = False
    parent = node(state, parent_of(state, target_id))
    if parent and (str(target.get("door_kind") or "").lower() == "device" or is_container_door(state, target_id)):
        mutable_states(parent)[DiscreteState.IS_OPEN.value] = False
    for child_id, child_parent in state.get("parent_of", {}).items():
        if child_parent != target_id:
            continue
        child = node(state, child_id)
        if str(child.get("door_kind") or "") == "device":
            mutable_states(child)[DiscreteState.IS_OPEN.value] = False


def press_target(state: dict[str, Any], target_id: str) -> None:
    target = node(state, target_id)
    target_states = mutable_states(target)
    target_states[DiscreteState.IS_PRESSED.value] = True
    target_semantic = semantic(target)
    if target_semantic != "printer" and "finite_resource" in {str(cap).lower() for cap in (target.get("capabilities") or [])}:
        for resource_key in (DiscreteState.USES_LEFT.value, DiscreteState.COUNT.value, DiscreteState.AMOUNT.value):
            if resource_key in target_states:
                remaining = max(0.0, float(target_states.get(resource_key) or 0.0) - 1.0)
                target_states[resource_key] = int(remaining) if remaining.is_integer() else round(remaining, 4)
                break
    if target_semantic == "faucet":
        target_states[DiscreteState.IS_ON.value] = not bool(target_states.get(DiscreteState.IS_ON.value, False))
        _set_controlled_sink_water(state, target_id, bool(target_states[DiscreteState.IS_ON.value]))
        return
    if target_semantic in APPLIANCE_CYCLE_STEPS:
        target_states[DiscreteState.IS_ON.value] = True
        target_states[DiscreteState.IS_RUNNING.value] = True
        target_states[DiscreteState.CYCLE_REMAINING.value] = APPLIANCE_CYCLE_STEPS[target_semantic]
        if target_semantic in {"printer", "coffeemachine", "coffee_machine"}:
            start_process(state, target_id)
    for controlled_id in controlled_targets(state, target_id):
        controlled = node(state, controlled_id)
        controlled_states = mutable_states(controlled)
        controlled_semantic = semantic(controlled)
        duration = APPLIANCE_CYCLE_STEPS.get(controlled_semantic)
        if duration:
            controlled_states[DiscreteState.IS_ON.value] = True
            controlled_states[DiscreteState.IS_RUNNING.value] = True
            controlled_states[DiscreteState.CYCLE_REMAINING.value] = duration
            if controlled_semantic in {"printer", "coffeemachine", "coffee_machine"}:
                start_process(state, controlled_id)
        elif DiscreteState.IS_ON.value in controlled_states:
            controlled_states[DiscreteState.IS_ON.value] = not bool(controlled_states.get(DiscreteState.IS_ON.value, False))
        if controlled_semantic in {"air_conditioner", "air_conditioning", "aircon"}:
            _apply_air_conditioner_environment(state, controlled_id, bool(controlled_states.get(DiscreteState.IS_ON.value, False)))
    if target_semantic not in APPLIANCE_CYCLE_STEPS and DiscreteState.IS_ON.value in target_states:
        target_states[DiscreteState.IS_ON.value] = not bool(target_states.get(DiscreteState.IS_ON.value, False))
    if target_semantic in {"air_conditioner", "air_conditioning", "aircon"}:
        _apply_air_conditioner_environment(state, target_id, bool(target_states.get(DiscreteState.IS_ON.value, False)))


def _apply_air_conditioner_environment(state: dict[str, Any], device_id: str, is_on: bool) -> None:
    """Minimal discrete HVAC coupling: on cools its room, off releases it."""
    room_id = str(state.get("room_of", {}).get(device_id) or "")
    if not room_id:
        return
    world = state.setdefault("world_state", {})
    room_temperatures = world.setdefault("room_temperature", {})
    if is_on:
        room_temperatures[room_id] = "cold"
    else:
        baseline = str(world.get("temperature") or "comfortable")
        room_temperatures[room_id] = {"comfortable": "room"}.get(baseline, baseline)


def brush_target(state: dict[str, Any], target_id: str) -> None:
    target = node(state, target_id)
    if semantic(target) in CLOTH_SEMANTICS:
        return
    target_states = mutable_states(target)
    target_states[DiscreteState.IS_DIRTY.value] = False
    if semantic(target) in {"sink", "trash_bin", "bin", "basket", "container"}:
        if DiscreteState.FILL_LEVEL.value in target_states:
            target_states[DiscreteState.FILL_LEVEL.value] = 0.0
        if DiscreteState.IS_FULL.value in target_states:
            target_states[DiscreteState.IS_FULL.value] = False


def _set_controlled_sink_water(state: dict[str, Any], faucet_id: str, has_water: bool) -> None:
    """A faucet controls a sink's binary water state; no sink volume is modeled."""
    for sink_id in controlled_targets(state, faucet_id):
        sink = node(state, sink_id)
        if semantic(sink) == "sink":
            mutable_states(sink)["has_water"] = has_water


def _apply_sink_entry_effect(state: dict[str, Any], object_id: str, sink_id: str) -> None:
    sink = node(state, sink_id)
    if semantic(sink) != "sink" or not mutable_states(sink).get("has_water", False):
        return
    item = node(state, object_id)
    item_states = mutable_states(item)
    item_semantic = semantic(item)
    if item_semantic in {"cup", "mug", "bowl", "vase", "bottle", "winebottle", "pot", "pan", "container", "coffeemachine", "coffee_machine"}:
        item_states["has_water"] = True
        item_states["is_full"] = True
    elif item_semantic in {"clothes", "towel", "blanket", "shoes", "paper_towel"}:
        item_states[DiscreteState.IS_WET.value] = True


def fold_target(state: dict[str, Any], target_id: str) -> None:
    mutable_states(node(state, target_id))[DiscreteState.FOLDED.value] = True


def place_relation_for_target(target: dict[str, Any]) -> str:
    return "on" if semantic(target) in SURFACE_SEMANTICS else "in"


def dump_held_container(state: dict[str, Any], actor_id: str, target_id: str) -> None:
    held_id = holding(state, actor_id)
    held = node(state, held_id)
    rule = DUMP_RULES.get(semantic(held))
    if not rule:
        return
    if rule.effect == "empty_trash_bin":
        for child_id in list(children_of(state, held_id)):
            child = node(state, child_id)
            child_states = mutable_states(child)
            child_states["is_rotten"] = False
            child_states["is_burnt"] = False
            if semantic(child) == "food":
                fridge_id = next(
                    (
                        node_id
                        for node_id, item in state.get("nodes", {}).items()
                        if semantic(item) in {"refrigerator", "fridge"}
                    ),
                    "",
                )
                move_node(state, child_id, fridge_id or target_id, "in")
            else:
                move_node(state, child_id, target_id, "in")
        mutable_states(held)[DiscreteState.IS_DIRTY.value] = False
    elif rule.effect == "empty_fill_level":
        held_states = mutable_states(held)
        held_states[DiscreteState.FILL_LEVEL.value] = 0.0
        held_states[DiscreteState.IS_FULL.value] = False


__all__ = [
    "brush_target",
    "close_target",
    "dump_held_container",
    "fold_target",
    "move_node",
    "_apply_sink_entry_effect",
    "open_target",
    "place_relation_for_target",
    "press_target",
]
