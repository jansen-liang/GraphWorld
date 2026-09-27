from backend.core.mutation import MutationPipeline
from backend.core.world_graph import WorldGraph


def test_action_pipeline_commits_edge_and_returns_delta():
    graph = WorldGraph({
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

    result = MutationPipeline(graph).apply_action({"agent": "robot", "action": "pick", "object": "shirt"})

    assert result.ok is True
    assert graph.parent_of["shirt"] == "robot"
    assert result.delta.edges_removed[0]["source_id"] == "room"
    assert result.delta.edges_added[0]["source_id"] == "robot"
