#!/usr/bin/env python3
"""Aggregate the EFE goal-authority ablation without third-party packages."""

from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


METRICS = (
    "final_score",
    "state_score",
    "spatial_score",
    "human_event_score",
)
DIAGNOSTICS = (
    "efe_coverage",
    "goal_commitments",
    "selection_opportunities",
    "pipeline_direct_commits",
    "efe_selections",
    "rule_selections",
    "random_selections",
    "goal_completions",
    "goal_stuck_failures",
    "goal_stuck_rate",
    "goal_switches",
    "same_target_reselections",
    "goal_reversal_count",
    "goal_conflict_count",
    "conflicting_candidates_removed",
    "single_candidate_rate",
    "phase_done_action_count",
    "mean_completed_goal_duration",
    "mean_failed_goal_duration",
    "efe_score_tie_opportunities",
    "efe_score_tie_rate",
    "mean_candidates_per_selection",
)


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def load_rows(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*/seed_*/*/*/*/summary.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        runs = data.get("runs") or []
        robot_run = next(
            (run for run in runs if run.get("experiment") == "with_robot"),
            None,
        )
        if not robot_run:
            continue
        by_robot = robot_run.get("efe_authority_diagnostics") or {}
        diagnostic = next(iter(by_robot.values()), {})
        final = robot_run.get("final_metrics") or {}
        condition = str(data.get("efe_goal_authority") or path.parts[-6])
        row: dict[str, Any] = {
            "condition": condition,
            "scene": str(data.get("scene") or ""),
            "seed": int(data.get("schedule_seed") or 0),
            "steps": int(data.get("steps") or 0),
            "candidate_source": str(data.get("efe_candidate_source") or ""),
            "run_id": str(data.get("run_id") or ""),
            "summary_path": str(path.resolve()),
        }
        row.update({key: _number(final.get(key)) for key in METRICS})
        row.update({key: _number(diagnostic.get(key)) for key in DIAGNOSTICS})
        rows.append(row)
    return rows


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["condition"], row["scene"])].append(row)
    result: list[dict[str, Any]] = []
    for (condition, scene), items in sorted(groups.items()):
        out: dict[str, Any] = {
            "condition": condition,
            "scene": scene,
            "runs": len(items),
        }
        for key in (*METRICS, *DIAGNOSTICS):
            values = [float(item[key]) for item in items if math.isfinite(float(item[key]))]
            out[f"{key}_mean"] = statistics.fmean(values) if values else math.nan
            out[f"{key}_std"] = statistics.stdev(values) if len(values) > 1 else 0.0
        result.append(out)
    return result


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fmt(value: Any) -> str:
    number = _number(value)
    return "-" if not math.isfinite(number) else f"{number:.4f}"


def write_report(path: Path, rows: list[dict[str, Any]], agg: list[dict[str, Any]]) -> None:
    lines = [
        "# EFE Goal-Authority Ablation",
        "",
        f"Completed runs: {len(rows)}",
        "",
        "| condition | scene | runs | final | state | spatial | human | EFE coverage | single-candidate | conflicts | reversals | done-actions | stuck |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in agg:
        lines.append(
            "| {condition} | {scene} | {runs} | {final} | {state} | {spatial} | "
            "{human} | {coverage} | {single} | {conflicts} | {reversals} | {done} | {stuck} |".format(
                condition=row["condition"], scene=row["scene"], runs=row["runs"],
                final=fmt(row["final_score_mean"]),
                state=fmt(row["state_score_mean"]),
                spatial=fmt(row["spatial_score_mean"]),
                human=fmt(row["human_event_score_mean"]),
                coverage=fmt(row["efe_coverage_mean"]),
                single=fmt(row["single_candidate_rate_mean"]),
                conflicts=fmt(row["goal_conflict_count_mean"]),
                reversals=fmt(row["goal_reversal_count_mean"]),
                done=fmt(row["phase_done_action_count_mean"]),
                stuck=fmt(row["goal_stuck_failures_mean"]),
            )
        )
    lines.extend([
        "",
        "Values are means across completed seeds; standard deviations are in aggregate_summary.csv.",
        "The experiment uses deterministic skill/pipeline high-level candidates; the LLM is retained for legal action selection.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else
                "backend/data/experiments/efe_goal_authority_v3_goal_lifecycle_fix").resolve()
    root.mkdir(parents=True, exist_ok=True)
    rows = load_rows(root)
    agg = aggregate(rows)
    write_csv(root / "runs.csv", rows)
    write_csv(root / "aggregate_summary.csv", agg)
    (root / "aggregate_summary.json").write_text(
        json.dumps(agg, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(root / "aggregate_report.md", rows, agg)
    print(f"Aggregated {len(rows)} runs under {root}")
    print(f"Report: {root / 'aggregate_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
