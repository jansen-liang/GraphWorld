from __future__ import annotations

from typing import Any

from backend.runtime.agent import (
    candidate_actions,
    fallback_choose_action,
    llm_choose_action,
    llm_choose_reactive_action,
    llm_review_goal,
    perceive,
    remember,
)
from backend.runtime.agent.goal_lifecycle import (
    active_goal_claims,
    candidate_goal_options,
    goal_conflicts_with_claims,
    refresh_active_goal_snapshot,
)
from backend.runtime.agent.maintenance_goals import (
    global_restore_goal,
    visible_dispose_food_goal,
    visible_empty_cup_goal,
    visible_laundry_goal,
    visible_restore_goal,
)
from backend.runtime.agent.rule_baselines import RULE_AGENT_MODES, choose_rule_action
from backend.runtime.scene_preparation import robot_ids


def choose_robot_actions(
    *,
    orchestrator: Any,
    baseline: dict[str, Any],
    robot_count: int,
    agent_mode: str,
    use_llm: bool,
    agent_model: str,
    active_goals: dict[str, dict[str, Any] | None],
    memories: dict[str, dict[str, Any] | None],
    recent_histories: dict[str, list[dict[str, Any]]],
    recent_score_records: list[dict[str, Any]],
    blocking_cases: list[dict[str, Any]],
    step: int,
) -> tuple[
    list[dict[str, Any]],
    dict[str, list[dict[str, Any]]],
    dict[str, str],
    dict[str, str],
    dict[str, dict[str, Any]],
]:
    actions: list[dict[str, Any]] = []
    candidates_by_robot: dict[str, list[dict[str, Any]]] = {}
    llm_answers: dict[str, str] = {}
    goal_review_answers: dict[str, str] = {}
    observations: dict[str, dict[str, Any]] = {}
    claimed_goal_nodes: set[str] = set()
    for robot_id in robot_ids(robot_count):
        claimed_goal_nodes.update(
            claim
            for other_robot_id, goal in active_goals.items()
            if other_robot_id != robot_id
            for claim in active_goal_claims(goal)
        )
        if agent_mode != "reactive" and active_goals.get(robot_id) is None:
            proposed_goal = global_restore_goal(orchestrator.graph.to_scene(), baseline, robot_id, step)
            if proposed_goal and not goal_conflicts_with_claims(proposed_goal, claimed_goal_nodes):
                active_goals[robot_id] = refresh_active_goal_snapshot(proposed_goal, orchestrator.graph.to_scene(), robot_id)
        observation = perceive(orchestrator, robot_id)
        observations[robot_id] = observation
        memories[robot_id] = remember(memories.get(robot_id), observation)
        if agent_mode != "reactive" and active_goals.get(robot_id) is None:
            proposed_goal = visible_dispose_food_goal(observation, orchestrator.graph.to_scene(), step, robot_id, baseline)
            if proposed_goal and goal_conflicts_with_claims(proposed_goal, claimed_goal_nodes):
                proposed_goal = None
            if not proposed_goal:
                proposed_goal = visible_empty_cup_goal(observation, orchestrator.graph.to_scene(), step)
                if proposed_goal and goal_conflicts_with_claims(proposed_goal, claimed_goal_nodes):
                    proposed_goal = None
            if not proposed_goal:
                proposed_goal = visible_laundry_goal(observation, orchestrator.graph.to_scene(), step)
                if proposed_goal and goal_conflicts_with_claims(proposed_goal, claimed_goal_nodes):
                    proposed_goal = None
            if not proposed_goal:
                proposed_goal = visible_restore_goal(observation, baseline, step)
                if proposed_goal and goal_conflicts_with_claims(proposed_goal, claimed_goal_nodes):
                    proposed_goal = None
            if proposed_goal:
                active_goals[robot_id] = refresh_active_goal_snapshot(proposed_goal, orchestrator.graph.to_scene(), robot_id)
        if use_llm and agent_mode == "goal_review":
            goal_options = candidate_goal_options(
                orchestrator.graph.to_scene(),
                baseline,
                observation,
                robot_id,
                step,
                claimed_goal_nodes,
            )
            high_level_options = ["maintain_order"]
            active_task = str((active_goals.get(robot_id) or {}).get("task") or "")
            if active_task:
                high_level_options.append(active_task)
            high_level_options.extend(task for task in goal_options if task not in high_level_options)
            review, review_answer = llm_review_goal(
                observation,
                agent_model,
                initial_scene=baseline,
                active_goal=active_goals.get(robot_id),
                high_level_options=high_level_options,
                recent_history=recent_histories.get(robot_id, []),
                agent_id=robot_id,
            )
            goal_review_answers[robot_id] = review_answer
            decision = str(review.get("decision") or "")
            reviewed_task = str(review.get("high_level_task") or "")
            if decision in {"finish", "drop"} or reviewed_task == "maintain_order":
                active_goals[robot_id] = None
            elif decision == "switch":
                active_goals[robot_id] = goal_options.get(reviewed_task)
            elif active_goals.get(robot_id):
                active_goals[robot_id] = refresh_active_goal_snapshot(
                    active_goals[robot_id],
                    orchestrator.graph.to_scene(),
                    robot_id,
                )
        claimed_goal_nodes.update(active_goal_claims(active_goals.get(robot_id)))
        candidates = candidate_actions(orchestrator, observation, robot_id)
        if not candidates:
            raise RuntimeError(
                f"no legal candidates for {robot_id} at step {step}; "
                f"room={orchestrator.graph.room_of.get(robot_id)}; "
                f"parent={orchestrator.graph.parent_of.get(robot_id)}; "
                f"visible={len(observation.get('nodes') or [])}"
            )
        candidates_by_robot[robot_id] = candidates
        if use_llm:
            if agent_mode == "reactive":
                recent_scores = [
                    {
                        "step": int(record.get("step") or 0),
                        "final_score": record.get("final_score"),
                        "state_score": record.get("state_score"),
                        "spatial_score": record.get("spatial_score"),
                        "human_event_score": record.get("human_event_score"),
                    }
                    for record in recent_score_records[-10:]
                ]
                action, llm_answer = llm_choose_reactive_action(
                    candidates,
                    observation,
                    agent_model,
                    recent_scores=recent_scores,
                    agent_id=robot_id,
                )
            else:
                action, llm_answer = llm_choose_action(
                    candidates,
                    observation,
                    agent_model,
                    baseline,
                    active_goal=active_goals.get(robot_id),
                    agent_id=robot_id,
                )
            llm_answers[robot_id] = llm_answer
        elif agent_mode in RULE_AGENT_MODES:
            action = choose_rule_action(
                agent_mode=agent_mode,
                candidates=candidates,
                observation=observation,
                scene=orchestrator.graph.to_scene(),
                baseline=baseline,
                active_goal=active_goals.get(robot_id),
                blocking_cases=blocking_cases,
                robot_id=robot_id,
            )
        else:
            action = fallback_choose_action(candidates)
        actions.append(action)
    return actions, candidates_by_robot, llm_answers, goal_review_answers, observations
