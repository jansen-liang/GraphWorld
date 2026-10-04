from __future__ import annotations

import copy
from enum import Enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Mapping


class ActionType(str, Enum):
    RAISE_HAND = "raise_hand"
    LOWER_HAND = "lower_hand"
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
class Action:
    """Canonical semantic request independent of a frontend."""

    type: ActionType | str
    actor: str = ""
    target: str = ""
    object_id: str = ""
    params: Mapping[str, Any] = field(default_factory=dict)
    target_link_id: str | None = None
    hand: str | None = None
    hit_point: tuple[float, float, float] | None = None
    hit_normal: tuple[float, float, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        value = dict(self.params)
        value.update({"action": ActionType(self.type).value, "actor": self.actor, "target": self.target})
        if self.object_id:
            value["object"] = self.object_id
        if self.target_link_id is not None:
            value["target_link_id"] = self.target_link_id
        if self.hand is not None:
            value["hand"] = self.hand
        if self.hit_point is not None:
            value["hit_point"] = list(self.hit_point)
        if self.hit_normal is not None:
            value["hit_normal"] = list(self.hit_normal)
        return {key: item for key, item in value.items() if item not in ("", None)}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Action":
        reserved = {"action", "actor", "agent", "target", "object", "target_link_id", "hand", "hit_point", "hit_normal"}
        point = value.get("hit_point")
        normal = value.get("hit_normal")
        return cls(
            type=ActionType(str(value.get("action") or "wait")),
            actor=str(value.get("actor") or value.get("agent") or ""),
            target=str(value.get("target") or ""),
            object_id=str(value.get("object") or ""),
            params={key: item for key, item in value.items() if key not in reserved},
            target_link_id=str(value["target_link_id"]) if value.get("target_link_id") is not None else None,
            hand=str(value["hand"]) if value.get("hand") is not None else None,
            hit_point=tuple(float(item) for item in point) if isinstance(point, (list, tuple)) and len(point) == 3 else None,
            hit_normal=tuple(float(item) for item in normal) if isinstance(normal, (list, tuple)) and len(normal) == 3 else None,
        )

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
    ActionType.RAISE_HAND: ActionSpec(
        action_type=ActionType.RAISE_HAND, category="presentation", params=("agent", "hand"),
        description="Raise a hand when an interaction ray has no target.", mutates_edges=False, mutates_states=False,
        effect_summary=("record hand presentation intent",),
    ),
    ActionType.LOWER_HAND: ActionSpec(
        action_type=ActionType.LOWER_HAND, category="presentation", params=("agent", "hand"),
        description="Lower a hand after the interaction input is released.", mutates_edges=False, mutates_states=False,
        effect_summary=("record hand presentation intent",),
    ),
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



from backend.core.effect import Effect
from backend.core.requirement import Requirement


@dataclass(frozen=True)
class ActionDefinition:
    """Serializable semantic action declaration owned by core."""

    name: str
    parameters: tuple[str, ...] = ()
    preconditions: tuple[Requirement, ...] = ()
    effects: tuple[Effect, ...] = ()
    description: str = ""
    duration_steps: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "parameters": list(self.parameters),
            "preconditions": [item.to_dict() for item in self.preconditions],
            "effects": [item.to_dict() for item in self.effects],
            "description": self.description,
            "duration_steps": self.duration_steps,
        }


__all__ = ["ACTION_SPECS", "Action", "ActionDefinition", "ActionSpec", "ActionType", "action_spec"]
