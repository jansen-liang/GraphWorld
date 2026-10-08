from backend.runtime.elevator import advance_elevator, enqueue_request
from backend.runtime.action_engine import press_target


def _elevator():
    return {
        "id": "car",
        "node_type": "object",
        "semantic_type": "elevator",
        "capabilities": ["transport_device"],
        "floor_ids": ["f1", "f2", "f3", "f4"],
        "states": {"current_floor": "f1", "direction": "idle", "door_phase": "closed", "is_open": False},
    }


def test_elevator_orders_stops_in_current_direction_and_merges_requests():
    car = _elevator()
    enqueue_request(car, "f4", "cabin", step=1)
    enqueue_request(car, "f2", "hall_up", step=2)
    enqueue_request(car, "f2", "cabin", step=3)
    events = []
    # Continuous travel plus the configured two-tick dwell/close cycle takes
    # nine ticks to complete both requested stops.
    for _ in range(10):
        events.extend(advance_elevator(car, 1))
    arrivals = [event["floor_id"] for event in events if event["type"] == "elevator_arrived"]
    assert arrivals[:2] == ["f2", "f4"]
    assert car["request_queue"] == []


def test_elevator_dwell_reopens_on_same_floor_request_and_then_closes():
    car = _elevator()
    enqueue_request(car, "f1", "hall_up", step=1)
    events = advance_elevator(car, 1)
    assert events and car["states"]["door_phase"] == "opening"
    assert car["states"]["is_open"] is True
    advance_elevator(car, 1)
    assert car["states"]["door_phase"] == "dwelling"
    enqueue_request(car, "f1", "hall_down", step=2)
    advance_elevator(car, 1)
    assert car["states"]["door_phase"] == "dwelling"
    assert car["states"]["is_open"] is True


def test_elevator_stays_closed_on_arrival_tick_before_opening_next_tick():
    car = _elevator()
    car["states"].update({
        "current_floor": "f1",
        "current_height": 0.0,
        "door_phase": "closed",
        "is_open": False,
    })
    enqueue_request(car, "f2", "cabin", step=1)

    # Start travel, then reach the target. Reaching the target starts opening
    # immediately because the car is already stopped.
    advance_elevator(car, 1)
    assert car["states"]["motion_state"] == "moving"
    advance_elevator(car, 1)
    assert car["states"]["current_floor"] == "f2"
    assert car["states"]["motion_state"] == "stopped"
    assert car["states"]["door_phase"] == "opening"
    assert car["states"]["is_open"] is True


def test_elevator_projection_uses_boolean_joint_states_for_both_sliding_doors():
    state = {
        "nodes": {
            "car": {**_elevator(), "served_rooms": ["f1", "f2"]},
                "hall": {"id": "hall", "node_type": "object", "semantic_type": "door", "door_kind": "elevator_hall", "states": {"is_open": False}},
            "button": {"id": "button", "node_type": "object", "semantic_type": "button", "request_floor": "f1", "states": {"is_pressed": False, "is_on": False}},
        },
            "edges": [{"source_id": "hall", "target_id": "f1", "relation": "connects"}],
    }
    state["nodes"]["car"]["states"].update({"current_floor": "f1", "door_phase": "dwelling", "dwell_remaining": 2, "is_open": True})
    from backend.runtime.elevator import advance_elevators
    advance_elevators(state)
    assert state["nodes"]["hall"]["joint_states"] == {"hall": True, "hall.left": True, "hall.right": True}
    assert state["nodes"]["car"]["joint_states"]["car.car_door_left"] is True


def test_hall_door_projection_uses_explicit_floor_id():
    state = {
        "nodes": {
            "car": {**_elevator(), "served_rooms": ["f1", "f2"], "states": {"current_floor": "f2", "door_phase": "dwelling", "dwell_remaining": 2, "is_open": True}},
                "hall": {"id": "hall", "node_type": "object", "semantic_type": "door", "door_kind": "elevator_hall", "states": {"is_open": False}},
        },
            "edges": [{"source_id": "hall", "target_id": "f2", "relation": "connects"}],
    }
    from backend.runtime.elevator import advance_elevators
    advance_elevators(state)
    assert state["nodes"]["hall"]["states"]["is_open"] is True


def test_current_floor_hall_request_opens_without_extra_tick():
    from backend.runtime.action_engine import press_target

    state = {
        "nodes": {
            "car": {**_elevator(), "served_rooms": ["f1", "f2"], "states": {"current_floor": "f1", "door_phase": "closed", "motion_state": "idle", "is_open": False}},
            "button": {"id": "button", "semantic_type": "button", "request_floor": "f1", "request_kind": "hall_up", "states": {"is_on": False}},
        },
        "edges": [{"source_id": "button", "target_id": "car", "relation": "controls"}],
        "world_state": {"step": 0},
    }
    press_target(state, "button")
    assert state["nodes"]["car"]["states"]["door_phase"] == "opening"
    assert state["nodes"]["car"]["states"]["is_open"] is True
    assert state["nodes"]["car"]["states"]["dwell_remaining"] == 2


def test_move_agent_selects_upper_floor_when_2d_rooms_overlap():
    from backend.runtime.world.graph import World

    scene = {
        "scene_name": "test", "schema_version": 2, "id_namespace": "editor",
        "nodes": [
            {"id": "agent", "node_type": "agent"},
            {"id": "f1", "node_type": "room"},
            {"id": "f3", "node_type": "room"},
        ],
        "edges": [{"source_id": "f1", "target_id": "agent", "relation": "at"}],
        "layout": {"grid_size": 1.0, "rooms": {
            "f1": {"grid_x": 0, "grid_y": 0, "width_cells": 4, "depth_cells": 4, "floor_number": 1},
            "f3": {"grid_x": 0, "grid_y": 0, "width_cells": 4, "depth_cells": 4, "floor_number": 3},
        }, "objects": {}},
    }
    world = World(scene)
    state = world.ensure_agent_state("agent")
    state["position"] = {"x": 2.0, "y": 6.4 + 1.6, "z": 2.0}
    world.move_agent("agent", 0.0, 0.0, 0.0)
    assert world.room_of["agent"] == "f3"


def test_exiting_car_reanchors_height_before_room_update():
    from backend.runtime.world.graph import World

    scene = {
        "scene_name": "test", "schema_version": 2, "id_namespace": "editor",
        "nodes": [
            {"id": "agent", "node_type": "agent"},
            {"id": "car", "node_type": "object", "capabilities": ["transport_device"], "states": {"current_floor": "f3", "current_height": 6.4}},
            {"id": "shaft", "node_type": "room"},
            {"id": "f3", "node_type": "room"},
        ],
        "edges": [
            {"source_id": "car", "target_id": "agent", "relation": "in"},
            {"source_id": "shaft", "target_id": "car", "relation": "in"},
        ],
        "layout": {"grid_size": 1.0, "rooms": {
            "shaft": {"grid_x": 0, "grid_y": 0, "width_cells": 4, "depth_cells": 4, "floor_number": 1},
            "f3": {"grid_x": 0, "grid_y": 0, "width_cells": 4, "depth_cells": 4, "floor_number": 3},
        }, "objects": {"car": {"room_id": "shaft", "width_cm": 300, "depth_cm": 300, "height_cm": 240}}},
    }
    world = World(scene)
    state = world.ensure_agent_state("agent")
    state["position"] = {"x": 1.0, "y": 1.6, "z": 1.0}
    world.move_agent("agent", 2.0, 0.0, 0.1)
    assert state["room_id"] == "f3"
    assert state["position"]["y"] == 8.0


def test_all_floor_enter_exit_transitions_keep_authoritative_room():
    from backend.runtime.scene_preparation import ensure_demo_elevator
    from backend.app.runtime.scene_layout import ensure_scene_layout
    from backend.runtime.world.graph import World
    import json

    scene = json.load(open("backend/data/scene_versions/simple_home_1f__v9.json"))
    ensure_demo_elevator(scene)
    scene = ensure_scene_layout(scene)
    scene["nodes"].append({"id": "__simulation_player__", "node_type": "agent", "semantic_type": "agent"})
    scene["edges"].append({"source_id": "outside_home", "target_id": "__simulation_player__", "relation": "at"})
    world = World(scene)
    agent_id = "__simulation_player__"
    car_id = "elevator_car_outside_home"
    shaft = world.metadata["layout"]["rooms"]["elevator_shaft_outside_home"]
    grid = world.metadata["layout"]["grid_size"]
    center = ((shaft["grid_x"] + shaft["width_cells"] / 2) * grid,
              (shaft["grid_y"] + shaft["depth_cells"] / 2) * grid)
    car = world.node(car_id)
    for floor_id, height in (("outside_home", 0.0), ("outside_home_f2", 3.2), ("outside_home_f3", 6.4)):
        car["states"].update({"current_floor": floor_id, "current_height": height, "is_open": True, "door_phase": "dwelling"})
        state = world.ensure_agent_state(agent_id)
        state["position"] = {"x": center[0], "y": height + 1.6, "z": center[1]}
        state["room_id"] = floor_id
        world.move_node(agent_id, floor_id, "at")
        entered = world.move_agent(agent_id, 0.0, 0.0, 0.0)
        assert world.parent_of.get(agent_id) == car_id, (floor_id, entered, world.parent_of.get(agent_id))
        assert entered["room_id"] == floor_id
        state["position"]["z"] = center[1] + 1.2
        exited = world.move_agent(agent_id, 0.0, 0.0, 0.0)
        assert world.parent_of.get(agent_id) != car_id, (floor_id, exited, world.parent_of.get(agent_id))
        assert exited["room_id"] == floor_id


def test_floor_button_press_latches_until_served():
    state = {
        "nodes": {
            "car": {**_elevator(), "served_rooms": ["f1", "f2"], "transport_rooms": ["f1", "f2"]},
            "button": {"id": "button", "node_type": "object", "semantic_type": "button", "capabilities": ["switchable"], "request_floor": "f2", "states": {}},
        },
        "edges": [{"source_id": "button", "target_id": "car", "relation": "controls"}],
        "control_edges": [{"source_id": "button", "target_id": "car", "relation": "controls"}],
        "world_state": {"step": 0},
    }
    press_target(state, "button")
    assert state["nodes"]["button"]["states"]["is_on"] is True
    assert state["nodes"]["car"].get("request_queue") == [{"floor_id": "f2", "kinds": ["hall_up"], "created_at": 0}]


def test_cabin_open_button_runs_opening_then_full_dwell_cycle():
    car = _elevator()
    button = {
        "id": "open",
        "semantic_type": "button",
        "component_role": "open_button",
        "owner_id": "car",
        "states": {},
    }
    state = {"nodes": {"car": car, "open": button}, "world_state": {"step": 0}}

    press_target(state, "open")
    assert car["states"] == {
        "current_floor": "f1",
        "direction": "idle",
        "door_phase": "opening",
        "is_open": True,
        "motion_state": "stopped",
        "dwell_remaining": 2,
    }

    advance_elevator(car, 1)
    assert car["states"]["door_phase"] == "dwelling"
    assert car["states"]["dwell_remaining"] == 2
    advance_elevator(car, 1)
    assert car["states"]["door_phase"] == "dwelling"
    assert car["states"]["dwell_remaining"] == 1
    advance_elevator(car, 1)
    assert car["states"]["door_phase"] == "closing"
    assert car["states"]["is_open"] is False


def test_cabin_open_button_is_ignored_while_car_is_moving():
    car = _elevator()
    car["states"].update({
        "motion_state": "moving",
        "direction": "up",
        "target_floor": "f3",
        "target_height": 6.4,
        "current_height": 3.2,
        "door_phase": "closed",
        "is_open": False,
    })
    button = {
        "id": "open",
        "semantic_type": "button",
        "component_role": "open_button",
        "owner_id": "car",
        "states": {},
    }
    state = {"nodes": {"car": car, "open": button}, "world_state": {"step": 0}}

    press_target(state, "open")

    assert car["states"]["motion_state"] == "moving"
    assert car["states"]["door_phase"] == "closed"
    assert car["states"]["is_open"] is False


def test_elevator_descends_to_ground_floor_zero_height():
    car = _elevator()
    car["states"].update({
        "current_floor": "f3",
        "current_height": 6.4,
        "door_phase": "closed",
        "is_open": False,
    })
    enqueue_request(car, "f1", "cabin", step=1)

    advance_elevator(car, 1)
    assert car["states"]["motion_state"] == "moving"
    advance_elevator(car, 1)

    assert car["states"]["current_floor"] == "f1"
    assert car["states"]["current_height"] == 0.0
    assert car["states"]["target_height"] == 0.0
