"""Physics-engine collision and raycast adapters."""

from .placement import (
    floor_collision_failure,
    normalized_surface_anchor,
    surface_collision_failure,
    surface_fit_failure,
    surface_load_failure,
    volume_load_failure,
)

__all__ = [
    "floor_collision_failure", "normalized_surface_anchor", "surface_collision_failure",
    "surface_fit_failure", "surface_load_failure", "volume_load_failure",
]
