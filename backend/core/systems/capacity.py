"""Capacity and containment system boundary."""

from typing import Any


def can_place(world: Any, object_id: str, target_id: str) -> bool:
    return True


__all__ = ["can_place"]
