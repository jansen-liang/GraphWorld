"""Derived visual cues for UI/simulation renderers."""

from __future__ import annotations

from typing import Any


def visual_cues(item: dict[str, Any]) -> list[str]:
    states = item.get("states") or {}
    semantic = str(item.get("semantic_type") or "").lower()
    cues: list[str] = []
    if str(item.get("physics_state") or "") == "falling":
        cues.append("falling")
    if states.get("is_running"):
        cues.append("running_pulse")
    if semantic in {"fan", "ceiling_fan", "ventilator"} and states.get("is_on"):
        cues.append("airflow")
    if states.get("is_on") and semantic in {"light", "room_light", "lamp"}:
        cues.append("emissive")
    if states.get("is_open"):
        cues.append("open_pose")
    if states.get("is_wet"):
        cues.append("water_droplets")
        if states.get("cycle_remaining") is not None:
            cues.append("drying_bubbles")
    if str(states.get("temperature") or "").lower() == "hot":
        cues.append("steam")
    if states.get("is_broken"):
        cues.append("broken")
    return cues


__all__ = ["visual_cues"]
