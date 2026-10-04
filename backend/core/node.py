from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from enum import Enum
from copy import deepcopy
from typing import Any, ClassVar
from .transform import Transform


@dataclass(frozen=True, slots=True)
class ShapeSpec:
    kind: str = "rectangle"
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SizeSpec:
    dimensions: tuple[float, ...] = ()
    unit: str = "m"


@dataclass(slots=True)
class Node(ABC):
    id: str
    role: str = "root"
    editor_id: str = ""
    runtime_id: str = ""
    semantic_type: str = ""
    template_id: str = ""
    name: str = ""
    name_cn: str = ""
    capabilities: tuple[str, ...] = ()
    states: dict[str, Any] = field(default_factory=dict)
    geometry: dict[str, Any] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)

    NODE_TYPE: ClassVar[NodeType]

    @property
    def node_type(self) -> NodeType:
        return self.NODE_TYPE

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Node":
        """Build the appropriate broad node class from a serialized record."""
        raw_type = value.get("node_type") or NodeType.OBJECT.value
        node_type = NodeType(str(raw_type).strip().lower())
        node_class = {
            NodeType.FLOOR: Floor,
            NodeType.ROOM: Room,
            NodeType.OBJECT: Object,
            NodeType.AGENT: Agent,
        }[node_type]
        known = {
            "id",
            "role",
            "editor_id",
            "runtime_id",
            "node_type",
            "semantic_type",
            "template_id",
            "name",
            "name_cn",
            "capabilities",
            "states",
            "geometry",
            "attributes",
            # Legacy aliases are intentionally ignored by the core model;
            # scene import performs their one-time migration at the boundary.
            "object_type", "surface_size_cm", "support_surface_cm",
            "surface_grid_cm", "support_grid_cm", "max_capacity",
            "capacity_per_slot", "requires_contained_capabilities",
            "accepted_semantic_types", "accepts", "capacity_cm3",
        }
        attributes = dict(value.get("attributes") or {})
        attributes.update({key: item for key, item in value.items() if key not in known})
        return node_class(
            id=str(value.get("runtime_id") or value.get("editor_id") or value.get("id") or ""),
            role=str(value.get("role") or "root"),
            editor_id=str(value.get("editor_id") or value.get("id") or ""),
            runtime_id=str(value.get("runtime_id") or ""),
            semantic_type=str(value.get("semantic_type") or ""),
            template_id=str(value.get("template_id") or ""),
            name=str(value.get("name") or value.get("id") or ""),
            name_cn=str(value.get("name_cn") or ""),
            capabilities=tuple(dict.fromkeys(str(item) for item in value.get("capabilities") or ())),
            states=deepcopy(dict(value.get("states") or {})),
            geometry=deepcopy(dict(value.get("geometry") or {})),
            attributes=deepcopy(attributes),
        )

    def to_dict(self) -> dict[str, Any]:
        value = deepcopy(self.attributes)
        value.update({
            "id": self.runtime_id or self.editor_id or self.id,
            "role": self.role,
            "editor_id": self.editor_id or self.id,
            "node_type": self.node_type.value,
            "semantic_type": self.semantic_type,
            "name": self.name or self.id,
            "states": deepcopy(self.states),
        })
        if self.template_id:
            value["template_id"] = self.template_id
        if self.runtime_id:
            value["runtime_id"] = self.runtime_id
        if self.name_cn:
            value["name_cn"] = self.name_cn
        if self.capabilities:
            value["capabilities"] = list(self.capabilities)
        if self.geometry:
            value["geometry"] = deepcopy(self.geometry)
        return value


class NodeType(str, Enum):
    FLOOR = "floor"
    ROOM = "room"
    OBJECT = "object"
    AGENT = "agent"

@dataclass(slots=True)
class Floor(Node):
    NODE_TYPE: ClassVar[NodeType] = NodeType.FLOOR

    @property
    def shape(self) -> ShapeSpec:
        raw = self.geometry.get("shape") or self.attributes.get("shape") or {}
        if isinstance(raw, str):
            return ShapeSpec(raw)
        return ShapeSpec(str(raw.get("kind") or "rectangle"), dict(raw.get("parameters") or {}))

    @property
    def size(self) -> SizeSpec:
        value = self.geometry.get("dimensions_m") or self.attributes.get("dimensions_m") or ()
        return SizeSpec(tuple(float(item) for item in value), "m")

    @property
    def transform(self) -> Transform:
        return Transform.from_dict(self.geometry.get("transform") or self.attributes.get("transform"))

    def dimensions(self) -> tuple[float, float]:
        value = self.geometry.get("dimensions_m") or self.attributes.get("dimensions_m") or ()
        if len(value) >= 2:
            return float(value[0]), float(value[1])
        return 0.0, 0.0

    def grid_size(self) -> float:
        return max(0.001, float(self.geometry.get("grid_size_m") or self.attributes.get("grid_size_m") or 0.1))

    @property
    def area(self) -> float:
        width, depth = self.dimensions()
        return width * depth

    def contains_point(self, point: tuple[float, float]) -> bool:
        width, depth = self.dimensions()
        x, y = point
        return width > 0 and depth > 0 and 0 <= x <= width and 0 <= y <= depth

    def grid_to_world(self, cell: tuple[int, int]) -> tuple[float, float]:
        size = self.grid_size()
        origin = self.geometry.get("origin_m") or self.attributes.get("origin_m") or (0.0, 0.0)
        return float(origin[0]) + int(cell[0]) * size, float(origin[1]) + int(cell[1]) * size

    def world_to_grid(self, point: tuple[float, float]) -> tuple[int, int]:
        size = self.grid_size()
        origin = self.geometry.get("origin_m") or self.attributes.get("origin_m") or (0.0, 0.0)
        return int((point[0] - float(origin[0])) // size), int((point[1] - float(origin[1])) // size)

    def is_valid_cell(self, cell: tuple[int, int]) -> bool:
        width, depth = self.dimensions()
        return width > 0 and depth > 0 and 0 <= cell[0] < int(width / self.grid_size()) and 0 <= cell[1] < int(depth / self.grid_size())

@dataclass(slots=True)
class Room(Node):
    NODE_TYPE: ClassVar[NodeType] = NodeType.ROOM

    @property
    def shape(self) -> ShapeSpec:
        raw = self.geometry.get("shape") or self.attributes.get("shape") or {}
        if isinstance(raw, str):
            return ShapeSpec(raw)
        return ShapeSpec(str(raw.get("kind") or "rectangle"), dict(raw.get("parameters") or {}))

    @property
    def size(self) -> SizeSpec:
        value = self.geometry.get("dimensions_m") or self.attributes.get("dimensions_m") or ()
        return SizeSpec(tuple(float(item) for item in value), "m")

    @property
    def transform(self) -> Transform:
        return Transform.from_dict(self.geometry.get("transform") or self.attributes.get("transform"))

    def dimensions(self) -> tuple[float, float, float]:
        value = self.geometry.get("dimensions_m") or self.attributes.get("dimensions_m") or ()
        return tuple(float(item) for item in value[:3]) if len(value) >= 3 else (0.0, 0.0, 0.0)

    def environment(self, key: str) -> Any:
        if key in self.states:
            return self.states[key]
        return (self.states.get("environment") or {}).get(key)

    @property
    def area(self) -> float:
        width, depth, _ = self.dimensions()
        return width * depth

    def has_environment_state(self, key: str) -> bool:
        return key in self.states or key in (self.states.get("environment") or {})


@dataclass(slots=True)
class Object(Node):
    NODE_TYPE: ClassVar[NodeType] = NodeType.OBJECT

    @property
    def editable_source(self) -> Any:
        return self.attributes.get("editable_source") or self.geometry.get("editable_source")

    @property
    def visual_reference(self) -> str | None:
        value = self.attributes.get("visual_reference") or self.attributes.get("visual_ref")
        return str(value) if value is not None else None

    @property
    def collision_reference(self) -> str | None:
        value = self.attributes.get("collision_reference") or self.attributes.get("collision_ref")
        return str(value) if value is not None else None

    @property
    def process_bindings(self) -> tuple[dict[str, Any], ...]:
        value = self.attributes.get("process_bindings") or ()
        return tuple(dict(item) for item in value if isinstance(item, dict))

    def has_capability(self, capability: str) -> bool:
        return str(capability) in self.capabilities

    def is_pickable(self) -> bool:
        return self.has_capability("pickable")

    def dimensions(self) -> tuple[float, float, float]:
        value = self.geometry.get("dimensions_cm") or self.attributes.get("dimensions_cm") or self.attributes.get("size_cm") or ()
        return tuple(float(item) for item in value[:3]) if len(value) >= 3 else (0.0, 0.0, 0.0)

    def volume(self) -> float:
        width, depth, height = self.dimensions()
        return width * depth * height

    def is_surface(self) -> bool:
        return self.has_capability("support_surface")

    def accepts_semantic_type(self, semantic_type: str) -> bool:
        accepted = self.attributes.get("accepted_capabilities") or ()
        if isinstance(accepted, str):
            accepted = (accepted,)
        return not accepted or str(semantic_type) in {str(value) for value in accepted}

    def volume_capacity(self) -> float:
        value = self.attributes.get("volume_capacity_cm3") or 0
        return max(0.0, float(value))

    def joint_definition(self) -> dict[str, Any] | None:
        value = self.attributes.get("joint")
        return deepcopy(value) if isinstance(value, dict) else None

    def surface_dimensions(self) -> tuple[float, float] | None:
        spec = self.attributes.get("surface_spec") or {}
        value = (spec.get("width_cm"), spec.get("depth_cm")) if isinstance(spec, dict) else None
        return (float(value[0]), float(value[1])) if isinstance(value, (list, tuple)) and len(value) >= 2 else None

    def part_tree(self, graph: Any):
        """Return a read-only tree view derived from graph structure edges."""
        from .articulation import part_tree_from_edges

        nodes = graph.nodes.values() if hasattr(graph, "nodes") else graph.get("nodes", ())
        edges = graph.edges if hasattr(graph, "edges") else graph.get("edges", ())
        return part_tree_from_edges(self.id, nodes, edges)


@dataclass(slots=True)
class Agent(Node):
    NODE_TYPE: ClassVar[NodeType] = NodeType.AGENT

    @property
    def embodiment(self) -> dict[str, Any]:
        value = self.attributes.get("embodiment") or {}
        return dict(value) if isinstance(value, dict) else {}

    @property
    def control_profile(self) -> dict[str, Any]:
        value = self.attributes.get("control_profile") or {}
        return dict(value) if isinstance(value, dict) else {}

    def part_tree(self, graph: Any):
        """Return the agent embodiment tree derived from structure edges."""
        from .articulation import part_tree_from_edges

        nodes = graph.nodes.values() if hasattr(graph, "nodes") else graph.get("nodes", ())
        edges = graph.edges if hasattr(graph, "edges") else graph.get("edges", ())
        return part_tree_from_edges(self.id, nodes, edges)

    def collision_shape(self) -> dict[str, Any]:
        value = self.attributes.get("collision_shape")
        if isinstance(value, dict):
            return deepcopy(value)
        return {"type": "capsule", "radius_m": 0.3, "height_m": 1.6}

    def hand_count(self) -> int:
        return max(0, int(self.attributes.get("hand_count") or 2))

    def hand_names(self) -> tuple[str, ...]:
        configured = self.attributes.get("hands")
        if isinstance(configured, (list, tuple)):
            return tuple(str(hand) for hand in configured[:self.hand_count()])
        return ("left", "right")[:self.hand_count()]

    def reach_distance_m(self) -> float:
        return max(0.0, float(self.attributes.get("reach_distance_m") or 2.2))

    def can_hold_with(self, required_hands: int) -> bool:
        return 0 < int(required_hands) <= self.hand_count()

# Uppercase aliases keep old scene/template imports source-compatible while
# the public core vocabulary uses the documented class names.
FLOOR = Floor
ROOM = Room
OBJECT = Object
AGENT = Agent

__all__ = ["Node", "NodeType", "ShapeSpec", "SizeSpec", "Floor", "Room", "Object", "Agent", "FLOOR", "ROOM", "OBJECT", "AGENT"]
