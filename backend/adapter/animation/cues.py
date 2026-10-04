"""Derived visual cues for UI/simulation renderers."""

from __future__ import annotations

from typing import Any


def visual_cues(item: dict[str, Any]) -> list[str]:
    states = item.get("states") or {}
    semantic = str(item.get("semantic_type") or "").lower()
    capabilities = {str(value).strip().lower() for value in item.get("capabilities") or ()}
    cues: list[str] = []

    # Assets may declare renderer-facing effects without teaching the runtime
    # about a new semantic object type.  Keep this deliberately flat: a cue is
    # a stable visual contract, while its implementation belongs to an adapter.
    declared = item.get("visual_effects") or item.get("visual_cues") or ()
    if isinstance(declared, str):
        declared = [declared]
    if isinstance(declared, (list, tuple, set)):
        cues.extend(str(value) for value in declared if str(value).strip())

    def add(cue: str) -> None:
        if cue not in cues:
            cues.append(cue)

    if str(item.get("physics_state") or "") == "falling":
        add("falling")
    if states.get("is_running"):
        add("running_pulse")
    if states.get("is_on") and ({"airflow", "rotating"} & capabilities):
        add("airflow")
    if states.get("is_on") and "emissive" in capabilities:
        add("emissive")
    if states.get("is_open"):
        add("open_pose")
    if states.get("is_wet"):
        add("water_droplets")
        if states.get("cycle_remaining") is not None:
            add("drying_bubbles")
    if str(states.get("temperature") or "").lower() == "hot":
        add("steam")
    if states.get("is_broken"):
        add("broken")

    # Compatibility for legacy scene records that predate declarative
    # capabilities/effects.  New assets should use the fields above.
    if states.get("is_on") and semantic in {"fan", "ceiling_fan", "ventilator"}:
        add("airflow")
    if states.get("is_on") and semantic in {"light", "room_light", "lamp"}:
        add("emissive")
    return cues


__all__ = ["visual_cues"]
