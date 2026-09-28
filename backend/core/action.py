from __future__ import annotations

from enum import Enum
from dataclasses import dataclass


class ActionType(str, Enum):
    WAIT = "wait"
    MOVE = "move"
    PICK = "pick"
    PLACE = "place"
    PRESS = "press"
    OPEN = "open"
    CLOSE = "close"
    BRUSH = "brush"
    FOLD = "fold"
    DUMP = "dump"
    REFILL = "refill"
    DISPENSE = "dispense"
    RELEASE = "release"
    CONSUME = "consume"

@dataclass(frozen=True)
class ActionSpec:
    action_type: ActionType
    category: str
    params: tuple[str, ...]
    description: str
    mutates_edges: bool
    mutates_states: bool
    effect_summary: tuple[str, ...]

ACTION_SPECS: dict[ActionType, ActionSpec] = {
    ActionType.WAIT: ActionSpec(
        action_type=ActionType.WAIT,
        category="temporal",
        params=("agent",),
        description="Advance the world by one step without manipulating an object.",
        mutates_edges=False,
        mutates_states=False,
        effect_summary=("advance timed transitions",),
    ),
    ActionType.PICK: ActionSpec(
        action_type=ActionType.PICK,
        category="manipulation",
        params=("agent", "object"),
        description="Detach a movable object from its current parent and attach it to the agent.",
        mutates_edges=True,
        mutates_states=True,
        effect_summary=("remove(object -> parent)", "add(object -> agent, held_by)"),
    ),
    ActionType.PLACE: ActionSpec(
        action_type=ActionType.PLACE,
        category="manipulation",
        params=("agent", "object", "target"),
        description="Detach a held object from the agent and place it on or in a target node.",
        mutates_edges=True,
        mutates_states=True,
        effect_summary=("remove(object -> agent, held_by)", "add(object -> target, in/on)"),
    ),
    ActionType.MOVE: ActionSpec(
        action_type=ActionType.MOVE,
        category="navigation",
        params=("agent", "target"),
        description="Move the agent to a room or fixture node.",
        mutates_edges=True,
        mutates_states=True,
        effect_summary=("remove(agent -> current_parent)", "add(agent -> target, at/in)"),
    ),
    ActionType.PRESS: ActionSpec(
        action_type=ActionType.PRESS,
        category="manipulation",
        params=("agent", "target"),
        description="Press a control-like node such as a button, switch, or faucet.",
        mutates_edges=False,
        mutates_states=True,
        effect_summary=("press target control", "possibly propagate to controlled object"),
    ),
    ActionType.OPEN: ActionSpec(
        action_type=ActionType.OPEN,
        category="manipulation",
        params=("agent", "target"),
        description="Open an openable node such as a door, drawer, cabinet, or appliance door.",
        mutates_edges=False,
        mutates_states=True,
        effect_summary=("set is_open = True when applicable", "or set opened = True"),
    ),
    ActionType.CLOSE: ActionSpec(
        action_type=ActionType.CLOSE,
        category="manipulation",
        params=("agent", "target"),
        description="Close a closeable node such as a door, drawer, cabinet, or appliance door.",
        mutates_edges=False,
        mutates_states=True,
        effect_summary=("set is_open = False when applicable", "or set closed = True"),
    ),
    ActionType.BRUSH: ActionSpec(
        action_type=ActionType.BRUSH,
        category="manipulation",
        params=("agent", "target"),
        description="Brush or scrub a reachable surface/object to change its surface condition.",
        mutates_edges=False,
        mutates_states=True,
        effect_summary=("set brushed = True", "possibly reduce dirty/particles on target surface"),
    ),
    ActionType.FOLD: ActionSpec(
        action_type=ActionType.FOLD,
        category="manipulation",
        params=("agent", "target"),
        description="Fold dry clothes, towels, or blankets.",
        mutates_edges=False,
        mutates_states=True,
        effect_summary=("require is_wet = False", "set folded = True"),
    ),
    ActionType.DUMP: ActionSpec(
        action_type=ActionType.DUMP,
        category="manipulation",
        params=("agent", "target"),
        description="Empty a held dumpable container into a compatible target.",
        mutates_edges=True,
        mutates_states=True,
        effect_summary=("require agent holds dumpable container", "apply container-specific dump rule"),
    ),
    ActionType.REFILL: ActionSpec(
        action_type=ActionType.REFILL,
        category="resource",
        params=("agent", "target", "object"),
        description="Restore a finite resource to its declared refill capacity.",
        mutates_edges=False,
        mutates_states=True,
        effect_summary=("reset uses_left/count/amount to capacity", "consume compatible supply object"),
    ),
    ActionType.DISPENSE: ActionSpec(
        action_type=ActionType.DISPENSE,
        category="resource",
        params=("agent", "target"),
        description="Dispense one independent item instance from a finite resource pool.",
        mutates_edges=True,
        mutates_states=True,
        effect_summary=("decrement source available_count", "create item instance held by agent"),
    ),
    ActionType.RELEASE: ActionSpec(
        action_type=ActionType.RELEASE,
        category="manipulation",
        params=("agent", "object"),
        description="Release a held object onto the current room floor under gravity.",
        mutates_edges=True,
        mutates_states=True,
        effect_summary=("detach object from agent", "drop object into current room", "break fragile object when drop is unsafe"),
    ),
    ActionType.CONSUME: ActionSpec(
        action_type=ActionType.CONSUME,
        category="resource",
        params=("agent", "object"),
        description="Consume a held food or drink item and remove its independent instance.",
        mutates_edges=True,
        mutates_states=True,
        effect_summary=("require a held consumable", "remove the consumed instance", "emit object_consumed with source provenance"),
    ),
}


def action_spec(action_type: ActionType | str) -> ActionSpec:
    normalized = ActionType(action_type)
    return ACTION_SPECS[normalized]


# Action execution is kept in this module with the action vocabulary.  The
# following implementation blocks are appended from the former split modules
# during the migration and intentionally share the same public Action API.


from .rules import APPLIANCE_CYCLE_STEPS, DUMP_RULES, SURFACE_SEMANTICS, RECIPE_SPECS, process_ready, start_process
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
from .relationship_ops import move_relationship
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
    move_relationship(state, node_id, parent_id, relation)
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


def _stop_timed_device(state: dict[str, Any], device_id: str, device_states: dict[str, Any]) -> None:
    device_states[DiscreteState.IS_ON.value] = False
    device_states[DiscreteState.IS_RUNNING.value] = False
    device_states[DiscreteState.CYCLE_REMAINING.value] = 0
    processes = state.setdefault("processes", [])
    processes[:] = [process for process in processes if str(process.get("device_id") or "") != str(device_id)]
    state.setdefault("world_state", {}).setdefault("event_log", []).append({
        "type": "device_stopped",
        "device_id": str(device_id),
    })


def press_target(state: dict[str, Any], target_id: str, payload: dict[str, Any] | None = None) -> None:
    target = node(state, target_id)
    target_states = mutable_states(target)
    target_states[DiscreteState.IS_PRESSED.value] = True
    target_semantic = semantic(target)
    capabilities = object_capabilities(target)
    if bool(target_states.get(DiscreteState.IS_RUNNING.value, False)) and "timed_device" in capabilities:
        _stop_timed_device(state, target_id, target_states)
        return
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
    if "water_source_control" in capabilities:
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
        if bool(controlled_states.get(DiscreteState.IS_RUNNING.value, False)) and "timed_device" in object_capabilities(controlled):
            _stop_timed_device(state, controlled_id, controlled_states)
            continue
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

from dataclasses import dataclass
from typing import Any, Callable
from .rules import DRYING_RACK_STEPS
from .predicates import (
    MOVABLE_NODE_TYPES,
    adjacent_room_failure,
    capacity_place_failures,
    carrying_type_failures,
    contained_capability_failures,
    container_access_failure,
    controlled_targets,
    device_door_failures,
    elevator_room_failure,
    dump_failures,
    holding,
    held_objects,
    is_open,
    node,
    node_type,
    object_capabilities,
    parent_of,
    place_target_failure,
    process_input_failures,
    requires_closed_to_start,
    room_of,
    same_room,
    semantic,
    states,
    structural_door_failure,
    supports_action,
    trash_place_failures,
)
from .system import can_dispense, dispense_resource, refill_rule
from .placement import (
    attach_surface_metadata,
    attach_volume_metadata,
    floor_collision_failure,
    surface_collision_failure,
    surface_fit_failure,
    surface_load_failure,
    volume_collision_failure,
    volume_fit_failure,
    volume_load_failure,
)


Precondition = Callable[["ActionContext"], str | None]
Effect = Callable[["ActionContext"], None]

CONSUMABLE_SEMANTICS = frozenset({"food", "fruit", "vegetable", "milk", "juice", "coffee", "sandwich", "cooked_egg"})


@dataclass(frozen=True)
class ActionContext:
    state: dict[str, Any]
    action: ActionType
    actor_id: str
    target_id: str
    object_id: str
    step: int = 0
    payload: dict[str, Any] | None = None

    @property
    def actor(self) -> dict[str, Any]:
        return node(self.state, self.actor_id)

    @property
    def target(self) -> dict[str, Any]:
        return node(self.state, self.target_id)

    @property
    def object(self) -> dict[str, Any]:
        return node(self.state, self.object_id)


@dataclass(frozen=True)
class ActionSchema:
    action: ActionType
    parameters: tuple[str, ...]
    preconditions: tuple[Precondition, ...]
    effects: tuple[Effect, ...]
    description: str = ""

    def failures(self, ctx: ActionContext) -> list[str]:
        return [failure for check in self.preconditions if (failure := check(ctx))]

    def apply(self, ctx: ActionContext) -> list[str]:
        failures = self.failures(ctx)
        if failures:
            return failures
        for effect in self.effects:
            effect(ctx)
        return []


def bind_action(state: dict[str, Any], action: dict[str, Any], *, step: int = 0) -> tuple[ActionContext | None, tuple[str, ...]]:
    action_name = str(action.get("action") or "").lower()
    if not action_name:
        return None, ("missing action",)
    try:
        action_type = ActionType(action_name)
    except ValueError:
        return None, (f"unsupported action: {action_name}",)

    actor_id = str(action.get("agent") or "robot_01")
    target_id = str(action.get("target") or "")
    raw_object_id = str(action.get("object") or "")
    object_id = raw_object_id or (target_id if action_type == ActionType.PICK else "")
    if action_type in {ActionType.RELEASE, ActionType.CONSUME} and not object_id:
        object_id = holding(state, actor_id)
    failures: list[str] = []
    if not node(state, actor_id):
        failures.append(f"unknown agent: {actor_id}")
    if action_type in {
        ActionType.MOVE,
        ActionType.OPEN,
        ActionType.CLOSE,
        ActionType.PRESS,
        ActionType.BRUSH,
        ActionType.PLACE,
        ActionType.FOLD,
        ActionType.DUMP,
        ActionType.REFILL,
        ActionType.DISPENSE,
    } and (not target_id or not node(state, target_id)):
        failures.append(f"unknown target: {target_id}")
    if action_type in {ActionType.PICK, ActionType.REFILL, ActionType.RELEASE, ActionType.CONSUME} and (not object_id or not node(state, object_id)):
        failures.append(f"unknown object: {object_id}")
    if failures:
        return None, tuple(failures)
    return ActionContext(state=state, action=action_type, actor_id=actor_id, target_id=target_id, object_id=object_id, step=step, payload=dict(action)), ()


def effect_wait(ctx: ActionContext) -> None:
    """Record an intentional temporal no-op; the runtime tick does the aging."""
    ctx.state.setdefault("world_state", {}).setdefault("event_log", []).append({
        "type": "robot_action_wait",
        "actor_id": str(ctx.actor_id),
        "step": int(ctx.step),
    })


def require_move_target(ctx: ActionContext) -> str | None:
    target_type = node_type(ctx.target)
    current_room = room_of(ctx.state, ctx.actor_id)
    if str(ctx.state.get("parent_of", {}).get(ctx.actor_id) or "") == ctx.target_id:
        return f"agent already near target: {ctx.target_id}"
    if target_type == "room":
        if ctx.target_id == current_room:
            return f"agent already in room: {ctx.target_id}"
        adjacency_failure = adjacent_room_failure(ctx.state, current_room, ctx.target_id)
        if adjacency_failure:
            elevator_failure = elevator_room_failure(ctx.state, current_room, ctx.target_id)
            if elevator_failure:
                return f"{adjacency_failure}; {elevator_failure}"
        return structural_door_failure(ctx.state, current_room, ctx.target_id)
    if target_type not in {"fixed_object", "control_object"}:
        return "move target should be a room, fixed object, or control object"
    if not same_room(ctx.state, ctx.actor_id, ctx.target_id):
        return "target is not in the same room"
    return None


def require_object_movable(ctx: ActionContext) -> str | None:
    return None if node_type(ctx.object) in MOVABLE_NODE_TYPES else "target is not movable"


def require_hand_empty(ctx: ActionContext) -> str | None:
    hand = str((ctx.payload or {}).get("hand") or "right").lower()
    if hand == "both":
        return "both hands must be free" if held_objects(ctx.state, ctx.actor_id) else None
    return f"{hand} hand already holds an object" if holding(ctx.state, ctx.actor_id, hand) else None


def require_object_same_room(ctx: ActionContext) -> str | None:
    return None if same_room(ctx.state, ctx.actor_id, ctx.object_id) else "object is not in the same room"


def require_object_parent_accessible(ctx: ActionContext) -> str | None:
    parent_id = parent_of(ctx.state, ctx.object_id)
    return container_access_failure(ctx.state, parent_id) if parent_id else None


def require_holding_place_object(ctx: ActionContext) -> str | None:
    held = ctx.object_id or holding(ctx.state, ctx.actor_id)
    if not held:
        return "agent holds nothing"
    if ctx.state.get("parent_of", {}).get(held) != ctx.actor_id:
        return f"agent is not holding {held}"
    return None


def require_place_target(ctx: ActionContext) -> str | None:
    return place_target_failure(ctx.target)


def require_target_same_room(ctx: ActionContext) -> str | None:
    return None if same_room(ctx.state, ctx.actor_id, ctx.target_id) else "target is not in the same room"


def require_place_target_accessible(ctx: ActionContext) -> str | None:
    # Detergent and similar consumables are loaded into the appliance's
    # dedicated supply slot, not into its user-facing drum/interior.  Keep
    # this resource-loading path available while the appliance door is closed
    # (legacy scenes and catalog templates model the slot as front-accessible).
    accepted = DEVICE_RESOURCE_LOADS.get(semantic(ctx.target), frozenset())
    if semantic(ctx.object) in accepted:
        return None
    return container_access_failure(ctx.state, ctx.target_id)


def require_device_resource_slot(ctx: ActionContext) -> str | None:
    accepted = DEVICE_RESOURCE_LOADS.get(semantic(ctx.target), frozenset())
    if semantic(ctx.object) not in accepted:
        return None
    for child_id, parent_id in (ctx.state.get("parent_of") or {}).items():
        if parent_id == ctx.target_id and semantic(node(ctx.state, child_id)) in accepted:
            return f"device resource slot already occupied: {ctx.target_id}"
    return None


def require_place_capacity(ctx: ActionContext) -> str | None:
    failures = capacity_place_failures(ctx.state, ctx.target_id)
    return "; ".join(failures) if failures else None


def require_surface_fit(ctx: ActionContext) -> str | None:
    placed_id = ctx.object_id or holding(ctx.state, ctx.actor_id)
    failure = surface_fit_failure(ctx.state.get("nodes", {}).get(placed_id) or {}, ctx.target, ctx.payload)
    return failure


def require_surface_collision_free(ctx: ActionContext) -> str | None:
    placed_id = ctx.object_id or holding(ctx.state, ctx.actor_id)
    return surface_collision_failure(ctx.state, ctx.state.get("nodes", {}).get(placed_id) or {}, ctx.target, ctx.payload)


def require_surface_load(ctx: ActionContext) -> str | None:
    placed_id = ctx.object_id or holding(ctx.state, ctx.actor_id)
    return surface_load_failure(ctx.state, ctx.state.get("nodes", {}).get(placed_id) or {}, ctx.target)


def require_volume_fit(ctx: ActionContext) -> str | None:
    placed_id = ctx.object_id or holding(ctx.state, ctx.actor_id)
    return volume_fit_failure(ctx.state.get("nodes", {}).get(placed_id) or {}, ctx.target, ctx.payload)


def require_volume_collision_free(ctx: ActionContext) -> str | None:
    placed_id = ctx.object_id or holding(ctx.state, ctx.actor_id)
    return volume_collision_failure(ctx.state, ctx.state.get("nodes", {}).get(placed_id) or {}, ctx.target, ctx.payload)


def require_volume_load(ctx: ActionContext) -> str | None:
    placed_id = ctx.object_id or holding(ctx.state, ctx.actor_id)
    return volume_load_failure(ctx.state, ctx.state.get("nodes", {}).get(placed_id) or {}, ctx.target)


def require_carrying_type(ctx: ActionContext) -> str | None:
    placed_id = ctx.object_id or holding(ctx.state, ctx.actor_id)
    failures = carrying_type_failures(ctx.state, placed_id, ctx.target_id)
    return "; ".join(failures) if failures else None


def require_contained_capabilities(ctx: ActionContext) -> str | None:
    placed_id = ctx.object_id or holding(ctx.state, ctx.actor_id)
    failures = contained_capability_failures(ctx.state, placed_id, ctx.target_id)
    return "; ".join(failures) if failures else None


def require_trash_placement(ctx: ActionContext) -> str | None:
    placed_id = ctx.object_id or holding(ctx.state, ctx.actor_id)
    failures = trash_place_failures(ctx.state, placed_id, ctx.target_id)
    return "; ".join(failures) if failures else None


def require_target_supports_action(ctx: ActionContext) -> str | None:
    return None if supports_action(ctx.target, ctx.action.value) else f"target does not support {ctx.action.value}: {ctx.target_id}"


def require_open_not_redundant(ctx: ActionContext) -> str | None:
    if semantic(ctx.target) == "faucet":
        return f"target is already on: {ctx.target_id}" if bool(states(ctx.target).get("is_on", False)) else None
    return f"target is already open: {ctx.target_id}" if is_open(ctx.target) else None


def require_open_not_running(ctx: ActionContext) -> str | None:
    """A running process locks its attached access doors generically."""
    target = ctx.target
    if semantic(target) != "door":
        return None
    host_id = parent_of(ctx.state, ctx.target_id)
    host = node(ctx.state, host_id)
    if host_id and bool(states(host).get("is_running", False)):
        return f"device is running; door is locked: {ctx.target_id}"
    return None


def require_close_not_redundant(ctx: ActionContext) -> str | None:
    if semantic(ctx.target) == "faucet":
        return None if bool(states(ctx.target).get("is_on", False)) else f"target is already off: {ctx.target_id}"
    return None if is_open(ctx.target) else f"target is already closed: {ctx.target_id}"


def require_brushable(ctx: ActionContext) -> str | None:
    if "washable" in object_capabilities(ctx.target):
        return "washable objects must use a compatible washing process"
    if states(ctx.target).get("is_dirty") is not True:
        return f"target does not need brushing: {ctx.target_id}"
    required_tool = str(ctx.target.get("required_tool") or "").strip().lower()
    if required_tool:
        held_id = holding(ctx.state, ctx.actor_id)
        held = node(ctx.state, held_id)
        held_semantic = semantic(held)
        held_tool = str(held.get("tool_type") or held.get("tool") or "").strip().lower()
        if required_tool not in {held_semantic, held_tool}:
            return f"required tool not held for {ctx.target_id}: {required_tool}"
        uses_left = states(held).get("uses_left")
        if uses_left is not None and float(uses_left or 0) <= 0:
            return f"tool exhausted: {held_id}"
    held_id = holding(ctx.state, ctx.actor_id)
    held = node(ctx.state, held_id)
    held_capabilities = {str(value).lower() for value in (held.get("capabilities") or ())}
    if "cleaning_tool" in held_capabilities and not bool(states(held).get("is_wet", False)):
        return "cleaning tool must be wet"
    return None


def require_press_ready(ctx: ActionContext) -> str | None:
    if semantic(ctx.target) in {"elevator", "lift"}:
        destination = str((ctx.payload or {}).get("destination_room") or (ctx.payload or {}).get("target_room") or "")
        served = {str(room_id) for room_id in ctx.target.get("served_rooms") or ctx.target.get("transport_rooms") or []}
        if destination not in served:
            return f"elevator destination is not served: {destination or '<missing>'}"
        if ctx.state.get("parent_of", {}).get(ctx.actor_id) != ctx.target_id:
            return "agent must be inside elevator before selecting a floor"
        if bool(states(ctx.target).get("is_running", False)):
            return f"elevator is already running: {ctx.target_id}"
        if not is_open(ctx.target):
            return "elevator door must be open before selecting a floor"
        return None
    capabilities = {str(cap).lower() for cap in (ctx.target.get("capabilities") or [])}
    # A second press is a stop command. Starting prerequisites such as loaded
    # detergent or a closed door do not apply to stopping an active device.
    if bool(states(ctx.target).get("is_running", False)) and "timed_device" in capabilities:
        return None
    if "finite_resource" in capabilities:
        resource_values = [states(ctx.target).get(key) for key in ("uses_left", "count", "amount") if key in states(ctx.target)]
        if resource_values and max(float(value or 0) for value in resource_values) <= 0:
            return f"resource exhausted: {ctx.target_id}"
    if requires_closed_to_start(ctx.target) and is_open(ctx.target):
        return f"device door must be closed before start: {ctx.target_id}"
    input_failures = process_input_failures(ctx.state, ctx.target_id)
    if input_failures:
        return "; ".join(input_failures)
    if semantic(ctx.target) in RECIPE_SPECS and not process_ready(ctx.state, ctx.target_id):
        return f"process inputs unavailable: {ctx.target_id}"
    credential_failure = access_credential_failure(ctx.state, ctx.actor_id, ctx.target_id)
    if credential_failure:
        return credential_failure
    failures = device_door_failures(ctx.state, [ctx.target_id, *controlled_targets(ctx.state, ctx.target_id)])
    return "; ".join(failures) if failures else None


def access_credential_failure(state: dict[str, Any], actor_id: str, control_id: str) -> str | None:
    """Require a held credential when a control opens a protected door."""
    for target_id in controlled_targets(state, control_id):
        target = node(state, target_id)
        required = str(target.get("required_credential") or "")
        if not required:
            continue
        held_id = holding(state, actor_id)
        held = node(state, held_id)
        credential = str(held.get("credential") or held.get("credential_type") or semantic(held))
        if credential != required:
            return f"missing credential for {target_id}: {required}"
    return None


def require_foldable_and_dry(ctx: ActionContext) -> str | None:
    if "foldable" not in object_capabilities(ctx.target):
        return "target is not foldable"
    if bool(states(ctx.target).get("is_wet", False)):
        return "wet cloth cannot be folded"
    return None


def require_dumpable(ctx: ActionContext) -> str | None:
    failures = dump_failures(ctx.state, ctx.actor_id, ctx.target_id)
    return "; ".join(failures) if failures else None


def effect_move(ctx: ActionContext) -> None:
    relation = "at" if node_type(ctx.target) == "room" else ("in" if semantic(ctx.target) in {"elevator", "lift"} else "near")
    move_node(ctx.state, ctx.actor_id, ctx.target_id, relation)


def effect_pick(ctx: ActionContext) -> None:
    hand = str((ctx.payload or {}).get("hand") or "right").lower()
    relation = "held_by" if hand in {"right", "primary"} else f"held_by_{hand}"
    move_node(ctx.state, ctx.object_id, ctx.actor_id, relation)


def effect_place(ctx: ActionContext) -> None:
    placed_id = ctx.object_id or holding(ctx.state, ctx.actor_id)
    if semantic(ctx.target) == "printer" and _load_printer_supply(ctx.state, placed_id, ctx.target_id):
        return
    relation = place_relation_for_target(ctx.target)
    move_node(ctx.state, placed_id, ctx.target_id, relation)
    item = node(ctx.state, placed_id)
    if bool(ctx.target.get("allow_stacking", False)):
        item["_placement_state_nodes"] = list(ctx.state.get("nodes", {}).values())
    attach_surface_metadata(item, ctx.target, ctx.payload)
    attach_volume_metadata(item, ctx.target, ctx.payload)
    _apply_sink_entry_effect(ctx.state, placed_id, ctx.target_id)
    loaded_resource = _load_device_resource(ctx.state, placed_id, ctx.target_id)
    # Loading a finite appliance supply is its own semantic transition. Do
    # not append a generic object_placed event after resource_loaded, since
    # consumers use the final event in the step as the authoritative resource
    # accounting record.
    if loaded_resource:
        return
    contained_profile = ctx.target.get("contained_temporal_profile")
    contained_duration = ctx.target.get("contained_process_duration_steps")
    if isinstance(contained_profile, dict) and contained_duration:
        placed_states = node(ctx.state, placed_id).setdefault("states", {})
        if bool(placed_states.get("is_wet", False)):
            placed_states["cycle_remaining"] = max(1, int(contained_duration))
    if semantic(ctx.target) == "trash_bin":
        ctx.target.setdefault("states", {})["is_dirty"] = True
    event: dict[str, Any] = {
        "type": "object_placed",
        "object_id": str(placed_id),
        "target_id": str(ctx.target_id),
        "relation": relation,
    }
    item = node(ctx.state, placed_id)
    if "placement_anchor" in item:
        event["surface_anchor"] = list(item["placement_anchor"])
    if "placement_volume_anchor" in item:
        event["volume_anchor"] = list(item["placement_volume_anchor"])
    ctx.state.setdefault("world_state", {}).setdefault("event_log", []).append(event)


def _load_printer_supply(state: dict[str, Any], item_id: str, printer_id: str) -> bool:
    item = node(state, item_id) or {}
    printer = node(state, printer_id) or {}
    item_semantic = semantic(item)
    if item_semantic not in {"paper_pack", "ink_cartridge"} or semantic(printer) != "printer":
        return False
    item_states = item.get("states") or {}
    printer_states = printer.setdefault("states", {})
    if item_semantic == "paper_pack":
        amount = float(item_states.get("count", 1) or 0)
        key = "count"
    else:
        amount = float(item_states.get("amount", 1) or 0)
        key = "amount"
    if amount <= 0:
        return False
    current = float(printer_states.get(key, 0) or 0)
    capacity = float((printer.get("resource_capacity") or {}).get(key, current + amount) or current + amount)
    printer_states[key] = int(min(capacity, current + amount)) if float(min(capacity, current + amount)).is_integer() else round(min(capacity, current + amount), 4)
    source_id = str(item.get("resource_instance_of") or "")
    if source_id:
        source = state.get("nodes", {}).get(source_id) or {}
        pool = source.get("resource_pool") if isinstance(source, dict) else None
        if isinstance(pool, dict):
            pool["consumed_count"] = int(pool.get("consumed_count", 0) or 0) + 1
    state.get("nodes", {}).pop(item_id, None)
    state.get("parent_of", {}).pop(item_id, None)
    state.get("relation_of", {}).pop(item_id, None)
    event = {
        "type": "resource_loaded",
        "device_id": str(printer_id),
        "instance_id": str(item_id),
        "resource_semantic_type": item_semantic,
        "quantity_key": key,
        "quantity_added": amount,
        "new_quantity": printer_states[key],
    }
    if source_id:
        event["source_id"] = source_id
    state.setdefault("world_state", {}).setdefault("event_log", []).append(event)
    return True


DEVICE_RESOURCE_LOADS: dict[str, frozenset[str]] = {
    "washer": frozenset({"detergent", "laundry_detergent"}),
    "washing_machine": frozenset({"detergent", "laundry_detergent"}),
    "dishwasher": frozenset({"detergent", "dishwasher_detergent"}),
}


def _load_device_resource(state: dict[str, Any], item_id: str, device_id: str) -> bool:
    item = node(state, item_id) or {}
    device = node(state, device_id) or {}
    accepted = DEVICE_RESOURCE_LOADS.get(semantic(device), frozenset())
    if semantic(item) not in accepted:
        return False
    existing = [
        child_id for child_id, parent_id in (state.get("parent_of") or {}).items()
        if child_id != item_id and parent_id == device_id and semantic(node(state, child_id)) in accepted
    ]
    if existing:
        return False
    state.setdefault("world_state", {}).setdefault("event_log", []).append({
        "type": "resource_loaded",
        "device_id": str(device_id),
        "instance_id": str(item_id),
        "resource_semantic_type": semantic(item),
        "consumed_on_start": True,
    })
    return True


def effect_open(ctx: ActionContext) -> None:
    open_target(ctx.state, ctx.target_id)


def effect_close(ctx: ActionContext) -> None:
    close_target(ctx.state, ctx.target_id)


def effect_press(ctx: ActionContext) -> None:
    press_target(ctx.state, ctx.target_id, ctx.payload)


def effect_brush(ctx: ActionContext) -> None:
    brush_target(ctx.state, ctx.target_id)
    required_tool = str(ctx.target.get("required_tool") or "").strip().lower()
    if not required_tool:
        return
    held_id = holding(ctx.state, ctx.actor_id)
    held = node(ctx.state, held_id)
    held_states = held.setdefault("states", {})
    if "uses_left" in held_states:
        held_states["uses_left"] = max(0, float(held_states["uses_left"] or 0) - 1)
        if float(held_states["uses_left"]).is_integer():
            held_states["uses_left"] = int(held_states["uses_left"])
    ctx.state.setdefault("world_state", {}).setdefault("event_log", []).append({
        "type": "tool_used",
        "tool_id": str(held_id),
        "target_id": str(ctx.target_id),
        "tool": required_tool,
        "uses_left": held_states.get("uses_left"),
    })


def effect_fold(ctx: ActionContext) -> None:
    fold_target(ctx.state, ctx.target_id)


def effect_dump(ctx: ActionContext) -> None:
    dump_held_container(ctx.state, ctx.actor_id, ctx.target_id)


def effect_refill(ctx: ActionContext) -> None:
    target_states = ctx.target.setdefault("states", {})
    capacities = ctx.target.get("resource_capacity") or {}
    for key in ("uses_left", "count", "amount"):
        if key in target_states:
            target_states[key] = capacities.get(key, target_states[key])
    state_nodes = ctx.state.get("nodes", {})
    state_nodes.pop(ctx.object_id, None)
    ctx.state.get("parent_of", {}).pop(ctx.object_id, None)
    ctx.state.get("relation_of", {}).pop(ctx.object_id, None)


def require_refill_supply(ctx: ActionContext) -> str | None:
    return None if refill_rule(ctx.state, ctx.target_id, ctx.object_id) else f"incompatible refill supply: {ctx.object_id} -> {ctx.target_id}"


def require_resource_available(ctx: ActionContext) -> str | None:
    if not supports_action(ctx.target, "dispense"):
        return f"target does not support dispense: {ctx.target_id}"
    if not can_dispense(ctx.target):
        return f"resource exhausted or pool missing: {ctx.target_id}"
    parent_ctx = ActionContext(
        state=ctx.state,
        action=ctx.action,
        actor_id=ctx.actor_id,
        target_id=ctx.target_id,
        object_id=ctx.target_id,
        step=ctx.step,
    )
    return require_object_parent_accessible(parent_ctx)


def effect_dispense(ctx: ActionContext) -> None:
    dispense_resource(ctx.state, ctx.target_id, ctx.actor_id)


def require_release_object(ctx: ActionContext) -> str | None:
    if not ctx.object_id or ctx.state.get("parent_of", {}).get(ctx.object_id) != ctx.actor_id:
        return "agent holds no releasable object"
    return None


def require_release_floor_clear(ctx: ActionContext) -> str | None:
    actor_room = room_of(ctx.state, ctx.actor_id)
    room = node(ctx.state, actor_room) if actor_room else {}
    if not room:
        return None
    item = node(ctx.state, ctx.object_id)
    raw_anchor = (ctx.payload or {}).get("release_anchor")
    if isinstance(raw_anchor, (list, tuple)) and len(raw_anchor) >= 3:
        payload = {"release_anchor": [raw_anchor[0], 0.0, raw_anchor[2]]}
    else:
        payload = None
    return floor_collision_failure(ctx.state, item, room, payload)


def effect_release(ctx: ActionContext) -> None:
    actor_room = room_of(ctx.state, ctx.actor_id)
    if not actor_room:
        return
    item = node(ctx.state, ctx.object_id)
    states = item.setdefault("states", {})
    material = str(item.get("material") or item.get("properties", {}).get("material") or "").lower()
    fragile = bool(item.get("fragile", False)) or material in {"glass", "ceramic"}
    drop_height_cm = float(item.get("drop_height_cm") or item.get("release_height_cm") or 0.0)
    if fragile and drop_height_cm > 30:
        states["is_broken"] = True
        ctx.state.setdefault("world_state", {}).setdefault("event_log", []).append({
            "type": "object_broken",
            "object_id": str(ctx.object_id),
            "material": material or "fragile",
            "drop_height_cm": drop_height_cm,
            "cause": "high_release",
        })
    # Keep release distinct from placement: planners/renderers can identify
    # the floor drop and its originating height even after the parent changes.
    item["release_mode"] = "release"
    item["release_room"] = actor_room
    raw_anchor = list(ctx.payload.get("release_anchor") or [0.5, 0.0, 0.5]) if ctx.payload else [0.5, 0.0, 0.5]
    # Release is a floor hit, so only horizontal coordinates are meaningful.
    # Clamp malformed client hints instead of allowing an object to land
    # outside the current room's normalized footprint.
    while len(raw_anchor) < 3:
        raw_anchor.append(0.5)
    def unit(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = 0.5
        return max(0.0, min(1.0, number))

    release_anchor = [unit(raw_anchor[0]), 0.0, unit(raw_anchor[2])]
    item["release_anchor"] = release_anchor
    item["floor_contact"] = {"room_id": actor_room, "anchor": release_anchor}
    item["physics_state"] = "falling" if drop_height_cm > 0 else "settled"
    item["drop_height_cm"] = max(0.0, drop_height_cm)
    move_node(ctx.state, ctx.object_id, actor_room, "in")
    ctx.state.setdefault("world_state", {}).setdefault("event_log", []).append({
        "type": "object_released",
        "object_id": str(ctx.object_id),
        "room_id": actor_room,
        "release_anchor": release_anchor,
        "physics_state": item["physics_state"],
    })


def require_consumable(ctx: ActionContext) -> str | None:
    if str(ctx.state.get("parent_of", {}).get(ctx.object_id) or "") != ctx.actor_id:
        return "agent must hold the consumable"
    item = ctx.object
    states = item.get("states") or {}
    if bool(states.get("is_rotten", False)) or bool(states.get("is_burnt", False)):
        return "rotten or burnt food cannot be consumed"
    capabilities = {str(cap).lower() for cap in item.get("capabilities") or []}
    if semantic(item) not in CONSUMABLE_SEMANTICS and "consumable" not in capabilities and not bool(item.get("consumable", False)):
        return f"object is not consumable: {ctx.object_id}"
    return None


def effect_consume(ctx: ActionContext) -> None:
    item = ctx.object
    source_id = str(item.get("resource_instance_of") or "")
    event = {
        "type": "object_consumed",
        "object_id": str(ctx.object_id),
        "actor_id": str(ctx.actor_id),
        "semantic_type": semantic(item),
    }
    if source_id:
        event["source_id"] = source_id
        source = ctx.state.get("nodes", {}).get(source_id)
        if isinstance(source, dict):
            pool = source.get("resource_pool")
            if isinstance(pool, dict):
                pool["consumed_count"] = int(pool.get("consumed_count", 0) or 0) + 1
    ctx.state.get("nodes", {}).pop(ctx.object_id, None)
    ctx.state.get("parent_of", {}).pop(ctx.object_id, None)
    ctx.state.get("relation_of", {}).pop(ctx.object_id, None)
    ctx.state.setdefault("world_state", {}).setdefault("event_log", []).append(event)
    if source_id:
        ctx.state.setdefault("world_state", {}).setdefault("event_log", []).append({
            "type": "resource_consumed",
            "source_id": source_id,
            "instance_id": str(ctx.object_id),
            "actor_id": str(ctx.actor_id),
            "resource_semantic_type": semantic(item),
        })


ACTION_SCHEMAS: dict[ActionType, ActionSchema] = {
    ActionType.WAIT: ActionSchema(
        action=ActionType.WAIT,
        parameters=("actor",),
        preconditions=(),
        effects=(effect_wait,),
        description="Advance one simulation step while waiting for a process or timed transition.",
    ),
    ActionType.MOVE: ActionSchema(
        action=ActionType.MOVE,
        parameters=("actor", "target"),
        preconditions=(require_move_target,),
        effects=(effect_move,),
        description="Move an actor to an adjacent room or nearby fixture.",
    ),
    ActionType.PICK: ActionSchema(
        action=ActionType.PICK,
        parameters=("actor", "object"),
        preconditions=(require_object_movable, require_hand_empty, require_object_same_room, require_object_parent_accessible),
        effects=(effect_pick,),
        description="Attach a movable object to the actor as held.",
    ),
    ActionType.PLACE: ActionSchema(
        action=ActionType.PLACE,
        parameters=("actor", "object", "target"),
        preconditions=(
            require_holding_place_object,
            require_place_target,
            require_target_same_room,
            require_place_target_accessible,
            require_device_resource_slot,
            require_place_capacity,
            require_surface_fit,
            require_surface_collision_free,
            require_surface_load,
            require_volume_fit,
            require_volume_collision_free,
            require_volume_load,
            require_carrying_type,
            require_contained_capabilities,
            require_trash_placement,
        ),
        effects=(effect_place,),
        description="Place a held object on or in a target.",
    ),
    ActionType.OPEN: ActionSchema(
        action=ActionType.OPEN,
        parameters=("actor", "target"),
        preconditions=(require_target_same_room, require_target_supports_action, require_open_not_redundant, require_open_not_running),
        effects=(effect_open,),
        description="Open an openable target.",
    ),
    ActionType.CLOSE: ActionSchema(
        action=ActionType.CLOSE,
        parameters=("actor", "target"),
        preconditions=(require_target_same_room, require_target_supports_action, require_close_not_redundant),
        effects=(effect_close,),
        description="Close an open target.",
    ),
    ActionType.PRESS: ActionSchema(
        action=ActionType.PRESS,
        parameters=("actor", "target"),
        preconditions=(require_target_same_room, require_target_supports_action, require_press_ready),
        effects=(effect_press,),
        description="Press a control or start a device.",
    ),
    ActionType.BRUSH: ActionSchema(
        action=ActionType.BRUSH,
        parameters=("actor", "target"),
        preconditions=(require_target_same_room, require_target_supports_action, require_brushable),
        effects=(effect_brush,),
        description="Clean a dirty, brushable non-cloth target.",
    ),
    ActionType.FOLD: ActionSchema(
        action=ActionType.FOLD,
        parameters=("actor", "target"),
        preconditions=(require_target_same_room, require_target_supports_action, require_foldable_and_dry),
        effects=(effect_fold,),
        description="Fold dry cloth.",
    ),
    ActionType.DUMP: ActionSchema(
        action=ActionType.DUMP,
        parameters=("actor", "target"),
        preconditions=(require_target_same_room, require_target_supports_action, require_dumpable),
        effects=(effect_dump,),
        description="Dump a held container into a compatible target.",
    ),
    ActionType.REFILL: ActionSchema(
        action=ActionType.REFILL,
        parameters=("actor", "target", "object"),
        preconditions=(require_target_same_room, require_target_supports_action, require_refill_supply, require_object_same_room),
        effects=(effect_refill,),
        description="Refill a finite resource to its declared capacity.",
    ),
    ActionType.DISPENSE: ActionSchema(
        action=ActionType.DISPENSE,
        parameters=("actor", "target"),
        preconditions=(require_target_same_room, require_resource_available, require_hand_empty),
        effects=(effect_dispense,),
        description="Create one independent item from a finite source pool and hold it.",
    ),
    ActionType.RELEASE: ActionSchema(
        action=ActionType.RELEASE,
        parameters=("actor", "object"),
        preconditions=(require_release_object, require_release_floor_clear),
        effects=(effect_release,),
        description="Release a held object onto the current room floor.",
    ),
    ActionType.CONSUME: ActionSchema(
        action=ActionType.CONSUME,
        parameters=("actor", "object"),
        preconditions=(require_consumable,),
        effects=(effect_consume,),
        description="Consume a held food or drink item.",
    ),
}


def validate_action_schema(state: dict[str, Any], action: dict[str, Any], *, step: int = 0) -> tuple[str, ...]:
    ctx, binding_failures = bind_action(state, action, step=step)
    if binding_failures or ctx is None:
        return binding_failures
    schema = ACTION_SCHEMAS.get(ctx.action)
    if not schema:
        return (f"unsupported action: {ctx.action.value}",)
    return tuple(schema.failures(ctx))


def apply_action_schema(state: dict[str, Any], action: dict[str, Any], *, step: int = 0) -> tuple[str, ...]:
    ctx, binding_failures = bind_action(state, action, step=step)
    if binding_failures or ctx is None:
        return binding_failures
    schema = ACTION_SCHEMAS.get(ctx.action)
    if not schema:
        return (f"unsupported action: {ctx.action.value}",)
    return tuple(schema.apply(ctx))


__all__ = [
    "ACTION_SCHEMAS", "ACTION_SPECS", "ActionContext", "ActionSchema", "ActionSpec", "ActionType",
    "action_spec", "apply_action_schema", "bind_action", "validate_action_schema",
    "brush_target", "close_target", "dump_held_container", "fold_target", "move_node",
    "_apply_sink_entry_effect", "open_target", "place_relation_for_target", "press_target",
]

