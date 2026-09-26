from __future__ import annotations

from typing import Any

from .domain_rules import APPLIANCE_CYCLE_STEPS, DUMP_RULES, SURFACE_SEMANTICS
from .predicates import (
    children_of,
    descendants_of,
    controlled_targets,
    holding,
    is_container_door,
    mutable_states,
    node,
    node_type,
    object_capabilities,
    object_property,
    parent_of,
    semantic,
)
from .states import DiscreteState
from .processes import RECIPE_SPECS, start_process
from .temporal import apply_effects, temporal_effects, profile_duration


def _process_duration(item: dict[str, Any]) -> int:
    """Return the configured cycle length, with legacy semantic fallback."""
    configured = profile_duration(item)
    if configured:
        return configured
    return int(APPLIANCE_CYCLE_STEPS.get(semantic(item), 0))


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
    if "water_source_control" in object_capabilities(target):
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
    if "water_source_control" in object_capabilities(target):
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


def press_target(state: dict[str, Any], target_id: str, payload: dict[str, Any] | None = None) -> None:
    target = node(state, target_id)
    target_states = mutable_states(target)
    target_states[DiscreteState.IS_PRESSED.value] = True
    target_semantic = semantic(target)
    if target_semantic in {"elevator", "lift"}:
        destination = str((payload or {}).get("destination_room") or (payload or {}).get("target_room") or "")
        target["requested_room"] = destination
        target_states[DiscreteState.IS_OPEN.value] = False
        target_states[DiscreteState.IS_RUNNING.value] = True
        target_states[DiscreteState.CYCLE_REMAINING.value] = APPLIANCE_CYCLE_STEPS.get("elevator", 2)
        state.setdefault("world_state", {}).setdefault("event_log", []).append({
            "type": "elevator_departed",
            "elevator_id": str(target_id),
            "destination_room": destination,
        })
        return
    if target_semantic != "printer" and "finite_resource" in {str(cap).lower() for cap in (target.get("capabilities") or [])}:
        for resource_key in (DiscreteState.USES_LEFT.value, DiscreteState.COUNT.value, DiscreteState.AMOUNT.value):
            if resource_key in target_states:
                remaining = max(0.0, float(target_states.get(resource_key) or 0.0) - 1.0)
                target_states[resource_key] = int(remaining) if remaining.is_integer() else round(remaining, 4)
                break
    if "water_source_control" in object_capabilities(target):
        target_states[DiscreteState.IS_ON.value] = not bool(target_states.get(DiscreteState.IS_ON.value, False))
        _set_controlled_sink_water(state, target_id, bool(target_states[DiscreteState.IS_ON.value]))
        return
    target_duration = _process_duration(target)
    if target_duration:
        _consume_appliance_detergent(state, target_id)
        target_states[DiscreteState.IS_ON.value] = True
        target_states[DiscreteState.IS_RUNNING.value] = True
        target_states[DiscreteState.CYCLE_REMAINING.value] = target_duration
        _apply_process_start_effects(state, target_id)
        if target_semantic in RECIPE_SPECS:
            start_process(state, target_id)
    for controlled_id in controlled_targets(state, target_id):
        controlled = node(state, controlled_id)
        controlled_states = mutable_states(controlled)
        controlled_semantic = semantic(controlled)
        duration = _process_duration(controlled)
        if duration:
            _consume_appliance_detergent(state, controlled_id)
            controlled_states[DiscreteState.IS_ON.value] = True
            controlled_states[DiscreteState.IS_RUNNING.value] = True
            controlled_states[DiscreteState.CYCLE_REMAINING.value] = duration
            _apply_process_start_effects(state, controlled_id)
            if controlled_semantic in RECIPE_SPECS:
                start_process(state, controlled_id)
        if controlled_semantic == "toilet":
            controlled_states[DiscreteState.IS_DIRTY.value] = False
        elif controlled_semantic == "door" and str(controlled.get("door_kind") or "") == "structural":
            controlled_states[DiscreteState.IS_OPEN.value] = True
        elif DiscreteState.IS_ON.value in controlled_states:
            controlled_states[DiscreteState.IS_ON.value] = not bool(controlled_states.get(DiscreteState.IS_ON.value, False))
        _apply_environment_effect(state, controlled_id, bool(controlled_states.get(DiscreteState.IS_ON.value, False)))
    if not target_duration and DiscreteState.IS_ON.value in target_states:
        target_states[DiscreteState.IS_ON.value] = not bool(target_states.get(DiscreteState.IS_ON.value, False))
    _apply_environment_effect(state, target_id, bool(target_states.get(DiscreteState.IS_ON.value, False)))


def _consume_appliance_detergent(state: dict[str, Any], appliance_id: str) -> None:
    """Consume one loaded resource matching the device capability contract."""
    appliance = node(state, appliance_id)
    required = {
        str(value).lower()
        for value in (appliance.get("required_process_capabilities") or object_property(appliance, "required_process_capabilities", ()) or ())
    }
    if not required:
        return
    detergent_id = next(
        (
            child_id
            for child_id in descendants_of(state, appliance_id)
            if object_capabilities(node(state, child_id)) & required
        ),
        None,
    )
    if not detergent_id:
        return
    state.setdefault("world_state", {}).setdefault("event_log", []).append({
        "type": "resource_consumed",
        "source_id": str(node(state, detergent_id).get("resource_instance_of") or ""),
        "instance_id": str(detergent_id),
        "device_id": str(appliance_id),
        "resource_semantic_type": semantic(node(state, detergent_id)),
    })
    state.get("nodes", {}).pop(detergent_id, None)
    state.get("parent_of", {}).pop(detergent_id, None)
    state.get("relation_of", {}).pop(detergent_id, None)


def _apply_process_start_effects(state: dict[str, Any], device_id: str) -> None:
    """Apply only immediate effects declared by contained capabilities.

    Long-running effects remain in the timed transition engine. This keeps
    state lifecycles independent: washable items become wet immediately, but
    cleanliness changes only when the process completes.
    """
    device = node(state, device_id)
    composition = device.get("composition") or {}
    storage = composition.get("storage") if isinstance(composition, dict) else None
    accepted = storage.get("accepted_capabilities") if isinstance(storage, dict) else None
    required = {str(value).lower() for value in (device.get("requires_contained_capabilities") or accepted or ())}
    device_capabilities = {str(value).lower() for value in (device.get("capabilities") or ())}
    profile = device.get("temporal_profile") or {}
    if not profile:
        try:
            from .assets.object_library import OBJECT_LIBRARY
            template = OBJECT_LIBRARY.get(semantic(device))
            if template:
                profile = template._property("temporal_profile", {})
        except (ImportError, AttributeError):
            profile = {}
    device["temporal_profile"] = profile
    for child_id in descendants_of(state, device_id):
        child = node(state, child_id)
        capabilities = {str(value).lower() for value in (child.get("capabilities") or ())}
        apply_effects(child, capabilities, temporal_effects({"temporal_profile": profile}, "start"))


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


def _apply_fan_environment(state: dict[str, Any], device_id: str, is_on: bool) -> None:
    """Fans exchange room air without pretending to cool it directly."""
    room_id = str(state.get("room_of", {}).get(device_id) or "")
    if not room_id:
        return
    ventilation = state.setdefault("world_state", {}).setdefault("room_ventilation", {})
    ventilation[room_id] = "active" if is_on else "idle"


def _apply_environment_effect(state: dict[str, Any], device_id: str, is_on: bool) -> None:
    """Apply a declarative room environment effect from capability metadata."""
    device = node(state, device_id)
    effect = object_property(device, "environment_effect", {}) or {}
    if not isinstance(effect, dict) or not effect.get("channel"):
        return
    room_id = str(state.get("room_of", {}).get(device_id) or "")
    if not room_id:
        return
    world = state.setdefault("world_state", {})
    channel = str(effect["channel"])
    value = effect.get("active_value") if is_on else effect.get("inactive_value")
    if value == "baseline":
        value = {"comfortable": "room"}.get(str(world.get("temperature") or "comfortable"), world.get("temperature", "room"))
    world.setdefault(f"room_{channel}", {})[room_id] = value


def brush_target(state: dict[str, Any], target_id: str) -> None:
    target = node(state, target_id)
    if "washable" in object_capabilities(target):
        return
    target_states = mutable_states(target)
    target_states[DiscreteState.IS_DIRTY.value] = False
    if semantic(target) in {"sink", "trash_bin", "bin", "basket", "container"}:
        if DiscreteState.FILL_LEVEL.value in target_states:
            target_states[DiscreteState.FILL_LEVEL.value] = 0.0
        if DiscreteState.IS_FULL.value in target_states:
            target_states[DiscreteState.IS_FULL.value] = False


def _set_controlled_sink_water(state: dict[str, Any], faucet_id: str, has_water: bool) -> None:
    """A faucet controls flow; the shared clock fills the sink gradually."""
    for sink_id in controlled_targets(state, faucet_id):
        sink = node(state, sink_id)
        if "water_reservoir" in object_capabilities(sink):
            sink_states = mutable_states(sink)
            sink_states["water_flowing"] = has_water


def _apply_sink_entry_effect(state: dict[str, Any], object_id: str, sink_id: str) -> None:
    sink = node(state, sink_id)
    sink_capabilities = object_capabilities(sink)
    if "water_reservoir" not in sink_capabilities:
        return
    sink_states = mutable_states(sink)
    available = float(sink_states.get("water_level") or (100.0 if sink_states.get("has_water") else 0.0))
    if available <= 0:
        return
    item = node(state, object_id)
    item_states = mutable_states(item)
    item_capabilities = object_capabilities(item)
    transferred = 0.0
    if "water_container" in item_capabilities:
        current = float(item_states.get("water_level") or (100.0 if item_states.get("has_water") else 0.0))
        capacity = max(current, float(item.get("water_capacity") or 100.0))
        transferred = min(available, max(0.0, capacity - current))
        next_level = current + transferred
        item_states["has_water"] = next_level > 0
        item_states["water_level"] = round(next_level, 2)
        item_states["is_full"] = next_level >= capacity
    elif "wettable" in item_capabilities or "washable" in item_capabilities:
        transferred = min(available, max(0.1, float(item.get("water_absorption") or 10.0)))
        item_states[DiscreteState.IS_WET.value] = True
    if transferred <= 0:
        return
    remaining = max(0.0, available - transferred)
    sink_states["water_level"] = round(remaining, 2)
    sink_states["has_water"] = remaining > 0
    state.setdefault("world_state", {}).setdefault("event_log", []).append({
        "type": "water_transferred",
        "source_id": str(sink_id),
        "target_id": str(object_id),
        "amount": round(transferred, 2),
        "remaining": round(remaining, 2),
    })


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
    elif rule.effect == "water_plant":
        held_states = mutable_states(held)
        current_level = float(held_states.get(DiscreteState.WATER_LEVEL.value, 100.0 if held_states.get(DiscreteState.HAS_WATER.value) else 0.0) or 0.0)
        next_level = max(0.0, current_level - 35.0)
        held_states[DiscreteState.WATER_LEVEL.value] = next_level
        held_states[DiscreteState.HAS_WATER.value] = next_level > 0.0
        target_states = mutable_states(node(state, target_id))
        target_semantic = semantic(node(state, target_id))
        if target_semantic == "vase":
            target_states[DiscreteState.HAS_WATER.value] = True
            target_states[DiscreteState.WATER_LEVEL.value] = 100.0
            return
        vitality = float(target_states.get(DiscreteState.VITALITY.value, 0.0) or 0.0)
        target_states[DiscreteState.VITALITY.value] = min(1.0, round(vitality + 0.35, 4))
        target_states[DiscreteState.IS_WILTED.value] = False


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
