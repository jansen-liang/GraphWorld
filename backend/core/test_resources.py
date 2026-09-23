from backend.core.action_schemas import apply_action_schema, validate_action_schema
from backend.core.resources import available_count
from backend.core.timed_transitions import apply_timed_transitions


def _state():
    source = {
        "id": "fridge_milk_pool",
        "semantic_type": "milk",
        "node_type": "fixed_object",
        "interactive_actions": ["dispense"],
        "parent": "kitchen",
        "resource_pool": {
            "available_count": 2,
            "instance_prefix": "milk",
            "instance": {"semantic_type": "milk", "states": {"temperature": "cold"}},
        },
        "states": {},
    }
    return {
        "nodes": {
            "robot_01": {"id": "robot_01", "node_type": "robot", "parent": "kitchen", "states": {}},
            "kitchen": {"id": "kitchen", "node_type": "room", "states": {}},
            source["id"]: source,
        },
        "parent_of": {"robot_01": "kitchen", source["id"]: "kitchen"},
        "relation_of": {"robot_01": "at", source["id"]: "in"},
        "room_of": {"robot_01": "kitchen", source["id"]: "kitchen"},
        "control_edges": [],
        "room_edges": [],
    }


def test_dispense_creates_independent_held_instances_and_decrements_pool():
    state = _state()
    action = {"agent": "robot_01", "action": "dispense", "target": "fridge_milk_pool"}
    assert validate_action_schema(state, action) == ()
    assert apply_action_schema(state, action) == ()
    first = state["nodes"]["fridge_milk_pool"]["resource_pool"]
    assert available_count(state["nodes"]["fridge_milk_pool"]) == 1
    instance = state["nodes"]["fridge_milk_pool_milk_1"]
    assert instance["parent"] == "robot_01"
    assert instance["runtime_relation"] == "held_by"
    assert state["world_state"]["event_log"][0] == {
        "type": "resource_dispensed",
        "source_id": "fridge_milk_pool",
        "instance_id": "fridge_milk_pool_milk_1",
        "actor_id": "robot_01",
        "remaining": 1,
    }
    state["parent_of"].pop("fridge_milk_pool_milk_1")
    state["relation_of"].pop("fridge_milk_pool_milk_1")
    assert apply_action_schema(state, action) == ()
    assert available_count(state["nodes"]["fridge_milk_pool"]) == 0
    assert "fridge_milk_pool_milk_2" in state["nodes"]
    assert first["dispensed_count"] == 2
    assert state["world_state"]["event_log"][-1] == {
        "type": "resource_depleted",
        "source_id": "fridge_milk_pool",
        "resource_semantic_type": "milk",
    }
    failures = validate_action_schema(state, action)
    assert "resource exhausted or pool missing: fridge_milk_pool" in failures


def test_consume_removes_held_resource_instance_and_records_source():
    state = _state()
    assert apply_action_schema(state, {"agent": "robot_01", "action": "dispense", "target": "fridge_milk_pool"}) == ()
    assert apply_action_schema(state, {"agent": "robot_01", "action": "consume"}) == ()
    assert "fridge_milk_pool_milk_1" not in state["nodes"]
    assert state["nodes"]["fridge_milk_pool"]["resource_pool"]["consumed_count"] == 1
    assert state["world_state"]["event_log"][-1] == {
        "type": "resource_consumed",
        "source_id": "fridge_milk_pool",
        "instance_id": "fridge_milk_pool_milk_1",
        "actor_id": "robot_01",
        "resource_semantic_type": "milk",
    }
    assert state["world_state"]["event_log"][-2] == {
        "type": "object_consumed",
        "object_id": "fridge_milk_pool_milk_1",
        "actor_id": "robot_01",
        "semantic_type": "milk",
        "source_id": "fridge_milk_pool",
    }


def test_consume_rejects_rotten_or_non_consumable_held_objects():
    state = _state()
    state["nodes"]["rotten"] = {"id": "rotten", "node_type": "movable_object", "semantic_type": "food", "parent": "robot_01", "states": {"is_rotten": True}}
    state["parent_of"]["rotten"] = "robot_01"
    state["relation_of"]["rotten"] = "held_by"
    assert "rotten or burnt food cannot be consumed" in validate_action_schema(state, {"agent": "robot_01", "action": "consume", "object": "rotten"})
    state["nodes"].pop("rotten")
    state["nodes"]["box"] = {"id": "box", "node_type": "movable_object", "semantic_type": "box", "parent": "robot_01", "states": {}}
    state["parent_of"]["box"] = "robot_01"
    state["relation_of"]["box"] = "held_by"
    assert "object is not consumable: box" in validate_action_schema(state, {"agent": "robot_01", "action": "consume", "object": "box"})


def test_release_drops_held_object_and_breaks_fragile_material_when_dropped():
    state = _state()
    state["nodes"]["glass"] = {
        "id": "glass",
        "node_type": "movable_object",
        "semantic_type": "glass",
        "parent": "robot_01",
        "material": "glass",
        "drop_height_cm": 50,
        "states": {},
    }
    state["parent_of"]["glass"] = "robot_01"
    state["relation_of"]["glass"] = "held_by"
    action = {"agent": "robot_01", "action": "release", "object": "glass"}
    assert validate_action_schema(state, action) == ()
    assert apply_action_schema(state, action) == ()
    assert state["parent_of"]["glass"] == "kitchen"
    assert state["relation_of"]["glass"] == "in"
    assert state["nodes"]["glass"]["states"]["is_broken"] is True
    assert state["nodes"]["glass"]["release_mode"] == "release"
    assert state["nodes"]["glass"]["release_room"] == "kitchen"
    assert state["world_state"]["event_log"][-1]["type"] == "object_released"
    broken = next(event for event in state["world_state"]["event_log"] if event["type"] == "object_broken")
    assert broken["object_id"] == "glass" and broken["cause"] == "high_release"


def test_release_advances_through_falling_to_settled_contact():
    state = _state()
    state["nodes"]["box"] = {
        "id": "box", "node_type": "movable_object", "semantic_type": "box",
        "parent": "robot_01", "drop_height_cm": 120, "states": {},
    }
    state["parent_of"]["box"] = "robot_01"
    state["relation_of"]["box"] = "held_by"
    assert apply_action_schema(state, {"agent": "robot_01", "action": "release", "object": "box"}) == ()
    assert state["nodes"]["box"]["physics_state"] == "falling"
    apply_timed_transitions(state, 1)
    assert state["nodes"]["box"]["drop_height_cm"] == 70
    apply_timed_transitions(state, 2)
    assert state["nodes"]["box"]["physics_state"] == "falling"
    apply_timed_transitions(state, 3)
    assert state["nodes"]["box"]["physics_state"] == "settled"
    settled = next(event for event in state["world_state"]["event_log"] if event["type"] == "object_settled")
    assert settled["object_id"] == settled["item_id"] == "box"


def test_release_anchor_is_clamped_to_room_floor():
    state = _state()
    state["nodes"]["box"] = {
        "id": "box", "node_type": "movable_object", "semantic_type": "box",
        "parent": "robot_01", "drop_height_cm": 0, "states": {},
    }
    state["parent_of"]["box"] = "robot_01"
    state["relation_of"]["box"] = "held_by"
    assert apply_action_schema(state, {
        "agent": "robot_01", "action": "release", "object": "box",
        "release_anchor": [-2, 4, 3],
    }) == ()
    assert state["nodes"]["box"]["release_anchor"] == [0.0, 0.0, 1.0]
    assert state["nodes"]["box"]["floor_contact"] == {"room_id": "kitchen", "anchor": [0.0, 0.0, 1.0]}


def test_release_rejects_floor_overlap_at_same_anchor():
    state = _state()
    state["nodes"]["box"] = {
        "id": "box", "node_type": "movable_object", "semantic_type": "box",
        "parent": "robot_01", "footprint_cm": [20, 20], "states": {},
    }
    state["nodes"]["cup_on_floor"] = {
        "id": "cup_on_floor", "node_type": "movable_object", "semantic_type": "cup",
        "parent": "kitchen", "release_room": "kitchen", "release_anchor": [0.5, 0.0, 0.5],
        "footprint_cm": [10, 10], "physics_state": "settled", "states": {},
    }
    state["parent_of"]["box"] = "robot_01"
    state["relation_of"]["box"] = "held_by"
    failures = validate_action_schema(state, {
        "agent": "robot_01", "action": "release", "object": "box",
        "release_anchor": [0.5, 0.0, 0.5],
    })
    assert any("floor footprint overlaps cup_on_floor" in failure for failure in failures)
