"""Surface placement metadata and deterministic snapping helpers."""

from __future__ import annotations

from typing import Any

from backend.core.transform import IDENTITY_TRANSFORM, Transform


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
    spec = target.get("surface_spec") if isinstance(target.get("surface_spec"), dict) else {}
    target_dimensions = _target_dimensions(target)
    target_size = [spec.get("width_cm"), spec.get("depth_cm")]
    if not all(isinstance(value, (int, float)) and float(value) > 0 for value in target_size):
        target_size = [target_dimensions[0], target_dimensions[1]]
    grid_cm = spec.get("grid_size_cm") or 1.0
    item["placement_anchor"] = normalized_surface_anchor(
        {**(payload or {}), "surface_size_cm": target_size},
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
    spec = target.get("surface_spec") if isinstance(target.get("surface_spec"), dict) else {}
    surface = [spec.get("width_cm"), spec.get("depth_cm")]
    if any(value is None for value in surface):
        return None
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
    grid = _number(spec.get("grid_size_cm") or 1.0, 1.0)
    anchor = normalized_surface_anchor(merged, grid_cm=grid)
    half_width = item_width / (2.0 * surface_width)
    half_depth = item_depth / (2.0 * surface_depth)
    # Anchors are serialized to six decimal places after grid snapping. A
    # legal edge anchor such as 59/60 becomes 0.983333, while the exact
    # footprint boundary is 0.983333333... . Treat that serialization error
    # as equality; do not reject an item that exactly touches the edge.
    epsilon = 1e-6
    if anchor[0] < half_width - epsilon or anchor[0] > 1.0 - half_width + epsilon or anchor[1] < half_depth - epsilon or anchor[1] > 1.0 - half_depth + epsilon:
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
    spec = target.get("surface_spec") if isinstance(target.get("surface_spec"), dict) else {}
    surface = [spec.get("width_cm"), spec.get("depth_cm")]
    if any(value is None for value in surface):
        return None
    if not isinstance(surface, (list, tuple)) or len(surface) < 2:
        return None
    merged = {**(payload or {}), "surface_size_cm": (payload or {}).get("surface_size_cm") or surface}
    grid = _number(spec.get("grid_size_cm") or 1.0, 1.0)
    anchor = normalized_surface_anchor(merged, grid_cm=grid)
    item_width, item_depth = _footprint(item)
    width, depth = max(0.001, _number(surface[0], 1.0)), max(0.001, _number(surface[1], 1.0))
    for other_id, other in (state.get("nodes") or {}).items():
        if not isinstance(other, dict) or str(other_id) == str(item.get("id") or ""):
            continue
        if str((state.get("parent_of") or {}).get(str(other_id)) or "") != str(target.get("id") or ""):
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
        if str((state.get("parent_of") or {}).get(str(other_id)) or "") == str(target.get("id") or ""):
            total += _number(other.get("mass_kg") or other.get("weight_kg"), 0.0)
    return f"surface load {total:g}kg exceeds {maximum:g}kg" if total > maximum else None


def _dimensions(item: dict[str, Any]) -> tuple[float, float, float]:
    value = item.get("bounds_cm") or item.get("dimensions_cm") or item.get("size_cm")
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return tuple(max(0.001, _number(value[index], 10.0)) for index in range(3))  # type: ignore[return-value]
    width, depth = _footprint(item)
    return width, depth, max(0.001, _number(item.get("height_cm") or item.get("height"), 10.0))


def _target_dimensions(target: dict[str, Any]) -> tuple[float, float, float]:
    """Return target dimensions in centimetres, using the authored asset size."""
    value = target.get("bounds_cm") or target.get("dimensions_cm") or target.get("size_cm")
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return tuple(max(0.001, _number(value[index], 0.0)) for index in range(3))  # type: ignore[return-value]
    spec = target.get("surface_spec") if isinstance(target.get("surface_spec"), dict) else {}
    surface = (spec.get("width_cm"), spec.get("depth_cm")) or (10.0, 10.0)
    width = _number(surface[0], 10.0) if isinstance(surface, (list, tuple)) and surface else 10.0
    depth = _number(surface[1], 10.0) if isinstance(surface, (list, tuple)) and len(surface) > 1 else 10.0
    return max(0.001, width), max(0.001, depth), max(0.001, _number(target.get("height_cm"), 10.0))


def _world_transform(target: dict[str, Any]) -> Transform:
    value = target.get("world_transform") or target.get("transform")
    return Transform.from_dict(value) if isinstance(value, dict) else IDENTITY_TRANSFORM


def solve_placement_transform(
    item: dict[str, Any],
    target: dict[str, Any],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate the deterministic transform produced by a place action.

    Surface placement is expressed in the target's local frame.  The target
    root is treated as a centred asset, so the support plane is its +Z face;
    the item's bottom face is placed on that plane.  A containing link has a
    semantic interior anchor instead: contents are hidden and attached to the
    link's local origin, avoiding invented world geometry for opaque storage.
    """
    payload = payload or {}
    # A room target represents its floor.  The renderer sends the ray hit in
    # its Three.js basis (x, height, depth); convert it to the protocol's
    # right-handed Z-up basis and place the held object's bottom on z=0.
    # This keeps floor placement tied to the exact previewed hit instead of
    # falling back to the room/node origin.
    if str(target.get("node_type") or "").lower() == "room":
        hit = payload.get("interaction_hit")
        point = hit.get("point_cm") if isinstance(hit, dict) else None
        item_width, item_depth, item_height = _dimensions(item)
        if isinstance(point, (list, tuple)) and len(point) >= 3:
            try:
                x = float(point[0]) / 100.0
                y = -float(point[2]) / 100.0
                z = item_height / 200.0
                local = Transform(position=(round(x, 6), round(y, 6), round(z, 6)))
                return {
                    "relation": "on",
                    "local_transform": local.to_dict(),
                    "world_transform": local.to_dict(),
                    "storage_mode": "visible",
                    "support_surface": {
                        "target_id": str(target.get("id") or ""),
                        "anchor": [round(x, 6), round(y, 6)],
                        "size_cm": None,
                        "grid_cm": 1.0,
                    },
                }
            except (TypeError, ValueError):
                pass
    relation = "inside" if (_interior_size(target) is not None or bool(target.get("can_contain"))) else "on"
    item_width, item_depth, item_height = _dimensions(item)
    if relation == "inside":
        local = Transform(position=(0.0, 0.0, 0.0))
        return {
            "relation": relation,
            "local_transform": local.to_dict(),
            "world_transform": _world_transform(target).compose(local).to_dict(),
            "storage_mode": "hidden",
            "support_surface": None,
        }

    spec = target.get("surface_spec") if isinstance(target.get("surface_spec"), dict) else {}
    surface = [spec.get("width_cm"), spec.get("depth_cm")]
    if not all(isinstance(value, (int, float)) and float(value) > 0 for value in surface):
        surface = list(_target_dimensions(target)[:2])
    width = max(0.001, _number(surface[0], 10.0))
    depth = max(0.001, _number(surface[1], 10.0))
    grid = _number(spec.get("grid_size_cm") or 1.0, 1.0)
    anchor = normalized_surface_anchor({**payload, "surface_size_cm": [width, depth]}, grid_cm=grid)
    target_width, target_depth, target_height = _target_dimensions(target)
    # Keep the object footprint within the plane.  This is also enforced by
    # surface_fit_failure; clamping here makes the transform safe for direct
    # callers and preview code.
    half_u = item_width / (2.0 * width)
    half_v = item_depth / (2.0 * depth)
    u = max(half_u, min(1.0 - half_u, anchor[0]))
    v = max(half_v, min(1.0 - half_v, anchor[1]))
    local_position = tuple(round(value, 6) for value in (
        (u - 0.5) * width / 100.0,
        (v - 0.5) * depth / 100.0,
        target_height / 200.0 + item_height / 200.0,
    ))
    local = Transform(position=local_position)
    return {
        "relation": relation,
        "local_transform": local.to_dict(),
        "world_transform": _world_transform(target).compose(local).to_dict(),
        "storage_mode": "visible",
        "support_surface": {
            "target_id": str(target.get("id") or ""),
            "anchor": [round(u, 6), round(v, 6)],
            "size_cm": [width, depth],
            "grid_cm": grid,
        },
    }


def _interior_size(target: dict[str, Any]) -> tuple[float, float, float] | None:
    spec = target.get("interior_spec") if isinstance(target.get("interior_spec"), dict) else {}
    value = target.get("interior_size_cm")
    if value is None and all(spec.get(key) is not None for key in ("width_cm", "depth_cm", "height_cm")):
        value = (spec["width_cm"], spec["depth_cm"], spec["height_cm"])
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


def _is_storage_slot(target: dict[str, Any]) -> bool:
    # Older materialized scenes may omit component_role while retaining the
    # canonical semantic type or containment contract.
    return (
        str(target.get("component_role") or "").lower() == "storage_slot"
        or str(target.get("semantic_type") or "").lower() == "storage_slot"
        or bool(target.get("can_contain"))
    )


def attach_volume_metadata(item: dict[str, Any], target: dict[str, Any], payload: dict[str, Any] | None = None) -> None:
    volume = _interior_size(target)
    if volume is None:
        return
    merged = {**(payload or {}), "interior_size_cm": (payload or {}).get("interior_size_cm") or list(volume)}
    # A storage slot is represented by a placement surface whose contents
    # mount at its origin. The ray hit may be on an edge of the visible plane,
    # but that edge is not a semantic interior anchor and must not reject an
    # otherwise fitting item.
    # This metadata is the normalized validation anchor. The actual mounted
    # transform remains the slot origin and is computed separately.
    item["placement_volume_anchor"] = [0.5, 0.5, 0.5] if _is_storage_slot(target) else normalized_volume_anchor(merged, grid_cm=_number(target.get("volume_grid_cm") or 1.0, 1.0))
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
    anchor = [0.5, 0.5, 0.5] if _is_storage_slot(target) else normalized_volume_anchor(merged, grid_cm=_number(target.get("volume_grid_cm") or 1.0, 1.0))
    if any(anchor[index] < dimensions[index] / (2 * volume[index]) or anchor[index] > 1 - dimensions[index] / (2 * volume[index]) for index in range(3)):
        return f"item dimensions do not fit at interior anchor {anchor}"
    return None


def volume_collision_failure(state: dict[str, Any], item: dict[str, Any], target: dict[str, Any], payload: dict[str, Any] | None = None) -> str | None:
    volume = _interior_size(target)
    if volume is None or bool(target.get("allow_stacking", False)):
        return None
    merged = {**(payload or {}), "interior_size_cm": (payload or {}).get("interior_size_cm") or list(volume)}
    anchor = [0.5, 0.5, 0.5] if _is_storage_slot(target) else normalized_volume_anchor(merged, grid_cm=_number(target.get("volume_grid_cm") or 1.0, 1.0))
    dimensions = _dimensions(item)
    for other_id, other in (state.get("nodes") or {}).items():
        if not isinstance(other, dict) or str(other_id) == str(item.get("id") or ""):
            continue
        if str((state.get("parent_of") or {}).get(str(other_id)) or "") != str(target.get("id") or "") or str(other.get("placement_volume_target") or "") != str(target.get("id") or ""):
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
    for other_id, other in (state.get("nodes") or {}).items():
        if not isinstance(other, dict) or str((state.get("parent_of") or {}).get(str(other_id)) or "") != target_id:
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


__all__ = ["attach_surface_metadata", "attach_volume_metadata", "floor_collision_failure", "normalized_surface_anchor", "normalized_volume_anchor", "surface_collision_failure", "surface_fit_failure", "surface_load_failure", "volume_collision_failure", "volume_fit_failure", "volume_load_failure"]
