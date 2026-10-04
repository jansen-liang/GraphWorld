from backend.generation.assets.object_templates import structure_for, materialize_templates, validate_templates
from backend.generation.assets.object_library import OBJECT_LIBRARY
from backend.runtime.world import World
from backend.tests.core.scene_factory import scene_v2


def test_device_and_storage_templates_expose_composition_contracts():
    washer = OBJECT_LIBRARY["washing_machine"].instantiate("washer_01")
    toilet = OBJECT_LIBRARY["toilet"].instantiate("toilet_01")
    cabinet = OBJECT_LIBRARY["cabinet"].instantiate("cabinet_01")

    assert {item["role"] for item in washer["structure"]["components"]} == {"hinge", "door", "start_button"}
    for semantic_type in ("washing_machine", "washer", "microwave", "dishwasher", "dryer", "clothesdryer"):
        start_button = next(item for item in structure_for(semantic_type).to_dict()["components"] if item["role"] == "start_button")
        assert start_button["mount_face"] == "top"
    assert toilet["structure"]["components"][0]["role"] == "flush_button"
    assert {key: cabinet["structure"]["storage"][key] for key in ("kind", "levels", "columns", "depth_cm", "drawer_count", "slot_semantic_type")} == {
        "kind": "mixed",
        "levels": 3,
        "columns": 2,
        "depth_cm": 35.0,
        "drawer_count": 2,
        "slot_semantic_type": "storage_slot",
    }
    for semantic_type in ("microwave", "dishwasher"):
        roles = {item["role"] for item in OBJECT_LIBRARY[semantic_type].instantiate(semantic_type)["structure"]["components"]}
        assert roles == {"hinge", "door", "start_button"}
    assert {item["role"] for item in structure_for("clothesdryer").to_dict()["components"]} == {"hinge", "door", "start_button"}


def test_composition_validation_checks_mount_faces():
    assert validate_templates([
        {"id": "washer", "structure": structure_for("washer").to_dict()},
        {"id": "washer_button", "component_of": "washer", "relation": "controls"},
    ]) == []
    issues = validate_templates([
        {"id": "button"},
        {"id": "cabinet", "composition": {"components": [{"role": "bad", "mount_face": "diagonal"}]}},
    ])
    assert any("invalid mount face" in issue for issue in issues)


def test_materialization_adds_control_and_storage_children_idempotently():
    host = OBJECT_LIBRARY["cabinet"].instantiate("cabinet_01")
    scene = {"nodes": [host], "edges": []}
    materialize_templates(scene)
    first_ids = {node["id"] for node in scene["nodes"]}
    assert "cabinet_01_door" in first_ids
    assert "cabinet_01_drawer_1" in first_ids
    assert "cabinet_01_slot_l3_c2" in first_ids
    cabinet_door = next(node for node in scene["nodes"] if node["id"] == "cabinet_01_door")
    drawer = next(node for node in scene["nodes"] if node["id"] == "cabinet_01_drawer_1")
    assert cabinet_door["states"]["is_open"] is False
    assert cabinet_door["interactive_actions"] == ["open", "close"]
    assert drawer["states"]["is_open"] is False
    assert set(("open", "close", "place")).issubset(drawer["interactive_actions"])
    washer = OBJECT_LIBRARY["washing_machine"].instantiate("washer_01")
    control_scene = {"nodes": [washer], "edges": []}
    materialize_templates(control_scene)
    assert any(edge["relation"] == "controls" for edge in control_scene["edges"])
    assert any(node["id"] == "washer_01_hinge" and node["component_role"] == "hinge" for node in control_scene["nodes"])
    assert any(edge["relation"] == "hinge_of" and edge["source_id"] == "washer_01_hinge" and edge["target_id"] == "washer_01_door" for edge in control_scene["edges"])
    assert any(edge["relation"] == "slides_in" and edge["source_id"] == "cabinet_01_drawer_1" and edge["target_id"] == "cabinet_01" for edge in scene["edges"])
    materialize_templates(scene)
    assert {node["id"] for node in scene["nodes"]} == first_ids
    assert sum(edge.get("relation") == "slides_in" for edge in scene["edges"]) == 2
    assert sum(edge.get("relation") == "hinge_of" for edge in scene["edges"]) == 1
    scene["edges"] = [edge for edge in scene["edges"] if edge.get("relation") != "hinge_of"]
    materialize_templates(scene)
    assert sum(edge.get("relation") == "hinge_of" for edge in scene["edges"]) == 1


def test_door_bearing_storage_templates_materialize_real_access_and_slots():
    for semantic_type, expected_levels in (("medicine_fridge", 3), ("locker", 4)):
        host = OBJECT_LIBRARY[semantic_type].instantiate(f"{semantic_type}_01")
        scene = {"nodes": [host], "edges": []}
        materialize_templates(scene)
        nodes = {node["id"]: node for node in scene["nodes"]}
        assert f"{semantic_type}_01_hinge" in nodes
        door = nodes[f"{semantic_type}_01_door"]
        assert door["interactive_actions"] == ["open", "close"]
        assert door["states"]["is_open"] is False
        slots = [node for node in scene["nodes"] if node.get("component_role") == "storage_slot"]
        assert len(slots) == expected_levels
        assert all(node.get("interior_size_cm") for node in slots)


def test_appliance_storage_slots_materialize_capacity_and_required_abilities():
    expectations = {
        "washing_machine": (6, ["washable"]),
        "microwave": (1, ["cookable"]),
        "dishwasher": (8, ["dishwashable"]),
        "clothesdryer": (6, ["dryable"]),
    }
    for semantic_type, (capacity, abilities) in expectations.items():
        host = OBJECT_LIBRARY[semantic_type].instantiate(f"{semantic_type}_01")
        scene = {"nodes": [host], "edges": []}
        materialize_templates(scene)
        slot = next(node for node in scene["nodes"] if node.get("component_role") == "storage_slot")
        assert slot["max_capacity"] == capacity
        assert slot["states"]["capacity"] == capacity
        assert slot["requires_contained_capabilities"] == abilities


def test_legacy_partial_appliance_composition_inherits_missing_storage():
    current = OBJECT_LIBRARY["washer"].instantiate("washer")
    legacy = {
        "id": "washer",
        "node_type": "object",
        "semantic_type": "washer",
        "states": {"is_open": False},
        "composition": {"components": current["structure"]["components"]},
    }
    scene = {"nodes": [legacy], "edges": []}

    materialize_templates(scene)

    slot = next(node for node in scene["nodes"] if node.get("component_role") == "storage_slot")
    assert slot["id"] == "washer_slot_l1_c1"
    assert slot["requires_contained_capabilities"] == ["washable"]
    assert scene["nodes"][0]["structure"]["storage"]["capacity_per_slot"] == 6


def test_dresser_is_drawer_storage_not_a_single_block():
    host = OBJECT_LIBRARY["dresser"].instantiate("dresser_01")
    scene = {"nodes": [host], "edges": []}
    materialize_templates(scene)
    drawers = [node for node in scene["nodes"] if node.get("component_role") == "drawer"]
    assert len(drawers) == 3
    assert all({"open", "close", "place"}.issubset(node["interactive_actions"]) for node in drawers)


def test_mechanical_relations_round_trip_through_scene_graph():
    graph = World(scene_v2({
        "scene_name": "mechanical",
        "nodes": [{"id": "hinge", "node_type": "object"}, {"id": "door", "node_type": "object"}, {"id": "drawer", "node_type": "object"}, {"id": "cabinet", "node_type": "object"}],
        "edges": [
            {"source_id": "hinge", "target_id": "door", "relation": "hinge_of"},
            {"source_id": "drawer", "target_id": "cabinet", "relation": "slides_in"},
            {"source_id": "drawer", "target_id": "cabinet", "relation": "touching"},
        ],
    }))
    assert {edge["relation"] for edge in graph.edges} == {"hinge_of", "slides_in", "touching"}


def test_watering_can_template_starts_with_numeric_water_quantity():
    wateringcan = OBJECT_LIBRARY["wateringcan"].instantiate("wateringcan_01")
    assert wateringcan["states"]["water_level"] == 100.0
    assert wateringcan["states"]["has_water"] is True


def test_vase_template_starts_with_empty_numeric_water_quantity():
    vase = OBJECT_LIBRARY["vase"].instantiate("vase_01")
    assert vase["states"]["water_level"] == 0.0
    assert vase["states"]["has_water"] is False


def test_water_level_normalization_is_bounded():
    from backend.core.state import normalize_discrete_value

    assert normalize_discrete_value("water_level", -5) == 0.0
    assert normalize_discrete_value("water_level", 125) == 100.0
