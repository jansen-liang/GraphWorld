from backend.core.changes import WorldDelta
from backend.runtime.action_executor import WorldTransaction
from backend.runtime.world import World


def test_runtime_delta_exposes_canonical_changes_and_legacy_projections():
    delta = WorldDelta(
        session_id="sim-1",
        base_revision=3,
        revision=4,
        time_seconds=1.5,
        state_changes=({"node_id": "lamp", "state": "is_on", "before": False, "after": True},),
        edges_added=({"source_id": "agent", "target_id": "shoe", "relation": "held_by"},),
        nodes_removed=("water",),
    )

    payload = delta.to_dict()
    assert payload["base_revision"] == 3
    assert payload["state_changes"][0]["state"] == "is_on"
    assert [change["change_type"] for change in payload["changes"]] == [
        "state_changed", "edge_added", "node_removed",
    ]


def test_transaction_emits_joint_state_changes_for_frontend_consumers():
    world = World({
        "schema_version": 2,
        "id_namespace": "editor",
        "nodes": [{"id": "machine", "node_type": "object", "joint_states": {"door": 0.0}}],
        "edges": [],
    })
    transaction = WorldTransaction(world)
    world.nodes["machine"]["joint_states"]["door"] = 1.0
    payload = transaction.commit().to_dict()
    assert payload["changes"] == [{
        "change_type": "joint_state_changed",
        "change_id": payload["changes"][0]["change_id"],
        "source": "runtime",
        "payload": {"node_id": "machine", "joint_id": "door", "before": 0.0, "after": 1.0},
    }]


def test_transaction_and_delta_publish_new_nodes():
    world = World({
        "schema_version": 2,
        "id_namespace": "editor",
        "nodes": [{"id": "machine", "node_type": "object"}],
        "edges": [],
    })
    transaction = WorldTransaction(world)
    world.nodes["receipt_1"] = {"id": "receipt_1", "node_type": "object", "states": {}}
    payload = transaction.commit().to_dict()
    assert payload["nodes_added"] == [{"id": "receipt_1", "node_type": "object", "states": {}}]
    assert any(change["change_type"] == "node_added" for change in payload["changes"])


def test_transaction_projects_state_driven_revolute_joint_changes():
    world = World({
        "schema_version": 2,
        "id_namespace": "editor",
        "nodes": [
            {"id": "machine", "node_type": "object"},
            {"id": "door", "node_type": "object", "role": "component", "owner_id": "machine", "states": {"is_open": False}},
        ],
        "edges": [{
            "id": "machine-door", "source_id": "machine", "target_id": "door", "relation": "structure",
            "properties": {"parent": "machine", "child": "door", "joint_type": "revolute", "origin": {}},
        }],
    })
    transaction = WorldTransaction(world)
    world.nodes["door"]["states"]["is_open"] = True
    changes = transaction.commit().to_dict()["changes"]
    assert any(change["change_type"] == "joint_state_changed" and change["payload"]["after"] > 1.5 for change in changes)


def test_transaction_publishes_visual_cue_removal_as_node_update():
    world = World({
        "schema_version": 2,
        "id_namespace": "editor",
        "nodes": [{
            "id": "lamp",
            "node_type": "object",
            "capabilities": ["emissive"],
            "states": {"is_on": True},
        }],
        "edges": [],
    })
    transaction = WorldTransaction(world)
    world.nodes["lamp"]["states"]["is_on"] = False
    changes = transaction.commit().to_dict()["changes"]
    cue_change = next(change for change in changes if change["change_type"] == "node_updated")
    assert cue_change["payload"] == {"node_id": "lamp", "visual_cues": []}
