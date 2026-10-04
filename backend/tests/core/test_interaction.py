from backend.runtime.agent_profile import profile_for_agent
from backend.runtime.input_adapter import InteractionRequest, resolve_interaction
from backend.runtime.action_executor import ActionExecutor
from backend.runtime.world import World


def _graph(*extra_nodes):
    return World({
        "schema_version": 2,
        "id_namespace": "editor",
        "nodes": [
            {"id": "room", "editor_id": "room", "node_type": "room", "states": {}},
            {"id": "robot", "editor_id": "robot", "node_type": "agent", "states": {}},
            {
                "id": "cabinet", "editor_id": "cabinet", "node_type": "object",
                "capabilities": ["openable", "place_target"], "states": {"is_open": False},
            },
            {
                "id": "shirt", "editor_id": "shirt", "node_type": "object",
                "capabilities": ["pickable", "washable"], "states": {},
            },
            *[{**item, "editor_id": item["id"], "node_type": "object"} for item in extra_nodes],
        ],
        "edges": [
            {"source_id": "room", "target_id": "robot", "relation": "at"},
            {"source_id": "room", "target_id": "cabinet", "relation": "inside"},
            {"source_id": "room", "target_id": "shirt", "relation": "inside"},
            *[{"source_id": "room", "target_id": item["id"], "relation": "inside"} for item in extra_nodes],
        ],
    })


def _apply_interaction(graph, request):
    resolved = resolve_interaction(graph.state_for_rules(), request)
    assert resolved.action is not None, resolved.failures
    return resolved, ActionExecutor(graph).execute(resolved.action)


def test_interaction_resolves_open_and_pick_without_exposing_business_input():
    state = _graph().state_for_rules()
    assert resolve_interaction(
        state, {"actor_id": "robot", "input": "interact_primary", "target_id": "cabinet"}
    ).action["action"] == "open"
    assert resolve_interaction(state, InteractionRequest("robot", "grab", "shirt")).action == {
        "agent": "robot", "action": "pick", "object": "shirt"
    }


def test_legacy_structural_door_uses_declared_open_action_as_affordance():
    graph = _graph({
        "id": "door", "semantic_type": "door",
        "interactive_actions": ["open", "close"], "states": {"is_open": False},
    })
    result = resolve_interaction(graph.state_for_rules(), {
        "actor_id": "robot", "input": "interact_primary", "target_id": "door",
    })
    assert result.action == {"agent": "robot", "action": "open", "target": "door"}


def test_door_action_uses_serialized_boolean_state_without_reversing_it():
    graph = _graph({
        "id": "door", "semantic_type": "door",
        "interactive_actions": ["open", "close"], "states": {"is_open": "false"},
    })
    result = resolve_interaction(graph.state_for_rules(), {
        "actor_id": "robot", "input": "interact_primary", "target_id": "door",
    })
    assert result.action == {"agent": "robot", "action": "open", "target": "door"}


def test_interaction_resolves_place_from_hand_edge():
    graph = _graph()
    graph.move_node("shirt", "robot", "held_by")
    result = resolve_interaction(
        graph.state_for_rules(),
        {"actor_id": "robot", "input": "interact_primary", "target_id": "cabinet"},
    )
    assert result.action["action"] == "place"
    assert result.action["object"] == "shirt"


def test_held_object_only_blocks_the_same_hand():
    graph = _graph({
        "id": "door", "semantic_type": "door",
        "interactive_actions": ["open", "close"], "states": {"is_open": False},
    })
    graph.move_node("shirt", "robot", "held_by_left")
    result = resolve_interaction(graph.state_for_rules(), {
        "actor_id": "robot", "input": "interact_primary", "target_id": "door", "hand": "right",
    })
    assert result.action["action"] == "open"
    graph.move_node("shirt", "robot", "held_by_right")
    result = resolve_interaction(graph.state_for_rules(), {
        "actor_id": "robot", "input": "interact_primary", "target_id": "door", "hand": "right",
    })
    assert result.action is None
    assert "target cannot receive held object" in result.failures[0]


def test_occupied_interaction_hand_cannot_open_door():
    graph = _graph({
        "id": "door", "semantic_type": "door",
        "interactive_actions": ["open", "close"], "states": {"is_open": False},
    })
    graph.move_node("shirt", "robot", "held_by_right")
    result = resolve_interaction(graph.state_for_rules(), {
        "actor_id": "robot", "input": "interact_primary", "target_id": "door", "hand": "right",
    })
    assert result.action is None
    assert "target cannot receive held object" in result.failures[0]


def test_place_preserves_3d_hit_as_canonical_volume_anchor():
    graph = _graph()
    graph.move_node("shirt", "robot", "held_by")
    result = resolve_interaction(graph.state_for_rules(), {
        "actor_id": "robot", "target_id": "cabinet", "hand": "right",
        "hit": {"node_id": "cabinet", "volume_uv": [0.25, 0.5, 0.75]},
    })
    assert result.action["volume_anchor"] == [0.25, 0.5, 0.75]
    assert result.action["interaction_hit"]["node_id"] == "cabinet"


def test_resolved_interaction_commits_through_mutation_pipeline():
    graph = _graph()
    resolved, result = _apply_interaction(
        graph, {"actor_id": "robot", "input": "grab", "target_id": "shirt"}
    )
    assert result.ok is True
    assert resolved.action["action"] == "pick"
    assert graph.parent_of["shirt"] == "robot"
    assert result.delta.edges_added


def test_agent_profile_declares_embodiment_and_manipulator_capacity():
    profile = profile_for_agent({"geometry": {"collision_shape": "capsule", "height_m": 1.7}, "hand_count": 2})
    assert profile.collision_shape == "capsule"
    assert profile.height_m == 1.7
    assert profile.hand_count == 2
    assert "grasp" in profile.hand_capabilities


def test_interaction_rejects_two_hand_target_for_single_hand_agent():
    graph = _graph()
    graph.nodes["shirt"]["capabilities"].append("two_hand_required")
    graph.nodes["robot"]["hand_count"] = 1
    result = resolve_interaction(
        graph.state_for_rules(),
        {"actor_id": "robot", "input": "grab", "target_id": "shirt"},
    )
    assert result.action is None
    assert "two hands" in result.failures[0]


def test_left_and_right_hands_can_hold_independent_objects():
    graph = _graph({
        "id": "towel",
        "capabilities": ["pickable"], "states": {},
    })
    _, right = _apply_interaction(graph, {
        "actor_id": "robot", "input": "grab", "target_id": "shirt", "hand": "right",
    })
    _, left = _apply_interaction(graph, {
        "actor_id": "robot", "input": "grab", "target_id": "towel", "hand": "left",
    })
    assert right.ok is True
    assert left.ok is True
    assert graph.relation_of["shirt"] == "held_by"
    assert graph.relation_of["towel"] == "held_by_left"


def test_two_hand_object_reserves_both_hands_and_blocks_second_pick():
    graph = _graph({
        "id": "towel",
        "capabilities": ["pickable"], "states": {},
    })
    graph.nodes["shirt"]["capabilities"].append("two_hand_required")
    _, first = _apply_interaction(graph, {
        "actor_id": "robot", "input": "grab", "target_id": "shirt", "hand": "left",
    })
    assert first.ok is True
    assert graph.relation_of["shirt"] == "held_by_both"
    blocked = resolve_interaction(graph.state_for_rules(), {
        "actor_id": "robot", "input": "grab", "target_id": "towel", "hand": "left",
    })
    assert blocked.action is None
    assert "already holds" in blocked.failures[0] or "cannot receive" in blocked.failures[0]
