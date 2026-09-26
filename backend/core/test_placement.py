from backend.core.action_schemas import apply_action_schema, validate_action_schema
from backend.core.placement import normalized_surface_anchor


def test_surface_anchor_is_clamped_and_grid_snapped():
    assert normalized_surface_anchor({"surface_point_cm": [24.9, 9.9], "surface_size_cm": [50, 20]}, grid_cm=5) == [0.5, 0.5]
    assert normalized_surface_anchor({"surface_anchor": [2, -1]}) == [1.0, 0.0]
    assert normalized_surface_anchor({"interaction_hit": {"node_id": "table", "surface_uv": [0.25, 0.75]}}) == [0.25, 0.75]


def test_volume_anchor_accepts_interaction_hit_volume_coordinates():
    from backend.core.placement import normalized_volume_anchor

    assert normalized_volume_anchor({"interaction_hit": {"node_id": "drawer", "volume_uv": [0.2, 0.6, 0.8]}}) == [0.2, 0.6, 0.8]


def test_place_records_surface_anchor_and_target():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "room", "states": {}},
            "room": {"id": "room", "node_type": "room", "states": {}},
            "table": {
                "id": "table", "node_type": "fixed_object", "semantic_type": "table",
                "parent": "room", "interactive_actions": ["place"], "surface_size_cm": [50, 20],
                "surface_grid_cm": 5, "states": {},
            },
            "cup": {"id": "cup", "node_type": "movable_object", "semantic_type": "cup", "parent": "robot", "footprint_cm": [10, 10], "states": {}},
        },
        "parent_of": {"robot": "room", "table": "room", "cup": "robot"},
        "relation_of": {"robot": "at", "table": "in", "cup": "held_by"},
        "room_of": {"robot": "room", "table": "room", "cup": "room"},
        "control_edges": [], "room_edges": [],
    }
    action = {"agent": "robot", "action": "place", "object": "cup", "target": "table", "surface_point_cm": [24.9, 9.9]}
    assert validate_action_schema(state, action) == ()
    assert apply_action_schema(state, action) == ()
    assert state["nodes"]["cup"]["placement_target"] == "table"
    assert state["nodes"]["cup"]["placement_anchor"] == [0.5, 0.5]
    assert state["world_state"]["event_log"][-1] == {
        "type": "object_placed", "object_id": "cup", "target_id": "table",
        "relation": "on", "surface_anchor": [0.5, 0.5],
    }
    state["nodes"]["box"] = {"id": "box", "node_type": "movable_object", "semantic_type": "box", "parent": "robot", "footprint_cm": [10, 10], "states": {}}
    state["parent_of"]["box"] = "robot"
    state["relation_of"]["box"] = "held_by"
    overlap = {"agent": "robot", "action": "place", "object": "box", "target": "table", "surface_anchor": [0.5, 0.5]}
    assert any("overlaps cup" in failure for failure in validate_action_schema(state, overlap))


def test_place_rejects_footprint_outside_surface_boundary():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "room", "states": {}},
            "room": {"id": "room", "node_type": "room", "states": {}},
            "table": {"id": "table", "node_type": "fixed_object", "semantic_type": "table", "parent": "room", "interactive_actions": ["place"], "surface_size_cm": [50, 20], "states": {}},
            "box": {"id": "box", "node_type": "movable_object", "semantic_type": "box", "parent": "robot", "footprint_cm": [20, 10], "states": {}},
        },
        "parent_of": {"robot": "room", "table": "room", "box": "robot"},
        "relation_of": {"robot": "at", "table": "in", "box": "held_by"},
        "room_of": {"robot": "room", "table": "room", "box": "room"},
        "control_edges": [], "room_edges": [],
    }
    action = {"agent": "robot", "action": "place", "object": "box", "target": "table", "surface_anchor": [0.05, 0.5]}
    failures = validate_action_schema(state, action)
    assert any("does not fit at surface anchor" in failure for failure in failures)


def test_place_rejects_surface_overload():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "room", "states": {}},
            "room": {"id": "room", "node_type": "room", "states": {}},
            "table": {"id": "table", "node_type": "fixed_object", "semantic_type": "table", "parent": "room", "interactive_actions": ["place"], "surface_size_cm": [50, 20], "max_load_kg": 1, "states": {}},
            "box": {"id": "box", "node_type": "movable_object", "semantic_type": "box", "parent": "robot", "mass_kg": 2, "footprint_cm": [10, 10], "states": {}},
        },
        "parent_of": {"robot": "room", "table": "room", "box": "robot"},
        "relation_of": {"robot": "at", "table": "in", "box": "held_by"},
        "room_of": {"robot": "room", "table": "room", "box": "room"},
        "control_edges": [], "room_edges": [],
    }
    failures = validate_action_schema(state, {"agent": "robot", "action": "place", "object": "box", "target": "table"})
    assert any("exceeds 1kg" in failure for failure in failures)


def test_place_on_stackable_surface_records_stack_level_and_support():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "room", "states": {}},
            "room": {"id": "room", "node_type": "room", "states": {}},
            "table": {"id": "table", "node_type": "fixed_object", "semantic_type": "table", "parent": "room", "interactive_actions": ["place"], "surface_size_cm": [50, 20], "allow_stacking": True, "states": {}},
            "first": {"id": "first", "node_type": "movable_object", "semantic_type": "box", "parent": "table", "footprint_cm": [10, 10], "placement_target": "table", "placement_anchor": [0.5, 0.5], "stack_index": 1, "states": {}},
            "second": {"id": "second", "node_type": "movable_object", "semantic_type": "box", "parent": "robot", "footprint_cm": [10, 10], "states": {}},
        },
        "parent_of": {"robot": "room", "table": "room", "first": "table", "second": "robot"},
        "relation_of": {"robot": "at", "table": "in", "first": "on", "second": "held_by"},
        "room_of": {"robot": "room", "table": "room", "first": "room", "second": "room"},
        "control_edges": [], "room_edges": [], "world_state": {},
    }
    assert apply_action_schema(state, {"agent": "robot", "action": "place", "object": "second", "target": "table"}) == ()
    assert state["nodes"]["second"]["stack_index"] == 2
    assert state["nodes"]["second"]["support_object_id"] == "first"


def _volume_state(*, closed: bool = False):
    return {
        "nodes": {
            "robot": {"id": "robot", "node_type": "robot", "parent": "room", "states": {}},
            "room": {"id": "room", "node_type": "room", "states": {}},
            "cabinet": {"id": "cabinet", "node_type": "fixed_object", "semantic_type": "cabinet", "parent": "room", "interactive_actions": ["place"], "states": {"is_open": not closed}},
            "slot": {"id": "slot", "node_type": "fixed_object", "semantic_type": "storage_slot", "parent": "cabinet", "interactive_actions": ["place"], "interior_size_cm": [40, 30, 30], "states": {}},
            "box": {"id": "box", "node_type": "movable_object", "semantic_type": "box", "parent": "robot", "bounds_cm": [10, 10, 10], "states": {}},
        },
        "parent_of": {"robot": "room", "cabinet": "room", "slot": "cabinet", "box": "robot"},
        "relation_of": {"robot": "at", "cabinet": "in", "slot": "in", "box": "held_by"},
        "room_of": {"robot": "room", "cabinet": "room", "slot": "room", "box": "room"},
        "control_edges": [], "room_edges": [],
    }


def test_place_supports_container_volume_and_records_3d_anchor():
    state = _volume_state()
    action = {"agent": "robot", "action": "place", "object": "box", "target": "slot", "volume_anchor": [0.5, 0.5, 0.5]}
    assert validate_action_schema(state, action) == ()
    assert apply_action_schema(state, action) == ()
    assert state["nodes"]["box"]["placement_volume_anchor"] == [0.5, 0.5, 0.5]
    assert state["nodes"]["box"]["placement_volume_target"] == "slot"
    assert state["world_state"]["event_log"][-1]["type"] == "object_placed"
    assert state["world_state"]["event_log"][-1]["volume_anchor"] == [0.5, 0.5, 0.5]


def test_place_rejects_volume_overflow_and_3d_overlap():
    state = _volume_state()
    state["nodes"]["box"]["bounds_cm"] = [50, 10, 10]
    failures = validate_action_schema(state, {"agent": "robot", "action": "place", "object": "box", "target": "slot"})
    assert any("exceed interior" in failure for failure in failures)
    state = _volume_state()
    state["nodes"]["other"] = {"id": "other", "node_type": "movable_object", "semantic_type": "box", "parent": "slot", "bounds_cm": [10, 10, 10], "placement_volume_target": "slot", "placement_volume_anchor": [0.5, 0.5, 0.5], "states": {}}
    state["parent_of"]["other"] = "slot"
    state["relation_of"]["other"] = "in"
    failures = validate_action_schema(state, {"agent": "robot", "action": "place", "object": "box", "target": "slot"})
    assert any("volume overlaps other" in failure for failure in failures)


def test_place_rejects_closed_ancestor_of_storage_slot():
    state = _volume_state(closed=True)
    failures = validate_action_schema(state, {"agent": "robot", "action": "place", "object": "box", "target": "slot"})
    assert any("container is closed: cabinet" in failure for failure in failures)


def test_place_rejects_interior_overload():
    state = _volume_state()
    state["nodes"]["slot"]["max_load_kg"] = 1
    state["nodes"]["box"]["mass_kg"] = 2
    failures = validate_action_schema(state, {"agent": "robot", "action": "place", "object": "box", "target": "slot"})
    assert any("interior load 2kg exceeds 1kg" in failure for failure in failures)


def test_composite_slot_requires_declared_capability():
    state = _volume_state()
    state["nodes"]["slot"]["requires_contained_capabilities"] = ["washable"]
    state["nodes"]["box"]["capabilities"] = ["pickable"]
    failures = validate_action_schema(state, {"agent": "robot", "action": "place", "object": "box", "target": "slot"})
    assert any("lacks required containment capability: washable" in failure for failure in failures)
    state["nodes"]["box"]["capabilities"].append("washable")
    assert validate_action_schema(state, {"agent": "robot", "action": "place", "object": "box", "target": "slot"}) == ()


def test_composite_slots_check_catalog_capabilities_for_real_items():
    state = _volume_state()
    state["nodes"]["slot"]["requires_contained_capabilities"] = ["washable"]
    state["nodes"]["box"].update(semantic_type="clothes", capabilities=None)
    assert validate_action_schema(state, {"agent": "robot", "action": "place", "object": "box", "target": "slot"}) == ()
    state["nodes"]["box"].update(semantic_type="toothpaste", capabilities=None)
    failures = validate_action_schema(state, {"agent": "robot", "action": "place", "object": "box", "target": "slot"})
    assert any("lacks required containment capability: washable" in failure for failure in failures)

    state["nodes"]["slot"]["requires_contained_capabilities"] = ["cookable"]
    state["nodes"]["box"].update(semantic_type="milk", capabilities=None)
    assert validate_action_schema(state, {"agent": "robot", "action": "place", "object": "box", "target": "slot"}) == ()
    state["nodes"]["box"].update(semantic_type="clothes", capabilities=None)
    failures = validate_action_schema(state, {"agent": "robot", "action": "place", "object": "box", "target": "slot"})
    assert any("lacks required containment capability: cookable" in failure for failure in failures)


def test_internal_slot_capacity_limits_item_count():
    state = _volume_state()
    state["nodes"]["slot"]["max_capacity"] = 1
    state["nodes"]["existing"] = {
        "id": "existing", "node_type": "movable_object", "semantic_type": "box",
        "parent": "slot", "bounds_cm": [5, 5, 5], "states": {},
    }
    state["parent_of"]["existing"] = "slot"
    state["relation_of"]["existing"] = "inside"
    failures = validate_action_schema(state, {"agent": "robot", "action": "place", "object": "box", "target": "slot"})
    assert any("target capacity exceeded: slot" in failure for failure in failures)
