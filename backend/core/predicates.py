from __future__ import annotations

from typing import Any

from .domain_rules import (
    APPLIANCE_CYCLE_STEPS,
    BLOCKED_PLACE_TARGET_SEMANTICS,
    CLOTH_SEMANTICS,
    CONTAINMENT_CONTAINER_SEMANTICS,
    DUMP_RULES,
    PLACE_TARGET_TYPES,
    TRASHABLE_SEMANTICS,
)


MOVABLE_NODE_TYPES = frozenset({"movable_object"})


def node(state: dict[str, Any], node_id: str) -> dict[str, Any]:
    return state.get("nodes", {}).get(str(node_id)) or {}


def states(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("states") or {}


def mutable_states(item: dict[str, Any]) -> dict[str, Any]:
    return item.setdefault("states", {})


def semantic(item: dict[str, Any]) -> str:
    return str(item.get("semantic_type") or item.get("object_type") or "").strip().lower()


def node_type(item: dict[str, Any]) -> str:
    return str(item.get("node_type") or "").strip().lower()


def room_of(state: dict[str, Any], node_id: str) -> str:
    return str(state.get("room_of", {}).get(str(node_id)) or "")


def parent_of(state: dict[str, Any], node_id: str) -> str:
    node_id = str(node_id)
    return str(state.get("parent_of", {}).get(node_id) or node(state, node_id).get("parent") or "")


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
        accepted = {"held_by", "held_by_both"}
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
    return str(action_name).lower() in actions


def is_open(item: dict[str, Any]) -> bool:
    return bool(states(item).get("is_open", False))


def is_containment_container(item: dict[str, Any]) -> bool:
    return bool(item.get("blocks_containment")) or semantic(item) in CONTAINMENT_CONTAINER_SEMANTICS


def is_container_door(state: dict[str, Any], door_id: str) -> bool:
    door = node(state, door_id)
    if semantic(door) != "door":
        return False
    return is_containment_container(node(state, parent_of(state, door_id)))


def container_access_failure(state: dict[str, Any], container_id: str) -> str | None:
    # Storage slots and attached components inherit access from every host
    # container above them (slot -> cabinet, drawer -> cabinet, etc.).
    current_id = str(container_id or "")
    visited: set[str] = set()
    while current_id and current_id not in visited:
        visited.add(current_id)
        container = node(state, current_id)
        if container and is_containment_container(container) and not is_open(container):
            return f"container is closed: {current_id}"
        current_id = parent_of(state, current_id)
    return None


def capacity_place_failures(state: dict[str, Any], target_id: str) -> list[str]:
    target = node(state, target_id)
    capacity_value = target.get("max_capacity") or states(target).get("max_capacity") or states(target).get("capacity")
    if capacity_value in (None, ""):
        return []
    try:
        capacity = int(capacity_value)
    except (TypeError, ValueError):
        return []
    if len(children_of(state, target_id)) >= capacity:
        return [f"target capacity exceeded: {target_id}"]
    return []


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
        from .assets.object_library import OBJECT_LIBRARY

        template = OBJECT_LIBRARY.get(semantic_type)
        return {capability.name for capability in template.capabilities} if template else set()
    except (ImportError, AttributeError):
        return set()


def object_property(item: dict[str, Any], property_name: str, default: Any = None) -> Any:
    if property_name in item:
        return item[property_name]
    try:
        from .assets.object_library import OBJECT_LIBRARY

        template = OBJECT_LIBRARY.get(semantic(item))
        return template._property(property_name, default) if template else default
    except (ImportError, AttributeError):
        return default


def contained_capability_failures(state: dict[str, Any], item_id: str, target_id: str) -> list[str]:
    """Require declared item abilities demanded by a composite's storage slot."""
    target = node(state, target_id)
    required = {str(value).lower() for value in target.get("requires_contained_capabilities") or ()}
    if not required:
        return []
    item = node(state, item_id)
    available = object_capabilities(item)
    missing = sorted(required - available)
    if not missing:
        return []
    return [f"{semantic(item) or item_id} lacks required containment capability: {', '.join(missing)}"]


def process_input_failures(state: dict[str, Any], device_id: str) -> list[str]:
    device = node(state, device_id)
    required = {str(value).lower() for value in device.get("required_process_capabilities") or ()}
    if not required:
        return []
    child_ids = children_of(state, device_id)
    available: set[str] = set()
    for child_id in child_ids:
        child = node(state, child_id)
        explicit = child.get("capabilities")
        if isinstance(explicit, (list, tuple, set)):
            available.update(str(value).lower() for value in explicit)
        else:
            try:
                from .assets.object_library import OBJECT_LIBRARY
                template = OBJECT_LIBRARY.get(semantic(child))
                if template:
                    available.update(capability.name for capability in template.capabilities)
            except (ImportError, AttributeError):
                pass
    missing = sorted(required - available)
    return [f"process input capability missing: {value}" for value in missing]


def carrying_type_failures(state: dict[str, Any], held_id: str, target_id: str) -> list[str]:
    target = node(state, target_id)
    accepted = tuple(target.get("accepted_families") or ())
    if not accepted:
        return []
    held = node(state, held_id)
    held_family = str(held.get("family") or "")
    is_food = held_family == "food" or semantic(held) in {"food", "fruit", "vegetable", "drink", "juice", "milk", "egg", "bread"}
    wanted = "food" if is_food else "non_food"
    return [] if wanted in accepted else [f"{semantic(target)} only accepts {', '.join(accepted)} items"]


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


def requires_closed_to_start(item: dict[str, Any]) -> bool:
    capabilities = {str(value).lower() for value in (item.get("capabilities") or ())}
    # A timed device opts into the closed-door invariant through capability
    # metadata.  The semantic-cycle map remains only for legacy scene data.
    if "timed_device" in capabilities or "process_profile" in capabilities:
        return bool(item.get("requires_closed_to_start", True))
    return semantic(item) in APPLIANCE_CYCLE_STEPS and bool(item.get("requires_closed_to_start", True))


def device_door_failures(state: dict[str, Any], device_ids: list[str]) -> list[str]:
    failures: list[str] = []
    device_set = set(device_ids)
    for node_id, current_parent in state.get("parent_of", {}).items():
        if current_parent not in device_set:
            continue
        item = node(state, node_id)
        if str(item.get("door_kind") or "").lower() != "device":
            continue
        if bool(item.get("requires_closed_to_start", True)) and is_open(item):
            failures.append(f"device door must be closed before start: {node_id}")
    return failures


def place_target_failure(target: dict[str, Any]) -> str | None:
    target_semantic = semantic(target)
    if target_semantic == "trash_bin":
        return None
    if target_semantic in BLOCKED_PLACE_TARGET_SEMANTICS:
        return "place target should be a stable surface, container, room, or trash bin"
    if node_type(target) not in PLACE_TARGET_TYPES:
        return "place target should be a room, fixed object, or trash bin"
    return None


def trash_place_failures(state: dict[str, Any], held_id: str, target_id: str) -> list[str]:
    target = node(state, target_id)
    if semantic(target) != "trash_bin":
        return []
    held = node(state, held_id)
    failures: list[str] = []
    if semantic(held) not in TRASHABLE_SEMANTICS:
        failures.append("trash bin only accepts trashable food items")
    held_states = states(held)
    if not (bool(held_states.get("is_rotten", False)) or bool(held_states.get("is_burnt", False))):
        failures.append("food must be rotten or burnt before disposal")
    capacity = int(target.get("max_capacity") or states(target).get("max_capacity") or 3)
    if len(children_of(state, target_id)) >= capacity:
        failures.append(f"trash bin capacity exceeded: {target_id}")
    return failures


def dump_failures(state: dict[str, Any], actor_id: str, target_id: str) -> list[str]:
    held_id = holding(state, actor_id)
    if not held_id:
        return ["agent must hold a dumpable container"]
    held = node(state, held_id)
    held_semantic = semantic(held)
    target_semantic = semantic(node(state, target_id))
    rule = DUMP_RULES.get(held_semantic)
    if not rule:
        return [f"held object is not dumpable: {held_id}"]
    if target_semantic not in rule.target_semantics:
        return [f"cannot dump {held_semantic} into {target_semantic}"]
    if held_semantic == "trash_bin" and not children_of(state, held_id):
        return ["trash bin is empty"]
    if held_semantic == "cup":
        held_states = states(held)
        if float(held_states.get("fill_level") or 0.0) <= 0.0 and not bool(held_states.get("is_full", False)):
            return ["cup is empty"]
    if held_semantic == "wateringcan" and float(states(held).get("water_level", 100.0 if states(held).get("has_water") else 0.0) or 0.0) <= 0.0:
        return ["watering can is empty"]
    return []


def adjacent_room_failure(state: dict[str, Any], current_room: str, target_room: str) -> str | None:
    for edge in state.get("room_edges", []):
        source = str(edge.get("source_id") or "")
        target = str(edge.get("target_id") or "")
        if {source, target} == {current_room, target_room}:
            return None
    return f"target room is not adjacent: {current_room}->{target_room}"


def elevator_room_failure(state: dict[str, Any], current_room: str, target_room: str) -> str | None:
    """Allow a room transition through an open elevator serving both rooms."""
    for elevator_id, elevator in (state.get("nodes") or {}).items():
        if semantic(elevator) not in {"elevator", "lift"}:
            continue
        served = {str(room_id) for room_id in elevator.get("served_rooms") or elevator.get("transport_rooms") or []}
        if {current_room, target_room}.issubset(served) and is_open(elevator):
            return None
    return f"no open elevator connects: {current_room}->{target_room}"


def structural_door_failure(state: dict[str, Any], current_room: str, target_room: str) -> str | None:
    for item in state.get("nodes", {}).values():
        if str(item.get("door_kind") or "") != "structural":
            continue
        connected = {str(room_id) for room_id in item.get("connected_rooms") or []}
        if {current_room, target_room}.issubset(connected) and not is_open(item):
            return f"room path is blocked by closed door: {current_room}->{target_room}"
    return None


__all__ = [
    "MOVABLE_NODE_TYPES",
    "adjacent_room_failure",
    "capacity_place_failures",
    "carrying_type_failures",
    "children_of",
    "descendants_of",
    "container_access_failure",
    "process_input_failures",
    "controlled_targets",
    "device_door_failures",
    "dump_failures",
    "elevator_room_failure",
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
    "place_target_failure",
    "requires_closed_to_start",
    "room_of",
    "same_room",
    "semantic",
    "states",
    "structural_door_failure",
    "supports_action",
    "trash_place_failures",
]
