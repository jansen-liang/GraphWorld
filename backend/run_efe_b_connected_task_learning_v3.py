#!/usr/bin/env python3
"""Independent runner for the connected Goal-conditioned-B V3 experiment."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import run_experiment
from backend.runtime.agent.efe_agent import efe_core
from backend.runtime.agent.efe_b_connected_task_learning_v3 import (
    EfeBConnectedTaskLearningV3Loop,
    connected_decompose_goal_v3,
    connected_select_goal_v3,
)


if __name__ == "__main__":
    run_experiment.EfeLoop = EfeBConnectedTaskLearningV3Loop
    efe_core.decompose_goal = connected_decompose_goal_v3
    efe_core.select_goal = connected_select_goal_v3
    run_experiment.main()
