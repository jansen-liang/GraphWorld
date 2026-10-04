"""Serializable, composable action preconditions.

Requirements only inspect a world context. They never mutate world state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol


class RequirementContext(Protocol):
    def node(self, node_id: str) -> Mapping[str, Any]: ...

    def has_edge(self, source_id: str, target_id: str, relation: str) -> bool: ...


class Requirement:
    code = "requirement_failed"

    def check(self, context: RequirementContext, bindings: Mapping[str, str]) -> str | None:
        raise NotImplementedError


@dataclass(frozen=True)
class CallbackRequirement(Requirement):
    """Named runtime predicate used while migrating legacy action schemas."""

    name: str
    callback: Callable[[Any], str | None] = field(compare=False, repr=False)

    def check(self, context: Any, bindings: Mapping[str, str]) -> str | None:
        return self.callback(context)

    def to_dict(self) -> dict[str, Any]:
        return {"type": "runtime_predicate", "name": self.name}

@dataclass(frozen=True)
class CapabilityRequirement(Requirement):
    subject: str
    capability: str
    code: str = "missing_capability"

    def check(self, context: RequirementContext, bindings: Mapping[str, str]) -> str | None:
        node = context.node(bindings[self.subject])
        if self.capability not in {str(item).lower() for item in node.get("capabilities", ())}:
            return f"{self.code}:{self.subject}:{self.capability}"
        return None

    def to_dict(self) -> dict[str, Any]:
        return {"type": "capability", "subject": self.subject, "capability": self.capability}


@dataclass(frozen=True)
class StateRequirement(Requirement):
    subject: str
    state: str
    expected: Any
    code: str = "state_mismatch"

    def check(self, context: RequirementContext, bindings: Mapping[str, str]) -> str | None:
        actual = (context.node(bindings[self.subject]).get("states") or {}).get(self.state)
        if actual != self.expected:
            return f"{self.code}:{self.subject}:{self.state}:{actual!r}!={self.expected!r}"
        return None

    def to_dict(self) -> dict[str, Any]:
        return {"type": "state", "subject": self.subject, "state": self.state, "expected": self.expected}


@dataclass(frozen=True)
class EdgeRequirement(Requirement):
    source: str
    target: str
    relation: str
    present: bool = True
    code: str = "edge_mismatch"

    def check(self, context: RequirementContext, bindings: Mapping[str, str]) -> str | None:
        actual = context.has_edge(bindings[self.source], bindings[self.target], self.relation)
        if actual != self.present:
            return f"{self.code}:{self.relation}"
        return None

    def to_dict(self) -> dict[str, Any]:
        return {"type": "edge", "source": self.source, "target": self.target, "relation": self.relation, "present": self.present}


@dataclass(frozen=True)
class AllOf(Requirement):
    requirements: tuple[Requirement, ...]

    def check(self, context: RequirementContext, bindings: Mapping[str, str]) -> str | None:
        for requirement in self.requirements:
            failure = requirement.check(context, bindings)
            if failure:
                return failure
        return None

    def to_dict(self) -> dict[str, Any]:
        return {"type": "all", "requirements": [item.to_dict() for item in self.requirements]}


@dataclass(frozen=True)
class AnyOf(Requirement):
    requirements: tuple[Requirement, ...]

    def check(self, context: RequirementContext, bindings: Mapping[str, str]) -> str | None:
        failures = [item.check(context, bindings) for item in self.requirements]
        if any(failure is None for failure in failures):
            return None
        return "any_of_failed:" + "|".join(item for item in failures if item)

    def to_dict(self) -> dict[str, Any]:
        return {"type": "any", "requirements": [item.to_dict() for item in self.requirements]}


@dataclass(frozen=True)
class Not(Requirement):
    requirement: Requirement

    def check(self, context: RequirementContext, bindings: Mapping[str, str]) -> str | None:
        return None if self.requirement.check(context, bindings) else "not_requirement_failed"

    def to_dict(self) -> dict[str, Any]:
        return {"type": "not", "requirement": self.requirement.to_dict()}


__all__ = ["AllOf", "AnyOf", "CallbackRequirement", "CapabilityRequirement", "EdgeRequirement", "Not", "Requirement", "StateRequirement"]
