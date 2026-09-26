from backend.core.agent import profile_for_agent
from backend.core.interaction import InteractionRequest, resolve_and_apply_interaction, resolve_interaction


def _state():
    return {
        "nodes": {
            "room": {"id": "room", "node_type": "room", "states": {}},
            "robot": {"id": "robot", "node_type": "robot", "parent": "room", "states": {}},
            "cabinet": {"id": "cabinet", "node_type": "fixed_object", "parent": "room", "capabilities": ["openable", "place_target"], "states": {"is_open": False}},
            "shirt": {"id": "shirt", "node_type": "movable_object", "parent": "room", "capabilities": ["pickable", "washable"], "states": {}},
        },
        "parent_of": {"robot": "room", "cabinet": "room", "shirt": "room"},
        "relation_of": {}, "room_of": {"robot": "room", "cabinet": "room", "shirt": "room"},
        "control_edges": [], "room_edges": [],
    }


def test_interaction_resolves_open_and_pick_without_exposing_business_input():
    state = _state()
    assert resolve_interaction(state, {"actor_id": "robot", "input": "interact_primary", "target_id": "cabinet"}).action["action"] == "open"
    assert resolve_interaction(state, InteractionRequest("robot", "grab", "shirt")).action == {"agent": "robot", "action": "pick", "object": "shirt"}


def test_interaction_resolves_place_from_hand_state():
    state = _state()
    state["nodes"]["shirt"]["parent"] = "robot"
    state["parent_of"]["shirt"] = "robot"
    state["relation_of"]["shirt"] = "held_by"
    result = resolve_interaction(state, {"actor_id": "robot", "input": "interact_primary", "target_id": "cabinet"})
    assert result.action["action"] == "place"
    assert result.action["object"] == "shirt"


def test_resolve_and_apply_commits_canonical_transition():
    state = _state()
    result = resolve_and_apply_interaction(state, {"actor_id": "robot", "input": "grab", "target_id": "shirt"})
    assert result.applied is True
    assert result.action["action"] == "pick"
    assert state["parent_of"]["shirt"] == "robot"


def test_agent_profile_declares_embodiment_and_manipulator_capacity():
    profile = profile_for_agent({"geometry": {"collision_shape": "capsule", "height_m": 1.7}, "hand_count": 2})
    assert profile.collision_shape == "capsule"
    assert profile.height_m == 1.7
    assert profile.hand_count == 2
    assert "grasp" in profile.hand_capabilities


def test_interaction_rejects_two_hand_target_for_single_hand_agent():
    state = _state()
    state["nodes"]["shirt"]["capabilities"].append("two_hand_required")
    state["nodes"]["robot"]["hand_count"] = 1
    result = resolve_interaction(state, {"actor_id": "robot", "input": "grab", "target_id": "shirt"})
    assert result.action is None
    assert "two hands" in result.failures[0]


def test_left_and_right_hands_can_hold_independent_objects():
    state = _state()
    state["nodes"]["towel"] = {
        "id": "towel", "node_type": "movable_object", "parent": "room",
        "capabilities": ["pickable"], "states": {},
    }
    state["parent_of"]["towel"] = "room"
    state["room_of"]["towel"] = "room"
    right = resolve_and_apply_interaction(state, {
        "actor_id": "robot", "input": "grab", "target_id": "shirt", "hand": "right",
    })
    left = resolve_and_apply_interaction(state, {
        "actor_id": "robot", "input": "grab", "target_id": "towel", "hand": "left",
    })
    assert right.applied is True
    assert left.applied is True
    assert state["relation_of"]["shirt"] == "held_by"
    assert state["relation_of"]["towel"] == "held_by_left"


def test_two_hand_object_reserves_both_hands_and_blocks_second_pick():
    state = _state()
    state["nodes"]["shirt"]["capabilities"].append("two_hand_required")
    first = resolve_and_apply_interaction(state, {
        "actor_id": "robot", "input": "grab", "target_id": "shirt", "hand": "left",
    })
    assert first.applied is True
    assert state["relation_of"]["shirt"] == "held_by_both"
    state["nodes"]["towel"] = {
        "id": "towel", "node_type": "movable_object", "parent": "room",
        "capabilities": ["pickable"], "states": {},
    }
    state["parent_of"]["towel"] = "room"
    state["room_of"]["towel"] = "room"
    blocked = resolve_interaction(state, {
        "actor_id": "robot", "input": "grab", "target_id": "towel", "hand": "left",
    })
    assert blocked.action is None
    assert "already holds" in blocked.failures[0] or "cannot receive" in blocked.failures[0]
