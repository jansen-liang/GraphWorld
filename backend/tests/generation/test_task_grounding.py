from backend.generation.task_grounding import ground_template


def test_grounding_reads_locations_from_canonical_edges_without_runtime_helpers():
    scene = {
        "nodes": [
            {"id": "kitchen", "node_type": "room", "semantic_type": "kitchen"},
            {"id": "cup", "node_type": "object", "semantic_type": "cup"},
        ],
        "edges": [
            {"source_id": "kitchen", "target_id": "cup", "relation": "in"},
        ],
    }
    tasks = ground_template(scene, {
        "task_id": "find_cup",
        "parameters": {"item": {"object_query": {"semantic_type": "cup"}}},
    })
    assert tasks == [{
        "task_id": "find_cup",
        "family": None,
        "binding": {"item": "cup"},
        "requirements": {},
        "goal": [],
        "pddl": {},
        "status": "grounded",
    }]
