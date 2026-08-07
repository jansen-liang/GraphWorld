#!/usr/bin/env python3
"""Fail fast unless a smoke run performed real Goal-conditioned B updates."""

from __future__ import annotations

import json
import sys
from pathlib import Path


root = Path(sys.argv[1])
summaries = sorted(root.rglob("summary.json"))
if len(summaries) != 1:
    raise SystemExit(
        f"B smoke validation failed: expected 1 summary, found {len(summaries)}")
data = json.loads(summaries[0].read_text(encoding="utf-8"))
run = next(
    (item for item in data.get("runs", [])
     if item.get("experiment") == "with_robot"),
    None,
)
if run is None:
    raise SystemExit("B smoke validation failed: with_robot run is missing")
diagnostics = next(iter(
    (run.get("efe_authority_diagnostics") or {}).values()), {})
transition = diagnostics.get("goal_transition_model") or {}
updates = int(transition.get("updates") or 0)
observations = int(transition.get("observations") or 0)
mode = str(diagnostics.get("efe_mode") or "")
print(f"B smoke result: mode={mode}, updates={updates}, observations={observations}")
if mode != "goal_conditioned_b" or updates <= 0:
    raise SystemExit(
        "B smoke validation failed: formal groups will NOT start because "
        "goal_conditioned_b produced no B updates")
print("B smoke validation passed; formal experiment may start.")
