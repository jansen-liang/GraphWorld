"""Canonical entity records for GraphWorld.

The records deliberately avoid semantic subclasses. Object behavior comes
from template capabilities, state definitions, actions, rules, and systems.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping

from enum import Enum


class NodeType(str, Enum):
    FLOOR = "floor"
    ROOM = "room"
    FIXED_OBJECT = "fixed_object"
    MOVABLE_OBJECT = "movable_object"
    CONTROL_OBJECT = "control_object"
    ROBOT = "robot"
    HUMAN = "human"


CONTROL_OBJECT_TYPES = frozenset({"button", "door"})


@dataclass(slots=True)
class Node:
    id: str
    node_type: str
    semantic_type: str = ""
    name: str = ""
    name_cn: str = ""
    template_id: str = ""
    states: dict[str, Any] = field(default_factory=dict)
    capabilities: tuple[str, ...] = ()
    geometry: dict[str, Any] = field(default_factory=dict)
    structure: dict[str, Any] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Node":
        known = {
            "id", "node_type", "semantic_type", "name", "name_cn",
            "template_id", "states", "capabilities", "geometry", "structure",
            # Legacy relationship fields are consumed by the scene adapter.
            "parent", "runtime_relation", "inventory", "floor_id",
        }
        return cls(
            id=str(value.get("id") or ""),
            node_type=str(value.get("node_type") or "fixed_object"),
            semantic_type=str(value.get("semantic_type") or value.get("object_type") or ""),
            name=str(value.get("name") or value.get("id") or ""),
            name_cn=str(value.get("name_cn") or ""),
            template_id=str(value.get("template_id") or ""),
            states=deepcopy(dict(value.get("states") or {})),
            capabilities=tuple(str(item) for item in value.get("capabilities") or ()),
            geometry=deepcopy(dict(value.get("geometry") or {})),
            structure=deepcopy(dict(value.get("structure") or {})),
            attributes=deepcopy({key: item for key, item in value.items() if key not in known}),
        )

    def to_dict(self) -> dict[str, Any]:
        value = deepcopy(self.attributes)
        value.update({
            "id": self.id,
            "node_type": self.node_type,
            "semantic_type": self.semantic_type,
            "name": self.name or self.id,
            "states": deepcopy(self.states),
        })
        if self.name_cn:
            value["name_cn"] = self.name_cn
        if self.template_id:
            value["template_id"] = self.template_id
        if self.capabilities:
            value["capabilities"] = list(self.capabilities)
        if self.geometry:
            value["geometry"] = deepcopy(self.geometry)
        if self.structure:
            value["structure"] = deepcopy(self.structure)
        return value


def make_node(node_id: str, node_type: NodeType | str, *, semantic_type: str = "", name: str = "", name_cn: str = "", states: dict[str, Any] | None = None, capabilities: tuple[str, ...] | list[str] = (), **attributes: Any) -> dict[str, Any]:
    normalized_type = NodeType(node_type)
    return Node(
        id=str(node_id), node_type=normalized_type.value,
        semantic_type=str(semantic_type or normalized_type.value),
        name=str(name or node_id), name_cn=str(name_cn), states=dict(states or {}),
        capabilities=tuple(str(item) for item in capabilities), attributes=dict(attributes),
    ).to_dict()


def node_type_from_legacy(value: str) -> NodeType:
    normalized = str(value or "").strip().lower()
    aliases = {"space": NodeType.ROOM, "movable": NodeType.MOVABLE_OBJECT, "control": NodeType.CONTROL_OBJECT, "agent": NodeType.HUMAN}
    if normalized in aliases:
        return aliases[normalized]
    try:
        return NodeType(normalized)
    except ValueError:
        return NodeType.FIXED_OBJECT


__all__ = [
    "CONTROL_OBJECT_TYPES", "Node", "NodeType", "make_node", "node_type_from_legacy",
]
