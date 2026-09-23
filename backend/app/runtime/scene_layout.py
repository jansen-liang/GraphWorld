from __future__ import annotations

import copy
import math
from collections import defaultdict, deque
from typing import Any

from backend.core.composition import validate_composition_nodes
from backend.core.composition import composition_for


GRID_SIZE_METERS = 0.1
LEGACY_GRID_SIZE_METERS = 0.5
DEFAULT_ROOM_WIDTH_CELLS = 10
DEFAULT_ROOM_DEPTH_CELLS = 8
DEFAULT_DOOR_WIDTH_METERS = 1.0
GEOMETRY_RESOLUTION_CM = 1
DEFAULT_ROOM_HEIGHT_CM = 260

OBJECT_DIMENSIONS_CM = {
    # Consumables are intentionally small in the editor; quantity is a
    # runtime state and must not be represented by a larger mesh.
    "vegetable": (15, 15, 15),
    "fruit": (12, 12, 12),
    "food": (18, 18, 12),
    "tissue": (8, 8, 2),
    "tissuebox": (14, 10, 12),
    "cabinet": (120, 55, 90),
    "shelf": (150, 50, 180),
    "rack": (150, 50, 180),
    "wardrobe": (140, 65, 180),
    "shoe_rack": (100, 35, 100),
    "drawer": (80, 50, 75),
    "counter": (180, 65, 90),
    "chair": (60, 60, 85),
    "seat": (60, 60, 85),
    "toothpaste": (5, 5, 18),
    "toothbrush": (2, 2, 18),
    "button": (8, 8, 4),
    "knob": (6, 6, 5),
    "room_light": (30, 30, 10),
    "faucet": (20, 20, 30),
    "microwave": (60, 45, 35),
    "dishwasher": (60, 65, 85),
    "washing_machine": (60, 65, 85),
    "washer": (60, 65, 85),
    "refrigerator": (90, 80, 180),
    "fridge": (90, 80, 180),
    "coffeemachine": (35, 30, 45),
    "coffee_machine": (35, 30, 45),
    "bed": (200, 160, 50),
    "sofa": (200, 90, 85),
    "table": (140, 80, 75),
    "desk": (130, 70, 75),
}


ROOM_DIMENSIONS_CELLS = {
    # Discrete representatives of RoomTypeSpec area/aspect priors.
    "entrance": (8, 6),
    "living_room": (12, 10),
    "kitchen": (8, 6),
    "bedroom": (10, 8),
    "bathroom": (6, 5),
    "balcony": (8, 4),
    "outside_home": (10, 8),
    "corridor": (14, 4),
    "corridor_main": (14, 4),
    "lobby": (12, 8),
    "waiting_area": (10, 8),
    "open_office": (14, 10),
    "meeting_room": (8, 6),
    "warehouse": (14, 10),
    "workshop": (12, 10),
    "assembly_line": (14, 8),
}


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


def _room_dimensions(node: dict[str, Any]) -> tuple[int, int]:
    semantic = _semantic_type(node).lower()
    node_id = str(node.get("id") or "").lower()
    for key in (node_id, semantic):
        if key in ROOM_DIMENSIONS_CELLS:
            base_width, base_depth = ROOM_DIMENSIONS_CELLS[key]
            scale = round(LEGACY_GRID_SIZE_METERS / GRID_SIZE_METERS)
            return base_width * scale, base_depth * scale
    if "corridor" in node_id or "corridor" in semantic:
        base_width, base_depth = ROOM_DIMENSIONS_CELLS["corridor"]
        scale = round(LEGACY_GRID_SIZE_METERS / GRID_SIZE_METERS)
        return base_width * scale, base_depth * scale
    scale = round(LEGACY_GRID_SIZE_METERS / GRID_SIZE_METERS)
    return DEFAULT_ROOM_WIDTH_CELLS * scale, DEFAULT_ROOM_DEPTH_CELLS * scale


def _default_object_size_cells(node: dict[str, Any]) -> tuple[int, int]:
    semantic = _semantic_type(node)
    sizes_meters = {
        "button": (0.25, 0.25),
        "knob": (0.2, 0.2),
        "room_light": (0.3, 0.3),
        "faucet": (0.3, 0.3),
        "display": (1.2, 0.6),
        "computer": (1.0, 0.7),
        "cabinet": (1.2, 0.55),
        "drawer": (0.8, 0.5),
        "shelf": (1.5, 0.5),
        "rack": (1.5, 0.5),
        "seat": (0.6, 0.6),
        "chair": (0.6, 0.6),
        "machine": (1.5, 1.0),
        "washing_machine": (0.8, 0.8),
        "washer": (0.8, 0.8),
        "dishwasher": (0.8, 0.65),
        "microwave": (0.6, 0.5),
        "refrigerator": (0.9, 0.8),
        "fridge": (0.9, 0.8),
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
        "toothpaste": (0.05, 0.05),
        "toothbrush": (0.03, 0.03),
        "vegetable": (0.15, 0.15),
        "fruit": (0.12, 0.12),
        "food": (0.18, 0.18),
        "tissue": (0.08, 0.08),
        "tissuebox": (0.14, 0.10),
    }
    width, depth = sizes_meters.get(
        semantic,
        (0.32, 0.32) if _node_type(node) == "movable_object" else (0.8, 0.55),
    )
    return max(1, math.ceil(width / GRID_SIZE_METERS)), max(1, math.ceil(depth / GRID_SIZE_METERS))


def _object_dimensions_cm(node: dict[str, Any], placement: dict[str, Any], catalog_dimensions: dict[str, tuple[float, float, float]] | None = None) -> tuple[int, int, int]:
    semantic = _semantic_type(node).lower()
    if catalog_dimensions and semantic in catalog_dimensions:
        return tuple(max(1, int(round(value))) for value in catalog_dimensions[semantic])  # type: ignore[return-value]
    if semantic in OBJECT_DIMENSIONS_CM:
        return OBJECT_DIMENSIONS_CM[semantic]
    width = max(1, int(round(float(placement.get("width_cells", 1)) * GRID_SIZE_METERS * 100)))
    depth = max(1, int(round(float(placement.get("depth_cells", 1)) * GRID_SIZE_METERS * 100)))
    return width, depth, 80


def _add_physical_geometry(source: dict[str, Any], catalog_dimensions: dict[str, tuple[float, float, float]] | None = None) -> None:
    layout = source.get("layout")
    if not isinstance(layout, dict):
        return
    nodes_by_id = {str(node.get("id")): node for node in source.get("nodes") or [] if isinstance(node, dict) and node.get("id")}
    cell_cm = int(round(float(layout.get("grid_size", GRID_SIZE_METERS)) * 100))
    layout["geometry_resolution_cm"] = GEOMETRY_RESOLUTION_CM
    layout["doors"] = {
        door_id: {
            **door,
            "hinge_side": door.get("hinge_side", "start"),
            "open_direction": door.get("open_direction", "inward"),
            "open_angle_deg": int(door.get("open_angle_deg", 90)),
        }
        for door_id, door in (layout.get("doors") or {}).items()
    }
    layout["rooms"] = {
        room_id: {
            **geometry,
            "x_cm": int(geometry.get("grid_x", 0)) * cell_cm,
            "y_cm": int(geometry.get("grid_y", 0)) * cell_cm,
            "z_cm": 0,
            "width_cm": int(geometry.get("width_cells", 1)) * cell_cm,
            "depth_cm": int(geometry.get("depth_cells", 1)) * cell_cm,
            "height_cm": int(geometry.get("height_cm", DEFAULT_ROOM_HEIGHT_CM)),
        }
        for room_id, geometry in (layout.get("rooms") or {}).items()
    }
    enriched_objects = {}
    for object_id, placement in (layout.get("objects") or {}).items():
        room = layout["rooms"].get(placement.get("room_id"), {})
        node = nodes_by_id.get(str(object_id), {})
        width_cm, depth_cm, height_cm = _object_dimensions_cm(node, placement, catalog_dimensions)
        # Keep editor-authored physical coordinates across graph/layout reads.
        # Older layouts omit these fields, so their grid coordinates remain the
        # deterministic fallback. In particular, z_cm is the object's height
        # above its placement base and must not be reset during re-enrichment.
        default_x_cm = int(room.get("x_cm", 0)) + int(placement.get("grid_x", 0)) * cell_cm
        default_y_cm = int(room.get("y_cm", 0)) + int(placement.get("grid_y", 0)) * cell_cm
        parent_object_id = str(placement.get("parent_object_id") or "")
        parent_geometry = enriched_objects.get(parent_object_id) if parent_object_id else None
        if placement.get("placement_mode") == "contained" and parent_geometry:
            # Component/storage children follow the host footprint. Their
            # vertical offset remains local, while X/Y are derived from the
            # current host so moving a cabinet also moves its drawers/slots.
            default_x_cm = int(parent_geometry.get("x_cm", default_x_cm))
            default_y_cm = int(parent_geometry.get("y_cm", default_y_cm))
        contained_parent = placement.get("placement_mode") == "contained" and parent_geometry
        enriched_objects[object_id] = {
            **placement,
            "grid_x": int(parent_geometry.get("grid_x", placement.get("grid_x", 0))) if contained_parent else placement.get("grid_x", 0),
            "grid_y": int(parent_geometry.get("grid_y", placement.get("grid_y", 0))) if contained_parent else placement.get("grid_y", 0),
            "x_cm": default_x_cm if contained_parent else int(placement.get("x_cm", default_x_cm)),
            "y_cm": default_y_cm if contained_parent else int(placement.get("y_cm", default_y_cm)),
            "z_cm": int(placement.get("z_cm", 0)),
            "width_cm": width_cm,
            "depth_cm": depth_cm,
            "height_cm": height_cm,
        }
    layout["objects"] = enriched_objects


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


def _object_layout_priority(node: dict[str, Any]) -> tuple[int, str]:
    """Place structural furniture first so small controls can use remaining space."""
    semantic = _semantic_type(node).lower()
    priority = {
        "bed": 0,
        "sofa": 0,
        "wardrobe": 1,
        "refrigerator": 1,
        "fridge": 1,
        "counter": 1,
        "table": 2,
        "desk": 2,
        "shelf": 2,
        "rack": 2,
        "sink": 3,
        "stove": 3,
        "dishwasher": 3,
        "washing_machine": 3,
        "washer": 3,
        "microwave": 4,
        "tv": 4,
        "button": 8,
        "room_light": 8,
        "faucet": 8,
    }.get(semantic, 5)
    return priority, str(node.get("id") or "")


def _preferred_object_positions(
    semantic: str,
    room_semantic: str,
    room_width: int,
    room_depth: int,
    width: int,
    depth: int,
) -> list[tuple[int, int, str]]:
    """Return deterministic anchors: furniture hugs walls, work surfaces form a zone."""
    max_x = max(1, room_width - 1 - width)
    max_y = max(1, room_depth - 1 - depth)
    center_x = max(1, (room_width - width) // 2)
    center_y = max(1, (room_depth - depth) // 2)
    anchors: list[tuple[int, int, str]] = []
    if semantic in {"bed", "wardrobe"}:
        anchors.extend([(1, 1, "north-west"), (max_x, 1, "north-east"), (1, max_y, "south-west")])
    elif semantic in {"sofa", "tv", "shelf", "rack"}:
        anchors.extend([(1, 1, "north-wall"), (max_x, max_y, "south-east"), (1, max_y, "south-west")])
    elif room_semantic in {"kitchen", "workshop", "warehouse"} or semantic in {
        "counter", "refrigerator", "fridge", "sink", "stove", "dishwasher", "microwave", "washing_machine", "washer",
    }:
        anchors.extend([(1, 1, "service-wall"), (center_x, 1, "service-wall"), (max_x, 1, "service-wall"), (max_x, center_y, "side-wall")])
    elif semantic in {"table", "desk"}:
        anchors.extend([(center_x, center_y, "work-zone"), (1, max_y, "south-wall"), (max_x, max_y, "south-east")])
    elif semantic in {"button", "room_light", "faucet", "knob", "light"}:
        anchors.extend([(1, 1, "control-wall"), (max_x, 1, "control-wall"), (1, max_y, "control-wall"), (max_x, max_y, "control-wall")])
    else:
        anchors.extend([(center_x, center_y, "center"), (1, 1, "north-west"), (max_x, max_y, "south-east")])
    # Always retain a deterministic scan fallback for crowded rooms.
    anchors.extend((x, y, "scan") for y in range(1, max_y + 1) for x in range(1, max_x + 1))
    seen: set[tuple[int, int]] = set()
    return [(x, y, anchor) for x, y, anchor in anchors if not ((x, y) in seen or seen.add((x, y)))]


def _place_objects_in_room(room_id: str, room: dict[str, int], room_node: dict[str, Any], room_objects: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    room_semantic = _semantic_type(room_node).lower()
    occupied: list[tuple[int, int, int, int]] = []
    result: dict[str, dict[str, Any]] = {}
    mounted_index = 0
    for node in sorted(room_objects, key=_object_layout_priority):
        width, depth = _default_object_size_cells(node)
        width = min(width, max(1, room["width_cells"] - 2))
        depth = min(depth, max(1, room["depth_cells"] - 2))
        parent_id = str(node.get("parent") or "")
        parent_placement = result.get(parent_id)
        if parent_placement and parent_id != room_id:
            # Contents, controls, and parts share the parent's footprint. They
            # are represented in the graph, but do not consume another floor cell.
            result[str(node["id"])] = {
                "room_id": room_id,
                "grid_x": parent_placement["grid_x"],
                "grid_y": parent_placement["grid_y"],
                "width_cells": width,
                "depth_cells": depth,
                "rotation": 0,
                "layout_anchor": "contained",
                "placement_mode": "contained",
                "parent_object_id": parent_id,
            }
            continue
        semantic = _semantic_type(node).lower()
        if semantic in {"button", "room_light", "faucet", "knob", "light"}:
            # Controls and fixtures are wall/ceiling mounted, so they should
            # not consume a floor slot or collide with kitchen work surfaces.
            result[str(node["id"])] = {
                "room_id": room_id,
                "grid_x": mounted_index % max(1, room["width_cells"] - width + 1),
                "grid_y": 0,
                "width_cells": width,
                "depth_cells": depth,
                "rotation": 0,
                "layout_anchor": "wall-mounted",
                "placement_mode": "wall_mounted",
            }
            mounted_index += 1
            continue
        position = next(
            ((x, y, anchor) for x, y, anchor in _preferred_object_positions(
                _semantic_type(node).lower(), room_semantic, room["width_cells"], room["depth_cells"], width, depth,
            ) if not any(_boxes_overlap((x, y, width, depth), existing) for existing in occupied)),
            (1, 1, "fallback"),
        )
        x, y, anchor = position
        occupied.append((x, y, width, depth))
        result[str(node["id"])] = {
            "room_id": room_id,
            "grid_x": x,
            "grid_y": y,
            "width_cells": width,
            "depth_cells": depth,
            "rotation": 0,
            "layout_anchor": anchor,
        }
    return result


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


def _place_rooms(room_nodes: list[dict[str, Any]], pairs: list[tuple[str, str]]) -> dict[str, dict[str, int]]:
    """Embed the small room graph on an integer grid with connected rooms sharing walls."""
    room_ids = [str(node["id"]) for node in room_nodes]
    dimensions = {str(node["id"]): _room_dimensions(node) for node in room_nodes}
    adjacency: dict[str, list[str]] = defaultdict(list)
    edges = {frozenset(pair) for pair in pairs}
    for first, second in pairs:
        adjacency[first].append(second)
        adjacency[second].append(first)
    positions: dict[str, tuple[int, int]] = {}

    def geometry(room_id: str, position: tuple[int, int]) -> dict[str, int]:
        width, depth = dimensions[room_id]
        return {"grid_x": position[0], "grid_y": position[1], "width_cells": width, "depth_cells": depth}

    def touches(candidate_id: str, candidate: tuple[int, int], other_id: str, other: tuple[int, int]) -> bool:
        a = geometry(candidate_id, candidate)
        b = geometry(other_id, other)
        shared = _shared_wall(a, b) is not None
        # Non-connected rooms may touch at a corner or along a wall. Only
        # connected pairs impose a shared-wall requirement; forbidding every
        # incidental contact makes heterogeneous room sizes impossible to embed.
        return shared if frozenset((candidate_id, other_id)) in edges else True

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

        def search(index: int) -> bool:
            if index == len(order):
                return all(_shared_wall(
                    geometry(a, positions[a]), geometry(b, positions[b]),
                ) for a, b in pairs if a in positions and b in positions)
            room_id = order[index]
            parent_id = parent[room_id]
            if parent_id is None:
                return False
            px, py = positions[parent_id]
            parent_width, parent_depth = dimensions[parent_id]
            room_width, room_depth = dimensions[room_id]
            directions = (
                (px - room_width, py),
                (px + parent_width, py),
                (px, py - room_depth),
                (px, py + parent_depth),
            )
            for candidate in directions:
                candidate_box = (candidate[0], candidate[1], room_width, room_depth)
                if any(_boxes_overlap(candidate_box, (*other_position, *dimensions[other_id])) for other_id, other_position in positions.items()):
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
        component_offset = max(x + dimensions[room_id][0] for room_id, (x, _) in positions.items()) + DEFAULT_ROOM_WIDTH_CELLS * 2

    min_x = min((x for x, _ in positions.values()), default=0)
    min_y = min((y for _, y in positions.values()), default=0)
    return {
        room_id: {
            "grid_x": x - min_x + 1,
            "grid_y": y - min_y + 1,
            "width_cells": dimensions[room_id][0],
            "depth_cells": dimensions[room_id][1],
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
        width = min(max(1, round(DEFAULT_DOOR_WIDTH_METERS / GRID_SIZE_METERS)), end - start)
        axis_origin = rooms[room_a]["grid_y"] if wall in {"east", "west"} else rooms[room_a]["grid_x"]
        offset = start - axis_origin + max(0, (end - start - width) // 2)
        result[door_id] = {
            "room_a_id": room_a,
            "room_b_id": room_b,
            "wall": wall,
            "offset_cells": offset,
            "width_cells": width,
            "hinge_side": "start",
            "open_direction": "inward",
            "open_angle_deg": 90,
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


def _door_sweeps(rooms: dict[str, dict[str, Any]], doors: dict[str, dict[str, Any]]) -> dict[str, list[tuple[int, int, int, int]]]:
    """Return conservative grid rectangles reserved for inward door leaves."""
    sweeps: dict[str, list[tuple[int, int, int, int]]] = defaultdict(list)
    for placement in doors.values():
        if not isinstance(placement, dict):
            continue
        room_id = str(placement.get("room_a_id") or "")
        room = rooms.get(room_id)
        offset = _integer(placement.get("offset_cells"))
        width = _integer(placement.get("width_cells"))
        if not isinstance(room, dict) or offset is None or width is None or width <= 0:
            continue
        rw, rd = int(room["width_cells"]), int(room["depth_cells"])
        wall = str(placement.get("wall") or "")
        if wall == "north": sweep = (offset, 0, width, width)
        elif wall == "south": sweep = (offset, max(0, rd - width), width, width)
        elif wall == "west": sweep = (0, offset, width, width)
        elif wall == "east": sweep = (max(0, rw - width), offset, width, width)
        else: continue
        sweeps[room_id].append(sweep)
    return sweeps


def _reposition_door_blockers(layout: dict[str, Any], nodes_by_id: dict[str, dict[str, Any]]) -> None:
    """Move floor objects out of door leaf sweeps while preserving containment."""
    rooms = layout.get("rooms") or {}
    objects = layout.get("objects") or {}
    sweeps = _door_sweeps(rooms, layout.get("doors") or {})
    for room_id, room_sweeps in sweeps.items():
        room = rooms.get(room_id)
        if not isinstance(room, dict): continue
        entries = [(oid, item) for oid, item in objects.items() if item.get("room_id") == room_id and item.get("placement_mode") != "wall_mounted"]
        occupied: list[tuple[int, int, int, int]] = []
        for oid, item in sorted(entries, key=lambda pair: _object_layout_priority(nodes_by_id.get(pair[0], {}))):
            if item.get("placement_mode") == "contained":
                continue
            width, depth = int(item.get("width_cells", 1)), int(item.get("depth_cells", 1))
            current = (int(item.get("grid_x", 0)), int(item.get("grid_y", 0)), width, depth)
            blocked = any(_boxes_overlap(current, sweep) for sweep in room_sweeps)
            candidate = current
            if blocked:
                for y in range(1, max(1, int(room["depth_cells"]) - depth + 1)):
                    for x in range(1, max(1, int(room["width_cells"]) - width + 1)):
                        trial = (x, y, width, depth)
                        if not any(_boxes_overlap(trial, other) for other in occupied) and not any(_boxes_overlap(trial, sweep) for sweep in room_sweeps):
                            candidate = trial
                            break
                    if candidate != current: break
            item["grid_x"], item["grid_y"] = candidate[0], candidate[1]
            occupied.append(candidate)


def ensure_scene_layout(source_json: dict[str, Any], catalog_dimensions: dict[str, tuple[float, float, float]] | None = None) -> dict[str, Any]:
    """Return a scene copy with a deterministic, topology-aware grid layout."""
    source = copy.deepcopy(source_json)
    nodes = [node for node in source.get("nodes") or [] if isinstance(node, dict) and node.get("id")]
    for node in nodes:
        semantic_type = str(node.get("semantic_type") or node.get("object_type") or "").lower()
        if "composition" not in node:
            composition = composition_for(semantic_type).to_dict()
            if composition["components"] or composition.get("storage"):
                node["composition"] = composition
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
        if layout.get("object_layout_strategy") != "semantic_v1":
            migrated_objects: dict[str, dict[str, Any]] = {}
            objects_by_room: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for node in nodes:
                if _is_placeable(node):
                    room_id = _room_ancestor(str(node["id"]), nodes_by_id)
                    if room_id in layout["rooms"]:
                        objects_by_room[room_id].append(node)
            for room_id, room_objects in objects_by_room.items():
                migrated_objects.update(_place_objects_in_room(
                    room_id, layout["rooms"][room_id], nodes_by_id[room_id], room_objects,
                ))
            layout["objects"] = migrated_objects
            layout["object_layout_strategy"] = "semantic_v1"
        _reposition_door_blockers(layout, nodes_by_id)
        source["layout"] = layout
        _add_physical_geometry(source, catalog_dimensions)
        _normalize_door_edges(source, layout["doors"])
        return source

    room_layouts = _place_rooms(rooms_nodes, pairs)
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
        room_node = nodes_by_id[room_id]
        object_layouts.update(_place_objects_in_room(room_id, room, room_node, room_objects))

    source["layout"] = {
        "units": "meter",
        "grid_size": GRID_SIZE_METERS,
        "object_layout_strategy": "semantic_v1",
        "rooms": room_layouts,
        "doors": door_layouts,
        "objects": object_layouts,
    }
    _reposition_door_blockers(source["layout"], nodes_by_id)
    _add_physical_geometry(source, catalog_dimensions)
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
    issues.extend(validate_composition_nodes(nodes))
    edges = source_json.get("edges") or []
    edge_issues = _validate_scene_graph_edges(nodes_by_id, edges)
    issues.extend(edge_issues)
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

    for room_id, room_sweeps in _door_sweeps(rooms, doors).items():
        for object_id, placement in objects.items():
            if str(placement.get("room_id") or "") != room_id or placement.get("placement_mode") == "wall_mounted":
                continue
            values = [_integer(placement.get(key)) for key in ("grid_x", "grid_y", "width_cells", "depth_cells")]
            if any(value is None for value in values):
                continue
            box = tuple(int(value) for value in values if value is not None)
            if any(_boxes_overlap(box, sweep) for sweep in room_sweeps):
                issues.append(f"Object {object_id} blocks a door opening sweep in room {room_id}.")

    for room_id in room_nodes:
        if room_id not in rooms:
            issues.append(f"Room {room_id} has no layout geometry.")
    return issues


def _validate_scene_graph_edges(nodes_by_id: dict[str, dict[str, Any]], edges: Any) -> list[str]:
    """Check structural/control edges before geometry validation.

    The runtime still accepts legacy edge aliases, but every referenced node
    must exist and containment must remain acyclic. This prevents a malformed
    component or room parent from later producing misleading layout errors.
    """
    issues: list[str] = []
    parent_edges: dict[str, str] = {}
    if not isinstance(edges, list):
        return ["Scene edges must be a list."]
    for edge in edges:
        if not isinstance(edge, dict):
            issues.append("Scene edge must be an object.")
            continue
        source = str(edge.get("source_id") or edge.get("source") or "")
        target = str(edge.get("target_id") or edge.get("target") or "")
        relation = str(edge.get("relation") or edge.get("edge_type") or "")
        if not source or source not in nodes_by_id:
            issues.append(f"Edge {relation or '<unknown>'} references missing source {source or '<empty>'}.")
        if not target or target not in nodes_by_id:
            issues.append(f"Edge {relation or '<unknown>'} references missing target {target or '<empty>'}.")
        if source not in nodes_by_id or target not in nodes_by_id:
            continue
        if relation == "component_of":
            previous = parent_edges.get(target)
            if previous and previous != source:
                issues.append(f"Component {target} has multiple component hosts: {previous}, {source}.")
            parent_edges[target] = source
        if relation == "controls":
            source_type = str(nodes_by_id[source].get("node_type") or "")
            if source_type not in {"control_object", "fixed_object", "movable_object"}:
                issues.append(f"Control source {source} has unsupported node type {source_type or '<empty>'}.")
        if relation in {"hinge_of", "slides_in"}:
            source_node = nodes_by_id[source]
            target_node = nodes_by_id[target]
            source_role = str(source_node.get("component_role") or "")
            target_role = str(target_node.get("component_role") or "")
            source_host = str(source_node.get("component_of") or "")
            target_host = str(target_node.get("component_of") or "")
            if relation == "hinge_of":
                if source_role != "hinge" or target_role != "door" or not source_host or source_host != target_host:
                    issues.append(f"Mechanical edge hinge_of must connect a hinge and door on the same host: {source} -> {target}.")
            elif source_role != "drawer" or source_host != target:
                issues.append(f"Mechanical edge slides_in must connect a drawer to its host: {source} -> {target}.")
    for child in parent_edges:
        seen: set[str] = set()
        current = child
        while current in parent_edges:
            if current in seen:
                issues.append(f"Component containment cycle detected at {current}.")
                break
            seen.add(current)
            current = parent_edges[current]
    return issues


__all__ = ["ensure_scene_layout", "validate_scene_layout"]
