#!/usr/bin/env python3
"""Independent runner for clean-entry evidence formula experiments."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import run_experiment
from backend.runtime.agent.efe_agent import efe_core
from backend.runtime.agent.efe_clean_entry_evidence_v1 import (
    EfeCleanEntryEvidenceV1Loop,
)
from backend.runtime.agent.efe_formula_staleness_v1 import (
    configured_decompose_goal,
    configured_select_goal,
)


if __name__ == "__main__":
    run_experiment.EfeLoop = EfeCleanEntryEvidenceV1Loop
    efe_core.decompose_goal = configured_decompose_goal
    efe_core.select_goal = configured_select_goal
    run_experiment.main()
