#!/usr/bin/env python3
"""Validate that a V3 smoke run updated B and reused it in later scores."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

# Direct execution sets sys.path[0] to scripts/, so add the repository root
# before importing backend modules.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.runtime.agent.efe_agent.goal_transition_model import (
    HierarchicalGoalTransitionModel,
)


root = Path(sys.argv[1]).resolve()
summaries = sorted(root.rglob("summary.json"))
if len(summaries) != 1:
    raise SystemExit(
        f"V3预检失败：预期1个summary.json，实际找到{len(summaries)}个")

data = json.loads(summaries[0].read_text(encoding="utf-8"))
run = next(
    (item for item in data.get("runs", [])
     if item.get("experiment") == "with_robot"),
    None,
)
if run is None:
    raise SystemExit("V3预检失败：没有with_robot结果")
diagnostics = next(iter(
    (run.get("efe_authority_diagnostics") or {}).values()), {})
transition = diagnostics.get("goal_transition_model") or {}
updates = int(transition.get("updates") or 0)
skipped = int(transition.get("v3_maintain_samples_skipped") or 0)
connection = str(diagnostics.get("b_connection_variant") or "")

max_leaf_samples = 0.0
max_score_change_from_fresh_b = 0.0
scored_rows = 0
metrics_paths = sorted(root.rglob("metrics.csv"))
for metrics_path in metrics_paths:
    with metrics_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                payload = json.loads(row.get("efe_authority_diagnostics") or "{}")
            except json.JSONDecodeError:
                continue
            for robot_data in payload.values():
                step_data = (robot_data or {}).get("step") or {}
                for candidate in step_data.get("candidate_table") or []:
                    scored_rows += 1
                    max_leaf_samples = max(
                        max_leaf_samples,
                        float(candidate.get("leaf_samples") or 0.0),
                    )
                    # Hierarchical B deliberately transfers evidence from
                    # action-kind/family/target parents before an exact leaf
                    # signature repeats.  Therefore leaf_samples may remain
                    # zero even though learned B changed this candidate's
                    # score.  Compare the logged score against a brand-new B
                    # under the exact same signature and state prior.
                    signature = str(candidate.get("signature") or "").split("|")
                    prior = candidate.get("prior")
                    observed_g = candidate.get("G")
                    if (len(signature) == 4 and isinstance(prior, list)
                            and isinstance(observed_g, (int, float))):
                        fresh_goal = {
                            "efe_signature": dict(zip(
                                ("family", "target_class", "workflow", "domain"),
                                signature,
                            )),
                            "_efe_state_prior": prior,
                        }
                        fresh_g = HierarchicalGoalTransitionModel().score(
                            fresh_goal)["G"]
                        max_score_change_from_fresh_b = max(
                            max_score_change_from_fresh_b,
                            abs(float(observed_g) - float(fresh_g)),
                        )

print(
    "V3 smoke result: "
    f"connection={connection}, B_updates={updates}, "
    f"maintain_skipped={skipped}, scored_candidates={scored_rows}, "
    f"max_leaf_samples={max_leaf_samples:.3f}, "
    f"max_score_change_from_fresh_B={max_score_change_from_fresh_b:.6f}"
)
if connection != "efe_b_connected_task_learning_v3":
    raise SystemExit("V3预检失败：运行时没有使用V3接线")
if updates <= 0:
    raise SystemExit("V3预检失败：任务/探索B没有发生更新")
if skipped <= 0:
    raise SystemExit("V3预检失败：没有过滤重复maintain证据")
if max_score_change_from_fresh_b <= 1e-9:
    raise SystemExit("V3预检失败：候选评分与全新默认B完全相同")
print("V3预检通过：学习后的B已进入候选目标评分。")
