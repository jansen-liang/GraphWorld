"""Generic event and time rule declarations owned by the domain core."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .effect import Effect
from .requirement import Requirement


@dataclass(frozen=True, slots=True)
class Rule:
    """Declarative rule; matching and mutation are executed by runtime."""

    id: str
    trigger: str
    conditions: tuple[Requirement, ...] = ()
    effects: tuple[Effect, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def matches(self, context: Any, bindings: Mapping[str, str]) -> bool:
        return all(condition.check(context, bindings) is None for condition in self.conditions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "trigger": self.trigger,
            "conditions": [condition.to_dict() for condition in self.conditions],
            "effects": [effect.to_dict() for effect in self.effects],
            "metadata": dict(self.metadata),
        }


__all__ = ["Rule"]
