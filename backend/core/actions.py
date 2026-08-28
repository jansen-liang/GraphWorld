from __future__ import annotations

from enum import Enum
from dataclasses import dataclass


class ActionType(str, Enum):
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
}


def action_spec(action_type: ActionType | str) -> ActionSpec:
    normalized = ActionType(action_type)
    return ACTION_SPECS[normalized]
