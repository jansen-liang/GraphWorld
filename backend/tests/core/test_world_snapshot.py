from backend.runtime.world import World
from backend.runtime.scene_schema import validate_canonical_scene


def test_runtime_agent_and_held_object_transforms_override_editor_transform():
    world = World({
        "schema_version": 2,
        "id_namespace": "editor",
        "nodes": [
            {"id": "room", "node_type": "room", "states": {}},
            {"id": "agent", "node_type": "agent", "world_transform": {"position": [99, 0, 99]}, "states": {}},
            {"id": "shoe", "node_type": "object", "world_transform": {"position": [1, 0, 1]}, "states": {}},
        ],
        "edges": [
            {"source_id": "room", "target_id": "agent", "relation": "at"},
            {"source_id": "agent", "target_id": "shoe", "relation": "held_by"},
        ],
        "world_state": {"agents": {"agent": {"position": {"x": 2.0, "y": 1.6, "z": 3.0}}}},
    })

    scene = world.to_scene()
    nodes = {item["id"]: item for item in scene["nodes"]}
    assert scene["coordinate_system"] == {
        "units": "m",
        "handedness": "right",
        "up_axis": "z",
        "rotation": "quaternion_xyzw",
    }
    assert nodes["agent"]["world_transform"]["position"] == [2.0, -3.0, 1.6]
    assert nodes["shoe"]["world_transform"]["position"] == [2.0, -3.0, 1.6]


def test_structure_snapshot_composes_parent_origin_and_joint_state():
    world = World({
        "schema_version": 2,
        "id_namespace": "editor",
        "nodes": [
            {"id": "machine", "node_type": "object", "role": "root", "world_transform": {"position": [1, 2, 3], "rotation": [0, 0, 0, 1], "scale": [1, 1, 1]}, "joint_states": {"slide": {"position": 0.4}}},
            {"id": "drawer", "node_type": "object", "role": "component", "owner_id": "machine"},
        ],
        "edges": [{
            "id": "slide", "source_id": "machine", "target_id": "drawer", "relation": "structure",
            "properties": {"parent": "machine", "child": "drawer", "joint_type": "prismatic", "axis": [0, 0, 1], "origin": {"position": [0, 1, 0]}},
        }],
    })
    drawer = next(node for node in world.to_scene()["nodes"] if node["id"] == "drawer")
    assert drawer["world_transform"]["position"] == [1.0, 3.0, 3.4]
    assert drawer["transform_space"] == "graphworld_z_up"
    assert drawer["transform_origin"] == "structure"


def test_structure_snapshot_projects_component_open_state_to_joint_state():
    world = World({
        "schema_version": 2,
        "id_namespace": "editor",
        "nodes": [
            {"id": "machine", "node_type": "object", "role": "root", "world_transform": {"position": [0, 0, 0], "rotation": [0, 0, 0, 1], "scale": [1, 1, 1]}},
            {"id": "door", "node_type": "object", "role": "component", "owner_id": "machine", "states": {"is_open": True}},
        ],
        "edges": [{
            "id": "machine-door", "source_id": "machine", "target_id": "door", "relation": "structure",
            "properties": {"parent": "machine", "child": "door", "joint_type": "revolute", "axis": [0, 0, 1], "origin": {}},
        }],
    })
    machine = next(node for node in world.to_scene()["nodes"] if node["id"] == "machine")
    assert machine["joint_states"]["machine-door"] == 1.5707963267948966


def test_canonical_schema_accepts_agent_embodiment_structure():
    scene = {
        "schema_version": 2,
        "id_namespace": "editor",
        "nodes": [
            {"id": "agent", "node_type": "agent", "role": "root"},
            {"id": "hand", "node_type": "object", "role": "component", "owner_id": "agent"},
        ],
        "edges": [{
            "source_id": "agent", "target_id": "hand", "relation": "structure",
            "properties": {"parent": "agent", "child": "hand", "joint_type": "fixed"},
        }],
    }
    assert validate_canonical_scene(scene)["edges"][0]["relation"] == "structure"


def test_snapshot_always_exposes_visual_cues_for_delta_reconciliation():
    world = World({
        "schema_version": 2,
        "id_namespace": "editor",
        "nodes": [{"id": "lamp", "node_type": "object", "states": {"is_on": False}}],
        "edges": [],
    })
    lamp = next(node for node in world.to_scene()["nodes"] if node["id"] == "lamp")
    assert lamp["visual_cues"] == []


def test_layout_object_world_transform_includes_room_floor_elevation():
    world = World({
        "schema_version": 2,
        "id_namespace": "editor",
        "layout": {
            "grid_size": 0.1,
            "rooms": {"f2_room": {"grid_x": 0, "grid_y": 0, "width_cells": 10, "depth_cells": 10, "floor_number": 2}},
            "objects": {"hall_button": {"room_id": "f2_room", "x_cm": 10, "y_cm": 10, "z_cm": 120, "width_cm": 20, "depth_cm": 8, "height_cm": 8}},
        },
        "nodes": [
            {"id": "f2_room", "node_type": "room", "states": {}},
            {"id": "hall_button", "node_type": "object", "semantic_type": "button", "states": {}},
        ],
        "edges": [{"source_id": "f2_room", "target_id": "hall_button", "relation": "contains"}],
    })
    button = next(node for node in world.to_scene()["nodes"] if node["id"] == "hall_button")
    assert button["world_transform"]["position"][2] == 4.44
