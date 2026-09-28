from backend.core.action import ActionExecutor
from backend.core.world import World


def test_action_pipeline_commits_edge_and_returns_delta():
    graph = World({
        "nodes": [
            {"id": "room", "node_type": "room", "states": {}},
            {"id": "robot", "node_type": "robot", "states": {}},
            {"id": "shirt", "node_type": "movable_object", "capabilities": ["pickable"], "states": {}},
        ],
        "edges": [
            {"source_id": "room", "target_id": "robot", "relation": "at"},
            {"source_id": "room", "target_id": "shirt", "relation": "in"},
        ],
    })

    result = ActionExecutor(graph).execute({"agent": "robot", "action": "pick", "object": "shirt"})

    assert result.ok is True
    assert graph.parent_of["shirt"] == "robot"
    assert result.delta.edges_removed[0]["source_id"] == "room"
    assert result.delta.edges_added[0]["source_id"] == "robot"
