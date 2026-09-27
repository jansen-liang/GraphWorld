"""Flat domain records for GraphWorld.

The records deliberately avoid semantic subclasses. Object behavior comes
from template capabilities, state definitions, actions, rules, and systems.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping

from enum import Enum


POSITION_RELATIONS = frozenset({
    "at", "in", "inside", "inside_room", "contains", "on", "near", "held_by", "held_by_left",
    "held_by_right", "held_by_both", "worn_by", "belongs_to",
})


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


@dataclass(slots=True)
class Edge:
    source_id: str
    target_id: str
    relation: str
    properties: dict[str, Any] = field(default_factory=dict)
    category: str = "physical"
    id: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def is_position(self) -> bool:
        return self.relation in POSITION_RELATIONS

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Edge":
        known = {"id", "source_id", "target_id", "relation", "properties", "category", "edge_type"}
        relation = str(value.get("relation") or "").lower()
        category = str(value.get("category") or ("logical" if relation in {"controls", "linked_to", "powered_by"} else "physical"))
        attributes = {key: item for key, item in value.items() if key not in known}
        if value.get("edge_type"):
            attributes["edge_type"] = value["edge_type"]
        return cls(
            id=str(value.get("id") or ""),
            source_id=str(value.get("source_id") or ""),
            target_id=str(value.get("target_id") or ""),
            relation=relation,
            properties=deepcopy(dict(value.get("properties") or {})),
            category=category,
            attributes=deepcopy(attributes),
        )

    def to_dict(self) -> dict[str, Any]:
        value = deepcopy(self.attributes)
        value.update({
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation,
            "category": self.category,
            "properties": deepcopy(self.properties),
        })
        if self.id:
            value["id"] = self.id
        return value


class EdgeType(str, Enum):
    OBJECT_EDGE = "object_edge"
    OBJECT_ROOM_EDGE = "object_room_edge"
    ROOM_EDGE = "room_edge"
    ROOM_FLOOR_EDGE = "room_floor_edge"
    TRANSPORT_EDGE = "transport_edge"
    CONTROL_EDGE = "control_edge"


class EdgeCategory(str, Enum):
    PHYSICAL = "physical"
    LOGICAL = "logical"


class SpatialRelation(str, Enum):
    AT = "at"
    IN = "in"
    ON = "on"
    ONTOP = "ontop"
    INSIDE = "inside"
    UNDER = "under"
    BESIDE = "beside"
    NEXT_TO = "next_to"
    NEAR = "near"
    HELD_BY = "held_by"
    FAR = "far"
    NEIGHBOUR = "neighbour"
    CONTAINS = "contains"
    BELONGS_TO = "belongs_to"
    CONNECTED = "connected"
    HINGE_OF = "hinge_of"
    SLIDES_IN = "slides_in"
    TOUCHING = "touching"
    CONTROLS = "controls"
    LINKED_TO = "linked_to"
    POWERED_BY = "powered_by"


CANONICAL_POSITION_RELATIONS = tuple(sorted(POSITION_RELATIONS))
PARENT_RELATIONS = CANONICAL_POSITION_RELATIONS
ROOM_CONNECTIVITY_RELATIONS = (
    SpatialRelation.NEXT_TO.value,
    SpatialRelation.NEIGHBOUR.value,
    SpatialRelation.CONNECTED.value,
)


@dataclass(frozen=True)
class RelationSpec:
    relation: str
    source_roles: tuple[str, ...] = ()
    target_roles: tuple[str, ...] = ()
    positive_when: str = ""
    negative_when: str = ""
    changed_by: tuple[str, ...] = ()
    downstream_effects: tuple[str, ...] = ()
    score_weight: float = 1.0


RELATION_SPECS = {
    relation: RelationSpec(relation=relation)
    for relation in (
        SpatialRelation.AT.value, SpatialRelation.IN.value, SpatialRelation.ON.value,
        SpatialRelation.NEAR.value, SpatialRelation.HELD_BY.value,
        SpatialRelation.INSIDE.value, SpatialRelation.NEXT_TO.value,
        SpatialRelation.TOUCHING.value,
    )
}


def create_edge(source_id: str, target_id: str, relation: SpatialRelation | str, **kwargs: Any) -> Edge:
    relation_value = SpatialRelation(relation).value
    category = kwargs.pop("category", None)
    edge_type = kwargs.pop("edge_type", None)
    properties = dict(kwargs.pop("properties", {}) or {})
    properties.update(kwargs)
    logical = relation_value in {SpatialRelation.CONTROLS.value, SpatialRelation.LINKED_TO.value, SpatialRelation.POWERED_BY.value}
    attributes = {"edge_type": str(edge_type or (EdgeType.CONTROL_EDGE.value if logical else EdgeType.OBJECT_EDGE.value))}
    return Edge(
        source_id=str(source_id), target_id=str(target_id), relation=relation_value,
        category=str(category or (EdgeCategory.LOGICAL.value if logical else EdgeCategory.PHYSICAL.value)),
        properties=properties, attributes=attributes,
    )


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
    "CANONICAL_POSITION_RELATIONS", "CONTROL_OBJECT_TYPES", "Edge", "EdgeCategory", "EdgeType",
    "Node", "NodeType", "PARENT_RELATIONS", "POSITION_RELATIONS", "RELATION_SPECS",
    "ROOM_CONNECTIVITY_RELATIONS", "RelationSpec", "SpatialRelation", "create_edge", "make_node",
    "node_type_from_legacy",
]
