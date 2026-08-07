from __future__ import annotations

from backend.runtime.agent.efe_b_connected_task_learning_v3 import (
    CausalGoalTransitionModelV3,
    connected_decompose_goal_v3,
)


TASK_GOAL = {
    "type": "skill",
    "skill": "clean_exam_bed",
    "task": "clean_exam_bed exam_bed_clinic_1",
    "object": "exam_bed_clinic_1",
    "target": "exam_bed_clinic_1",
    "_candidate_source": "skill",
    "efe_family": "clean_state",
    "efe_target_class": "bed",
    "efe_workflow": "clean_exam_bed",
    "efe_domain": "hospital",
    "efe_signature": {
        "family": "clean_state",
        "target_class": "bed",
        "workflow": "clean_exam_bed",
        "domain": "hospital",
    },
}


def score(model: CausalGoalTransitionModelV3) -> dict:
    return connected_decompose_goal_v3(
        TASK_GOAL,
        [],
        None,
        efe_mode="goal_conditioned_b",
        goal_transition_model=model,
    )


def test_connected_scorer_consumes_learned_b() -> None:
    model = CausalGoalTransitionModelV3()
    before = score(model)
    for _ in range(12):
        model.learn(TASK_GOAL, "completed", [], target_issue_after=False)
    after = score(model)
    assert before["leaf_samples"] == 0.0
    assert after["leaf_samples"] > 0.0
    assert after["G"] != before["G"]


def test_task_only_model_skips_correlated_maintain() -> None:
    model = CausalGoalTransitionModelV3(learn_maintain=False)
    maintain = {
        "type": "maintain",
        "task": "maintain_order",
        "target": "lobby",
        "efe_family": "maintain",
        "efe_target_class": "room",
        "efe_workflow": "wait",
        "efe_domain": "hospital",
    }
    result = model.learn(maintain, "completed", [])
    assert result["skip_reason"] == "correlated_null_action"
    assert model.update_count == 0
    assert model.maintain_samples_skipped == 1


def test_all_outcome_control_can_learn_maintain() -> None:
    model = CausalGoalTransitionModelV3(learn_maintain=True)
    maintain = {
        "type": "maintain",
        "task": "maintain_order",
        "target": "lobby",
        "efe_family": "maintain",
        "efe_target_class": "room",
        "efe_workflow": "wait",
        "efe_domain": "hospital",
    }
    model.learn(maintain, "completed", [])
    assert model.update_count == 1
    assert model.maintain_samples_skipped == 0
