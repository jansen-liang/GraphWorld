from backend.core.transitions import envelope_for_event, transition_log


def test_transition_envelope_is_versioned_and_preserves_legacy_event():
    event = {
        "step": 4,
        "type": "process_completed",
        "device_id": "washer",
        "output_id": "receipt_01",
    }
    envelope = envelope_for_event(event, 0)
    assert envelope["schema_version"] == 1
    assert envelope["source"] == "process"
    assert envelope["event_type"] == "process_completed"
    assert envelope["step_before"] == 3
    assert envelope["step_after"] == 4
    assert envelope["event"] == event
    assert envelope["transition_id"] == envelope_for_event(event, 0)["transition_id"]


def test_transition_log_is_deterministic_and_classifies_actions_and_time():
    events = [
        {"step": 0, "type": "robot_action", "action": {"action": "pick"}},
        {"step": 1, "type": "food_spoiled", "object_id": "food_01"},
    ]
    first = transition_log(events)
    second = transition_log(events)
    assert [item["transition_id"] for item in first] == [item["transition_id"] for item in second]
    assert first[0]["source"] == "action"
    assert second[1]["source"] == "timed_transition"
    assert second[1]["effects"]["object_id"] == "food_01"
