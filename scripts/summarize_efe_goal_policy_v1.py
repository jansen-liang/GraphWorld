#!/usr/bin/env python3
"""Summarise the four-condition EFE goal-policy v1 quick experiment."""

from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


FIELDS = (
    "final_score", "state_score", "spatial_score", "human_event_score",
    "goal_commitments", "goal_completions", "goal_stuck_failures",
    "efe_score_tie_rate", "single_candidate_rate",
    "mean_candidates_per_selection", "pipeline_direct_commits",
    "pipeline_candidates_scored", "mean_completed_goal_duration",
    "goal_b_updates", "goal_b_observations",
    "goal_b_mean_prequential_nll", "goal_b_recent_20_prequential_nll",
)


def number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def load_runs(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*/seed_*/*/*/*/summary.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        run = next((item for item in data.get("runs") or []
                    if item.get("experiment") == "with_robot"), None)
        if not run:
            continue
        diagnostic = next(iter(
            (run.get("efe_authority_diagnostics") or {}).values()), {})
        metrics = run.get("final_metrics") or {}
        family_counts = diagnostic.get("selected_goal_family_counts") or {}
        goal_b = diagnostic.get("goal_transition_model") or {}
        commitments = max(1.0, number(diagnostic.get("goal_commitments")))
        explore_count = number(family_counts.get("explore", 0))
        maintain_count = number(family_counts.get("maintain", 0))
        relative = path.relative_to(root)
        row: dict[str, Any] = {
            "condition": relative.parts[0],
            "scene": str(data.get("scene") or ""),
            "seed": int(data.get("schedule_seed") or 0),
            "efe_mode": str(diagnostic.get("efe_mode") or ""),
            "goal_outcome_learning": bool(
                diagnostic.get("goal_outcome_learning", False)),
            "explore_goal_count": explore_count,
            "maintain_goal_count": maintain_count,
            "task_goal_count": commitments - explore_count - maintain_count,
            "explore_goal_rate": explore_count / commitments,
            "maintain_goal_rate": maintain_count / commitments,
            "summary_path": str(path.resolve()),
            "goal_b_updates": number(goal_b.get("updates")),
            "goal_b_observations": number(goal_b.get("observations")),
            "goal_b_mean_prequential_nll": number(
                goal_b.get("mean_prequential_nll")),
            "goal_b_recent_20_prequential_nll": number(
                goal_b.get("recent_20_prequential_nll")),
            "goal_b_family_nll": json.dumps(
                goal_b.get("family_nll") or {}, sort_keys=True),
        }
        row.update({field: number(metrics.get(field, diagnostic.get(field)))
                    for field in FIELDS if field not in row})
        rows.append(row)
    return rows


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["scene"]), str(row["condition"]))].append(row)
    fields = (*FIELDS, "explore_goal_count", "maintain_goal_count",
              "task_goal_count", "explore_goal_rate", "maintain_goal_rate")
    output: list[dict[str, Any]] = []
    for (scene, condition), items in sorted(grouped.items()):
        summary: dict[str, Any] = {
            "scene": scene, "condition": condition, "runs": len(items),
        }
        for field in fields:
            values = [float(item[field]) for item in items
                      if math.isfinite(float(item[field]))]
            summary[f"{field}_mean"] = statistics.fmean(values) if values else math.nan
            summary[f"{field}_std"] = statistics.stdev(values) if len(values) > 1 else 0.0
        output.append(summary)
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else
                "backend/data/experiments/efe_goal_policy_v1_quick").resolve()
    rows = load_runs(root)
    summaries = aggregate(rows)
    write_csv(root / "goal_policy_runs.csv", rows)
    write_csv(root / "goal_policy_aggregate.csv", summaries)
    lines = [
        "# EFE Goal Policy v1 Quick Experiment", "",
        f"Completed runs: {len(rows)}", "",
        "| scene | condition | final | spatial | completions | stuck | tie rate | explore rate | maintain rate | B updates | B NLL | B recent NLL |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summaries:
        lines.append(
            "| {scene} | {condition} | {final:.4f} | {spatial:.4f} | {completed:.2f} | "
            "{stuck:.2f} | {tie:.3f} | {explore:.3f} | {maintain:.3f} | "
            "{updates:.1f} | {nll:.4f} | {recent_nll:.4f} |".format(
                scene=item["scene"],
                condition=item["condition"],
                final=item["final_score_mean"],
                spatial=item["spatial_score_mean"],
                completed=item["goal_completions_mean"],
                stuck=item["goal_stuck_failures_mean"],
                tie=item["efe_score_tie_rate_mean"],
                explore=item["explore_goal_rate_mean"],
                maintain=item["maintain_goal_rate_mean"],
                updates=item["goal_b_updates_mean"],
                nll=item["goal_b_mean_prequential_nll_mean"],
                recent_nll=item["goal_b_recent_20_prequential_nll_mean"],
            )
        )
    (root / "goal_policy_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    print(f"Aggregated {len(rows)} runs under {root}")
    print(f"Report: {root / 'goal_policy_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
