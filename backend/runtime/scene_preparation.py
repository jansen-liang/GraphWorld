from __future__ import annotations

import copy
from typing import Any

from backend.generation.assets.npc_library import get_default_npcs
from backend.runtime.systems.resource import scene_resource_pool_specs
from backend.runtime.scene_utils import node, scene_type


def ensure_node(scene: dict[str, Any], item: dict[str, Any]) -> None:
    normalized = copy.deepcopy(item)
    # Water quantity has one canonical representation. Older scene exports
    # used normalized `fill_level`; migrate it at the preparation boundary so
    # runtime rules and renderers only need `water_level` (0..100).
    if str(normalized.get("semantic_type") or "").lower() == "sink":
        states = normalized.setdefault("states", {})
        if "water_level" not in states and "fill_level" in states:
            try:
                states["water_level"] = max(0.0, min(100.0, float(states.get("fill_level") or 0.0) * 100.0))
            except (TypeError, ValueError):
                states["water_level"] = 0.0
        states.pop("fill_level", None)
        states["has_water"] = float(states.get("water_level") or 0.0) > 0.0
    host_id = str(normalized.pop("host_id", "") or "")
    if {"parent", "child", "inventory", "floor_id", "runtime_relation"} & normalized.keys():
        raise ValueError("scene nodes must encode relationships as edges")
    existing = node(scene, str(normalized["id"]))
    if existing:
        for key, value in normalized.items():
            if key in {"child", "resource_pool"}:
                continue
            existing[key] = value
        if isinstance(normalized.get("resource_pool"), dict):
            current_pool = existing.setdefault("resource_pool", {})
            for key, value in normalized["resource_pool"].items():
                if key in {"available_count", "dispensed_count", "consumed_count"} and key in current_pool:
                    continue
                current_pool[key] = copy.deepcopy(value)
    else:
        scene.setdefault("nodes", []).append(normalized)
    if host_id:
        ensure_edge(scene, host_id, str(normalized["id"]), "at" if normalized.get("node_type") == "agent" else "in")


def ensure_edge(scene: dict[str, Any], source_id: str, target_id: str, relation: str) -> None:
    for edge in scene.setdefault("edges", []):
        if edge.get("source_id") == source_id and edge.get("target_id") == target_id and edge.get("relation") == relation:
            return
    scene["edges"].append(
        {
            "source_id": source_id,
            "target_id": target_id,
            "edge_type": "runtime_seed_edge",
            "relation": relation,
            "category": "runtime_seed",
            "properties": {},
        }
    )


def robot_ids(robot_count: int) -> tuple[str, ...]:
    return tuple(f"robot_{index:02d}" for index in range(1, max(0, int(robot_count)) + 1))


def human_ids(human_count: int) -> tuple[str, ...]:
    count = max(0, int(human_count))
    return tuple("human_resident" if index == 1 else f"human_resident_{index:02d}" for index in range(1, count + 1))


def actor_specs_for_scene(scene: dict[str, Any], human_count: int) -> list[dict[str, str]]:
    if scene_type(scene) == "hospital":
        defaults = get_default_npcs("hospital")
        return defaults[: max(0, int(human_count))]
    if scene_type(scene) == "supermarket":
        defaults = get_default_npcs("supermarket")
        return defaults[: max(0, int(human_count))]
    if scene_type(scene) == "office":
        defaults = get_default_npcs("office")
        return defaults[: max(0, int(human_count))]
    if scene_type(scene) == "factory":
        defaults = get_default_npcs("factory")
        return defaults[: max(0, int(human_count))]
    return [
        {
            "id": human_id,
            "name": "resident",
            "name_cn": "resident",
            "role": "resident",
            "host_id": "bed_bedroom",
            "room": "bedroom",
            "activity": "sleeping",
            "persona": "weekday_office_worker",
        }
        for human_id in human_ids(human_count)
    ]


def prepare_scene(raw_scene: dict[str, Any], robot_count: int, human_count: int) -> dict[str, Any]:
    scene = copy.deepcopy(raw_scene)
    scene.setdefault("world_state", {}).setdefault("step", 0)
    scene["world_state"].setdefault("time_min", 360)
    scene["world_state"].setdefault("minutes_per_step", 10)
    scene["world_state"].setdefault("day", 1)
    scene["world_state"].setdefault("room_humidity", {})
    if scene_type(scene) == "home":
        ensure_demo_elevator(scene)
        ensure_laundry_detergent_station(scene)
    if scene_type(scene) in {"home", "supermarket", "office", "factory"}:
        for spec in actor_specs_for_scene(scene, human_count):
            human_id = str(spec["id"])
            parent_id = str(spec.get("host_id") or "outside_home")
            ensure_node(
                scene,
                {
                    "id": human_id,
                    "name": spec.get("name", "human"),
                    "name_cn": spec.get("name_cn", spec.get("name", "human")),
                    "node_type": "agent",
                    "semantic_type": "human",
                    "role": spec.get("role", "resident"),
                    "persona": spec.get("persona", ""),
                    "current_activity": spec.get("activity", ""),
                    "states": {},
                    "host_id": parent_id,
                    "interactive_actions": [],
                },
            )
            ensure_edge(scene, parent_id, human_id, "at")
    for robot_id in robot_ids(robot_count):
        if scene_type(scene) == "hospital":
            robot_parent = "lobby"
        elif scene_type(scene) == "supermarket":
            robot_parent = "entrance"
        elif scene_type(scene) in {"office", "factory"}:
            robot_parent = "entrance"
        else:
            robot_parent = "living_room"
        ensure_node(
            scene,
            {
                "id": robot_id,
                "name": "robot",
                "name_cn": "robot",
                "node_type": "agent",
                "semantic_type": "robot",
                "states": {},
                "host_id": robot_parent,
                "capabilities": ["agent", "first_person_control"],
                "interactive_actions": [],
            },
        )
        ensure_edge(scene, robot_parent, robot_id, "at")
    support_nodes = []
    if scene_type(scene) == "home":
        support_nodes.extend(
            [
                {
                    "id": "laundry_detergent_station_outside_home",
                    "name": "laundry detergent station",
                    "name_cn": "洗衣液资源站",
                    "node_type": "object",
                    "semantic_type": "resource_station",
                    "states": {},
                    "structure": {
                        "components": [
                            {
                                "role": "storage_slot",
                                "semantic_type": "storage_slot",
                                "node_type": "object",
                                "mount_face": "interior",
                                "anchor": [0.5, 0.5, 0.5],
                                "capabilities": ["place_target", "receptacle"],
                                "repeatable": False,
                            }
                        ],
                        "storage": {
                            "kind": "open",
                            "levels": 1,
                            "columns": 1,
                            "depth_cm": 30.0,
                            "capacity_per_slot": 10,
                            "accepted_capabilities": ["laundry_detergent"],
                        },
                    },
                    "host_id": "outside_home",
                    "interactive_actions": ["move"],
                },
                {
                    "id": "garbage_station_outside_home",
                    "name": "garbage station",
                    "name_cn": "垃圾处理站",
                    "node_type": "object",
                    "semantic_type": "garbage_station",
                    "states": {},
                    "host_id": "outside_home",
                    "interactive_actions": ["move", "dump"],
                },
                {
                    "id": "trash_bin_living_room",
                    "name": "trash bin",
                    "name_cn": "trash bin",
                    "node_type": "object",
                    "capabilities": ["pickable"],
                    "semantic_type": "trash_bin",
                    "states": {"is_dirty": False},
                    "host_id": "living_room",
                    "interactive_actions": ["pick", "place"],
                    "max_capacity": 3,
                },
                {
                    "id": "food_living_room",
                    "name": "food",
                    "name_cn": "food",
                    "node_type": "object",
                    "capabilities": ["pickable"],
                    "semantic_type": "food",
                    "states": {"is_cooked": True, "is_rotten": False},
                    "host_id": "fridge_kitchen",
                    "interactive_actions": ["pick", "place"],
                },
                {
                    "id": "plate_living_room",
                    "name": "plate",
                    "name_cn": "plate",
                    "node_type": "object",
                    "capabilities": ["pickable"],
                    "semantic_type": "plate",
                    "states": {"is_dirty": False},
                    "host_id": "dishwasher_kitchen",
                    "interactive_actions": ["pick", "place", "brush"],
                },
                {
                    "id": "cup_living_room",
                    "name": "cup",
                    "name_cn": "cup",
                    "node_type": "object",
                    "capabilities": ["pickable"],
                    "semantic_type": "cup",
                    "states": {"is_dirty": False, "is_wet": False},
                    "host_id": "dishwasher_kitchen",
                    "interactive_actions": ["pick", "place", "brush"],
                },
            ]
        )
        # Seed ten reusable detergent packets in the station's slot. They are
        # ordinary nodes, so the existing storage-stack LIFO retrieval and
        # placement flow can be reused without a dispenser-specific action.
        station_id = "laundry_detergent_station_outside_home"
        slot_id = f"{station_id}_slot_l1_c1"
        support_nodes.append({
            "id": slot_id,
            "name": "laundry detergent slot",
            "name_cn": "洗衣液槽",
            "node_type": "object",
            "semantic_type": "storage_slot",
            "component_role": "storage_slot",
            "capabilities": ["place_target", "receptacle"],
            "accepted_capabilities": ["laundry_detergent"],
            "max_items": 10,
            "storage_stack": [f"{station_id}_packet_{index}" for index in range(1, 11)],
            "host_id": station_id,
            "interactive_actions": ["place", "pick"],
        })
        for index in range(1, 11):
            support_nodes.append({
                "id": f"{station_id}_packet_{index}",
                "name": "laundry detergent packet",
                "name_cn": "洗衣液包",
                "node_type": "object",
                "semantic_type": "laundry_detergent",
                "capabilities": ["pickable", "laundry_detergent"],
                "states": {"amount": 1.0},
                "host_id": slot_id,
                "interactive_actions": ["pick", "place"],
            })
    support_nodes.extend(scene_resource_pool_specs(scene_type(scene), scene))
    for item in support_nodes:
        ensure_node(scene, item)
    for item in scene.get("nodes") or []:
        if str(item.get("semantic_type") or "") == "sink":
            actions = item.setdefault("interactive_actions", [])
            if "dump" not in actions:
                actions.append("dump")
    return scene


def ensure_demo_elevator(scene: dict[str, Any]) -> None:
    """Add one visible elevator to the unused strip below outside_home.

    This is a generated demo asset, not a renderer fallback. The nodes and
    layout placement are persisted in the prepared scene so every adapter sees
    the same elevator identity and geometry anchor.
    """
    node_ids = {str(item.get("id") or "") for item in scene.get("nodes") or []}
    layout = scene.setdefault("layout", {})
    rooms = layout.setdefault("rooms", {})
    outside = rooms.get("outside_home")
    if not isinstance(outside, dict):
        return
    outside.setdefault("floor_number", 1)

    # The demo scene is intentionally small, but it must still exercise the
    # multi-floor elevator contract. Each upper floor has one landing room;
    # these are ordinary Floor/Room/Node records, not elevator-specific types.
    nodes = scene.setdefault("nodes", [])
    edges = scene.setdefault("edges", [])
    floor_specs = (("F2", "outside_home_f2", 2), ("F3", "outside_home_f3", 3))
    for floor_id, room_id, floor_number in floor_specs:
        if floor_id not in node_ids:
            nodes.append({
                "id": floor_id,
                "name": f"Floor {floor_number}",
                "name_cn": f"第 {floor_number} 层",
                "node_type": "floor",
                "semantic_class": "space",
                "semantic_type": "floor",
                "mobility": "structural",
                "states": {},
                "floor_number": floor_number,
                "editor_id": floor_id,
            })
            node_ids.add(floor_id)
        if room_id not in node_ids:
            nodes.append({
                "id": room_id,
                "name": room_id,
                "name_cn": f"电梯厅 {floor_number} 层",
                "node_type": "room",
                "semantic_class": "space",
                "semantic_type": "room",
                "mobility": "fixed",
                "states": {},
                "floor_number": floor_number,
                "editor_id": room_id,
            })
            node_ids.add(room_id)
        if not any(
            str(edge.get("source_id")) == floor_id
            and str(edge.get("target_id")) == room_id
            and str(edge.get("relation")) == "contains"
            for edge in edges
        ):
            edges.append({
                "source_id": floor_id,
                "target_id": room_id,
                "edge_type": "structural_edge",
                "relation": "contains",
                "category": "structural",
                "properties": {},
            })

        # Upper-floor plans share the same XY projection as the first floor.
        # The 2-D editor selects one floor at a time; the 3-D renderer applies
        # floor_number as the vertical offset.
        if room_id not in rooms:
            room_copy = copy.deepcopy(outside)
            room_copy["floor_number"] = floor_number
            room_copy["grid_x"] = int(outside.get("grid_x", 0))
            room_copy["grid_y"] = int(outside.get("grid_y", 0))
            rooms[room_id] = room_copy

    objects = layout.setdefault("objects", {})
    cell_cm = float(layout.get("grid_size") or 0.1) * 100
    # Place the shaft just beyond the outside room's south wall. It is an
    # additional structure, not a replacement for the outside room.
    y_cm = float(outside.get("y_cm") or float(outside.get("grid_y") or 0) * float(layout.get("grid_size") or 0.1) * 100) + float(outside.get("depth_cm") or 400.0) + 40.0
    shaft_id = "elevator_shaft_outside_home"
    car_id = "elevator_car_outside_home"
    objects.pop(shaft_id, None)
    obsolete_shaft_ids = {f"{shaft_id}_f2", f"{shaft_id}_f3"}
    nodes[:] = [item for item in nodes if str(item.get("id")) not in obsolete_shaft_ids]
    for obsolete_id in obsolete_shaft_ids:
        rooms.pop(obsolete_id, None)
    edges[:] = [edge for edge in edges if str(edge.get("source_id")) not in obsolete_shaft_ids and str(edge.get("target_id")) not in obsolete_shaft_ids]
    # One shaft room spans the full vertical travel. Floor-specific hall doors
    # connect each landing room to this same room.
    shaft_floor_ids = {"outside_home": shaft_id}
    # Migrate the first prototype's incorrect containment edges before adding
    # the proper floor/shaft topology.
    edges[:] = [
        edge for edge in edges
        if not (
            str(edge.get("source_id")) == "outside_home"
            and str(edge.get("target_id")) in {shaft_id, car_id}
            and str(edge.get("relation")) == "in"
        )
    ]
    # A shaft is a vertical space, represented in the floor plan by one room
    # section per floor. The sections share the same XY footprint and are
    # connected vertically; the moving car remains an ordinary Object.
    shaft_width = 26
    shaft_depth = 26
    shaft_grid_x = int(outside.get("grid_x", 0)) + max(0, (int(outside.get("width_cells", shaft_width)) - shaft_width) // 2)
    shaft_grid_y = int(outside.get("grid_y", 0)) + int(outside.get("depth_cells", 8))
    for floor_id, shaft_room_id in shaft_floor_ids.items():
        floor_number = 1
        if shaft_room_id not in node_ids:
            nodes.append({
                "id": shaft_room_id,
                "editor_id": shaft_room_id,
                "node_type": "room",
                "role": "shaft",
                "semantic_type": "elevator_shaft",
                "name": "elevator shaft",
                "name_cn": f"电梯井 {floor_number} 层",
                "mobility": "structural",
                "floor_number": 1,
                "states": {},
            })
            node_ids.add(shaft_room_id)
        if shaft_room_id not in rooms:
            rooms[shaft_room_id] = {
                "grid_x": shaft_grid_x,
                "grid_y": shaft_grid_y,
                "width_cells": shaft_width,
                "depth_cells": shaft_depth,
                "floor_number": floor_number,
            }
        floor_parent_id = "F1"
        if not any(str(edge.get("source_id")) == floor_parent_id and str(edge.get("target_id")) == shaft_room_id and str(edge.get("relation")) == "contains" for edge in edges):
            edges.append({"source_id": floor_parent_id, "target_id": shaft_room_id, "relation": "contains", "edge_type": "structural_edge", "category": "structural", "properties": {}})
        for landing_id in ("outside_home", "outside_home_f2", "outside_home_f3"):
            if not any({str(edge.get("source_id")), str(edge.get("target_id"))} == {landing_id, shaft_room_id} and str(edge.get("relation")) == "connected" for edge in edges):
                edges.append({"source_id": landing_id, "target_id": shaft_room_id, "relation": "connected", "edge_type": "spatial_edge", "category": "spatial", "properties": {}})
        # One landing door belongs to the floor's room and connects it to the
        # shaft section. The same physical opening is projected at each floor.
        door_id = f"elevator_hall_door_f{floor_number}"
        if door_id not in node_ids:
            nodes.append({
                "id": door_id, "editor_id": door_id, "node_type": "object",
                "role": "root", "semantic_type": "door", "name": "elevator hall door",
                "name_cn": f"电梯厅门 {floor_number} 层", "states": {"is_open": False},
                "interactive_actions": [], "door_kind": "elevator_hall",
            })
            node_ids.add(door_id)
        else:
            # Relationships belong to edges in the canonical schema.  Older
            # generated scenes may still carry this legacy field, so remove it
            # while normalizing the existing node in place.
            next(item for item in nodes if str(item.get("id")) == door_id).pop("floor_id", None)
        if not any(str(edge.get("source_id")) == floor_id and str(edge.get("target_id")) == door_id and str(edge.get("relation")) == "contains" for edge in edges):
            edges.append({"source_id": floor_id, "target_id": door_id, "relation": "contains", "edge_type": "structural_edge", "category": "structural", "properties": {}})
        if not any(str(edge.get("source_id")) == door_id and str(edge.get("target_id")) == shaft_room_id and str(edge.get("relation")) == "connects" for edge in edges):
            edges.append({"source_id": door_id, "target_id": shaft_room_id, "relation": "connects", "edge_type": "structural_edge", "category": "spatial", "properties": {}})
        if not any(str(edge.get("source_id")) == door_id and str(edge.get("target_id")) == floor_id and str(edge.get("relation")) == "connects" for edge in edges):
            edges.append({"source_id": door_id, "target_id": floor_id, "relation": "connects", "edge_type": "structural_edge", "category": "spatial", "properties": {}})
        layout.setdefault("doors", {})[door_id] = {
            "room_a_id": floor_id,
            "room_b_id": shaft_id,
            "wall": "south",
            "offset_cells": max(0, (int(outside.get("width_cells", 10)) - 18) // 2),
            "width_cells": 18,
            "hinge_side": "start",
            "open_direction": "inward",
            "open_angle_deg": 90,
        }
    # Upper landings use the same single shaft room, with their own hall door.
    for floor_number, floor_id in ((2, "outside_home_f2"), (3, "outside_home_f3")):
        door_id = f"elevator_hall_door_f{floor_number}"
        if door_id not in node_ids:
            nodes.append({
                "id": door_id, "editor_id": door_id, "node_type": "object", "role": "root",
                "semantic_type": "door", "name": "elevator hall door", "name_cn": f"电梯厅门 {floor_number} 层",
                "states": {"is_open": False}, "interactive_actions": [], "door_kind": "elevator_hall",
            })
            node_ids.add(door_id)
        else:
            next(item for item in nodes if str(item.get("id")) == door_id).pop("floor_id", None)
        for source_id, target_id, relation in ((floor_id, door_id, "contains"), (door_id, shaft_id, "connects"), (door_id, floor_id, "connects")):
            if not any(str(edge.get("source_id")) == source_id and str(edge.get("target_id")) == target_id and str(edge.get("relation")) == relation for edge in edges):
                edges.append({"source_id": source_id, "target_id": target_id, "relation": relation, "edge_type": "structural_edge", "category": "spatial", "properties": {}})
        layout.setdefault("doors", {})[door_id] = {
            "room_a_id": floor_id, "room_b_id": shaft_id, "wall": "south",
            "offset_cells": max(0, (int(outside.get("width_cells", 10)) - 18) // 2), "width_cells": 18,
            "hinge_side": "start", "open_direction": "inward", "open_angle_deg": 90,
        }
    # Keep the stable shaft identifier for existing runtime references.
    if shaft_id not in node_ids:
        node_ids.add(shaft_id)
    shaft_node = next(item for item in nodes if str(item.get("id")) == shaft_id)
    shaft_node.update({"node_type": "room", "role": "shaft", "semantic_type": "elevator_shaft"})
    for item in nodes:
        if str(item.get("door_kind") or "") == "elevator_hall":
            item["interactive_actions"] = []
    if car_id not in node_ids:
        nodes.append({
            "id": car_id, "editor_id": car_id, "node_type": "object", "role": "root",
            "semantic_type": "elevator", "name": "elevator car", "capabilities": ["transport_device", "contain", "openable"],
            "states": {"is_open": True, "current_floor": "outside_home", "direction": "idle", "door_phase": "dwelling", "dwell_remaining": 2, "current_height": 0.0},
            "floor_ids": ["outside_home", "outside_home_f2", "outside_home_f3"],
            "floor_elevations": {"outside_home": 0.0, "outside_home_f2": 3.2, "outside_home_f3": 6.4},
            "served_rooms": ["outside_home", "outside_home_f2", "outside_home_f3"],
            "transport_rooms": ["outside_home", "outside_home_f2", "outside_home_f3"],
            "elevator_system_id": "elevator_system_demo", "elevator_car_id": car_id, "shaft_id": shaft_id,
            "interactive_actions": ["move", "open", "close", "press"],
        })
        node_ids.add(car_id)
    for target_id in (car_id,):
        if not any(
            str(edge.get("source_id")) == shaft_id
            and str(edge.get("target_id")) == target_id
            and str(edge.get("relation")) == "in"
            for edge in edges
        ):
            edges.append({"source_id": shaft_id, "target_id": target_id, "relation": "in", "category": "spatial", "properties": {}})
    car = next(item for item in nodes if str(item.get("id")) == car_id)
    car["floor_ids"] = ["outside_home", "outside_home_f2", "outside_home_f3"]
    car["served_rooms"] = list(car["floor_ids"])
    car["transport_rooms"] = list(car["floor_ids"])
    car["floor_elevations"] = {"outside_home": 0.0, "outside_home_f2": 3.2, "outside_home_f3": 6.4}
    car_states = car.setdefault("states", {})
    current_floor = str(car_states.get("current_floor") or "outside_home")
    elevations = car["floor_elevations"]
    if current_floor not in elevations:
        current_floor = "outside_home"
        car_states["current_floor"] = current_floor
    # A prepared scene starts at its semantic floor. Never carry a runtime
    # height from an earlier run: values such as current_floor=f2 with
    # current_height=0 are numerically valid but physically contradictory and
    # make the cabin render below the landing. Runtime movement owns this
    # field only after the simulation has started.
    current_height = float(elevations[current_floor])
    car_states["current_height"] = current_height
    car_states["target_height"] = current_height
    car_states["motion_state"] = "idle"
    car_states["direction"] = "idle"
    car_states["arrival_pending"] = False
    # Keep the authored transport speed explicit.  Without this field the
    # runtime fallback (6.4m per tick) reaches the next floor in one tick,
    # which makes the car appear to jump between floors.
    car.setdefault("speed_m_per_step", 2.0)
    # Cabin controls are graph-backed child nodes. Their visual meshes are
    # rendered under the car composite, while these identities are the
    # interaction targets for future elevator request rules.
    button_specs = [
        ("f1", "1F", "floor_button"),
        ("f2", "2F", "floor_button"),
        ("f3", "3F", "floor_button"),
        ("open", "open", "open_button"),
        ("close", "close", "close_button"),
    ]
    for suffix, label, role in button_specs:
        button_id = f"{car_id}_{suffix}_button"
        if button_id not in node_ids:
            nodes.append({
                "id": button_id, "editor_id": button_id, "node_type": "object",
                "role": "component", "component_role": role, "semantic_type": "button",
                "owner_id": car_id,
                "name": f"elevator {label} button", "capabilities": ["switchable"],
                "interactive_actions": ["press"], "states": {"is_pressed": False, "is_on": False},
                "request_floor": {"f1": "outside_home", "f2": "outside_home_f2", "f3": "outside_home_f3"}.get(suffix, ""),
            })
            node_ids.add(button_id)
        else:
            button_node = next((item for item in nodes if str(item.get("id")) == button_id), None)
            if isinstance(button_node, dict):
                button_node.setdefault("states", {}).setdefault("is_on", False)
                if suffix in {"f1", "f2", "f3"}:
                    button_node["request_floor"] = {"f1": "outside_home", "f2": "outside_home_f2", "f3": "outside_home_f3"}[suffix]
        if not any(str(edge.get("source_id")) == car_id and str(edge.get("target_id")) == button_id and str(edge.get("relation")) == "structure" for edge in edges):
            edges.append({
                "source_id": car_id, "target_id": button_id, "relation": "structure",
                "edge_type": "structural_edge", "category": "structural",
                "properties": {"parent": car_id, "child": button_id, "joint_type": "fixed", "origin": {"position": [0, 0, 0]}},
            })
        if suffix in {"f1", "f2", "f3"} and not any(
            str(edge.get("source_id")) == button_id
            and str(edge.get("target_id")) == car_id
            and str(edge.get("relation")) == "controls"
            for edge in edges
        ):
            edges.append({
                "source_id": button_id, "target_id": car_id, "relation": "controls",
                "edge_type": "control_edge", "category": "logical",
                "properties": {"request_kind": "cabin", "floor_id": {"f1": "outside_home", "f2": "outside_home_f2", "f3": "outside_home_f3"}[suffix]},
            })
    # Hall call panels belong to each landing Room, not to the moving car.
    # They are ordinary visible button Objects placed beside that floor's
    # hall door. Their up/down requests are independent graph targets.
    for floor_number, floor_id in ((1, "outside_home"), (2, "outside_home_f2"), (3, "outside_home_f3")):
        landing = rooms.get(floor_id) or outside
        if floor_number == 1:
            allowed_suffixes = (("up", "up"),)
        elif floor_number == 3:
            allowed_suffixes = (("down", "down"),)
        else:
            allowed_suffixes = (("up", "up"), ("down", "down"))
        allowed_ids = {f"elevator_hall_f{floor_number}_{suffix}_button" for suffix, _ in allowed_suffixes}
        # Re-preparing a scene must also remove buttons invalidated by the
        # floor boundary rule (the old demo emitted both directions on every
        # landing).
        for stale_suffix in ("up", "down"):
            stale_id = f"elevator_hall_f{floor_number}_{stale_suffix}_button"
            if stale_id in allowed_ids:
                continue
            node_ids.discard(stale_id)
            nodes[:] = [item for item in nodes if str(item.get("id") or "") != stale_id]
            edges[:] = [edge for edge in edges if stale_id not in {str(edge.get("source_id") or ""), str(edge.get("target_id") or "")}]
            objects.pop(stale_id, None)
        for suffix, label in allowed_suffixes:
            button_id = f"elevator_hall_f{floor_number}_{suffix}_button"
            if button_id not in node_ids:
                nodes.append({
                    "id": button_id, "editor_id": button_id, "node_type": "object",
                    "role": "root", "semantic_type": "button", "component_role": "hall_call_button",
                    "name": f"elevator hall {label} button", "name_cn": f"电梯厅{label}按钮",
                    "capabilities": ["switchable"], "interactive_actions": ["press"],
                    "states": {"is_pressed": False},
                    "request_floor": floor_id,
                    "request_kind": f"hall_{suffix}",
                })
                node_ids.add(button_id)
            else:
                button_node = next((item for item in nodes if str(item.get("id")) == button_id), None)
                if isinstance(button_node, dict):
                    button_node.pop("floor_id", None)
                    button_node["request_floor"] = floor_id
                    button_node["request_kind"] = f"hall_{suffix}"
            room_width = int(landing.get("width_cells", 50))
            room_depth = int(landing.get("depth_cells", 40))
            door_width = 18
            door_offset = max(0, (room_width - door_width) // 2)
            # Keep both call buttons outside the door sweep.  The right-hand
            # button is positioned after the complete opening, so widening
            # the hall door cannot make it overlap the doorway.
            button_x = int(landing.get("grid_x", 0)) + (
                door_offset - 3 if suffix == "up" else door_offset + door_width + 1
            )
            button_y = int(landing.get("grid_y", 0)) + max(1, room_depth - 3)
            objects[button_id] = {
                "room_id": floor_id, "grid_x": button_x - int(landing.get("grid_x", 0)),
                "grid_y": button_y - int(landing.get("grid_y", 0)),
                "width_cells": 2, "depth_cells": 1,
                "x_cm": button_x * cell_cm, "y_cm": button_y * cell_cm, "z_cm": 120.0,
                "width_cm": 20.0, "depth_cm": 8.0, "height_cm": 8.0,
                "placement_mode": "surface", "rotation": 0,
            }
            if not any(
                str(edge.get("source_id")) == floor_id
                and str(edge.get("target_id")) == button_id
                and str(edge.get("relation")) == "contains"
                for edge in edges
            ):
                edges.append({
                    "source_id": floor_id,
                    "target_id": button_id,
                    "relation": "contains",
                    "edge_type": "structural_edge",
                    "category": "structural",
                    "properties": {},
                })
            if not any(
                str(edge.get("source_id")) == button_id
                and str(edge.get("target_id")) == car_id
                and str(edge.get("relation")) == "controls"
                for edge in edges
            ):
                edges.append({
                    "source_id": button_id,
                    "target_id": car_id,
                    "relation": "controls",
                    "edge_type": "control_edge",
                    "category": "logical",
                    "properties": {"request_kind": f"hall_{suffix}", "floor_id": floor_id},
                })
    x_cm = shaft_grid_x * cell_cm
    y_cm = shaft_grid_y * cell_cm
    for object_id, width, depth, height in ((shaft_id, 260.0, 260.0, 320.0), (car_id, 190.0, 190.0, 240.0)):
        if object_id == shaft_id:
            continue
        objects[object_id] = {
            "room_id": shaft_id, "grid_x": 1, "grid_y": 1,
            "width_cells": max(1, round(width / cell_cm)),
            "depth_cells": max(1, round(depth / cell_cm)),
            "x_cm": x_cm, "y_cm": y_cm, "z_cm": 0.0,
            "width_cm": width, "depth_cm": depth, "height_cm": height,
            "placement_mode": "surface", "rotation": 0,
        }


def ensure_laundry_detergent_station(scene: dict[str, Any]) -> None:
    """Add the shared home detergent station and ten reusable packets."""
    if scene_type(scene) != "home":
        return
    station_id = "laundry_detergent_station_outside_home"
    slot_id = f"{station_id}_slot_l1_c1"
    ensure_node(scene, {
        "id": station_id, "name": "laundry detergent station", "name_cn": "洗衣液资源站",
        "node_type": "object", "semantic_type": "resource_station", "states": {},
        "structure": {"components": [], "storage": {"kind": "open", "levels": 1, "columns": 1,
            "depth_cm": 30.0, "capacity_per_slot": 10,
            "accepted_capabilities": ["laundry_detergent"]}},
        "host_id": "outside_home", "interactive_actions": ["move"],
    })
    ensure_node(scene, {
        "id": slot_id, "name": "laundry detergent slot", "name_cn": "洗衣液槽",
        "node_type": "object", "semantic_type": "storage_slot", "component_role": "storage_slot",
        "capabilities": ["place_target", "receptacle"],
        "accepted_capabilities": ["laundry_detergent"], "max_items": 10,
        "storage_stack": [f"{station_id}_packet_{index}" for index in range(1, 11)],
        "interactive_actions": ["place", "pick"],
    })
    # The slot is a PartTree child of the station, not an independently
    # placed room object. Keep the generated storage interaction target on the
    # station while its contents retain normal containment edges.
    scene["edges"] = [
        edge for edge in scene.get("edges", [])
        if not (
            str(edge.get("target_id") or "") == slot_id
            and str(edge.get("relation") or "") in {"at", "in", "inside", "contains", "on"}
        )
    ]
    ensure_edge(scene, station_id, slot_id, "component_of")
    for index in range(1, 11):
        packet_id = f"{station_id}_packet_{index}"
        ensure_node(scene, {
            "id": packet_id, "name": "laundry detergent packet", "name_cn": "洗衣液包",
            "node_type": "object", "semantic_type": "laundry_detergent",
            "capabilities": ["pickable", "laundry_detergent"], "states": {"amount": 1.0},
            "storage_mode": "hidden", "visibility": False, "collision_enabled": False,
            "host_id": slot_id, "interactive_actions": ["pick", "place"],
        })
        # The initial stock is physically inside the station slot. This
        # positional edge is required so packets inherit the station's room
        # anchor instead of being laid out as ten independent room objects.
        ensure_edge(scene, slot_id, packet_id, "contains")
    # This helper is used by both editor reads and simulation starts, some of
    # which have already passed the general materialization boundary.
    from backend.generation.assets.object_templates import materialize_templates
    materialize_templates(scene)


def prepare_home_scene(raw_scene: dict[str, Any], robot_count: int, human_count: int) -> dict[str, Any]:
    return prepare_scene(raw_scene, robot_count=robot_count, human_count=human_count)
