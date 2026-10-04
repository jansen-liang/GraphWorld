from backend.app.services.simulation_service import SimulationWorldService
from backend.app.schemas.scene import SimulationDispatchRequest, SimulationStartRequest


def test_simulation_session_keeps_one_runtime_for_interaction_and_motion():
    scene = {
        "schema_version": 2,
        "id_namespace": "editor",
        "nodes": [
            {"id": "room", "node_type": "room", "states": {}},
            {"id": "robot", "node_type": "agent", "states": {}},
            {"id": "light", "node_type": "object", "semantic_type": "light", "capabilities": ["switchable"], "states": {"is_on": False}},
        ],
        "edges": [
            {"source_id": "room", "target_id": "robot", "relation": "at"},
            {"source_id": "room", "target_id": "light", "relation": "in"},
        ],
        "layout": {"grid_size": 0.5, "rooms": {"room": {"grid_x": 0, "grid_y": 0, "width_cells": 8, "depth_cells": 8}}, "objects": {}},
    }
    service = SimulationWorldService()
    started = service.start(SimulationStartRequest(source_json=scene, actor_id="robot"))
    assert started.snapshot["revision"] == 0
    assert started.snapshot["session_id"] == started.simulation_id
    moved = service.dispatch(SimulationDispatchRequest(simulation_id=started.simulation_id, input="move_step", direction="1 0", elapsed_seconds=0.1))
    assert moved.applied is True
    position = moved.snapshot["world_state"]["agents"]["robot"]["position"]
    assert position["x"] > 0
    assert moved.snapshot["revision"] == 1
    assert moved.delta["base_revision"] == 0
    assert moved.delta["revision"] == 1
    movement_payload = moved.delta["changes"][0]["payload"]
    assert movement_payload["transform_space"] == "graphworld_z_up"
    assert movement_payload["world_transform"]["position"] == [position["x"], -position["z"], position["y"]]
    pressed = service.dispatch(SimulationDispatchRequest(simulation_id=started.simulation_id, target_id="light"))
    assert pressed.applied is True
    assert next(node for node in pressed.snapshot["nodes"] if node["id"] == "light")["states"]["is_on"] is True


def test_simulation_session_tick_mutates_the_same_runtime():
    scene = {
        "schema_version": 2,
        "nodes": [
            {"id": "room", "node_type": "room", "states": {}},
            {"id": "agent", "node_type": "agent", "states": {}},
            {"id": "washer", "node_type": "object", "semantic_type": "washer", "capabilities": ["timed_device"], "states": {"is_running": True, "cycle_remaining": 2}},
        ],
        "edges": [
            {"source_id": "room", "target_id": "agent", "relation": "at"},
            {"source_id": "room", "target_id": "washer", "relation": "in"},
        ],
    }
    service = SimulationWorldService()
    started = service.start(SimulationStartRequest(source_json=scene, actor_id="agent"))
    result = service.dispatch(SimulationDispatchRequest(simulation_id=started.simulation_id, input="tick"))
    washer = next(node for node in result.snapshot["nodes"] if node["id"] == "washer")
    assert result.applied is True
    assert washer["states"]["cycle_remaining"] == 1
    assert any(change["state"] == "cycle_remaining" for change in result.delta["state_changes"])


def test_simulation_session_rejects_duplicate_input_event():
    scene = {
        "schema_version": 2, "id_namespace": "editor",
        "nodes": [{"id": "room", "node_type": "room", "states": {}}, {"id": "robot", "node_type": "agent", "states": {}}, {"id": "light", "node_type": "object", "capabilities": ["switchable"], "states": {"is_on": False}}],
        "edges": [{"source_id": "room", "target_id": "robot", "relation": "at"}, {"source_id": "room", "target_id": "light", "relation": "in"}],
    }
    service = SimulationWorldService()
    started = service.start(SimulationStartRequest(source_json=scene, actor_id="robot"))
    event = {"event_id": "evt-1", "sequence": 1, "event_type": "key", "phase": "pressed"}
    first = service.dispatch(SimulationDispatchRequest(simulation_id=started.simulation_id, target_id="light", event=event))
    duplicate = service.dispatch(SimulationDispatchRequest(simulation_id=started.simulation_id, target_id="light", event=event))
    assert first.applied is True
    assert duplicate.applied is False
    assert "duplicate" in duplicate.failures[0]


def test_simulation_session_rejects_reused_sequence_with_new_event_id():
    scene = {
        "schema_version": 2, "id_namespace": "editor",
        "nodes": [{"id": "room", "node_type": "room", "states": {}}, {"id": "robot", "node_type": "agent", "states": {}}, {"id": "light", "node_type": "object", "capabilities": ["switchable"], "states": {"is_on": False}}],
        "edges": [{"source_id": "room", "target_id": "robot", "relation": "at"}, {"source_id": "room", "target_id": "light", "relation": "in"}],
    }
    service = SimulationWorldService()
    started = service.start(SimulationStartRequest(source_json=scene, actor_id="robot"))
    first = service.dispatch(SimulationDispatchRequest(
        simulation_id=started.simulation_id,
        target_id="light",
        event={"event_id": "evt-1", "sequence": 1, "event_type": "key", "phase": "pressed"},
    ))
    reused = service.dispatch(SimulationDispatchRequest(
        simulation_id=started.simulation_id,
        target_id="light",
        event={"event_id": "evt-2", "sequence": 1, "event_type": "key", "phase": "pressed"},
    ))
    assert first.applied is True
    assert reused.applied is False
    assert "stale" in reused.failures[0]
