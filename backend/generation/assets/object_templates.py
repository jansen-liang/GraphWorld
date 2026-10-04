"""Composable object declarations shared by scene generation and runtime.

The declarations are intentionally geometric-light: they describe semantic
parts and their attachment contract, while renderers remain free to choose
the actual mesh implementation.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


MOUNT_FACES = frozenset({"front", "back", "left", "right", "top", "bottom", "interior"})


@dataclass(frozen=True)
class ComponentTemplate:
    role: str
    semantic_type: str
    node_type: str = "object"
    mount_face: str = "front"
    anchor: tuple[float, float, float] = (0.5, 0.5, 0.0)
    relation: str = "component_of"
    capabilities: tuple[str, ...] = ()
    optional: bool = False
    repeatable: bool = False

    def __post_init__(self) -> None:
        if self.mount_face not in MOUNT_FACES:
            raise ValueError(f"unsupported component mount face: {self.mount_face}")
        if len(self.anchor) != 3 or any(not 0 <= value <= 1 for value in self.anchor):
            raise ValueError("component anchor must contain three normalized values")

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "semantic_type": self.semantic_type,
            "node_type": self.node_type,
            "mount_face": self.mount_face,
            "anchor": list(self.anchor),
            "relation": self.relation,
            "capabilities": list(self.capabilities),
            "optional": self.optional,
            "repeatable": self.repeatable,
        }


@dataclass(frozen=True)
class StorageSpec:
    kind: str = "open"
    levels: int = 1
    columns: int = 1
    depth_cm: float = 30.0
    drawer_count: int = 0
    slot_semantic_type: str = "storage_slot"
    capacity_per_slot: int = 8
    accepted_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in {"open", "shelved", "drawer", "mixed"}:
            raise ValueError(f"unsupported storage topology: {self.kind}")
        if self.levels < 1 or self.columns < 1 or self.depth_cm <= 0 or self.drawer_count < 0 or self.capacity_per_slot < 1:
            raise ValueError("storage topology dimensions must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "levels": self.levels,
            "columns": self.columns,
            "depth_cm": self.depth_cm,
            "drawer_count": self.drawer_count,
            "slot_semantic_type": self.slot_semantic_type,
            "capacity_per_slot": self.capacity_per_slot,
            "accepted_capabilities": list(self.accepted_capabilities),
        }


@dataclass(frozen=True)
class ObjectStructure:
    components: tuple[ComponentTemplate, ...] = ()
    storage: StorageSpec | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"components": [item.to_dict() for item in self.components]}
        if self.storage is not None:
            payload["storage"] = self.storage.to_dict()
        return payload


def _component(role: str, semantic_type: str, *, face: str = "front", anchor: tuple[float, float, float] = (0.5, 0.5, 0.0), node_type: str = "object", capabilities: tuple[str, ...] = (), optional: bool = False, repeatable: bool = False) -> ComponentTemplate:
    return ComponentTemplate(role, semantic_type, node_type=node_type, mount_face=face, anchor=anchor, capabilities=capabilities, optional=optional, repeatable=repeatable)


DEFAULT_STRUCTURES: dict[str, ObjectStructure] = {
    "rack": ObjectStructure(storage=StorageSpec(kind="shelved", levels=3, columns=1, depth_cm=35.0, capacity_per_slot=6)),
    "drying_rack": ObjectStructure(storage=StorageSpec(kind="shelved", levels=3, columns=1, depth_cm=45.0, capacity_per_slot=6)),
    "shoe_rack": ObjectStructure(storage=StorageSpec(kind="shelved", levels=3, columns=2, depth_cm=32.0, capacity_per_slot=4)),
    "shelf": ObjectStructure(storage=StorageSpec(kind="shelved", levels=4, columns=1, depth_cm=32.0, capacity_per_slot=8)),
    "washing_machine": ObjectStructure(components=(
        _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="object"),
        _component("door", "door", face="front", anchor=(0.5, 0.48, 0.0), capabilities=("openable",)),
        _component("start_button", "button", face="top", anchor=(0.82, 0.15, 0.0), capabilities=("switchable",)),
    ), storage=StorageSpec(kind="open", levels=1, columns=1, depth_cm=55.0, capacity_per_slot=6, accepted_capabilities=("washable",))),
    "washer": ObjectStructure(components=(
        _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="object"),
        _component("door", "door", face="front", anchor=(0.5, 0.48, 0.0), capabilities=("openable",)),
        _component("start_button", "button", face="top", anchor=(0.82, 0.15, 0.0), capabilities=("switchable",)),
    ), storage=StorageSpec(kind="open", levels=1, columns=1, depth_cm=55.0, capacity_per_slot=6, accepted_capabilities=("washable",))),
    "microwave": ObjectStructure(components=(
        _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="object"),
        _component("door", "door", face="front", anchor=(0.5, 0.5, 0.0), capabilities=("openable",)),
        _component("start_button", "button", face="top", anchor=(0.82, 0.15, 0.0), capabilities=("switchable",)),
    ), storage=StorageSpec(kind="open", levels=1, columns=1, depth_cm=35.0, capacity_per_slot=1, accepted_capabilities=("cookable",))),
    "dishwasher": ObjectStructure(components=(
        _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="object"),
        _component("door", "door", face="front", anchor=(0.5, 0.5, 0.0), capabilities=("openable",)),
        _component("start_button", "button", face="top", anchor=(0.82, 0.15, 0.0), capabilities=("switchable",)),
    ), storage=StorageSpec(kind="open", levels=1, columns=1, depth_cm=55.0, capacity_per_slot=8, accepted_capabilities=("dishwashable",))),
    "dryer": ObjectStructure(components=(
        _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="object"),
        _component("door", "door", face="front", anchor=(0.5, 0.48, 0.0), capabilities=("openable",)),
        _component("start_button", "button", face="top", anchor=(0.82, 0.15, 0.0), capabilities=("switchable",)),
    ), storage=StorageSpec(kind="open", levels=1, columns=1, depth_cm=55.0, capacity_per_slot=6, accepted_capabilities=("dryable",))),
    "clothesdryer": ObjectStructure(components=(
        _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="object"),
        _component("door", "door", face="front", anchor=(0.5, 0.48, 0.0), capabilities=("openable",)),
        _component("start_button", "button", face="top", anchor=(0.82, 0.15, 0.0), capabilities=("switchable",)),
    ), storage=StorageSpec(kind="open", levels=1, columns=1, depth_cm=55.0, capacity_per_slot=6, accepted_capabilities=("dryable",))),
    "elevator": ObjectStructure(components=(
        # The car shell and its paired sliding doors are generated by the
        # renderer as articulated children of the car.  Do not add the
        # generic single hinged appliance door here: it rendered as a second
        # green panel in the centre of the cabin and was not part of the
        # elevator articulation.
        _component("floor_button", "button", face="interior", anchor=(0.86, 0.45, 0.0), capabilities=("switchable",), optional=True),
    )),
    "toilet": ObjectStructure(components=(
        _component("flush_button", "button", face="top", anchor=(0.72, 0.62, 0.0), capabilities=("switchable",)),
    )),
    "refrigerator": ObjectStructure(components=(
        _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="object"),
        _component("door", "door", face="front", anchor=(0.95, 0.5, 0.0), capabilities=("openable",)),
        _component("storage_slot", "storage_slot", face="interior", anchor=(0.5, 0.5, 0.5), node_type="object", capabilities=("place_target",), repeatable=True),
    ), storage=StorageSpec(kind="shelved", levels=4, columns=1, depth_cm=55.0, capacity_per_slot=8)),
    "medicine_fridge": ObjectStructure(components=(
        _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="object"),
        _component("door", "door", face="front", anchor=(0.95, 0.5, 0.0), capabilities=("openable",)),
        _component("storage_slot", "storage_slot", face="interior", anchor=(0.5, 0.5, 0.5), node_type="object", capabilities=("place_target",), repeatable=True),
    ), storage=StorageSpec(kind="shelved", levels=3, columns=1, depth_cm=30.0, capacity_per_slot=8)),
    "locker": ObjectStructure(components=(
        _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="object"),
        _component("door", "door", face="front", anchor=(0.95, 0.5, 0.0), capabilities=("openable",)),
        _component("storage_slot", "storage_slot", face="interior", anchor=(0.5, 0.5, 0.5), node_type="object", capabilities=("place_target",), repeatable=True),
    ), storage=StorageSpec(kind="shelved", levels=4, columns=1, depth_cm=35.0, capacity_per_slot=8)),
    "cabinet": ObjectStructure(
        components=(
            _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="object"),
            _component("door", "door", face="front", anchor=(0.5, 0.5, 0.0), capabilities=("openable",), optional=True),
            _component("storage_slot", "storage_slot", face="interior", anchor=(0.5, 0.5, 0.5), node_type="object", capabilities=("place_target",), repeatable=True),
        ),
        storage=StorageSpec(kind="mixed", levels=3, columns=2, depth_cm=35.0, drawer_count=2, capacity_per_slot=8),
    ),
    "wardrobe": ObjectStructure(
        components=(
            _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="object"),
            _component("door", "door", face="front", anchor=(0.5, 0.5, 0.0), capabilities=("openable",), optional=True),
            _component("storage_slot", "storage_slot", face="interior", anchor=(0.5, 0.5, 0.5), node_type="object", capabilities=("place_target",), repeatable=True),
        ),
        storage=StorageSpec(kind="mixed", levels=4, columns=2, depth_cm=55.0, drawer_count=2, capacity_per_slot=8),
    ),
    "dresser": ObjectStructure(
        components=(
            _component("storage_slot", "storage_slot", face="interior", anchor=(0.5, 0.5, 0.5), node_type="object", capabilities=("place_target",), repeatable=True),
        ),
        storage=StorageSpec(kind="drawer", levels=3, columns=1, depth_cm=40.0, drawer_count=3, capacity_per_slot=8),
    ),
    "desk": ObjectStructure(
        components=(
            _component("storage_slot", "storage_slot", face="interior", anchor=(0.5, 0.5, 0.5), node_type="object", capabilities=("place_target",), repeatable=True),
        ),
        storage=StorageSpec(kind="mixed", levels=2, columns=1, depth_cm=42.0, drawer_count=2, capacity_per_slot=8),
    ),
    "drawer": ObjectStructure(components=(
        _component("drawer_slot", "storage_slot", face="interior", anchor=(0.5, 0.5, 0.5), node_type="object", capabilities=("place_target",)),
    )),
}


def structure_for(semantic_type: str) -> ObjectStructure:
    return DEFAULT_STRUCTURES.get(str(semantic_type or "").lower(), ObjectStructure())


def validate_templates(nodes: list[dict[str, Any]] | dict[str, dict[str, Any]]) -> list[str]:
    """Validate declared component references without requiring generated IDs."""
    values = list(nodes.values()) if isinstance(nodes, dict) else nodes
    by_id = {str(item.get("id")): item for item in values if isinstance(item, dict) and item.get("id")}
    issues: list[str] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("id") or "")
        structure = item.get("structure") or item.get("composition") or {}
        for component in structure.get("components") or []:
            if not isinstance(component, dict):
                issues.append(f"{node_id} has an invalid composition component")
                continue
            face = component.get("mount_face", "front")
            if face not in MOUNT_FACES:
                issues.append(f"{node_id} component {component.get('role', '')} has invalid mount face {face}")
    return issues


def materialize_templates(scene: dict[str, Any]) -> dict[str, Any]:
    """Expand declared structures into runtime child nodes and edges.

    The operation is idempotent and mutates the supplied scene in place. A
    structure remains a declaration on the host node; generated children are
    connected through immutable structure and mechanical edges.
    """
    from .object_library import build_object_node

    nodes = scene.setdefault("nodes", [])
    if not isinstance(nodes, list):
        return scene
    by_id = {str(item.get("id")): item for item in nodes if isinstance(item, dict) and item.get("id")}
    edges = scene.setdefault("edges", [])
    if not isinstance(edges, list):
        edges = []
        scene["edges"] = edges

    # Upgrade materialized snapshots from the pre-PartTree format.  These
    # edges represented the same immutable parent/child fact as `structure`,
    # but also added a redundant host->component `in` edge.  Normalize them
    # before generating any new children so repeated loads converge.
    upgraded_edges: list[dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        relation = str(edge.get("relation") or "")
        if relation == "component_of":
            parent = str(edge.get("source_id") or edge.get("source") or "")
            child = str(edge.get("target_id") or edge.get("target") or "")
            child_node = by_id.get(child)
            if parent and child and child_node is not None:
                child_node.setdefault("role", "component")
                child_node.setdefault("owner_id", parent)
                child_node.setdefault("link_id", child)
                child_node.setdefault("local_transform", {
                    "position": [0.0, 0.0, 0.0],
                    "rotation": [0.0, 0.0, 0.0, 1.0],
                    "scale": [1.0, 1.0, 1.0],
                })
                if child_node.get("component_role") in {"storage_slot", "drawer"}:
                    capacity = int(child_node.get("max_capacity") or child_node.get("max_items") or 8)
                    child_node["can_contain"] = True
                    child_node["max_capacity"] = capacity
                    child_node["max_items"] = capacity
                    accepted = child_node.get("requires_contained_capabilities") or child_node.get("accepted_capabilities") or []
                    if accepted:
                        child_node["accepted_capabilities"] = list(accepted)
                props = dict(edge.get("properties") or {})
                upgraded_edges.append({
                    **edge,
                    "relation": "structure",
                    "edge_type": "structure_edge",
                    "properties": {
                        **props,
                        "parent": parent,
                        "child": child,
                        "joint_type": str(props.get("joint_type") or "fixed"),
                        "axis": list(props.get("axis") or (0.0, 0.0, 1.0)),
                        "origin": props.get("origin") or {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0, 1.0], "scale": [1.0, 1.0, 1.0]},
                    },
                })
                continue
        if relation in {"in", "inside"} and (edge.get("properties") or {}).get("generated"):
            source = str(edge.get("source_id") or "")
            target = str(edge.get("target_id") or "")
            if source in by_id and target in by_id:
                source_node = by_id[source]
                target_node = by_id[target]
                if target_node.get("role") == "component" or target_node.get("component_role"):
                    continue
        upgraded_edges.append(edge)
    edges[:] = upgraded_edges

    def add_child(host_id: str, child_id: str, spec: dict[str, Any], *, role: str, index: int | None = None) -> None:
        if child_id in by_id:
            return
        semantic_type = str(spec.get("semantic_type") or "object")
        node = build_object_node(child_id, semantic_type)
        node["node_type"] = str(spec.get("node_type") or node.get("node_type") or "object")
        # Component declarations are the authoritative affordance contract.
        # Do not let the generic semantic template (for example the reusable
        # storage_slot template) leak capabilities that this component does
        # not actually expose.
        declared_capabilities = {str(value) for value in (spec.get("capabilities") or ())}
        node["capabilities"] = sorted(declared_capabilities)
        if semantic_type == "storage_slot":
            node["capabilities"] = sorted(capability for capability in declared_capabilities if capability != "pickable")
        node["component_role"] = role
        node["role"] = "component"
        node["owner_id"] = host_id
        node["link_id"] = child_id
        host_layout = ((scene.get("layout") or {}).get("objects") or {}).get(host_id, {})
        host_dimensions = (
            host_layout.get("width_cm"), host_layout.get("depth_cm"), host_layout.get("height_cm")
        ) if isinstance(host_layout, dict) else (None, None, None)
        anchor = tuple(float(value) for value in (spec.get("anchor") or (0.5, 0.5, 0.0))[:3])
        dimensions_m = tuple(float(value or 0.0) / 100.0 for value in host_dimensions)
        local_position = [
            (anchor[index] - 0.5) * dimensions_m[index] if dimensions_m[index] > 0 else 0.0
            for index in range(3)
        ]
        node["local_transform"] = {
            "position": local_position,
            "rotation": [0.0, 0.0, 0.0, 1.0],
            "scale": [1.0, 1.0, 1.0],
        }
        node["structure_materialized"] = True
        node["mount_face"] = str(spec.get("mount_face") or "front")
        node["mount_anchor"] = list(spec.get("anchor") or (0.5, 0.5, 0.0))
        if semantic_type == "storage_slot":
            # A slot is a real placement volume, not only a visual divider.
            depth = float((structure.get("storage") or {}).get("depth_cm") or 30.0)
            levels = max(1, int((structure.get("storage") or {}).get("levels") or 1))
            columns = max(1, int((structure.get("storage") or {}).get("columns") or 1))
            node["interior_size_cm"] = [120.0 / columns, depth, 100.0 / levels]
            node["volume_grid_cm"] = 1.0
            storage = structure.get("storage") or {}
            node["max_capacity"] = int(storage.get("capacity_per_slot") or 8)
            node["can_contain"] = True
            node["max_items"] = node["max_capacity"]
            node["states"]["capacity"] = node["max_capacity"]
            accepted = storage.get("accepted_capabilities") or []
            if accepted:
                node["requires_contained_capabilities"] = list(accepted)
                node["accepted_capabilities"] = list(accepted)
        if semantic_type == "door":
            node["door_kind"] = "device"
            node["parent_device_type"] = str(by_id.get(host_id, {}).get("semantic_type") or "")
            node["requires_closed_to_start"] = bool(by_id.get(host_id, {}).get("requires_closed_to_start"))
            # Generated appliance/container doors are independently actionable.
            # The generic ``door`` template is structural by default, so make
            # the component's affordance explicit when it is mounted on a
            # non-structural host.
            if node.get("door_kind") != "structural":
                node["door_kind"] = "device"
                node["capabilities"] = ["openable"]
                node["interactive_actions"] = ["open", "close"]
                node.setdefault("states", {})["is_open"] = False
        if semantic_type == "drawer":
            node["capabilities"] = ["openable", "place_target"]
            node["interactive_actions"] = ["open", "close", "place"]
            node.setdefault("states", {})["is_open"] = False
            node["max_capacity"] = int((structure.get("storage") or {}).get("capacity_per_slot") or 8)
            node["can_contain"] = True
            node["max_items"] = node["max_capacity"]
            node["states"]["capacity"] = node["max_capacity"]
        if index is not None:
            node["component_index"] = index
        if semantic_type == "button":
            node.setdefault("states", {}).setdefault("is_pressed", False)
            node.setdefault("interactive_actions", []).append("press")
            control_edge = {
                "source_id": child_id,
                "target_id": host_id,
                "relation": "controls",
                "edge_type": "control_edge",
                "category": "logical",
                "properties": {"component_role": role},
            }
            if not any(
                str(edge.get("source_id") or "") == child_id
                and str(edge.get("target_id") or "") == host_id
                and str(edge.get("relation") or "") == "controls"
                for edge in edges
                if isinstance(edge, dict)
            ):
                edges.append(control_edge)
        component_edge = {
            "source_id": host_id,
            "target_id": child_id,
            "relation": "structure",
            "edge_type": "structure_edge",
            "category": "physical",
            "properties": {
                "parent": host_id,
                "child": child_id,
                "joint_type": str(spec.get("joint_type") or "fixed"),
                "axis": list(spec.get("axis") or (0.0, 0.0, 1.0)),
                "origin": {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0, 1.0], "scale": [1.0, 1.0, 1.0]},
                "component_role": role,
                "mount_face": node["mount_face"],
            },
        }
        if not any(
            str(edge.get("source_id") or "") == host_id
            and str(edge.get("target_id") or "") == child_id
            and str(edge.get("relation") or "") in {"structure", "component_of"}
            for edge in edges
            if isinstance(edge, dict)
        ):
            edges.append(component_edge)
        nodes.append(node)
        by_id[child_id] = node

    def promote_existing_child(host_id: str, child_id: str, spec: dict[str, Any], *, role: str, index: int | None = None) -> None:
        """Migrate an authored pre-PartTree child into the canonical link.

        Older scene versions stored appliance parts as ordinary root nodes with
        ``contains`` edges.  Once a structure declaration exists, the declared
        ``host_id + role`` link is the only identity and must become a
        structure child without leaving a duplicate render/interaction proxy.
        This is intentionally semantic and applies to every asset, not only a
        particular appliance.
        """
        node = by_id.get(child_id)
        if node is None:
            add_child(host_id, child_id, spec, role=role, index=index)
            return
        node["role"] = "component"
        node["owner_id"] = host_id
        node["link_id"] = child_id
        node["component_role"] = role
        node["structure_materialized"] = True
        node["mount_face"] = str(spec.get("mount_face") or node.get("mount_face") or "front")
        node.setdefault("local_transform", {
            "position": [0.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0, 1.0],
            "scale": [1.0, 1.0, 1.0],
        })
        # A migrated component must no longer be independently placed in a
        # room or container. Its sole spatial parent is the structure edge.
        edges[:] = [
            edge for edge in edges
            if not (
                isinstance(edge, dict)
                and str(edge.get("target_id") or edge.get("target") or "") == child_id
                and str(edge.get("relation") or "") in {"at", "in", "inside", "inside_room", "on", "contains"}
                and str(edge.get("source_id") or edge.get("source") or "") != host_id
            )
        ]
        declared = {str(value) for value in (spec.get("capabilities") or ())}
        if role == "storage_slot": declared.discard("pickable")
        if declared:
            node["capabilities"] = sorted(declared)
        if role == "door":
            node["capabilities"] = ["openable"]
            node["interactive_actions"] = ["open", "close"]
            node.setdefault("states", {}).setdefault("is_open", False)
        if role == "drawer":
            node["capabilities"] = ["openable", "place_target"]
            node["interactive_actions"] = ["open", "close", "place"]
            node.setdefault("states", {}).setdefault("is_open", False)
        if role == "start_button" or str(spec.get("semantic_type") or "") == "button":
            node.setdefault("states", {}).setdefault("is_pressed", False)
            node["interactive_actions"] = sorted(set(node.get("interactive_actions") or []) | {"press"})

        for edge in edges:
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("source_id") or edge.get("source") or "")
            target = str(edge.get("target_id") or edge.get("target") or "")
            if source != host_id or target != child_id:
                continue
            relation = str(edge.get("relation") or "")
            if relation in {"contains", "component_of", "part_of"}:
                edge.update({
                    "source_id": host_id,
                    "target_id": child_id,
                    "relation": "structure",
                    "edge_type": "structure_edge",
                    "category": "physical",
                    "properties": {
                        **dict(edge.get("properties") or {}),
                        "parent": host_id,
                        "child": child_id,
                        "joint_type": str((edge.get("properties") or {}).get("joint_type") or spec.get("joint_type") or "fixed"),
                        "axis": list((edge.get("properties") or {}).get("axis") or spec.get("axis") or (0.0, 0.0, 1.0)),
                        "origin": (edge.get("properties") or {}).get("origin") or {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0, 1.0], "scale": [1.0, 1.0, 1.0]},
                        "component_role": role,
                        "mount_face": node["mount_face"],
                    },
                })
                break
        else:
            edges.append({
                "source_id": host_id,
                "target_id": child_id,
                "relation": "structure",
                "edge_type": "structure_edge",
                "category": "physical",
                "properties": {
                    "parent": host_id,
                    "child": child_id,
                    "joint_type": str(spec.get("joint_type") or "fixed"),
                    "axis": list(spec.get("axis") or (0.0, 0.0, 1.0)),
                    "origin": {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0, 1.0], "scale": [1.0, 1.0, 1.0]},
                    "component_role": role,
                    "mount_face": node["mount_face"],
                },
            })

    for host in list(nodes):
        if not isinstance(host, dict) or not host.get("id"):
            continue
        host_id = str(host["id"])
        # Revisit materialized root hosts to repair newly introduced
        # mechanical edges, but never recursively materialize a generated
        # component (for example, a drawer's own storage slot).
        component_host_ids = {
            str(edge.get("target_id") or "")
            for edge in edges
            if isinstance(edge, dict) and str(edge.get("relation") or "") in {"structure", "component_of"}
        }
        if host.get("structure_materialized") and host_id in component_host_ids:
            continue
        structure = host.get("structure") or host.get("composition") or {}
        # Old snapshots can carry an earlier partial declaration (for
        # example, appliance controls without the later storage contract).
        # Preserve instance-authored components and fill only missing static
        # structure from the current template.
        semantic_type = str(host.get("semantic_type") or "")
        if semantic_type:
            template = build_object_node("__template__", semantic_type)
            # Existing scene snapshots may predate capability or support
            # surface declarations. Materialization upgrades those instances
            # from the same object template used for newly created nodes.
            host["capabilities"] = sorted({
                str(value).lower()
                for value in [*(host.get("capabilities") or []), *(template.get("capabilities") or [])]
            })
            host["interactive_actions"] = sorted({
                str(value).lower()
                for value in [*(host.get("interactive_actions") or []), *(template.get("interactive_actions") or [])]
            })
            for key in ("surface_size_cm", "surface_grid_cm", "support_surface_cm", "support_grid_cm", "footprint_cm", "interior_size_cm"):
                if key not in host and key in template:
                    host[key] = deepcopy(template[key])
            template_structure = template.get("structure") or template.get("composition") or {}
            if not structure and template_structure:
                structure = deepcopy(template_structure)
            elif template_structure.get("storage") and not structure.get("storage"):
                structure = {**structure, "storage": deepcopy(template_structure["storage"])}
            if structure:
                host["structure"] = structure
                host.pop("composition", None)
        host_capabilities = {str(value).lower() for value in host.get("capabilities") or ()}
        if host.get("surface_size_cm") and "support_surface" not in host_capabilities:
            host_capabilities.add("support_surface")
            host["capabilities"] = sorted(host_capabilities)
        # Link capacity is explicit runtime data. Keep the root object's
        # temporary support surface distinct from child containment slots.
        # Receiving an object is not the same as exposing a root top surface.
        # Only the explicit support capability grants a default top surface;
        # place_target may describe a container/link or another semantic target.
        if "support_surface" in host_capabilities:
            host["can_support"] = True
        if "receptacle" in host_capabilities:
            host["can_contain"] = True
        component_specs = structure.get("components") or []
        for spec in component_specs:
            if not isinstance(spec, dict):
                continue
            role = str(spec.get("role") or spec.get("semantic_type") or "component")
            if role == "storage_slot" and spec.get("repeatable"):
                continue
            child_id = f"{host_id}_{role}"
            if child_id not in by_id:
                # Historical snapshots used semantic names such as
                # ``*_button`` while the current declaration uses the role
                # ``*_start_button``. Reuse the existing graph Node by its
                # host edge and semantic role instead of creating a duplicate.
                expected_semantic = str(spec.get("semantic_type") or role)
                for candidate_edge in edges:
                    if not isinstance(candidate_edge, dict):
                        continue
                    if str(candidate_edge.get("source_id") or candidate_edge.get("source") or "") != host_id:
                        continue
                    if str(candidate_edge.get("relation") or "") not in {"contains", "component_of", "part_of", "structure"}:
                        continue
                    candidate_id = str(candidate_edge.get("target_id") or candidate_edge.get("target") or "")
                    candidate = by_id.get(candidate_id) or {}
                    candidate_role = str(candidate.get("component_role") or "")
                    candidate_semantic = str(candidate.get("semantic_type") or "")
                    if candidate_role == role or candidate_semantic == expected_semantic:
                        child_id = candidate_id
                        break
            else:
                # If a canonical generated link already exists, discard a
                # second legacy root child with the same host/semantic role.
                expected_semantic = str(spec.get("semantic_type") or role)
                duplicate_ids = {
                    str(edge.get("target_id") or edge.get("target") or "")
                    for edge in edges
                    if isinstance(edge, dict)
                    and str(edge.get("source_id") or edge.get("source") or "") == host_id
                    and str(edge.get("relation") or "") in {"contains", "component_of", "part_of"}
                    and str(edge.get("target_id") or edge.get("target") or "") != child_id
                    and str((by_id.get(str(edge.get("target_id") or edge.get("target") or "")) or {}).get("semantic_type") or "") == expected_semantic
                }
                if duplicate_ids:
                    nodes[:] = [node for node in nodes if str(node.get("id") or "") not in duplicate_ids]
                    edges[:] = [edge for edge in edges if str(edge.get("source_id") or edge.get("source") or "") not in duplicate_ids and str(edge.get("target_id") or edge.get("target") or "") not in duplicate_ids]
                    for duplicate_id in duplicate_ids:
                        by_id.pop(duplicate_id, None)
            # Promote an existing authored child when it already has the
            # canonical id; this removes the old root-node interpretation.
            promote_existing_child(host_id, child_id, spec, role=role)

        storage = structure.get("storage") or {}
        levels = max(1, int(storage.get("levels") or 1))
        columns = max(1, int(storage.get("columns") or 1))
        slot_spec = next((spec for spec in component_specs if isinstance(spec, dict) and spec.get("role") == "storage_slot"), None)
        if slot_spec is None and storage:
            slot_spec = {
                "role": "storage_slot",
                "semantic_type": str(storage.get("slot_semantic_type") or "storage_slot"),
                "node_type": "object",
                "mount_face": "interior",
                "anchor": [0.5, 0.5, 0.5],
                "capabilities": ["place_target"],
                "repeatable": True,
            }
        if slot_spec and slot_spec.get("repeatable"):
            for level in range(levels):
                for column in range(columns):
                    slot_id = f"{host_id}_slot_l{level + 1}_c{column + 1}"
                    slot = dict(slot_spec)
                    slot["anchor"] = [
                        (column + 0.5) / columns,
                        (level + 0.5) / levels,
                        float(slot_spec.get("anchor", [0.5, 0.5, 0.5])[2]),
                    ]
                    add_child(host_id, slot_id, slot, role="storage_slot", index=level * columns + column)
        drawer_count = max(0, int(storage.get("drawer_count") or 0))
        for drawer_index in range(drawer_count):
            drawer_id = f"{host_id}_drawer_{drawer_index + 1}"
            drawer_spec = {
                "semantic_type": "drawer",
                "node_type": "object",
                "mount_face": "front",
                "anchor": [(drawer_index + 0.5) / max(1, drawer_count), 0.15, 0.0],
            }
            add_child(host_id, drawer_id, drawer_spec, role="drawer", index=drawer_index)
        # Preserve the mechanical relationships between generated parts. The
        # containment edge says that both parts belong to the host; these
        # edges say how the parts move relative to one another.
        component_ids = {
            str((by_id.get(str(edge.get("target_id") or "")) or {}).get("component_role") or ""): str(edge.get("target_id") or "")
            for edge in edges
            if isinstance(edge, dict)
            and str(edge.get("source_id") or "") == host_id
            and str(edge.get("relation") or "") in {"structure", "component_of"}
            and edge.get("target_id")
        }
        hinge_id = component_ids.get("hinge")
        door_id = component_ids.get("door")
        if hinge_id and door_id and not any(
            str(edge.get("source_id") or "") == hinge_id
            and str(edge.get("target_id") or "") == door_id
            and str(edge.get("relation") or "") == "hinge_of"
            for edge in edges
            if isinstance(edge, dict)
        ):
            edges.append({
                "source_id": hinge_id,
                "target_id": door_id,
                "relation": "hinge_of",
                "edge_type": "mechanical_edge",
                "category": "physical",
                "properties": {"host_id": host_id},
            })
        for edge in edges:
            if not isinstance(edge, dict) or str(edge.get("source_id") or "") != host_id or str(edge.get("relation") or "") not in {"structure", "component_of"}:
                continue
            drawer_id = str(edge.get("target_id") or "")
            if str((by_id.get(drawer_id) or {}).get("component_role") or "") != "drawer":
                continue
            if drawer_id and not any(
                str(edge.get("source_id") or "") == drawer_id
                and str(edge.get("target_id") or "") == host_id
                and str(edge.get("relation") or "") == "slides_in"
                for edge in edges
                if isinstance(edge, dict)
            ):
                edges.append({
                    "source_id": drawer_id,
                    "target_id": host_id,
                    "relation": "slides_in",
                    "edge_type": "mechanical_edge",
                    "category": "physical",
                    "properties": {"host_id": host_id},
                })
        if structure.get("components") or structure.get("storage"):
            host["structure_materialized"] = True
            host.pop("composition_materialized", None)
    return scene


__all__ = ["ComponentTemplate", "ObjectStructure", "DEFAULT_STRUCTURES", "StorageSpec", "structure_for", "materialize_templates", "validate_templates"]
