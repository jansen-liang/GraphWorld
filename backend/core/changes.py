"""Atomic world change protocol shared by actions, rules and processes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping
from uuid import uuid4


CHANGE_TYPES = frozenset({
    "node_added", "node_updated", "node_removed", "edge_added", "edge_updated", "edge_removed",
    "state_changed", "joint_state_changed", "process_started", "process_updated",
    "process_finished", "process_interrupted",
})


@dataclass(frozen=True, slots=True)
class JointState:
    joint_id: str
    position: float | tuple[float, ...] = 0.0
    velocity: float | tuple[float, ...] = 0.0
    target: float | tuple[float, ...] | None = None
    motion_status: str = "static"

    def to_dict(self) -> dict[str, Any]:
        return {
            "joint_id": self.joint_id,
            "position": self.position,
            "velocity": self.velocity,
            "target": self.target,
            "motion_status": self.motion_status,
        }


@dataclass(frozen=True, slots=True)
class WorldSnapshot:
    session_id: str
    scene_id: str
    revision: int
    time_seconds: float
    nodes: tuple[Mapping[str, Any], ...] = ()
    edges: tuple[Mapping[str, Any], ...] = ()
    processes: tuple[Mapping[str, Any], ...] = ()
    events: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "scene_id": self.scene_id,
            "revision": self.revision,
            "time_seconds": self.time_seconds,
            "nodes": [dict(item) for item in self.nodes],
            "edges": [dict(item) for item in self.edges],
            "processes": [dict(item) for item in self.processes],
            "events": [dict(item) for item in self.events],
        }


@dataclass(frozen=True, slots=True)
class WorldChange:
    change_type: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    source: str = ""
    change_id: str = field(default_factory=lambda: f"chg_{uuid4().hex}")

    def __post_init__(self) -> None:
        if self.change_type not in CHANGE_TYPES:
            raise ValueError(f"unsupported world change: {self.change_type}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_type": self.change_type,
            "change_id": self.change_id,
            "source": self.source,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True, slots=True)
class WorldDelta:
    session_id: str = ""
    base_revision: int = 0
    revision: int = 0
    time_seconds: float = 0.0
    changes: tuple[WorldChange, ...] = ()
    nodes_added: tuple[Mapping[str, Any], ...] = ()
    nodes_removed: tuple[str, ...] = ()
    edges_removed: tuple[Any, ...] = ()
    # These named projections remain for existing callers while the wire
    # protocol converges on `changes`. They are derived by runtime commits.
    state_changes: tuple[Mapping[str, Any], ...] = ()
    edges_added: tuple[Mapping[str, Any], ...] = ()
    events: tuple[Mapping[str, Any], ...] = ()

    def canonical_changes(self) -> tuple[WorldChange, ...]:
        changes: list[WorldChange] = list(self.changes)
        for item in self.nodes_added:
            changes.append(WorldChange("node_added", dict(item)))
        for item in self.state_changes:
            changes.append(WorldChange("state_changed", dict(item)))
        for item in self.edges_added:
            changes.append(WorldChange("edge_added", dict(item)))
        for item in self.edges_removed:
            changes.append(WorldChange("edge_removed", dict(item) if isinstance(item, Mapping) else {"edge_id": item}))
        for node_id in self.nodes_removed:
            changes.append(WorldChange("node_removed", {"node_id": node_id}))
        return tuple(changes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "base_revision": self.base_revision,
            "revision": self.revision,
            "time_seconds": self.time_seconds,
            "changes": [change.to_dict() for change in self.canonical_changes()],
            "nodes_added": [dict(item) for item in self.nodes_added],
            "nodes_removed": list(self.nodes_removed),
            "edges_removed": list(self.edges_removed),
            "state_changes": [dict(item) for item in self.state_changes],
            "edges_added": [dict(item) for item in self.edges_added],
            "events": [dict(item) for item in self.events],
        }


__all__ = ["CHANGE_TYPES", "JointState", "WorldChange", "WorldDelta", "WorldSnapshot"]
