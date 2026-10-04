import pytest

from backend.runtime.world import World
from backend.runtime.action_executor import ActionExecutor


def _scene(nodes, edges, **metadata):
    return {
        "scene_name": "test",
        "schema_version": 2,
        "id_namespace": "editor",
        **metadata,
        "nodes": [
            {"editor_id": item["id"], **item}
            for item in nodes
        ],
        "edges": edges,
    }


def test_world_rejects_legacy_parent_relationships():
    with pytest.raises(ValueError, match="schema_version=2"):
        World({
            "nodes": [{"id": "shirt", "node_type": "object", "parent": "room"}],
            "edges": [],
        })


def test_relationship_indices_are_rebuilt_from_edges():
    graph = World(_scene(
        [
            {"id": "room", "node_type": "room", "states": {}},
            {"id": "table", "node_type": "object", "states": {}},
            {"id": "cup", "node_type": "object", "states": {}},
        ],
        [
            {"source_id": "room", "target_id": "table", "relation": "in"},
            {"source_id": "table", "target_id": "cup", "relation": "on"},
        ],
    ))

    assert graph.parent_of == {"table": "room", "cup": "table"}
    assert graph.relation_of["cup"] == "on"
    assert graph.room_of["cup"] == "room"


def test_move_replaces_the_only_position_edge_and_round_trips():
    graph = World(_scene(
        [
            {"id": "room", "node_type": "room", "states": {}},
            {"id": "robot", "node_type": "agent", "states": {}},
            {"id": "cup", "node_type": "object", "states": {}},
        ],
        [
            {"source_id": "room", "target_id": "robot", "relation": "at"},
            {"source_id": "room", "target_id": "cup", "relation": "in"},
        ],
    ))

    graph.move_node("cup", "robot", "held_by")
    scene = graph.to_scene()
    position_edges = [edge for edge in scene["edges"] if edge["target_id"] == "cup"]
    assert [(edge["source_id"], edge["relation"]) for edge in position_edges] == [("robot", "held_by")]
    assert all("parent" not in node for node in scene["nodes"])


def test_round_trip_preserves_renderer_metadata():
    layout = {"grid_size": 20, "rooms": {"room": {"grid_x": 0}}}
    graph = World(_scene(
        [{"id": "room", "node_type": "room", "states": {}}],
        [], layout=layout, scene_domain="home",
    ))

    result = graph.to_scene()
    assert result["layout"] == layout
    assert result["scene_domain"] == "home"


def test_runtime_position_is_not_overwritten_by_initial_layout_after_move():
    graph = World(_scene(
        [
            {"id": "bedroom", "node_type": "room", "states": {}},
            {"id": "bathroom", "node_type": "room", "states": {}},
            {"id": "shirt", "node_type": "object", "states": {}},
        ],
        [{"source_id": "bedroom", "target_id": "shirt", "relation": "inside_room"}],
        layout={"objects": {"shirt": {"room_id": "bedroom", "placement_mode": "surface"}}},
    ))

    graph.move_node("shirt", "bathroom", "in")
    rebuilt = World(graph.to_scene())

    assert rebuilt.parent_of["shirt"] == "bathroom"
    assert rebuilt.relation_of["shirt"] == "in"


def test_snapshot_exposes_engine_neutral_transform_and_visibility_fields():
    graph = World(_scene(
        [{"id": "room", "node_type": "room", "states": {}}, {"id": "box", "node_type": "object", "states": {}}],
        [{"source_id": "room", "target_id": "box", "relation": "in"}],
        layout={"objects": {"box": {"room_id": "room", "x_cm": 100, "y_cm": 20, "z_cm": 40}}},
    ))
    box = next(item for item in graph.to_scene()["nodes"] if item["id"] == "box")
    assert box["world_transform"]["position"] == [1.0, -0.2, 0.4]
    assert box["visibility"] == "visible"
    assert box["collision_enabled"] is True
    assert box["joint_states"] == {}


def test_transaction_delta_lists_removed_nodes_and_edges():
    graph = World(_scene(
        [{"id": "room", "node_type": "room", "states": {}}, {"id": "item", "node_type": "object", "states": {}}],
        [{"source_id": "room", "target_id": "item", "relation": "in"}],
    ))
    result = ActionExecutor(graph).run(lambda _state: graph.remove_node("item"))
    delta = result.to_dict()
    assert delta["nodes_removed"] == ["item"]
    assert delta["edges_removed"]
