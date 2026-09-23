from backend.core.action_schemas import apply_action_schema, validate_action_schema


def _state():
    return {
        "nodes": {
            "robot_01": {"id": "robot_01", "node_type": "robot", "parent": "room"},
            "room": {"id": "room", "node_type": "room", "parent": ""},
        },
        "parent_of": {"robot_01": "room"},
        "relation_of": {"robot_01": "at"},
        "room_of": {"robot_01": "room", "room": "room"},
        "world_state": {"event_log": []},
    }


def test_wait_is_a_legal_temporal_noop_and_emits_audit_event():
    state = _state()
    action = {"agent": "robot_01", "action": "wait"}

    assert validate_action_schema(state, action) == ()
    assert apply_action_schema(state, action, step=7) == ()
    assert state["world_state"]["event_log"][-1] == {
        "type": "robot_action_wait",
        "actor_id": "robot_01",
        "step": 7,
    }
