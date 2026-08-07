"""Goal-conditioned outcome beliefs for high-level EFE selection.

The room-level A/B model can distinguish wait/explore/act, but it cannot tell
two concrete ``act`` goals apart.  This small Beta-Bernoulli model learns a
separate completion probability and duration for each semantic goal family.
It is deliberately independent from the executor and serialisable with the
rest of :class:`EfeLoop` state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


GOAL_FAMILIES = (
    "explore",
    "maintain",
    "restore_object",
    "clean_state",
    "return_supply",
    "dispose_waste",
    "laundry",
    "hospital_bed",
    "deliver_to_human",
    "generic_skill",
    "other",
)


def goal_family(goal: dict[str, Any] | None) -> str:
    """Map an executable GraphWorld goal to a learnable semantic family."""
    goal = goal or {}
    gtype = str(goal.get("type") or "")
    skill = str(goal.get("skill") or "").lower()
    task = str(goal.get("task") or "").lower()
    text = f"{skill} {task}"
    if gtype in {"explore", "patrol"}:
        return "explore"
    if gtype in {"maintain", "idle", "wait"}:
        return "maintain"
    if gtype in {"restore_initial_position", "restore", "patrol_restore"}:
        return "restore_object"
    if any(token in text for token in ("bed", "linen", "sheet")):
        return "hospital_bed"
    if any(token in text for token in ("waste", "dispose", "trash", "garbage")):
        return "dispose_waste"
    if any(token in text for token in ("laundry", "washer", "clothes", "towel", "blanket")):
        return "laundry"
    if any(token in text for token in ("deliver", "patient", "human")):
        return "deliver_to_human"
    if any(token in text for token in (
        "return_", "replenish", "restock", "medicine", "prescription", "wheelchair"
    )):
        return "return_supply"
    if any(token in text for token in ("clean", "brush", "empty_cup")):
        return "clean_state"
    if gtype == "skill" or skill:
        return "generic_skill"
    return "other"


def _digamma(value: float) -> float:
    """Stable positive-domain digamma approximation without scipy."""
    x = max(float(value), 1e-9)
    result = 0.0
    while x < 8.0:
        result -= 1.0 / x
        x += 1.0
    inv = 1.0 / x
    inv2 = inv * inv
    return result + math.log(x) - 0.5 * inv - inv2 * (
        1.0 / 12.0 - inv2 * (1.0 / 120.0 - inv2 / 252.0)
    )


def _binary_entropy(probability: float) -> float:
    p = min(1.0 - 1e-12, max(1e-12, float(probability)))
    return -p * math.log(p) - (1.0 - p) * math.log(1.0 - p)


@dataclass
class GoalFamilyBelief:
    """Beta completion belief plus an online duration mean."""

    success_alpha: float = 1.0
    failure_beta: float = 1.0
    duration_total: float = 8.0
    duration_weight: float = 1.0
    completions: int = 0
    failures: int = 0

    @property
    def success_probability(self) -> float:
        total = self.success_alpha + self.failure_beta
        return self.success_alpha / total if total > 0.0 else 0.5

    @property
    def mean_duration(self) -> float:
        return self.duration_total / max(self.duration_weight, 1e-9)

    def information_gain(self) -> float:
        """Mutual information I(theta; next Bernoulli outcome), in nats."""
        a = max(self.success_alpha, 1e-9)
        b = max(self.failure_beta, 1e-9)
        total = a + b
        mean = a / total
        expected_theta_log_theta = mean * (_digamma(a + 1.0) - _digamma(total + 1.0))
        expected_fail_log_fail = (1.0 - mean) * (
            _digamma(b + 1.0) - _digamma(total + 1.0)
        )
        return max(0.0, _binary_entropy(mean)
                   + expected_theta_log_theta + expected_fail_log_fail)

    def update(self, result: str, duration: int | float) -> None:
        if result == "completed":
            self.success_alpha += 1.0
            self.completions += 1
        elif str(result).startswith("failed"):
            self.failure_beta += 1.0
            self.failures += 1
        else:
            return
        self.duration_total += max(0.0, float(duration))
        self.duration_weight += 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success_alpha": self.success_alpha,
            "failure_beta": self.failure_beta,
            "duration_total": self.duration_total,
            "duration_weight": self.duration_weight,
            "completions": self.completions,
            "failures": self.failures,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GoalFamilyBelief":
        return cls(
            success_alpha=float(data.get("success_alpha", 1.0)),
            failure_beta=float(data.get("failure_beta", 1.0)),
            duration_total=float(data.get("duration_total", 8.0)),
            duration_weight=float(data.get("duration_weight", 1.0)),
            completions=int(data.get("completions", 0)),
            failures=int(data.get("failures", 0)),
        )


class GoalOutcomeModel:
    """Collection of per-family beliefs used by goal-conditioned EFE."""

    def __init__(self) -> None:
        self._families: dict[str, GoalFamilyBelief] = {
            family: GoalFamilyBelief() for family in GOAL_FAMILIES
        }

    def belief(self, goal_or_family: dict[str, Any] | str) -> GoalFamilyBelief:
        family = (goal_family(goal_or_family)
                  if isinstance(goal_or_family, dict) else str(goal_or_family))
        if family not in self._families:
            self._families[family] = GoalFamilyBelief()
        return self._families[family]

    def update(self, goal: dict[str, Any], result: str, duration: int | float) -> None:
        self.belief(goal).update(result, duration)

    def to_dict(self) -> dict[str, Any]:
        return {family: belief.to_dict()
                for family, belief in sorted(self._families.items())}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GoalOutcomeModel":
        model = cls()
        for family, raw in (data or {}).items():
            if isinstance(raw, dict):
                model._families[str(family)] = GoalFamilyBelief.from_dict(raw)
        return model


__all__ = ["GOAL_FAMILIES", "GoalFamilyBelief", "GoalOutcomeModel", "goal_family"]
