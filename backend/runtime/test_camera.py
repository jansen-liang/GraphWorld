from backend.runtime.camera import camera_spec_for_agent, validate_interaction_hit


def test_first_person_camera_contract_is_bound_to_agent_room_and_center_ray():
    scene = {
        "nodes": [
            {"id": "kitchen", "node_type": "room"},
            {"id": "robot_01", "node_type": "robot", "parent": "kitchen"},
        ]
    }

    camera = camera_spec_for_agent(scene, "robot_01")

    assert camera["contract_version"] == 1
    assert camera["agent_id"] == "robot_01"
    assert camera["room_id"] == "kitchen"
    assert camera["interaction_ray"]["screen_uv"] == [0.5, 0.5]
    assert camera["interaction_ray"]["space"] == "agent_local"
    assert camera["origin"][1] == 1.6


def test_declared_agent_camera_overrides_defaults_without_changing_contract():
    scene = {
        "nodes": [
            {"id": "room", "node_type": "room"},
            {
                "id": "robot_01",
                "node_type": "robot",
                "parent": "room",
                "camera": {"eye_height_m": 1.72, "forward": [1.0, 0.0, 0.0]},
            },
        ]
    }

    camera = camera_spec_for_agent(scene, "robot_01")

    assert camera["eye_height_m"] == 1.72
    assert camera["interaction_ray"]["direction"] == [1.0, 0.0, 0.0]
    assert camera["contract_version"] == 1


def test_malformed_camera_metadata_falls_back_to_safe_frame():
    scene = {"nodes": [
        {"id": "room", "node_type": "room"},
        {"id": "robot_01", "node_type": "robot", "parent": "room", "camera": {
            "eye_height_m": "invalid", "forward": [0, 0, 0], "viewport_uv": [4],
        }},
    ]}

    camera = camera_spec_for_agent(scene, "robot_01")

    assert camera["eye_height_m"] == 1.6
    assert camera["forward"] == [0.0, 0.0, 1.0]
    assert camera["viewport_uv"] == [0.5, 0.5]


def test_interaction_hit_requires_visible_target_and_normalized_surface_coordinate():
    valid = {"node_id": "table", "surface_uv": [0.25, 0.75], "distance_m": 2.0}
    assert validate_interaction_hit(valid, target_id="table", visible_node_ids={"table"}) == ()
    assert validate_interaction_hit(valid, target_id="other", visible_node_ids={"table"})
    assert validate_interaction_hit({"node_id": "table", "surface_uv": [1.2, 0.5]}, target_id="table")
    assert validate_interaction_hit({"node_id": "table"}, target_id="table")
    assert validate_interaction_hit({"node_id": "drawer", "volume_uv": [0.2, 0.4, 0.8]}, target_id="drawer") == ()
