from backend.runtime.action_conflicts import conflict_metrics


def test_conflict_metrics_report_shared_targets_and_objects_before_resolution():
    metrics = conflict_metrics([
        {"agent": "robot_01", "action": "press", "target": "washer_button"},
        {"agent": "robot_02", "action": "press", "target": "washer_button"},
        {"agent": "robot_01", "action": "pick", "object": "box"},
        {"agent": "robot_02", "action": "place", "object": "box"},
    ])

    assert metrics == {
        "action_conflict_count": 2,
        "action_conflict_groups": 2,
        "action_conflict_agents": 2,
        "action_conflict_targets": 1,
        "action_conflict_objects": 1,
    }
