"""Independent, auditable EFE formula variants for long-run experiments.

The stale-room variants model unobserved room drift as a symmetric two-state
Markov process.  Exploration value is the mutual information I(S; O) under
the predicted room belief, rather than an ad-hoc visit bonus.
"""

from __future__ import annotations

import math
import os
from typing import Any

from backend.runtime.agent.efe_agent.efe_scorer import (
    compute_goal_conditioned_efe,
    decompose_goal as base_decompose_goal,
)
from backend.runtime.agent.efe_agent.goal_outcome_model import (
    GoalOutcomeModel,
    goal_family,
)
from backend.runtime.agent.efe_goal_conditioned_safe_maintain_v1 import (
    EfeGoalConditionedSafeMaintainV1Loop,
)


FORMULA_VARIANTS = {
    "global_ab",
    "goal_conditioned_current",
    "null_fixed",
    "stale_h005",
    "stale_h020",
}

# Same likelihood semantics as graphworld_model(): columns are
# [needs_attention, normal], rows are [low, medium, high] urgency.
OBSERVATION_MODEL = (
    (0.30, 0.80),
    (0.40, 0.15),
    (0.30, 0.05),
)
HAZARD_BY_VARIANT = {
    "stale_h005": 0.005,
    "stale_h020": 0.020,
}


def _entropy(probabilities: list[float] | tuple[float, ...]) -> float:
    return -sum(p * math.log(p) for p in probabilities if p > 0.0)


def predicted_room_risk(current_risk: float, elapsed_steps: int,
                        hazard: float) -> float:
    """Predict P(needs_attention) after unobserved symmetric state drift.

    With transition matrix [[1-h, h], [h, 1-h]], the closed form is
    q_t = 1/2 + (q_0 - 1/2)(1 - 2h)^t.
    """
    q0 = min(1.0, max(0.0, float(current_risk)))
    elapsed = max(0, int(elapsed_steps))
    h = min(0.499999, max(0.0, float(hazard)))
    return 0.5 + (q0 - 0.5) * ((1.0 - 2.0 * h) ** elapsed)


def room_observation_information_gain(predicted_risk: float) -> float:
    """Exact I(S;O)=H(O)-E_s[H(O|s)] for the fixed likelihood A."""
    q = min(1.0, max(0.0, float(predicted_risk)))
    state_distribution = (q, 1.0 - q)
    observation_distribution = tuple(
        row[0] * q + row[1] * (1.0 - q) for row in OBSERVATION_MODEL
    )
    conditional_entropy = sum(
        state_distribution[state] * _entropy(tuple(row[state] for row in OBSERVATION_MODEL))
        for state in (0, 1)
    )
    return max(0.0, _entropy(observation_distribution) - conditional_entropy)


class NoMaintainLearningGoalOutcomeModel(GoalOutcomeModel):
    """Treat the null/maintain action as a baseline, not a success task."""

    def update(self, goal: dict[str, Any], result: str,
               duration: int | float) -> None:
        if goal_family(goal) == "maintain":
            return
        super().update(goal, result, duration)


def formula_decomposition(
    goal: dict[str, Any],
    deviations: list[dict[str, Any]],
    world_belief: Any | None = None,
    *,
    variant: str,
    outcome_model: GoalOutcomeModel | None = None,
    efe_mode: str = "goal_conditioned",
    **kwargs: Any,
) -> dict[str, Any]:
    """Return an auditable score breakdown for one configured variant."""
    if variant in {"global_ab", "goal_conditioned_current"}:
        # ``select_goal`` carries legacy scheduling arguments such as ``tau``
        # and ``total_steps``.  They are accepted by the selection API but are
        # not inputs to the generative A/B/C equation, so do not leak them into
        # ``compute_efe_generative`` through decompose_goal's **kwargs.
        return base_decompose_goal(
            goal, deviations, world_belief,
            beta=float(kwargs.get("beta", 0.15)),
            efe_mode=efe_mode,
            outcome_model=outcome_model,
        )

    result = compute_goal_conditioned_efe(
        goal, deviations, world_belief, outcome_model)
    family = goal_family(goal)
    if family == "maintain":
        # A null action has zero incremental utility.  It is selected only
        # when every instrumental action has non-negative expected value.
        result.update({
            "information_gain": 0.0,
            "failure_risk": 0.0,
            "distance_cost": 0.0,
            "duration_cost": 0.0,
            "revisit_cost": 0.0,
            "switch_cost": 0.0,
            "G": 0.0,
            "formula_variant": variant,
        })
        return result

    if family == "explore" and variant in HAZARD_BY_VARIANT:
        room = str(goal.get("target_room") or goal.get("room")
                   or goal.get("target") or "")
        risk = 0.5
        if world_belief is not None and room and room in world_belief:
            risk = float(world_belief[room].risk_confidence)
        elapsed = max(0, int(goal.get("_steps_since_visit", 0) or 0))
        predicted_risk = predicted_room_risk(
            risk, elapsed, HAZARD_BY_VARIANT[variant])
        information_gain = room_observation_information_gain(predicted_risk)
        # Revisit count is deliberately absent: environmental process noise,
        # not a hand-written patrol cooldown, restores epistemic value.
        result.update({
            "predicted_room_risk": predicted_risk,
            "steps_since_visit": elapsed,
            "hazard": HAZARD_BY_VARIANT[variant],
            "information_gain": information_gain,
            "revisit_cost": 0.0,
        })
        result["G"] = (
            float(result["distance_cost"])
            + float(result["duration_cost"])
            - information_gain
        )
    result["formula_variant"] = variant
    return result


class EfeFormulaStalenessV1Loop(EfeGoalConditionedSafeMaintainV1Loop):
    """Safe-maintain loop enriched with elapsed-observation-time features."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.formula_variant = os.environ.get(
            "EFE_FORMULA_VARIANT", "goal_conditioned_current")
        if self.formula_variant not in FORMULA_VARIANTS:
            raise ValueError(f"unsupported formula variant: {self.formula_variant}")
        self._formula_step = 0
        super().__init__(*args, **kwargs)
        if self.formula_variant in {"null_fixed", *HAZARD_BY_VARIANT}:
            self.goal_outcome_model = NoMaintainLearningGoalOutcomeModel()

    def _enrich_goal_decision_features(
        self, goal: dict[str, Any], robot_room: str,
    ) -> dict[str, Any]:
        enriched = super()._enrich_goal_decision_features(goal, robot_room)
        destination = str(
            enriched.get("target_room") or enriched.get("room")
            or enriched.get("target") or ""
        )
        last_visit = self._room_last_visited.get(destination)
        enriched["_steps_since_visit"] = (
            self.total_steps if last_visit is None
            else max(0, self._formula_step - int(last_visit))
        )
        return enriched

    def authority_diagnostics(self) -> dict[str, Any]:
        diagnostics = super().authority_diagnostics()
        diagnostics["formula_variant"] = self.formula_variant
        diagnostics["maintain_outcome_learning"] = (
            self.formula_variant not in {"null_fixed", *HAZARD_BY_VARIANT}
        )
        return diagnostics

    def step(self, observation: dict[str, Any], candidates: list[dict[str, Any]],
             step: int, **kwargs: Any) -> dict[str, Any]:
        self._formula_step = int(step)
        return super().step(observation, candidates, step, **kwargs)


def configured_decompose_goal(
    goal: dict[str, Any], deviations: list[dict[str, Any]],
    world_belief: Any | None = None, **kwargs: Any,
) -> dict[str, Any]:
    variant = os.environ.get("EFE_FORMULA_VARIANT", "goal_conditioned_current")
    return formula_decomposition(
        goal, deviations, world_belief, variant=variant, **kwargs)


def configured_select_goal(
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
        (float(configured_decompose_goal(
            goal, deviations, world_belief, **kwargs)["G"]), goal)
        for goal in candidate_goals
    ]
    return min(scored, key=lambda item: item[0])


__all__ = [
    "EfeFormulaStalenessV1Loop",
    "NoMaintainLearningGoalOutcomeModel",
    "configured_decompose_goal",
    "configured_select_goal",
    "predicted_room_risk",
    "room_observation_information_gain",
]
