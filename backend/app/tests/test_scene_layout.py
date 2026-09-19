from __future__ import annotations

import json

from backend.app.runtime.scene_layout import ensure_scene_layout, validate_scene_layout


def load_home_scene() -> dict:
    with open("backend/data/sg_output/simple_graph/simple_home_1f.json", encoding="utf-8") as file:
        return json.load(file)


def load_hospital_scene() -> dict:
    with open("backend/data/sg_output/simple_graph/simple_hospital_1f.json", encoding="utf-8") as file:
        return json.load(file)


def test_generates_valid_layout_for_existing_home_scene():
    scene = ensure_scene_layout(load_home_scene())

    assert scene["layout"]["units"] == "meter"
    assert scene["layout"]["grid_size"] == 0.5
    assert len(scene["layout"]["rooms"]) == 7
    assert "living_room" in scene["layout"]["rooms"]
    assert "sofa_living_room" in scene["layout"]["objects"]
    assert "door_living_room" in scene["layout"]["doors"]
    assert "door_living_room" not in scene["layout"]["objects"]
    assert scene["layout"]["doors"]["door_living_room"]["room_a_id"] == "entrance"
    door_edges = {
        (edge["source_id"], edge["target_id"])
        for edge in scene["edges"]
        if edge["relation"] == "connects"
    }
    assert ("door_living_room", "entrance") in door_edges
    assert ("door_living_room", "living_room") in door_edges
    assert validate_scene_layout(scene) == []


def test_rejects_room_overlap_and_object_outside_room():
    scene = ensure_scene_layout(load_home_scene())
    scene["layout"]["rooms"]["kitchen"]["grid_x"] = scene["layout"]["rooms"]["living_room"]["grid_x"]
    scene["layout"]["rooms"]["kitchen"]["grid_y"] = scene["layout"]["rooms"]["living_room"]["grid_y"]
    scene["layout"]["objects"]["sofa_living_room"]["grid_x"] = 99

    issues = validate_scene_layout(scene)

    assert any("overlap" in issue for issue in issues)
    assert any("sofa_living_room" in issue and "inside room" in issue for issue in issues)


def test_corridor_connections_are_open_passages_without_doors():
    scene = ensure_scene_layout(load_hospital_scene())
    doors = scene["layout"]["doors"].values()

    assert all("corridor_main" not in {door["room_a_id"], door["room_b_id"]} for door in doors)
    assert validate_scene_layout(scene) == []
