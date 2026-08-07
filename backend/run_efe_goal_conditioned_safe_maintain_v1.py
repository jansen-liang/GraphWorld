#!/usr/bin/env python3
"""Independent experiment entry for safe goal-conditioned maintenance."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import run_experiment
from backend.runtime.agent.efe_goal_conditioned_safe_maintain_v1 import (
    EfeGoalConditionedSafeMaintainV1Loop,
)


if __name__ == "__main__":
    run_experiment.EfeLoop = EfeGoalConditionedSafeMaintainV1Loop
    run_experiment.main()
