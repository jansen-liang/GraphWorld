"""Liquid system boundary.

Liquid transfer and level updates belong here; object templates only declare
container capabilities and liquid metadata.
"""

from typing import Any


def tick(world: Any, elapsed_steps: int = 1) -> None:
    return None


__all__ = ["tick"]
