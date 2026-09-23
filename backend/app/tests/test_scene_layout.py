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
    assert scene["layout"]["grid_size"] == 0.1
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


def test_room_and_object_footprints_are_template_sensitive():
    scene = ensure_scene_layout(load_home_scene())
    rooms = scene["layout"]["rooms"]
    objects = scene["layout"]["objects"]

    assert len({(room["width_cells"], room["depth_cells"]) for room in rooms.values()}) >= 4
    assert objects["button_entrance"]["width_cells"] == 3
    assert objects["button_entrance"]["depth_cells"] == 3
    assert objects["bed_bedroom"]["width_cells"] > objects["button_entrance"]["width_cells"]


def test_layout_exposes_centimeter_quantized_physical_geometry():
    scene = ensure_scene_layout(load_home_scene())
    layout = scene["layout"]

    assert layout["geometry_resolution_cm"] == 1
    assert layout["rooms"]["kitchen"]["width_cm"] == layout["rooms"]["kitchen"]["width_cells"] * 10
    assert layout["rooms"]["kitchen"]["height_cm"] == 260
    assert layout["objects"]["fridge_kitchen"]["width_cm"] == 90
    assert layout["objects"]["fridge_kitchen"]["height_cm"] == 180


def test_layout_reenrichment_preserves_editor_physical_coordinates():
    scene = ensure_scene_layout(load_home_scene())
    placement = scene["layout"]["objects"]["button_kitchen"]
    placement.update({"x_cm": 123, "y_cm": 456, "z_cm": 178})

    enriched = ensure_scene_layout(scene)
    restored = enriched["layout"]["objects"]["button_kitchen"]

    assert (restored["x_cm"], restored["y_cm"], restored["z_cm"]) == (123, 456, 178)


def test_contained_children_follow_host_physical_position():
    scene = ensure_scene_layout(load_home_scene())
    objects = scene["layout"]["objects"]
    host = objects["fridge_kitchen"]
    child = objects["juice_fridge_kitchen"]
    host.update({"x_cm": 321, "y_cm": 654})
    child.update({"x_cm": 1, "y_cm": 2, "z_cm": 42})

    enriched = ensure_scene_layout(scene)
    restored = enriched["layout"]["objects"]["juice_fridge_kitchen"]

    assert (restored["grid_x"], restored["grid_y"]) == (host["grid_x"], host["grid_y"])
    assert (restored["x_cm"], restored["y_cm"], restored["z_cm"]) == (321, 654, 42)


def test_layout_validation_rejects_missing_edge_endpoints_and_component_cycles():
    scene = ensure_scene_layout(load_home_scene())
    scene["edges"].append({"source_id": "missing", "target_id": "kitchen", "relation": "component_of"})
    scene["edges"].append({"source_id": "counter_kitchen", "target_id": "counter_kitchen", "relation": "component_of"})

    issues = validate_scene_layout(scene)

    assert any("missing source" in issue for issue in issues)
    assert any("containment cycle" in issue for issue in issues)


def test_mechanical_edges_require_matching_component_hosts():
    scene = ensure_scene_layout(load_home_scene())
    scene["nodes"].extend([
        {"id": "bad_hinge", "component_role": "hinge", "component_of": "fridge_kitchen"},
        {"id": "bad_door", "component_role": "door", "component_of": "microwave_kitchen"},
        {"id": "bad_drawer", "component_role": "drawer", "component_of": "cabinet_kitchen"},
    ])
    scene["edges"].extend([
        {"source_id": "bad_hinge", "target_id": "bad_door", "relation": "hinge_of"},
        {"source_id": "bad_drawer", "target_id": "microwave_kitchen", "relation": "slides_in"},
    ])
    issues = validate_scene_layout(scene)
    assert any("hinge_of" in issue for issue in issues)
    assert any("slides_in" in issue for issue in issues)


def test_room_layout_uses_semantic_anchors_for_composite_and_mounted_objects():
    scene = ensure_scene_layout(load_home_scene())
    objects = scene["layout"]["objects"]

    assert objects["counter_kitchen"]["layout_anchor"] == "service-wall"
    assert objects["juice_fridge_kitchen"]["placement_mode"] == "contained"
    assert objects["juice_fridge_kitchen"]["parent_object_id"] == "fridge_kitchen"
    assert objects["button_kitchen"]["placement_mode"] == "wall_mounted"
    assert objects["button_kitchen"]["grid_y"] == 0
