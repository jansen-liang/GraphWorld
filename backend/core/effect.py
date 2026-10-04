"""Declarative world effects. Effects are applied by runtime transactions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol


class EffectContext(Protocol):
    def set_state(self, node_id: str, state: str, value: Any) -> None: ...

    def add_edge(self, source_id: str, target_id: str, relation: str, properties: Mapping[str, Any] | None = None) -> None: ...

    def remove_edge(self, source_id: str, target_id: str, relation: str) -> None: ...

    def emit(self, event: Mapping[str, Any]) -> None: ...


class Effect:
    def apply(self, context: EffectContext, bindings: Mapping[str, str]) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class CallbackEffect(Effect):
    """Named runtime effect used while migrating legacy action schemas."""

    name: str
    callback: Callable[[Any], None] = field(compare=False, repr=False)

    def apply(self, context: Any, bindings: Mapping[str, str]) -> None:
        self.callback(context)

    def to_dict(self) -> dict[str, Any]:
        return {"type": "runtime_effect", "name": self.name}

@dataclass(frozen=True)
class StateEffect(Effect):
    subject: str
    state: str
    value: Any

    def apply(self, context: EffectContext, bindings: Mapping[str, str]) -> None:
        context.set_state(bindings[self.subject], self.state, self.value)

    def to_dict(self) -> dict[str, Any]:
        return {"type": "state", "subject": self.subject, "state": self.state, "value": self.value}


@dataclass(frozen=True)
class EdgeEffect(Effect):
    operation: str
    source: str
    target: str
    relation: str
    properties: Mapping[str, Any] = None

    def apply(self, context: EffectContext, bindings: Mapping[str, str]) -> None:
        source, target = bindings[self.source], bindings[self.target]
        if self.operation == "add":
            context.add_edge(source, target, self.relation, self.properties)
        elif self.operation == "remove":
            context.remove_edge(source, target, self.relation)
        else:
            raise ValueError(f"unsupported edge effect operation: {self.operation}")

    def to_dict(self) -> dict[str, Any]:
        return {"type": "edge", "operation": self.operation, "source": self.source, "target": self.target, "relation": self.relation, "properties": dict(self.properties or {})}


@dataclass(frozen=True)
class EventEffect(Effect):
    event_type: str
    payload: Mapping[str, Any] = None

    def apply(self, context: EffectContext, bindings: Mapping[str, str]) -> None:
        event = dict(self.payload or {})
        event["type"] = self.event_type
        context.emit(event)

    def to_dict(self) -> dict[str, Any]:
        return {"type": "event", "event_type": self.event_type, "payload": dict(self.payload or {})}


@dataclass(frozen=True)
class NodeEffect(Effect):
    operation: str
    subject: str

    def apply(self, context: EffectContext, bindings: Mapping[str, str]) -> None:
        raise NotImplementedError("Node creation/removal is owned by WorldTransaction")

    def to_dict(self) -> dict[str, Any]:
        return {"type": "node", "operation": self.operation, "subject": self.subject}


__all__ = ["CallbackEffect", "EdgeEffect", "Effect", "EventEffect", "NodeEffect", "StateEffect"]
