from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from backend.experiments.io import load_json
from backend.experiments.paths import EXPERIMENT_DIR


def checkpoint_payload(
    *,
    scene_id: str,
    run_id: str,
    experiment_name: str,
    step: int,
    steps: int,
    robot_count: int,
    human_count: int,
    agent_model: str,
    agent_mode: str,
    use_llm: bool,
    schedule_mode: str,
    schedule_seed: int,
    current_scene: dict[str, Any],
    baseline_scene: dict[str, Any],
    memories: dict[str, dict[str, Any] | None],
    active_goals: dict[str, dict[str, Any] | None],
    recent_histories: dict[str, list[dict[str, Any]]],
    recent_score_records: list[dict[str, Any]],
    last_record: dict[str, Any],
    cumulative_state_score: float,
    cumulative_spatial_score: float,
    blocking_cases: list[dict[str, Any]],
    human_blocking_total: int,
    human_blocking_recovered: int,
    matrix_paths: list[str],
    metrics_csv: Path,
    replay_jsonl: Path,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "scene_id": scene_id,
        "run_id": run_id,
        "experiment": experiment_name,
        "next_step": int(step) + 1,
        "requested_steps": int(steps),
        "robot_count": int(robot_count),
        "human_count": int(human_count),
        "agent_model": agent_model,
        "agent_mode": agent_mode,
        "use_llm": bool(use_llm),
        "schedule_mode": schedule_mode,
        "schedule_seed": int(schedule_seed),
        "current_scene": current_scene,
        "baseline_scene": baseline_scene,
        "memories": memories,
        "active_goals": active_goals,
        "recent_histories": recent_histories,
        "recent_score_records": recent_score_records,
        "last_record": last_record,
        "cumulative_state_score": cumulative_state_score,
        "cumulative_spatial_score": cumulative_spatial_score,
        "blocking_cases": blocking_cases,
        "human_blocking_total": int(human_blocking_total),
        "human_blocking_recovered": int(human_blocking_recovered),
        "matrix_paths": matrix_paths,
        "metrics_csv": str(metrics_csv),
        "replay_jsonl": str(replay_jsonl),
        "updated_at": time.time(),
    }


def find_resume_candidates() -> list[Path]:
    candidates: list[Path] = []
    if not EXPERIMENT_DIR.exists():
        return candidates
    for checkpoint in EXPERIMENT_DIR.glob("*/*/*/*/checkpoint.json"):
        run_dir = checkpoint.parent.parent
        if (run_dir / "summary.json").exists():
            continue
        candidates.append(run_dir)
    return sorted(set(candidates), key=lambda path: path.stat().st_mtime, reverse=True)


def resolve_resume_run(value: str) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise RuntimeError("--resume-run requires a run directory or run_id")
    path = Path(raw).expanduser()
    if path.exists():
        path = path.resolve()
        if (path / "summary.json").exists():
            raise RuntimeError(f"run is already complete: {path}")
        if list(path.glob("*/checkpoint.json")):
            return path
        raise RuntimeError(f"no checkpoint.json found under run directory: {path}")
    matches = [candidate for candidate in find_resume_candidates() if candidate.name == raw]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise RuntimeError(f"no resumable run found for: {raw}")
    raise RuntimeError(f"ambiguous run_id {raw}: " + ", ".join(str(path) for path in matches))


def print_resume_candidates() -> None:
    candidates = find_resume_candidates()
    if not candidates:
        print("No resumable runs found.")
        return
    print("Resumable runs:")
    for index, run_dir in enumerate(candidates, start=1):
        checkpoints = []
        for checkpoint in sorted(run_dir.glob("*/checkpoint.json")):
            payload = load_json(checkpoint)
            checkpoints.append(
                f"{checkpoint.parent.name}: next_step={payload.get('next_step')}/{payload.get('requested_steps')}"
            )
        print(f"{index}. {run_dir}")
        print(f"   run_id={run_dir.name}")
        print(f"   checkpoints={'; '.join(checkpoints)}")
    print("\nUse --resume --resume-run <run_id-or-run_dir> to continue one of them.")


def load_run_checkpoints(run_dir: Path) -> dict[str, dict[str, Any]]:
    checkpoints: dict[str, dict[str, Any]] = {}
    for checkpoint in sorted(run_dir.glob("*/checkpoint.json")):
        checkpoints[checkpoint.parent.name] = load_json(checkpoint)
    if not checkpoints:
        raise RuntimeError(f"no checkpoint.json found under run directory: {run_dir}")
    return checkpoints
