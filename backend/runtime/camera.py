"""Deterministic first-person camera contract for runtime observations.

This module deliberately describes the camera frame, not a renderer-specific
raycast result.  A client may use the frame to raycast against its own mesh,
while the server continues to validate the submitted surface/volume anchor.
"""

from __future__ import annotations

from typing import Any

from backend.runtime.scene_utils import node, room_of


DEFAULT_CAMERA = {
    "eye_height_m": 1.6,
    "fov_deg": 75.0,
    "near_m": 0.05,
    "far_m": 50.0,
    "forward": [0.0, 0.0, 1.0],
    "up": [0.0, 1.0, 0.0],
    "viewport_uv": [0.5, 0.5],
}


def _number(value: Any, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number > 0 else fallback


def _vector(value: Any, fallback: list[float]) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return list(fallback)
    try:
        vector = [float(component) for component in value]
    except (TypeError, ValueError):
        return list(fallback)
    if sum(component * component for component in vector) <= 1e-9:
        return list(fallback)
    return vector


def camera_spec_for_agent(scene: dict[str, Any], agent_id: str) -> dict[str, Any]:
    """Return a serializable, renderer-independent first-person camera frame."""
    actor = node(scene, agent_id) or {}
    declared = actor.get("camera") if isinstance(actor.get("camera"), dict) else {}
    room_id = room_of(scene, agent_id)
    spec = {**DEFAULT_CAMERA, **declared}
    spec["eye_height_m"] = _number(spec.get("eye_height_m"), DEFAULT_CAMERA["eye_height_m"])
    spec["fov_deg"] = _number(spec.get("fov_deg"), DEFAULT_CAMERA["fov_deg"])
    spec["near_m"] = _number(spec.get("near_m"), DEFAULT_CAMERA["near_m"])
    spec["far_m"] = _number(spec.get("far_m"), DEFAULT_CAMERA["far_m"])
    spec["forward"] = _vector(spec.get("forward"), DEFAULT_CAMERA["forward"])
    spec["up"] = _vector(spec.get("up"), DEFAULT_CAMERA["up"])
    viewport = spec.get("viewport_uv")
    if not isinstance(viewport, (list, tuple)) or len(viewport) != 2:
        viewport = DEFAULT_CAMERA["viewport_uv"]
    try:
        spec["viewport_uv"] = [min(1.0, max(0.0, float(value))) for value in viewport]
    except (TypeError, ValueError):
        spec["viewport_uv"] = list(DEFAULT_CAMERA["viewport_uv"])
    spec["agent_id"] = str(agent_id)
    spec["room_id"] = room_id
    # Keep vectors and the center ray explicit so clients never infer a
    # different handedness or click origin from absent fields.
    spec["origin"] = [0.0, float(spec["eye_height_m"]), 0.0]
    spec["interaction_ray"] = {
        "screen_uv": list(spec["viewport_uv"]),
        "origin": list(spec["origin"]),
        "direction": list(spec["forward"]),
        "space": "agent_local",
    }
    spec["contract_version"] = 1
    return spec


def validate_interaction_hit(
    hit: Any,
    *,
    target_id: str,
    visible_node_ids: set[str] | None = None,
) -> tuple[str, ...]:
    """Validate renderer hit metadata without trusting client geometry."""
    if not isinstance(hit, dict):
        return ("interaction_hit must be an object",)
    node_id = str(hit.get("node_id") or hit.get("target_id") or "")
    if node_id != str(target_id):
        return (f"interaction hit node does not match target: {node_id or '<empty>'}",)
    if visible_node_ids is not None and node_id not in visible_node_ids:
        return (f"interaction hit node is not visible: {node_id}",)
    uv = hit.get("surface_uv") or hit.get("volume_uv") or hit.get("uv")
    if uv is not None:
        if not isinstance(uv, (list, tuple)) or len(uv) < 2:
            return ("interaction_hit surface coordinates must contain at least two values",)
        try:
            if any(float(value) < 0.0 or float(value) > 1.0 for value in uv[:2]):
                return ("interaction_hit surface coordinates must be normalized to [0, 1]",)
        except (TypeError, ValueError):
            return ("interaction_hit surface coordinates must be numeric",)
    for key in ("point_cm", "normal", "ray_origin", "ray_direction"):
        value = hit.get(key)
        if value is None:
            continue
        if not isinstance(value, (list, tuple)) or len(value) < 3:
            return (f"interaction_hit.{key} must contain three values",)
        try:
            [float(component) for component in value[:3]]
        except (TypeError, ValueError):
            return (f"interaction_hit.{key} must be numeric",)
    if "distance_m" in hit:
        try:
            distance = float(hit["distance_m"])
        except (TypeError, ValueError):
            return ("interaction_hit.distance_m must be numeric",)
        if distance < 0.0:
            return ("interaction_hit.distance_m must be non-negative",)
    if uv is None and hit.get("point_cm") is None:
        return ("interaction_hit requires surface_uv or point_cm",)
    return ()


__all__ = ["DEFAULT_CAMERA", "camera_spec_for_agent", "validate_interaction_hit"]
