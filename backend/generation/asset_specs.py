"""Static geometry defaults used while generating legacy/simple assets.

These values describe generated asset declarations.  They are deliberately
kept outside the physics adapter; the adapter only evaluates the dimensions
that a materialized node carries.
"""

from __future__ import annotations

from typing import Any


DEFAULT_SURFACE_SIZES_CM: dict[str, tuple[float, float]] = {
    "table": (100.0, 60.0),
    "coffee_table": (90.0, 50.0),
    "counter": (180.0, 65.0),
    "desk": (120.0, 60.0),
    "shelf": (150.0, 35.0),
    "rack": (150.0, 35.0),
    "cabinet": (120.0, 35.0),
    "drawer": (80.0, 45.0),
    "drying_rack": (120.0, 45.0),
    "bed": (190.0, 90.0),
    "sofa": (180.0, 80.0),
    "seat": (60.0, 60.0),
    "chair": (50.0, 50.0),
}

DEFAULT_FOOTPRINTS_CM: dict[str, tuple[float, float]] = {
    "cup": (10.0, 10.0), "mug": (12.0, 10.0), "plate": (25.0, 25.0),
    "bowl": (20.0, 20.0), "glass": (8.0, 8.0), "milk": (8.0, 8.0),
    "juice": (8.0, 8.0), "fruit": (12.0, 12.0), "vegetable": (15.0, 15.0),
    "book": (20.0, 14.0), "box": (20.0, 20.0), "bread": (25.0, 12.0),
}

DEFAULT_INTERIOR_SIZES_CM: dict[str, tuple[float, float, float]] = {
    "storage_slot": (40.0, 30.0, 30.0),
    "drawer": (80.0, 45.0, 15.0),
    "refrigerator": (60.0, 55.0, 150.0),
    "fridge": (60.0, 55.0, 150.0),
    "cabinet": (120.0, 35.0, 120.0),
    "wardrobe": (120.0, 55.0, 180.0),
    "washer": (55.0, 55.0, 55.0),
    "washing_machine": (55.0, 55.0, 55.0),
    "microwave": (45.0, 35.0, 25.0),
}


def surface_spec_for(semantic_type: str) -> dict[str, Any] | None:
    size = DEFAULT_SURFACE_SIZES_CM.get(str(semantic_type or "").lower())
    return {"surface_size_cm": list(size), "surface_grid_cm": 1.0} if size else None


def footprint_for(semantic_type: str) -> dict[str, Any] | None:
    size = DEFAULT_FOOTPRINTS_CM.get(str(semantic_type or "").lower())
    return {"footprint_cm": list(size)} if size else None


def interior_spec_for(semantic_type: str) -> dict[str, Any] | None:
    size = DEFAULT_INTERIOR_SIZES_CM.get(str(semantic_type or "").lower())
    return {"interior_size_cm": list(size)} if size else None


__all__ = [
    "DEFAULT_FOOTPRINTS_CM",
    "DEFAULT_INTERIOR_SIZES_CM",
    "DEFAULT_SURFACE_SIZES_CM",
    "footprint_for",
    "interior_spec_for",
    "surface_spec_for",
]
