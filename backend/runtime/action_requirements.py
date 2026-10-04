from __future__ import annotations

from typing import Any

from backend.runtime.domain.queries import (
    children_of, descendants_of, is_containment_container, is_open, mutable_states, node, node_type,
    object_capabilities, parent_of, semantic, states, supports_action, holding,
)
from backend.runtime.process_definitions import DUMP_RULES, PLACE_TARGET_TYPES, TRASHABLE_SEMANTICS

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
    capacity_value = target.get("max_items") or states(target).get("capacity")
    if capacity_value in (None, ""):
        return []
    try:
        capacity = int(capacity_value)
    except (TypeError, ValueError):
        return []
    if len(children_of(state, target_id)) >= capacity:
        return [f"target capacity exceeded: {target_id}"]
    return []

def contained_capability_failures(state: dict[str, Any], item_id: str, target_id: str) -> list[str]:
    """Require declared item abilities demanded by a composite's storage slot."""
    target = node(state, target_id)
    required = {str(value).lower() for value in (target.get("accepted_capabilities") or ())}
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
    child_ids = descendants_of(state, device_id)
    available: set[str] = set()
    for child_id in child_ids:
        child = node(state, child_id)
        explicit = child.get("capabilities")
        if isinstance(explicit, (list, tuple, set)):
            available.update(str(value).lower() for value in explicit)
        else:
            try:
                from backend.generation.assets.object_library import OBJECT_LIBRARY
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

def requires_closed_to_start(item: dict[str, Any]) -> bool:
    capabilities = {str(value).lower() for value in (item.get("capabilities") or ())}
    # A timed device opts into the closed-door invariant through capability
    # metadata.  The semantic-cycle map remains only for legacy scene data.
    if "timed_device" in capabilities or "process_profile" in capabilities:
        return bool(item.get("requires_closed_to_start", True))
    process_definition = item.get("process_definition")
    if not isinstance(process_definition, dict):
        properties = item.get("capability_properties") or {}
        process_definition = properties.get("process_definition") if isinstance(properties, dict) else None
    return bool(process_definition) and bool(item.get("requires_closed_to_start", True))

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
    if (
        "place_target" not in object_capabilities(target)
        and not supports_action(target, "place")
        and not target.get("surface_spec")
        and not target.get("can_contain")
        and node_type(target) != "room"
    ):
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
    capacity = int(target.get("max_items") or states(target).get("capacity") or 3)
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

__all__ = ['adjacent_room_failure', 'capacity_place_failures', 'carrying_type_failures', 'contained_capability_failures', 'container_access_failure', 'device_door_failures', 'dump_failures', 'elevator_room_failure', 'place_target_failure', 'process_input_failures', 'requires_closed_to_start', 'structural_door_failure', 'trash_place_failures']
