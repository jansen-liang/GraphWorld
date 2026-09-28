"""Canonical relationship records and relation definitions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


POSITION_RELATIONS = frozenset({
    "at", "in", "inside", "inside_room", "contains", "on", "near", "held_by", "held_by_left",
    "held_by_right", "held_by_both", "worn_by", "belongs_to",
})


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


__all__ = [
    "CANONICAL_POSITION_RELATIONS", "Edge", "EdgeCategory", "EdgeType", "PARENT_RELATIONS",
    "POSITION_RELATIONS", "RELATION_SPECS", "ROOM_CONNECTIVITY_RELATIONS", "RelationSpec",
    "SpatialRelation", "create_edge",
]
