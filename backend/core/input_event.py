"""Transport-neutral input events from clients to adapters/runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


EVENT_TYPES = frozenset({"key", "pointer_interact", "movement", "physics"})
PHASES = frozenset({"pressed", "released", "sampled", "completed"})


@dataclass(frozen=True, slots=True)
class InputEvent:
    event_id: str
    session_id: str
    actor_id: str
    sequence: int
    timestamp: float
    event_type: str
    phase: str
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.event_type not in EVENT_TYPES:
            raise ValueError(f"unsupported input event type: {self.event_type}")
        if self.phase not in PHASES:
            raise ValueError(f"unsupported input phase: {self.phase}")
        if self.sequence < 0:
            raise ValueError("input sequence must be non-negative")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "InputEvent":
        return cls(
            event_id=str(value["event_id"]),
            session_id=str(value.get("session_id") or ""),
            actor_id=str(value.get("actor_id") or ""),
            sequence=int(value.get("sequence") or 0),
            timestamp=float(value.get("timestamp") or 0.0),
            event_type=str(value.get("event_type") or "key"),
            phase=str(value.get("phase") or "pressed"),
            payload=dict(value.get("payload") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "actor_id": self.actor_id,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "phase": self.phase,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True, slots=True)
class InteractEvent:
    """Semantic interaction intent created after a client ray hit."""

    actor_id: str
    hand: str = "right"
    target_node_id: str | None = None
    target_link_id: str | None = None
    hit_point: tuple[float, float, float] | None = None
    hit_normal: tuple[float, float, float] | None = None
    input: str = "interact"
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "actor_id": self.actor_id,
            "hand": self.hand,
            "target_node_id": self.target_node_id,
            "target_link_id": self.target_link_id,
            "hit_point": list(self.hit_point) if self.hit_point is not None else None,
            "hit_normal": list(self.hit_normal) if self.hit_normal is not None else None,
            "input": self.input,
        }
        value.update(dict(self.parameters))
        return {key: item for key, item in value.items() if item is not None}


__all__ = ["EVENT_TYPES", "PHASES", "InputEvent", "InteractEvent"]
