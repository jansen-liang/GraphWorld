from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .actions import ActionType
from .domain_rules import CLOTH_SEMANTICS, DRYING_RACK_STEPS
from .effects import (
    brush_target,
    close_target,
    dump_held_container,
    fold_target,
    _apply_sink_entry_effect,
    move_node,
    open_target,
    place_relation_for_target,
    press_target,
)
from .predicates import (
    MOVABLE_NODE_TYPES,
    adjacent_room_failure,
    capacity_place_failures,
    carrying_type_failures,
    container_access_failure,
    controlled_targets,
    device_door_failures,
    dump_failures,
    holding,
    is_open,
    node,
    node_type,
    parent_of,
    place_target_failure,
    requires_closed_to_start,
    room_of,
    same_room,
    semantic,
    states,
    structural_door_failure,
    supports_action,
    trash_place_failures,
)
from .resource_rules import refill_rule
from .processes import process_ready


Precondition = Callable[["ActionContext"], str | None]
Effect = Callable[["ActionContext"], None]


@dataclass(frozen=True)
class ActionContext:
    state: dict[str, Any]
    action: ActionType
    actor_id: str
    target_id: str
    object_id: str
    step: int = 0

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
    } and (not target_id or not node(state, target_id)):
        failures.append(f"unknown target: {target_id}")
    if action_type in {ActionType.PICK, ActionType.REFILL} and (not object_id or not node(state, object_id)):
        failures.append(f"unknown object: {object_id}")
    if failures:
        return None, tuple(failures)
    return ActionContext(state=state, action=action_type, actor_id=actor_id, target_id=target_id, object_id=object_id, step=step), ()


def require_move_target(ctx: ActionContext) -> str | None:
    target_type = node_type(ctx.target)
    current_room = room_of(ctx.state, ctx.actor_id)
    if str(ctx.state.get("parent_of", {}).get(ctx.actor_id) or "") == ctx.target_id:
        return f"agent already near target: {ctx.target_id}"
    if target_type == "room":
        if ctx.target_id == current_room:
            return f"agent already in room: {ctx.target_id}"
        return adjacent_room_failure(ctx.state, current_room, ctx.target_id) or structural_door_failure(ctx.state, current_room, ctx.target_id)
    if target_type not in {"fixed_object", "control_object"}:
        return "move target should be a room, fixed object, or control object"
    if not same_room(ctx.state, ctx.actor_id, ctx.target_id):
        return "target is not in the same room"
    return None


def require_object_movable(ctx: ActionContext) -> str | None:
    return None if node_type(ctx.object) in MOVABLE_NODE_TYPES else "target is not movable"


def require_hand_empty(ctx: ActionContext) -> str | None:
    return "agent already holds an object" if holding(ctx.state, ctx.actor_id) else None


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
    return container_access_failure(ctx.state, ctx.target_id)


def require_place_capacity(ctx: ActionContext) -> str | None:
    failures = capacity_place_failures(ctx.state, ctx.target_id)
    return "; ".join(failures) if failures else None


def require_carrying_type(ctx: ActionContext) -> str | None:
    placed_id = ctx.object_id or holding(ctx.state, ctx.actor_id)
    failures = carrying_type_failures(ctx.state, placed_id, ctx.target_id)
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


def require_close_not_redundant(ctx: ActionContext) -> str | None:
    if semantic(ctx.target) == "faucet":
        return None if bool(states(ctx.target).get("is_on", False)) else f"target is already off: {ctx.target_id}"
    return None if is_open(ctx.target) else f"target is already closed: {ctx.target_id}"


def require_brushable(ctx: ActionContext) -> str | None:
    if semantic(ctx.target) in CLOTH_SEMANTICS:
        return "cloth must be washed in washer"
    if states(ctx.target).get("is_dirty") is not True:
        return f"target does not need brushing: {ctx.target_id}"
    return None


def require_press_ready(ctx: ActionContext) -> str | None:
    capabilities = {str(cap).lower() for cap in (ctx.target.get("capabilities") or [])}
    if "finite_resource" in capabilities:
        resource_values = [states(ctx.target).get(key) for key in ("uses_left", "count", "amount") if key in states(ctx.target)]
        if resource_values and max(float(value or 0) for value in resource_values) <= 0:
            return f"resource exhausted: {ctx.target_id}"
    if requires_closed_to_start(ctx.target) and is_open(ctx.target):
        return f"device door must be closed before start: {ctx.target_id}"
    if semantic(ctx.target) in {"printer", "coffeemachine", "coffee_machine"} and not process_ready(ctx.state, ctx.target_id):
        return f"process inputs unavailable: {ctx.target_id}"
    failures = device_door_failures(ctx.state, [ctx.target_id, *controlled_targets(ctx.state, ctx.target_id)])
    return "; ".join(failures) if failures else None


def require_foldable_and_dry(ctx: ActionContext) -> str | None:
    if semantic(ctx.target) not in CLOTH_SEMANTICS:
        return "target is not foldable cloth"
    if bool(states(ctx.target).get("is_wet", False)):
        return "wet cloth cannot be folded"
    return None


def require_dumpable(ctx: ActionContext) -> str | None:
    failures = dump_failures(ctx.state, ctx.actor_id, ctx.target_id)
    return "; ".join(failures) if failures else None


def effect_move(ctx: ActionContext) -> None:
    relation = "at" if node_type(ctx.target) == "room" else "near"
    move_node(ctx.state, ctx.actor_id, ctx.target_id, relation)


def effect_pick(ctx: ActionContext) -> None:
    move_node(ctx.state, ctx.object_id, ctx.actor_id, "held_by")


def effect_place(ctx: ActionContext) -> None:
    placed_id = ctx.object_id or holding(ctx.state, ctx.actor_id)
    relation = place_relation_for_target(ctx.target)
    move_node(ctx.state, placed_id, ctx.target_id, relation)
    _apply_sink_entry_effect(ctx.state, placed_id, ctx.target_id)
    if semantic(ctx.target) == "drying_rack":
        placed_states = node(ctx.state, placed_id).setdefault("states", {})
        if bool(placed_states.get("is_wet", False)):
            weather = str(ctx.state.get("world_state", {}).get("weather") or "sunny").lower()
            placed_states["cycle_remaining"] = {"sunny": 6, "cloudy": 8, "rainy": 12}.get(weather, DRYING_RACK_STEPS)
    if semantic(ctx.target) == "trash_bin":
        ctx.target.setdefault("states", {})["is_dirty"] = True


def effect_open(ctx: ActionContext) -> None:
    open_target(ctx.state, ctx.target_id)


def effect_close(ctx: ActionContext) -> None:
    close_target(ctx.state, ctx.target_id)


def effect_press(ctx: ActionContext) -> None:
    press_target(ctx.state, ctx.target_id)


def effect_brush(ctx: ActionContext) -> None:
    brush_target(ctx.state, ctx.target_id)


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


ACTION_SCHEMAS: dict[ActionType, ActionSchema] = {
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
            require_place_capacity,
            require_carrying_type,
            require_trash_placement,
        ),
        effects=(effect_place,),
        description="Place a held object on or in a target.",
    ),
    ActionType.OPEN: ActionSchema(
        action=ActionType.OPEN,
        parameters=("actor", "target"),
        preconditions=(require_target_same_room, require_target_supports_action, require_open_not_redundant),
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
    "ACTION_SCHEMAS",
    "ActionContext",
    "ActionSchema",
    "apply_action_schema",
    "bind_action",
    "validate_action_schema",
]
