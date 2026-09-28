"""Canonical graph store with Edge-owned relationships."""

from __future__ import annotations

import copy
from typing import Any, Iterable

from .animation import visual_cues
from .model import Edge, Node, POSITION_RELATIONS, ROOM_CONNECTIVITY_RELATIONS
from .states import DISCRETE_STATE_SPACE
from .transitions import transition_log


def _values(scene: dict[str, Any], plural: str, singular: str) -> list[dict[str, Any]]:
    if isinstance(scene.get(plural), list):
        return copy.deepcopy(scene.get(plural) or [])
    if isinstance(scene.get(singular), dict):
        return copy.deepcopy(list((scene.get(singular) or {}).values()))
    return []


class WorldGraph:
    """One mutable world graph; relationship indices are disposable caches."""

    def __init__(self, scene: dict[str, Any]):
        self.scene_name = str(scene.get("scene_name") or "scene")
        core_keys = {"scene_name", "nodes", "node", "edges", "edge", "world_state", "processes"}
        self.metadata = copy.deepcopy({key: value for key, value in scene.items() if key not in core_keys})
        raw_nodes = _values(scene, "nodes", "node")
        self.nodes = {
            model.id: model.to_dict()
            for raw in raw_nodes
            if (model := Node.from_dict(raw)).id
        }
        self.edges = [
            model.to_dict()
            for raw in _values(scene, "edges", "edge")
            if (model := Edge.from_dict(raw)).source_id and model.target_id and model.relation
        ]
        self.world_state = copy.deepcopy(scene.get("world_state") or {})
        self._initialize_world_state()
        self._migrate_dynamic_state_fields()
        self._validate_node_states()
        self._import_legacy_relationships(raw_nodes)
        self.refresh_indices()

    def _initialize_world_state(self) -> None:
        defaults = {
            "step": 0,
            "event_log": [],
            "blocking_cases": [],
            "temperature": "comfortable",
            "weather": "sunny",
            "day_phase": "day",
            "room_temperature": {},
            "room_humidity": {},
            "natural_change_counters": {},
            "natural_dirt_enabled": True,
            "processes": [],
        }
        for key, value in defaults.items():
            self.world_state.setdefault(key, copy.deepcopy(value))

    def _migrate_dynamic_state_fields(self) -> None:
        for item in self.nodes.values():
            if str(item.get("semantic_type") or "") != "sink":
                continue
            states = item.setdefault("states", {})
            if "has_water" not in states:
                states["has_water"] = bool(float(states.get("fill_level") or 0.0) > 0.0)
            states.pop("fill_level", None)
            states.pop("is_full", None)

    def _validate_node_states(self) -> None:
        allowed = set(DISCRETE_STATE_SPACE)
        invalid = [
            f"{node_id}.{state_name}"
            for node_id, node in sorted(self.nodes.items())
            for state_name in sorted(set(node.get("states") or {}) - allowed)
        ]
        if invalid:
            preview = ", ".join(invalid[:20])
            suffix = "" if len(invalid) <= 20 else f", ... ({len(invalid)} total)"
            raise ValueError(f"states outside DISCRETE_STATE_SPACE: {preview}{suffix}")

    def _import_legacy_relationships(self, raw_nodes: Iterable[dict[str, Any]]) -> None:
        for raw in raw_nodes:
            node_id = str(raw.get("id") or "")
            parent_id = str(raw.get("parent") or raw.get("floor_id") or "")
            if not node_id or not parent_id or parent_id not in self.nodes:
                continue
            relation = str(raw.get("runtime_relation") or ("at" if raw.get("node_type") in {"robot", "human"} else "in"))
            self._replace_position_edge(node_id, parent_id, relation)
        # Legacy inventories represented a held relation. They are imported
        # only when the child did not already declare a concrete parent.
        positioned = {str(edge.get("target_id") or "") for edge in self.edges if str(edge.get("relation") or "") in POSITION_RELATIONS}
        for raw in raw_nodes:
            actor_id = str(raw.get("id") or "")
            for item_id in raw.get("inventory") or ():
                item_id = str(item_id)
                if actor_id in self.nodes and item_id in self.nodes and item_id not in positioned:
                    self._replace_position_edge(item_id, actor_id, "held_by")

    def _replace_position_edge(self, node_id: str, parent_id: str, relation: str) -> None:
        self.edges[:] = [
            edge for edge in self.edges
            if not (str(edge.get("target_id") or "") == node_id and str(edge.get("relation") or "") in POSITION_RELATIONS)
        ]
        self.edges.append(Edge(parent_id, node_id, relation, {"canonical": True}).to_dict())

    def refresh_indices(self) -> None:
        parent_of: dict[str, str] = {}
        relation_of: dict[str, str] = {}
        for edge in self.edges:
            relation = str(edge.get("relation") or "").lower()
            source = str(edge.get("source_id") or "")
            target = str(edge.get("target_id") or "")
            if relation in POSITION_RELATIONS and source in self.nodes and target in self.nodes:
                parent_of[target] = source
                relation_of[target] = relation
        current_parent = getattr(self, "parent_of", {})
        current_relation = getattr(self, "relation_of", {})
        current_parent.clear()
        current_parent.update(parent_of)
        current_relation.clear()
        current_relation.update(relation_of)
        self.parent_of = current_parent
        self.relation_of = current_relation
        room_of = {node_id: self.room_for(node_id) for node_id in self.nodes}
        current_rooms = getattr(self, "room_of", {})
        current_rooms.clear()
        current_rooms.update(room_of)
        self.room_of = current_rooms
        controls = [edge for edge in self.edges if str(edge.get("relation") or "").lower() == "controls"]
        rooms = [edge for edge in self.edges if str(edge.get("relation") or "").lower() in ROOM_CONNECTIVITY_RELATIONS]
        current_controls = getattr(self, "control_edges", [])
        current_room_edges = getattr(self, "room_edges", [])
        current_controls[:] = controls
        current_room_edges[:] = rooms
        self.control_edges = current_controls
        self.room_edges = current_room_edges

    def commit_relationship_indices(self) -> None:
        """Rebuild disposable relationship indices from canonical edges."""
        for node in self.nodes.values():
            node.pop("parent", None)
            node.pop("runtime_relation", None)
            node.pop("inventory", None)
        self.refresh_indices()

    def room_for(self, node_id: str) -> str:
        current = str(node_id)
        seen: set[str] = set()
        while current and current not in seen:
            seen.add(current)
            item = self.nodes.get(current) or {}
            if str(item.get("node_type") or "") == "room":
                return current
            current = self.parent_of.get(current, "")
        return ""

    def state_for_rules(self) -> dict[str, Any]:
        return {
            "_graph": self,
            "nodes": self.nodes,
            "edges": self.edges,
            "world_state": self.world_state,
            "parent_of": self.parent_of,
            "relation_of": self.relation_of,
            "room_of": self.room_of,
            "control_edges": self.control_edges,
            "room_edges": self.room_edges,
            "processes": self.world_state.setdefault("processes", []),
        }

    def node(self, node_id: str) -> dict[str, Any]:
        return self.nodes.get(str(node_id)) or {}

    def nodes_by_semantic(self, semantic_type: str, room_id: str = "") -> list[str]:
        return [
            node_id for node_id, item in self.nodes.items()
            if str(item.get("semantic_type") or "") == semantic_type
            and (not room_id or self.room_of.get(node_id) == room_id)
        ]

    def adjacent_rooms(self, room_id: str) -> set[str]:
        adjacent: set[str] = set()
        for edge in self.room_edges:
            source = str(edge.get("source_id") or "")
            target = str(edge.get("target_id") or "")
            if source == room_id:
                adjacent.add(target)
            if target == room_id:
                adjacent.add(source)
        return adjacent

    def target_reachable_from_room(self, target_id: str, room_id: str) -> bool:
        target = self.node(target_id)
        return bool(room_id) and (
            self.room_of.get(target_id) == room_id
            or room_id in {str(item) for item in target.get("connected_rooms") or []}
        )

    def has_structural_door_between(self, room_a: str, room_b: str) -> bool:
        pair = {room_a, room_b}
        return any(
            str(item.get("door_kind") or "") == "structural"
            and pair.issubset({str(room_id) for room_id in item.get("connected_rooms") or []})
            for item in self.nodes.values()
        )

    def log(self, event_type: str, detail: str, **payload: Any) -> None:
        event = {"step": int(self.world_state.get("step") or 0), "type": event_type, "detail": detail}
        event.update(payload)
        self.world_state.setdefault("event_log", []).append(event)

    def move_node(self, node_id: str, parent_id: str, relation: str) -> None:
        if node_id not in self.nodes or parent_id not in self.nodes:
            return
        self._replace_position_edge(str(node_id), str(parent_id), str(relation))
        self.refresh_indices()

    def set_node_states(self, node_id: str, **updates: Any) -> None:
        if invalid := sorted(set(updates) - set(DISCRETE_STATE_SPACE)):
            raise ValueError(f"{node_id} received states outside DISCRETE_STATE_SPACE: {invalid}")
        if node_id in self.nodes:
            self.nodes[node_id].setdefault("states", {}).update(updates)

    def held_by(self, agent_id: str) -> str:
        return next((
            node_id for node_id, parent_id in self.parent_of.items()
            if parent_id == agent_id and str(self.relation_of.get(node_id) or "").startswith("held_by")
        ), "")

    def sync_runtime_edges(self) -> None:
        self.commit_relationship_indices()

    def to_scene(self) -> dict[str, Any]:
        self.commit_relationship_indices()
        self.world_state["transition_log"] = transition_log(self.world_state.get("event_log") or [])
        snapshots = []
        for item in self.nodes.values():
            snapshot = copy.deepcopy(item)
            if cues := visual_cues(snapshot):
                snapshot["visual_cues"] = cues
            snapshots.append(snapshot)
        return {
            **copy.deepcopy(self.metadata),
            "scene_name": self.scene_name,
            "world_state": copy.deepcopy(self.world_state),
            "nodes": snapshots,
            "edges": copy.deepcopy(self.edges),
            "processes": copy.deepcopy(self.world_state.get("processes", [])),
        }


__all__ = ["WorldGraph"]
