#!/usr/bin/env python3
"""Canonical V3 summary excluding known overlapping launcher outputs."""

from __future__ import annotations

import math
import sys
from pathlib import Path

from summarize_efe_goal_policy_v1 import aggregate, load_runs, write_csv


# These runs came from launchers that were believed stopped but later resumed
# concurrently. Their intended clean-restart counterparts remain included.
EXCLUDED_RUN_IDS = {
    "20260807T041320Z_a587a160",  # abnormal 185-minute group 9
    "20260807T071911Z_1a8366db",  # overlapping second group 13
}


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    rows = [
        row for row in load_runs(root)
        if not any(run_id in str(row.get("summary_path") or "")
                   for run_id in EXCLUDED_RUN_IDS)
    ]

    seen: dict[tuple[str, int], str] = {}
    for row in rows:
        key = (str(row["condition"]), int(row["seed"]))
        if key in seen:
            raise SystemExit(
                "Canonical V3 summary refused an unexpected duplicate for "
                f"{key}: {seen[key]} and {row['summary_path']}")
        seen[key] = str(row["summary_path"])

    summaries = aggregate(rows)
    write_csv(root / "goal_policy_runs.csv", rows)
    write_csv(root / "goal_policy_aggregate.csv", summaries)
    lines = [
        "# EFE Connected-B V3 Canonical Experiment", "",
        f"Canonical completed runs: {len(rows)}", "",
        "Excluded overlapping run ids: " + ", ".join(sorted(EXCLUDED_RUN_IDS)),
        "",
        "| scene | condition | final | spatial | completions | stuck | tie rate | explore rate | maintain rate | B updates | B NLL | B recent NLL |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summaries:
        lines.append(
            "| {scene} | {condition} | {final:.4f} | {spatial:.4f} | "
            "{completed:.2f} | {stuck:.2f} | {tie:.3f} | {explore:.3f} | "
            "{maintain:.3f} | {updates:.1f} | {nll:.4f} | {recent:.4f} |".format(
                scene=item["scene"], condition=item["condition"],
                final=item["final_score_mean"],
                spatial=item["spatial_score_mean"],
                completed=item["goal_completions_mean"],
                stuck=item["goal_stuck_failures_mean"],
                tie=item["efe_score_tie_rate_mean"],
                explore=item["explore_goal_rate_mean"],
                maintain=item["maintain_goal_rate_mean"],
                updates=item["goal_b_updates_mean"],
                nll=item["goal_b_mean_prequential_nll_mean"],
                recent=item["goal_b_recent_20_prequential_nll_mean"],
            )
        )
    (root / "goal_policy_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    print(f"Canonical V3 runs: {len(rows)}")
    print(f"Report: {root / 'goal_policy_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
