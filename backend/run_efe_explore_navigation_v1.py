#!/usr/bin/env python3
"""Independent entry point for the EFE exploration-navigation v1 experiment."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import run_experiment
from backend.runtime.agent.efe_explore_navigation_v1 import EfeExploreNavigationV1Loop


def main() -> None:
    # run_experiment constructs EfeLoop through this module binding.  Replacing
    # it here affects only this process and does not modify the original file.
    run_experiment.EfeLoop = EfeExploreNavigationV1Loop
    run_experiment.main()


if __name__ == "__main__":
    main()
