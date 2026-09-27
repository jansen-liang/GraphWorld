from backend.app.schemas.scene import SceneInteractionRequest, SceneTickRequest
from backend.app.services.simulation_service import SimulationService


def test_stateless_scene_interaction_returns_canonical_delta():
    scene = {
        "nodes": [
            {"id": "room", "node_type": "room", "states": {}},
            {"id": "robot", "node_type": "robot", "states": {}},
            {"id": "light", "node_type": "fixed_object", "semantic_type": "room_light", "capabilities": ["switchable"], "interactive_actions": ["press"], "states": {"is_on": False}},
        ],
        "edges": [
            {"source_id": "room", "target_id": "robot", "relation": "at"},
            {"source_id": "room", "target_id": "light", "relation": "in"},
        ],
    }

    result = SimulationService().interact(SceneInteractionRequest(
        source_json=scene, actor_id="robot", target_id="light",
    ))

    assert result.applied is True
    assert result.action == {"agent": "robot", "action": "press", "target": "light"}
    assert result.delta["state_changes"] == [
        {"node_id": "light", "state": "is_on", "before": False, "after": True},
        {"node_id": "light", "state": "is_pressed", "before": None, "after": True},
    ]
    light = next(node for node in result.source_json["nodes"] if node["id"] == "light")
    assert light["states"]["is_on"] is True


def test_stateless_scene_tick_returns_system_delta():
    scene = {
        "nodes": [
            {"id": "room", "node_type": "room", "states": {}},
            {"id": "washer", "node_type": "fixed_object", "semantic_type": "washer", "capabilities": ["timed_device"], "states": {"is_on": True, "is_running": True, "cycle_remaining": 2}},
        ],
        "edges": [{"source_id": "room", "target_id": "washer", "relation": "in"}],
    }

    result = SimulationService().tick(SceneTickRequest(source_json=scene))

    assert result.applied is True
    assert {item["state"] for item in result.delta["state_changes"]} >= {"cycle_remaining"}
    washer = next(node for node in result.source_json["nodes"] if node["id"] == "washer")
    assert washer["states"]["cycle_remaining"] == 1


def test_faucet_action_response_can_round_trip_into_tick():
    scene = {
        "nodes": [
            {"id": "room", "node_type": "room", "states": {}},
            {"id": "robot", "node_type": "robot", "states": {}},
            {"id": "faucet", "node_type": "fixed_object", "semantic_type": "faucet", "interactive_actions": ["press", "move"], "states": {"is_on": False}},
            {"id": "sink", "node_type": "fixed_object", "semantic_type": "sink", "states": {"has_water": False, "water_level": 0}},
        ],
        "edges": [
            {"source_id": "room", "target_id": "robot", "relation": "at"},
            {"source_id": "room", "target_id": "faucet", "relation": "in"},
            {"source_id": "room", "target_id": "sink", "relation": "in"},
            {"source_id": "faucet", "target_id": "sink", "relation": "controls"},
        ],
    }
    service = SimulationService()
    action_result = service.interact(SceneInteractionRequest(
        source_json=scene, actor_id="robot", target_id="faucet",
    ))
    assert action_result.applied is True
    sink = next(node for node in action_result.source_json["nodes"] if node["id"] == "sink")
    assert sink["states"]["water_flowing"] is True

    tick_result = service.tick(SceneTickRequest(source_json=action_result.source_json))

    assert tick_result.applied is True
    sink = next(node for node in tick_result.source_json["nodes"] if node["id"] == "sink")
    assert sink["states"]["water_level"] > 0
