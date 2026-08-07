"""Hierarchical Goal-conditioned generative model for EFE goal selection.

This module keeps the learning rule inside the Active-Inference generative
model.  There is no learned scalar reward: a completed macro-goal contributes
evidence for the state transition that actually occurred,

    b^sigma_ij <- b^sigma_ij + Q(s_{t+1}=i, s_t=j | o_{t+1}, sigma)

and candidate goals are ranked only by risk + ambiguity under fixed A and C.

The transition model uses an explainable Dirichlet back-off hierarchy:

    action kind -> goal family -> target class -> full goal signature.

Sparse signatures therefore inherit their parent's transition probabilities;
with more observations their own posterior counts dominate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

try:
    from .efe_model import entropy, infer, kl_divergence, softmax
    from .goal_outcome_model import goal_family as legacy_goal_family
except ImportError:
    from efe_model import entropy, infer, kl_divergence, softmax
    from goal_outcome_model import goal_family as legacy_goal_family


STATE_NAMES = (
    "normal_unknown", "mild_unknown", "severe_unknown",
    "normal_known", "mild_known", "severe_known",
)
OBSERVATION_NAMES = ("unobserved", "low", "medium", "high")

# A[o, s] = P(o | s).  A and C are deliberately fixed in v1 so the learned
# versus frozen comparison isolates Goal-conditioned B learning.
DEFAULT_A = np.array([
    [0.85, 0.85, 0.85, 0.02, 0.02, 0.02],  # unobserved
    [0.12, 0.06, 0.02, 0.88, 0.15, 0.03],  # low urgency
    [0.02, 0.07, 0.05, 0.08, 0.70, 0.17],  # medium urgency
    [0.01, 0.02, 0.08, 0.02, 0.13, 0.78],  # high urgency
], dtype=float)

# P_C(o) is fixed before learning.  The log form is the conventional C table.
DEFAULT_PREFERENCE = np.array([0.08, 0.72, 0.15, 0.05], dtype=float)
DEFAULT_C = np.log(DEFAULT_PREFERENCE)


@dataclass(frozen=True)
class GoalSignature:
    """Stable, transferable semantic identity of a macro-goal."""

    family: str
    target_class: str
    workflow: str
    domain: str

    @property
    def action_kind(self) -> str:
        if self.family == "explore":
            return "explore"
        if self.family == "maintain":
            return "wait"
        return "task"

    @property
    def key(self) -> str:
        return "|".join((self.family, self.target_class,
                         self.workflow, self.domain))


def _node(scene: dict[str, Any] | None, node_id: str) -> dict[str, Any] | None:
    for item in (scene or {}).get("nodes") or []:
        if isinstance(item, dict) and str(item.get("id") or "") == node_id:
            return item
    return None


def _domain(scene: dict[str, Any] | None) -> str:
    name = str((scene or {}).get("scene_name") or "").lower()
    for value in ("hospital", "supermarket", "office", "factory"):
        if value in name:
            return value
    return "home" if name else "generic"


def _family(goal: dict[str, Any]) -> str:
    explicit = str(goal.get("efe_family") or "").strip().lower()
    if explicit:
        return explicit
    gtype = str(goal.get("type") or "").lower()
    skill = str(goal.get("skill") or "").lower()
    if gtype in {"explore", "patrol"}:
        return "explore"
    if gtype in {"maintain", "idle", "wait"}:
        return "maintain"
    if gtype in {"restore_initial_position", "restore", "patrol_restore"}:
        return "restore_object"
    if skill == "dispose_food" or "waste" in skill:
        return "dispose_waste"
    if skill == "laundry_clothes":
        return "laundry"
    if any(token in skill for token in ("linen", "sheet")):
        return "bed_linen"
    if skill in {"clean_waiting_area", "clean_exam_bed", "empty_cup"}:
        return "clean_state"
    family = legacy_goal_family(goal)
    return "bed_linen" if family == "hospital_bed" else family


def goal_signature(goal: dict[str, Any],
                   scene: dict[str, Any] | None = None,
                   baseline: dict[str, Any] | None = None) -> GoalSignature:
    """Build a structured signature without relying on free-form task text."""
    explicit = goal.get("efe_signature")
    if isinstance(explicit, dict):
        return GoalSignature(
            family=str(explicit.get("family") or _family(goal)),
            target_class=str(explicit.get("target_class") or "generic_target"),
            workflow=str(explicit.get("workflow") or "generic_workflow"),
            domain=str(explicit.get("domain") or "generic"),
        )

    object_id = str(goal.get("object") or "")
    target_id = str(goal.get("target") or "")
    target_node = (_node(scene, object_id) or _node(baseline, object_id)
                   or _node(scene, target_id) or _node(baseline, target_id) or {})
    target_class = str(target_node.get("semantic_type") or "").lower()
    if not target_class:
        target_class = "room" if _family(goal) == "explore" else "generic_target"

    gtype = str(goal.get("type") or "").lower()
    skill = str(goal.get("skill") or "").lower()
    workflow = skill or {
        "restore_initial_position": "direct_restore",
        "restore": "direct_restore",
        "patrol_restore": "direct_restore",
        "explore": "inspect_room",
        "patrol": "inspect_room",
        "maintain": "wait",
        "idle": "wait",
        "wait": "wait",
    }.get(gtype, gtype or "generic_workflow")

    return GoalSignature(
        family=_family(goal), target_class=target_class,
        workflow=workflow, domain=_domain(scene or baseline),
    )


def enrich_goal_signature(goal: dict[str, Any],
                          scene: dict[str, Any] | None = None,
                          baseline: dict[str, Any] | None = None,
                          ) -> dict[str, Any]:
    enriched = dict(goal)
    signature = goal_signature(enriched, scene, baseline)
    enriched["efe_family"] = signature.family
    enriched["efe_target_class"] = signature.target_class
    enriched["efe_workflow"] = signature.workflow
    enriched["efe_domain"] = signature.domain
    enriched["efe_signature"] = asdict(signature)
    return enriched


def _credit_target_ids(goal: dict[str, Any]) -> set[str]:
    """Entities whose condition the executed Goal can causally change.

    For structured task Goals, ``object`` is the problem-bearing entity while
    ``target`` is commonly only its destination (sink, cabinet, room, ...).
    Goals without an object use their target as the affected entity.
    """
    object_id = str(goal.get("object") or "")
    if object_id:
        return {object_id}
    target_id = str(goal.get("target") or "")
    return {target_id} if target_id else set()


def _matched_urgency(goal: dict[str, Any],
                     deviations: list[dict[str, Any]] | None,
                     *, include_rooms: bool) -> tuple[bool, float]:
    targets = _credit_target_ids(goal)
    rooms = {
        str(goal.get(key) or "")
        for key in ("room", "object_room", "target_room")
        if str(goal.get(key) or "")
    }
    matched = False
    urgency = 0.0
    for deviation in deviations or []:
        node_id = str(deviation.get("node_id") or "")
        room = str(deviation.get("room") or "")
        if node_id in targets or (include_rooms and room and room in rooms):
            matched = True
            urgency = max(urgency, float(deviation.get("urgency", 0.0)))
    return matched, urgency


def _base_transition(action_kind: str) -> np.ndarray:
    """Weak, auditable prior B for task/explore/wait macro-actions."""
    B = np.zeros((6, 6), dtype=float)
    if action_kind == "wait":
        return np.eye(6, dtype=float)
    if action_kind == "explore":
        for condition in range(3):
            B[condition, condition] = 0.20
            B[condition + 3, condition] = 0.80
            B[condition + 3, condition + 3] = 1.0
        return B

    # Generic task prior: a macro-action often improves a deviated condition,
    # but the prior remains deliberately weak and is replaced by evidence.
    condition_transition = np.array([
        [0.90, 0.55, 0.35],
        [0.08, 0.40, 0.40],
        [0.02, 0.05, 0.25],
    ], dtype=float)
    for source in range(6):
        source_condition = source % 3
        known_probability = 0.98 if source >= 3 else 0.90
        for next_condition in range(3):
            p = condition_transition[next_condition, source_condition]
            B[next_condition, source] += p * (1.0 - known_probability)
            B[next_condition + 3, source] += p * known_probability
    return B


class HierarchicalGoalTransitionModel:
    """Fixed A/C plus hierarchical Dirichlet posteriors over B^sigma."""

    def __init__(self, *, A: np.ndarray | None = None,
                 C: np.ndarray | None = None,
                 root_strength: float = 6.0,
                 backoff_strength: float = 8.0) -> None:
        self.A = np.asarray(DEFAULT_A if A is None else A, dtype=float)
        self.C = np.asarray(DEFAULT_C if C is None else C, dtype=float)
        self.root_strength = float(root_strength)
        self.backoff_strength = float(backoff_strength)
        self.counts: dict[str, np.ndarray] = {}
        self.update_count = 0
        self.observation_count = 0
        self.prequential_nll: list[float] = []
        # Per-goal-family prequential NLL, so maintain/explore fitting can be
        # separated from task-family learning.  Recorded for Frozen too (it
        # evaluates the same predictions, update=False only skips counts).
        self.prequential_nll_by_family: dict[str, list[float]] = {}
        self.last_update: dict[str, Any] = {}

    @staticmethod
    def _level_keys(signature: GoalSignature) -> tuple[str, str, str, str]:
        return (
            "kind:%s" % signature.action_kind,
            "family:%s" % signature.family,
            "target:%s|%s" % (signature.family, signature.target_class),
            "signature:%s" % signature.key,
        )

    def _evidence(self, key: str) -> np.ndarray:
        if key not in self.counts:
            self.counts[key] = np.zeros((6, 6), dtype=float)
        return self.counts[key]

    def transition_with_counts(self, goal: dict[str, Any]
                               ) -> tuple[np.ndarray, np.ndarray, GoalSignature]:
        signature = goal_signature(goal)
        keys = self._level_keys(signature)
        root_counts = self.root_strength * _base_transition(signature.action_kind)
        effective = root_counts + self._evidence(keys[0])
        B = effective / np.where(effective.sum(axis=0, keepdims=True) > 0.0,
                                 effective.sum(axis=0, keepdims=True), 1.0)
        for key in keys[1:]:
            effective = self.backoff_strength * B + self._evidence(key)
            B = effective / np.where(effective.sum(axis=0, keepdims=True) > 0.0,
                                     effective.sum(axis=0, keepdims=True), 1.0)
        return B, effective, signature

    def transition(self, goal: dict[str, Any]) -> np.ndarray:
        return self.transition_with_counts(goal)[0]

    @staticmethod
    def state_prior(goal: dict[str, Any],
                    deviations: list[dict[str, Any]] | None = None,
                    world_belief: Any | None = None) -> np.ndarray:
        """Q(s) for this candidate from target urgency and knowledge state."""
        signature = goal_signature(goal)
        # Task Goals use only the entity they can causally affect.  Room-level
        # deviations belong to explore/maintain and must not contaminate a
        # restore/clean Goal merely because both happen in the same room.
        _matched, urgency = _matched_urgency(
            goal, deviations,
            include_rooms=signature.family in {"explore", "maintain"},
        )
        issue_before = goal.get("_efe_target_issue_before")
        if (signature.action_kind == "task" and issue_before is True
                and urgency <= 0.0):
            urgency = 1.0

        # A maintain/wait policy acts on the whole currently available world,
        # not only on the robot's present room.  If structured task candidates
        # are pending, its starting state cannot be labelled "normal" merely
        # because the local room is quiet.  This is a state inference input to
        # Q(s_t), not a reward or an additive policy penalty.
        pending_tasks = int(goal.get("_pending_task_count", 0) or 0)
        if signature.family in {"explore", "maintain"} and pending_tasks > 0:
            urgency = max(
                urgency,
                max((float(item.get("urgency", 0.0))
                     for item in (deviations or [])), default=0.0),
            )

        if urgency >= 5.0:
            condition = np.array([0.05, 0.20, 0.75])
        elif urgency > 0.0:
            condition = np.array([0.15, 0.70, 0.15])
        elif signature.family in {"explore", "maintain"} and pending_tasks > 0:
            condition = np.array([0.10, 0.75, 0.15])
        elif signature.family == "explore":
            room = str(goal.get("target_room") or goal.get("room") or "")
            risk = 0.35
            try:
                if world_belief is not None and room and room in world_belief:
                    risk = float(world_belief[room].risk_confidence)
            except (KeyError, AttributeError, TypeError, ValueError):
                pass
            risk = min(0.90, max(0.05, risk))
            condition = np.array([1.0 - risk, 0.65 * risk, 0.35 * risk])
        elif str(goal.get("_candidate_source") or "") in {
            "pipeline", "pipeline_skill", "skill", "llm"
        }:
            condition = np.array([0.15, 0.70, 0.15])
        else:
            condition = np.array([0.85, 0.10, 0.05])
        condition = condition / condition.sum()

        unknown = (signature.family == "explore"
                   and int(goal.get("_visit_count", 0) or 0) <= 0)
        p_known = 0.10 if unknown else 0.95
        prior = np.concatenate((condition * (1.0 - p_known),
                                condition * p_known))
        return prior / prior.sum()

    def score(self, goal: dict[str, Any],
              deviations: list[dict[str, Any]] | None = None,
              world_belief: Any | None = None) -> dict[str, Any]:
        B, effective_counts, signature = self.transition_with_counts(goal)
        prior_raw = goal.get("_efe_state_prior")
        prior = (np.asarray(prior_raw, dtype=float)
                 if isinstance(prior_raw, (list, tuple, np.ndarray))
                 else self.state_prior(goal, deviations, world_belief))
        predicted_state = B @ prior
        predicted_observation = self.A @ predicted_state
        preference = softmax(self.C)
        risk = kl_divergence(predicted_observation, preference)
        ambiguity = float(np.dot(predicted_state, entropy(self.A, axis=0)))

        alpha0 = effective_counts.sum(axis=0, keepdims=True)
        variance = (effective_counts * (alpha0 - effective_counts)
                    / np.where(alpha0 > 0.0,
                               alpha0 * alpha0 * (alpha0 + 1.0), 1.0))
        parameter_uncertainty = float(np.mean(np.sum(variance, axis=0)))
        levels = self._level_keys(signature)
        leaf_samples = float(self._evidence(levels[-1]).sum())
        return {
            "goal_signature": signature.key,
            "goal_family": signature.family,
            "risk": risk,
            "ambiguity": ambiguity,
            "parameter_uncertainty": parameter_uncertainty,
            "leaf_samples": leaf_samples,
            "predicted_observation": {
                name: float(value)
                for name, value in zip(OBSERVATION_NAMES, predicted_observation)
            },
            "G": risk + ambiguity,
        }

    @staticmethod
    def observation_index(goal: dict[str, Any], result: str,
                          deviations: list[dict[str, Any]] | None = None, *,
                          target_issue_after: bool | None = None) -> int:
        signature = goal_signature(goal)
        is_task = signature.action_kind == "task"
        matched, urgency = _matched_urgency(
            goal, deviations, include_rooms=not is_task)

        # A task posterior is the condition of its own affected entity after
        # execution.  The detector result is preferred because visible
        # deviations may be top-k truncated or partially observed.
        if is_task:
            if target_issue_after is False:
                return 1
            if target_issue_after is True:
                return 3 if urgency >= 5.0 else 2
            if urgency >= 5.0:
                return 3
            if matched or result.startswith("failed"):
                return 2
            if result == "completed":
                return 1
            return 0

        # Non-repair goals do not earn credit for observing one quiet room
        # while known work remains elsewhere.  Their posterior observation is
        # global because their causal claim is effectively "the world can be
        # left alone / inspected instead of repairing it".
        if (signature.family in {"explore", "maintain"}
                and int(goal.get("_pending_task_count", 0) or 0) > 0
                and deviations):
            matched = True
            urgency = max(
                urgency,
                max(float(item.get("urgency", 0.0))
                    for item in deviations),
            )
        if urgency >= 5.0:
            return 3
        if matched:
            return 2
        if result == "completed":
            return 1
        return 0

    def learn(self, goal: dict[str, Any], result: str,
              deviations: list[dict[str, Any]] | None = None, *,
              update: bool = True,
              target_issue_after: bool | None = None) -> dict[str, Any]:
        """Score one observed transition, optionally updating B.

        ``update=False`` is the Frozen control: it records the same
        prequential prediction error but leaves every Dirichlet count intact.
        """
        B, _effective, signature = self.transition_with_counts(goal)
        prior_raw = goal.get("_efe_state_prior")
        prior = (np.asarray(prior_raw, dtype=float)
                 if isinstance(prior_raw, (list, tuple, np.ndarray))
                 else self.state_prior(goal, deviations))
        observation = self.observation_index(
            goal, result, deviations,
            target_issue_after=target_issue_after)
        predicted = B @ prior
        predicted_observation = self.A @ predicted
        predictive_probability = max(
            1e-12, float(predicted_observation[observation]))
        predictive_nll = float(-np.log(predictive_probability))
        self.observation_count += 1
        self.prequential_nll.append(predictive_nll)
        self.prequential_nll_by_family.setdefault(
            signature.family, []).append(predictive_nll)
        posterior = infer(self.A, predicted, observation)

        # xi_ij proportional to A[o,i] B_ij q_t(j), normalized jointly.
        xi = self.A[observation, :, None] * B * prior[None, :]
        total = float(xi.sum())
        if total > 0.0:
            xi /= total
        else:
            xi = np.outer(posterior, prior)
        if update:
            for key in self._level_keys(signature):
                self._evidence(key)[:] += xi
            self.update_count += 1
        self.last_update = {
            "goal_signature": signature.key,
            "result": result,
            "observation": OBSERVATION_NAMES[observation],
            "credit_assignment": (
                "target_condition" if signature.action_kind == "task"
                else "environment_condition"
            ),
            "target_issue_before": goal.get("_efe_target_issue_before"),
            "target_issue_after": target_issue_after,
            "updated": bool(update),
            "predictive_probability": predictive_probability,
            "prequential_nll": predictive_nll,
            "prior": prior.tolist(),
            "posterior": posterior.tolist(),
            "transition_evidence": xi.tolist(),
        }
        return dict(self.last_update)

    def diagnostics(self) -> dict[str, Any]:
        signature_keys = [key for key in self.counts if key.startswith("signature:")]
        recent = self.prequential_nll[-20:]
        return {
            "updates": self.update_count,
            "observations": self.observation_count,
            "mean_prequential_nll": (
                float(np.mean(self.prequential_nll))
                if self.prequential_nll else 0.0
            ),
            "recent_20_prequential_nll": (
                float(np.mean(recent)) if recent else 0.0
            ),
            "family_nll": {
                family: {
                    "count": len(vals),
                    "mean": float(np.mean(vals)),
                    "recent_20": (float(np.mean(vals[-20:]))
                                  if vals else 0.0),
                }
                for family, vals in sorted(
                    self.prequential_nll_by_family.items())
            },
            "learned_signatures": len([
                key for key in signature_keys if float(self.counts[key].sum()) > 0.0
            ]),
            "signature_samples": {
                key.removeprefix("signature:"): float(self.counts[key].sum())
                for key in sorted(signature_keys)
                if float(self.counts[key].sum()) > 0.0
            },
            "last_update": dict(self.last_update),
            "state_names": list(STATE_NAMES),
            "observation_names": list(OBSERVATION_NAMES),
            "preference": softmax(self.C).tolist(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "A": self.A.tolist(), "C": self.C.tolist(),
            "root_strength": self.root_strength,
            "backoff_strength": self.backoff_strength,
            "counts": {key: value.tolist() for key, value in self.counts.items()},
            "update_count": self.update_count,
            "observation_count": self.observation_count,
            "prequential_nll": list(self.prequential_nll),
            "prequential_nll_by_family": {
                family: list(vals)
                for family, vals in self.prequential_nll_by_family.items()
            },
            "last_update": dict(self.last_update),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HierarchicalGoalTransitionModel":
        model = cls(
            A=np.asarray(data.get("A", DEFAULT_A), dtype=float),
            C=np.asarray(data.get("C", DEFAULT_C), dtype=float),
            root_strength=float(data.get("root_strength", 6.0)),
            backoff_strength=float(data.get("backoff_strength", 8.0)),
        )
        model.counts = {
            str(key): np.asarray(value, dtype=float)
            for key, value in (data.get("counts") or {}).items()
        }
        model.update_count = int(data.get("update_count", 0))
        model.observation_count = int(data.get(
            "observation_count", len(data.get("prequential_nll") or [])))
        model.prequential_nll = [
            float(value) for value in data.get("prequential_nll") or []
        ]
        model.prequential_nll_by_family = {
            str(family): [float(value) for value in vals]
            for family, vals in (
                data.get("prequential_nll_by_family") or {}).items()
        }
        model.last_update = dict(data.get("last_update") or {})
        return model


__all__ = [
    "STATE_NAMES", "OBSERVATION_NAMES", "DEFAULT_A", "DEFAULT_C",
    "GoalSignature", "goal_signature", "enrich_goal_signature",
    "HierarchicalGoalTransitionModel",
]
