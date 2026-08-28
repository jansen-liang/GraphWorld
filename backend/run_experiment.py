from __future__ import annotations

import argparse
import copy
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.experiments.checkpointing import (
    checkpoint_payload,
    load_run_checkpoints,
    print_resume_candidates,
    resolve_resume_run,
)
from backend.experiments.episode_records import (
    append_robot_history,
    build_experiment_summary,
    build_metrics_row,
    build_replay_row,
    resolved_blocking_count,
    score_step_metrics,
    update_blocking_metrics,
    write_tensorboard_scores,
)
from backend.experiments.episode_policy import choose_robot_actions
from backend.experiments.figures import build_room_index, save_step_matrices
from backend.experiments.io import (
    append_csv_row,
    append_jsonl,
    convert_jsonl_to_json_array,
    load_json,
    write_csv_rows,
    write_json_atomic,
    write_jsonl_rows,
)
from backend.experiments.paths import (
    EXPERIMENT_DIR,
    SCENE_DIR,
    TENSORBOARD_DIR,
    _slug,
    canonical_experiment_group,
    canonical_run_group,
    clean_old_outputs,
    utc_run_id,
)
from backend.experiments.tensorboard import TensorBoardWriter
from backend.runtime.agent import reflect
from backend.runtime.agent.goal_lifecycle import update_active_goal
from backend.runtime.agent.rule_baselines import RULE_AGENT_MODES
from backend.runtime.action_conflicts import resolve_robot_action_conflicts
from backend.runtime.blocking import finalize_blocking_case_outcomes, update_blocking_cases
from backend.runtime.engine import Orchestrator
from backend.runtime.eval import build_matrix_snapshot
from backend.runtime.scene_preparation import prepare_scene, robot_ids
from backend.runtime.scene_utils import room_of
from backend.runtime.schedule import expected_events, planned_event_for_step, planned_events_for_step
from backend.tools.agent import resolved_agent_config

LLM_AGENT_MODES = ("reactive", "single_round", "goal_review")
AGENT_MODES = (*LLM_AGENT_MODES, *RULE_AGENT_MODES)


def check_llm_agent(agent_model: str, timeout: float = 30.0) -> tuple[bool, str]:
    try:
        cfg = resolved_agent_config(agent_model)
    except Exception:
        return False, f"unsupported agent: {agent_model}"
    served_name = str(cfg.get("model") or agent_model)
    if cfg.get("type") != "openai":
        return True, served_name
    base_url = str(cfg.get("base_url") or "").rstrip("/")
    if not base_url:
        return False, f"missing base_url for agent: {agent_model}"
    try:
        health_url = base_url.rsplit("/v1", 1)[0] + "/health"
        request = urllib.request.Request(health_url)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=timeout) as response:
            response.read()
        return True, served_name
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def require_llm_agent(agent_model: str) -> str:
    model_ok, model_status = check_llm_agent(agent_model)
    if not model_ok:
        raise RuntimeError(f"LLM agent is required but unavailable: {model_status}")
    return model_status


def run_episode(
    raw_scene: dict[str, Any],
    *,
    scene_id: str,
    steps: int,
    robot_count: int,
    human_count: int,
    run_id: str,
    agent_model: str,
    use_llm: bool,
    agent_mode: str,
    expected: tuple[str, ...],
    output_dir: Path,
    matrix_viz: bool,
    replay_scene_interval: int = 1,
    metric_log_interval: int = 1,
    schedule_mode: str = "fixed",
    schedule_seed: int = 0,
    resume: bool = False,
) -> dict[str, Any]:
    scene = prepare_scene(raw_scene, robot_count=robot_count, human_count=human_count)
    scene.setdefault("world_state", {})["schedule_mode"] = schedule_mode
    scene.setdefault("world_state", {})["schedule_seed"] = int(schedule_seed)
    baseline = copy.deepcopy(scene)
    room_index_map = build_room_index(scene)
    orchestrator = Orchestrator(scene)
    memories: dict[str, dict[str, Any] | None] = {robot_id: None for robot_id in robot_ids(robot_count)}
    active_goals: dict[str, dict[str, Any] | None] = {robot_id: None for robot_id in robot_ids(robot_count)}
    recent_histories: dict[str, list[dict[str, Any]]] = {robot_id: [] for robot_id in robot_ids(robot_count)}
    recent_score_records: list[dict[str, Any]] = []
    last_record: dict[str, Any] = {}
    cumulative_state_score = 0.0
    cumulative_spatial_score = 0.0
    blocking_cases: list[dict[str, Any]] = []
    human_blocking_total = 0
    human_blocking_recovered = 0
    experiment_name = "with_robot" if robot_count else "no_robot"
    experiment_output_dir = output_dir / experiment_name
    experiment_output_dir.mkdir(parents=True, exist_ok=True)
    matrix_output_dir = experiment_output_dir / "matrices"
    planning_label = agent_mode
    model_name = (
        f"{agent_model}__{planning_label}"
        if robot_count and use_llm
        else (f"rule__{planning_label}" if robot_count and agent_mode in RULE_AGENT_MODES else ("heuristic" if robot_count else "npc_only_baseline"))
    )
    tb_dir = TENSORBOARD_DIR / _slug(scene_id) / canonical_run_group(
        scene_id,
        experiment_name,
        model_name,
        steps,
        robot_count,
        human_count,
        schedule_mode,
        schedule_seed,
    ) / run_id
    tb_dir.mkdir(parents=True, exist_ok=True)
    writer = TensorBoardWriter(tb_dir)
    replay_path = experiment_output_dir / "replay.json"
    replay_jsonl_path = experiment_output_dir / "replay.jsonl"
    csv_path = experiment_output_dir / "metrics.csv"
    checkpoint_path = experiment_output_dir / "checkpoint.json"
    model_ok = bool(robot_count and use_llm)
    model_status = require_llm_agent(agent_model) if model_ok else "not_used"
    previous_snapshot = build_matrix_snapshot(orchestrator.graph.to_scene(), expected)
    baseline_snapshot = build_matrix_snapshot(baseline, expected)
    matrix_paths: list[str] = []
    replay_scene_interval = max(0, int(replay_scene_interval))
    metric_log_interval = max(1, int(metric_log_interval))
    start_step = 0
    if resume and checkpoint_path.exists():
        checkpoint = load_json(checkpoint_path)
        checkpoint_experiment = str(checkpoint.get("experiment") or "")
        if checkpoint_experiment != experiment_name:
            raise RuntimeError(f"checkpoint experiment mismatch: {checkpoint_experiment} != {experiment_name}")
        start_step = int(checkpoint.get("next_step") or 0)
        if start_step > int(steps):
            raise RuntimeError(f"checkpoint next_step={start_step} exceeds requested steps={steps}")
        baseline = copy.deepcopy(checkpoint.get("baseline_scene") or baseline)
        scene = copy.deepcopy(checkpoint.get("current_scene") or scene)
        orchestrator = Orchestrator(scene)
        room_index_map = build_room_index(baseline)
        memories = copy.deepcopy(checkpoint.get("memories") or memories)
        active_goals = copy.deepcopy(checkpoint.get("active_goals") or active_goals)
        recent_histories = copy.deepcopy(checkpoint.get("recent_histories") or recent_histories)
        legacy_records = copy.deepcopy(checkpoint.get("records") or [])
        legacy_replay_steps = copy.deepcopy(checkpoint.get("replay_steps") or [])
        if legacy_records and not csv_path.exists():
            write_csv_rows(csv_path, legacy_records)
        if legacy_replay_steps and not replay_jsonl_path.exists():
            write_jsonl_rows(replay_jsonl_path, legacy_replay_steps)
        recent_score_records = copy.deepcopy(checkpoint.get("recent_score_records") or legacy_records[-10:])
        last_record = copy.deepcopy(checkpoint.get("last_record") or (legacy_records[-1] if legacy_records else {}))
        cumulative_state_score = float(checkpoint.get("cumulative_state_score") or 0.0)
        cumulative_spatial_score = float(checkpoint.get("cumulative_spatial_score") or 0.0)
        blocking_cases = copy.deepcopy(checkpoint.get("blocking_cases") or blocking_cases)
        human_blocking_total = int(
            checkpoint.get(
                "human_blocking_total",
                (last_record or {}).get("human_blocking_total", human_blocking_total),
            )
            or 0
        )
        human_blocking_recovered = int(
            checkpoint.get(
                "human_blocking_recovered",
                (last_record or {}).get("human_blocking_recovered", human_blocking_recovered),
            )
            or 0
        )
        matrix_paths = list(checkpoint.get("matrix_paths") or [])
        previous_snapshot = build_matrix_snapshot(orchestrator.graph.to_scene(), expected)
        baseline_snapshot = build_matrix_snapshot(baseline, expected)
        tqdm.write(f"{experiment_name}: resuming {run_id} from step {start_step}/{steps}")
    elif resume:
        tqdm.write(f"{experiment_name}: no checkpoint found, starting from step 0")
    for step in tqdm(range(start_step, steps), desc=experiment_name, unit="step", dynamic_ncols=True):
        schedule_scene = orchestrator.graph.to_scene()
        event_id = planned_event_for_step(schedule_scene, step)
        human_events = planned_events_for_step(schedule_scene, step)
        actions, candidates_by_robot, llm_answers, goal_review_answers, observations = choose_robot_actions(
            orchestrator=orchestrator,
            baseline=baseline,
            robot_count=robot_count,
            agent_mode=agent_mode,
            use_llm=use_llm,
            agent_model=agent_model,
            active_goals=active_goals,
            memories=memories,
            recent_histories=recent_histories,
            recent_score_records=recent_score_records,
            blocking_cases=blocking_cases,
            step=step,
        )
        actions = resolve_robot_action_conflicts(actions, candidates_by_robot)
        result = orchestrator.step(
            robot_actions=actions,
            human_events=human_events,
            capture_robot_scene=bool(robot_count),
            capture_scene=False,
        )
        for robot_id in robot_ids(robot_count):
            memories[robot_id] = reflect(memories.get(robot_id), result)
        current = orchestrator.graph.to_scene()
        new_blocking_cases: list[dict[str, Any]] = []
        for event_result in result.get("human_events") or []:
            for case in event_result.get("blocking_cases") or []:
                new_blocking_cases.append(copy.deepcopy(case))
        if new_blocking_cases:
            blocking_cases.extend(new_blocking_cases)
            human_blocking_total += sum(1 for case in new_blocking_cases if bool(case.get("recoverable", False)))
        action_results = {
            robot_id: copy.deepcopy(action_result)
            for robot_id, action_result in zip(robot_ids(robot_count), result.get("robot_actions") or [])
        }
        actions_by_robot = {str(action.get("agent") or ""): action for action in actions}
        for robot_id in robot_ids(robot_count):
            active_goals[robot_id] = update_active_goal(
                active_goals.get(robot_id),
                current,
                robot_id,
                actions_by_robot.get(robot_id, {}),
                action_results.get(robot_id, {}),
                step,
            )
        current_snapshot = build_matrix_snapshot(current, expected)
        robot_snapshot = build_matrix_snapshot(result["robot_scene"], expected) if robot_count else current_snapshot
        metrics, cumulative_state_score, cumulative_spatial_score = score_step_metrics(
            current_snapshot=current_snapshot,
            baseline_snapshot=baseline_snapshot,
            previous_snapshot=previous_snapshot,
            robot_snapshot=robot_snapshot,
            cumulative_state_score=cumulative_state_score,
            cumulative_spatial_score=cumulative_spatial_score,
            step=step,
            human_blocking_total=human_blocking_total,
            human_blocking_recovered=human_blocking_recovered,
        )
        previous_snapshot = current_snapshot
        primary_action = actions[0] if actions else {}
        action_name = str(primary_action.get("action") or "")
        before_resolved = resolved_blocking_count(blocking_cases)
        update_blocking_cases(blocking_cases, current, actions, step)
        finalize_blocking_case_outcomes(blocking_cases, result.get("human_events") or [])
        after_resolved = resolved_blocking_count(blocking_cases)
        human_blocking_recovered += max(0, after_resolved - before_resolved)
        update_blocking_metrics(
            metrics,
            human_blocking_total=human_blocking_total,
            human_blocking_recovered=human_blocking_recovered,
        )
        append_robot_history(
            recent_histories=recent_histories,
            current=current,
            orchestrator=orchestrator,
            robot_count=robot_count,
            active_goals=active_goals,
            actions_by_robot=actions_by_robot,
            metrics=metrics,
            step=step,
        )
        if step % metric_log_interval == 0 or step + 1 == steps:
            write_tensorboard_scores(writer, metrics, action_name=action_name, step=step)
        if matrix_viz:
            matrix_paths.append(
                save_step_matrices(
                    current_snapshot,
                    step=step,
                    output_dir=matrix_output_dir,
                )
            )
        row = build_metrics_row(
            step=step,
            experiment_name=experiment_name,
            event_id=event_id,
            action_name=action_name,
            primary_action=primary_action,
            actions=actions,
            llm_answers=llm_answers,
            goal_review_answers=goal_review_answers,
            active_goals=active_goals,
            metrics=metrics,
        )
        append_csv_row(csv_path, row)
        recent_score_records.append(row)
        del recent_score_records[:-10]
        last_record = row
        primary_robot = robot_ids(robot_count)[0] if robot_count else ""
        robot_room = room_of(current, primary_robot) if primary_robot else ""
        if primary_robot and robot_room:
            writer.add_scalar("trajectory/room_index", room_index_map.get(robot_room, -1), step)
        include_scene = replay_scene_interval > 0 and (step % replay_scene_interval == 0 or step + 1 == steps)
        replay_row = build_replay_row(
            step=step,
            robot_count=robot_count,
            use_llm=use_llm,
            model_ok=model_ok,
            agent_mode=agent_mode,
            rule_agent_modes=RULE_AGENT_MODES,
            event_id=event_id,
            llm_answers=llm_answers,
            goal_review_answers=goal_review_answers,
            primary_action=primary_action,
            actions=actions,
            blocking_cases=blocking_cases,
            observations=observations,
            memories=memories,
            active_goals=active_goals,
            human_events=human_events,
            metrics=metrics,
            current=current,
            include_scene=include_scene,
            orchestrator=orchestrator,
            primary_robot=primary_robot,
            robot_room=robot_room,
        )
        append_jsonl(replay_jsonl_path, replay_row)
        write_json_atomic(
            checkpoint_path,
            checkpoint_payload(
                scene_id=scene_id,
                run_id=run_id,
                experiment_name=experiment_name,
                step=step,
                steps=steps,
                robot_count=robot_count,
                human_count=human_count,
                agent_model=agent_model,
                agent_mode=agent_mode,
                use_llm=use_llm,
                schedule_mode=schedule_mode,
                schedule_seed=schedule_seed,
                current_scene=current,
                baseline_scene=baseline,
                memories=memories,
                active_goals=active_goals,
                recent_histories=recent_histories,
                recent_score_records=recent_score_records,
                last_record=last_record,
                cumulative_state_score=cumulative_state_score,
                cumulative_spatial_score=cumulative_spatial_score,
                blocking_cases=blocking_cases,
                human_blocking_total=human_blocking_total,
                human_blocking_recovered=human_blocking_recovered,
                matrix_paths=matrix_paths,
                metrics_csv=csv_path,
                replay_jsonl=replay_jsonl_path,
            ),
        )
    writer.add_text(
        "trajectory/room_index_map",
        "\n".join(f"{index}: {room_id}" for room_id, index in sorted(room_index_map.items(), key=lambda item: item[1])),
        0,
    )
    tqdm.write(f"{experiment_name}: flushing tensorboard")
    writer.flush()
    writer.close()
    tqdm.write(f"{experiment_name}: writing replay to {replay_path}")
    replay_count = convert_jsonl_to_json_array(replay_jsonl_path, replay_path, desc=f"{experiment_name} replay")
    return {
        "experiment": experiment_name,
        "records": [last_record] if last_record else [],
        "tensorboard_log_dir": str(tb_dir),
        "replay_path": str(replay_path),
        "metrics_csv": str(csv_path),
        "matrix_dir": str(matrix_output_dir) if matrix_viz else "",
        "matrix_count": len(matrix_paths),
        "replay_count": replay_count,
        "model_ok": model_ok,
        "model_status": model_status,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", default="simple_home_1f")
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--agent-model", default="vllm-qwen3.5-4b")
    parser.add_argument("--robots", type=int, default=1)
    parser.add_argument("--humans", type=int, default=1)
    parser.add_argument("--no-clean", action="store_true")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--goal-review", choices=("on", "off"), default="on")
    parser.add_argument("--agent-mode", choices=AGENT_MODES, default="")
    parser.add_argument("--only", choices=("both", "no_robot", "with_robot"), default="both")
    parser.add_argument("--matrix-viz", action="store_true")
    parser.add_argument("--replay-scene-interval", type=int, default=1)
    parser.add_argument("--metric-log-interval", type=int, default=1)
    parser.add_argument("--schedule-mode", choices=("fixed", "calendar", "stochastic"), default="fixed")
    parser.add_argument("--schedule-seed", type=int, default=0)
    parser.add_argument("--resume", action="store_true", help="List resumable interrupted runs, or resume --resume-run.")
    parser.add_argument("--resume-run", default="", help="Run id or run directory to continue when --resume is set.")
    args = parser.parse_args()
    if args.resume and not str(args.resume_run or "").strip():
        print_resume_candidates()
        return
    agent_mode = str(args.agent_mode or "").strip() or ("goal_review" if args.goal_review == "on" else "single_round")
    agent_model = str(args.agent_model)
    requested_use_llm = not args.no_llm and agent_mode not in RULE_AGENT_MODES
    scene_id = str(args.scene or "simple_home_1f").removesuffix(".json")
    steps = int(args.steps)
    robots = max(0, int(args.robots))
    humans = max(0, int(args.humans))
    schedule_mode = str(args.schedule_mode or "fixed")
    schedule_seed = int(args.schedule_seed)
    group_robots = 0 if args.only == "no_robot" else robots
    resume_checkpoints: dict[str, dict[str, Any]] = {}
    if args.resume:
        output_dir = resolve_resume_run(str(args.resume_run))
        resume_checkpoints = load_run_checkpoints(output_dir)
        first_checkpoint = next(iter(resume_checkpoints.values()))
        run_id = output_dir.name
        experiment_group = output_dir.parent.name
        scene_id = str(first_checkpoint.get("scene_id") or scene_id)
        steps = int(first_checkpoint.get("requested_steps") or steps)
        robots = int(first_checkpoint.get("robot_count") or robots)
        humans = int(first_checkpoint.get("human_count") or humans)
        agent_model = str(first_checkpoint.get("agent_model") or agent_model)
        agent_mode = str(first_checkpoint.get("agent_mode") or agent_mode)
        schedule_mode = str(first_checkpoint.get("schedule_mode") or schedule_mode)
        schedule_seed = int(first_checkpoint.get("schedule_seed") or schedule_seed)
        if "with_robot" in resume_checkpoints:
            robots = int(resume_checkpoints["with_robot"].get("robot_count") or robots)
            group_robots = robots
        else:
            group_robots = 0
    else:
        if not args.no_clean:
            clean_old_outputs()
        experiment_model = (
            "npc_only_baseline"
            if group_robots == 0
            else (f"rule__{agent_mode}" if agent_mode in RULE_AGENT_MODES else ("heuristic" if args.no_llm else f"{agent_model}__{agent_mode}"))
        )
        experiment_group = canonical_experiment_group(
            scene_id,
            steps,
            group_robots,
            humans,
            experiment_model,
            schedule_mode,
            schedule_seed,
        )
        run_id = utc_run_id()
        output_dir = EXPERIMENT_DIR / _slug(scene_id) / experiment_group / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    scene_path = SCENE_DIR / f"{scene_id}.json"
    raw_scene = json.loads(scene_path.read_text(encoding="utf-8"))
    expected_scene = prepare_scene(raw_scene, robot_count=robots, human_count=humans)
    expected_scene.setdefault("world_state", {})["schedule_mode"] = schedule_mode
    expected_scene.setdefault("world_state", {})["schedule_seed"] = int(schedule_seed)
    expected = expected_events(expected_scene, steps)
    results = []
    should_run_no_robot = args.only in {"both", "no_robot"}
    should_run_with_robot = args.only in {"both", "with_robot"}
    if args.resume:
        checkpoint_experiments = set(resume_checkpoints)
        if args.only == "both":
            should_run_no_robot = "no_robot" in checkpoint_experiments
            should_run_with_robot = "with_robot" in checkpoint_experiments
        else:
            requested_experiment = "no_robot" if args.only == "no_robot" else "with_robot"
            if requested_experiment not in checkpoint_experiments:
                raise RuntimeError(
                    f"requested --only {args.only}, but checkpoint has {sorted(checkpoint_experiments)}"
                )
    if should_run_no_robot:
        results.append(
            run_episode(
                raw_scene,
                scene_id=scene_id,
                steps=steps,
                robot_count=0,
                human_count=humans,
                run_id=run_id,
                agent_model=agent_model,
                use_llm=False,
                agent_mode="no_robot",
                expected=expected,
                output_dir=output_dir,
                matrix_viz=args.matrix_viz,
                replay_scene_interval=args.replay_scene_interval,
                metric_log_interval=args.metric_log_interval,
                schedule_mode=schedule_mode,
                schedule_seed=schedule_seed,
                resume=args.resume,
            )
        )
    if should_run_with_robot:
        results.append(
            run_episode(
                raw_scene,
                scene_id=scene_id,
                steps=steps,
                robot_count=robots,
                human_count=humans,
                run_id=run_id,
                agent_model=agent_model,
                use_llm=bool(resume_checkpoints.get("with_robot", {}).get("use_llm", requested_use_llm)) if args.resume else requested_use_llm,
                agent_mode=agent_mode,
                expected=expected,
                output_dir=output_dir,
                matrix_viz=args.matrix_viz,
                replay_scene_interval=args.replay_scene_interval,
                metric_log_interval=args.metric_log_interval,
                schedule_mode=schedule_mode,
                schedule_seed=schedule_seed,
                resume=args.resume,
            )
        )
    summary = build_experiment_summary(
        run_id=run_id,
        scene_id=scene_id,
        experiment_group=experiment_group,
        steps=steps,
        agent_model=agent_model,
        agent_mode=agent_mode,
        goal_review=args.goal_review,
        schedule_mode=schedule_mode,
        schedule_seed=schedule_seed,
        group_robots=group_robots,
        humans=humans,
        expected=expected,
        results=results,
    )
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
