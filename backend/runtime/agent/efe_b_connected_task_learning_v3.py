"""Connected Goal-conditioned-B experiment with causal evidence filtering.

V2 updated an internal transition model, but its formula adapter omitted that
model when scoring candidates.  This isolated V3 adapter explicitly passes the
same learned model into every decomposition and selection call.

The optional task-only rule treats one-step ``maintain`` outcomes as correlated
null observations, not hundreds of independent transition samples.  The wait
transition remains the fixed identity prior; task and explore transitions keep
the standard Bayesian/Dirichlet update.
"""

from __future__ import annotations

import os
from typing import Any

from backend.runtime.agent.efe_agent.efe_scorer import (
    decompose_goal as base_decompose_goal,
)
from backend.runtime.agent.efe_agent.goal_transition_model import (
    HierarchicalGoalTransitionModel,
    goal_signature,
)
from backend.runtime.agent.efe_clean_entry_b_learning_v2 import (
    EfeCleanEntryBLearningV2Loop,
)


class CausalGoalTransitionModelV3(HierarchicalGoalTransitionModel):
    """B learner that can exclude temporally correlated null-action samples."""

    def __init__(self, *args: Any, learn_maintain: bool = False,
                 **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.learn_maintain = bool(learn_maintain)
        self.maintain_samples_skipped = 0

    def learn(self, goal: dict[str, Any], result: str,
              deviations: list[dict[str, Any]] | None = None, *,
              update: bool = True,
              target_issue_after: bool | None = None) -> dict[str, Any]:
        signature = goal_signature(goal)
        if signature.family == "maintain" and not self.learn_maintain:
            self.maintain_samples_skipped += 1
            self.last_update = {
                "goal_signature": signature.key,
                "result": result,
                "updated": False,
                "skipped": True,
                "skip_reason": "correlated_null_action",
            }
            return dict(self.last_update)
        return super().learn(
            goal,
            result,
            deviations,
            update=update,
            target_issue_after=target_issue_after,
        )

    def diagnostics(self) -> dict[str, Any]:
        result = super().diagnostics()
        result.update({
            "v3_learn_maintain": self.learn_maintain,
            "v3_maintain_samples_skipped": self.maintain_samples_skipped,
        })
        return result


class EfeBConnectedTaskLearningV3Loop(EfeCleanEntryBLearningV2Loop):
    """Clean-entry loop whose learned Goal-B is connected to V3 scoring."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        previous = self.goal_transition_model
        self.goal_transition_model = CausalGoalTransitionModelV3(
            A=previous.A,
            C=previous.C,
            root_strength=previous.root_strength,
            backoff_strength=previous.backoff_strength,
            learn_maintain=(
                os.environ.get("EFE_B_LEARN_MAINTAIN", "0") == "1"
            ),
        )

    def authority_diagnostics(self) -> dict[str, Any]:
        result = super().authority_diagnostics()
        result["b_connection_variant"] = "efe_b_connected_task_learning_v3"
        return result


def connected_decompose_goal_v3(
    goal: dict[str, Any],
    deviations: list[dict[str, Any]],
    world_belief: Any | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Score with the actual learned model; do not silently construct a new B."""
    efe_mode = str(kwargs.get("efe_mode") or "goal_conditioned_b")
    if efe_mode != "goal_conditioned_b":
        raise ValueError(
            "V3 connected scorer requires efe_mode=goal_conditioned_b, got "
            f"{efe_mode!r}")
    transition_model = kwargs.get("goal_transition_model")
    if transition_model is None:
        raise ValueError(
            "V3 connected scorer requires the live goal_transition_model")
    return base_decompose_goal(
        goal,
        deviations,
        world_belief,
        beta=float(kwargs.get("beta", 0.15)),
        efe_mode=efe_mode,
        outcome_model=kwargs.get("outcome_model"),
        goal_transition_model=transition_model,
    )


def connected_select_goal_v3(
    candidate_goals: list[dict[str, Any]],
    deviations: list[dict[str, Any]],
    memory: Any = None,
    world_belief: Any | None = None,
    step: int = 0,
    total_steps: int = 1600,
    **kwargs: Any,
) -> tuple[float, dict[str, Any]] | None:
    if not candidate_goals:
        return None
    scored = [
        (
            float(connected_decompose_goal_v3(
                goal, deviations, world_belief, **kwargs)["G"]),
            goal,
        )
        for goal in candidate_goals
    ]
    return min(scored, key=lambda item: item[0])


__all__ = [
    "CausalGoalTransitionModelV3",
    "EfeBConnectedTaskLearningV3Loop",
    "connected_decompose_goal_v3",
    "connected_select_goal_v3",
]
