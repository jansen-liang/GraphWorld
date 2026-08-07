#!/usr/bin/env python3
"""Independent runner for the budgeted EFE exploration-navigation v2."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import run_experiment
from backend.runtime.agent.efe_explore_navigation_v2_budgeted import (
    EfeExploreNavigationV2BudgetedLoop,
)


if __name__ == "__main__":
    run_experiment.EfeLoop = EfeExploreNavigationV2BudgetedLoop
    run_experiment.main()
