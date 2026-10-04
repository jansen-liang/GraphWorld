"""Simulation clock owned by the runtime layer."""

from __future__ import annotations

from typing import Any

from backend.runtime.process_rules import advance_time as advance_world_rules


def advance_time(world: dict[str, Any], elapsed_steps: int = 1) -> list[str]:
    """Advance the shared simulation clock through the core transition rules."""
    return advance_world_rules(world, elapsed_steps)


__all__ = ["advance_time"]
