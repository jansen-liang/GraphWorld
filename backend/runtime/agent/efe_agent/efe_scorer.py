"""EFE Scorer — Expected Free Energy goal selection.

G(g) = -(P(g) + E(g) + beta * N(g))            (phase-1 hybrid scorer)
  P(g) = pragmatic: preference-weighted urgency of covered deviations, normed to [0,1)
  E(g) = epistemic: mean *belief entropy* of the rooms the goal visits (Beta variance)
  N(g) = novelty:   bonus for rooms not yet tracked by WorldBelief
  beta = fixed novelty coefficient

The true generative-model score is also available:
  G(g) = risk + ambiguity                          (efe_mode="generative")
where risk = KL(predicted observation || preference) and ambiguity is the
expected entropy of the observation model — both from the same A/B/C tables
(see efe_model.py).  No exploration scheduler, no scalar preference weights:
`alpha` was deleted (handoff §1.3 / §2.3 #4).

Changes vs the previous scorer:
  - E(g) reads WorldBelief Beta variance, NOT memory staleness (#2).
  - STATE_KEY_WEIGHT became C preference log-coefficients; the effective
    weight is softmax(C) — a distribution, not scalar weights (#3).
  - compute_alpha() removed; exploration is endogenous through entropy (#4).
"""

from __future__ import annotations

from typing import Any

import numpy as np

try:
    from .efe_model import GenerativeModel, graphworld_model, kl_divergence
    from .goal_outcome_model import GoalOutcomeModel, goal_family
    from .goal_transition_model import HierarchicalGoalTransitionModel
except ImportError:
    from efe_model import GenerativeModel, graphworld_model, kl_divergence
    from goal_outcome_model import GoalOutcomeModel, goal_family
    from goal_transition_model import HierarchicalGoalTransitionModel


# ============================================================
# C preference distribution over deviation types
# ============================================================
# Deviation-type *preference* log-coefficients, keyed by the engine's
# BAD_STATE_KEYS + "parent".  softmax(C) is the preference distribution
# P_pref — "C 必须是分布，不是标量权重" (handoff §1.1).
#
# Values are derived from the old TYPE_WEIGHT priorities: C[key] = ln(weight).
# The distribution keeps the same ordering while exposing it as a proper
# probability that the pragmatic term (a KL against preference) can consume.
STATE_KEY_PREFERENCE_LOG: dict[str, float] = {
    # ── NPC precondition states (all ln(1.0) = 0.0) ──
    "is_dirty":   0.0,
    "is_wet":     0.0,
    "folded":     0.0,
    "is_open":    0.0,
    "parent":     0.0,
    # ── NPC side-effect states (ranked by hazard) ──
    "is_burnt":   0.0,            # ln(1.0)
    "is_rotten":  -0.1053605,     # ln(0.9)
    "is_full":    -0.3566749,     # ln(0.7)
    "fill_level": -0.6931472,     # ln(0.5)
}

DEFAULT_TAU: int = 50        # kept for API compatibility; no longer used
DEFAULT_BETA: float = 0.15
_PREFERENCE_CACHE: dict[str, float] | None = None
_PREFERENCE_MEAN: float | None = None


def preference_distribution() -> tuple[dict[str, float], float]:
    """softmax(STATE_KEY_PREFERENCE_LOG) plus its mean (fallback for unknown keys).

    Cached: the key set is fixed at import time.
    """
    global _PREFERENCE_CACHE, _PREFERENCE_MEAN
    if _PREFERENCE_CACHE is None:
        keys = list(STATE_KEY_PREFERENCE_LOG)
        C = np.array([STATE_KEY_PREFERENCE_LOG[k] for k in keys], dtype=float)
        p = softmax_local(C)
        _PREFERENCE_CACHE = {k: float(v) for k, v in zip(keys, p)}
        _PREFERENCE_MEAN = float(np.mean(p))
    return _PREFERENCE_CACHE, _PREFERENCE_MEAN


def softmax_local(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    e = np.exp(x - np.max(x))
    return e / np.sum(e)


def _state_key_weight(state_key: str) -> float:
    """Preference weight for a deviation type (P_pref[key], mean for unknown)."""
    pref, mean = preference_distribution()
    return pref.get(state_key, mean)


# ============================================================
# pragmatic term (phase-1 hybrid: preference-weighted urgency)
# ============================================================

def _room_boost(world_belief: Any, room_id: str) -> float:
    """WorldBelief status inflates/deflates the urgency of a deviation."""
    if world_belief is None or not room_id:
        return 1.0
    try:
        rb = world_belief[room_id]
        if rb.status == "high_risk":
            return 1.3
        if rb.status == "safe":
            return 0.7
    except (KeyError, AttributeError):
        pass
    return 1.0


def compute_pragmatic(goal: dict[str, Any],
                      deviations: list[dict[str, Any]],
                      world_belief: Any | None = None) -> float:
    """P(g) = preference-weighted urgency of deviations covered by *goal*.

    mass = Σ urgency · softmax(C)[state_key] · room_boost
    P    = mass / (1 + mass)         # monotone, normalised to [0, 1)

    Normalising aligns P with the epistemic term's [0, 1] scale (handoff
    §1.3 "量纲一致") while preserving the dominance of large-urgency hazards.
    """
    goal_obj = str(goal.get("object") or goal.get("target") or "")
    goal_room = str(goal.get("target_room") or goal.get("room") or "")

    mass = 0.0
    for d in deviations or []:
        d_node = str(d.get("node_id") or "")
        d_room = str(d.get("room") or "")
        if not (d_node == goal_obj or d_room == goal_room):
            continue
        state_key = str(d.get("state_key") or "")
        weight = _state_key_weight(state_key)
        urgency = float(d.get("urgency", 0.0))
        boost = _room_boost(world_belief, d_room)
        mass += urgency * weight * boost

    return mass / (1.0 + mass)


# ============================================================
# epistemic term — belief entropy, not staleness
# ============================================================

def _goal_rooms(goal: dict[str, Any]) -> list[str]:
    """Room ids this goal will visit (deduplicated, order-preserving)."""
    rooms: list[str] = []
    for key in ("target_room", "room", "source_room", "dest_room", "object_room"):
        v = goal.get(key)
        if v:
            rooms.append(str(v))
    return list(dict.fromkeys(rooms))


def compute_epistemic(goal: dict[str, Any],
                      world_belief: Any | None = None,
                      memory: Any = None,
                      step: int = 0,
                      tau: int = DEFAULT_TAU) -> float:
    """E(g) = mean belief entropy of the rooms the goal visits.

    Information gain is measured by the Beta-posterior variance
    (RoomBelief.room_entropy()), NOT by memory staleness: a room can be stale
    yet certain (just visited, saturated belief) or fresh yet uncertain
    (mixed evidence).  Unknown rooms get 1.0 = maximum entropy, which makes
    exploration endogenous — no alpha scheduler needed.
    """
    rooms = _goal_rooms(goal)
    if not rooms:
        return 0.0
    vals = []
    for r in rooms:
        if world_belief is not None and r in world_belief:
            vals.append(world_belief[r].room_entropy())
        else:
            vals.append(1.0)
    return sum(vals) / len(vals)


# ============================================================
# novelty term
# ============================================================

def compute_novelty(goal: dict[str, Any],
                    world_belief: Any | None = None) -> float:
    """N(g) = count of goal rooms not yet tracked by WorldBelief."""
    if world_belief is None:
        return 0.0
    rooms = _goal_rooms(goal)
    if not rooms:
        return 0.0
    return sum(1 for r in rooms if r not in world_belief)


# ============================================================
# true generative-model EFE (phase 2)
# ============================================================

def goal_action_index(goal: dict[str, Any]) -> int:
    """Map a GraphWorld goal onto the generative model's action axis.

      explore / patrol           -> 1 (explore, BS-like)
      skill / restore / fix      -> 2 (act, DS-like)
      anything else              -> 0 (wait, DA-like)

    Shared by generative scoring AND by the B-transition learner, so the
    action a goal executed is the same action a whose transition slice gets
    updated (Phase 3 structured transition counts by goal type).
    """
    gtype = str(goal.get("type") or goal.get("skill") or "")
    if gtype in ("explore", "patrol"):
        return 1
    if gtype in ("skill", "restore_initial_position", "fix", "restore",
                 "patrol_restore"):
        return 2
    return 0


def compute_efe_generative(goal: dict[str, Any],
                           deviations: list[dict[str, Any]] | None = None,
                           world_belief: Any | None = None,
                           step: int = 0,
                           model: GenerativeModel | None = None,
                           gamma: float = 1.0) -> tuple[float, float, float]:
    """(risk, ambiguity, G) for one goal, from the A/B/C generative model.

    The goal maps onto the model through:
      prior  Q0 = [risk_confidence(room), 1 - risk_confidence(room)]  — WorldBelief
      action a = goal_action_index(goal)
    Urgency enters through the belief: thinker_post raises a room's
    risk_confidence when deviations are observed, which tilts Q0 toward
    needs_attention and makes the fixing goal's predicted observation match
    the preference (low urgency).  Risk and ambiguity share one generative
    model, so no weighting coefficient is applied (1.8: the formula is only
    rational *given* the model — the model itself is corrected by Dirichlet
    learning and defined by the designer).
    """
    if model is None:
        model = graphworld_model(gamma=gamma)

    room = str(goal.get("target_room") or goal.get("room")
               or goal.get("object_room") or "")
    conf = 0.5
    if world_belief is not None and room and room in world_belief:
        conf = world_belief[room].risk_confidence
    Q_prior = np.array([conf, 1.0 - conf], dtype=float)

    return model.efe(goal_action_index(goal), Q_prior)


# ============================================================
# goal-conditioned EFE (semantic outcome learning)
# ============================================================

def _goal_need(goal: dict[str, Any],
               deviations: list[dict[str, Any]] | None) -> float:
    """Normalised task value from matching engine deviations.

    Structured pipeline/skill goals retain a modest value even before an
    engine deviation becomes visible.  Exploration receives value through
    information gain instead of this pragmatic term.
    """
    if goal_family(goal) == "explore":
        return 0.0
    if goal_family(goal) == "maintain":
        return 0.0
    obj = str(goal.get("object") or goal.get("target") or "")
    rooms = set(_goal_rooms(goal))
    urgency = 0.0
    for deviation in deviations or []:
        node_id = str(deviation.get("node_id") or "")
        room = str(deviation.get("room") or "")
        if node_id == obj or (room and room in rooms):
            urgency = max(urgency, float(deviation.get("urgency", 0.0)))
    if urgency > 0.0:
        return urgency / (urgency + 5.0)
    source = str(goal.get("_candidate_source") or "")
    if source in {"pipeline", "pipeline_skill", "skill"}:
        return 0.35
    return 0.20


def compute_goal_conditioned_efe(
    goal: dict[str, Any],
    deviations: list[dict[str, Any]] | None = None,
    world_belief: Any | None = None,
    outcome_model: GoalOutcomeModel | None = None,
) -> dict[str, Any]:
    """Auditable semantic goal objective; lower is better.

    ``expected_value`` is the pragmatic value of completing a needed task.
    ``information_gain`` is the expected reduction in uncertainty: physical
    room uncertainty for exploration and Beta-Bernoulli outcome information
    for task families.  Distance, duration and failure remain explicit costs
    instead of being hidden inside the EFE term.
    """
    model = outcome_model or GoalOutcomeModel()
    family = goal_family(goal)
    belief = model.belief(family)
    success_probability = belief.success_probability
    need = _goal_need(goal, deviations)
    expected_value = need * success_probability

    room = str(goal.get("target_room") or goal.get("room")
               or goal.get("object_room") or "")
    room_uncertainty = 1.0
    if world_belief is not None and room and room in world_belief:
        room_uncertainty = float(world_belief[room].room_entropy())

    if family == "explore":
        visit_count = max(0, int(goal.get("_visit_count", 0) or 0))
        # A fresh room remains worth checking when no repair exists, but a
        # concrete structured task should normally beat curiosity alone.
        # Re-entry decays sharply so successful navigation cannot create a
        # perpetual patrol loop.
        information_gain = 0.12 * room_uncertainty / (1.0 + visit_count)
    else:
        information_gain = 0.10 * belief.information_gain() * (0.5 + need)

    path_distance = max(0.0, float(goal.get("_path_distance", 0.0) or 0.0))
    distance_cost = 0.12 * min(path_distance / 6.0, 1.0)
    duration_cost = 0.10 * min(belief.mean_duration / 30.0, 1.0)
    failure_risk = 0.35 * need * (1.0 - success_probability)
    revisit_cost = (0.05 * min(max(0, int(goal.get("_visit_count", 0) or 0)), 3)
                    if family == "explore" else 0.0)
    switch_cost = max(0.0, float(goal.get("_switch_cost", 0.0) or 0.0))

    score = (failure_risk + distance_cost + duration_cost + revisit_cost + switch_cost
             - expected_value - information_gain)
    return {
        "goal_family": family,
        "need": need,
        "success_probability": success_probability,
        "expected_value": expected_value,
        "information_gain": information_gain,
        "failure_risk": failure_risk,
        "distance_cost": distance_cost,
        "duration_cost": duration_cost,
        "revisit_cost": revisit_cost,
        "switch_cost": switch_cost,
        "G": score,
    }


def compute_goal_conditioned_b_efe(
    goal: dict[str, Any],
    deviations: list[dict[str, Any]] | None = None,
    world_belief: Any | None = None,
    transition_model: HierarchicalGoalTransitionModel | None = None,
) -> dict[str, Any]:
    """Pure A/B/C EFE using a hierarchical Goal-conditioned transition B.

    Unlike ``compute_goal_conditioned_efe``, this score contains no learned
    completion reward and no hand-weighted distance/duration terms.  A and C
    are fixed; only the Dirichlet posterior over B^signature can evolve.
    """
    model = transition_model or HierarchicalGoalTransitionModel()
    return model.score(goal, deviations, world_belief)


# ============================================================
# scoring API
# ============================================================

def score_goal(goal: dict[str, Any],
               deviations: list[dict[str, Any]],
               memory: Any = None,
               world_belief: Any | None = None,
               step: int = 0,
               total_steps: int = 1600,
               tau: int = DEFAULT_TAU,
               beta: float = DEFAULT_BETA,
               efe_mode: str = "phase1",
               **kwargs) -> float:
    """G(g) for one candidate goal.  Lower = better.

    efe_mode="phase1":     -(P + E + beta*N)   (pragmatic + belief-entropy)
    efe_mode="generative": risk + ambiguity    (true EFE, from A/B/C tables)
    """
    if efe_mode == "goal_conditioned_b":
        return compute_goal_conditioned_b_efe(
            goal, deviations, world_belief,
            kwargs.get("goal_transition_model"))["G"]
    if efe_mode == "goal_conditioned":
        kwargs.pop("goal_transition_model", None)
        outcome_model = kwargs.pop("outcome_model", None)
        return compute_goal_conditioned_efe(
            goal, deviations, world_belief, outcome_model)["G"]
    if efe_mode == "generative":
        kwargs.pop("outcome_model", None)
        kwargs.pop("goal_transition_model", None)
        _, _, G = compute_efe_generative(goal, deviations, world_belief,
                                         step, **kwargs)
        return G
    P = compute_pragmatic(goal, deviations, world_belief)
    E = compute_epistemic(goal, world_belief, memory, step, tau)
    N = compute_novelty(goal, world_belief)
    return -(P + E + beta * N)


def decompose_goal(goal: dict[str, Any],
                   deviations: list[dict[str, Any]],
                   world_belief: Any | None = None,
                   beta: float = DEFAULT_BETA,
                   efe_mode: str = "generative",
                   **kwargs) -> dict[str, float]:
    """Auditable decomposition of a goal's score (acceptance criterion #3).

    efe_mode="generative" reports risk + ambiguity (the true EFE split);
    efe_mode="phase1" reports pragmatic / epistemic / novelty.
    """
    if efe_mode == "goal_conditioned_b":
        return compute_goal_conditioned_b_efe(
            goal, deviations, world_belief,
            kwargs.get("goal_transition_model"))
    if efe_mode == "goal_conditioned":
        return compute_goal_conditioned_efe(
            goal, deviations, world_belief, kwargs.get("outcome_model"))
    if efe_mode == "generative":
        kwargs.pop("outcome_model", None)
        kwargs.pop("goal_transition_model", None)
        risk, amb, G = compute_efe_generative(goal, deviations, world_belief,
                                              **kwargs)
        return {"risk": risk, "ambiguity": amb, "G": G}
    P = compute_pragmatic(goal, deviations, world_belief)
    E = compute_epistemic(goal, world_belief)
    N = compute_novelty(goal, world_belief)
    return {"pragmatic": P, "epistemic": E, "novelty": N,
            "G": -(P + E + beta * N)}


def select_goal(candidate_goals: list[dict[str, Any]],
                deviations: list[dict[str, Any]],
                memory: Any = None,
                world_belief: Any | None = None,
                step: int = 0,
                total_steps: int = 1600,
                efe_mode: str = "phase1",
                **kwargs) -> tuple[float, dict[str, Any]] | None:
    """Score and rank candidate goals; return (G, best_goal) or None."""
    if not candidate_goals:
        return None
    scored = []
    for g in candidate_goals:
        G = score_goal(g, deviations, memory, world_belief, step, total_steps,
                       efe_mode=efe_mode, **kwargs)
        scored.append((G, g))
    scored.sort(key=lambda x: x[0])
    return scored[0]


def select_goal_generative(candidate_goals: list[dict[str, Any]],
                           deviations: list[dict[str, Any]],
                           world_belief: Any | None = None,
                           step: int = 0,
                           **kwargs) -> tuple[float, dict[str, Any]] | None:
    """select_goal with efe_mode="generative" (true EFE)."""
    return select_goal(candidate_goals, deviations, None, world_belief,
                       step, 0, efe_mode="generative", **kwargs)


__all__ = [
    "STATE_KEY_PREFERENCE_LOG", "preference_distribution",
    "compute_pragmatic", "compute_epistemic", "compute_novelty",
    "compute_goal_conditioned_efe",
    "compute_goal_conditioned_b_efe",
    "goal_action_index", "compute_efe_generative",
    "score_goal", "select_goal",
    "select_goal_generative", "decompose_goal",
    "DEFAULT_TAU", "DEFAULT_BETA",
]
