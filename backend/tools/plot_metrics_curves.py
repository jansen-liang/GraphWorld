from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def plot_metrics(metrics_csv: Path, output: Path) -> Path:
    frame = pd.read_csv(metrics_csv)
    required = ["step", "final_score", "state_score", "spatial_score", "human_event_score"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"missing metric columns: {', '.join(missing)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig, (score_ax, blocking_ax) = plt.subplots(2, 1, figsize=(12, 7), sharex=True, gridspec_kw={"height_ratios": (3, 1)})
    styles = {
        "final_score": ("final score", "#1565c0"),
        "state_score": ("state score", "#2e7d32"),
        "spatial_score": ("spatial score", "#ef6c00"),
        "human_event_score": ("human event score", "#8e24aa"),
    }
    for column, (label, color) in styles.items():
        score_ax.plot(frame["step"], frame[column], label=label, linewidth=1.4, color=color)
    score_ax.set_ylabel("score")
    score_ax.set_ylim(0, 1.05)
    score_ax.grid(True, alpha=0.25)
    score_ax.legend(loc="best", ncol=2)
    if "human_blocking_total" in frame.columns:
        blocking_ax.plot(frame["step"], frame["human_blocking_total"], label="blocking total", color="#c62828", linewidth=1.2)
    if "human_blocking_recovered" in frame.columns:
        blocking_ax.plot(frame["step"], frame["human_blocking_recovered"], label="blocking recovered", color="#00838f", linewidth=1.2)
    blocking_ax.set_xlabel("step")
    blocking_ax.set_ylabel("blocking")
    blocking_ax.grid(True, alpha=0.25)
    blocking_ax.legend(loc="best")
    fig.suptitle(f"GraphWorld metrics: {metrics_csv.parent.name}")
    fig.tight_layout()
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Plot GraphWorld episode metric curves.")
    parser.add_argument("metrics_csv", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.metrics_csv.with_name("metrics_curves.png")
    print(plot_metrics(args.metrics_csv, output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
