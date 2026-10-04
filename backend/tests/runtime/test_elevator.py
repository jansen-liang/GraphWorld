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
    advance_elevator(car, 1)
    assert car["states"]["door_phase"] == "dwelling"
    enqueue_request(car, "f1", "hall_down", step=2)
    advance_elevator(car, 1)
    assert car["states"]["door_phase"] == "dwelling"
    assert car["states"]["is_open"] is True


def test_elevator_projection_uses_boolean_joint_states_for_both_sliding_doors():
    state = {
        "nodes": {
            "car": {**_elevator(), "served_rooms": ["f1", "f2"]},
            "hall": {"id": "hall", "node_type": "object", "semantic_type": "door", "door_kind": "elevator_hall", "floor_id": "f1", "states": {"is_open": False}},
            "button": {"id": "button", "node_type": "object", "semantic_type": "button", "request_floor": "f1", "states": {"is_pressed": False, "is_on": False}},
        },
        "edges": [],
    }
    state["nodes"]["car"]["states"].update({"current_floor": "f1", "door_phase": "dwelling", "dwell_remaining": 2, "is_open": True})
    from backend.runtime.elevator import advance_elevators
    advance_elevators(state)
    assert state["nodes"]["hall"]["joint_states"] == {"hall": True, "hall.left": True, "hall.right": True}
    assert state["nodes"]["car"]["joint_states"]["car.car_door_left"] is True


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
