"""Declarative temporal state effects used by devices and natural processes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _template_property(item: dict[str, Any], key: str, default: Any = None) -> Any:
    try:
        from .assets.object_library import OBJECT_LIBRARY
        from .predicates import semantic

        template = OBJECT_LIBRARY.get(semantic(item))
        return template._property(key, default) if template else default
    except (ImportError, AttributeError):
        return default


@dataclass(frozen=True)
class StateEffect:
    capability: str
    state: str
    value: Any
    phase: str = "complete"
    delay_steps: int = 0

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "StateEffect":
        return cls(
            capability=str(value.get("capability") or ""),
            state=str(value.get("state") or ""),
            value=value.get("value"),
            phase=str(value.get("phase") or "complete"),
            delay_steps=max(0, int(value.get("delay_steps") or 0)),
        )


def temporal_effects(item: dict[str, Any], phase: str) -> tuple[StateEffect, ...]:
    profile = item.get("temporal_profile")
    if not isinstance(profile, dict):
        return ()
    raw = profile.get(f"on_{phase}") or []
    return tuple(StateEffect.from_dict(value) for value in raw if isinstance(value, dict))


def apply_effects(item: dict[str, Any], capabilities: set[str], effects: tuple[StateEffect, ...]) -> None:
    states = item.setdefault("states", {})
    for effect in effects:
        if effect.capability and effect.capability not in capabilities:
            continue
        states[effect.state] = effect.value


def profile_duration(item: dict[str, Any], *, contained: bool = False, default: int = 0) -> int:
    """Read a process duration from declarative capability metadata."""
    key = "contained_process_duration_steps" if contained else "process_duration_steps"
    try:
        return max(0, int(item.get(key) or _template_property(item, key, default) or default))
    except (TypeError, ValueError):
        return max(0, int(default))


def contained_profile(item: dict[str, Any]) -> dict[str, Any]:
    profile = item.get("contained_temporal_profile") or _template_property(item, "contained_temporal_profile", {})
    return profile if isinstance(profile, dict) else {}


def contextual_duration(profile: dict[str, Any], *, default: int, world: dict[str, Any], room_id: str = "") -> int:
    """Evaluate declarative world/room modifiers for a temporal profile."""
    config = profile.get("duration") if isinstance(profile.get("duration"), dict) else {}
    duration = max(1, int(config.get("default_steps") or default or 1))
    for world_key, mapping in (config.get("world_value_maps") or {}).items():
        if isinstance(mapping, dict):
            duration = int(mapping.get(str(world.get(world_key) or "").lower(), duration))
    for source, rules in (config.get("room_numeric_adjustments") or {}).items():
        values = world.get(source) or {}
        try:
            value = float(values.get(room_id, world.get(source.removeprefix("room_"), 0.0))) if isinstance(values, dict) else float(values)
        except (TypeError, ValueError):
            continue
        for rule in rules if isinstance(rules, list) else []:
            if not isinstance(rule, dict):
                continue
            if "gte" in rule and value >= float(rule["gte"]):
                duration += int(rule.get("delta") or 0)
            elif "lte" in rule and value <= float(rule["lte"]):
                duration += int(rule.get("delta") or 0)
    return max(1, duration)


__all__ = ["StateEffect", "temporal_effects", "apply_effects", "profile_duration", "contained_profile", "contextual_duration"]
