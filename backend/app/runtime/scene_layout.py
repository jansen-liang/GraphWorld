from __future__ import annotations

import copy
import math
from collections import defaultdict, deque
from typing import Any


GRID_SIZE_METERS = 0.5
DEFAULT_ROOM_WIDTH_CELLS = 10
DEFAULT_ROOM_DEPTH_CELLS = 8
DEFAULT_DOOR_WIDTH_CELLS = 2


def _node_type(node: dict[str, Any]) -> str:
    return str(node.get("node_type") or node.get("type") or "")


def _semantic_type(node: dict[str, Any]) -> str:
    return str(node.get("semantic_type") or node.get("object_type") or "")


def _is_room(node: dict[str, Any]) -> bool:
    return _node_type(node) == "room" or _semantic_type(node) == "room"


def _is_floor(node: dict[str, Any]) -> bool:
    return _node_type(node) == "floor" or _semantic_type(node) == "floor"


def _is_door(node: dict[str, Any]) -> bool:
    return _semantic_type(node) == "door"


def _is_corridor(node: dict[str, Any]) -> bool:
    values = (
        node.get("id"),
        node.get("name"),
        node.get("name_cn"),
        node.get("semantic_type"),
        node.get("room_type"),
    )
    return any("corridor" in str(value or "").lower() or "走廊" in str(value or "") for value in values)


def _is_placeable(node: dict[str, Any]) -> bool:
    return not _is_room(node) and not _is_floor(node) and not _is_door(node) and _node_type(node) not in {"human", "robot", "agent"}


def _default_object_size_cells(node: dict[str, Any]) -> tuple[int, int]:
    semantic = _semantic_type(node)
    sizes_meters = {
        "bed": (2.0, 1.6),
        "sofa": (2.0, 0.9),
        "table": (1.4, 0.8),
        "desk": (1.3, 0.7),
        "counter": (1.8, 0.65),
        "wardrobe": (1.4, 0.65),
        "refrigerator": (0.8, 0.75),
        "washing_machine": (0.7, 0.7),
        "dishwasher": (0.65, 0.65),
        "toilet": (0.7, 0.45),
        "sink": (0.7, 0.5),
    }
    width, depth = sizes_meters.get(
        semantic,
        (0.32, 0.32) if _node_type(node) == "movable_object" else (0.8, 0.55),
    )
    return max(1, math.ceil(width / GRID_SIZE_METERS)), max(1, math.ceil(depth / GRID_SIZE_METERS))


def _room_ancestor(node_id: str, nodes_by_id: dict[str, dict[str, Any]]) -> str | None:
    seen: set[str] = set()
    current = nodes_by_id.get(node_id)
    while current is not None:
        current_id = str(current.get("id") or "")
        if current_id in seen:
            return None
        seen.add(current_id)
        if _is_room(current):
            return current_id
        current = nodes_by_id.get(str(current.get("parent") or ""))
    return None


def _connected_room_pairs(source: dict[str, Any], room_ids: set[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    seen: set[frozenset[str]] = set()
    for edge in source.get("edges") or []:
        if not isinstance(edge, dict) or str(edge.get("relation") or edge.get("edge_type") or "") != "connected":
            continue
        source_id = str(edge.get("source_id") or edge.get("source") or "")
        target_id = str(edge.get("target_id") or edge.get("target") or "")
        key = frozenset((source_id, target_id))
        if source_id in room_ids and target_id in room_ids and source_id != target_id and key not in seen:
            pairs.append((source_id, target_id))
            seen.add(key)
    return pairs


def _boxes_overlap(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ad = first
    bx, by, bw, bd = second
    return min(ax + aw, bx + bw) > max(ax, bx) and min(ay + ad, by + bd) > max(ay, by)


def _shared_wall(first: dict[str, Any], second: dict[str, Any]) -> tuple[str, int, int] | None:
    ax, ay = int(first["grid_x"]), int(first["grid_y"])
    aw, ad = int(first["width_cells"]), int(first["depth_cells"])
    bx, by = int(second["grid_x"]), int(second["grid_y"])
    bw, bd = int(second["width_cells"]), int(second["depth_cells"])
    if ax + aw == bx or bx + bw == ax:
        start, end = max(ay, by), min(ay + ad, by + bd)
        if end > start:
            return ("east" if ax + aw == bx else "west", start, end)
    if ay + ad == by or by + bd == ay:
        start, end = max(ax, bx), min(ax + aw, bx + bw)
        if end > start:
            return ("south" if ay + ad == by else "north", start, end)
    return None


def _place_rooms(room_ids: list[str], pairs: list[tuple[str, str]]) -> dict[str, dict[str, int]]:
    """Embed the small room graph on an integer grid with connected rooms sharing walls."""
    adjacency: dict[str, list[str]] = defaultdict(list)
    edges = {frozenset(pair) for pair in pairs}
    for first, second in pairs:
        adjacency[first].append(second)
        adjacency[second].append(first)
    positions: dict[str, tuple[int, int]] = {}

    def touches(candidate_id: str, candidate: tuple[int, int], other_id: str, other: tuple[int, int]) -> bool:
        a = {"grid_x": candidate[0], "grid_y": candidate[1], "width_cells": DEFAULT_ROOM_WIDTH_CELLS, "depth_cells": DEFAULT_ROOM_DEPTH_CELLS}
        b = {"grid_x": other[0], "grid_y": other[1], "width_cells": DEFAULT_ROOM_WIDTH_CELLS, "depth_cells": DEFAULT_ROOM_DEPTH_CELLS}
        shared = _shared_wall(a, b) is not None
        return shared == (frozenset((candidate_id, other_id)) in edges)

    def place_component(component: list[str], origin_x: int) -> None:
        root = max(component, key=lambda room_id: (len(adjacency[room_id]), -room_ids.index(room_id)))
        positions[root] = (origin_x, 0)
        queue = deque([root])
        parent: dict[str, str | None] = {root: None}
        order: list[str] = []
        while queue:
            current = queue.popleft()
            for neighbor in adjacency[current]:
                if neighbor not in parent:
                    parent[neighbor] = current
                    order.append(neighbor)
                    queue.append(neighbor)

        directions = (
            (-DEFAULT_ROOM_WIDTH_CELLS, 0),
            (DEFAULT_ROOM_WIDTH_CELLS, 0),
            (0, -DEFAULT_ROOM_DEPTH_CELLS),
            (0, DEFAULT_ROOM_DEPTH_CELLS),
        )

        def search(index: int) -> bool:
            if index == len(order):
                return all(_shared_wall(
                    {"grid_x": positions[a][0], "grid_y": positions[a][1], "width_cells": DEFAULT_ROOM_WIDTH_CELLS, "depth_cells": DEFAULT_ROOM_DEPTH_CELLS},
                    {"grid_x": positions[b][0], "grid_y": positions[b][1], "width_cells": DEFAULT_ROOM_WIDTH_CELLS, "depth_cells": DEFAULT_ROOM_DEPTH_CELLS},
                ) for a, b in pairs if a in positions and b in positions)
            room_id = order[index]
            parent_id = parent[room_id]
            if parent_id is None:
                return False
            px, py = positions[parent_id]
            for dx, dy in directions:
                candidate = (px + dx, py + dy)
                candidate_box = (candidate[0], candidate[1], DEFAULT_ROOM_WIDTH_CELLS, DEFAULT_ROOM_DEPTH_CELLS)
                if any(_boxes_overlap(candidate_box, (x, y, DEFAULT_ROOM_WIDTH_CELLS, DEFAULT_ROOM_DEPTH_CELLS)) for x, y in positions.values()):
                    continue
                if not all(touches(room_id, candidate, other_id, other) for other_id, other in positions.items()):
                    continue
                positions[room_id] = candidate
                if search(index + 1):
                    return True
                del positions[room_id]
            return False

        if not search(0):
            raise ValueError("Room connectivity cannot be embedded with at most one neighbor per wall.")

    remaining = set(room_ids)
    component_offset = 0
    while remaining:
        seed = next(room_id for room_id in room_ids if room_id in remaining)
        component: list[str] = []
        queue = deque([seed])
        remaining.remove(seed)
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in adjacency[current]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
        place_component(component, component_offset)
        component_offset = max(x for x, _ in positions.values()) + DEFAULT_ROOM_WIDTH_CELLS * 2

    min_x = min((x for x, _ in positions.values()), default=0)
    min_y = min((y for _, y in positions.values()), default=0)
    return {
        room_id: {
            "grid_x": x - min_x + 1,
            "grid_y": y - min_y + 1,
            "width_cells": DEFAULT_ROOM_WIDTH_CELLS,
            "depth_cells": DEFAULT_ROOM_DEPTH_CELLS,
        }
        for room_id, (x, y) in positions.items()
    }


def _assign_doors(
    pairs: list[tuple[str, str]],
    rooms: dict[str, dict[str, int]],
    nodes_by_id: dict[str, dict[str, Any]],
    source: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    room_nodes = {node_id: node for node_id, node in nodes_by_id.items() if _is_room(node)}
    candidates: dict[str, list[str]] = defaultdict(list)
    all_doors: list[str] = []
    for node_id, node in nodes_by_id.items():
        if _is_door(node) and str(node.get("parent") or "") in room_nodes:
            candidates[str(node.get("parent"))].append(node_id)
            all_doors.append(node_id)
    used: set[str] = set()
    result: dict[str, dict[str, Any]] = {}
    for room_a, room_b in pairs:
        if _is_corridor(room_nodes[room_a]) or _is_corridor(room_nodes[room_b]):
            continue
        choices = candidates[room_b] + candidates[room_a] + all_doors
        door_id = next((candidate for candidate in choices if candidate not in used), None)
        if door_id is None:
            base_id = f"door_{room_a}_{room_b}"
            door_id = base_id
            counter = 2
            while door_id in nodes_by_id:
                door_id = f"{base_id}_{counter}"
                counter += 1
            door_node = {
                "id": door_id,
                "name": "Door",
                "name_cn": "门",
                "node_type": "fixed_object",
                "semantic_class": "control",
                "semantic_type": "door",
                "mobility": "fixed",
                "states": {"is_open": False},
                "property": {"physical": {"movable": False}},
                "parent": room_b,
                "child": [],
                "interactive_actions": ["open", "close"],
                "door_kind": "structural",
                "blocks_visibility": True,
                "blocks_navigation": True,
            }
            source.setdefault("nodes", []).append(door_node)
            nodes_by_id[door_id] = door_node
            children = room_nodes[room_b].setdefault("child", [])
            if door_id not in children:
                children.append(door_id)
            candidates[room_b].append(door_id)
            all_doors.append(door_id)
        shared = _shared_wall(rooms[room_a], rooms[room_b])
        if shared is None:
            continue
        wall, start, end = shared
        width = min(DEFAULT_DOOR_WIDTH_CELLS, end - start)
        axis_origin = rooms[room_a]["grid_y"] if wall in {"east", "west"} else rooms[room_a]["grid_x"]
        offset = start - axis_origin + max(0, (end - start - width) // 2)
        result[door_id] = {
            "room_a_id": room_a,
            "room_b_id": room_b,
            "wall": wall,
            "offset_cells": offset,
            "width_cells": width,
        }
        used.add(door_id)
    return result


def _normalize_door_edges(source: dict[str, Any], doors: dict[str, dict[str, Any]]) -> None:
    door_ids = set(doors)
    source["edges"] = [
        edge for edge in source.get("edges") or []
        if not (
            isinstance(edge, dict)
            and str(edge.get("source_id") or edge.get("source") or "") in door_ids
            and str(edge.get("relation") or edge.get("edge_type") or "") == "connects"
        )
    ]
    for door_id, placement in doors.items():
        for room_key in ("room_a_id", "room_b_id"):
            source["edges"].append({
                "source_id": door_id,
                "target_id": placement[room_key],
                "edge_type": "structural_edge",
                "relation": "connects",
                "category": "structural",
                "properties": {},
            })


def ensure_scene_layout(source_json: dict[str, Any]) -> dict[str, Any]:
    """Return a scene copy with a deterministic, topology-aware grid layout."""
    source = copy.deepcopy(source_json)
    nodes = [node for node in source.get("nodes") or [] if isinstance(node, dict) and node.get("id")]
    nodes_by_id = {str(node["id"]): node for node in nodes}
    rooms_nodes = [node for node in nodes if _is_room(node)]
    room_ids = [str(node["id"]) for node in rooms_nodes]
    pairs = _connected_room_pairs(source, set(room_ids))
    existing = source.get("layout")
    is_grid_layout = isinstance(existing, dict) and isinstance(existing.get("rooms"), dict) and all(
        isinstance(value, dict) and "grid_x" in value for value in existing["rooms"].values()
    )
    if is_grid_layout:
        layout = copy.deepcopy(existing)
        layout.setdefault("units", "meter")
        layout.setdefault("grid_size", GRID_SIZE_METERS)
        layout.setdefault("doors", {})
        layout.setdefault("objects", {})
        source["layout"] = layout
        _normalize_door_edges(source, layout["doors"])
        return source

    room_layouts = _place_rooms(room_ids, pairs)
    door_layouts = _assign_doors(pairs, room_layouts, nodes_by_id, source)
    object_layouts: dict[str, dict[str, Any]] = {}
    objects_by_room: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        if _is_placeable(node):
            room_id = _room_ancestor(str(node["id"]), nodes_by_id)
            if room_id in room_layouts:
                objects_by_room[room_id].append(node)
    for room_id, room_objects in objects_by_room.items():
        room = room_layouts[room_id]
        cursor_x = cursor_y = 1
        row_depth = 1
        for node in room_objects:
            width, depth = _default_object_size_cells(node)
            width = min(width, room["width_cells"] - 2)
            depth = min(depth, room["depth_cells"] - 2)
            if cursor_x + width > room["width_cells"] - 1:
                cursor_x = 1
                cursor_y += row_depth + 1
                row_depth = 1
            if cursor_y + depth > room["depth_cells"] - 1:
                cursor_x, cursor_y, row_depth = 1, 1, 1
            object_layouts[str(node["id"])] = {
                "room_id": room_id,
                "grid_x": cursor_x,
                "grid_y": cursor_y,
                "width_cells": width,
                "depth_cells": depth,
                "rotation": 0,
            }
            cursor_x += width + 1
            row_depth = max(row_depth, depth)

    source["layout"] = {
        "units": "meter",
        "grid_size": GRID_SIZE_METERS,
        "rooms": room_layouts,
        "doors": door_layouts,
        "objects": object_layouts,
    }
    _normalize_door_edges(source, door_layouts)
    return source


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else None


def validate_scene_layout(source_json: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    nodes = [node for node in source_json.get("nodes") or [] if isinstance(node, dict)]
    node_ids = [str(node.get("id") or "") for node in nodes]
    nonempty_ids = [node_id for node_id in node_ids if node_id]
    if len(nonempty_ids) != len(set(nonempty_ids)):
        issues.append("Node IDs must be unique.")
    nodes_by_id = {str(node.get("id")): node for node in nodes if node.get("id")}
    room_nodes = {node_id: node for node_id, node in nodes_by_id.items() if _is_room(node)}

    layout = source_json.get("layout")
    if not isinstance(layout, dict):
        return ["Scene layout is missing."]
    if layout.get("units") != "meter":
        issues.append("Layout units must be 'meter'.")
    try:
        if float(layout.get("grid_size", 0)) <= 0:
            issues.append("layout.grid_size must be positive.")
    except (TypeError, ValueError):
        issues.append("layout.grid_size must be numeric.")
    rooms = layout.get("rooms")
    doors = layout.get("doors")
    objects = layout.get("objects")
    if not isinstance(rooms, dict):
        issues.append("layout.rooms must be an object.")
        rooms = {}
    if not isinstance(doors, dict):
        issues.append("layout.doors must be an object.")
        doors = {}
    if not isinstance(objects, dict):
        issues.append("layout.objects must be an object.")
        objects = {}

    room_boxes: list[tuple[str, int, int, int, int]] = []
    for room_id, geometry in rooms.items():
        if room_id not in room_nodes:
            issues.append(f"Unknown room layout target: {room_id}.")
            continue
        if not isinstance(geometry, dict):
            issues.append(f"Room {room_id} geometry must be an object.")
            continue
        values = [_integer(geometry.get(key)) for key in ("grid_x", "grid_y", "width_cells", "depth_cells")]
        if any(value is None for value in values):
            issues.append(f"Room {room_id} geometry must use integer grid cells.")
            continue
        x, y, width, depth = (int(value) for value in values if value is not None)
        if x < 0 or y < 0:
            issues.append(f"Room {room_id} must use non-negative grid coordinates.")
        if width <= 0 or depth <= 0:
            issues.append(f"Room {room_id} must have positive cell dimensions.")
        room_boxes.append((room_id, x, y, width, depth))

    for index, first in enumerate(room_boxes):
        first_id, ax, ay, aw, ad = first
        for second_id, bx, by, bw, bd in room_boxes[index + 1:]:
            if _boxes_overlap((ax, ay, aw, ad), (bx, by, bw, bd)):
                issues.append(f"Rooms {first_id} and {second_id} overlap.")

    pairs = _connected_room_pairs(source_json, set(room_nodes))
    pair_keys = {frozenset(pair) for pair in pairs}
    for first_id, second_id in pairs:
        if first_id in rooms and second_id in rooms and _shared_wall(rooms[first_id], rooms[second_id]) is None:
            issues.append(f"Connected rooms {first_id} and {second_id} must share a wall.")

    doors_by_pair: dict[frozenset[str], list[str]] = defaultdict(list)
    occupied_sides: set[tuple[str, str]] = set()
    opposite = {"west": "east", "east": "west", "north": "south", "south": "north"}
    for door_id, placement in doors.items():
        if door_id not in nodes_by_id or not _is_door(nodes_by_id[door_id]):
            issues.append(f"Unknown door layout target: {door_id}.")
            continue
        if not isinstance(placement, dict):
            issues.append(f"Door {door_id} placement must be an object.")
            continue
        room_a = str(placement.get("room_a_id") or "")
        room_b = str(placement.get("room_b_id") or "")
        wall = str(placement.get("wall") or "")
        if room_a not in rooms or room_b not in rooms or room_a == room_b:
            issues.append(f"Door {door_id} must connect two known rooms.")
            continue
        pair = frozenset((room_a, room_b))
        doors_by_pair[pair].append(door_id)
        if pair not in pair_keys:
            issues.append(f"Door {door_id} connects rooms without a connected relation.")
        shared = _shared_wall(rooms[room_a], rooms[room_b])
        if shared is None:
            issues.append(f"Door {door_id} endpoints must share a wall.")
            continue
        expected_wall, start, end = shared
        offset = _integer(placement.get("offset_cells"))
        width = _integer(placement.get("width_cells"))
        if wall != expected_wall:
            issues.append(f"Door {door_id} must be on the shared {expected_wall} wall of {room_a}.")
        axis_origin = int(rooms[room_a]["grid_y"] if expected_wall in {"east", "west"} else rooms[room_a]["grid_x"])
        if offset is None or width is None or width <= 0 or axis_origin + offset < start or axis_origin + offset + width > end:
            issues.append(f"Door {door_id} must fit inside the shared wall segment.")
        side_a = (room_a, expected_wall)
        side_b = (room_b, opposite[expected_wall])
        if side_a in occupied_sides or side_b in occupied_sides:
            issues.append(f"A room wall can contain at most one door ({door_id}).")
        occupied_sides.update((side_a, side_b))

    for room_a, room_b in pairs:
        count = len(doors_by_pair[frozenset((room_a, room_b))])
        is_open_passage = _is_corridor(room_nodes[room_a]) or _is_corridor(room_nodes[room_b])
        if is_open_passage and count:
            issues.append(f"Corridor connection {room_a} / {room_b} must be an open passage without a door.")
        if not is_open_passage and count != 1:
            issues.append(f"Connected rooms {room_a} and {room_b} must share exactly one door.")

    connect_edges = {
        (str(edge.get("source_id") or edge.get("source") or ""), str(edge.get("target_id") or edge.get("target") or ""))
        for edge in source_json.get("edges") or [] if isinstance(edge, dict)
        and str(edge.get("relation") or edge.get("edge_type") or "") == "connects"
    }
    for door_id, placement in doors.items():
        if isinstance(placement, dict):
            for room_key in ("room_a_id", "room_b_id"):
                room_id = str(placement.get(room_key) or "")
                if (door_id, room_id) not in connect_edges:
                    issues.append(f"Door {door_id} is missing its connects edge to {room_id}.")

    for object_id, placement in objects.items():
        if object_id not in nodes_by_id or not _is_placeable(nodes_by_id[object_id]):
            issues.append(f"Unknown object layout target: {object_id}.")
            continue
        if not isinstance(placement, dict):
            issues.append(f"Object {object_id} placement must be an object.")
            continue
        room_id = str(placement.get("room_id") or "")
        room = rooms.get(room_id)
        if not isinstance(room, dict):
            issues.append(f"Object {object_id} references unknown room {room_id or '<empty>'}.")
            continue
        values = [_integer(placement.get(key)) for key in ("grid_x", "grid_y", "width_cells", "depth_cells")]
        if any(value is None for value in values):
            issues.append(f"Object {object_id} placement must use integer grid cells.")
            continue
        x, y, width, depth = (int(value) for value in values if value is not None)
        if width <= 0 or depth <= 0:
            issues.append(f"Object {object_id} must have positive cell dimensions.")
        if x < 0 or y < 0 or x + width > int(room["width_cells"]) or y + depth > int(room["depth_cells"]):
            issues.append(f"Object {object_id} must remain inside room {room_id}.")

    for room_id in room_nodes:
        if room_id not in rooms:
            issues.append(f"Room {room_id} has no layout geometry.")
    return issues


__all__ = ["ensure_scene_layout", "validate_scene_layout"]
