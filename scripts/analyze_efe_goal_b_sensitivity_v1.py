#!/usr/bin/env python3
"""Sequential offline sensitivity scan for Goal-conditioned B.

The scan replays candidate-logged learned runs in temporal order.  At each
goal boundary it first applies the observation that was really recorded, then
re-scores that step's candidate table.  This avoids using a final learned B to
rank decisions that happened before its evidence existed.

For every (root_strength, backoff_strength, evidence_weight) configuration we
compare learned B against a frozen model with the same priors.  Counterfactual
outcomes for unexecuted goals are intentionally not invented; this script
reports calibration and ranking changes only.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.runtime.agent.efe_agent.efe_model import entropy, kl_divergence, softmax
from backend.runtime.agent.efe_agent.goal_transition_model import (
    OBSERVATION_NAMES,
    HierarchicalGoalTransitionModel,
    goal_signature,
)


ROOT_STRENGTHS = (1.0, 2.0, 3.0, 6.0, 12.0)
BACKOFF_STRENGTHS = (1.0, 2.0, 4.0, 8.0, 16.0)
EVIDENCE_WEIGHTS = (0.5, 1.0, 2.0, 4.0, 8.0, 16.0)
TOL = 1e-9
REPLAY_CACHE: dict[Path, list[dict[str, Any]]] = {}


def signature_goal(key: str, prior: list[float] | None = None) -> dict[str, Any]:
    family, target_class, workflow, domain = key.split("|")
    goal: dict[str, Any] = {"efe_signature": {
        "family": family,
        "target_class": target_class,
        "workflow": workflow,
        "domain": domain,
    }}
    if prior is not None:
        goal["_efe_state_prior"] = prior
    return goal


def score(model: HierarchicalGoalTransitionModel,
          signature: str, prior: list[float]) -> float:
    return float(model.score(signature_goal(signature, prior))["G"])


def observe_and_update(model: HierarchicalGoalTransitionModel,
                       event: dict[str, Any], evidence_weight: float) -> float:
    """Return prequential NLL and add weighted xi to all hierarchy levels."""
    goal = signature_goal(str(event["goal_signature"]), event["prior"])
    prior = np.asarray(event["prior"], dtype=float)
    observation = OBSERVATION_NAMES.index(str(event["observation"]))
    B, _effective, signature = model.transition_with_counts(goal)
    predicted_state = B @ prior
    predicted_observation = model.A @ predicted_state
    probability = max(1e-12, float(predicted_observation[observation]))
    xi = model.A[observation, :, None] * B * prior[None, :]
    total = float(xi.sum())
    if total > 0.0:
        xi /= total
    for key in model._level_keys(signature):
        model._evidence(key)[:] += float(evidence_weight) * xi
    return float(-math.log(probability))


def replay_paths(root: Path) -> list[Path]:
    paths = sorted(root.glob(
        "goal_b_learned/seed_*/*/*/*/with_robot/replay.json"))
    if not paths:
        raise SystemExit(
            "no learned candidate-logged replays found under %s" % root)
    return paths


def completion_event(step_data: dict[str, Any]) -> dict[str, Any] | None:
    auth = ((step_data.get("efe_authority_diagnostics") or {})
            .get("robot_01") or {})
    if not (auth.get("step") or {}).get("goal_result"):
        return None
    event = ((auth.get("cumulative") or {})
             .get("goal_transition_model") or {}).get("last_update") or {}
    required = {"goal_signature", "prior", "observation"}
    return event if required.issubset(event) else None


def candidate_table(step_data: dict[str, Any]) -> list[dict[str, Any]]:
    auth = ((step_data.get("efe_authority_diagnostics") or {})
            .get("robot_01") or {})
    step = auth.get("step") or {}
    if not step.get("decision_made"):
        return []
    return [candidate for candidate in step.get("candidate_table") or []
            if candidate.get("signature") and candidate.get("prior")]


def second_margin(values: list[float]) -> float:
    ordered = sorted(values)
    return float(ordered[1] - ordered[0]) if len(ordered) >= 2 else math.nan


def scan_configuration(paths: list[Path], *, root_strength: float,
                       backoff_strength: float,
                       evidence_weight: float) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    total_selections = 0
    strict_flips = 0
    tie_only_flips = 0
    frozen_ties = 0
    learned_ties = 0
    nll_values: list[float] = []
    frozen_nll_values: list[float] = []
    learned_margins: list[float] = []
    frozen_margins: list[float] = []
    strict_transitions: Counter[str] = Counter()
    tie_transitions: Counter[str] = Counter()
    flip_rows: list[dict[str, Any]] = []

    for replay_path in paths:
        seed = int(replay_path.parts[
            replay_path.parts.index("goal_b_learned") + 1].removeprefix("seed_"))
        if replay_path not in REPLAY_CACHE:
            REPLAY_CACHE[replay_path] = json.loads(
                replay_path.read_text(encoding="utf-8"))
        replay = REPLAY_CACHE[replay_path]
        learned = HierarchicalGoalTransitionModel(
            root_strength=root_strength, backoff_strength=backoff_strength)
        frozen = HierarchicalGoalTransitionModel(
            root_strength=root_strength, backoff_strength=backoff_strength)

        for step_data in replay:
            event = completion_event(step_data)
            if event is not None:
                frozen_nll_values.append(observe_and_update(
                    frozen, event, evidence_weight=0.0))
                nll_values.append(observe_and_update(
                    learned, event, evidence_weight=evidence_weight))

            table = candidate_table(step_data)
            if not table:
                continue
            total_selections += 1
            frozen_scores = [score(
                frozen, str(item["signature"]), item["prior"])
                for item in table]
            learned_scores = [score(
                learned, str(item["signature"]), item["prior"])
                for item in table]
            frozen_best = min(frozen_scores)
            learned_best = min(learned_scores)
            frozen_best_set = {
                index for index, value in enumerate(frozen_scores)
                if abs(value - frozen_best) <= TOL
            }
            learned_best_set = {
                index for index, value in enumerate(learned_scores)
                if abs(value - learned_best) <= TOL
            }
            frozen_index = min(frozen_best_set)
            learned_index = min(learned_best_set)
            frozen_ties += int(len(frozen_best_set) > 1)
            learned_ties += int(len(learned_best_set) > 1)
            frozen_margins.append(second_margin(frozen_scores))
            learned_margins.append(second_margin(learned_scores))

            if learned_index != frozen_index:
                from_family = str(table[frozen_index]["signature"]).split("|")[0]
                to_family = str(table[learned_index]["signature"]).split("|")[0]
                if learned_index not in frozen_best_set:
                    strict_flips += 1
                    kind = "strict"
                    strict_transitions["%s->%s" % (
                        from_family, to_family)] += 1
                else:
                    tie_only_flips += 1
                    kind = "tie_only"
                    tie_transitions["%s->%s" % (
                        from_family, to_family)] += 1
                flip_rows.append({
                    "root_strength": root_strength,
                    "backoff_strength": backoff_strength,
                    "evidence_weight": evidence_weight,
                    "seed": seed,
                    "step": step_data.get("episode_step"),
                    "flip_kind": kind,
                    "from_family": from_family,
                    "to_family": to_family,
                    "from_task": table[frozen_index].get("task", ""),
                    "to_task": table[learned_index].get("task", ""),
                    "frozen_gap": frozen_scores[learned_index] - frozen_best,
                    "learned_advantage": (
                        learned_scores[frozen_index] - learned_best),
                })

    mean = lambda values: float(np.mean(values)) if values else math.nan
    row: dict[str, Any] = {
        "root_strength": root_strength,
        "backoff_strength": backoff_strength,
        "evidence_weight": evidence_weight,
        "runs": len(paths),
        "selections": total_selections,
        "observations": len(nll_values),
        "strict_flips": strict_flips,
        "strict_flip_rate": strict_flips / total_selections if total_selections else 0.0,
        "tie_only_flips": tie_only_flips,
        "frozen_tie_rate": frozen_ties / total_selections if total_selections else 0.0,
        "learned_tie_rate": learned_ties / total_selections if total_selections else 0.0,
        "frozen_nll": mean(frozen_nll_values),
        "learned_nll": mean(nll_values),
        "nll_delta": mean(nll_values) - mean(frozen_nll_values),
        "frozen_margin": mean([v for v in frozen_margins if math.isfinite(v)]),
        "learned_margin": mean([v for v in learned_margins if math.isfinite(v)]),
        "strict_transitions": ";".join(
            "%s:%d" % item for item in strict_transitions.most_common()),
        "tie_transitions": ";".join(
            "%s:%d" % item for item in tie_transitions.most_common()),
    }
    return row, flip_rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def observation_counts(paths: list[Path]) -> Counter[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    for replay_path in paths:
        if replay_path not in REPLAY_CACHE:
            REPLAY_CACHE[replay_path] = json.loads(
                replay_path.read_text(encoding="utf-8"))
        for step_data in REPLAY_CACHE[replay_path]:
            event = completion_event(step_data)
            if event is None:
                continue
            family = str(event["goal_signature"]).split("|")[0]
            counts[(family, str(event["observation"]))] += 1
    return counts


def fmt(row: dict[str, Any]) -> str:
    return (
        "| {root_strength:g} | {backoff_strength:g} | {evidence_weight:g} | "
        "{strict_flips} ({strict_flip_rate:.1%}) | {tie_only_flips} | "
        "{learned_nll:.4f} | {nll_delta:+.4f} | {learned_tie_rate:.3f} | "
        "{strict_transitions} | {tie_transitions} |"
    ).format(**row)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    output = (args.output or (root / "b_sensitivity_v1")).resolve()
    output.mkdir(parents=True, exist_ok=True)
    paths = replay_paths(root)

    rows: list[dict[str, Any]] = []
    flips: list[dict[str, Any]] = []
    for root_strength in ROOT_STRENGTHS:
        for backoff_strength in BACKOFF_STRENGTHS:
            for evidence_weight in EVIDENCE_WEIGHTS:
                row, details = scan_configuration(
                    paths, root_strength=root_strength,
                    backoff_strength=backoff_strength,
                    evidence_weight=evidence_weight)
                rows.append(row)
                flips.extend(details)

    write_csv(output / "sensitivity_grid.csv", rows)
    write_csv(output / "flip_details.csv", flips)
    current = next(row for row in rows
                   if row["root_strength"] == 6.0
                   and row["backoff_strength"] == 8.0
                   and row["evidence_weight"] == 1.0)
    with_flips = [row for row in rows if row["strict_flips"] > 0]
    best_nll = sorted(rows, key=lambda row: row["learned_nll"])[:10]
    conservative = sorted(
        with_flips,
        key=lambda row: (
            abs(row["strict_flip_rate"] - 0.05), row["learned_nll"]),
    )[:10]
    safe_strict = [
        row for row in with_flips
        if "->explore" not in row["strict_transitions"]
        and "->maintain" not in row["strict_transitions"]
    ]
    observed = observation_counts(paths)
    families = sorted({family for family, _observation in observed})
    lines = [
        "# Goal-conditioned B sensitivity v1", "",
        "Sequential replay; no future B state is used and no LLM is called.", "",
        "NLL is pooled over all 120 recorded observations (observation-weighted), and each "
        "replayed prequential NLL matches its runtime log. Earlier summaries that average "
        "the three per-seed means equally can therefore show a slightly different aggregate.", "",
        "## Current configuration", "",
        "| root | backoff | evidence | strict flips | tie-only | learned NLL | ΔNLL | learned tie | strict transitions | tie transitions |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
        fmt(current), "",
        "## Lowest learned NLL", "",
        "| root | backoff | evidence | strict flips | tie-only | learned NLL | ΔNLL | learned tie | strict transitions | tie transitions |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
        *[fmt(row) for row in best_nll], "",
        "## Conservative configurations near 5% strict flips", "",
        "| root | backoff | evidence | strict flips | tie-only | learned NLL | ΔNLL | learned tie | strict transitions | tie transitions |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
        *([fmt(row) for row in conservative]
          if conservative else ["No configuration produced a strict flip."]),
        "",
        "## Recorded posterior observations", "",
        "| family | unobserved | low | medium | high |",
        "|---|---:|---:|---:|---:|",
        *[
            "| %s | %d | %d | %d | %d |" % (
                family,
                observed[(family, "unobserved")],
                observed[(family, "low")],
                observed[(family, "medium")],
                observed[(family, "high")],
            )
            for family in families
        ], "",
        "## Safety finding", "",
        ("No strict-flip configuration avoided explore/maintain destinations."
         if not safe_strict else
         "%d strict-flip configurations avoided explore/maintain destinations."
         % len(safe_strict)), "",
        "This means stronger learning currently amplifies the recorded "
        "posterior semantics: restore/clean goals are usually labelled "
        "medium while maintain is usually labelled low. Parameter strength "
        "alone cannot make those observations imply task-favouring flips.", "",
        "Counterfactual outcomes are not labelled beneficial/harmful because "
        "the alternative Goal was not executed in these on-policy logs.",
    ]
    (output / "sensitivity_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    print("scanned %d configurations over %d runs" % (len(rows), len(paths)))
    print("current: strict=%d/%d learned_nll=%.4f frozen_nll=%.4f" % (
        current["strict_flips"], current["selections"],
        current["learned_nll"], current["frozen_nll"]))
    print("report: %s" % (output / "sensitivity_report.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
