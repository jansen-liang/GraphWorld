"""efe_agent — Active Inference agent for GraphWorld simulation.

Architecture:
  1. LLM: receives world state + posterior of last goal → updates belief,
          adjusts parameters, proposes candidate goals.
  2. EFE: scores candidates using belief state → picks the best.
  3. LLM: executes chosen goal via llm_choose_action.
  4. After goal completion → back to step 1.
"""

from __future__ import annotations

import copy
import json
import os
import random
from collections import deque
from typing import Any

import numpy as np

# Goal lifecycle is based on *lack of observable progress*, not wall-clock
# duration.  Multi-stage goals (dispose/laundry/navigation) may legitimately
# take much longer than 30 steps as long as their phase, object position, or
# robot position continues to advance.
GOAL_NO_PROGRESS_STEPS: int = 12
GOAL_MAX_DURATION_STEPS: int = 160
GOAL_FAIL_COOLDOWN: int = 40

try:
    from .world_belief import WorldBelief
    from .efe_scorer import select_goal, goal_action_index, decompose_goal
    from .efe_model import GenerativeModel, graphworld_model, normalize_B
    from .thinker_post import observe_deviations, goal_outcome, urgency_to_obs
    from .efe_goal_builder import build_skill_goals, refresh_goal_snapshot, \
        goal_still_needed
    from .goal_outcome_model import GoalOutcomeModel, goal_family
    from .goal_transition_model import (
        HierarchicalGoalTransitionModel, enrich_goal_signature, goal_signature,
    )
    from ..decision import choose_explore_navigation_action
except ImportError:
    from world_belief import WorldBelief
    from efe_scorer import select_goal, goal_action_index, decompose_goal
    from efe_model import GenerativeModel, graphworld_model, normalize_B
    from thinker_post import observe_deviations, goal_outcome, urgency_to_obs
    from efe_goal_builder import build_skill_goals, refresh_goal_snapshot, \
        goal_still_needed
    from goal_outcome_model import GoalOutcomeModel, goal_family
    from goal_transition_model import (
        HierarchicalGoalTransitionModel, enrich_goal_signature, goal_signature,
    )
    from backend.runtime.agent.decision import choose_explore_navigation_action


# ============================================================
# helpers
# ============================================================

def _merge_observation_scene(baseline: dict[str, Any],
                             observation: dict[str, Any]) -> dict[str, Any]:
    """Approximate the current scene by overlaying visible nodes on baseline.

    EfeLoop lacks the orchestrator's graph.to_scene(); this builds a best-effort
    current scene so skill goal builders can resolve object positions/states.
    Nodes seen in observation replace their baseline counterparts; baseline
    geometry (rooms, edges, fixed objects) stays intact.
    """
    merged = copy.deepcopy(baseline)
    nodes = merged.get("nodes")
    if isinstance(nodes, list):
        index = {str(n.get("id") or ""): n for n in nodes if isinstance(n, dict)}
        for on in observation.get("nodes") or []:
            if not isinstance(on, dict) or not on.get("id"):
                continue
            oid = str(on.get("id") or "")
            # keep baseline's node_type/semantic if observation omits them
            merged_node = copy.deepcopy(on)
            if oid in index:
                for key in ("node_type", "semantic_type"):
                    if not merged_node.get(key):
                        merged_node[key] = index[oid].get(key)
                index[oid].update(merged_node)
            else:
                index[oid] = merged_node
        merged["nodes"] = list(index.values())
    return merged


def _room_behind_door(door_id: str, observation: dict, exclude_room: str) -> str:
    """Find which room is on the other side of a door."""
    for node in observation.get("nodes") or []:
        if isinstance(node, dict) and str(node.get("id") or "") == door_id:
            for rid in node.get("connected_rooms") or []:
                if str(rid) != exclude_room:
                    return str(rid)
    return "?"


def _robot_room(observation: dict[str, Any], agent_id: str = "robot_01") -> str:
    # try robot node first
    for node in observation.get("nodes") or []:
        if isinstance(node, dict) and str(node.get("id") or "") == agent_id:
            parent = str(node.get("parent") or "")
            # walk up to find room
            for _ in range(3):
                found = None
                for n2 in observation.get("nodes") or []:
                    if isinstance(n2, dict) and str(n2.get("id") or "") == parent:
                        if str(n2.get("node_type") or "") == "room":
                            return parent
                        found = str(n2.get("parent") or "")
                        break
                if found:
                    parent = found
                else:
                    break
            return ""
    # fallback: look at visible rooms from world_state
    visible = (observation.get("world_state") or {}).get("visible_rooms") or []
    return str(visible[0]) if visible else ""


def _expected_holding(goal: dict[str, Any]) -> str:
    """The object the current goal expects the robot to be holding, if any."""
    if not goal:
        return ""
    phase = str(goal.get("phase") or "")
    if phase in ("take_bin", "dump_bin", "return_bin"):
        return str(goal.get("trash_bin") or "")
    return str(goal.get("object") or "")


def _drop_goal(holding: str, observation: dict[str, Any],
               baseline: dict[str, Any], agent_id: str) -> dict[str, Any]:
    """A restore goal that frees the robot's hands (state-consistency drop).

    This is a hard *constraint* (the robot must not wander off holding a wrong
    object), not a preference override of the EFE ranking.
    """
    room = _robot_room(observation, agent_id)
    initial_parent = ""
    for node in baseline.get("nodes") or []:
        if isinstance(node, dict) and str(node.get("id") or "") == holding:
            initial_parent = str(node.get("parent") or "")
            break
    return {
        "type": "restore_initial_position",
        "task": "drop %s to free hands" % holding,
        "object": holding,
        "target": initial_parent or room,
        "room": room,
        "object_room": room,
        "target_room": room,
        "robot_room": room,
        "_transient_constraint": True,
    }


# ============================================================
# LLM goal proposer + belief updater
# ============================================================

def _llm_propose_and_update(
    observation: dict[str, Any],
    deviations: list[dict[str, Any]],
    world_belief: WorldBelief,
    memory: Any,
    step: int,
    last_goal: dict[str, Any] | None,
    last_goal_result: str,   # "success" | "failed" | "started"
    llm_fn: Any,
    agent_id: str = "robot_01",
    agent_model: str = "vllm-qwen3.5-9b",
) -> dict[str, Any]:
    """Ask the LLM to propose candidate goals.

    Belief and EFE parameters are NOT LLM-writable (handoff §1.7: the LLM must
    not rewrite decision inputs). The belief is fed as read-only context and
    updated data-driven by thinker_post.

    Returns {"goals": [...]} or {"goals": []} on failure.
    """

    # ── build room summaries ──
    room_lines = []
    for rid, rb in sorted(world_belief.items()):
        room_lines.append("%s: risk_confidence=%.2f epistemic=%.2f status=%s visits=%d" % (
            rid, rb.risk_confidence, rb.epistemic_norm, rb.status, rb.evidence_count))

    # ── deviation summary ──
    dev_lines = []
    for d in (deviations or [])[:12]:
        dev_lines.append("%s | %s | urgency=%.1f | room=%s" % (
            d.get("node_id", "?"), d.get("deviation", ""),
            d.get("urgency", 0.0), d.get("room", "?")))

    # ── visible objects ──
    obj_lines = []
    for node in (observation.get("nodes") or [])[:20]:
        if not isinstance(node, dict):
            continue
        nid = node.get("id", "")
        ntype = node.get("node_type", "")
        parent = node.get("parent", "")
        if ntype in ("room", "robot", "floor", ""):
            continue
        states = node.get("states") or {}
        state_str = " ".join("%s=%s" % (k, v) for k, v in states.items()
                             if v not in (False, None, 0, 0.0, ""))
        obj_lines.append("%s (%s) in %s %s" % (nid, ntype, parent, state_str))

    # ── last goal posterior ──
    posterior_str = "no previous goal"
    if last_goal:
        posterior_str = "goal: %s | type: %s | result: %s" % (
            last_goal.get("task", "?"),
            last_goal.get("type", "?"),
            last_goal_result,
        )

    prompt = json.dumps({
        "step": step,
        "robot_room": _robot_room(observation, agent_id),
        "rooms_visited": ", ".join(sorted(memory._visited_rooms)),
        "unchecked_rooms": ", ".join(sorted(memory.unchecked_rooms())),
        "room_beliefs": "\n".join(room_lines),
        "visible_deviations": "\n".join(dev_lines) or "(none)",
        "visible_objects": "\n".join(obj_lines),
        "last_goal_posterior": posterior_str,
        "task": (
            "You are the goal proposer for a home service robot. The belief "
            "state below is maintained by data-driven Active Inference and is "
            "READ-ONLY for you — do NOT suggest modifying it.\n\n"
            "Propose 3-5 candidate goals the robot should consider next. Each "
            "goal MUST have: task (short string), "
            "type (skill/restore_initial_position/explore/patrol), "
            "target (node_id or room_id), room (which room to go to).\n"
            "Prefer concrete, actionable goals over vague exploration.\n\n"
            "Additionally return \"room_observations\": a dict mapping each "
            "VISIBLE room's id to its urgency observation class inferred from "
            "the current scene — 0=low/normal, 1=medium, 2=high.  This is "
            "observation compression ONLY: you choose the discrete symbol the "
            "scene implies.  You must NOT output beliefs, probabilities, "
            "confidence values, or anything that would modify the belief "
            "state or the generative model.  If a goal just finished, the "
            "symbol you give for its target room doubles as the POSTERIOR "
            "observation of that goal's effect — report what the scene "
            "actually shows now (did the issue resolve, or is it still bad?).\n\n"
            "Return JSON: {\"goals\": [...], \"room_observations\": {\"room_id\": 0|1|2}}"
        ),
    }, ensure_ascii=True)

    try:
        answer = llm_fn(
            system_prompt="Return only valid JSON. No markdown, no explanation.",
            user_query=prompt,
            agent=agent_model,
            timeout=60,
        )
        payload = json.loads(answer)
        if isinstance(payload, dict):
            return {
                "goals": payload.get("goals", []),
                "room_observations": payload.get("room_observations", {}) or {},
            }
        return {"goals": [], "room_observations": {}}
    except Exception:
        return {"goals": [], "room_observations": {}}


# ============================================================
# EfeLoop
# ============================================================

class EfeLoop:
    def __init__(self, baseline: dict[str, Any], *,
                 agent_id: str = "robot_01",
                 agent_model: str = "vllm-qwen3.5-9b",
                 tau: int = 50, beta: float = 0.15,
                 total_steps: int = 1600,
                 efe_mode: str = "generative",
                 goal_authority: str = "current",
                 candidate_source: str = "hybrid",
                 selection_seed: int = 0,
                 goal_outcome_learning: bool = True,
                 explore_navigation: str = "v1",
                 preference_c: Any = None,
                 engine_ranked_fn: Any = None,
                 engine_node_index_fn: Any = None,
                 engine_scene_node_index_fn: Any = None):
        self.agent_id = agent_id
        self.agent_model = agent_model
        self.tau = tau
        self.beta = beta
        self.total_steps = total_steps
        self.baseline = baseline
        if goal_authority not in {"current", "efe_all", "rule_all", "random_all"}:
            raise ValueError("unsupported EFE goal authority: %s" % goal_authority)
        if candidate_source not in {"hybrid", "skill_only"}:
            raise ValueError("unsupported EFE candidate source: %s" % candidate_source)
        if explore_navigation not in {"v1", "llm"}:
            raise ValueError(
                "unsupported EFE explore navigation: %s" % explore_navigation)
        self.goal_authority = goal_authority
        self.candidate_source = candidate_source
        self.explore_navigation = explore_navigation
        self._selection_rng = random.Random(int(selection_seed))
        self.goal_outcome_learning = bool(goal_outcome_learning)

        self._engine_ranked_fn = engine_ranked_fn
        self._engine_node_index_fn = engine_node_index_fn
        self._engine_scene_node_index_fn = engine_scene_node_index_fn

        self.world_belief = WorldBelief.from_baseline(baseline)
        self._room_last_seen: dict[str, int] = {}
        self._room_last_visited: dict[str, int] = {}
        self._room_visit_count: dict[str, int] = {}
        self._last_physical_room: str = ""
        self._all_rooms: set[str] = set()
        self._visited_rooms: set[str] = set()
        for node in baseline.get("nodes") or []:
            if isinstance(node, dict) and str(node.get("node_type") or "") == "room":
                rid = str(node.get("id") or "")
                if rid:
                    self._all_rooms.add(rid)

        self._failed_targets: dict[str, int] = {}
        self._last_goal: dict[str, Any] | None = None
        self._last_goal_result: str = "started"
        self._goal_commit_step: int = -999

        # Scoring mode (1.8 division of labour): "generative" is the TRUE EFE —
        # risk + ambiguity from the A/B/C model, the rational-selection layer.
        # "phase1" = -(P + E + beta*N) hybrid is kept only as a thesis comparison
        # baseline.  The LLM proposes goals but can never rewrite the belief or
        # the EFE inputs (handoff §1.7 iron law).
        self.efe_mode: str = efe_mode
        self.preference_c = preference_c
        self.generative_model: GenerativeModel = graphworld_model(C=preference_c)
        self.goal_outcome_model = GoalOutcomeModel()
        self.goal_transition_model = HierarchicalGoalTransitionModel()

        # Debug logging: EFE_DEBUG=1 prints goal selection + belief on every
        # re-selection and emergency events; =2 additionally prints every step.
        self.debug: int = int(os.environ.get("EFE_DEBUG", "0") or 0)
        # EFE_CANDIDATE_LOG=1 records the full scored candidate table (task,
        # signature, state prior, score decomposition) into step_authority for
        # offline counterfactual re-scoring.  Pure observation: the selection
        # logic is untouched.
        self._candidate_log = os.environ.get("EFE_CANDIDATE_LOG", "0") == "1"
        self._debug_last_task: str = ""

        # Goal lifecycle state: anti-thrash cooldown per failed target, and
        # the last *finished* goal (for the LLM proposer's posterior).
        self._goal_fail_step: dict[str, int] = {}
        self._last_finished_goal: dict[str, Any] | None = None
        self._last_finished_result: str = "started"
        # A finished goal whose transition learning awaits the LLM's posterior
        # observation (resolved in the same step's goal-switch branch; None if
        # nothing is pending).
        self._pending_transition: tuple[dict[str, Any], str] | None = None

        # LLM-proposed candidate goals (populated at goal-switching time)
        self._llm_candidate_goals: list[dict[str, Any]] = []

        # Goal-authority experiment telemetry.  These counters deliberately
        # live in EfeLoop, where direct pipeline commits and selector commits
        # can both be observed without reconstructing them from action logs.
        self._authority_stats: dict[str, Any] = {
            "goal_commitments": 0,
            "selection_opportunities": 0,
            "efe_selections": 0,
            "rule_selections": 0,
            "random_selections": 0,
            "pipeline_direct_commits": 0,
            "goal_completions": 0,
            "goal_stuck_failures": 0,
            "goal_no_progress_failures": 0,
            "goal_hard_timeout_failures": 0,
            "goal_progress_events": 0,
            "transient_drop_constraints": 0,
            "goal_switches": 0,
            "same_target_reselections": 0,
            "goal_reversal_count": 0,
            "goal_conflict_count": 0,
            "conflicting_candidates_removed": 0,
            "single_candidate_opportunities": 0,
            "phase_done_action_count": 0,
            "completed_goal_duration_total": 0,
            "failed_goal_duration_total": 0,
            "efe_score_tie_opportunities": 0,
            "llm_action_calls": 0,
            "llm_action_successes": 0,
            "pipeline_candidates_scored": 0,
            "total_candidates_at_selection": 0,
            "selected_source_counts": {},
            "selected_goal_family_counts": {},
        }
        self._explore_navigation_stats: dict[str, int] = {
            "decisions": 0,
            "overrides": 0,
            "move_next_room": 0,
            "open_connecting_door": 0,
            "move_connecting_door": 0,
            "fallbacks": 0,
            "arrivals": 0,
        }
        self._last_committed_key: tuple[str, str, str] | None = None
        self._last_committed_target: str = ""
        self._last_target_by_object: dict[str, str] = {}
        self._step_authority: dict[str, Any] = {}

    @staticmethod
    def _goal_key(goal: dict[str, Any] | None) -> tuple[str, str, str]:
        goal = goal or {}
        return (
            str(goal.get("type") or goal.get("skill") or ""),
            str(goal.get("target") or goal.get("object") or ""),
            str(goal.get("task") or ""),
        )

    def _commit_goal(self, goal: dict[str, Any], step: int,
                     selected_by: str, candidate_count: int = 0) -> None:
        """Commit a genuinely new high-level goal and update audit counters."""
        key = self._goal_key(goal)
        if key == self._goal_key(self._last_goal):
            return
        target = str(goal.get("target") or goal.get("object") or "")
        object_id = str(goal.get("object") or "")
        if self._last_committed_key is not None:
            self._authority_stats["goal_switches"] += 1
        if target and target == self._last_committed_target:
            self._authority_stats["same_target_reselections"] += 1
        previous_object_target = self._last_target_by_object.get(object_id, "")
        if object_id and previous_object_target and previous_object_target != target:
            self._authority_stats["goal_reversal_count"] += 1
        if object_id and target:
            self._last_target_by_object[object_id] = target
        self._authority_stats["goal_commitments"] += 1
        counter_key = {
            "efe": "efe_selections",
            "rule": "rule_selections",
            "random": "random_selections",
            "pipeline_direct": "pipeline_direct_commits",
        }[selected_by]
        self._authority_stats[counter_key] += 1
        source = str(goal.get("_candidate_source") or
                     ("pipeline" if selected_by == "pipeline_direct" else "unknown"))
        source_counts = self._authority_stats["selected_source_counts"]
        source_counts[source] = int(source_counts.get(source, 0)) + 1
        family = (goal_signature(goal).family
                  if self.efe_mode == "goal_conditioned_b"
                  else goal_family(goal))
        family_counts = self._authority_stats["selected_goal_family_counts"]
        family_counts[family] = int(family_counts.get(family, 0)) + 1
        self._last_committed_key = key
        self._last_committed_target = target
        goal = dict(goal)
        goal["_committed_step"] = int(step)
        goal["last_progress_step"] = int(step)
        goal["steps_without_progress"] = 0
        self._last_goal = goal
        self._goal_commit_step = step
        self._step_authority.update({
            "decision_made": 1,
            "selected_by": selected_by,
            "selected_source": source,
            "selected_task": str(goal.get("task") or ""),
            "selected_target": target,
            "candidate_count": int(candidate_count),
        })

    def authority_diagnostics(self) -> dict[str, Any]:
        stats = copy.deepcopy(self._authority_stats)
        commitments = int(stats["goal_commitments"])
        stats["efe_coverage"] = (
            float(stats["efe_selections"]) / commitments if commitments else 0.0
        )
        stats["goal_stuck_rate"] = (
            float(stats["goal_stuck_failures"]) / commitments
            if commitments else 0.0
        )
        opportunities = int(stats["selection_opportunities"])
        stats["mean_candidates_per_selection"] = (
            float(stats["total_candidates_at_selection"]) / opportunities
            if opportunities else 0.0
        )
        stats["single_candidate_rate"] = (
            float(stats["single_candidate_opportunities"]) / opportunities
            if opportunities else 0.0
        )
        stats["efe_score_tie_rate"] = (
            float(stats["efe_score_tie_opportunities"]) / opportunities
            if opportunities else 0.0
        )
        completed = int(stats["goal_completions"])
        failed = int(stats["goal_stuck_failures"])
        stats["mean_completed_goal_duration"] = (
            float(stats["completed_goal_duration_total"]) / completed
            if completed else 0.0
        )
        stats["mean_failed_goal_duration"] = (
            float(stats["failed_goal_duration_total"]) / failed
            if failed else 0.0
        )
        stats["goal_authority"] = self.goal_authority
        stats["candidate_source"] = self.candidate_source
        stats["efe_mode"] = self.efe_mode
        nav = copy.deepcopy(self._explore_navigation_stats)
        nav_decisions = int(nav["decisions"])
        stats.update({
            "explore_navigation_variant": (
                "efe_explore_navigation_v1"
                if self.explore_navigation == "v1" else "llm"
            ),
            **{"explore_navigation_%s" % key: value
               for key, value in nav.items()},
            "explore_navigation_override_rate": (
                float(nav["overrides"]) / nav_decisions
                if nav_decisions else 0.0
            ),
            "explore_navigation_fallback_rate": (
                float(nav["fallbacks"]) / nav_decisions
                if nav_decisions else 0.0
            ),
        })
        stats["goal_outcome_learning"] = self.goal_outcome_learning
        stats["goal_family_beliefs"] = self.goal_outcome_model.to_dict()
        stats["goal_transition_model"] = self.goal_transition_model.diagnostics()
        return stats

    def _refresh_held_goal(self, scene: dict[str, Any], step: int) -> None:
        """Refresh execution fields and update progress-based lifecycle state.

        Progress is deliberately observable and task-agnostic: a phase change,
        object relocation, or robot relocation is evidence that the selected
        Goal is advancing.  Merely spending another step on the same Goal is
        not.  This keeps long workflows alive while terminating loops.
        """
        if self._last_goal is None:
            return
        previous = self._last_goal
        committed_step = int(
            previous.get("_committed_step", self._goal_commit_step))
        refreshed = refresh_goal_snapshot(previous, scene, self.agent_id)
        refreshed["_candidate_source"] = previous.get(
            "_candidate_source", "unknown")
        refreshed["_committed_step"] = committed_step
        semantic_progress = any(
            str(refreshed.get(field) or "") != str(previous.get(field) or "")
            for field in ("phase", "object_parent")
        )
        old_room = str(previous.get("robot_room") or "")
        new_room = str(refreshed.get("robot_room") or "")
        planned_next = str(previous.get("next_room") or "")
        destination = str(
            previous.get("target_room") or previous.get("room") or "")
        navigation_progress = bool(
            old_room and new_room and old_room != new_room
            and (
                new_room == planned_next
                or (
                    destination
                    and self._room_distance(new_room, destination)
                    < self._room_distance(old_room, destination)
                )
            )
        )
        progressed = semantic_progress or navigation_progress
        if self.debug >= 2 and progressed:
            changed = [
                "%s:%s->%s" % (
                    field, previous.get(field, ""), refreshed.get(field, ""))
                for field in ("phase", "object_parent", "robot_room")
                if str(previous.get(field) or "")
                != str(refreshed.get(field) or "")
            ]
            self._debug_log(
                "PROGRESS step=%d reason=%s next=%s destination=%s" % (
                    step, ",".join(changed) or "planned_navigation",
                    planned_next, destination))
        if progressed:
            refreshed["last_progress_step"] = int(step)
            refreshed["steps_without_progress"] = 0
            self._authority_stats["goal_progress_events"] += 1
        else:
            refreshed["last_progress_step"] = int(
                previous.get("last_progress_step", committed_step))
            refreshed["steps_without_progress"] = int(
                previous.get("steps_without_progress", 0)) + 1
        self._last_goal = refreshed

    # ----- Room tracking -----
    def unchecked_rooms(self) -> set[str]:
        return self._all_rooms - self._visited_rooms

    def stale_rooms(self, step: int, threshold: int = 50) -> set[str]:
        return {r for r, last in self._room_last_seen.items()
                if step - last > threshold}

    def update_memory(self, observation: dict[str, Any], step: int) -> None:
        robot_room = _robot_room(observation, self.agent_id)
        for node in observation.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            ntype = str(node.get("node_type") or "")
            nid = str(node.get("id") or "")
            if ntype == "room" and nid:
                self._room_last_seen[nid] = step
        if robot_room:
            self._visited_rooms.add(robot_room)
            self._room_last_seen[robot_room] = step
            self._room_last_visited[robot_room] = step
            if robot_room != self._last_physical_room:
                self._room_visit_count[robot_room] = \
                    self._room_visit_count.get(robot_room, 0) + 1
                self._last_physical_room = robot_room

    def _room_distance(self, source: str, target: str) -> int:
        """Shortest number of baseline room edges, or a bounded fallback."""
        if not source or not target or source == target:
            return 0
        graph: dict[str, set[str]] = {room: set() for room in self._all_rooms}
        for edge in self.baseline.get("edges") or []:
            if not isinstance(edge, dict):
                continue
            relation = str(edge.get("relation") or "").lower()
            if relation not in {"connected", "connected_to", "next_to", "neighbour"}:
                continue
            left = str(edge.get("source_id") or "")
            right = str(edge.get("target_id") or "")
            if left in graph and right in graph:
                graph[left].add(right)
                graph[right].add(left)
        queue: deque[tuple[str, int]] = deque([(source, 0)])
        seen = {source}
        while queue:
            room, distance = queue.popleft()
            for neighbor in sorted(graph.get(room, ())):
                if neighbor == target:
                    return distance + 1
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append((neighbor, distance + 1))
        return 6

    def _enrich_goal_decision_features(
        self, goal: dict[str, Any], robot_room: str,
    ) -> dict[str, Any]:
        enriched = dict(goal)
        destination = str(
            enriched.get("object_room") or enriched.get("target_room")
            or enriched.get("room") or ""
        )
        if goal_family(enriched) == "explore":
            destination = str(enriched.get("target_room") or enriched.get("room")
                              or enriched.get("target") or "")
        enriched["_path_distance"] = self._room_distance(robot_room, destination)
        enriched["_visit_count"] = self._room_visit_count.get(destination, 0)
        return enriched

    def _attach_goal_transition_features(
        self, goal: dict[str, Any], scene: dict[str, Any],
        deviations: list[dict[str, Any]],
        observation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Attach stable signature and Q(s) used at score and learning time."""
        enriched = enrich_goal_signature(goal, scene, self.baseline)
        if goal_signature(enriched).action_kind == "task":
            try:
                enriched["_efe_target_issue_before"] = goal_still_needed(
                    enriched, observation or {}, scene, self.baseline,
                    robot_id=self.agent_id)
            except Exception:
                enriched["_efe_target_issue_before"] = None
        enriched["_efe_state_prior"] = self.goal_transition_model.state_prior(
            enriched, deviations, self.world_belief).tolist()
        return enriched

    def _exploration_goals(self, observation: dict[str, Any], step: int,
                           limit: int = 2) -> list[dict[str, Any]]:
        """Always expose a small, deterministic set of physical patrol goals."""
        robot_room = _robot_room(observation, self.agent_id)
        rooms = [room for room in self._all_rooms if room != robot_room]
        rooms.sort(key=lambda room: (
            0 if room not in self._visited_rooms else 1,
            self._room_last_visited.get(room, -10**9),
            room,
        ))
        return [self._enrich_goal_decision_features({
            "type": "explore",
            "task": "explore %s" % room,
            "target": room,
            "room": room,
            "object_room": room,
            "target_room": room,
            "robot_room": robot_room,
            "_candidate_source": "explore",
        }, robot_room) for room in rooms[:max(0, int(limit))]]

    def _maintenance_goal(self, observation: dict[str, Any]) -> dict[str, Any]:
        room = _robot_room(observation, self.agent_id)
        return self._enrich_goal_decision_features({
            "type": "maintain",
            "task": "maintain_order",
            "target": room,
            "room": room,
            "target_room": room,
            "robot_room": room,
            "_candidate_source": "maintain",
        }, room)

    def _resolve_candidate_conflicts(
        self, goals: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Deduplicate goals and enforce one destination/owner per object."""
        unique: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str, str]] = set()
        for goal in goals:
            key = self._goal_key(goal)
            if key in seen_keys:
                self._authority_stats["conflicting_candidates_removed"] += 1
                continue
            seen_keys.add(key)
            unique.append(goal)

        grouped: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        for index, goal in enumerate(unique):
            object_id = str(goal.get("object") or "")
            if object_id:
                grouped.setdefault(object_id, []).append((index, goal))

        remove_ids: set[int] = set()
        for entries in grouped.values():
            targets = {str(goal.get("target") or "") for _, goal in entries}
            if len(targets) <= 1:
                continue
            self._authority_stats["goal_conflict_count"] += 1
            # A specialised lifecycle skill owns the object over a generic
            # baseline restore.  Source priority breaks ties deterministically.
            source_priority = {"pipeline": 0, "pipeline_skill": 0,
                               "skill": 1, "llm": 2, "unknown": 3}
            winner_index, _ = min(entries, key=lambda pair: (
                0 if str(pair[1].get("type") or "") == "skill" else 1,
                source_priority.get(
                    str(pair[1].get("_candidate_source") or "unknown"), 3),
                pair[0],
            ))
            for index, goal in entries:
                if index != winner_index:
                    remove_ids.add(id(goal))
        self._authority_stats["conflicting_candidates_removed"] += len(remove_ids)
        return [goal for goal in unique if id(goal) not in remove_ids]

    # ----- Dirichlet self-evolution (1.8: learning corrects the world model) -----
    def _debug_log(self, *parts: Any) -> None:
        """Print a line prefixed with [efe] when debug logging is enabled."""
        if self.debug:
            print("[efe] " + " ".join(str(p) for p in parts))

    def _room_risk(self, room_id: str) -> float:
        """P(needs_attention) prior for a room, from the Beta posterior."""
        if room_id and room_id in self.world_belief:
            return self.world_belief[room_id].risk_confidence
        return 0.5

    def _goal_achieved(self, goal: dict[str, Any],
                       observation: dict[str, Any],
                       deviations: list[dict[str, Any]],
                       scene: dict[str, Any] | None = None,
                       *, step: int | None = None) -> bool:
        """True when the held goal is actually done — honest completion check.

        explore/patrol : the target room has been *visited* (in memory), not
                         just "cleared by the pipeline"
        skill/restore  : the goal's own detector no longer fires — the world no
                         longer exhibits the issue the goal targets (rebuilt
                         against the current scene via goal_still_needed)
        other          : the target node no longer appears in the visible
                         deviation set
        """
        gtype = str(goal.get("type") or "")
        target = str(goal.get("target") or "")
        if gtype in ("explore", "patrol"):
            room = str(goal.get("target_room") or goal.get("room") or target or "")
            committed = int(goal.get("_committed_step", self._goal_commit_step))
            return self._room_last_visited.get(room, -10**9) >= committed
        if gtype in ("maintain", "idle", "wait"):
            committed = int(goal.get("_committed_step", self._goal_commit_step))
            # Maintain is a one-step temporal action: observe the next world
            # state, then close the transition.  Requiring a room change made
            # an intentional wait falsely remain active until timeout.
            return step is not None and step > committed
        if str(goal.get("phase") or "") == "done":
            return True
        if scene is not None:
            try:
                still = goal_still_needed(
                    goal, observation, scene, self.baseline,
                    robot_id=self.agent_id)
                if still is not None:
                    return not still
                if gtype in ("skill", "restore_initial_position"):
                    # Under partial observability, absence from a visible
                    # detector is not proof that a structured goal completed.
                    return False
            except Exception:
                pass
        if not target:
            return False
        return not any(str(d.get("node_id") or "") == target
                       for d in (deviations or []))

    def _learn_from_observation(self, observation: dict[str, Any],
                                deviations: list[dict[str, Any]]) -> None:
        """A-learning: correct P(urgency-class | room state) from what is seen.

        Deviated rooms feed their compressed urgency symbol; visible rooms
        without a deviation feed 'low'.  This is the passive (no action
        context) Dirichlet update — the world model drifts toward the agent's
        real experience (handoff §1.5 / 1.8).
        """
        dev_rooms = set()
        for d in deviations or []:
            room = str(d.get("room") or "")
            if not room:
                continue
            dev_rooms.add(room)
            o_obs = urgency_to_obs(float(d.get("urgency", 0.0)))
            Q_prior = np.array([self._room_risk(room), 1.0 - self._room_risk(room)])
            self.generative_model.learn_observation(o_obs, Q_prior)
        for node in observation.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            if str(node.get("node_type") or "") != "room":
                continue
            room = str(node.get("id") or "")
            if not room or room in dev_rooms:
                continue
            Q_prior = np.array([self._room_risk(room), 1.0 - self._room_risk(room)])
            self.generative_model.learn_observation(0, Q_prior)   # seen clean -> low

    def _learn_from_llm_observations(self, payload: dict[str, Any],
                                     step: int,
                                     exclude_room: str = "") -> int:
        """LLM-as-observation-compressor (1.8: one of the three intelligence
        locations).  At goal-switch time the LLM reads the scene and emits a
        discrete urgency observation symbol per visible room; those symbols go
        through the *same* data-driven pipeline as real observations:
          - A: learn_observation(o_obs, Q_prior)  (Dirichlet on the likelihood)
          - belief: Beta evidence via a FIXED designer-set symbol→weight map
        The LLM never writes a number — it only chooses which observation class
        the scene implies.  `exclude_room` skips the just-finished goal's room,
        whose symbol is consumed by _resolve_pending_transition instead (full
        action-context learn, no double A update).  Returns the number of
        belief updates applied.
        """
        room_obs = payload.get("room_observations") or {}
        applied = 0
        for room, o_raw in room_obs.items():
            room = str(room)
            if exclude_room and room == exclude_room:
                continue
            try:
                o_obs = int(round(float(o_raw)))
            except (TypeError, ValueError):
                continue
            if o_obs not in (0, 1, 2) or not room:
                continue
            Q_prior = np.array([self._room_risk(room), 1.0 - self._room_risk(room)])
            self.generative_model.learn_observation(o_obs, Q_prior)
            # fixed symbol→evidence map (designer-set, not LLM-controlled)
            if o_obs == 2:
                outcome, weight = "support", 0.5
            elif o_obs == 1:
                outcome, weight = "support", 0.3
            else:
                outcome, weight = "refute", 0.3
            if self.world_belief.update(room, outcome, weight,
                                        evidence_key="llm:%d:%s" % (step, room),
                                        step=step):
                applied += 1
            if self.debug >= 1:
                self._debug_log("LLM-OBS %s=o%d -> %s w=%.1f" % (
                    room, o_obs, outcome, weight))
        return applied

    def _resolve_pending_transition(self, room_obs: dict[str, Any],
                                    step: int) -> None:
        """Turn a finished goal's *posterior observation* into B/A learning.

        The LLM judges what the scene actually shows after the goal executed
        (its room_observations entry for the target room).  That symbol o_post
        goes through the full Bayes perception→learning step
        `learn(a, Q_prior, o_post)` — infer then update both A and B for the
        executed action `a` (1.8: the LLM only reports the observation, the
        math converts it into the state posterior and the parameter update).
        If no symbol was emitted (LLM silent/failed), fall back to the
        designer's hardcoded posterior (completed -> resolved, failed ->
        still needs attention).
        """
        if self._pending_transition is None:
            return
        goal, result = self._pending_transition
        self._pending_transition = None
        room = str(goal.get("room") or goal.get("target_room")
                   or goal.get("object_room") or "")
        if not room:
            return
        a = goal_action_index(goal)
        Q_prior = np.array([self._room_risk(room), 1.0 - self._room_risk(room)])
        try:
            o_post = int(round(float(room_obs.get(room, -1))))
        except (TypeError, ValueError):
            o_post = -1
        if o_post in (0, 1, 2):
            self.generative_model.learn(a, Q_prior, o_post)
            if self.debug >= 1:
                self._debug_log("POSTERIOR %s a=%d o=%d (llm)" % (room, a, o_post))
        else:
            # fallback: designer's hardcoded posterior
            self._learn_transition_from_goal(goal, result)
            if self.debug >= 1:
                self._debug_log("POSTERIOR %s a=%d fallback=%s" % (room, a, result))

    def _learn_transition_from_goal(self, goal: dict[str, Any] | None,
                                    result: str) -> None:
        """B-learning: correct P(state' | state, action) from the goal outcome.

        The executed goal's action slice accrues a transition from the prior
        belief to a soft posterior read off the outcome (completed -> resolved,
        failed -> still needs attention).  Structured transition counts by goal
        type (handoff Phase 3) — the same action index the scorer used.
        """
        if not goal or result == "started":
            return
        room = str(goal.get("room") or goal.get("target_room")
                   or goal.get("object_room") or "")
        if not room:
            return
        a = goal_action_index(goal)
        Q_prior = np.array([self._room_risk(room), 1.0 - self._room_risk(room)])
        if result == "completed":
            Q_post = np.array([0.2, 0.8])      # resolved -> normal-heavy
        elif result.startswith("failed"):
            Q_post = np.array([0.8, 0.2])      # still needs attention
        else:
            return
        self.generative_model.learn_transition(a, Q_prior, Q_post)

    # ----- cross-run transfer (Phase 3: WorldBelief + A/B/C model) -----
    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "efe_mode": self.efe_mode,
            "goal_authority": self.goal_authority,
            "candidate_source": self.candidate_source,
            "explore_navigation": self.explore_navigation,
            "goal_outcome_learning": self.goal_outcome_learning,
            "preference_c": (list(self.preference_c)
                             if self.preference_c is not None else None),
            "world_belief": self.world_belief.to_dict(),
            "generative_model": self.generative_model.to_dict(),
            "goal_outcome_model": self.goal_outcome_model.to_dict(),
            "goal_transition_model": self.goal_transition_model.to_dict(),
            "failed_targets": dict(self._failed_targets),
            "goal_fail_step": dict(self._goal_fail_step),
            "visited_rooms": sorted(self._visited_rooms),
            "room_last_seen": dict(self._room_last_seen),
            "room_last_visited": dict(self._room_last_visited),
            "room_visit_count": dict(self._room_visit_count),
            "last_physical_room": self._last_physical_room,
            "authority_stats": copy.deepcopy(self._authority_stats),
            "explore_navigation_stats": copy.deepcopy(
                self._explore_navigation_stats),
            "last_target_by_object": dict(self._last_target_by_object),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any],
                  baseline: dict[str, Any]) -> EfeLoop:
        pref_c = data.get("preference_c")
        if pref_c is not None:
            pref_c = np.asarray(pref_c, dtype=float)
        loop = cls(baseline, agent_id=data.get("agent_id", "robot_01"),
                   efe_mode=data.get("efe_mode", "generative"),
                   goal_authority=data.get("goal_authority", "current"),
                   candidate_source=data.get("candidate_source", "hybrid"),
                   explore_navigation=data.get("explore_navigation", "v1"),
                   goal_outcome_learning=data.get("goal_outcome_learning", True),
                   preference_c=pref_c)
        loop.world_belief = WorldBelief.from_dict(data["world_belief"])
        loop.generative_model = GenerativeModel.from_dict(data["generative_model"])
        loop.goal_outcome_model = GoalOutcomeModel.from_dict(
            data.get("goal_outcome_model", {}))
        loop.goal_transition_model = HierarchicalGoalTransitionModel.from_dict(
            data.get("goal_transition_model", {}))
        loop._failed_targets = dict(data.get("failed_targets", {}))
        loop._goal_fail_step = {str(k): int(v)
                                for k, v in data.get("goal_fail_step", {}).items()}
        loop._visited_rooms = set(data.get("visited_rooms", []))
        loop._room_last_seen = {str(k): int(v)
                                for k, v in data.get("room_last_seen", {}).items()}
        loop._room_last_visited = {
            str(k): int(v) for k, v in data.get("room_last_visited", {}).items()
        }
        loop._room_visit_count = {
            str(k): int(v) for k, v in data.get("room_visit_count", {}).items()
        }
        loop._last_physical_room = str(data.get("last_physical_room") or "")
        loop._authority_stats.update(copy.deepcopy(data.get("authority_stats", {})))
        loop._explore_navigation_stats.update(copy.deepcopy(
            data.get("explore_navigation_stats", {})))
        loop._last_target_by_object = {
            str(k): str(v) for k, v in data.get("last_target_by_object", {}).items()
        }
        return loop

    # ----- main step -----
    def step(self, observation: dict[str, Any],
             candidates: list[dict[str, Any]],
             step: int,
             deviations: list[dict[str, Any]] | None = None,
             active_goal: dict[str, Any] | None = None,
             pipeline_goals: list[dict[str, Any]] | None = None,
             world_scene: dict[str, Any] | None = None,
             recent_events: str = "",
             goal: str = "",
             llm_fn: Any = None,
             ) -> dict[str, Any]:

        if deviations is None:
            deviations = []
        pipeline_goals = list(pipeline_goals or [])
        if active_goal is not None:
            pipeline_goals.insert(0, active_goal)
        self._step_authority = {
            "decision_made": 0,
            "selected_by": "held",
            "selected_source": "",
            "selected_task": "",
            "selected_target": "",
            "candidate_count": 0,
        }
        # enrich deviations with room info
        for d in deviations:
            if not d.get("room"):
                nid = str(d.get("node_id") or "")
                for node in observation.get("nodes") or []:
                    if isinstance(node, dict) and str(node.get("id") or "") == nid:
                        d["room"] = str(node.get("parent") or "")
                        break
        self.update_memory(observation, step)

        # ── data-driven perception: visible deviations update the belief ──
        # (handoff Phase 1 #2 / §2.3 #6 — the world, not the LLM, writes belief)
        observe_deviations(self.world_belief, deviations, step)
        # ── Dirichlet A-learning: the world model learns from the same signal ──
        # (1.8: learning corrects the model; observation compression at work)
        self._learn_from_observation(observation, deviations)

        # ── detect goal completion ──
        # If experiment pipeline cleared active_goal, the previous goal completed.
        previous_active = getattr(self, "_prev_active_goal", None)
        if previous_active is not None and active_goal is None:
            # goal was cleared → completed (or stuck, but either way: posterior)
            pass
        self._prev_active_goal = active_goal

        # ── track failed targets ──
        if self._last_goal and deviations:
            last_target = self._last_goal.get("target", "")
            if last_target:
                still_deviated = any(
                    str(d.get("node_id") or "") == last_target
                    for d in deviations
                )
                if still_deviated:
                    self._failed_targets[last_target] = \
                        self._failed_targets.get(last_target, 0) + 1

        # ── goal commitment ──
        EMERGENCY_URGENCY = 8.0
        emergency = any(
            float(d.get("urgency", 0)) >= EMERGENCY_URGENCY
            for d in (deviations or [])
        )
        if self.debug >= 1 and emergency:
            top = max((float(d.get("urgency", 0)) for d in (deviations or [])),
                      default=0.0)
            self._debug_log("EMERGENCY step=%d top_urgency=%.1f" % (step, top))

        current_scene = (
            copy.deepcopy(world_scene)
            if isinstance(world_scene, dict)
            else _merge_observation_scene(self.baseline, observation)
        )

        # Refresh execution fields and progress counters before lifecycle
        # checks.  A phase/object/robot transition resets the no-progress
        # clock; long workflows are therefore not failed merely for being long.
        self._refresh_held_goal(current_scene, step)

        # ── EFE-owned goal lifecycle: complete / stuck check ──
        # EFE owns the full lifecycle of the goal it holds, whether that goal
        # came from its own selection or was adopted from the pipeline.  In efe
        # mode run_experiment.py never clears active_goals, so this check must
        # NOT depend on `active_goal is None` — otherwise a pipeline goal would
        # be held forever and EFE would never re-select (the "架空" failure).
        if self._last_goal is not None:
            held_done = self._goal_achieved(
                self._last_goal, observation, deviations, current_scene,
                step=step)
            no_progress = int(
                self._last_goal.get("steps_without_progress", 0)
            ) >= GOAL_NO_PROGRESS_STEPS
            hard_timeout = (
                step - self._goal_commit_step >= GOAL_MAX_DURATION_STEPS)
            held_stuck = no_progress or hard_timeout
            if held_done or held_stuck:
                result = "completed" if held_done else "failed"
                if held_done:
                    self._authority_stats["goal_completions"] += 1
                    self._authority_stats["completed_goal_duration_total"] += max(
                        0, step - self._goal_commit_step)
                else:
                    self._authority_stats["goal_stuck_failures"] += 1
                    if no_progress:
                        self._authority_stats["goal_no_progress_failures"] += 1
                    if hard_timeout:
                        self._authority_stats["goal_hard_timeout_failures"] += 1
                    self._authority_stats["failed_goal_duration_total"] += max(
                        0, step - self._goal_commit_step)
                tgt = str(self._last_goal.get("target") or "")
                if result == "failed" and tgt:
                    self._goal_fail_step[tgt] = step
                self._last_finished_goal = self._last_goal
                self._last_finished_result = result
                goal_duration = max(0, step - self._goal_commit_step)
                if self.efe_mode == "goal_conditioned_b":
                    target_issue_after = None
                    if goal_signature(self._last_goal).action_kind == "task":
                        try:
                            target_issue_after = goal_still_needed(
                                self._last_goal, observation, current_scene,
                                self.baseline, robot_id=self.agent_id)
                        except Exception:
                            target_issue_after = None
                    self.goal_transition_model.learn(
                        self._last_goal, result, deviations,
                        update=self.goal_outcome_learning,
                        target_issue_after=target_issue_after)
                elif self.goal_outcome_learning:
                    self.goal_outcome_model.update(
                        self._last_goal, result, goal_duration)
                goal_outcome(self.world_belief, self._last_goal, result, step)
                # Transition (B) learning is deferred to the same step's
                # goal-switch, where the LLM's *posterior observation* of the
                # goal's effect is available — instead of the hardcoded
                # [0.2,0.8]/[0.8,0.2] posterior.
                self._pending_transition = (self._last_goal, result)
                if self.debug >= 1:
                    self._debug_log("GOAL %s %s step=%d" % (
                        result.upper(),
                        str(self._last_goal.get("task") or "")[:40], step))
                self._last_goal = None
                self._goal_commit_step = -999
                # record the just-finished goal's outcome in this step's audit
                # trail (pure observation; decision logic untouched)
                self._step_authority["goal_result"] = result
                self._step_authority["goal_result_task"] = str(
                    (self._last_finished_goal or {}).get("task") or "")

        # ── goal decision ──
        # The pipeline's active_goal commits DIRECTLY (pipeline authority over
        # which goal to run) — it is not scored as a candidate.  EFE still owns
        # the lifecycle above (completion / stuck / cooldown).  Two guards keep
        # that consistent: a pipeline goal already resolved is treated as absent
        # (so EFE re-selects instead of thrashing), and a goal that just failed
        # within the cooldown window is skipped the same way.
        fresh_pipeline_goals: list[dict[str, Any]] = []
        for raw_goal in pipeline_goals:
            refreshed = refresh_goal_snapshot(
                dict(raw_goal), current_scene, self.agent_id)
            refreshed["_candidate_source"] = "pipeline"
            handed_target = str(refreshed.get("target") or "")
            if self._goal_achieved(
                    refreshed, observation, deviations, current_scene,
                    step=step):
                continue
            if step - self._goal_fail_step.get(handed_target, -10**9) \
                    < GOAL_FAIL_COOLDOWN:
                continue
            fresh_pipeline_goals.append(refreshed)
        pipeline_handed = (
            self.goal_authority == "current"
            and self.efe_mode not in {"goal_conditioned", "goal_conditioned_b"}
            and self._last_goal is None
            and bool(fresh_pipeline_goals)
        )
        if pipeline_handed:
            chosen_goal = fresh_pipeline_goals[0]
            # The pipeline re-hands the SAME goal object every step; only reset
            # the commit step when the goal actually changes, otherwise
            # GOAL_STUCK_STEPS would never accumulate (stuck never fires).
            self._commit_goal(chosen_goal, step, "pipeline_direct", 1)
            chosen_goal = self._last_goal
        elif self._last_goal is not None:
            # self-commitment: keep executing the chosen goal until it
            # completes or stalls (also during emergencies).
            # Holding a wrong object is a *state-consistency constraint*, not a
            # preference: inject a drop goal rather than let the robot wander
            # off holding something the current goal didn't ask for.
            holding = ""
            for node in observation.get("nodes") or []:
                if isinstance(node, dict) and str(node.get("parent") or "") == self.agent_id:
                    holding = str(node.get("id") or "")
                    break
            expected = _expected_holding(self._last_goal)
            if holding and expected and holding != expected:
                # This is a one-step execution constraint, not a new Goal.
                # Keep the original commitment and its structured signature so
                # the eventual B observation is credited to the selected Goal.
                chosen_goal = _drop_goal(
                    holding, observation, self.baseline, self.agent_id)
                self._authority_stats["transient_drop_constraints"] += 1
            else:
                chosen_goal = self._last_goal
        else:
            # ── LLM proposes candidate goals + observation compression ──
            room_obs: dict[str, Any] = {}
            if llm_fn is not None and self.candidate_source == "hybrid":
                payload = _llm_propose_and_update(
                    observation, deviations, self.world_belief,
                    self, step, self._last_finished_goal,
                    self._last_finished_result,
                    llm_fn, self.agent_id, self.agent_model,
                )
                self._llm_candidate_goals = payload.get("goals", [])
                room_obs = payload.get("room_observations") or {}

            # LLM-as-observation-compressor (1.8): the just-finished goal's
            # room symbol is its *posterior observation* — consumed by the
            # transition learning (B, plus A via the full learn step).  Other
            # rooms' symbols do passive A-learning + Beta.  Both run exactly
            # once per switch (this branch only runs while no goal is held).
            pending_room = ""
            if self._pending_transition is not None:
                pending_room = str(
                    self._pending_transition[0].get("room")
                    or self._pending_transition[0].get("target_room")
                    or self._pending_transition[0].get("object_room") or "")
            self._resolve_pending_transition(room_obs, step)
            self._learn_from_llm_observations(
                {"room_observations": room_obs}, step,
                exclude_room=pending_room)

            # ── EFE scores candidates ──
            candidate_goals = []
            rr = _robot_room(observation, self.agent_id)

            # ① pipeline-derived skill goals (full execution detail)
            # EfeLoop only has baseline (initial) + observation (visible subset);
            # merge observation over baseline to approximate the current scene so
            # phase detection sees the object's real current parent/state.
            skill_goals = build_skill_goals(
                observation, current_scene, self.baseline,
                robot_id=self.agent_id, step=step,
            )
            for g in skill_goals:
                refreshed = refresh_goal_snapshot(g, current_scene, self.agent_id)
                if not refreshed.get("room"):
                    refreshed["room"] = refreshed.get("object_room", "")
                refreshed["_candidate_source"] = "skill"
                candidate_goals.append(self._enrich_goal_decision_features(
                    refreshed, rr))

            # ② LLM-proposed candidate goals
            for g in self._llm_candidate_goals:
                g = dict(g)
                if not g.get("robot_room"):
                    g["robot_room"] = rr
                if not g.get("room"):
                    g["room"] = g.get("target_room", "")
                if not g.get("object_room"):
                    g["object_room"] = g.get("room", "")
                if not g.get("target_room"):
                    g["target_room"] = g.get("room", "")
                g["_candidate_source"] = "llm"
                candidate_goals.append(self._enrich_goal_decision_features(g, rr))

            # ③ In the all-candidate authority conditions, the upstream
            # pipeline goal competes in exactly the same candidate pool.
            if (self.goal_authority != "current"
                    or self.efe_mode in {"goal_conditioned", "goal_conditioned_b"}):
                for pipeline_goal in fresh_pipeline_goals:
                    pipeline_goal = dict(pipeline_goal)
                    pipeline_goal["_candidate_source"] = "pipeline"
                    pipeline_goal = self._enrich_goal_decision_features(
                        pipeline_goal, rr)
                    pipeline_key = self._goal_key(pipeline_goal)
                    duplicate = next(
                        (g for g in candidate_goals
                         if self._goal_key(g) == pipeline_key),
                        None,
                    )
                    if duplicate is None:
                        candidate_goals.append(pipeline_goal)
                    else:
                        duplicate["_candidate_source"] = "pipeline_skill"
                    self._authority_stats["pipeline_candidates_scored"] += 1

            # ④ Exploration remains a real alternative even when repair
            # goals exist; at most two deterministic patrol candidates keep
            # the pool compact.
            candidate_goals.extend(self._exploration_goals(
                observation, step, limit=2))
            if self.efe_mode in {"goal_conditioned", "goal_conditioned_b"}:
                candidate_goals.append(self._maintenance_goal(observation))

            if self.efe_mode == "goal_conditioned_b":
                pending_task_count = sum(
                    1 for goal_item in candidate_goals
                    if goal_signature(goal_item, current_scene, self.baseline).family
                    not in {"explore", "maintain"}
                )
                for goal_item in candidate_goals:
                    if goal_signature(
                            goal_item, current_scene, self.baseline
                    ).family in {"explore", "maintain"}:
                        goal_item["_pending_task_count"] = pending_task_count
                candidate_goals = [
                    self._attach_goal_transition_features(
                        goal_item, current_scene, deviations, observation)
                    for goal_item in candidate_goals
                ]

            # Enforce one owner/destination per object after all sources have
            # contributed.  This removes semantic reversals before scoring.
            candidate_goals = self._resolve_candidate_conflicts(candidate_goals)

            chosen_goal = None
            if candidate_goals:
                # Cooldown filtering is shared by EFE/rule/random so the
                # authority selector is the only experimental variable.
                eligible = [
                    g for g in candidate_goals
                    if not str(g.get("target") or "")
                    or step - self._goal_fail_step.get(
                        str(g.get("target") or ""), -10**9) >= GOAL_FAIL_COOLDOWN
                ] or candidate_goals
                self._authority_stats["selection_opportunities"] += 1
                self._authority_stats["total_candidates_at_selection"] += len(eligible)
                if len(eligible) == 1:
                    self._authority_stats["single_candidate_opportunities"] += 1
                self._step_authority["candidate_count"] = len(eligible)

                selector = "efe" if self.goal_authority in {"current", "efe_all"} \
                    else ("rule" if self.goal_authority == "rule_all" else "random")
                best = None
                if selector == "efe":
                    try:
                        scores = [
                            float(decompose_goal(
                                goal_item, deviations, self.world_belief,
                                efe_mode=self.efe_mode, beta=self.beta,
                                outcome_model=self.goal_outcome_model,
                                goal_transition_model=self.goal_transition_model)["G"])
                            for goal_item in eligible
                        ]
                        if len(scores) > 1:
                            best_score = min(scores)
                            if sum(abs(score - best_score) <= 1e-9
                                   for score in scores) > 1:
                                self._authority_stats[
                                    "efe_score_tie_opportunities"] += 1
                    except Exception:
                        pass
                    best = select_goal(eligible, deviations, self,
                                       self.world_belief, step, self.total_steps,
                                       tau=self.tau, beta=self.beta,
                                       efe_mode=self.efe_mode,
                                       outcome_model=self.goal_outcome_model,
                                       goal_transition_model=self.goal_transition_model)
                elif selector == "rule":
                    # Deterministic engine-like priority: pipeline first, then
                    # concrete skills, then LLM suggestions, then exploration;
                    # retain builder order within each source.
                    source_priority = {"pipeline": 0, "pipeline_skill": 0,
                                       "skill": 1, "llm": 2,
                                       "explore": 3, "maintain": 4,
                                       "unknown": 5}
                    chosen = min(
                        enumerate(eligible),
                        key=lambda pair: (
                            source_priority.get(
                                str(pair[1].get("_candidate_source") or "unknown"), 4),
                            pair[0],
                        ),
                    )[1]
                    best = (float("nan"), chosen)
                else:
                    chosen = eligible[self._selection_rng.randrange(len(eligible))]
                    best = (float("nan"), chosen)
                if best is not None:
                    _g_score, chosen_goal = best
                    self._commit_goal(chosen_goal, step, selector, len(eligible))
                    chosen_goal = self._last_goal
                    self._step_authority["selected_goal_family"] = goal_family(
                        chosen_goal) if self.efe_mode != "goal_conditioned_b" \
                        else goal_signature(chosen_goal).family
                    if selector == "efe":
                        self._step_authority["score_breakdown"] = decompose_goal(
                            chosen_goal, deviations, self.world_belief,
                            efe_mode=self.efe_mode, beta=self.beta,
                            outcome_model=self.goal_outcome_model,
                            goal_transition_model=self.goal_transition_model,
                        )
                    if self._candidate_log:
                        # Audit table of every scored candidate: structured
                        # signature, state prior and per-term score split.
                        # Replayed offline to re-rank with counterfactual
                        # (frozen-prior) B — read-only, selection untouched.
                        table: list[dict[str, Any]] = []
                        for g in eligible:
                            try:
                                dec = decompose_goal(
                                    g, deviations, self.world_belief,
                                    efe_mode=self.efe_mode, beta=self.beta,
                                    outcome_model=self.goal_outcome_model,
                                    goal_transition_model=self.goal_transition_model,
                                )
                            except Exception:
                                dec = {}
                            entry: dict[str, Any] = {
                                "task": str(g.get("task") or ""),
                                "type": str(g.get("type") or ""),
                                "source": str(
                                    g.get("_candidate_source") or ""),
                                "signature": goal_signature(g).key
                                if self.efe_mode == "goal_conditioned_b"
                                else "",
                                "prior": (
                                    [float(v) for v in g["_efe_state_prior"]]
                                    if isinstance(
                                        g.get("_efe_state_prior"),
                                        (list, tuple, np.ndarray))
                                    else None),
                            }
                            for key in ("risk", "ambiguity",
                                        "parameter_uncertainty",
                                        "leaf_samples", "G"):
                                value = dec.get(key)
                                if isinstance(value, (int, float)):
                                    entry[key] = float(value)
                            table.append(entry)
                        self._step_authority["candidate_table"] = table
                    if self.debug >= 1:
                        # audit trail: the candidate table EFE ranked
                        self._debug_log("SELECT step=%d G=%.3f task=%s type=%s room=%s" % (
                            step, _g_score,
                            str(chosen_goal.get("task") or "")[:40],
                            chosen_goal.get("type", ""),
                            chosen_goal.get("target_room", "")))
                        for g in candidate_goals:
                            try:
                                dec = decompose_goal(
                                    g, deviations, self.world_belief,
                                    efe_mode=self.efe_mode, beta=self.beta,
                                    outcome_model=self.goal_outcome_model,
                                    goal_transition_model=self.goal_transition_model)
                                dstr = " ".join(
                                    "%s=%.3f" % (k, v)
                                    for k, v in dec.items()
                                    if isinstance(v, (int, float))
                                )
                            except Exception:
                                dstr = "?"
                            self._debug_log(
                                "   cand: task=%-12s type=%-22s room=%-14s %s" % (
                                    str(g.get("task") or "")[:12],
                                    g.get("type", ""),
                                    str(g.get("target_room") or g.get("room") or ""),
                                    dstr))
                        for rid, rb in sorted(self.world_belief.items()):
                            self._debug_log(
                                "   belief %-12s conf=%.2f entr=%.2f status=%-8s ev=%d" % (
                                    rid, rb.risk_confidence, rb.room_entropy(),
                                    rb.status, rb.evidence_count))

        # ── action selection: same llm_choose_action as single_round ──
        # LLM picks action + ranker safety net overrides bad choices.
        action = None
        llm_response = ""

        if chosen_goal and str(chosen_goal.get("phase") or "") == "done":
            self._authority_stats["phase_done_action_count"] += 1

        if llm_fn is not None:
            self._authority_stats["llm_action_calls"] += 1
            action, llm_response = _llm_select_action(
                candidates, observation, deviations,
                chosen_goal, llm_fn,
                self.agent_id, self.agent_model, self.baseline)
            if action is not None:
                self._authority_stats["llm_action_successes"] += 1

        if action is None and self._engine_ranked_fn is not None:
            try:
                nodes = self._engine_node_index_fn(observation)
                initial_nodes = self._engine_scene_node_index_fn(self.baseline)
                ranked = self._engine_ranked_fn(
                    candidates, nodes, initial_nodes, chosen_goal, self.agent_id)
                if ranked:
                    _, best_idx, _ = ranked[0]
                    if 0 <= best_idx < len(candidates):
                        action = candidates[best_idx]
            except Exception:
                pass

        if action is None:
            action = _ranked_fallback(candidates, deviations, chosen_goal,
                                      self.agent_id, self._failed_targets)

        # Mainline explore executor.  Keep the LLM call above byte-identical
        # to single_round, then replace only an explore/patrol navigation step
        # with a legal deterministic BFS action.  Task Goal execution is never
        # touched.  ``llm`` remains available as an explicit ablation mode.
        explore_navigation = {
            "variant": "llm",
            "applicable": False,
            "choice_kind": "disabled",
        }
        if self.explore_navigation == "v1":
            nav_action, explore_navigation = \
                choose_explore_navigation_action(
                    baseline=self.baseline,
                    observation=observation,
                    candidates=candidates,
                    goal=self._last_goal,
                    agent_id=self.agent_id,
                )
            if explore_navigation["applicable"]:
                self._explore_navigation_stats["decisions"] += 1
                nav_kind = str(explore_navigation["choice_kind"])
                if nav_kind == "already_arrived":
                    self._explore_navigation_stats["arrivals"] += 1
                elif nav_action is None:
                    self._explore_navigation_stats["fallbacks"] += 1
                else:
                    self._explore_navigation_stats["overrides"] += 1
                    self._explore_navigation_stats[nav_kind] += 1
                    action = nav_action

        # ── debug: goal switches (EFE_DEBUG>=1) and every step (>=2) ──
        task = str(chosen_goal.get("task") or "") if chosen_goal else ""
        if self.debug >= 1 and task != self._debug_last_task:
            self._debug_log("GOAL switch -> %s (type=%s)" % (
                task[:40], chosen_goal.get("type", "") if chosen_goal else ""))
            self._debug_last_task = task
        if self.debug >= 2:
            act = str(action.get("action") or "?") if isinstance(action, dict) else "?"
            tgt = str(action.get("target") or "?") if isinstance(action, dict) else "?"
            self._debug_log("step=%d action=%s -> %s task=%s" % (step, act, tgt, task))

        return {
            "action": action,
            "high_level_task": chosen_goal.get("task", "") if chosen_goal else "",
            "deviations": deviations,
            "candidates": candidates,
            "llm_response": llm_response,
            "explore_navigation": explore_navigation,
            "authority_step": copy.deepcopy(self._step_authority),
            "authority_diagnostics": self.authority_diagnostics(),
        }


# ============================================================
# LLM action selector — goal-focused, lean prompt
# ============================================================

def _llm_select_action(candidates: list[dict[str, Any]],
                        observation: dict[str, Any],
                        deviations: list[dict[str, Any]] | None,
                        chosen_goal: dict[str, Any] | None,
                        llm_fn: Any,
                        agent_id: str,
                        agent_model: str,
                        initial_scene: dict[str, Any],
                        ) -> tuple[dict | None, str]:
    try:
        from backend.runtime.agent.decision import llm_choose_action
        action, answer = llm_choose_action(
            candidates=candidates, observation=observation,
            agent_model=agent_model, initial_scene=initial_scene,
            active_goal=chosen_goal, agent_id=agent_id,
        )
        return action, answer
    except Exception:
        return None, ""


# ============================================================
# Fallback action ranker (no LLM available)
# ============================================================

_ACTION_PRIORITY = {"dump": 10, "brush": 9, "fold": 8, "close": 5,
                    "open": 4, "press": 3, "pick": 6, "place": 7, "move": 2}


def _ranked_fallback(candidates: list[dict[str, Any]],
                     deviations: list[dict[str, Any]],
                     chosen_goal: dict[str, Any] | None,
                     agent_id: str,
                     failed_targets: dict[str, int] | None = None,
                     ) -> dict:
    if not candidates:
        return {}
    if failed_targets is None:
        failed_targets = {}
    dev_nodes = {str(d.get("node_id") or "") for d in (deviations or [])
                 if failed_targets.get(str(d.get("node_id") or ""), 0) < 2}
    goal_target = ""
    if chosen_goal:
        goal_target = str(chosen_goal.get("target") or chosen_goal.get("object") or "")

    best = candidates[0]
    best_score = -1
    for c in candidates:
        action = str(c.get("action") or "")
        target = str(c.get("target") or "")
        score = _ACTION_PRIORITY.get(action, 0)
        if target in dev_nodes:
            score += 100
        fail_count = failed_targets.get(target, 0)
        if fail_count >= 2:
            score -= 200
        if target == goal_target:
            score += 50
        if score > best_score:
            best_score = score
            best = c
    return best


# ============================================================
# Single-shot function (signature compatible with yuling_agent)
# ============================================================

def efe_agent(
    initial_scene: dict[str, Any],
    observation: dict[str, Any],
    candidates: list[dict[str, Any]],
    deviations: list[dict[str, Any]] | None = None,
    goal: str = "",
    active_goal: dict[str, Any] | None = None,
    recent_events: str = "",
    agent_id: str = "robot_01",
    agent_model: str = "vllm-qwen3.5-9b",
    llm_fn: Any = None,
    *,
    _efe_loop: EfeLoop | None = None,
    _step: int = 0,
) -> dict[str, Any]:
    if _efe_loop is None:
        _efe_loop = EfeLoop(initial_scene, agent_id=agent_id,
                            agent_model=agent_model)
    return _efe_loop.step(observation, candidates, _step,
                          deviations=deviations, active_goal=active_goal,
                          recent_events=recent_events, goal=goal, llm_fn=llm_fn)
