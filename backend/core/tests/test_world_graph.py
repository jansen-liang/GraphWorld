from backend.core.world import World


def test_legacy_parent_is_imported_as_canonical_edge_and_removed_from_node():
    graph = World({
        "scene_name": "legacy",
        "nodes": [
            {"id": "room", "node_type": "room", "states": {}},
            {"id": "robot", "node_type": "robot", "parent": "room", "states": {}},
            {"id": "shirt", "node_type": "movable_object", "parent": "room", "states": {}},
        ],
        "edges": [],
    })

    assert "parent" not in graph.node("shirt")
    assert graph.parent_of["shirt"] == "room"
    assert any(edge["source_id"] == "room" and edge["target_id"] == "shirt" for edge in graph.edges)


def test_relationship_indices_are_rebuilt_from_edges():
    graph = World({
        "nodes": [
            {"id": "room", "node_type": "room", "states": {}},
            {"id": "table", "node_type": "fixed_object", "states": {}},
            {"id": "cup", "node_type": "movable_object", "states": {}},
        ],
        "edges": [
            {"source_id": "room", "target_id": "table", "relation": "in"},
            {"source_id": "table", "target_id": "cup", "relation": "on"},
        ],
    })

    assert graph.parent_of == {"table": "room", "cup": "table"}
    assert graph.relation_of["cup"] == "on"
    assert graph.room_of["cup"] == "room"


def test_move_replaces_the_only_position_edge_and_round_trips():
    graph = World({
        "nodes": [
            {"id": "room", "node_type": "room", "states": {}},
            {"id": "robot", "node_type": "robot", "states": {}},
            {"id": "cup", "node_type": "movable_object", "states": {}},
        ],
        "edges": [
            {"source_id": "room", "target_id": "robot", "relation": "at"},
            {"source_id": "room", "target_id": "cup", "relation": "in"},
        ],
    })

    graph.move_node("cup", "robot", "held_by")
    scene = graph.to_scene()
    position_edges = [edge for edge in scene["edges"] if edge["target_id"] == "cup"]
    assert [(edge["source_id"], edge["relation"]) for edge in position_edges] == [("robot", "held_by")]
    assert all("parent" not in node for node in scene["nodes"])


def test_round_trip_preserves_renderer_metadata():
    layout = {"grid_size": 20, "rooms": {"room": {"grid_x": 0}}}
    graph = World({
        "scene_name": "layout",
        "nodes": [{"id": "room", "node_type": "room", "states": {}}],
        "edges": [],
        "layout": layout,
        "scene_domain": "home",
    })

    result = graph.to_scene()
    assert result["layout"] == layout
    assert result["scene_domain"] == "home"
