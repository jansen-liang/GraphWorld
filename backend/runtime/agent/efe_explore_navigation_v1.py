"""Compatibility entry points for the former NavigationV1 experiment.

NavigationV1 is now part of the main :class:`EfeLoop` and is enabled by
default.  This module remains so existing scripts and imports keep working.
"""

from __future__ import annotations

from typing import Any

from backend.runtime.agent.decision import (
    choose_explore_navigation_action,
    next_room_on_shortest_path,
    robot_room,
    room_graph,
)
from backend.runtime.agent.efe_agent.efe_core import EfeLoop


class EfeExploreNavigationV1Loop(EfeLoop):
    """Backward-compatible name for mainline EfeLoop with NavigationV1."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("explore_navigation", "v1")
        super().__init__(*args, **kwargs)


__all__ = [
    "EfeExploreNavigationV1Loop",
    "choose_explore_navigation_action",
    "next_room_on_shortest_path",
    "robot_room",
    "room_graph",
]
