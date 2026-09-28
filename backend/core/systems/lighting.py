"""Lighting system boundary for emitters, direction, and occlusion semantics."""

from typing import Any


def tick(world: Any, elapsed_steps: int = 1) -> None:
    return None


__all__ = ["tick"]
