"""Surface placement metadata and deterministic snapping helpers."""

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
}

DEFAULT_FOOTPRINTS_CM: dict[str, tuple[float, float]] = {
    "cup": (10.0, 10.0), "mug": (12.0, 10.0), "plate": (25.0, 25.0),
    "bowl": (20.0, 20.0), "glass": (8.0, 8.0), "milk": (8.0, 8.0),
    "juice": (8.0, 8.0), "fruit": (12.0, 12.0), "vegetable": (15.0, 15.0),
    "book": (20.0, 14.0), "box": (20.0, 20.0), "bread": (25.0, 12.0),
}

# Interior dimensions are expressed as width, depth, height in centimetres.
# A generated storage slot may override these with its topology-derived size.
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
    if size is None:
        return None
    return {"surface_size_cm": list(size), "surface_grid_cm": 1.0}


def footprint_for(semantic_type: str) -> dict[str, Any] | None:
    size = DEFAULT_FOOTPRINTS_CM.get(str(semantic_type or "").lower())
    return {"footprint_cm": list(size)} if size is not None else None


def interior_spec_for(semantic_type: str) -> dict[str, Any] | None:
    size = DEFAULT_INTERIOR_SIZES_CM.get(str(semantic_type or "").lower())
    return {"interior_size_cm": list(size)} if size is not None else None


def _number(value: Any, fallback: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return fallback
    return result if result == result else fallback


def normalized_surface_anchor(payload: dict[str, Any] | None, *, grid_cm: float = 1.0) -> list[float]:
    """Return a clamped, grid-snapped [u, v] surface anchor.

    `surface_anchor` is normalized. `surface_point_cm` is accepted when a
    caller has a physical hit point and `surface_size_cm` is known.
    """
    payload = payload or {}
    hit = payload.get("interaction_hit")
    hit_anchor = (hit.get("surface_uv") or hit.get("uv")) if isinstance(hit, dict) else None
    anchor = payload.get("surface_anchor") or hit_anchor
    if isinstance(anchor, dict):
        values = [_number(anchor.get("u"), 0.5), _number(anchor.get("v"), 0.5)]
    elif isinstance(anchor, (list, tuple)) and len(anchor) >= 2:
        values = [_number(anchor[0], 0.5), _number(anchor[1], 0.5)]
    else:
        point = payload.get("surface_point_cm")
        size = payload.get("surface_size_cm")
        if isinstance(point, (list, tuple)) and isinstance(size, (list, tuple)) and len(point) >= 2 and len(size) >= 2:
            width = max(0.001, _number(size[0], 1.0))
            depth = max(0.001, _number(size[1], 1.0))
            values = [_number(point[0], width / 2) / width, _number(point[1], depth / 2) / depth]
        else:
            values = [0.5, 0.5]
    step = max(0.0, _number(grid_cm, 0.0))
    size = payload.get("surface_size_cm")
    if step and isinstance(size, (list, tuple)) and len(size) >= 2:
        width = max(0.001, _number(size[0], 1.0))
        depth = max(0.001, _number(size[1], 1.0))
        values = [round(values[0] * width / step) * step / width, round(values[1] * depth / step) * step / depth]
    return [max(0.0, min(1.0, round(value, 6))) for value in values]


def attach_surface_metadata(item: dict[str, Any], target: dict[str, Any], payload: dict[str, Any] | None = None) -> None:
    """Record where an item was placed without changing its parent relation."""
    target_size = target.get("surface_size_cm") or target.get("support_surface_cm")
    grid_cm = target.get("surface_grid_cm") or target.get("support_grid_cm") or 1.0
    item["placement_anchor"] = normalized_surface_anchor(
        {**(payload or {}), "surface_size_cm": (payload or {}).get("surface_size_cm") or target_size},
        grid_cm=_number(grid_cm, 1.0),
    )
    item["placement_target"] = str(target.get("id") or "")
    if isinstance(payload, dict) and isinstance(payload.get("interaction_hit"), dict):
        item["interaction_hit"] = dict(payload["interaction_hit"])
    if target_size is not None:
        item["placement_surface_cm"] = list(target_size) if isinstance(target_size, (list, tuple)) else target_size
    if bool(target.get("allow_stacking", False)):
        siblings = [
            other for other in (item.get("_placement_state_nodes") or [])
            if isinstance(other, dict)
            and str(other.get("id") or "") != str(item.get("id") or "")
            and str(other.get("placement_target") or "") == str(target.get("id") or "")
        ]
        item["stack_index"] = 1 + max((int(other.get("stack_index") or 0) for other in siblings), default=0)
        if siblings:
            item["support_object_id"] = str(siblings[-1].get("id") or "")
        item.pop("_placement_state_nodes", None)


def surface_fit_failure(item: dict[str, Any], target: dict[str, Any], payload: dict[str, Any] | None = None) -> str | None:
    """Return a placement error when the item's footprint cannot fit."""
    surface = target.get("surface_size_cm") or target.get("support_surface_cm")
    if not isinstance(surface, (list, tuple)) or len(surface) < 2:
        return None
    footprint = item.get("footprint_cm") or item.get("size_cm")
    if not isinstance(footprint, (list, tuple)) or len(footprint) < 2:
        footprint = [item.get("width_cm", 10.0), item.get("depth_cm", 10.0)]
    surface_width = max(0.001, _number(surface[0], 0.0))
    surface_depth = max(0.001, _number(surface[1], 0.0))
    item_width = max(0.001, _number(footprint[0], 10.0))
    item_depth = max(0.001, _number(footprint[1], 10.0))
    if item_width > surface_width or item_depth > surface_depth:
        return f"item footprint {item_width:g}x{item_depth:g}cm exceeds surface {surface_width:g}x{surface_depth:g}cm"
    merged = {**(payload or {}), "surface_size_cm": (payload or {}).get("surface_size_cm") or surface}
    grid = _number(target.get("surface_grid_cm") or target.get("support_grid_cm") or 1.0, 1.0)
    anchor = normalized_surface_anchor(merged, grid_cm=grid)
    half_width = item_width / (2.0 * surface_width)
    half_depth = item_depth / (2.0 * surface_depth)
    if anchor[0] < half_width or anchor[0] > 1.0 - half_width or anchor[1] < half_depth or anchor[1] > 1.0 - half_depth:
        return f"item footprint does not fit at surface anchor {anchor}"
    return None


def _footprint(item: dict[str, Any]) -> tuple[float, float]:
    value = item.get("footprint_cm") or item.get("size_cm") or [item.get("width_cm", 10.0), item.get("depth_cm", 10.0)]
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return 10.0, 10.0
    return max(0.001, _number(value[0], 10.0)), max(0.001, _number(value[1], 10.0))


def surface_collision_failure(state: dict[str, Any], item: dict[str, Any], target: dict[str, Any], payload: dict[str, Any] | None = None) -> str | None:
    """Reject overlapping footprints already placed on the same target."""
    if bool(target.get("allow_stacking", False)):
        return None
    surface = target.get("surface_size_cm") or target.get("support_surface_cm")
    if not isinstance(surface, (list, tuple)) or len(surface) < 2:
        return None
    merged = {**(payload or {}), "surface_size_cm": (payload or {}).get("surface_size_cm") or surface}
    grid = _number(target.get("surface_grid_cm") or target.get("support_grid_cm") or 1.0, 1.0)
    anchor = normalized_surface_anchor(merged, grid_cm=grid)
    item_width, item_depth = _footprint(item)
    width, depth = max(0.001, _number(surface[0], 1.0)), max(0.001, _number(surface[1], 1.0))
    for other_id, other in (state.get("nodes") or {}).items():
        if not isinstance(other, dict) or str(other_id) == str(item.get("id") or ""):
            continue
        if str(other.get("parent") or "") != str(target.get("id") or ""):
            continue
        if str(other.get("placement_target") or "") != str(target.get("id") or ""):
            continue
        other_anchor = other.get("placement_anchor")
        if not isinstance(other_anchor, (list, tuple)) or len(other_anchor) < 2:
            continue
        other_width, other_depth = _footprint(other)
        if abs(anchor[0] - _number(other_anchor[0], 0.5)) < (item_width + other_width) / (2 * width) and abs(anchor[1] - _number(other_anchor[1], 0.5)) < (item_depth + other_depth) / (2 * depth):
            return f"item footprint overlaps {other_id} on target {target.get('id')}"
    return None


def surface_load_failure(state: dict[str, Any], item: dict[str, Any], target: dict[str, Any]) -> str | None:
    max_load = target.get("max_load_kg") or target.get("support_load_kg")
    if max_load in (None, ""):
        return None
    try:
        maximum = float(max_load)
    except (TypeError, ValueError):
        return None
    total = _number(item.get("mass_kg") or item.get("weight_kg"), 0.0)
    for other_id, other in (state.get("nodes") or {}).items():
        if str(other_id) == str(item.get("id") or "") or not isinstance(other, dict):
            continue
        if str(other.get("parent") or "") == str(target.get("id") or ""):
            total += _number(other.get("mass_kg") or other.get("weight_kg"), 0.0)
    return f"surface load {total:g}kg exceeds {maximum:g}kg" if total > maximum else None


def _dimensions(item: dict[str, Any]) -> tuple[float, float, float]:
    value = item.get("bounds_cm") or item.get("dimensions_cm") or item.get("size_cm")
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return tuple(max(0.001, _number(value[index], 10.0)) for index in range(3))  # type: ignore[return-value]
    width, depth = _footprint(item)
    return width, depth, max(0.001, _number(item.get("height_cm") or item.get("height"), 10.0))


def _interior_size(target: dict[str, Any]) -> tuple[float, float, float] | None:
    value = target.get("interior_size_cm") or target.get("container_size_cm") or target.get("placement_volume_cm")
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    return tuple(max(0.001, _number(value[index], 0.0)) for index in range(3))  # type: ignore[return-value]


def normalized_volume_anchor(payload: dict[str, Any] | None, *, grid_cm: float = 1.0) -> list[float]:
    """Return a clamped normalized [x, y, z] anchor inside a container."""
    payload = payload or {}
    hit = payload.get("interaction_hit")
    hit_anchor = (hit.get("volume_uv") or hit.get("volume_anchor") or hit.get("uv")) if isinstance(hit, dict) else None
    anchor = payload.get("placement_volume_anchor") or payload.get("volume_anchor") or hit_anchor
    if isinstance(anchor, dict):
        values = [_number(anchor.get(axis), 0.5) for axis in ("x", "y", "z")]
    elif isinstance(anchor, (list, tuple)) and len(anchor) >= 3:
        values = [_number(anchor[index], 0.5) for index in range(3)]
    else:
        point = payload.get("volume_point_cm") or payload.get("placement_point_cm")
        size = payload.get("interior_size_cm") or payload.get("container_size_cm")
        if isinstance(point, (list, tuple)) and isinstance(size, (list, tuple)) and len(point) >= 3 and len(size) >= 3:
            values = [_number(point[index], _number(size[index], 1.0) / 2) / max(0.001, _number(size[index], 1.0)) for index in range(3)]
        else:
            values = [0.5, 0.5, 0.5]
    step = max(0.0, _number(grid_cm, 0.0))
    size = _interior_size(payload)
    if step and size:
        values = [round(values[index] * size[index] / step) * step / size[index] for index in range(3)]
    return [max(0.0, min(1.0, round(value, 6))) for value in values]


def attach_volume_metadata(item: dict[str, Any], target: dict[str, Any], payload: dict[str, Any] | None = None) -> None:
    volume = _interior_size(target)
    if volume is None:
        return
    merged = {**(payload or {}), "interior_size_cm": (payload or {}).get("interior_size_cm") or list(volume)}
    item["placement_volume_anchor"] = normalized_volume_anchor(merged, grid_cm=_number(target.get("volume_grid_cm") or 1.0, 1.0))
    item["placement_volume_target"] = str(target.get("id") or "")
    item["placement_volume_cm"] = list(volume)
    if isinstance(payload, dict) and isinstance(payload.get("interaction_hit"), dict):
        item["interaction_hit"] = dict(payload["interaction_hit"])


def volume_fit_failure(item: dict[str, Any], target: dict[str, Any], payload: dict[str, Any] | None = None) -> str | None:
    volume = _interior_size(target)
    if volume is None:
        return None
    dimensions = _dimensions(item)
    if any(dimensions[index] > volume[index] for index in range(3)):
        return "item dimensions %.g x %.g x %.gcm exceed interior %.g x %.g x %.gcm" % (*dimensions, *volume)
    merged = {**(payload or {}), "interior_size_cm": (payload or {}).get("interior_size_cm") or list(volume)}
    anchor = normalized_volume_anchor(merged, grid_cm=_number(target.get("volume_grid_cm") or 1.0, 1.0))
    if any(anchor[index] < dimensions[index] / (2 * volume[index]) or anchor[index] > 1 - dimensions[index] / (2 * volume[index]) for index in range(3)):
        return f"item dimensions do not fit at interior anchor {anchor}"
    return None


def volume_collision_failure(state: dict[str, Any], item: dict[str, Any], target: dict[str, Any], payload: dict[str, Any] | None = None) -> str | None:
    volume = _interior_size(target)
    if volume is None or bool(target.get("allow_stacking", False)):
        return None
    merged = {**(payload or {}), "interior_size_cm": (payload or {}).get("interior_size_cm") or list(volume)}
    anchor = normalized_volume_anchor(merged, grid_cm=_number(target.get("volume_grid_cm") or 1.0, 1.0))
    dimensions = _dimensions(item)
    for other_id, other in (state.get("nodes") or {}).items():
        if not isinstance(other, dict) or str(other_id) == str(item.get("id") or ""):
            continue
        if str(other.get("parent") or "") != str(target.get("id") or "") or str(other.get("placement_volume_target") or "") != str(target.get("id") or ""):
            continue
        other_anchor = other.get("placement_volume_anchor")
        if not isinstance(other_anchor, (list, tuple)) or len(other_anchor) < 3:
            continue
        other_dimensions = _dimensions(other)
        if all(abs(anchor[index] - _number(other_anchor[index], 0.5)) < (dimensions[index] + other_dimensions[index]) / (2 * volume[index]) for index in range(3)):
            return f"item volume overlaps {other_id} in target {target.get('id')}"
    return None


def volume_load_failure(state: dict[str, Any], item: dict[str, Any], target: dict[str, Any]) -> str | None:
    """Reject an interior placement that exceeds the container load limit."""
    maximum_value = target.get("max_load_kg") or target.get("interior_load_kg")
    if maximum_value in (None, ""):
        return None
    try:
        maximum = float(maximum_value)
    except (TypeError, ValueError):
        return None
    total = _number(item.get("mass_kg") or item.get("weight_kg"), 0.0)
    target_id = str(target.get("id") or "")
    for other in (state.get("nodes") or {}).values():
        if not isinstance(other, dict) or str(other.get("parent") or "") != target_id:
            continue
        if str(other.get("placement_volume_target") or "") != target_id:
            continue
        total += _number(other.get("mass_kg") or other.get("weight_kg"), 0.0)
    return f"interior load {total:g}kg exceeds {maximum:g}kg" if total > maximum else None


def floor_collision_failure(
    state: dict[str, Any],
    item: dict[str, Any],
    room: dict[str, Any],
    payload: dict[str, Any] | None = None,
) -> str | None:
    """Reject a floor release whose footprint overlaps another released item.

    Release coordinates are normalized to the room floor, so this remains useful
    even when a room has no physical dimensions yet.  It intentionally covers
    discrete floor contacts only; continuous rigid-body simulation is a later
    layer.
    """
    if bool(room.get("allow_floor_stacking", False)):
        return None
    anchor = (payload or {}).get("release_anchor")
    if not isinstance(anchor, (list, tuple)) or len(anchor) < 3:
        anchor = item.get("release_anchor")
    if not isinstance(anchor, (list, tuple)) or len(anchor) < 3:
        return None
    item_width, item_depth = _footprint(item)
    floor_size = room.get("floor_size_cm") or room.get("dimensions_cm")
    width = _number(floor_size[0], 100.0) if isinstance(floor_size, (list, tuple)) and len(floor_size) >= 2 else 100.0
    depth = _number(floor_size[1], 100.0) if isinstance(floor_size, (list, tuple)) and len(floor_size) >= 2 else 100.0
    width = max(0.001, width)
    depth = max(0.001, depth)
    item_id = str(item.get("id") or "")
    room_id = str(room.get("id") or "")
    for other_id, other in (state.get("nodes") or {}).items():
        if not isinstance(other, dict) or str(other_id) == item_id:
            continue
        if str(other.get("release_room") or "") != room_id:
            continue
        other_anchor = other.get("release_anchor")
        if not isinstance(other_anchor, (list, tuple)) or len(other_anchor) < 3:
            continue
        other_width, other_depth = _footprint(other)
        if (
            abs(_number(anchor[0], 0.5) - _number(other_anchor[0], 0.5)) < (item_width + other_width) / (2 * width)
            and abs(_number(anchor[2], 0.5) - _number(other_anchor[2], 0.5)) < (item_depth + other_depth) / (2 * depth)
        ):
            return f"floor footprint overlaps {other_id} in room {room_id}"
    return None


__all__ = ["DEFAULT_FOOTPRINTS_CM", "DEFAULT_INTERIOR_SIZES_CM", "DEFAULT_SURFACE_SIZES_CM", "attach_surface_metadata", "attach_volume_metadata", "floor_collision_failure", "footprint_for", "interior_spec_for", "normalized_surface_anchor", "normalized_volume_anchor", "surface_collision_failure", "surface_fit_failure", "surface_load_failure", "surface_spec_for", "volume_collision_failure", "volume_fit_failure", "volume_load_failure"]
