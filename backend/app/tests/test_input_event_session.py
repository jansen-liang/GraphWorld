from backend.app.schemas.scene import SimulationDispatchRequest, SimulationStartRequest
from backend.app.services.simulation_service import SimulationWorldService


def test_key_release_event_is_ordered_without_mutating_world_semantics():
    scene = {
        "schema_version": 2,
        "id_namespace": "editor",
        "nodes": [
            {"id": "room", "node_type": "room", "states": {}},
            {"id": "agent", "node_type": "agent", "states": {}},
        ],
        "edges": [{"source_id": "room", "target_id": "agent", "relation": "at"}],
    }
    service = SimulationWorldService()
    started = service.start(SimulationStartRequest(source_json=scene, actor_id="agent"))
    result = service.dispatch(SimulationDispatchRequest(
        simulation_id=started.simulation_id,
        input="input_event",
        event={"event_id": "key-up-1", "sequence": 1, "event_type": "key", "phase": "released"},
    ))
    assert result.applied is True
    assert result.action == {"agent": "agent", "action": "input_event"}
    assert result.snapshot["revision"] == 1
    assert result.delta["base_revision"] == 0
    assert result.delta["revision"] == 1


def test_movement_release_clears_authoritative_moving_state():
    scene = {
        "schema_version": 2,
        "id_namespace": "editor",
        "nodes": [
            {"id": "room", "node_type": "room", "states": {}},
            {"id": "agent", "node_type": "agent", "states": {}},
        ],
        "edges": [{"source_id": "room", "target_id": "agent", "relation": "at"}],
    }
    service = SimulationWorldService()
    started = service.start(SimulationStartRequest(source_json=scene, actor_id="agent"))
    moved = service.dispatch(SimulationDispatchRequest(
        simulation_id=started.simulation_id,
        input="move_step",
        direction="1 0",
        elapsed_seconds=0.1,
        event={"event_id": "move-1", "sequence": 1, "event_type": "movement", "phase": "sampled"},
    ))
    assert moved.snapshot["world_state"]["agents"]["agent"]["moving"] is True
    released = service.dispatch(SimulationDispatchRequest(
        simulation_id=started.simulation_id,
        input="input_event",
        event={"event_id": "move-release-1", "sequence": 2, "event_type": "movement", "phase": "released"},
    ))
    assert released.applied is True
    assert released.snapshot["world_state"]["agents"]["agent"]["moving"] is False
    assert released.delta["changes"][0]["payload"]["runtime_state"]["moving"] is False


def test_movement_release_with_another_key_still_active_keeps_moving_state():
    scene = {
        "schema_version": 2,
        "id_namespace": "editor",
        "nodes": [
            {"id": "room", "node_type": "room", "states": {}},
            {"id": "agent", "node_type": "agent", "states": {}},
        ],
        "edges": [{"source_id": "room", "target_id": "agent", "relation": "at"}],
    }
    service = SimulationWorldService()
    started = service.start(SimulationStartRequest(source_json=scene, actor_id="agent"))
    service.dispatch(SimulationDispatchRequest(
        simulation_id=started.simulation_id,
        input="move_step",
        direction="1 0",
        elapsed_seconds=0.1,
        event={"event_id": "move-2", "sequence": 1, "event_type": "movement", "phase": "sampled"},
    ))
    released = service.dispatch(SimulationDispatchRequest(
        simulation_id=started.simulation_id,
        input="input_event",
        event={
            "event_id": "move-release-2",
            "sequence": 2,
            "event_type": "movement",
            "phase": "released",
            "payload": {"active_movement_keys": ["KeyD"]},
        },
    ))
    assert released.snapshot["world_state"]["agents"]["agent"]["moving"] is True
