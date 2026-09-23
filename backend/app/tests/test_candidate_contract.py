from backend.app.runtime.graphworld_adapter import compact_candidate


def test_candidate_contract_is_exposed_as_first_class_api_field():
    candidate = compact_candidate({
        "agent": "robot_01",
        "action": "wait",
        "action_contract": {
            "category": "temporal",
            "parameters": ["agent"],
            "description": "Advance one simulation step.",
        },
    })

    payload = candidate.model_dump(mode="json")
    assert payload["action_contract"]["category"] == "temporal"
    assert payload["payload"]["action_contract"]["parameters"] == ["agent"]
