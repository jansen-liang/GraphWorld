from backend.runtime.action_engine import apply_action_schema, validate_action_schema
from backend.adapter.physics.placement import normalized_surface_anchor


def test_surface_anchor_is_clamped_and_grid_snapped():
    assert normalized_surface_anchor({"surface_point_cm": [24.9, 9.9], "surface_size_cm": [50, 20]}, grid_cm=5) == [0.5, 0.5]
    assert normalized_surface_anchor({"surface_anchor": [2, -1]}) == [1.0, 0.0]
    assert normalized_surface_anchor({"interaction_hit": {"node_id": "table", "surface_uv": [0.25, 0.75]}}) == [0.25, 0.75]


def test_volume_anchor_accepts_interaction_hit_volume_coordinates():
    from backend.adapter.physics.placement import normalized_volume_anchor

    assert normalized_volume_anchor({"interaction_hit": {"node_id": "drawer", "volume_uv": [0.2, 0.6, 0.8]}}) == [0.2, 0.6, 0.8]


def test_place_records_surface_anchor_and_target():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "agent", "parent": "room", "states": {}},
            "room": {"id": "room", "node_type": "room", "states": {}},
            "table": {
                "id": "table", "node_type": "object", "semantic_type": "table",
                "parent": "room", "interactive_actions": ["place"], "can_support": True,
                "capabilities": ["support_surface"], "surface_spec": {"width_cm": 50, "depth_cm": 20, "grid_size_cm": 5},
                "states": {},
            },
            "cup": {"id": "cup", "node_type": "object", "semantic_type": "cup", "parent": "robot", "footprint_cm": [10, 10], "states": {}},
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
    assert state["nodes"]["cup"]["placement_transform"]["position"] == [0.0, 0.0, 0.1]
    assert state["nodes"]["cup"]["world_transform"]["position"] == [0.0, 0.0, 0.1]
    assert state["nodes"]["cup"]["storage_mode"] == "visible"
    assert state["world_state"]["event_log"][-1] == {
        "type": "object_placed", "object_id": "cup", "target_id": "table",
        "relation": "on", "surface_anchor": [0.5, 0.5],
    }
    state["nodes"]["box"] = {"id": "box", "node_type": "object", "semantic_type": "box", "parent": "robot", "footprint_cm": [10, 10], "states": {}}
    state["parent_of"]["box"] = "robot"
    state["relation_of"]["box"] = "held_by"
    overlap = {"agent": "robot", "action": "place", "object": "box", "target": "table", "surface_anchor": [0.5, 0.5]}
    assert any("overlaps cup" in failure for failure in validate_action_schema(state, overlap))


def test_place_rejects_footprint_outside_surface_boundary():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "agent", "parent": "room", "states": {}},
            "room": {"id": "room", "node_type": "room", "states": {}},
            "table": {"id": "table", "node_type": "object", "semantic_type": "table", "parent": "room", "interactive_actions": ["place"], "can_support": True, "capabilities": ["support_surface"], "surface_spec": {"width_cm": 50, "depth_cm": 20}, "states": {}},
            "box": {"id": "box", "node_type": "object", "semantic_type": "box", "parent": "robot", "footprint_cm": [20, 10], "states": {}},
        },
        "parent_of": {"robot": "room", "table": "room", "box": "robot"},
        "relation_of": {"robot": "at", "table": "in", "box": "held_by"},
        "room_of": {"robot": "room", "table": "room", "box": "room"},
        "control_edges": [], "room_edges": [],
    }
    action = {"agent": "robot", "action": "place", "object": "box", "target": "table", "surface_anchor": [0.05, 0.5]}
    failures = validate_action_schema(state, action)
    assert any("does not fit at surface anchor" in failure for failure in failures)


def test_place_accepts_grid_snapped_anchor_on_surface_edge():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "agent", "parent": "room", "states": {}},
            "room": {"id": "room", "node_type": "room", "states": {}},
            "table": {"id": "table", "node_type": "object", "parent": "room", "interactive_actions": ["place"], "can_support": True, "capabilities": ["support_surface"], "surface_spec": {"width_cm": 60, "depth_cm": 60, "grid_size_cm": 1}, "states": {}},
            "shoe": {"id": "shoe", "node_type": "object", "parent": "robot", "footprint_cm": [30, 12], "states": {}},
        },
        "parent_of": {"robot": "room", "table": "room", "shoe": "robot"},
        "relation_of": {"robot": "in", "table": "in", "shoe": "held_by"},
        "room_of": {"robot": "room", "table": "room", "shoe": "room"},
        "control_edges": [], "room_edges": [],
    }
    assert validate_action_schema(state, {"agent": "robot", "action": "place", "object": "shoe", "target": "table", "surface_anchor": [0.75, 0.9]}) == ()


def test_place_rejects_surface_overload():
    state = {
        "nodes": {
            "robot": {"id": "robot", "node_type": "agent", "parent": "room", "states": {}},
            "room": {"id": "room", "node_type": "room", "states": {}},
            "table": {"id": "table", "node_type": "object", "semantic_type": "table", "parent": "room", "interactive_actions": ["place"], "can_support": True, "capabilities": ["support_surface"], "surface_spec": {"width_cm": 50, "depth_cm": 20}, "max_load_kg": 1, "states": {}},
            "box": {"id": "box", "node_type": "object", "semantic_type": "box", "parent": "robot", "mass_kg": 2, "footprint_cm": [10, 10], "states": {}},
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
            "robot": {"id": "robot", "node_type": "agent", "parent": "room", "states": {}},
            "room": {"id": "room", "node_type": "room", "states": {}},
            "table": {"id": "table", "node_type": "object", "semantic_type": "table", "parent": "room", "interactive_actions": ["place"], "can_support": True, "capabilities": ["support_surface"], "surface_spec": {"width_cm": 50, "depth_cm": 20}, "allow_stacking": True, "states": {}},
            "first": {"id": "first", "node_type": "object", "semantic_type": "box", "parent": "table", "footprint_cm": [10, 10], "placement_target": "table", "placement_anchor": [0.5, 0.5], "stack_index": 1, "states": {}},
            "second": {"id": "second", "node_type": "object", "semantic_type": "box", "parent": "robot", "footprint_cm": [10, 10], "states": {}},
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
            "robot": {"id": "robot", "node_type": "agent", "parent": "room", "states": {}},
            "room": {"id": "room", "node_type": "room", "states": {}},
            "cabinet": {"id": "cabinet", "node_type": "object", "semantic_type": "cabinet", "parent": "room", "interactive_actions": ["place"], "states": {"is_open": not closed}},
            "slot": {"id": "slot", "node_type": "object", "semantic_type": "storage_slot", "parent": "cabinet", "interactive_actions": ["place"], "can_contain": True, "max_items": 4, "accepted_capabilities": [], "interior_size_cm": [40, 30, 30], "states": {}},
            "box": {"id": "box", "node_type": "object", "semantic_type": "box", "parent": "robot", "bounds_cm": [10, 10, 10], "states": {}},
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
    assert state["nodes"]["box"]["placement_transform"]["position"] == [0.0, 0.0, 0.0]
    assert state["nodes"]["box"]["storage_mode"] == "hidden"
    assert state["world_state"]["event_log"][-1]["type"] == "object_placed"
    assert state["world_state"]["event_log"][-1]["volume_anchor"] == [0.5, 0.5, 0.5]


def test_surface_placement_uses_hit_grid_and_target_world_transform():
    from backend.adapter.physics.placement import solve_placement_transform

    result = solve_placement_transform(
        {"id": "shoe", "footprint_cm": [10, 8], "height_cm": 6},
        {
                "id": "table", "surface_spec": {"width_cm": 50, "depth_cm": 20, "grid_size_cm": 5},
            "bounds_cm": [50, 20, 80],
            "world_transform": {"position": [1, 2, 3], "rotation": [0, 0, 0, 1], "scale": [1, 1, 1]},
        },
        {"surface_point_cm": [49, 10]},
    )
    # The hit is snapped to the edge grid, then shifted inward by half the
    # footprint so the shoe remains fully supported.
    assert result["support_surface"]["anchor"] == [0.9, 0.5]
    assert result["local_transform"]["position"] == [0.2, 0.0, 0.43]
    assert result["world_transform"]["position"] == [1.2, 2.0, 3.43]


def test_floor_placement_uses_interaction_hit_and_places_bottom_on_floor():
    from backend.adapter.physics.placement import solve_placement_transform

    result = solve_placement_transform(
        {"id": "shoe", "node_type": "object", "footprint_cm": [20, 10], "height_cm": 6},
        {"id": "bedroom", "node_type": "room"},
        {"interaction_hit": {"point_cm": [125, 0, 340]}},
    )
    assert result["relation"] == "on"
    assert result["storage_mode"] == "visible"
    assert result["world_transform"]["position"] == [1.25, -3.4, 0.03]


def test_place_rejects_volume_overflow_and_3d_overlap():
    state = _volume_state()
    state["nodes"]["box"]["bounds_cm"] = [50, 10, 10]
    failures = validate_action_schema(state, {"agent": "robot", "action": "place", "object": "box", "target": "slot"})
    assert any("exceed interior" in failure for failure in failures)
    state = _volume_state()
    state["nodes"]["other"] = {"id": "other", "node_type": "object", "semantic_type": "box", "parent": "slot", "bounds_cm": [10, 10, 10], "placement_volume_target": "slot", "placement_volume_anchor": [0.5, 0.5, 0.5], "states": {}}
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
    state["nodes"]["slot"]["accepted_capabilities"] = ["washable"]
    state["nodes"]["box"]["capabilities"] = ["pickable"]
    failures = validate_action_schema(state, {"agent": "robot", "action": "place", "object": "box", "target": "slot"})
    assert any("lacks required containment capability: washable" in failure for failure in failures)
    state["nodes"]["box"]["capabilities"].append("washable")
    assert validate_action_schema(state, {"agent": "robot", "action": "place", "object": "box", "target": "slot"}) == ()


def test_composite_slots_check_catalog_capabilities_for_real_items():
    state = _volume_state()
    state["nodes"]["slot"]["accepted_capabilities"] = ["washable"]
    state["nodes"]["box"].update(semantic_type="clothes", capabilities=None)
    assert validate_action_schema(state, {"agent": "robot", "action": "place", "object": "box", "target": "slot"}) == ()
    state["nodes"]["box"].update(semantic_type="toothpaste", capabilities=None)
    failures = validate_action_schema(state, {"agent": "robot", "action": "place", "object": "box", "target": "slot"})
    assert any("lacks required containment capability: washable" in failure for failure in failures)

    state["nodes"]["slot"]["accepted_capabilities"] = ["cookable"]
    state["nodes"]["box"].update(semantic_type="milk", capabilities=None)
    assert validate_action_schema(state, {"agent": "robot", "action": "place", "object": "box", "target": "slot"}) == ()
    state["nodes"]["box"].update(semantic_type="clothes", capabilities=None)
    failures = validate_action_schema(state, {"agent": "robot", "action": "place", "object": "box", "target": "slot"})
    assert any("lacks required containment capability: cookable" in failure for failure in failures)


def test_internal_slot_capacity_limits_item_count():
    state = _volume_state()
    state["nodes"]["slot"]["max_items"] = 1
    state["nodes"]["existing"] = {
        "id": "existing", "node_type": "object", "semantic_type": "box",
        "parent": "slot", "bounds_cm": [5, 5, 5], "states": {},
    }
    state["parent_of"]["existing"] = "slot"
    state["relation_of"]["existing"] = "inside"
    failures = validate_action_schema(state, {"agent": "robot", "action": "place", "object": "box", "target": "slot"})
    assert any("target capacity exceeded: slot" in failure for failure in failures)
