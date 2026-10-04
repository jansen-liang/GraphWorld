from backend.runtime.input_adapter import ActionResolver, resolve_interaction
from backend.runtime.world import World
from backend.core.input_event import InteractEvent


def test_action_resolver_is_the_canonical_input_boundary():
    world = World({
        "schema_version": 2,
        "id_namespace": "editor",
        "nodes": [
            {"id": "room", "node_type": "room", "states": {}},
            {"id": "agent", "node_type": "agent", "states": {}},
            {"id": "lamp", "node_type": "object", "capabilities": ["switchable"], "states": {"is_on": False}},
        ],
        "edges": [{"source_id": "room", "target_id": "agent", "relation": "at"}],
    })
    request = {"actor_id": "agent", "target_id": "lamp"}
    canonical = ActionResolver().resolve(world.state_for_rules(), request)
    compatibility = resolve_interaction(world.state_for_rules(), request)
    assert canonical.action == compatibility.action == {"agent": "agent", "action": "press", "target": "lamp"}


def test_action_resolver_accepts_core_interact_event():
    world = World({
        "schema_version": 2,
        "id_namespace": "editor",
        "nodes": [
            {"id": "room", "node_type": "room", "states": {}},
            {"id": "agent", "node_type": "agent", "states": {}},
            {"id": "lamp", "node_type": "object", "capabilities": ["switchable"], "states": {"is_on": False}},
        ],
        "edges": [{"source_id": "room", "target_id": "agent", "relation": "at"}],
    })
    result = ActionResolver().resolve(world.state_for_rules(), InteractEvent("agent", target_node_id="lamp"))
    assert result.action == {"agent": "agent", "action": "press", "target": "lamp"}


def test_action_resolver_turns_a_no_hit_interaction_into_raise_hand():
    world = World({
        "schema_version": 2, "id_namespace": "editor",
        "nodes": [{"id": "room", "node_type": "room"}, {"id": "agent", "node_type": "agent"}],
        "edges": [{"source_id": "room", "target_id": "agent", "relation": "at"}],
    })
    result = ActionResolver().resolve(world.state_for_rules(), {"actor_id": "agent", "hand": "left"})
    assert result.action == {"agent": "agent", "action": "raise_hand", "hand": "left"}
    lowered = ActionResolver().resolve(world.state_for_rules(), {"actor_id": "agent", "input": "lower_hand", "hand": "left"})
    assert lowered.action == {"agent": "agent", "action": "lower_hand", "hand": "left"}
