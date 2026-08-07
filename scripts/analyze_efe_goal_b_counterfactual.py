#!/usr/bin/env python3
"""Offline counterfactual analysis of Goal-conditioned B EFE validation runs.

Reads EFE_CANDIDATE_LOG=1 replays and re-ranks every scored candidate table
under the *frozen* (prior-only) hierarchical B, then compares against the
runtime (learned-B) selection.  Answers: does B learning change any decision?

Reports:
  - counterfactual flip rate: how often frozen-B argmin != runtime selection
  - learned-vs-frozen goal-family selection divergence per seed
  - per-family prequential NLL from summary diagnostics
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.runtime.agent.efe_agent.efe_model import kl_divergence, entropy, softmax
from backend.runtime.agent.efe_agent.goal_transition_model import (
    DEFAULT_A, DEFAULT_C, GoalSignature, HierarchicalGoalTransitionModel,
)


def frozen_efe_score(signature_key: str, prior: list[float],
                     model: HierarchicalGoalTransitionModel,
                     ) -> tuple[float, float]:
    """(risk, ambiguity) for a candidate under prior-only (frozen) B."""
    family, target_class, workflow, domain = signature_key.split("|")
    goal = {"efe_signature": {
        "family": family, "target_class": target_class,
        "workflow": workflow, "domain": domain,
    }}
    B, _, _ = model.transition_with_counts(goal)   # counts empty -> prior only
    q_state = B @ np.asarray(prior, dtype=float)
    q_obs = model.A @ q_state
    pref = softmax(model.C)
    risk = kl_divergence(q_obs, pref)
    ambiguity = float(np.dot(q_state, entropy(model.A, axis=0)))
    return risk, ambiguity


def load_candidate_tables(replay_path: Path,
                          replay: list | None = None) -> list[dict]:
    """Every step's scored candidate table from a candidate-logged replay."""
    if replay is None:
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
    tables = []
    for step_data in replay:
        auth = ((step_data.get("efe_authority_diagnostics") or {})
                .get("robot_01") or {})
        step_info = auth.get("step") or {}
        if not step_info.get("candidate_table"):
            continue
        tables.append({
            "step": step_data.get("episode_step"),
            "selected_task": step_info.get("selected_task"),
            "selected_family": step_info.get("selected_goal_family"),
            "decision_made": bool(step_info.get("decision_made")),
            "candidates": step_info["candidate_table"],
        })
    return tables


def analyze_run(replay_path: Path, replay: list | None = None) -> dict:
    model = HierarchicalGoalTransitionModel()
    tables = load_candidate_tables(replay_path, replay=replay)
    outcomes = goal_outcomes(replay_path, replay=replay)
    selections = 0
    flips = 0
    frozen_ties = 0
    examples: list[dict] = []
    for table in tables:
        if not table["decision_made"]:
            continue
        scored = []
        for cand in table["candidates"]:
            if not cand.get("signature") or not cand.get("prior"):
                continue
            risk, ambiguity = frozen_efe_score(
                cand["signature"], cand["prior"], model)
            scored.append((risk + ambiguity, cand))
        if not scored:
            continue
        selections += 1
        best_frozen = min(s for s, _ in scored)
        if sum(abs(s - best_frozen) <= 1e-9 for s, _ in scored) > 1:
            frozen_ties += 1
        best_cand = min(scored, key=lambda pair: pair[0])[1]
        # A genuine flip: the runtime selection is *strictly* worse under
        # frozen B than the frozen-B argmin (ties are not flips).
        selected_score = next(
            (s for s, c in scored if c.get("task") == table["selected_task"]),
            None)
        flipped = (selected_score is not None
                   and selected_score > best_frozen + 1e-9)
        if flipped:
            flips += 1
            if len(examples) < 10:
                examples.append({
                    "step": table["step"],
                    "selected": table["selected_task"],
                    "selected_family": table["selected_family"],
                    "selected_result": outcomes.get(
                        table["selected_task"], "?"),
                    "counterfactual": best_cand.get("task"),
                    "counterfactual_family": best_cand.get("signature", "")
                    .split("|")[0],
                    "counterfactual_gap": round(
                        selected_score - best_frozen, 4),
                })
    return {
        "selections": selections,
        "flips": flips,
        "flip_rate": flips / selections if selections else 0.0,
        "frozen_tie_rate": frozen_ties / selections if selections else 0.0,
        "examples": examples,
    }


def selection_sequence(replay_path: Path,
                       replay: list | None = None) -> list[str]:
    if replay is None:
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
    seq = []
    for step_data in replay:
        auth = ((step_data.get("efe_authority_diagnostics") or {})
                .get("robot_01") or {})
        step_info = auth.get("step") or {}
        if step_info.get("decision_made"):
            seq.append("%s|%s" % (step_info.get("selected_family", ""),
                                  step_info.get("selected_task", "")))
    return seq


def goal_outcomes(replay_path: Path,
                  replay: list | None = None) -> dict[str, str]:
    """Map finished-goal task -> result, from goal_result audit fields."""
    if replay is None:
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
    outcomes: dict[str, str] = {}
    for step_data in replay:
        auth = ((step_data.get("efe_authority_diagnostics") or {})
                .get("robot_01") or {})
        step_info = auth.get("step") or {}
        result = step_info.get("goal_result")
        task = step_info.get("goal_result_task")
        if result and task:
            outcomes[task] = result
    return outcomes


def cumulative_nll_series(replay_path: Path,
                          replay: list | None = None) -> list[float]:
    """Recover cumulative prequential NLL sums from per-step cumulative
    diagnostics (mean_nll * observations at each step), plus the last value
    as the run total."""
    if replay is None:
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
    sums = []
    for step_data in replay:
        auth = ((step_data.get("efe_authority_diagnostics") or {})
                .get("robot_01") or {})
        cum = auth.get("cumulative") or {}
        tm = cum.get("goal_transition_model") or {}
        obs = tm.get("observations")
        mean = tm.get("mean_prequential_nll")
        if isinstance(obs, (int, float)) and isinstance(mean, (int, float)) \
                and obs and mean is not None:
            sums.append(float(obs) * float(mean))
    return sums


def segment_nll(sums: list[float]) -> dict[str, float]:
    """Split recovered cumulative NLL sums into first/second half means."""
    if not sums:
        return {}
    n = len(sums)
    half = max(1, n // 2)
    first = sums[half - 1] / half if half else 0.0
    second = (sums[-1] - sums[half - 1]) / max(1, n - half)
    return {"first_half_nll": first, "second_half_nll": second}


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else
                "backend/data/experiments/efe_goal_b_v2_validation_home_100_candlog"
                ).resolve()
    runs = sorted(root.glob("*/seed_*/*/*/*/with_robot/replay.json"))
    print("runs found: %d\n" % len(runs))

    learned_sequences: dict[int, list[str]] = {}
    frozen_sequences: dict[int, list[str]] = {}
    learned_outcomes: dict[int, dict[str, str]] = {}
    flip_goal_results: dict[str, list[str]] = {}
    all_flips = 0
    all_selections = 0
    for replay_path in runs:
        condition = replay_path.relative_to(root).parts[0]
        seed = int(replay_path.relative_to(root).parts[1].removeprefix("seed_"))
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        stats = analyze_run(replay_path, replay=replay)
        seq = selection_sequence(replay_path, replay=replay)
        if condition == "goal_b_learned":
            learned_sequences[seed] = seq
            learned_outcomes[seed] = goal_outcomes(replay_path, replay=replay)
            for ex in stats["examples"]:
                flip_goal_results.setdefault(ex["selected_result"], [])\
                    .append(ex["selected"][:24])
        elif condition == "goal_b_frozen":
            frozen_sequences[seed] = seq
        all_flips += stats["flips"]
        all_selections += stats["selections"]
        print("== %-18s seed %d ==" % (condition, seed))
        seg = segment_nll(cumulative_nll_series(replay_path, replay=replay))
        print("   selections=%d flips=%d flip_rate=%.3f frozen_tie_rate=%.3f"
              % (stats["selections"], stats["flips"],
                 stats["flip_rate"], stats["frozen_tie_rate"]))
        if seg:
            print("   NLL first-half=%.3f second-half=%.3f (delta %.3f)"
                  % (seg["first_half_nll"], seg["second_half_nll"],
                     seg["second_half_nll"] - seg["first_half_nll"]))
        for ex in stats["examples"]:
            print("   flip@step%-4d sel=%-26s[%s] -> cf=%-26s(gap=%.3f)"
                  % (ex["step"], ex["selected"][:26], ex["selected_result"],
                     ex["counterfactual"][:26], ex["counterfactual_gap"]))
        if condition == "goal_b_learned" and seed in learned_outcomes:
            results = list(learned_outcomes[seed].values())
            done = results.count("completed")
            print("   goal outcomes: %d completed / %d failed / %d total"
                  % (done, len(results) - done, len(results)))

    print("\n== learned vs frozen selection divergence (per seed) ==")
    for seed in sorted(set(learned_sequences) & set(frozen_sequences)):
        lseq, fseq = learned_sequences[seed], frozen_sequences[seed]
        common = min(len(lseq), len(fseq))
        diff = sum(a != b for a, b in zip(lseq[:common], fseq[:common]))
        print("seed %d: learned=%d frozen=%d selections, common=%d, "
              "differing=%d (%.1f%%)"
              % (seed, len(lseq), len(fseq), common, diff,
                 100.0 * diff / common if common else 0.0))

    print("\n== flip goals by outcome (%d flips / %d selections, %.1f%%) =="
          % (all_flips, all_selections,
             100.0 * all_flips / all_selections if all_selections else 0.0))
    for result in ("completed", "failed", "?"):
        items = flip_goal_results.get(result, [])
        if items:
            print("  %-9s n=%d | %s" % (result, len(items), "; ".join(items)))

    # per-family NLL from summaries
    print("\n== per-family prequential NLL (from summary diagnostics) ==")
    for summary_path in sorted(root.glob("*/seed_*/*/*/*/summary.json")):
        condition = summary_path.relative_to(root).parts[0]
        seed = int(summary_path.relative_to(root).parts[1].removeprefix("seed_"))
        data = json.loads(summary_path.read_text(encoding="utf-8"))
        run = next((item for item in data.get("runs") or []
                    if item.get("experiment") == "with_robot"), None)
        if not run:
            continue
        diagnostic = next(iter(
            (run.get("efe_authority_diagnostics") or {}).values()), {})
        family_nll = (diagnostic.get("goal_transition_model") or {}) \
            .get("family_nll") or {}
        bits = []
        for family in ("maintain", "explore", "restore_object", "clean_state",
                       "dispose_waste", "laundry", "return_supply", "other"):
            info = family_nll.get(family)
            if info:
                bits.append("%s:%.3f(n=%d)" % (family, info["mean"],
                                               info["count"]))
        print("%-18s seed %d | %s" % (condition, seed, " ".join(bits)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
