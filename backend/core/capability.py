"""Capability definitions and the canonical capability registry.

Asset templates select names from this registry; they do not define a second
runtime capability system.
"""

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class Capability:
    """Composable capability card attached to a Node or Link."""

    name: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def accepts(self, value: Any) -> bool:
        accepted = self.parameters.get("accepted_values") if isinstance(self.parameters, Mapping) else None
        return not accepted or value in accepted


class CapabilitySet:
    def __init__(self, values: Iterable[Capability] = ()):
        self.values = {item.name: item for item in values}

    def has(self, name: str) -> bool:
        return str(name) in self.values

    def get(self, name: str) -> Capability | None:
        return self.values.get(str(name))

    def to_dict(self) -> dict[str, dict[str, Any]]:
        return {name: dict(card.parameters) for name, card in self.values.items()}


@dataclass(frozen=True)
class CapabilityDefinition:
    name: str
    commands: tuple[str, ...] = ()
    accepted_actions: tuple[str, ...] = ()
    states: tuple[str, ...] = ()
    systems: tuple[str, ...] = ()


CAPABILITY_REGISTRY: dict[str, CapabilityDefinition] = {
    "moveable": CapabilityDefinition("moveable", commands=("move", "rotate"), accepted_actions=("move", "rotate")),
    "pickable": CapabilityDefinition("pickable", commands=("pick", "release"), accepted_actions=("pick", "release")),
    "place_target": CapabilityDefinition("place_target", commands=("place", "remove"), accepted_actions=("place", "remove")),
    "openable": CapabilityDefinition("openable", commands=("open", "close"), accepted_actions=("open", "close"), states=("is_open",)),
    "switchable": CapabilityDefinition("switchable", commands=("turn_on", "turn_off", "toggle"), accepted_actions=("turn_on", "turn_off", "toggle"), states=("is_on",)),
    "process_device": CapabilityDefinition("process_device", commands=("start", "pause", "resume", "stop"), accepted_actions=("start", "pause", "resume", "stop"), states=("process_status",), systems=("time", "energy")),
    "liquid_container": CapabilityDefinition("liquid_container", commands=("pour", "receive", "drain"), accepted_actions=("pour", "receive", "drain"), states=("liquid_level",), systems=("liquid", "capacity")),
    "flushable": CapabilityDefinition("flushable", commands=("flush",), accepted_actions=("flush",)),
    "transport_device": CapabilityDefinition("transport_device", commands=("select_destination",), accepted_actions=("select_destination",), states=("process_status",), systems=("time",)),
    "resource_receiver": CapabilityDefinition("resource_receiver", commands=("load_resource",), accepted_actions=("place",), systems=("capacity",)),
    "trash_receiver": CapabilityDefinition("trash_receiver", commands=("discard",), accepted_actions=("place",), systems=("capacity",)),
    "cleanable": CapabilityDefinition("cleanable", commands=("clean",), accepted_actions=("clean",), states=("is_dirty",)),
    "foldable": CapabilityDefinition("foldable", commands=("fold", "unfold"), accepted_actions=("fold", "unfold"), states=("is_folded",)),
}


def capability(name: str) -> CapabilityDefinition:
    try:
        return CAPABILITY_REGISTRY[str(name).lower()]
    except KeyError as exc:
        raise KeyError(f"unknown capability: {name}") from exc


def capabilities(names: Iterable[str]) -> tuple[CapabilityDefinition, ...]:
    return tuple(capability(name) for name in names)

__all__ = ["Capability", "CapabilitySet", "CapabilityDefinition", "CAPABILITY_REGISTRY", "capability", "capabilities"]
