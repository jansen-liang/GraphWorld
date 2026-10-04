from __future__ import annotations

from typing import Any

from backend.runtime.process_definitions import DUMP_RULES, PLACE_TARGET_TYPES, TRASHABLE_SEMANTICS


def node(state: dict[str, Any], node_id: str) -> dict[str, Any]:
    return state.get("nodes", {}).get(str(node_id)) or {}


def states(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("states") or {}


def mutable_states(item: dict[str, Any]) -> dict[str, Any]:
    return item.setdefault("states", {})


def semantic(item: dict[str, Any]) -> str:
    return str(item.get("semantic_type") or "").strip().lower()


def node_type(item: dict[str, Any]) -> str:
    return str(item.get("node_type") or "").strip().lower()


def is_robot_movable(item: dict[str, Any]) -> bool:
    capabilities = {str(value).lower() for value in (item.get("capabilities") or ())}
    return "pickable" in capabilities or "graspable" in capabilities


def room_of(state: dict[str, Any], node_id: str) -> str:
    return str(state.get("room_of", {}).get(str(node_id)) or "")


def parent_of(state: dict[str, Any], node_id: str) -> str:
    node_id = str(node_id)
    return str(state.get("parent_of", {}).get(node_id) or "")


def children_of(state: dict[str, Any], parent_id: str) -> list[str]:
    parent_id = str(parent_id)
    return [node_id for node_id, current_parent in state.get("parent_of", {}).items() if current_parent == parent_id]


def descendants_of(state: dict[str, Any], parent_id: str) -> list[str]:
    """Return all nested children, including objects inside storage slots."""
    result: list[str] = []
    frontier = [str(parent_id)]
    while frontier:
        current = frontier.pop()
        children = children_of(state, current)
        result.extend(children)
        frontier.extend(children)
    return result


def holding(state: dict[str, Any], actor_id: str, hand: str | None = None) -> str:
    actor_id = str(actor_id)
    parent_map = state.get("parent_of", {})
    relation_map = state.get("relation_of", {})
    normalized_hand = str(hand or "").lower()
    if not normalized_hand:
        accepted = {"held_by", "held_by_left", "held_by_both"}
    elif normalized_hand in {"right", "primary"}:
        accepted = {"held_by", "held_by_right", "held_by_both"}
    elif normalized_hand == "left":
        accepted = {"held_by_left", "held_by_both"}
    else:
        accepted = {f"held_by_{normalized_hand}"}
    for node_id, current_parent in parent_map.items():
        if current_parent == actor_id and relation_map.get(node_id) in accepted:
            return node_id
    return ""


def held_objects(state: dict[str, Any], actor_id: str) -> dict[str, str]:
    """Return occupied hand slots without changing the legacy held_by fact."""
    result: dict[str, str] = {}
    parent_map = state.get("parent_of", {})
    relation_map = state.get("relation_of", {})
    for node_id, current_parent in parent_map.items():
        if current_parent != str(actor_id):
            continue
        relation = str(relation_map.get(node_id) or "")
        if relation == "held_by":
            result.setdefault("right", str(node_id))
        elif relation == "held_by_both":
            result.setdefault("left", str(node_id))
            result.setdefault("right", str(node_id))
        elif relation.startswith("held_by_"):
            result.setdefault(relation.removeprefix("held_by_"), str(node_id))
    return result


def same_room(state: dict[str, Any], a: str, b: str) -> bool:
    room_a = room_of(state, a)
    room_b = room_of(state, b)
    if room_a and room_a == room_b:
        return True
    target = node(state, b)
    connected_rooms = {str(room_id) for room_id in target.get("connected_rooms") or []}
    return bool(room_a and room_a in connected_rooms)


def supports_action(item: dict[str, Any], action_name: str) -> bool:
    actions = {str(action).lower() for action in item.get("interactive_actions") or []}
    wanted = str(action_name).lower()
    if wanted in actions:
        return True
    # Canonical scene snapshots may preserve capabilities while omitting the
    # derived interactive_actions list. Resolve the affordance from capability
    # names as the source of truth instead of rejecting a valid interaction.
    capability_actions = {
        "switchable": {"press", "turn_on", "turn_off", "toggle"},
        "openable": {"open", "close"},
        "pickable": {"pick", "grab", "release"},
        "place_target": {"place", "remove"},
        "cleanable": {"brush", "clean"},
        "foldable": {"fold", "unfold"},
        "flushable": {"press", "flush"},
        "water_source_control": {"press", "open", "close"},
        "dumpable": {"dump"},
    }
    return any(wanted in capability_actions.get(str(capability).lower(), set()) for capability in (item.get("capabilities") or ()))


def is_open(item: dict[str, Any]) -> bool:
    value = states(item).get("is_open", False)
    # Scene JSON may contain serialized booleans.  Treating the string
    # ``"false"`` as truthy reverses the open/close action resolver.
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "open"}
    return bool(value)


def is_containment_container(item: dict[str, Any]) -> bool:
    return (
        bool(item.get("blocks_containment"))
        or "containment_blocker" in object_capabilities(item)
        or ("is_open" in states(item) and supports_action(item, "place"))
    )


def is_container_door(state: dict[str, Any], door_id: str) -> bool:
    door = node(state, door_id)
    if semantic(door) != "door":
        return False
    return is_containment_container(node(state, parent_of(state, door_id)))






def object_capabilities(item: dict[str, Any]) -> set[str]:
    explicit = item.get("capabilities")
    if isinstance(explicit, (list, tuple, set)):
        return {str(capability).lower() for capability in explicit}
    semantic_type = semantic(item)
    if not semantic_type:
        return set()
    legacy_aliases = {
        "detergent": {"laundry_detergent"},
    }
    if semantic_type in legacy_aliases:
        return set(legacy_aliases[semantic_type])
    try:
        from backend.generation.assets.object_library import OBJECT_LIBRARY

        template = OBJECT_LIBRARY.get(semantic_type)
        return {capability.name for capability in template.capabilities} if template else set()
    except (ImportError, AttributeError):
        return set()


def object_property(item: dict[str, Any], property_name: str, default: Any = None) -> Any:
    if property_name in item:
        return item[property_name]
    try:
        from backend.generation.assets.object_library import OBJECT_LIBRARY

        template = OBJECT_LIBRARY.get(semantic(item))
        return template._property(property_name, default) if template else default
    except (ImportError, AttributeError):
        return default








def controlled_targets(state: dict[str, Any], control_id: str) -> list[str]:
    targets: list[str] = []
    for edge in state.get("control_edges", []):
        if str(edge.get("relation") or "").lower() != "controls":
            continue
        if str(edge.get("source_id") or "") == str(control_id):
            target_id = str(edge.get("target_id") or "")
            if target_id and target_id in state.get("nodes", {}):
                targets.append(target_id)
    return targets


















__all__ = [
    "is_robot_movable",
    "children_of",
    "descendants_of",
    "controlled_targets",
    "holding",
    "held_objects",
    "is_container_door",
    "is_containment_container",
    "is_open",
    "mutable_states",
    "node",
    "object_capabilities",
    "object_property",
    "node_type",
    "parent_of",
    "room_of",
    "same_room",
    "semantic",
    "states",
    "supports_action",
]
