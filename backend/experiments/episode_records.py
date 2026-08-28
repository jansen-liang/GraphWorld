from __future__ import annotations

import copy
import json
import time
from datetime import datetime, timezone
from typing import Any

from backend.experiments.figures import ACTION_CODES
from backend.runtime.agent import held_object
from backend.runtime.eval import matrix_score
from backend.runtime.scene_preparation import robot_ids
from backend.runtime.scene_utils import room_of


SCORE_KEYS = ("final_score", "state_score", "spatial_score", "human_event_score")
INSTANT_SCORE_KEYS = ("instant_final_score", "instant_state_score", "instant_spatial_score")
AVG_SCORE_KEYS = ("avg_final_score", "avg_state_score", "avg_spatial_score")


def score_step_metrics(
    *,
    current_snapshot: Any,
    baseline_snapshot: Any,
    previous_snapshot: Any,
    robot_snapshot: Any,
    cumulative_state_score: float,
    cumulative_spatial_score: float,
    step: int,
    human_blocking_total: int,
    human_blocking_recovered: int,
) -> tuple[dict[str, Any], float, float]:
    instant_metrics = matrix_score(current_snapshot, baseline_snapshot, previous_snapshot, robot_snapshot)
    instant_metrics.pop("robot_score", None)
    instant_state_score = float(instant_metrics["state_score"])
    instant_spatial_score = float(instant_metrics["spatial_score"])
    human_event_score = float(instant_metrics["human_event_score"])
    instant_final_score = round(
        instant_state_score * 0.45 + instant_spatial_score * 0.35 + human_event_score * 0.20,
        4,
    )
    cumulative_state_score += instant_state_score
    cumulative_spatial_score += instant_spatial_score
    avg_state_score = round(cumulative_state_score / (step + 1), 4)
    avg_spatial_score = round(cumulative_spatial_score / (step + 1), 4)
    avg_final_score = round(
        avg_state_score * 0.45
        + avg_spatial_score * 0.35
        + human_event_score * 0.20,
        4,
    )
    metrics = {
        "final_score": avg_final_score,
        "state_score": avg_state_score,
        "spatial_score": avg_spatial_score,
        "human_event_score": round(human_event_score, 4),
        "instant_final_score": instant_final_score,
        "instant_state_score": round(instant_state_score, 4),
        "instant_spatial_score": round(instant_spatial_score, 4),
        "avg_final_score": avg_final_score,
        "avg_state_score": avg_state_score,
        "avg_spatial_score": avg_spatial_score,
        "robot_state_improvements": instant_metrics.get("robot_state_improvements", 0),
        "robot_spatial_improvements": instant_metrics.get("robot_spatial_improvements", 0),
        "human_blocking_total": human_blocking_total,
        "human_blocking_recovered": human_blocking_recovered,
        "human_blocking_recovery_rate": (
            round(human_blocking_recovered / human_blocking_total, 4) if human_blocking_total else 0.0
        ),
    }
    return metrics, cumulative_state_score, cumulative_spatial_score


def resolved_blocking_count(blocking_cases: list[dict[str, Any]]) -> int:
    return sum(1 for case in blocking_cases if str(case.get("status") or "") in {"resolved", "closed_success"})


def update_blocking_metrics(
    metrics: dict[str, Any],
    *,
    human_blocking_total: int,
    human_blocking_recovered: int,
) -> None:
    metrics["human_blocking_total"] = human_blocking_total
    metrics["human_blocking_recovered"] = human_blocking_recovered
    metrics["human_blocking_recovery_rate"] = (
        round(human_blocking_recovered / human_blocking_total, 4) if human_blocking_total else 0.0
    )


def write_tensorboard_scores(writer: Any, metrics: dict[str, Any], *, action_name: str, step: int) -> None:
    for key in SCORE_KEYS:
        writer.add_scalar(f"scores/{key}", float(metrics[key]), step)
    for key in INSTANT_SCORE_KEYS:
        writer.add_scalar(f"scores/{key}", float(metrics[key]), step)
    for key in AVG_SCORE_KEYS:
        writer.add_scalar(f"scores/{key}", float(metrics[key]), step)
    writer.add_scalar("actions/action_code", ACTION_CODES.get(action_name, -1), step)


def build_metrics_row(
    *,
    step: int,
    experiment_name: str,
    event_id: str,
    action_name: str,
    primary_action: dict[str, Any],
    actions: list[dict[str, Any]],
    llm_answers: dict[str, str],
    goal_review_answers: dict[str, str],
    active_goals: dict[str, dict[str, Any] | None],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "step": step,
        "experiment": experiment_name,
        "event": event_id,
        "action": action_name,
        "target": primary_action.get("target", ""),
        "action_reason": primary_action.get("reason", ""),
        "action_legal": all(bool(action.get("legal", True)) for action in actions) if actions else True,
        "validation_failures": json.dumps(
            {str(action.get("agent") or ""): action.get("validation_failures", []) for action in actions},
            ensure_ascii=False,
        ),
        "llm_answer": json.dumps(llm_answers, ensure_ascii=False),
        "goal_review": json.dumps(goal_review_answers, ensure_ascii=False),
        "active_goal": json.dumps(active_goals, ensure_ascii=False),
        **metrics,
    }


def append_robot_history(
    *,
    recent_histories: dict[str, list[dict[str, Any]]],
    current: dict[str, Any],
    orchestrator: Any,
    robot_count: int,
    active_goals: dict[str, dict[str, Any] | None],
    actions_by_robot: dict[str, dict[str, Any]],
    metrics: dict[str, Any],
    step: int,
) -> None:
    for robot_id in robot_ids(robot_count):
        action_for_robot = actions_by_robot.get(robot_id, {})
        history = recent_histories.setdefault(robot_id, [])
        history.append(
            {
                "step": step,
                "room": room_of(current, robot_id),
                "holding": held_object(orchestrator, robot_id),
                "active_goal": str((active_goals.get(robot_id) or {}).get("task") or ""),
                "action": action_for_robot.get("action", ""),
                "target": action_for_robot.get("target", ""),
                "object": action_for_robot.get("object", ""),
                "final_score": float(metrics["final_score"]),
                "state_score": float(metrics["state_score"]),
                "spatial_score": float(metrics["spatial_score"]),
                "human_event_score": float(metrics["human_event_score"]),
            }
        )
        del history[:-10]


def build_replay_row(
    *,
    step: int,
    robot_count: int,
    use_llm: bool,
    model_ok: bool,
    agent_mode: str,
    rule_agent_modes: tuple[str, ...],
    event_id: str,
    llm_answers: dict[str, str],
    goal_review_answers: dict[str, str],
    primary_action: dict[str, Any],
    actions: list[dict[str, Any]],
    blocking_cases: list[dict[str, Any]],
    observations: dict[str, dict[str, Any]],
    memories: dict[str, dict[str, Any] | None],
    active_goals: dict[str, dict[str, Any] | None],
    human_events: list[dict[str, Any]],
    metrics: dict[str, Any],
    current: dict[str, Any],
    include_scene: bool,
    orchestrator: Any,
    primary_robot: str,
    robot_room: str,
) -> dict[str, Any]:
    return {
        "episode_step": step,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reasoning": json.dumps(llm_answers, ensure_ascii=False) if robot_count else "npc_only_baseline",
        "goal_review": json.dumps(goal_review_answers, ensure_ascii=False) if robot_count else "",
        "planner": {
            "mode": (
                "llm"
                if robot_count and use_llm and model_ok
                else ("rule" if robot_count and agent_mode in rule_agent_modes else ("heuristic" if robot_count else "npc_only_baseline"))
            ),
            "event": event_id,
        },
        "action": copy.deepcopy(primary_action),
        "robot_actions": copy.deepcopy(actions),
        "ok": all(bool(action.get("legal", True)) for action in actions) if actions else True,
        "failed_preconds": {
            str(action.get("agent") or ""): copy.deepcopy(action.get("validation_failures") or [])
            for action in actions
        },
        "blocking_cases": copy.deepcopy(blocking_cases),
        "observation": copy.deepcopy(observations),
        "memory_before": {},
        "memory_after": copy.deepcopy(memories),
        "active_goals": copy.deepcopy(active_goals),
        "event_log": copy.deepcopy(human_events),
        "scene_metrics": {
            "world_metrics": {
                "world_score": float(metrics["final_score"]),
                "human_score": float(metrics["human_event_score"]),
            },
            "top_issues": [],
        },
        "world_score": float(metrics["final_score"]),
        "scene": copy.deepcopy(current) if include_scene else {},
        "robot_state": {
            "room_id": robot_room,
            "holding": held_object(orchestrator, primary_robot) if primary_robot else "",
        },
        "robot_states": {
            robot_id: {
                "room_id": room_of(current, robot_id),
                "holding": held_object(orchestrator, robot_id),
            }
            for robot_id in robot_ids(robot_count)
        },
    }


def build_experiment_summary(
    *,
    run_id: str,
    scene_id: str,
    experiment_group: str,
    steps: int,
    agent_model: str,
    agent_mode: str,
    goal_review: str,
    schedule_mode: str,
    schedule_seed: int,
    group_robots: int,
    humans: int,
    expected: tuple[str, ...],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "scene": scene_id,
        "experiment_group": experiment_group,
        "steps": steps,
        "agent_model": agent_model,
        "agent_mode": agent_mode,
        "goal_review": goal_review,
        "schedule_mode": schedule_mode,
        "schedule_seed": schedule_seed,
        "robots": group_robots,
        "humans": humans,
        "expected_events": expected,
        "created_at": time.time(),
        "runs": [
            {key: value for key, value in result.items() if key != "records"}
            | {
                "final_metrics": {score_key: result["records"][-1][score_key] for score_key in SCORE_KEYS},
                "final_instant_metrics": {
                    score_key: result["records"][-1][score_key]
                    for score_key in INSTANT_SCORE_KEYS
                    if score_key in result["records"][-1]
                },
                "final_avg_metrics": {
                    score_key: result["records"][-1][score_key]
                    for score_key in AVG_SCORE_KEYS
                    if score_key in result["records"][-1]
                },
                "final_blocking_metrics": {
                    "human_blocking_total": result["records"][-1].get("human_blocking_total", 0),
                    "human_blocking_recovered": result["records"][-1].get("human_blocking_recovered", 0),
                    "human_blocking_recovery_rate": result["records"][-1].get("human_blocking_recovery_rate", 0.0),
                },
            }
            for result in results
        ],
    }
