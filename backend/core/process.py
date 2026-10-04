"""Generic time-bounded process protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(slots=True)
class Process:
    id: str
    owner_id: str
    status: str = "pending"
    started_at: float = 0.0
    duration: float = 0.0
    progress: float = 0.0
    consumed_resources: tuple[Mapping[str, Any], ...] = ()
    completion_effects: tuple[Mapping[str, Any], ...] = ()
    interruption_policy: Mapping[str, Any] = field(default_factory=dict)

    def advance(self, elapsed_seconds: float) -> bool:
        if self.status not in {"pending", "running"}:
            return self.status == "finished"
        self.status = "running"
        if self.duration <= 0:
            self.progress = 1.0
        else:
            self.progress = min(1.0, self.progress + max(0.0, float(elapsed_seconds)) / self.duration)
        if self.progress >= 1.0:
            self.progress = 1.0
            self.status = "finished"
        return self.status == "finished"

    def interrupt(self, reason: str = "") -> None:
        if self.status in {"finished", "interrupted"}:
            return
        self.status = "interrupted"
        if reason:
            self.interruption_policy = {**dict(self.interruption_policy), "reason": reason}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "status": self.status,
            "started_at": self.started_at,
            "duration": self.duration,
            "progress": self.progress,
            "consumed_resources": [dict(item) for item in self.consumed_resources],
            "completion_effects": [dict(item) for item in self.completion_effects],
            "interruption_policy": dict(self.interruption_policy),
        }


__all__ = ["Process"]
