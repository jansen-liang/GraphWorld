"""Numerical ground-truth tests for the Active Inference core.

Every assertion reproduces §1.6 of docs/active_inference/00_handoff_to_claude.md
to atol=1e-3.  Run standalone from the efe_agent dir:

    cd backend/runtime/agent/efe_agent
    python test_efe_numerical.py

or under pytest from the repo root:

    python -m pytest backend/runtime/agent/efe_agent/test_efe_numerical.py -v
"""

import copy
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

from efe_model import (
    GenerativeModel, softmax, kl_divergence, normalize_A, normalize_B,
    graphworld_model, predict_state, predict_obs, infer,
    update_A_counts, update_B_counts,
)
from world_belief import WorldBelief
from thinker_post import (
    observe_deviations, goal_outcome, thinker_update, urgency_to_obs,
)
from efe_scorer import compute_efe_generative, score_goal, goal_action_index


# ================================================================
# §1.6 fixture — DO NOT EDIT: these are the handoff's exact tables.
#   states  : [S = 信息充分, I = 信息不足]   (index 0 = S, index 1 = I)
#   obs     : [low, med, high]
#   actions : [DA, BS, DS]
# ================================================================
A_16 = np.array([[0.05, 0.60],
                 [0.25, 0.30],
                 [0.70, 0.10]])          # A[o, s]: col S / col I
B_16 = np.zeros((2, 2, 3))
B_16[:, :, 0] = [[1.00, 0.00], [0.00, 1.00]]   # DA: identity
B_16[:, :, 1] = [[0.90, 0.50], [0.10, 0.50]]   # BS: S->S .90, I->S .50
B_16[:, :, 2] = [[0.95, 0.75], [0.05, 0.25]]   # DS: S->S .95, I->S .75
C_16 = np.array([-4.0, 0.0, 4.0])
Q_16 = np.array([0.3, 0.7])                     # Q_prior = [S, I]

# initial Dirichlet pseudo-counts (§1.6): S column (1,5,14), I column (12,6,2)
ALPHA_16 = np.array([[1, 12], [5, 6], [14, 2]])
# B counts: DS slice S column (19,1), I column (15,5); DA/BS consistent
BETA_16 = np.zeros((2, 2, 3))
BETA_16[:, :, 0] = [[20, 0], [0, 20]]
BETA_16[:, :, 1] = [[18, 10], [2, 10]]
BETA_16[:, :, 2] = [[19, 15], [1, 5]]

DS, HIGH = 2, 2     # DS action index, high observation index


def model_16() -> GenerativeModel:
    return GenerativeModel(A_16, B_16, C_16,
                           alpha_counts=ALPHA_16, beta_counts=BETA_16)


def _close(a, b, atol=1e-3, msg=""):
    assert abs(a - b) <= atol, "%s: %.6f != %.6f (atol %.1e)" % (msg, a, b, atol)


# ================================================================
# §1.6 ground-truth tests
# ================================================================

def test_softmax_preference():
    """C=[-4,0,4] -> P_pref ≈ [0.0003, 0.018, 0.982]."""
    p = softmax(C_16)
    _close(p[0], 0.0003, 5e-4, "P_pref low")
    _close(p[1], 0.018, 5e-4, "P_pref med")
    _close(p[2], 0.982, 5e-4, "P_pref high")


def test_predict_state_ds():
    q = predict_state(B_16, Q_16, DS)
    assert np.allclose(q, [0.81, 0.19], atol=1e-3)


def test_predict_obs_ds():
    q = predict_obs(A_16, [0.81, 0.19])
    assert np.allclose(q, [0.1545, 0.2595, 0.586], atol=1e-3)


def test_efe_ds():
    risk, amb, G = model_16().efe(DS, Q_16)
    _close(risk, 1.3407, 1e-3, "risk(DS)")
    _close(amb, 0.7749, 1e-3, "amb(DS)")
    _close(G, 2.1156, 1e-3, "G(DS)")


def test_efe_all_actions():
    m = model_16()
    g_da = m.efe(0, Q_16)[2]
    g_bs = m.efe(1, Q_16)[2]
    g_ds = m.efe(2, Q_16)[2]
    _close(g_da, 4.4146, 1e-3, "G(DA)")
    _close(g_bs, 2.9128, 1e-3, "G(BS)")
    _close(g_ds, 2.1156, 1e-3, "G(DS)")


def test_policy_distribution():
    """softmax(-G) ≈ [DA 6.5%, BS 29.1%, DS 64.5%]; selected DS."""
    G, probs, best = model_16().policy(Q_16)
    _close(probs[0], 0.065, 2e-3, "P(DA)")
    _close(probs[1], 0.291, 2e-3, "P(BS)")
    _close(probs[2], 0.645, 2e-3, "P(DS)")
    assert best == DS, "argmin(G) must be DS"
    assert G[DS] == min(G), "DS must have the lowest EFE"


def test_infer_after_high():
    """o_obs=high -> Q_post = [0.9676, 0.0324]."""
    q_pred = predict_state(B_16, Q_16, DS)          # [0.81, 0.19]
    q_post = infer(A_16, q_pred, HIGH)
    assert np.allclose(q_post, [0.9676, 0.0324], atol=1e-3)


def test_learn_A():
    """A[high, S]: 0.70 -> 0.7138."""
    m = model_16()
    m.learn(DS, Q_16, HIGH)
    _close(m.A[HIGH, 0], 0.7138, 1e-3, "A[high,S] after learning")
    # whole high row re-normalised consistently
    _close(m.A[HIGH, 1], (2 + 0.0324) / (20 + 0.0324), 1e-3, "A[high,I]")


def test_learn_B():
    """B[S | I, DS]: 0.75 -> 0.7574."""
    m = model_16()
    m.learn(DS, Q_16, HIGH)
    _close(m.B[0, 1, DS], 0.7574, 1e-3, "B[S|I,DS] after learning")
    _close(m.B[0, 0, DS], 19.29028 / 20.3, 1e-3, "B[S|S,DS]")


def test_counts_functions():
    """update_A_counts / update_B_counts match the closed-form numbers."""
    alpha = update_A_counts(ALPHA_16, HIGH, np.array([0.9676, 0.0324]))
    _close(normalize_A(alpha)[HIGH, 0], 0.7138, 1e-3, "A[high,S] via counts")
    beta = update_B_counts(BETA_16, DS, Q_16, np.array([0.9676, 0.0324]))
    _close(normalize_B(beta)[0, 1, DS], 0.7574, 1e-3, "B[S|I,DS] via counts")


def test_normalize_roundtrip():
    """normalize_A / normalize_B recover the original matrices."""
    assert np.allclose(normalize_A(ALPHA_16), A_16, atol=1e-3)
    assert np.allclose(normalize_B(BETA_16), B_16, atol=1e-3)


def test_serialization_roundtrip():
    m = model_16()
    m.learn(DS, Q_16, HIGH)               # mutate before roundtrip
    data = m.to_dict()
    m2 = GenerativeModel.from_dict(data)
    assert np.allclose(m2.A, m.A)
    assert np.allclose(m2.B, m.B)
    assert np.allclose(m2.alpha_counts, m.alpha_counts)
    assert np.allclose(m2.beta_counts, m.beta_counts)


def test_kl_handles_zeros():
    """0 * ln(0) = 0; p=q -> KL 0."""
    assert abs(kl_divergence(np.array([1.0, 0.0]), np.array([1.0, 0.0]))) < 1e-12
    assert abs(kl_divergence(np.array([0.5, 0.5]), np.array([0.5, 0.5]))) < 1e-12


# ================================================================
# GraphWorld mapping sanity tests
# ================================================================

def test_graphworld_preference_prefers_low_urgency():
    gm = graphworld_model()
    pref = gm.preference()
    assert pref[0] > pref[1] > pref[2], "low urgency must be preferred"


def test_generative_favors_fix_on_deviated_room():
    """With belief strongly tilted toward needs_attention, the fix (act) goal
    must score lower (better) than re-exploring the same room."""
    wb = WorldBelief()
    for i in range(3):
        wb.update("kitchen", "support", weight=1.0, evidence_key="e%d" % i)
    assert wb["kitchen"].risk_confidence > 0.7

    fix = {"type": "skill", "target_room": "kitchen"}
    explore = {"type": "explore", "target_room": "kitchen"}
    g_fix = compute_efe_generative(fix, world_belief=wb)[2]
    g_explore = compute_efe_generative(explore, world_belief=wb)[2]
    assert g_fix < g_explore, "fix must beat explore on a deviated room"


def test_generative_prefers_explore_when_uncertain():
    """On a room never observed (flat prior), the explore goal must beat an
    idle goal — exploration is endogenous, not scheduled by an alpha."""
    wb = WorldBelief()
    explore = {"type": "explore", "target_room": "lab"}
    idle = {"type": "", "target_room": "lab"}      # unknown type -> wait
    g_explore = compute_efe_generative(explore, world_belief=wb)[2]
    g_idle = compute_efe_generative(idle, world_belief=wb)[2]
    assert g_explore < g_idle, "explore must beat idling on an unobserved room"


def test_generative_fix_beats_cross_room_explore():
    """Fixing a room the belief marks as needs-attention must beat exploring
    an unknown room — urgent maintenance wins over novelty-seeking."""
    wb = WorldBelief()
    for i in range(3):
        wb.update("kitchen", "support", weight=1.0, evidence_key="e%d" % i)
    fix = {"type": "skill", "target_room": "kitchen"}
    explore_unknown = {"type": "explore", "target_room": "lab"}
    g_fix = compute_efe_generative(fix, world_belief=wb)[2]
    g_explore = compute_efe_generative(explore_unknown, world_belief=wb)[2]
    assert g_fix < g_explore, "fix an urgent room before exploring unknown"


def test_room_entropy_decreases_with_evidence():
    rb = WorldBelief()
    rb.ensure_room("kitchen")
    h0 = rb["kitchen"].room_entropy()
    assert abs(h0 - 1.0) < 1e-6, "Beta(1,1) is max entropy"
    for i in range(40):
        rb.update("kitchen", "support", weight=1.0, evidence_key="s%d" % i)
    assert rb["kitchen"].room_entropy() < 0.1, "consistent evidence collapses entropy"


def test_thinker_post_mapping():
    """Deviations support the room; a completed goal refutes it."""
    wb = WorldBelief()
    devs = [{"node_id": "stove_01", "room": "kitchen", "urgency": 9.5,
             "state_key": "is_burning"}]
    n = observe_deviations(wb, devs, step=1)
    assert n == 1
    assert wb["kitchen"].risk_confidence > 0.5

    # repeat observation is fresh evidence (per-step key)
    assert observe_deviations(wb, devs, step=2) == 1

    applied = goal_outcome(wb, {"target": "stove_01", "target_room": "kitchen"},
                           "completed", step=5)
    assert applied is True
    # refute lowers confidence below its post-support peak
    assert wb["kitchen"].risk_confidence < 0.9

    # same goal+result must not double-apply (stable key)
    assert goal_outcome(wb, {"target": "stove_01", "target_room": "kitchen"},
                        "completed", step=6) is False


def test_thinker_update_integration():
    wb = WorldBelief()
    n = thinker_update(
        wb,
        [{"node_id": "x", "room": "kitchen", "urgency": 8.0}],
        goal={"target": "x", "target_room": "kitchen"}, result="completed",
        step=3,
    )
    assert n == 2
    assert wb["kitchen"].evidence_count == 2


def test_phase1_scorer_runs_without_alpha():
    """score_goal still returns a float; the alpha scheduler is gone."""
    wb = WorldBelief()
    g = {"type": "skill", "target": "stove_01", "target_room": "kitchen",
         "room": "kitchen"}
    devs = [{"node_id": "stove_01", "room": "kitchen", "urgency": 9.5,
             "state_key": "is_burning"}]
    G = score_goal(g, devs, world_belief=wb, efe_mode="phase1")
    assert isinstance(G, float)
    assert G < 0, "covered hazard must beat the neutral 0"


# ================================================================
# 1.8-aligned layers: observation compression, goal-action mapping,
# Dirichlet learning wired into the runtime loop
# ================================================================

def test_urgency_to_obs():
    """Observation compression: raw urgency -> discrete {low, med, high}."""
    assert urgency_to_obs(2.0) == 0
    assert urgency_to_obs(3.99) == 0
    assert urgency_to_obs(4.0) == 1
    assert urgency_to_obs(6.5) == 1
    assert urgency_to_obs(7.0) == 1
    assert urgency_to_obs(9.5) == 2
    assert urgency_to_obs(0.0) == 0


def test_goal_action_index():
    assert goal_action_index({"type": "explore"}) == 1
    assert goal_action_index({"type": "patrol"}) == 1
    assert goal_action_index({"type": "skill"}) == 2
    assert goal_action_index({"type": "restore_initial_position"}) == 2
    assert goal_action_index({"type": ""}) == 0
    assert goal_action_index({}) == 0


def test_learn_observation_updates_A():
    """Passive A-learning changes the likelihood in the observed row."""
    m = graphworld_model()
    a0 = m.A.copy()
    m.learn_observation(2, np.array([0.8, 0.2]))   # saw 'high' in an attention room
    # A[high, needs_attention] grew above its initial 0.30
    assert m.A[2, 0] > a0[2, 0]
    # columns stay stochastic
    assert np.allclose(m.A.sum(axis=0), 1.0)


def test_learn_transition_updates_B():
    """B-learning touches only the executed action's slice."""
    m = graphworld_model()
    b0 = m.B.copy()
    m.learn_transition(2, np.array([0.8, 0.2]), np.array([0.2, 0.8]))
    # act slice changed, explore and wait slices unchanged
    assert not np.allclose(m.B[:, :, 2], b0[:, :, 2])
    assert np.allclose(m.B[:, :, 0], b0[:, :, 0])
    assert np.allclose(m.B[:, :, 1], b0[:, :, 1])
    assert np.allclose(m.B.sum(axis=0), 1.0)


def test_efe_loop_learns_world_model_runtime():
    """After a step that observes a high-urgency deviation, the loop's
    generative model has absorbed the observation into A (1.8: learning
    corrects the model), and the belief moved."""
    from efe_core import EfeLoop
    baseline = {"nodes": [
        {"id": "robot_01", "node_type": "robot", "parent": "corridor"},
        {"id": "kitchen", "node_type": "room"},
        {"id": "bathroom", "node_type": "room"},
        {"id": "stove_01", "node_type": "appliance", "parent": "kitchen",
         "states": {"is_burning": True}},
    ]}
    obs = {"nodes": [
        {"id": "robot_01", "node_type": "robot", "parent": "corridor"},
        {"id": "kitchen", "node_type": "room"},
        {"id": "bathroom", "node_type": "room"},
        {"id": "stove_01", "node_type": "appliance", "parent": "kitchen",
         "states": {"is_burning": True}},
    ]}
    cands = [{"action": "move", "target": "kitchen"}]
    devs = [{"node_id": "stove_01", "room": "kitchen", "urgency": 9.5,
             "state_key": "is_burning"}]

    el = EfeLoop(baseline, agent_id="robot_01")          # default generative mode
    a_before = el.generative_model.A.copy()
    el.step(obs, cands, 0, deviations=devs, active_goal=None, llm_fn=None)
    assert el.efe_mode == "generative"
    # high-urgency deviation observed -> A[high, needs_attention] grew
    assert el.generative_model.A[2, 0] > a_before[2, 0]
    # belief reflects the deviation
    assert el.world_belief["kitchen"].risk_confidence > 0.5


def test_goal_authority_conditions_are_auditable():
    """The four authority conditions must commit through distinct selectors."""
    from efe_core import EfeLoop

    baseline = {"nodes": [
        {"id": "robot_01", "node_type": "robot", "parent": "hall"},
        {"id": "hall", "node_type": "room"},
        {"id": "kitchen", "node_type": "room"},
    ]}
    observation = {"nodes": [
        {"id": "robot_01", "node_type": "robot", "parent": "hall"},
        {"id": "hall", "node_type": "room"},
    ]}
    active_goal = {
        "type": "explore", "task": "explore kitchen", "target": "kitchen",
        "room": "kitchen", "target_room": "kitchen",
    }
    candidates = [{"action": "move", "agent": "robot_01", "target": "kitchen"}]
    expected = {
        "current": "pipeline_direct",
        "efe_all": "efe",
        "rule_all": "rule",
        "random_all": "random",
    }
    for authority, selector in expected.items():
        loop = EfeLoop(
            baseline, goal_authority=authority,
            candidate_source="skill_only", selection_seed=0,
        )
        result = loop.step(
            observation, candidates, 0, active_goal=active_goal,
            deviations=[], llm_fn=None,
        )
        assert result["authority_step"]["selected_by"] == selector
        assert result["authority_diagnostics"]["goal_commitments"] == 1


def test_hospital_bed_sheet_workflow_has_no_restore_conflict():
    """A sheet owned by the hospital workflow must have one destination only."""
    from efe_goal_builder import build_skill_goals

    baseline = {
        "scene_name": "simple_hospital_1f",
        "nodes": [
            {"id": "robot_01", "node_type": "robot", "parent": "treatment_room"},
            {"id": "treatment_room", "node_type": "room"},
            {"id": "treatment_bed", "node_type": "fixed_object",
             "semantic_type": "bed", "parent": "treatment_room"},
            {"id": "linen_bin", "node_type": "fixed_object",
             "semantic_type": "linen_bin", "parent": "treatment_room"},
            {"id": "supply_cabinet", "node_type": "fixed_object",
             "semantic_type": "supply_cabinet", "parent": "treatment_room"},
            {"id": "dirty_sheet", "node_type": "movable_object",
             "semantic_type": "bed_sheet", "parent": "treatment_bed",
             "states": {"is_dirty": False}},
            {"id": "clean_sheet_storage", "node_type": "movable_object",
             "semantic_type": "bed_sheet", "parent": "supply_cabinet",
             "states": {"is_dirty": False}},
        ],
    }

    # The clean sheet currently installed on the bed is valid and must not be
    # mistaken for spare stock that needs returning to the cabinet.
    initial_goals = build_skill_goals(
        baseline, baseline, baseline, robot_id="robot_01", step=0)
    assert not [g for g in initial_goals if g.get("object") == "dirty_sheet"]

    # After use, the dirty sheet belongs in the linen bin.  Once there, generic
    # baseline restore must not send it back to the treatment bed.
    after_change = copy.deepcopy(baseline)
    for node in after_change["nodes"]:
        if node["id"] == "dirty_sheet":
            node["parent"] = "linen_bin"
            node["states"]["is_dirty"] = True
    settled_goals = build_skill_goals(
        after_change, after_change, baseline, robot_id="robot_01", step=1)
    assert not [g for g in settled_goals if g.get("object") == "dirty_sheet"]

    # If the dirty sheet is outside its bin, exactly the collection skill owns
    # it; no restore_initial_position competitor may be emitted.
    displaced = copy.deepcopy(after_change)
    for node in displaced["nodes"]:
        if node["id"] == "dirty_sheet":
            node["parent"] = "treatment_room"
    displaced_goals = [g for g in build_skill_goals(
        displaced, displaced, baseline, robot_id="robot_01", step=2)
        if g.get("object") == "dirty_sheet"]
    assert len(displaced_goals) == 1
    assert displaced_goals[0]["skill"] == "collect_dirty_linen"
    assert displaced_goals[0]["target"] == "linen_bin"


def test_explore_requires_physical_visit_not_visibility():
    """Seeing an adjacent room must not instantly complete a patrol goal."""
    from efe_core import EfeLoop

    baseline = {"nodes": [
        {"id": "robot_01", "node_type": "robot", "parent": "hall"},
        {"id": "hall", "node_type": "room"},
        {"id": "kitchen", "node_type": "room"},
        {"id": "bedroom", "node_type": "room"},
    ]}
    observation = copy.deepcopy(baseline)
    loop = EfeLoop(baseline, goal_authority="efe_all",
                   candidate_source="skill_only")
    loop.update_memory(observation, 0)
    goal = {"type": "explore", "target": "kitchen", "room": "kitchen",
            "target_room": "kitchen", "_committed_step": 0}
    assert "kitchen" not in loop._visited_rooms
    assert not loop._goal_achieved(goal, observation, [], baseline)

    arrived = copy.deepcopy(observation)
    arrived["nodes"][0]["parent"] = "kitchen"
    loop.update_memory(arrived, 1)
    assert loop._goal_achieved(goal, arrived, [], arrived)


def test_maintain_is_one_step_temporal_goal():
    """Waiting observes one transition; it must not require leaving a room."""
    from efe_core import EfeLoop

    scene = {"nodes": [
        {"id": "robot_01", "node_type": "robot", "parent": "hall"},
        {"id": "hall", "node_type": "room"},
    ]}
    loop = EfeLoop(scene)
    goal = {
        "type": "maintain", "task": "maintain hall", "room": "hall",
        "target_room": "hall", "_committed_step": 4,
    }
    assert not loop._goal_achieved(goal, scene, [], scene, step=4)
    assert loop._goal_achieved(goal, scene, [], scene, step=5)


def test_goal_progress_resets_staleness_without_resetting_commitment():
    """A workflow phase/object transition extends its life, not its age."""
    from efe_core import EfeLoop

    baseline = {"nodes": [
        {"id": "robot_01", "node_type": "robot", "parent": "kitchen"},
        {"id": "kitchen", "node_type": "room"},
        {"id": "food", "node_type": "movable_object", "parent": "table",
         "states": {"is_rotten": True}},
        {"id": "table", "node_type": "fixed_object", "parent": "kitchen"},
        {"id": "bin", "node_type": "fixed_object", "semantic_type": "trash_bin",
         "parent": "kitchen"},
        {"id": "station", "node_type": "fixed_object",
         "semantic_type": "garbage_station", "parent": "kitchen"},
    ]}
    loop = EfeLoop(baseline)
    goal = {
        "type": "skill", "skill": "dispose_food", "task": "dispose food",
        "object": "food", "target": "station", "trash_bin": "bin",
        "trash_bin_home": "kitchen", "garbage_station": "station",
        "phase": "collect_food", "object_parent": "table",
        "robot_parent": "kitchen", "robot_room": "kitchen",
    }
    loop._commit_goal(goal, 0, "efe", 1)
    loop._last_goal["steps_without_progress"] = 11
    progressed = copy.deepcopy(baseline)
    next(item for item in progressed["nodes"] if item["id"] == "food")["parent"] = "bin"
    loop._refresh_held_goal(progressed, 12)
    assert loop._goal_commit_step == 0
    assert loop._last_goal["phase"] == "take_bin"
    assert loop._last_goal["steps_without_progress"] == 0
    assert loop.authority_diagnostics()["goal_progress_events"] == 1


def test_disposal_returns_empty_held_bin_before_collecting_new_food():
    from efe_goal_builder import dispose_food_phase

    scene = {"nodes": [
        {"id": "robot_01", "node_type": "robot", "parent": "outside"},
        {"id": "food", "node_type": "movable_object", "parent": "table",
         "states": {"is_rotten": True}},
        {"id": "bin", "node_type": "movable_object", "parent": "robot_01"},
    ]}
    assert dispose_food_phase(
        scene, "food", "bin", "robot_01", "living_room") == "return_bin"
    next(item for item in scene["nodes"] if item["id"] == "food")["parent"] = "bin"
    assert dispose_food_phase(
        scene, "food", "bin", "robot_01", "living_room") == "dump_bin"


def test_unplanned_room_motion_does_not_keep_goal_alive():
    """Oscillation away from the planned route is activity, not progress."""
    from efe_core import EfeLoop

    baseline = {"nodes": [
        {"id": "robot_01", "node_type": "robot", "parent": "hall"},
        {"id": "hall", "node_type": "room"},
        {"id": "kitchen", "node_type": "room"},
        {"id": "bedroom", "node_type": "room"},
    ], "edges": [
        {"source_id": "hall", "target_id": "kitchen", "relation": "connected"},
        {"source_id": "hall", "target_id": "bedroom", "relation": "connected"},
    ]}
    loop = EfeLoop(baseline)
    loop._commit_goal({
        "type": "explore", "task": "explore kitchen", "target": "kitchen",
        "room": "kitchen", "target_room": "kitchen", "robot_room": "hall",
        "next_room": "kitchen",
    }, 0, "efe", 1)
    wandered = copy.deepcopy(baseline)
    wandered["nodes"][0]["parent"] = "bedroom"
    loop._refresh_held_goal(wandered, 1)
    assert loop._last_goal["steps_without_progress"] == 1
    assert loop.authority_diagnostics()["goal_progress_events"] == 0


def test_transient_drop_preserves_selected_goal_and_signature():
    """Freeing the hand must not become a generic learned Goal transition."""
    from efe_core import EfeLoop
    from goal_transition_model import enrich_goal_signature, goal_signature

    baseline = {"scene_name": "simple_home_1f", "nodes": [
        {"id": "robot_01", "node_type": "robot", "parent": "kitchen"},
        {"id": "kitchen", "node_type": "room"},
        {"id": "cup", "node_type": "movable_object", "semantic_type": "cup",
         "parent": "table"},
        {"id": "book", "node_type": "movable_object", "semantic_type": "book",
         "parent": "table"},
        {"id": "table", "node_type": "fixed_object", "parent": "kitchen"},
        {"id": "sink", "node_type": "fixed_object", "semantic_type": "sink",
         "parent": "kitchen"},
    ]}
    loop = EfeLoop(baseline, efe_mode="goal_conditioned_b")
    original = enrich_goal_signature({
        "type": "restore_initial_position", "task": "restore cup",
        "object": "cup", "target": "sink", "object_parent": "table",
        "robot_parent": "kitchen", "robot_room": "kitchen",
        "_candidate_source": "skill",
    }, baseline)
    loop._commit_goal(original, 0, "efe", 1)
    original_signature = goal_signature(loop._last_goal).key
    loop._last_goal["steps_without_progress"] = 0
    observation = copy.deepcopy(baseline)
    next(item for item in observation["nodes"] if item["id"] == "book")["parent"] = "robot_01"
    result = loop.step(
        observation,
        [{"action": "place", "agent": "robot_01", "object": "book",
          "target": "table"}],
        1, world_scene=observation, deviations=[], llm_fn=None,
    )
    assert result["high_level_task"].startswith("drop book")
    assert goal_signature(loop._last_goal).key == original_signature
    assert loop._goal_commit_step == 0
    diagnostics = result["authority_diagnostics"]
    assert diagnostics["goal_commitments"] == 1
    assert diagnostics["transient_drop_constraints"] == 1


def test_completed_goal_closes_even_during_emergency():
    """Emergency evidence cannot keep phase=done alive until stuck timeout."""
    from efe_core import EfeLoop

    baseline = {"nodes": [
        {"id": "robot_01", "node_type": "robot", "parent": "kitchen"},
        {"id": "kitchen", "node_type": "room"},
        {"id": "bedroom", "node_type": "room"},
        {"id": "cup", "node_type": "movable_object", "semantic_type": "cup",
         "parent": "kitchen", "states": {"fill_level": 1.0, "is_full": True}},
        {"id": "sink", "node_type": "fixed_object", "semantic_type": "sink",
         "parent": "kitchen"},
    ]}
    loop = EfeLoop(baseline, goal_authority="current",
                   candidate_source="skill_only")
    goal = {"type": "skill", "skill": "empty_cup", "task": "empty cup",
            "object": "cup", "target": "sink", "sink": "sink",
            "room": "kitchen", "phase": "dump_cup"}
    candidates = [{"action": "dump", "agent": "robot_01", "target": "sink"}]
    loop.step(baseline, candidates, 0, pipeline_goals=[goal],
              world_scene=baseline, deviations=[], llm_fn=None)

    resolved = copy.deepcopy(baseline)
    for node_item in resolved["nodes"]:
        if node_item["id"] == "cup":
            node_item["states"] = {"fill_level": 0.0, "is_full": False}
    emergency = [{"node_id": "hazard", "room": "kitchen", "urgency": 9.0,
                  "state_key": "is_burnt"}]
    result = loop.step(resolved, candidates, 1, pipeline_goals=[],
                       world_scene=resolved, deviations=emergency, llm_fn=None)
    diagnostics = result["authority_diagnostics"]
    assert diagnostics["goal_completions"] == 1
    assert diagnostics["phase_done_action_count"] == 0


def test_repair_and_explore_are_concurrent_candidates():
    """A visible repair must not suppress all exploration alternatives."""
    from efe_core import EfeLoop

    baseline = {"nodes": [
        {"id": "robot_01", "node_type": "robot", "parent": "hall"},
        {"id": "hall", "node_type": "room"},
        {"id": "kitchen", "node_type": "room"},
        {"id": "bedroom", "node_type": "room"},
        {"id": "cup", "node_type": "movable_object", "semantic_type": "cup",
         "parent": "kitchen", "states": {}},
    ]}
    scene = copy.deepcopy(baseline)
    for node_item in scene["nodes"]:
        if node_item["id"] == "cup":
            node_item["parent"] = "hall"
    loop = EfeLoop(baseline, goal_authority="efe_all",
                   candidate_source="skill_only")
    result = loop.step(
        scene, [{"action": "pick", "agent": "robot_01", "target": "cup"}],
        0, world_scene=scene, deviations=[], llm_fn=None,
    )
    assert result["authority_step"]["candidate_count"] >= 3
    assert result["authority_diagnostics"]["single_candidate_rate"] == 0.0


def test_goal_family_outcome_model_learns_and_roundtrips():
    from goal_outcome_model import GoalOutcomeModel, goal_family

    supply = {"type": "skill", "skill": "return_refrigerated_medicine"}
    explore = {"type": "explore"}
    assert goal_family(supply) == "return_supply"
    assert goal_family(explore) == "explore"

    model = GoalOutcomeModel()
    before = model.belief(supply).success_probability
    model.update(supply, "completed", 4)
    after = model.belief(supply).success_probability
    assert after > before
    restored = GoalOutcomeModel.from_dict(model.to_dict())
    assert abs(restored.belief(supply).success_probability - after) < 1e-12
    assert restored.belief(supply).mean_duration == 6.0


def test_goal_conditioned_explore_value_decays_after_visits():
    from efe_scorer import compute_goal_conditioned_efe
    from goal_outcome_model import GoalOutcomeModel

    model = GoalOutcomeModel()
    fresh = {"type": "explore", "target_room": "lab",
             "_visit_count": 0, "_path_distance": 1}
    repeated = dict(fresh, _visit_count=3)
    fresh_score = compute_goal_conditioned_efe(
        fresh, [], outcome_model=model)["G"]
    repeated_score = compute_goal_conditioned_efe(
        repeated, [], outcome_model=model)["G"]
    assert fresh_score < repeated_score


def test_goal_conditioned_pipeline_is_candidate_not_direct_authority():
    from efe_core import EfeLoop

    baseline = {"nodes": [
        {"id": "robot_01", "node_type": "robot", "parent": "hall"},
        {"id": "hall", "node_type": "room"},
        {"id": "kitchen", "node_type": "room"},
        {"id": "cup", "node_type": "movable_object", "semantic_type": "cup",
         "parent": "hall", "states": {}},
    ], "edges": [
        {"source_id": "hall", "target_id": "kitchen", "relation": "connected"},
    ]}
    pipeline_goal = {
        "type": "restore_initial_position", "task": "restore cup",
        "object": "cup", "target": "kitchen", "object_room": "hall",
        "target_room": "kitchen",
    }
    loop = EfeLoop(
        baseline, goal_authority="current", candidate_source="skill_only",
        efe_mode="goal_conditioned",
    )
    result = loop.step(
        baseline,
        [{"action": "move", "agent": "robot_01", "target": "kitchen"}],
        0, pipeline_goals=[pipeline_goal], world_scene=baseline,
        deviations=[], llm_fn=None,
    )
    diagnostics = result["authority_diagnostics"]
    assert diagnostics["pipeline_direct_commits"] == 0
    assert diagnostics["pipeline_candidates_scored"] == 1
    assert diagnostics["efe_selections"] == 1
    assert result["authority_step"]["selected_goal_family"] in {
        "explore", "restore_object"
    }


def test_hierarchical_goal_signature_is_structured_not_object_id_specific():
    from goal_transition_model import enrich_goal_signature, goal_signature

    home = {
        "scene_name": "simple_home_1f",
        "nodes": [
            {"id": "cup_bathroom", "semantic_type": "cup"},
            {"id": "cup_kitchen", "semantic_type": "cup"},
        ],
    }
    first = enrich_goal_signature({
        "type": "restore_initial_position", "object": "cup_bathroom",
        "target": "bathroom",
    }, home)
    second = enrich_goal_signature({
        "type": "restore_initial_position", "object": "cup_kitchen",
        "target": "kitchen",
    }, home)
    assert goal_signature(first).key == goal_signature(second).key
    assert goal_signature(first).key == \
        "restore_object|cup|direct_restore|home"


def test_maintain_prior_reflects_pending_structured_tasks():
    """A global no-op cannot assume normal state while known work is pending."""
    from goal_transition_model import HierarchicalGoalTransitionModel

    model = HierarchicalGoalTransitionModel()
    quiet = {"type": "maintain", "_pending_task_count": 0}
    pending = {"type": "maintain", "_pending_task_count": 3}
    quiet_prior = model.state_prior(quiet)
    pending_prior = model.state_prior(pending)
    quiet_mild_or_severe = float(quiet_prior[[1, 2, 4, 5]].sum())
    pending_mild_or_severe = float(pending_prior[[1, 2, 4, 5]].sum())
    assert pending_mild_or_severe > quiet_mild_or_severe
    assert model.score(pending)["G"] > model.score(quiet)["G"]


def test_nonrepair_goal_observes_global_unresolved_condition():
    from goal_transition_model import HierarchicalGoalTransitionModel

    explore = {
        "type": "explore", "target": "quiet_room", "room": "quiet_room",
        "_pending_task_count": 2,
    }
    elsewhere = [{
        "node_id": "dirty_cup", "room": "kitchen", "urgency": 3.0,
    }]
    assert HierarchicalGoalTransitionModel.observation_index(
        explore, "completed", elsewhere) == 2
    assert HierarchicalGoalTransitionModel.observation_index(
        explore, "completed", []) == 1


def test_task_goal_prior_ignores_unrelated_same_room_deviation():
    """Another broken object in the room is not this Goal's initial state."""
    from goal_transition_model import (
        HierarchicalGoalTransitionModel, enrich_goal_signature,
    )

    goal = enrich_goal_signature({
        "type": "restore_initial_position", "object": "cup",
        "target": "cabinet", "room": "kitchen",
        "_candidate_source": "skill", "_efe_target_issue_before": True,
    })
    unrelated = [{
        "node_id": "plate", "room": "kitchen", "urgency": 8.0,
    }]
    target = [{
        "node_id": "cup", "room": "kitchen", "urgency": 8.0,
    }]
    model = HierarchicalGoalTransitionModel()
    unrelated_prior = model.state_prior(goal, unrelated)
    quiet_prior = model.state_prior(goal, [])
    target_prior = model.state_prior(goal, target)
    assert np.allclose(unrelated_prior, quiet_prior)
    assert float(target_prior[[2, 5]].sum()) > \
        float(unrelated_prior[[2, 5]].sum())


def test_task_goal_posterior_uses_target_condition_not_room_condition():
    from goal_transition_model import HierarchicalGoalTransitionModel

    goal = {
        "type": "restore_initial_position", "object": "cup",
        "target": "cabinet", "room": "kitchen",
    }
    unrelated = [{
        "node_id": "plate", "room": "kitchen", "urgency": 8.0,
    }]
    assert HierarchicalGoalTransitionModel.observation_index(
        goal, "completed", unrelated,
        target_issue_after=False) == 1
    assert HierarchicalGoalTransitionModel.observation_index(
        goal, "failed", unrelated,
        target_issue_after=True) == 2


def test_task_goal_b_records_explainable_target_credit_assignment():
    from goal_transition_model import (
        HierarchicalGoalTransitionModel, enrich_goal_signature,
    )

    goal = enrich_goal_signature({
        "type": "restore_initial_position", "object": "cup",
        "target": "cabinet", "_candidate_source": "skill",
        "_efe_target_issue_before": True,
    })
    model = HierarchicalGoalTransitionModel()
    goal["_efe_state_prior"] = model.state_prior(goal, []).tolist()
    event = model.learn(
        goal, "completed",
        [{"node_id": "plate", "room": "kitchen", "urgency": 8.0}],
        target_issue_after=False)
    assert event["observation"] == "low"
    assert event["credit_assignment"] == "target_condition"
    assert event["target_issue_before"] is True
    assert event["target_issue_after"] is False


def test_hierarchical_goal_b_learns_signature_specific_transitions():
    from goal_transition_model import (
        HierarchicalGoalTransitionModel, enrich_goal_signature,
    )

    scene = {
        "scene_name": "simple_home_1f",
        "nodes": [
            {"id": "cup", "semantic_type": "cup"},
            {"id": "blanket", "semantic_type": "blanket"},
        ],
    }
    cup = enrich_goal_signature({
        "type": "restore_initial_position", "object": "cup",
        "target": "kitchen", "_candidate_source": "skill",
    }, scene)
    blanket = enrich_goal_signature({
        "type": "restore_initial_position", "object": "blanket",
        "target": "bedroom", "_candidate_source": "skill",
    }, scene)
    deviations = [
        {"node_id": "cup", "urgency": 8.0},
        {"node_id": "blanket", "urgency": 8.0},
    ]
    model = HierarchicalGoalTransitionModel()
    for goal in (cup, blanket):
        goal["_efe_state_prior"] = model.state_prior(goal, deviations).tolist()

    assert abs(model.score(cup, deviations)["G"]
               - model.score(blanket, deviations)["G"]) < 1e-12
    for _ in range(12):
        model.learn(cup, "completed", [])
        model.learn(blanket, "failed", [
            {"node_id": "blanket", "urgency": 8.0},
        ])
    cup_score = model.score(cup, deviations)["G"]
    blanket_score = model.score(blanket, deviations)["G"]
    assert cup_score < blanket_score
    assert np.allclose(model.transition(cup).sum(axis=0), 1.0)
    assert model.diagnostics()["learned_signatures"] == 2


def test_hierarchical_goal_b_update_is_explainable_and_roundtrips():
    from goal_transition_model import (
        HierarchicalGoalTransitionModel, enrich_goal_signature,
    )

    scene = {
        "scene_name": "simple_hospital_1f",
        "nodes": [{"id": "sheet", "semantic_type": "bed_sheet"}],
    }
    goal = enrich_goal_signature({
        "type": "skill", "skill": "restock_clean_sheet",
        "object": "sheet", "target": "supply_cabinet",
        "_candidate_source": "skill",
    }, scene)
    model = HierarchicalGoalTransitionModel()
    goal["_efe_state_prior"] = model.state_prior(goal, [
        {"node_id": "sheet", "urgency": 6.0},
    ]).tolist()
    event = model.learn(goal, "completed", [])
    evidence = np.asarray(event["transition_evidence"])
    assert event["goal_signature"] == \
        "bed_linen|bed_sheet|restock_clean_sheet|hospital"
    assert event["observation"] == "low"
    assert event["predictive_probability"] > 0.0
    assert event["prequential_nll"] >= 0.0
    assert abs(float(evidence.sum()) - 1.0) < 1e-12

    restored = HierarchicalGoalTransitionModel.from_dict(model.to_dict())
    assert restored.update_count == 1
    assert restored.observation_count == 1
    assert restored.prequential_nll == model.prequential_nll
    assert np.allclose(restored.transition(goal), model.transition(goal))


def test_hierarchical_goal_b_frozen_observes_without_updating():
    from goal_transition_model import (
        HierarchicalGoalTransitionModel, enrich_goal_signature,
    )

    goal = enrich_goal_signature({
        "type": "restore_initial_position", "object": "cup",
        "target": "kitchen", "_candidate_source": "skill",
    }, {"scene_name": "simple_home_1f",
        "nodes": [{"id": "cup", "semantic_type": "cup"}]})
    model = HierarchicalGoalTransitionModel()
    before = model.transition(goal).copy()
    event = model.learn(goal, "completed", [], update=False)
    assert event["updated"] is False
    assert model.update_count == 0
    assert model.observation_count == 1
    assert len(model.prequential_nll) == 1
    assert np.allclose(model.transition(goal), before)


def test_goal_conditioned_b_scorer_reports_abc_terms():
    from efe_scorer import compute_goal_conditioned_b_efe
    from goal_transition_model import (
        HierarchicalGoalTransitionModel, enrich_goal_signature,
    )

    goal = enrich_goal_signature({
        "type": "restore_initial_position", "object": "cup",
        "target": "kitchen", "_candidate_source": "skill",
    }, {"scene_name": "simple_home_1f",
        "nodes": [{"id": "cup", "semantic_type": "cup"}]})
    decomposition = compute_goal_conditioned_b_efe(
        goal, [{"node_id": "cup", "urgency": 7.0}],
        transition_model=HierarchicalGoalTransitionModel())
    assert decomposition["goal_signature"] == \
        "restore_object|cup|direct_restore|home"
    assert abs(decomposition["G"] - decomposition["risk"]
               - decomposition["ambiguity"]) < 1e-12
    assert set(decomposition["predicted_observation"]) == {
        "unobserved", "low", "medium", "high"
    }


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS %s" % t.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL %s: %s" % (t.__name__, e))
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("ERROR %s: %r" % (t.__name__, e))
    print()
    print("%d/%d tests passed" % (len(tests) - failed, len(tests)))
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
