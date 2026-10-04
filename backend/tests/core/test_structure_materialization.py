from backend.runtime.world.graph import World
from backend.generation.assets.object_templates import materialize_templates


def test_materialization_upgrades_legacy_component_edges_without_spatial_duplicates():
    scene = {
        "schema_version": 2,
        "id_namespace": "editor",
        "scene_name": "legacy",
        "nodes": [
            {"id": "room", "editor_id": "room", "node_type": "room", "semantic_type": "kitchen"},
            {"id": "host", "editor_id": "host", "node_type": "object", "semantic_type": "cabinet"},
            {"id": "slot", "editor_id": "slot", "node_type": "object", "semantic_type": "storage_slot", "component_role": "storage_slot"},
        ],
        "edges": [
            {"source_id": "room", "target_id": "host", "relation": "inside_room"},
            {"source_id": "host", "target_id": "slot", "relation": "component_of"},
            {"source_id": "host", "target_id": "slot", "relation": "in", "properties": {"generated": True}},
        ],
    }

    materialize_templates(scene)

    structure = [edge for edge in scene["edges"] if edge["relation"] == "structure"]
    upgraded = next(edge for edge in structure if edge["target_id"] == "slot")
    assert upgraded["properties"]["parent"] == "host"
    assert upgraded["properties"]["child"] == "slot"
    assert not any(
        edge["relation"] in {"component_of", "in"}
        and edge.get("source_id") == "host"
        and edge.get("target_id") == "slot"
        for edge in scene["edges"]
    )
    assert next(node for node in scene["nodes"] if node["id"] == "slot")["role"] == "component"
    slot = next(node for node in scene["nodes"] if node["id"] == "slot")
    assert slot["can_contain"] is True
    assert slot["max_items"] == slot["max_capacity"]


def test_component_room_is_inherited_through_structure_parent():
    scene = {
        "schema_version": 2,
        "id_namespace": "editor",
        "scene_name": "structure-room",
        "nodes": [
            {"id": "room", "editor_id": "room", "node_type": "room", "semantic_type": "kitchen"},
            {"id": "host", "editor_id": "host", "node_type": "object", "semantic_type": "cabinet"},
            {"id": "slot", "editor_id": "slot", "role": "component", "owner_id": "host", "node_type": "object", "semantic_type": "storage_slot"},
        ],
        "edges": [
            {"source_id": "room", "target_id": "host", "relation": "inside_room"},
            {"source_id": "host", "target_id": "slot", "relation": "structure", "properties": {"parent": "host", "child": "slot", "joint_type": "fixed", "origin": {}}},
        ],
    }

    world = World(scene)
    assert world.room_for("slot") == "room"
