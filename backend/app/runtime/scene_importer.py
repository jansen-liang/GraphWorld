from __future__ import annotations

from dataclasses import dataclass, field
import copy
import json
from pathlib import Path
import re
from typing import Any

from backend.runtime.scene_schema import validate_canonical_scene


def normalize_legacy_scene(source_json: dict[str, Any]) -> dict[str, Any]:
    """Upgrade stored pre-canonical snapshots at the adapter boundary.

    Scene versions are immutable historical data, so migration happens on
    read.  The runtime only receives the small canonical envelope it owns:
    stable editor IDs, one of the four Node types, and graph-owned relations.
    """
    source = copy.deepcopy(source_json)
    source["schema_version"] = 2
    source["id_namespace"] = "editor"
    nodes = source.get("nodes") or []
    layout_doors = (source.get("layout") or {}).get("doors") or {}
    canonical_types = {"floor", "room", "object", "agent"}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or node.get("editor_id") or "")
        node["id"] = node_id
        node["editor_id"] = node_id
        raw_type = str(node.get("node_type") or "").lower()
        # Perform the one-time wire migration here. Runtime code must only
        # consume semantic_type and canonical capability declarations.
        semantic = str(node.get("semantic_type") or node.get("object_type") or "").lower()
        node["semantic_type"] = semantic
        node.pop("object_type", None)
        if raw_type not in canonical_types:
            if semantic == "floor" or raw_type in {"floor", "level"}:
                node["node_type"] = "floor"
            elif semantic == "room" or raw_type in {"room", "space", "area"}:
                node["node_type"] = "room"
            elif semantic in {"agent", "robot", "human", "npc"} or raw_type in {"robot", "human", "npc", "agent"}:
                node["node_type"] = "agent"
            else:
                node["node_type"] = "object"
        node.pop("type", None)
        # Legacy support/container declarations are normalized once at the
        # import boundary. A root support surface and a component receptacle
        # are deliberately distinct capabilities.
        capabilities = list(dict.fromkeys(str(item) for item in (node.get("capabilities") or ())))
        old_surface = node.pop("surface_size_cm", None) or node.pop("support_surface_cm", None)
        old_grid = node.pop("surface_grid_cm", None) or node.pop("support_grid_cm", None)
        can_support = bool(node.pop("can_support", False))
        if old_surface is not None:
            can_support = True
            node["surface_spec"] = {
                "width_cm": float(old_surface[0]),
                "depth_cm": float(old_surface[1]),
                "grid_size_cm": float(old_grid or 1.0),
            }
        if can_support:
            node["can_support"] = True
            if "support_surface" not in capabilities:
                capabilities.append("support_surface")
        old_capacity = node.pop("max_capacity", None)
        old_capacity = old_capacity if old_capacity is not None else node.pop("capacity_per_slot", None)
        old_accepted = node.pop("requires_contained_capabilities", None)
        old_accepted = old_accepted if old_accepted is not None else node.pop("accepted_capabilities", None)
        can_contain = bool(node.pop("can_contain", False)) or old_capacity is not None or old_accepted is not None
        if can_contain:
            node["can_contain"] = True
            if old_capacity is not None:
                node["max_items"] = int(old_capacity)
            if old_accepted is not None:
                node["accepted_capabilities"] = [str(item) for item in old_accepted]
            if "receptacle" not in capabilities:
                capabilities.append("receptacle")
        if capabilities:
            node["capabilities"] = capabilities
        node.pop("parent", None)
        node.pop("child", None)
        node.setdefault("role", "root")
        # Room-to-room doors are graph Nodes.  Older generated records kept
        # the room pair only in layout.doors; migrate that declaration into
        # the door Node once at import time.
        if str(node.get("semantic_type") or "").lower() == "door" and node_id in layout_doors:
            layout_door = layout_doors.get(node_id) or {}
            if isinstance(layout_door, dict):
                room_pair = [str(layout_door.get("room_a_id") or ""), str(layout_door.get("room_b_id") or "")]
                if all(room_pair):
                    node["connected_rooms"] = room_pair
    return source


@dataclass(frozen=True)
class ImportedSceneNode:
    node_key: str
    node_type: str = ""
    semantic_type: str = ""
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ImportedSceneEdge:
    source_key: str
    target_key: str
    relation: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ImportedScene:
    scene_id: str
    scene_version_id: str
    version: int
    name: str
    domain: str
    description: str
    source_json: dict[str, Any]
    graph_summary: dict[str, Any]
    nodes: list[ImportedSceneNode]
    edges: list[ImportedSceneEdge]


def _slug(raw: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_:-]+", "_", raw.strip())
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "scene"


def infer_scene_id(source_json: dict[str, Any], fallback: str = "scene") -> str:
    raw = source_json.get("scene_name") or source_json.get("id") or source_json.get("name") or fallback
    return _slug(str(raw))


def infer_domain(scene_id: str) -> str:
    parts = [part for part in scene_id.split("_") if part and part not in {"simple"}]
    if not parts:
        return ""
    return parts[0]


def make_scene_version_id(scene_id: str, version: int) -> str:
    return f"{scene_id}__v{int(version)}"


def graph_summary(source_json: dict[str, Any]) -> dict[str, Any]:
    nodes = [node for node in source_json.get("nodes") or [] if isinstance(node, dict)]
    edges = [edge for edge in source_json.get("edges") or [] if isinstance(edge, dict)]
    def node_type(node: dict[str, Any]) -> str:
        return str(node.get("node_type") or node.get("type") or "")

    def semantic_type(node: dict[str, Any]) -> str:
        return str(node.get("semantic_type") or "")

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "floor_count": sum(1 for node in nodes if node_type(node) == "floor" or semantic_type(node) == "floor"),
        "room_count": sum(1 for node in nodes if node_type(node) == "room" or semantic_type(node) == "room"),
        "agent_count": sum(1 for node in nodes if node_type(node) == "agent" or semantic_type(node) in {"agent", "robot", "human"}),
        "npc_count": sum(1 for node in nodes if node_type(node) == "agent" and semantic_type(node) in {"human", "npc"}),
        "robot_count": sum(1 for node in nodes if node_type(node) == "agent" and semantic_type(node) == "robot"),
        "object_count": sum(
            1
            for node in nodes
            if node_type(node) == "object"
        ),
        "scene_name_cn": source_json.get("scene_name_cn") or "",
        "world_state": copy.deepcopy(source_json.get("world_state") or {}),
        "variant_profile": copy.deepcopy(source_json.get("variant_profile") or {}),
        "variant_axes": copy.deepcopy(source_json.get("variant_axes") or {}),
        "web_seed": copy.deepcopy(source_json.get("web_seed") or {}),
    }


def import_scene(
    source_json: dict[str, Any],
    *,
    scene_id: str | None = None,
    version: int = 1,
    description: str = "",
) -> ImportedScene:
    # Import is the sole migration boundary: legacy payloads are upgraded
    # once, then validated and persisted as canonical scene JSON.
    source = validate_canonical_scene(normalize_legacy_scene(source_json))
    resolved_scene_id = _slug(scene_id) if scene_id else infer_scene_id(source)
    resolved_version = int(version)
    nodes: list[ImportedSceneNode] = []
    for raw_node in source.get("nodes") or []:
        if not isinstance(raw_node, dict):
            continue
        node_key = str(raw_node.get("id") or "").strip()
        if not node_key:
            continue
        nodes.append(
            ImportedSceneNode(
                node_key=str(raw_node.get("editor_id") or node_key),
                node_type=str(raw_node.get("node_type") or raw_node.get("type") or ""),
                semantic_type=str(raw_node.get("semantic_type") or ""),
                properties=copy.deepcopy(raw_node),
            )
        )

    edges: list[ImportedSceneEdge] = []
    for raw_edge in source.get("edges") or []:
        if not isinstance(raw_edge, dict):
            continue
        source_key = str(raw_edge.get("source_id") or raw_edge.get("source") or "").strip()
        target_key = str(raw_edge.get("target_id") or raw_edge.get("target") or "").strip()
        relation = str(raw_edge.get("relation") or raw_edge.get("edge_type") or "").strip()
        if not source_key or not target_key or not relation:
            continue
        edges.append(
            ImportedSceneEdge(
                source_key=source_key,
                target_key=target_key,
                relation=relation,
                properties=copy.deepcopy(raw_edge),
            )
        )

    return ImportedScene(
        scene_id=resolved_scene_id,
        scene_version_id=make_scene_version_id(resolved_scene_id, resolved_version),
        version=resolved_version,
        name=str(source.get("scene_name") or resolved_scene_id),
        domain=infer_domain(resolved_scene_id),
        description=description,
        source_json=source,
        graph_summary=graph_summary(source),
        nodes=nodes,
        edges=edges,
    )


def load_scene_file(path: str | Path, *, version: int = 1, description: str = "") -> ImportedScene:
    scene_path = Path(path)
    with scene_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    fallback_scene_id = scene_path.stem
    return import_scene(payload, scene_id=fallback_scene_id, version=version, description=description)
