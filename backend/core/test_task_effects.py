from backend.core.action_schemas import apply_action_schema
from backend.core.timed_transitions import apply_timed_transitions
from backend.core.assets.object_library import OBJECT_LIBRARY
from backend.core.assets.task_library import relevant_skills_for_nodes


def test_fan_toggle_updates_airflow_and_can_be_turned_off():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "room", "states": {}},
            "room": {"id": "room", "node_type": "room", "states": {}},
            "fan": {"id": "fan", "node_type": "fixed_object", "semantic_type": "fan", "parent": "room", "interactive_actions": ["press"], "states": {"is_on": False}},
        },
        "parent_of": {"robot": "room", "fan": "room"},
        "relation_of": {"robot": "at", "fan": "in"},
        "room_of": {"robot": "room", "fan": "room"},
        "control_edges": [], "room_edges": [], "world_state": {},
    }
    assert apply_action_schema(state, {"agent": "robot", "action": "press", "target": "fan"}) == ()
    assert state["nodes"]["fan"]["states"]["is_on"] is True
    assert state["world_state"]["room_ventilation"]["room"] == "active"
    assert apply_action_schema(state, {"agent": "robot", "action": "press", "target": "fan"}) == ()
    assert state["nodes"]["fan"]["states"]["is_on"] is False
    assert state["world_state"]["room_ventilation"]["room"] == "idle"


def test_flush_button_cleans_controlled_toilet():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "bathroom", "states": {}},
            "bathroom": {"id": "bathroom", "node_type": "room", "states": {}},
            "toilet": {"id": "toilet", "node_type": "fixed_object", "semantic_type": "toilet", "parent": "bathroom", "states": {"is_dirty": True}},
            "flush": {"id": "flush", "node_type": "control_object", "semantic_type": "button", "parent": "toilet", "interactive_actions": ["press"], "states": {"is_pressed": False}},
        },
        "parent_of": {"robot": "bathroom", "toilet": "bathroom", "flush": "toilet"},
        "relation_of": {"robot": "at", "toilet": "in", "flush": "in"},
        "room_of": {"robot": "bathroom", "toilet": "bathroom", "flush": "bathroom"},
        "control_edges": [{"source_id": "flush", "target_id": "toilet", "relation": "controls"}],
        "room_edges": [],
    }
    assert apply_action_schema(state, {"agent": "robot", "action": "press", "target": "flush"}) == ()
    assert state["nodes"]["toilet"]["states"]["is_dirty"] is False


def test_washer_consumes_loaded_detergent_instance_when_started():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "bathroom", "states": {}},
            "bathroom": {"id": "bathroom", "node_type": "room", "states": {}},
            "washer": {"id": "washer", "node_type": "fixed_object", "semantic_type": "washer", "parent": "bathroom", "interactive_actions": ["press"], "states": {"is_open": False}},
            "detergent": {"id": "detergent", "node_type": "movable_object", "semantic_type": "detergent", "resource_instance_of": "detergent_pool", "parent": "washer", "states": {}},
        },
        "parent_of": {"robot": "bathroom", "washer": "bathroom", "detergent": "washer"},
        "relation_of": {"robot": "at", "washer": "in", "detergent": "in"},
        "room_of": {"robot": "bathroom", "washer": "bathroom", "detergent": "bathroom"},
        "control_edges": [], "room_edges": [], "world_state": {},
    }
    assert apply_action_schema(state, {"agent": "robot", "action": "press", "target": "washer"}) == ()
    assert "detergent" not in state["nodes"]
    assert state["world_state"]["event_log"][-1] == {
        "type": "resource_consumed", "source_id": "detergent_pool", "instance_id": "detergent",
        "device_id": "washer", "resource_semantic_type": "detergent",
    }


def test_device_resource_loading_is_generic_and_rejects_duplicate_detergent():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "bathroom", "states": {}},
            "bathroom": {"id": "bathroom", "node_type": "room", "states": {}},
            "washer": {"id": "washer", "node_type": "fixed_object", "semantic_type": "washer", "parent": "bathroom", "interactive_actions": ["place", "press"], "states": {"is_open": False}},
            "detergent": {"id": "detergent", "node_type": "movable_object", "semantic_type": "detergent", "parent": "robot", "states": {}},
            "second": {"id": "second", "node_type": "movable_object", "semantic_type": "detergent", "parent": "robot", "states": {}},
        },
        "parent_of": {"robot": "bathroom", "washer": "bathroom", "detergent": "robot", "second": "robot"},
        "relation_of": {"robot": "at", "washer": "in", "detergent": "held_by", "second": "held_by"},
        "room_of": {"robot": "bathroom", "washer": "bathroom", "detergent": "bathroom", "second": "bathroom"},
        "control_edges": [], "room_edges": [], "world_state": {},
    }
    assert apply_action_schema(state, {"agent": "robot", "action": "place", "object": "detergent", "target": "washer"}) == ()
    assert state["parent_of"]["detergent"] == "washer"
    assert state["world_state"]["event_log"][-1]["type"] == "resource_loaded"
    failures = apply_action_schema(state, {"agent": "robot", "action": "place", "object": "second", "target": "washer"})
    assert any("device resource slot already occupied" in failure for failure in failures)
    assert state["parent_of"]["second"] == "robot"
    assert sum(event["type"] == "resource_loaded" for event in state["world_state"]["event_log"]) == 1


def test_dishwasher_consumes_loaded_detergent_instance_when_started():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "kitchen", "states": {}},
            "kitchen": {"id": "kitchen", "node_type": "room", "states": {}},
            "dishwasher": {"id": "dishwasher", "node_type": "fixed_object", "semantic_type": "dishwasher", "parent": "kitchen", "interactive_actions": ["press"], "states": {"is_open": False}},
            "detergent": {"id": "detergent", "node_type": "movable_object", "semantic_type": "dishwasher_detergent", "parent": "dishwasher", "resource_instance_of": "dishwasher_pool", "states": {}},
        },
        "parent_of": {"robot": "kitchen", "dishwasher": "kitchen", "detergent": "dishwasher"},
        "relation_of": {"robot": "at", "dishwasher": "in", "detergent": "in"},
        "room_of": {"robot": "kitchen", "dishwasher": "kitchen", "detergent": "kitchen"},
        "control_edges": [], "room_edges": [], "world_state": {},
    }
    assert apply_action_schema(state, {"agent": "robot", "action": "press", "target": "dishwasher"}) == ()
    assert "detergent" not in state["nodes"]
    assert state["world_state"]["event_log"][-1]["type"] == "resource_consumed"
    assert state["world_state"]["event_log"][-1]["device_id"] == "dishwasher"


def test_watering_can_restores_wilted_plant():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "room", "states": {}},
            "room": {"id": "room", "node_type": "room", "states": {}},
            "can": {"id": "can", "node_type": "movable_object", "semantic_type": "wateringcan", "parent": "robot", "states": {"has_water": True}},
            "plant": {"id": "plant", "node_type": "movable_object", "semantic_type": "plant", "parent": "room", "interactive_actions": ["dump"], "states": {"vitality": 0.1, "is_wilted": True}},
        },
        "parent_of": {"robot": "room", "can": "robot", "plant": "room"},
        "relation_of": {"robot": "at", "can": "held_by", "plant": "in"},
        "room_of": {"robot": "room", "can": "room", "plant": "room"},
        "control_edges": [], "room_edges": [],
    }
    assert apply_action_schema(state, {"agent": "robot", "action": "dump", "target": "plant"}) == ()
    assert state["nodes"]["can"]["states"]["has_water"] is True
    assert state["nodes"]["can"]["states"]["water_level"] == 65.0
    assert state["nodes"]["plant"]["states"]["vitality"] == 0.45
    assert state["nodes"]["plant"]["states"]["is_wilted"] is False


def test_numeric_water_level_is_consumed_while_legacy_has_water_stays_compatible():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "room", "states": {}},
            "room": {"id": "room", "node_type": "room", "states": {}},
            "can": {"id": "can", "node_type": "movable_object", "semantic_type": "wateringcan", "parent": "robot", "interactive_actions": ["dump"], "states": {"has_water": True, "water_level": 50}},
            "plant": {"id": "plant", "node_type": "movable_object", "semantic_type": "plant", "parent": "room", "interactive_actions": ["dump"], "states": {"vitality": 0.1, "is_wilted": True}},
        },
        "parent_of": {"robot": "room", "can": "robot", "plant": "room"},
        "relation_of": {"robot": "at", "can": "held_by", "plant": "in"},
        "room_of": {"robot": "room", "can": "room", "plant": "room"},
        "control_edges": [], "room_edges": [],
    }
    assert apply_action_schema(state, {"agent": "robot", "action": "dump", "target": "plant"}) == ()
    assert state["nodes"]["can"]["states"]["water_level"] == 15.0
    assert state["nodes"]["can"]["states"]["has_water"] is True


def test_running_sink_fills_empty_watering_can_when_placed_inside():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "room", "states": {}},
            "room": {"id": "room", "node_type": "room", "states": {}},
            "sink": {"id": "sink", "node_type": "fixed_object", "semantic_type": "sink", "parent": "room", "interactive_actions": ["place"], "states": {"has_water": True, "water_level": 100}},
            "can": {"id": "can", "node_type": "movable_object", "semantic_type": "wateringcan", "parent": "robot", "states": {"has_water": False, "water_level": 0}},
        },
        "parent_of": {"robot": "room", "sink": "room", "can": "robot"},
        "relation_of": {"robot": "at", "sink": "in", "can": "held_by"},
        "room_of": {"robot": "room", "sink": "room", "can": "room"},
        "control_edges": [], "room_edges": [],
    }
    assert apply_action_schema(state, {"agent": "robot", "action": "place", "object": "can", "target": "sink"}) == ()
    assert state["nodes"]["can"]["states"]["water_level"] == 100.0
    assert state["nodes"]["can"]["states"]["has_water"] is True
    assert state["nodes"]["sink"]["states"]["water_level"] == 0.0
    assert state["nodes"]["sink"]["states"]["has_water"] is False
    assert any(event["type"] == "water_transferred" for event in state["world_state"]["event_log"])


def test_wettable_tool_consumes_reservoir_water_before_it_can_clean():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "room", "states": {}},
            "room": {"id": "room", "node_type": "room", "states": {}},
            "sink": {"id": "sink", "node_type": "fixed_object", "parent": "room", "capabilities": ["water_reservoir", "place_target"], "states": {"has_water": True, "water_level": 25}},
            "towel": {"id": "towel", "node_type": "movable_object", "parent": "robot", "capabilities": ["pickable", "wettable", "cleaning_tool"], "water_absorption": 10, "states": {"is_wet": False}},
        },
        "parent_of": {"robot": "room", "sink": "room", "towel": "robot"},
        "relation_of": {"robot": "at", "sink": "in", "towel": "held_by"},
        "room_of": {"robot": "room", "sink": "room", "towel": "room"},
        "control_edges": [], "room_edges": [], "world_state": {},
    }
    assert apply_action_schema(state, {"agent": "robot", "action": "place", "object": "towel", "target": "sink"}) == ()
    assert state["nodes"]["towel"]["states"]["is_wet"] is True
    assert state["nodes"]["sink"]["states"]["water_level"] == 15.0


def test_cleaning_cloth_template_declares_water_interaction_capability():
    cloth = OBJECT_LIBRARY["cleaningcloth"].instantiate("cloth", parent="room")
    assert "cleaning_tool" in cloth["capabilities"]
    assert "wettable" in cloth["capabilities"]


def test_washing_rule_uses_capability_instead_of_semantic_name():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "states": {}},
            "uniform": {
                "id": "uniform", "semantic_type": "custom_uniform", "node_type": "movable_object",
                "capabilities": ["washable", "cleanable"], "states": {"is_dirty": True},
            },
        },
        "parent_of": {}, "relation_of": {}, "room_of": {}, "control_edges": [], "world_state": {},
    }
    failures = apply_action_schema(state, {"agent": "robot", "action": "brush", "target": "uniform"})
    assert "washable objects must use a compatible washing process" in failures
    assert state["nodes"]["uniform"]["states"]["is_dirty"] is True


def test_water_plant_skill_is_triggered_by_decay():
    nodes = {
        "plant": {"id": "plant", "semantic_type": "plant", "states": {"vitality": 0.4, "is_wilted": False}},
    }
    assert [skill["name"] for skill in relevant_skills_for_nodes(nodes)] == ["water_plant"]


def test_refill_vase_skill_is_triggered_when_flower_vase_is_empty():
    nodes = {
        "vase": {"id": "vase", "semantic_type": "vase", "states": {"has_water": False}},
        "flower": {"id": "flower", "semantic_type": "flower", "parent": "vase", "states": {"vitality": 1.0}},
    }
    assert [skill["name"] for skill in relevant_skills_for_nodes(nodes)] == ["refill_vase"]


def test_brush_requires_declared_tool_and_consumes_tool_uses():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "room", "states": {}},
            "room": {"id": "room", "node_type": "room", "states": {}},
            "scrub": {"id": "scrub", "node_type": "movable_object", "semantic_type": "scrubbrush", "parent": "robot", "states": {"uses_left": 2}},
            "counter": {"id": "counter", "node_type": "fixed_object", "semantic_type": "counter", "parent": "room", "interactive_actions": ["brush"], "required_tool": "scrubbrush", "states": {"is_dirty": True}},
        },
        "parent_of": {"robot": "room", "scrub": "robot", "counter": "room"},
        "relation_of": {"robot": "at", "scrub": "held_by", "counter": "in"},
        "room_of": {"robot": "room", "scrub": "room", "counter": "room"},
        "control_edges": [], "room_edges": [], "world_state": {},
    }
    assert apply_action_schema(state, {"agent": "robot", "action": "brush", "target": "counter"}) == ()
    assert state["nodes"]["counter"]["states"]["is_dirty"] is False
    assert state["nodes"]["scrub"]["states"]["uses_left"] == 1
    assert state["world_state"]["event_log"][-1]["type"] == "tool_used"


def test_microwave_cycle_heats_child_milk():
    state = {
        "nodes": {
            "microwave": {"id": "microwave", "node_type": "fixed_object", "semantic_type": "microwave", "parent": "kitchen", "interactive_actions": ["press"], "states": {"is_on": False, "is_running": False, "cycle_remaining": 0}},
            "milk": {"id": "milk", "node_type": "movable_object", "semantic_type": "milk", "parent": "microwave", "states": {"temperature": "cold"}},
        },
        "parent_of": {"microwave": "kitchen", "milk": "microwave"},
        "relation_of": {"microwave": "in", "milk": "in"},
        "room_of": {"microwave": "kitchen", "milk": "kitchen"},
        "control_edges": [], "room_edges": [], "world_state": {},
    }
    state["nodes"]["kitchen"] = {"id": "kitchen", "node_type": "room", "states": {}}
    assert apply_action_schema(state, {"agent": "robot", "action": "press", "target": "microwave"})[0].startswith("unknown agent")
    state["nodes"]["robot"] = {"id": "robot", "node_type": "robot", "parent": "kitchen", "states": {}}
    state["parent_of"]["robot"] = "kitchen"
    state["room_of"]["robot"] = "kitchen"
    assert apply_action_schema(state, {"agent": "robot", "action": "press", "target": "microwave"}) == ()
    apply_timed_transitions(state, 1)
    apply_timed_transitions(state, 2)
    assert state["nodes"]["milk"]["states"]["temperature"] == "hot"


def test_washer_requires_declared_laundry_detergent_input():
    state = {
        "nodes": {
            "room": {"id": "room", "node_type": "room", "states": {}},
            "robot": {"id": "robot", "node_type": "robot", "parent": "room", "states": {}},
            "washer": {"id": "washer", "node_type": "fixed_object", "semantic_type": "washer", "parent": "room", "capabilities": ["switchable", "timed_device", "openable", "start_requires_closed"], "required_process_capabilities": ["laundry_detergent"], "interactive_actions": ["press"], "states": {"is_open": False, "is_running": False}},
            "shirt": {"id": "shirt", "node_type": "movable_object", "semantic_type": "clothes", "parent": "washer", "capabilities": ["pickable", "washable"], "states": {"is_dirty": True}},
        },
        "parent_of": {"robot": "room", "washer": "room", "shirt": "washer"},
        "relation_of": {"shirt": "in"}, "room_of": {"robot": "room", "washer": "room", "shirt": "room"},
        "control_edges": [], "room_edges": [], "world_state": {},
    }
    failures = apply_action_schema(state, {"agent": "robot", "action": "press", "target": "washer"})
    assert failures == ("process input capability missing: laundry_detergent",)
    state["nodes"]["detergent"] = {"id": "detergent", "semantic_type": "laundry_detergent", "parent": "washer", "capabilities": ["laundry_detergent"], "states": {}}
    state["parent_of"]["detergent"] = "washer"
    assert apply_action_schema(state, {"agent": "robot", "action": "press", "target": "washer"}) == ()


def test_washing_process_applies_wetness_before_cleanliness_completion():
    state = {
        "nodes": {
            "room": {"id": "room", "node_type": "room", "states": {}},
            "robot": {"id": "robot", "node_type": "robot", "parent": "room", "states": {}},
            "washer": {"id": "washer", "node_type": "fixed_object", "semantic_type": "washer", "parent": "room", "composition": {"storage": {"accepted_capabilities": ["washable"]}}, "required_process_capabilities": ["laundry_detergent"], "interactive_actions": ["press"], "states": {"is_open": False, "is_running": False}},
            "shirt": {"id": "shirt", "node_type": "movable_object", "semantic_type": "clothes", "parent": "washer", "capabilities": ["washable"], "states": {"is_dirty": True, "is_wet": False}},
            "detergent": {"id": "detergent", "semantic_type": "laundry_detergent", "parent": "washer", "capabilities": ["laundry_detergent"], "states": {}},
        },
        "parent_of": {"robot": "room", "washer": "room", "shirt": "washer", "detergent": "washer"},
        "relation_of": {"shirt": "in", "detergent": "in"}, "room_of": {"robot": "room", "washer": "room", "shirt": "room", "detergent": "room"},
        "control_edges": [], "room_edges": [], "world_state": {},
    }
    assert apply_action_schema(state, {"agent": "robot", "action": "press", "target": "washer"}) == ()
    assert state["nodes"]["shirt"]["states"]["is_wet"] is True
    assert state["nodes"]["shirt"]["states"]["is_dirty"] is True


def test_temporal_profile_is_declarative_and_applies_independent_state_effects():
    from backend.core.temporal import apply_effects, temporal_effects

    item = {"states": {"is_dirty": True, "is_wet": False}, "temporal_profile": {
        "on_start": [{"capability": "washable", "state": "is_wet", "value": True}],
        "on_complete": [{"capability": "washable", "state": "is_dirty", "value": False}],
    }}
    apply_effects(item, {"washable"}, temporal_effects(item, "start"))
    assert item["states"] == {"is_dirty": True, "is_wet": True}
    apply_effects(item, {"washable"}, temporal_effects(item, "complete"))
    assert item["states"]["is_dirty"] is False


def test_access_button_opens_controlled_structural_door():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "room", "states": {}},
            "room": {"id": "room", "node_type": "room", "states": {}},
            "door": {"id": "door", "node_type": "control_object", "semantic_type": "door", "door_kind": "structural", "parent": "room", "states": {"is_open": False}},
            "badge": {"id": "badge", "node_type": "control_object", "semantic_type": "button", "parent": "room", "interactive_actions": ["press"], "states": {"is_pressed": False}},
        },
        "parent_of": {"robot": "room", "door": "room", "badge": "room"},
        "relation_of": {"robot": "at", "door": "in", "badge": "in"},
        "room_of": {"robot": "room", "door": "room", "badge": "room"},
        "control_edges": [{"source_id": "badge", "target_id": "door", "relation": "controls"}],
        "room_edges": [],
    }
    assert apply_action_schema(state, {"agent": "robot", "action": "press", "target": "badge"}) == ()
    assert state["nodes"]["door"]["states"]["is_open"] is True


def test_protected_access_control_requires_matching_held_credential():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "room", "states": {}},
            "room": {"id": "room", "node_type": "room", "states": {}},
            "door": {
                "id": "door", "node_type": "control_object", "semantic_type": "door",
                "door_kind": "structural", "parent": "room", "required_credential": "staff_badge",
                "states": {"is_open": False},
            },
            "reader": {
                "id": "reader", "node_type": "control_object", "semantic_type": "button",
                "parent": "room", "interactive_actions": ["press"], "states": {"is_pressed": False},
            },
            "badge": {
                "id": "badge", "node_type": "movable_object", "semantic_type": "badge",
                "credential": "staff_badge", "parent": "room", "states": {},
            },
        },
        "parent_of": {"robot": "room", "door": "room", "reader": "room", "badge": "room"},
        "relation_of": {"robot": "at", "door": "in", "reader": "in", "badge": "in"},
        "room_of": {"robot": "room", "door": "room", "reader": "room", "badge": "room"},
        "control_edges": [{"source_id": "reader", "target_id": "door", "relation": "controls"}],
        "room_edges": [],
    }
    denied = apply_action_schema(state, {"agent": "robot", "action": "press", "target": "reader"})
    assert denied == ("missing credential for door: staff_badge",)
    state["parent_of"]["badge"] = "robot"
    state["relation_of"]["badge"] = "held_by"
    state["nodes"]["badge"]["parent"] = "robot"
    assert apply_action_schema(state, {"agent": "robot", "action": "press", "target": "reader"}) == ()
    assert state["nodes"]["door"]["states"]["is_open"] is True


def test_workbench_recipe_consumes_inputs_and_spawns_output():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "kitchen", "states": {}},
            "kitchen": {"id": "kitchen", "node_type": "room", "states": {}},
            "bench": {"id": "bench", "node_type": "fixed_object", "semantic_type": "workbench", "parent": "kitchen", "interactive_actions": ["press", "place"], "states": {"is_on": False, "is_running": False, "cycle_remaining": 0}},
            "bread": {"id": "bread", "node_type": "movable_object", "semantic_type": "bread", "parent": "bench", "states": {}},
            "tomato": {"id": "tomato", "node_type": "movable_object", "semantic_type": "tomato", "parent": "bench", "states": {}},
        },
        "parent_of": {"robot": "kitchen", "bench": "kitchen", "bread": "bench", "tomato": "bench"},
        "relation_of": {"robot": "at", "bench": "in", "bread": "in", "tomato": "in"},
        "room_of": {"robot": "kitchen", "bench": "kitchen", "bread": "kitchen", "tomato": "kitchen"},
        "control_edges": [], "room_edges": [], "world_state": {},
    }
    assert apply_action_schema(state, {"agent": "robot", "action": "press", "target": "bench"}) == ()
    assert state["nodes"]["bench"]["states"]["is_running"] is True
    for _ in range(3):
        apply_timed_transitions(state, 1)
    assert state["nodes"]["bench"]["states"]["is_running"] is False
    assert "bread" not in state["nodes"]
    assert "tomato" not in state["nodes"]
    outputs = [item for item in state["nodes"].values() if item.get("semantic_type") == "sandwich"]
    assert len(outputs) == 1
    assert outputs[0]["parent"] == "bench"
    event_types = [event["type"] for event in state["world_state"]["event_log"]]
    assert event_types == ["process_started", "process_consumed", "process_consumed", "process_completed"]
    assert state["world_state"]["event_log"][-1]["output_id"] == outputs[0]["id"]


def test_workbench_rejects_start_without_recipe_inputs():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "kitchen", "states": {}},
            "kitchen": {"id": "kitchen", "node_type": "room", "states": {}},
            "bench": {"id": "bench", "node_type": "fixed_object", "semantic_type": "workbench", "parent": "kitchen", "interactive_actions": ["press", "place"], "states": {"is_on": False, "is_running": False, "cycle_remaining": 0}},
        },
        "parent_of": {"robot": "kitchen", "bench": "kitchen"},
        "relation_of": {"robot": "at", "bench": "in"},
        "room_of": {"robot": "kitchen", "bench": "kitchen"},
        "control_edges": [], "room_edges": [], "world_state": {},
    }
    failures = apply_action_schema(state, {"agent": "robot", "action": "press", "target": "bench"})
    assert failures == ("process inputs unavailable: bench",)
    assert state["nodes"]["bench"]["states"]["is_running"] is False


def test_stove_cooks_egg_into_independent_output():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "kitchen", "states": {}},
            "kitchen": {"id": "kitchen", "node_type": "room", "states": {}},
            "stove": {"id": "stove", "node_type": "fixed_object", "semantic_type": "stove", "parent": "kitchen", "interactive_actions": ["press", "place"], "states": {"is_running": False}},
            "egg": {"id": "egg", "node_type": "movable_object", "semantic_type": "egg", "parent": "stove", "states": {"is_cooked": False}},
        },
        "parent_of": {"robot": "kitchen", "stove": "kitchen", "egg": "stove"},
        "relation_of": {"robot": "at", "stove": "in", "egg": "in"},
        "room_of": {"robot": "kitchen", "stove": "kitchen", "egg": "kitchen"},
        "control_edges": [], "room_edges": [], "world_state": {},
    }
    assert apply_action_schema(state, {"agent": "robot", "action": "press", "target": "stove"}) == ()
    for _ in range(3):
        apply_timed_transitions(state, 1)
    assert "egg" not in state["nodes"]
    outputs = [item for item in state["nodes"].values() if item.get("semantic_type") == "cooked_egg"]
    assert len(outputs) == 1 and outputs[0]["parent"] == "stove"
    assert outputs[0]["states"] == {"is_cooked": True, "temperature": "hot"}


def test_recipe_specs_declare_output_states():
    from backend.core.processes import RECIPE_SPECS

    assert RECIPE_SPECS["stove"]["output_states"] == {"is_cooked": True, "temperature": "hot"}
    assert RECIPE_SPECS["coffeemachine"]["output_states"] == {"temperature": "hot"}
    assert RECIPE_SPECS["printer"]["resource_costs"] == {"count": 1, "amount": 1}


def test_printer_recipe_consumes_paper_and_ink_then_outputs_receipt():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "office", "states": {}},
            "office": {"id": "office", "node_type": "room", "states": {}},
            "printer": {"id": "printer", "node_type": "fixed_object", "semantic_type": "printer", "parent": "office", "interactive_actions": ["press"], "states": {"count": 2, "amount": 3, "is_running": False, "cycle_remaining": 0}},
        },
        "parent_of": {"robot": "office", "printer": "office"},
        "relation_of": {"robot": "at", "printer": "in"},
        "room_of": {"robot": "office", "printer": "office"},
        "control_edges": [], "room_edges": [], "world_state": {},
    }
    assert apply_action_schema(state, {"agent": "robot", "action": "press", "target": "printer"}) == ()
    assert state["nodes"]["printer"]["states"]["count"] == 1
    assert state["nodes"]["printer"]["states"]["amount"] == 2
    apply_timed_transitions(state, 1)
    apply_timed_transitions(state, 2)
    receipts = [item for item in state["nodes"].values() if item.get("semantic_type") == "receipt"]
    assert len(receipts) == 1 and receipts[0]["parent"] == "printer"
    assert receipts[0]["produced_by_device"] == "printer"
    assert receipts[0]["produced_by_recipe"] == "printer"


def test_printer_loads_dispensed_paper_and_ink_instances_into_internal_supplies():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "office", "states": {}},
            "office": {"id": "office", "node_type": "room", "states": {}},
            "printer": {"id": "printer", "node_type": "fixed_object", "semantic_type": "printer", "parent": "office", "interactive_actions": ["place", "press"], "resource_capacity": {"count": 10, "amount": 10}, "states": {"count": 0, "amount": 0}},
            "paper": {"id": "paper", "node_type": "movable_object", "semantic_type": "paper_pack", "parent": "robot", "resource_instance_of": "paper_pool", "states": {"count": 2}},
            "paper_pool": {"id": "paper_pool", "node_type": "fixed_object", "semantic_type": "paper_dispenser", "resource_pool": {"consumed_count": 0}, "states": {}},
        },
        "parent_of": {"robot": "office", "printer": "office", "paper": "robot", "paper_pool": "office"},
        "relation_of": {"robot": "at", "printer": "in", "paper": "held_by", "paper_pool": "in"},
        "room_of": {"robot": "office", "printer": "office", "paper": "office", "paper_pool": "office"},
        "control_edges": [], "room_edges": [], "world_state": {},
    }
    assert apply_action_schema(state, {"agent": "robot", "action": "place", "object": "paper", "target": "printer"}) == ()
    assert "paper" not in state["nodes"]
    assert state["nodes"]["printer"]["states"]["count"] == 2
    assert state["nodes"]["paper_pool"]["resource_pool"]["consumed_count"] == 1
    assert state["world_state"]["event_log"][-1]["type"] == "resource_loaded"


def test_print_document_skill_requires_both_printer_resources():
    from backend.core.assets.task_library import relevant_skills_for_nodes

    nodes = {"printer": {"id": "printer", "semantic_type": "printer", "states": {"count": 1, "amount": 1, "is_running": False}}}
    assert [skill["name"] for skill in relevant_skills_for_nodes(nodes)] == ["print_document"]
    nodes["printer"]["states"]["amount"] = 0
    assert not relevant_skills_for_nodes(nodes)


def test_dishwash_dishes_skill_is_discovered_for_dirty_loaded_dishes():
    from backend.core.assets.task_library import relevant_skills_for_nodes

    nodes = {
        "dishwasher": {"id": "dishwasher", "semantic_type": "dishwasher", "states": {"is_running": False}},
        "plate": {"id": "plate", "semantic_type": "plate", "parent": "dishwasher", "states": {"is_dirty": True}},
    }
    assert [skill["name"] for skill in relevant_skills_for_nodes(nodes)] == ["dishwash_dishes"]
    nodes["plate"]["states"]["is_dirty"] = False
    assert not relevant_skills_for_nodes(nodes)


def test_recipe_uses_numeric_water_level_and_preserves_compatibility_flag():
    from backend.core.processes import start_process

    state = {
        "nodes": {
            "machine": {"id": "machine", "semantic_type": "coffeemachine", "states": {"has_water": True, "water_level": 50}},
            "beans": {"id": "beans", "semantic_type": "coffee_beans", "parent": "machine", "states": {}},
            "cup": {"id": "cup", "semantic_type": "cup", "parent": "machine", "states": {}},
        },
        "parent_of": {"beans": "machine", "cup": "machine"},
        "world_state": {},
    }
    assert start_process(state, "machine") is True
    assert state["nodes"]["machine"]["states"]["water_level"] == 25.0
    assert state["nodes"]["machine"]["states"]["has_water"] is True


def test_assembly_line_consumes_delivered_parts_and_emits_finished_product():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "factory", "states": {}},
            "factory": {"id": "factory", "node_type": "room", "states": {}},
            "line": {
                "id": "line", "node_type": "fixed_object", "semantic_type": "assembly_line",
                "parent": "factory", "interactive_actions": ["press", "place"],
                "states": {"is_on": False, "is_running": False, "cycle_remaining": 0},
            },
            "part_a": {"id": "part_a", "node_type": "movable_object", "semantic_type": "component_a", "parent": "line", "states": {}},
            "part_b": {"id": "part_b", "node_type": "movable_object", "semantic_type": "component_b", "parent": "line", "states": {}},
        },
        "parent_of": {"robot": "factory", "line": "factory", "part_a": "line", "part_b": "line"},
        "relation_of": {"robot": "at", "line": "in", "part_a": "in", "part_b": "in"},
        "room_of": {"robot": "factory", "line": "factory", "part_a": "factory", "part_b": "factory"},
        "control_edges": [], "room_edges": [], "world_state": {},
    }
    assert apply_action_schema(state, {"agent": "robot", "action": "press", "target": "line"}) == ()
    for _ in range(4):
        apply_timed_transitions(state, 1)
    assert "part_a" not in state["nodes"]
    assert "part_b" not in state["nodes"]
    products = [node for node in state["nodes"].values() if node.get("semantic_type") == "finished_product"]
    assert len(products) == 1
    assert products[0]["parent"] == "line"
    assert [event["type"] for event in state["world_state"]["event_log"]] == [
        "process_started", "process_consumed", "process_consumed", "process_completed"
    ]


def test_assembly_line_skill_requires_both_parts():
    nodes = {
        "line": {"id": "line", "semantic_type": "assembly_line", "states": {"is_running": False}},
        "a": {"id": "a", "semantic_type": "component_a", "parent": "line", "states": {}},
        "b": {"id": "b", "semantic_type": "component_b", "parent": "line", "states": {}},
    }
    assert [skill["name"] for skill in relevant_skills_for_nodes(nodes)] == ["assemble_product"]
    nodes.pop("b")
    assert not relevant_skills_for_nodes(nodes)


def test_assembly_line_skill_is_discovered_for_upstream_inventory():
    nodes = {
        "line": {"id": "line", "semantic_type": "assembly_line", "states": {"is_running": False}},
        "warehouse": {"id": "warehouse", "semantic_type": "room", "states": {}},
        "workshop": {"id": "workshop", "semantic_type": "room", "states": {}},
        "a": {"id": "a", "semantic_type": "component_a", "parent": "warehouse", "states": {}},
        "b": {"id": "b", "semantic_type": "component_b", "parent": "workshop", "states": {}},
    }
    skills = relevant_skills_for_nodes(nodes)
    assert [skill["name"] for skill in skills] == ["assemble_product"]


def _elevator_state(is_open: bool):
    return {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "semantic_type": "robot", "parent": "room_a", "states": {}},
            "room_a": {"id": "room_a", "node_type": "room", "semantic_type": "room", "states": {}},
            "room_b": {"id": "room_b", "node_type": "room", "semantic_type": "room", "states": {}},
            "lift": {
                "id": "lift", "node_type": "fixed_object", "semantic_type": "elevator", "parent": "room_a",
                "interactive_actions": ["move", "open", "close"], "served_rooms": ["room_a", "room_b"],
                "states": {"is_open": is_open},
            },
        },
        "parent_of": {"robot": "room_a", "lift": "room_a"},
        "relation_of": {"robot": "at", "lift": "in"},
        "room_of": {"robot": "room_a", "lift": "room_a"},
        "control_edges": [], "room_edges": [],
    }


def test_move_can_use_open_elevator_between_non_adjacent_rooms():
    state = _elevator_state(True)
    assert apply_action_schema(state, {"agent": "robot", "action": "move", "target": "room_b"}) == ()
    assert state["parent_of"]["robot"] == "room_b"


def test_move_rejects_closed_elevator_between_non_adjacent_rooms():
    state = _elevator_state(False)
    failures = apply_action_schema(state, {"agent": "robot", "action": "move", "target": "room_b"})
    assert failures and "no open elevator connects" in failures[0]


def test_elevator_press_runs_then_delivers_robot_and_opens_door():
    state = _elevator_state(True)
    state["nodes"]["lift"]["interactive_actions"].append("press")
    assert apply_action_schema(state, {"agent": "robot", "action": "move", "target": "lift"}) == ()
    assert apply_action_schema(state, {"agent": "robot", "action": "press", "target": "lift", "destination_room": "room_b"}) == ()
    assert state["nodes"]["lift"]["states"]["is_running"] is True
    assert state["nodes"]["robot"]["parent"] == "lift"
    for _ in range(2):
        apply_timed_transitions(state, 1)
    assert state["nodes"]["robot"]["parent"] == "room_b"
    assert state["nodes"]["lift"]["states"]["is_open"] is True
    assert state["nodes"]["lift"].get("requested_room") is None


def test_elevator_requires_destination_and_rejects_running_cycle():
    state = _elevator_state(True)
    state["nodes"]["lift"]["interactive_actions"].append("press")
    apply_action_schema(state, {"agent": "robot", "action": "move", "target": "lift"})
    missing = apply_action_schema(state, {"agent": "robot", "action": "press", "target": "lift"})
    assert missing == ("elevator destination is not served: <missing>",)
    assert apply_action_schema(state, {"agent": "robot", "action": "press", "target": "lift", "destination_room": "room_b"}) == ()
    running = apply_action_schema(state, {"agent": "robot", "action": "press", "target": "lift", "destination_room": "room_a"})
    assert running == ("elevator is already running: lift",)


def test_time_transitions_emit_structured_lifecycle_events():
    state = {
        "nodes": {
            "vase": {"id": "vase", "semantic_type": "vase", "parent": "room", "states": {"has_water": True}},
            "flower": {"id": "flower", "semantic_type": "flower", "parent": "vase", "states": {"vitality": 0.2, "is_wilted": False}},
            "food": {"id": "food", "semantic_type": "food", "parent": "room", "states": {"is_rotten": False}},
            "shirt": {"id": "shirt", "semantic_type": "clothes", "parent": "rack", "states": {"is_wet": True, "cycle_remaining": 1}},
            "room": {"id": "room", "node_type": "room", "states": {}},
            "rack": {"id": "rack", "semantic_type": "drying_rack", "parent": "room", "states": {}},
        },
        "parent_of": {"vase": "room", "flower": "vase", "food": "room", "shirt": "rack", "rack": "room"},
        "relation_of": {}, "room_of": {"vase": "room", "flower": "room", "food": "room", "shirt": "room", "rack": "room"},
        "world_state": {"natural_change_enabled": True},
    }
    apply_timed_transitions(state, 1)
    for _ in range(11):
        apply_timed_transitions(state, 1)
    for _ in range(143):
        apply_timed_transitions(state, 1)
    event_types = [event["type"] for event in state["world_state"]["event_log"]]
    assert "drying_completed" in event_types
    assert "water_depleted" in event_types
    assert "flower_wilted" in event_types
    assert "food_spoiled" in event_types


def test_numeric_vase_water_depletes_in_steps_before_empty_event():
    state = {
        "nodes": {
            "vase": {"id": "vase", "semantic_type": "vase", "parent": "room", "states": {"has_water": True, "water_level": 100}},
            "flower": {"id": "flower", "semantic_type": "flower", "parent": "vase", "states": {"vitality": 1.0, "is_wilted": False}},
            "room": {"id": "room", "node_type": "room", "states": {}},
        },
        "parent_of": {"vase": "room", "flower": "vase"},
        "room_of": {"vase": "room", "flower": "room"},
        "world_state": {"natural_change_enabled": True},
    }
    for _ in range(12):
        apply_timed_transitions(state, 1)
    assert state["nodes"]["vase"]["states"]["water_level"] == 80.0
    assert state["nodes"]["vase"]["states"]["has_water"] is True
    assert not any(event["type"] == "water_depleted" for event in state["world_state"].get("event_log", []))


def test_faucet_fills_sink_gradually_on_shared_clock():
    from backend.core.timed_transitions import apply_timed_transitions

    state = {
        "nodes": {
            "room": {"id": "room", "node_type": "room", "states": {}},
            "faucet": {"id": "faucet", "semantic_type": "faucet", "states": {"is_on": True}},
            "sink": {"id": "sink", "semantic_type": "sink", "states": {"water_level": 0.0, "has_water": False}},
        },
        "control_edges": [{"source_id": "faucet", "target_id": "sink", "relation": "controls"}],
        "parent_of": {"faucet": "room", "sink": "room"}, "room_of": {"faucet": "room", "sink": "room"},
        "world_state": {},
    }
    apply_timed_transitions(state, 0)
    assert state["nodes"]["sink"]["states"]["water_level"] == 20.0
    apply_timed_transitions(state, 1)
    assert state["nodes"]["sink"]["states"]["water_level"] == 40.0


def test_humidity_changes_drying_duration_without_changing_default_weather_contract():
    def state_with_humidity(humidity):
        return {
            "nodes": {
                "room": {"id": "room", "node_type": "room", "states": {}},
                "rack": {"id": "rack", "semantic_type": "drying_rack", "parent": "room", "states": {}},
                "shirt": {"id": "shirt", "semantic_type": "clothes", "parent": "rack", "states": {"is_wet": True}},
            },
            "parent_of": {"rack": "room", "shirt": "rack"},
            "room_of": {"rack": "room", "shirt": "room"},
            "world_state": {"weather": "sunny", "room_humidity": {"room": humidity}},
        }
    dry = state_with_humidity(20)
    humid = state_with_humidity(90)
    apply_timed_transitions(dry, 1)
    apply_timed_transitions(humid, 1)
    assert dry["nodes"]["shirt"]["states"]["cycle_remaining"] == 3
    assert humid["nodes"]["shirt"]["states"]["cycle_remaining"] == 9


def test_advance_time_is_the_shared_batch_clock():
    from backend.core.timed_transitions import advance_time

    state = {
        "nodes": {
            "room": {"id": "room", "node_type": "room", "states": {}},
            "vase": {"id": "vase", "semantic_type": "vase", "parent": "room", "states": {"has_water": True, "water_level": 100}},
            "flower": {"id": "flower", "semantic_type": "flower", "parent": "vase", "states": {"vitality": 1.0, "is_wilted": False}},
        },
        "parent_of": {"vase": "room", "flower": "vase"},
        "room_of": {"vase": "room", "flower": "room"},
        "world_state": {"step": 4, "natural_change_enabled": True},
    }
    advance_time(state, 3)
    assert state["world_state"]["step"] == 7
    assert state["world_state"]["time_min"] == 30
