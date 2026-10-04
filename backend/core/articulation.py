"""Structure-edge backed part-tree views."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .transform import IDENTITY_TRANSFORM, Transform

JOINT_TYPES = frozenset({"fixed", "revolute", "continuous", "prismatic"})


@dataclass(frozen=True, slots=True)
class Link:
    id: str
    visual_ref: str | None = None
    collision_ref: str | None = None
    can_support: bool = False
    can_contain: bool = False
    max_items: int | None = None
    accepted_capabilities: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Joint:
    id: str
    parent_link: str
    child_link: str
    joint_type: str = "fixed"
    axis: tuple[float, float, float] = (0.0, 0.0, 1.0)
    origin: Transform = IDENTITY_TRANSFORM
    limits: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PartTree:
    root_id: str
    links: Mapping[str, Link]
    joints: Mapping[str, Joint]

    def children(self, link_id: str) -> tuple[str, ...]:
        return tuple(j.child_link for j in self.joints.values() if j.parent_link == link_id)

    def validate(self) -> tuple[str, ...]:
        issues: list[str] = []
        if self.root_id not in self.links:
            issues.append(f"missing root link: {self.root_id}")
        parent_by_child: dict[str, str] = {}
        for joint in self.joints.values():
            if joint.parent_link not in self.links or joint.child_link not in self.links:
                issues.append(f"joint {joint.id} references unknown link")
            if joint.child_link in parent_by_child:
                issues.append(f"link has multiple parents: {joint.child_link}")
            parent_by_child[joint.child_link] = joint.parent_link
            if joint.joint_type not in JOINT_TYPES:
                issues.append(f"unsupported joint type: {joint.joint_type}")
            if len(joint.axis) != 3:
                issues.append(f"joint axis must have three values: {joint.id}")
        if self.root_id in parent_by_child:
            issues.append("root link cannot have a parent")
        seen: set[str] = set()
        active: set[str] = set()

        def visit(link_id: str) -> None:
            if link_id in active:
                issues.append(f"structure cycle at link: {link_id}")
                return
            if link_id in seen:
                return
            active.add(link_id)
            for child in self.children(link_id):
                visit(child)
            active.remove(link_id)
            seen.add(link_id)

        if self.root_id in self.links:
            visit(self.root_id)
        for link_id in self.links:
            if link_id not in seen:
                issues.append(f"link is disconnected from root: {link_id}")
        return tuple(dict.fromkeys(issues))


def part_tree_from_edges(node_id: str, nodes: Iterable[Mapping[str, Any]], edges: Iterable[Mapping[str, Any]]) -> PartTree:
    node_map = {str(node.get("id")): node for node in nodes}
    links: dict[str, Link] = {}
    for item in node_map.values():
        owner = str(item.get("owner_id") or item.get("object_id") or node_id)
        if owner != node_id and str(item.get("id")) != node_id:
            continue
        link_id = str(item.get("link_id") or item.get("id"))
        links[link_id] = Link(
            id=link_id,
            visual_ref=item.get("visual_ref"),
            collision_ref=item.get("collision_ref"),
            can_support=bool(item.get("can_support")),
            can_contain=bool(item.get("can_contain")),
            max_items=item.get("max_items"),
            accepted_capabilities=tuple(str(x) for x in item.get("accepted_capabilities") or ()),
            metadata=dict(item.get("metadata") or {}),
        )
    links.setdefault(node_id, Link(node_id))
    joints: dict[str, Joint] = {}
    for edge in edges:
        if str(edge.get("relation") or "") != "structure":
            continue
        props = dict(edge.get("properties") or {})
        parent = str(props.get("parent") or edge.get("parent") or "")
        child = str(props.get("child") or edge.get("child") or "")
        if not parent or not child or parent not in links or child not in links:
            continue
        joint_id = str(edge.get("id") or f"{parent}->{child}")
        axis = tuple(float(x) for x in props.get("axis") or (0.0, 0.0, 1.0))
        joints[joint_id] = Joint(
            joint_id, parent, child, str(props.get("joint_type") or "fixed"),
            axis, Transform.from_dict(props.get("origin")), dict(props.get("limits") or {}),
        )
    roots = set(links) - {joint.child_link for joint in joints.values()}
    root = node_id if node_id in roots else sorted(roots)[0] if roots else node_id
    return PartTree(root, links, joints)


__all__ = ["JOINT_TYPES", "Joint", "Link", "PartTree", "part_tree_from_edges"]
