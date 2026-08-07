#!/usr/bin/env python3
"""Summarize the isolated EFE exploration-navigation v1 experiment."""

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
    "mean_failed_goal_duration", "explore_navigation_decisions",
    "explore_navigation_overrides", "explore_navigation_override_rate",
    "explore_navigation_fallbacks", "explore_navigation_fallback_rate",
    "explore_navigation_move_next_room", "explore_navigation_open_connecting_door",
    "explore_navigation_move_connecting_door", "explore_navigation_arrivals",
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
        diagnostic = next(iter((run.get("efe_authority_diagnostics") or {}).values()), {})
        metrics = run.get("final_metrics") or {}
        row: dict[str, Any] = {
            "condition": str(data.get("efe_goal_authority") or path.parts[-6]),
            "scene": str(data.get("scene") or ""),
            "seed": int(data.get("schedule_seed") or 0),
            "summary_path": str(path.resolve()),
        }
        row.update({key: number(metrics.get(key, diagnostic.get(key))) for key in FIELDS})
        rows.append(row)
    return rows


def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["condition"], row["scene"])].append(row)
    output: list[dict[str, Any]] = []
    for (condition, scene), items in sorted(groups.items()):
        summary: dict[str, Any] = {"condition": condition, "scene": scene, "runs": len(items)}
        for field in FIELDS:
            values = [float(item[field]) for item in items if math.isfinite(float(item[field]))]
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
                "backend/data/experiments/efe_explore_navigation_v1_hospital").resolve()
    rows = load_runs(root)
    summaries = aggregate(rows)
    write_csv(root / "navigation_runs.csv", rows)
    write_csv(root / "navigation_aggregate_summary.csv", summaries)
    (root / "navigation_aggregate_summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Aggregated {len(rows)} navigation-v1 runs under {root}")
    print(f"Aggregate: {root / 'navigation_aggregate_summary.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
