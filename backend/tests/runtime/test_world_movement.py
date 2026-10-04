from backend.runtime.world import World


def _world(is_open: bool) -> World:
    return World({
        "schema_version": 2,
        "id_namespace": "editor",
        "nodes": [
            {"id": "room_a", "node_type": "room", "states": {}},
            {"id": "room_b", "node_type": "room", "states": {}},
            {"id": "agent", "node_type": "agent", "states": {}},
            {
                "id": "door",
                "node_type": "object",
                "semantic_type": "door",
                "connected_rooms": ["room_a", "room_b"],
                "states": {"is_open": is_open},
            },
        ],
        "edges": [
            {"source_id": "room_a", "target_id": "room_b", "relation": "connected"},
            {"source_id": "room_a", "target_id": "agent", "relation": "at"},
            {"source_id": "room_a", "target_id": "door", "relation": "in"},
        ],
        "layout": {
            "grid_size": 1.0,
            "rooms": {
                "room_a": {"grid_x": 0, "grid_y": 0, "width_cells": 2, "depth_cells": 2},
                "room_b": {"grid_x": 2, "grid_y": 0, "width_cells": 2, "depth_cells": 2},
            },
            "objects": {},
        },
    })


def test_move_step_reports_room_by_position_without_reimplementing_door_collision():
    world = _world(False)
    state = world.ensure_agent_state("agent")
    state["position"] = {"x": 1.8, "y": 1.6, "z": 1.0}
    state["room_id"] = "room_a"

    moved = world.move_agent("agent", 1.0, 0.0, 0.5)

    assert moved["room_id"] == "room_b"
    assert moved["position"]["x"] > 1.8


def test_move_step_updates_room_after_door_opens():
    world = _world(True)
    state = world.ensure_agent_state("agent")
    state["position"] = {"x": 1.8, "y": 1.6, "z": 1.0}
    state["room_id"] = "room_a"

    moved = world.move_agent("agent", 1.0, 0.0, 0.5)

    assert moved["room_id"] == "room_b"
    assert world.room_for("agent") == "room_b"
