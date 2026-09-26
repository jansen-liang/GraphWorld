"""Composable object declarations shared by scene generation and runtime.

The declarations are intentionally geometric-light: they describe semantic
parts and their attachment contract, while renderers remain free to choose
the actual mesh implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


MOUNT_FACES = frozenset({"front", "back", "left", "right", "top", "bottom", "interior"})


@dataclass(frozen=True)
class ComponentSpec:
    role: str
    semantic_type: str
    node_type: str = "control_object"
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
class StorageTopology:
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
class CompositionSpec:
    components: tuple[ComponentSpec, ...] = ()
    storage: StorageTopology | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"components": [item.to_dict() for item in self.components]}
        if self.storage is not None:
            payload["storage"] = self.storage.to_dict()
        return payload


def _component(role: str, semantic_type: str, *, face: str = "front", anchor: tuple[float, float, float] = (0.5, 0.5, 0.0), node_type: str = "control_object", capabilities: tuple[str, ...] = (), optional: bool = False, repeatable: bool = False) -> ComponentSpec:
    return ComponentSpec(role, semantic_type, node_type=node_type, mount_face=face, anchor=anchor, capabilities=capabilities, optional=optional, repeatable=repeatable)


DEFAULT_COMPOSITIONS: dict[str, CompositionSpec] = {
    "rack": CompositionSpec(storage=StorageTopology(kind="shelved", levels=3, columns=1, depth_cm=35.0, capacity_per_slot=6)),
    "drying_rack": CompositionSpec(storage=StorageTopology(kind="shelved", levels=3, columns=1, depth_cm=45.0, capacity_per_slot=6)),
    "shoe_rack": CompositionSpec(storage=StorageTopology(kind="shelved", levels=3, columns=2, depth_cm=32.0, capacity_per_slot=4)),
    "shelf": CompositionSpec(storage=StorageTopology(kind="shelved", levels=4, columns=1, depth_cm=32.0, capacity_per_slot=8)),
    "washing_machine": CompositionSpec(components=(
        _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="fixed_object"),
        _component("door", "door", face="front", anchor=(0.5, 0.48, 0.0), capabilities=("openable",)),
        _component("start_button", "button", face="top", anchor=(0.82, 0.15, 0.0), capabilities=("switchable",)),
    ), storage=StorageTopology(kind="open", levels=1, columns=1, depth_cm=55.0, capacity_per_slot=6, accepted_capabilities=("washable",))),
    "washer": CompositionSpec(components=(
        _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="fixed_object"),
        _component("door", "door", face="front", anchor=(0.5, 0.48, 0.0), capabilities=("openable",)),
        _component("start_button", "button", face="top", anchor=(0.82, 0.15, 0.0), capabilities=("switchable",)),
    ), storage=StorageTopology(kind="open", levels=1, columns=1, depth_cm=55.0, capacity_per_slot=6, accepted_capabilities=("washable",))),
    "microwave": CompositionSpec(components=(
        _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="fixed_object"),
        _component("door", "door", face="front", anchor=(0.5, 0.5, 0.0), capabilities=("openable",)),
        _component("start_button", "button", face="top", anchor=(0.82, 0.15, 0.0), capabilities=("switchable",)),
    ), storage=StorageTopology(kind="open", levels=1, columns=1, depth_cm=35.0, capacity_per_slot=1, accepted_capabilities=("cookable",))),
    "dishwasher": CompositionSpec(components=(
        _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="fixed_object"),
        _component("door", "door", face="front", anchor=(0.5, 0.5, 0.0), capabilities=("openable",)),
        _component("start_button", "button", face="top", anchor=(0.82, 0.15, 0.0), capabilities=("switchable",)),
    ), storage=StorageTopology(kind="open", levels=1, columns=1, depth_cm=55.0, capacity_per_slot=8, accepted_capabilities=("dishwashable",))),
    "dryer": CompositionSpec(components=(
        _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="fixed_object"),
        _component("door", "door", face="front", anchor=(0.5, 0.48, 0.0), capabilities=("openable",)),
        _component("start_button", "button", face="top", anchor=(0.82, 0.15, 0.0), capabilities=("switchable",)),
    ), storage=StorageTopology(kind="open", levels=1, columns=1, depth_cm=55.0, capacity_per_slot=6, accepted_capabilities=("dryable",))),
    "clothesdryer": CompositionSpec(components=(
        _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="fixed_object"),
        _component("door", "door", face="front", anchor=(0.5, 0.48, 0.0), capabilities=("openable",)),
        _component("start_button", "button", face="top", anchor=(0.82, 0.15, 0.0), capabilities=("switchable",)),
    ), storage=StorageTopology(kind="open", levels=1, columns=1, depth_cm=55.0, capacity_per_slot=6, accepted_capabilities=("dryable",))),
    "elevator": CompositionSpec(components=(
        _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="fixed_object"),
        _component("door", "door", face="front", anchor=(0.5, 0.5, 0.0), capabilities=("openable",)),
        _component("floor_button", "button", face="interior", anchor=(0.86, 0.45, 0.0), capabilities=("switchable",), optional=True),
    )),
    "toilet": CompositionSpec(components=(
        _component("flush_button", "button", face="top", anchor=(0.72, 0.62, 0.0), capabilities=("switchable",)),
    )),
    "refrigerator": CompositionSpec(components=(
        _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="fixed_object"),
        _component("door", "door", face="front", anchor=(0.95, 0.5, 0.0), capabilities=("openable",)),
        _component("storage_slot", "storage_slot", face="interior", anchor=(0.5, 0.5, 0.5), node_type="fixed_object", capabilities=("place_target",), repeatable=True),
    ), storage=StorageTopology(kind="shelved", levels=4, columns=1, depth_cm=55.0, capacity_per_slot=8)),
    "medicine_fridge": CompositionSpec(components=(
        _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="fixed_object"),
        _component("door", "door", face="front", anchor=(0.95, 0.5, 0.0), capabilities=("openable",)),
        _component("storage_slot", "storage_slot", face="interior", anchor=(0.5, 0.5, 0.5), node_type="fixed_object", capabilities=("place_target",), repeatable=True),
    ), storage=StorageTopology(kind="shelved", levels=3, columns=1, depth_cm=30.0, capacity_per_slot=8)),
    "locker": CompositionSpec(components=(
        _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="fixed_object"),
        _component("door", "door", face="front", anchor=(0.95, 0.5, 0.0), capabilities=("openable",)),
        _component("storage_slot", "storage_slot", face="interior", anchor=(0.5, 0.5, 0.5), node_type="fixed_object", capabilities=("place_target",), repeatable=True),
    ), storage=StorageTopology(kind="shelved", levels=4, columns=1, depth_cm=35.0, capacity_per_slot=8)),
    "cabinet": CompositionSpec(
        components=(
            _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="fixed_object"),
            _component("door", "door", face="front", anchor=(0.5, 0.5, 0.0), capabilities=("openable",), optional=True),
            _component("storage_slot", "storage_slot", face="interior", anchor=(0.5, 0.5, 0.5), node_type="fixed_object", capabilities=("place_target",), repeatable=True),
        ),
        storage=StorageTopology(kind="mixed", levels=3, columns=2, depth_cm=35.0, drawer_count=2, capacity_per_slot=8),
    ),
    "wardrobe": CompositionSpec(
        components=(
            _component("hinge", "hinge", face="front", anchor=(0.08, 0.5, 0.0), node_type="fixed_object"),
            _component("door", "door", face="front", anchor=(0.5, 0.5, 0.0), capabilities=("openable",), optional=True),
            _component("storage_slot", "storage_slot", face="interior", anchor=(0.5, 0.5, 0.5), node_type="fixed_object", capabilities=("place_target",), repeatable=True),
        ),
        storage=StorageTopology(kind="mixed", levels=4, columns=2, depth_cm=55.0, drawer_count=2, capacity_per_slot=8),
    ),
    "dresser": CompositionSpec(
        components=(
            _component("storage_slot", "storage_slot", face="interior", anchor=(0.5, 0.5, 0.5), node_type="fixed_object", capabilities=("place_target",), repeatable=True),
        ),
        storage=StorageTopology(kind="drawer", levels=3, columns=1, depth_cm=40.0, drawer_count=3, capacity_per_slot=8),
    ),
    "desk": CompositionSpec(
        components=(
            _component("storage_slot", "storage_slot", face="interior", anchor=(0.5, 0.5, 0.5), node_type="fixed_object", capabilities=("place_target",), repeatable=True),
        ),
        storage=StorageTopology(kind="mixed", levels=2, columns=1, depth_cm=42.0, drawer_count=2, capacity_per_slot=8),
    ),
    "drawer": CompositionSpec(components=(
        _component("drawer_slot", "storage_slot", face="interior", anchor=(0.5, 0.5, 0.5), node_type="fixed_object", capabilities=("place_target",)),
    )),
}


def composition_for(semantic_type: str) -> CompositionSpec:
    return DEFAULT_COMPOSITIONS.get(str(semantic_type or "").lower(), CompositionSpec())


def validate_composition_nodes(nodes: list[dict[str, Any]] | dict[str, dict[str, Any]]) -> list[str]:
    """Validate declared component references without requiring generated IDs."""
    values = list(nodes.values()) if isinstance(nodes, dict) else nodes
    by_id = {str(item.get("id")): item for item in values if isinstance(item, dict) and item.get("id")}
    issues: list[str] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("id") or "")
        composition = item.get("composition") or {}
        for component in composition.get("components") or []:
            if not isinstance(component, dict):
                issues.append(f"{node_id} has an invalid composition component")
                continue
            face = component.get("mount_face", "front")
            if face not in MOUNT_FACES:
                issues.append(f"{node_id} component {component.get('role', '')} has invalid mount face {face}")
        parent = str(item.get("component_of") or "")
        if parent and parent not in by_id:
            issues.append(f"component {node_id} references missing host {parent}")
        if parent and item.get("relation") not in {None, "component_of", "controls", "inside", "on"}:
            issues.append(f"component {node_id} has unsupported host relation {item.get('relation')}")
    return issues


def materialize_compositions(scene: dict[str, Any]) -> dict[str, Any]:
    """Expand declared compositions into runtime child nodes and edges.

    The operation is idempotent and mutates the supplied scene in place. A
    composition remains a declaration on the host node; generated children
    carry ``component_of`` and their local mount metadata for renderers.
    """
    from .assets.object_library import build_object_node

    nodes = scene.setdefault("nodes", [])
    if not isinstance(nodes, list):
        return scene
    by_id = {str(item.get("id")): item for item in nodes if isinstance(item, dict) and item.get("id")}
    edges = scene.setdefault("edges", [])
    if not isinstance(edges, list):
        edges = []
        scene["edges"] = edges

    def add_child(host_id: str, child_id: str, spec: dict[str, Any], *, role: str, index: int | None = None) -> None:
        if child_id in by_id:
            return
        semantic_type = str(spec.get("semantic_type") or "object")
        node = build_object_node(child_id, semantic_type, parent=host_id)
        node["node_type"] = str(spec.get("node_type") or node.get("node_type") or "fixed_object")
        node["component_of"] = host_id
        node["component_role"] = role
        node["composition_materialized"] = True
        node["mount_face"] = str(spec.get("mount_face") or "front")
        node["mount_anchor"] = list(spec.get("anchor") or (0.5, 0.5, 0.0))
        node["runtime_relation"] = "in"
        if semantic_type == "storage_slot":
            # A slot is a real placement volume, not only a visual divider.
            depth = float((composition.get("storage") or {}).get("depth_cm") or 30.0)
            levels = max(1, int((composition.get("storage") or {}).get("levels") or 1))
            columns = max(1, int((composition.get("storage") or {}).get("columns") or 1))
            node["interior_size_cm"] = [120.0 / columns, depth, 100.0 / levels]
            node["volume_grid_cm"] = 1.0
            storage = composition.get("storage") or {}
            node["max_capacity"] = int(storage.get("capacity_per_slot") or 8)
            node["states"]["capacity"] = node["max_capacity"]
            accepted = storage.get("accepted_capabilities") or []
            if accepted:
                node["requires_contained_capabilities"] = list(accepted)
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
            node["max_capacity"] = int((composition.get("storage") or {}).get("capacity_per_slot") or 8)
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
            "relation": "component_of",
            "edge_type": "object_edge",
            "category": "physical",
            "properties": {"component_role": role, "mount_face": node["mount_face"]},
        }
        if not any(
            str(edge.get("source_id") or "") == host_id
            and str(edge.get("target_id") or "") == child_id
            and str(edge.get("relation") or "") == "component_of"
            for edge in edges
            if isinstance(edge, dict)
        ):
            edges.append(component_edge)
        nodes.append(node)
        by_id[child_id] = node

    for host in list(nodes):
        if not isinstance(host, dict) or not host.get("id"):
            continue
        host_id = str(host["id"])
        # Revisit materialized root hosts to repair newly introduced
        # mechanical edges, but never recursively materialize a generated
        # component (for example, a drawer's own storage slot).
        if host.get("composition_materialized") and host.get("component_of"):
            continue
        composition = host.get("composition") or {}
        component_specs = composition.get("components") or []
        for spec in component_specs:
            if not isinstance(spec, dict):
                continue
            role = str(spec.get("role") or spec.get("semantic_type") or "component")
            if role == "storage_slot" and spec.get("repeatable"):
                continue
            child_id = f"{host_id}_{role}"
            add_child(host_id, child_id, spec, role=role)

        storage = composition.get("storage") or {}
        levels = max(1, int(storage.get("levels") or 1))
        columns = max(1, int(storage.get("columns") or 1))
        slot_spec = next((spec for spec in component_specs if isinstance(spec, dict) and spec.get("role") == "storage_slot"), None)
        if slot_spec is None and storage:
            slot_spec = {
                "role": "storage_slot",
                "semantic_type": str(storage.get("slot_semantic_type") or "storage_slot"),
                "node_type": "fixed_object",
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
                "node_type": "fixed_object",
                "mount_face": "front",
                "anchor": [(drawer_index + 0.5) / max(1, drawer_count), 0.15, 0.0],
            }
            add_child(host_id, drawer_id, drawer_spec, role="drawer", index=drawer_index)
        # Preserve the mechanical relationships between generated parts. The
        # containment edge says that both parts belong to the host; these
        # edges say how the parts move relative to one another.
        component_ids = {
            str(node.get("component_role")): str(node.get("id"))
            for node in nodes
            if isinstance(node, dict)
            and str(node.get("component_of") or "") == host_id
            and node.get("id")
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
        for node in nodes:
            if not isinstance(node, dict) or str(node.get("component_of") or "") != host_id:
                continue
            if str(node.get("component_role") or "") != "drawer":
                continue
            drawer_id = str(node.get("id") or "")
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
        if composition.get("components") or composition.get("storage"):
            host["composition_materialized"] = True
    return scene


__all__ = ["ComponentSpec", "CompositionSpec", "DEFAULT_COMPOSITIONS", "StorageTopology", "composition_for", "materialize_compositions", "validate_composition_nodes"]
