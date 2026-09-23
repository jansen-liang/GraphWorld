from backend.app.services.run_service import RunService


class _FakeAdapter:
    def candidate_by_id(self, orchestrator, *, visibility_mode, selected_action_id):
        return {
            "action": "place",
            "agent": "robot_01",
            "target": "slot",
            "object": "box",
        }


class _FakeRun:
    visibility_mode = "full"


class _FakeAdapterWithObservation(_FakeAdapter):
    def runtime_observation(self, orchestrator, *, visibility_mode):
        return {"nodes": [{"id": "slot"}]}


def test_human_action_payload_only_adds_geometry_hints(monkeypatch):
    service = object.__new__(RunService)
    monkeypatch.setattr(service, "_adapter_and_orchestrator", lambda run: (_FakeAdapter(), object()))
    selected = service._candidate_for_current_state(
        _FakeRun(),
        "place:slot:box",
        {
            "volume_anchor": [0.5, 0.5, 0.5],
            "action": "release",
            "target": "other",
        },
    )
    assert selected["action"] == "place"
    assert selected["target"] == "slot"
    assert selected["volume_anchor"] == [0.5, 0.5, 0.5]
    assert selected["object"] == "box"


def test_interaction_hit_is_allowed_only_for_the_server_selected_target(monkeypatch):
    service = object.__new__(RunService)
    monkeypatch.setattr(service, "_adapter_and_orchestrator", lambda run: (_FakeAdapterWithObservation(), object()))
    selected = service._candidate_for_current_state(
        _FakeRun(),
        "place:slot:box",
        {"interaction_hit": {"node_id": "slot", "surface_uv": [0.4, 0.6]}},
    )
    assert selected["interaction_hit"]["surface_uv"] == [0.4, 0.6]
