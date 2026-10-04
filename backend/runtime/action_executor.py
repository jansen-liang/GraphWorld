"""Runtime action execution and atomic world transactions."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, TYPE_CHECKING

from backend.core.action import Action
from backend.core.changes import WorldChange, WorldDelta
from backend.adapter.animation.cues import visual_cues
from backend.runtime.action_engine import apply_action_schema

if TYPE_CHECKING:
    from .world import World


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    failures: tuple[str, ...] = ()
    delta: WorldDelta = field(default_factory=WorldDelta)


def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(edge.get("source_id") or ""),
        str(edge.get("source_link_id") or ""),
        str(edge.get("relation") or ""),
        str(edge.get("target_id") or ""),
        str(edge.get("target_link_id") or ""),
    )


class WorldTransaction:
    """Atomic change boundary used by actions and runtime systems."""

    def __init__(self, world: "World"):
        self.world = world
        self.before = {
            "nodes": copy.deepcopy(world.nodes),
            "edges": copy.deepcopy(world.edges),
            "world_state": copy.deepcopy(world.world_state),
        }
        self.closed = False

    def rollback(self) -> None:
        if self.closed:
            return
        self.world.nodes.clear()
        self.world.nodes.update(copy.deepcopy(self.before["nodes"]))
        self.world.edges[:] = copy.deepcopy(self.before["edges"])
        self.world.world_state.clear()
        self.world.world_state.update(copy.deepcopy(self.before["world_state"]))
        self.world.refresh_indices()
        self.closed = True

    # EffectContext implementation. Declarative effects use these methods so
    # they cannot bypass the transaction boundary.
    def node(self, node_id: str) -> dict[str, Any]:
        return self.world.node(node_id)

    def has_edge(self, source_id: str, target_id: str, relation: str) -> bool:
        return any(
            str(edge.get("source_id")) == str(source_id)
            and str(edge.get("target_id")) == str(target_id)
            and str(edge.get("relation")) == str(relation)
            for edge in self.world.edges
        )

    def set_state(self, node_id: str, state: str, value: Any) -> None:
        self.world.node(node_id).setdefault("states", {})[state] = copy.deepcopy(value)

    def add_edge(self, source_id: str, target_id: str, relation: str, properties: Mapping[str, Any] | None = None) -> None:
        from backend.core.edge import Edge

        self.world.edges.append(Edge(str(source_id), str(target_id), str(relation), dict(properties or {})).to_dict())

    def remove_edge(self, source_id: str, target_id: str, relation: str) -> None:
        self.world.edges[:] = [
            edge for edge in self.world.edges
            if not (str(edge.get("source_id")) == str(source_id) and str(edge.get("target_id")) == str(target_id) and str(edge.get("relation")) == str(relation))
        ]

    def emit(self, event: Mapping[str, Any]) -> None:
        self.world.world_state.setdefault("event_log", []).append(copy.deepcopy(dict(event)))

    def commit(self) -> WorldDelta:
        if self.closed:
            raise RuntimeError("transaction is already closed")
        self.world.commit_relationship_indices()
        before_nodes = self.before["nodes"]
        nodes_added = tuple(
            copy.deepcopy(self.world.nodes[node_id])
            for node_id in sorted(set(self.world.nodes) - set(before_nodes))
        )
        nodes_removed = tuple(sorted(set(before_nodes) - set(self.world.nodes)))
        state_changes: list[dict[str, Any]] = []
        joint_changes: list[WorldChange] = []
        node_updates: list[WorldChange] = []
        for node_id in sorted(set(before_nodes) | set(self.world.nodes)):
            old = (before_nodes.get(node_id) or {}).get("states") or {}
            new = (self.world.nodes.get(node_id) or {}).get("states") or {}
            for state_name in sorted(set(old) | set(new)):
                if old.get(state_name) != new.get(state_name):
                    state_changes.append({"node_id": node_id, "state": state_name, "before": old.get(state_name), "after": new.get(state_name)})
            old_cues = visual_cues(before_nodes.get(node_id) or {})
            new_cues = visual_cues(self.world.nodes.get(node_id) or {})
            if old_cues != new_cues:
                node_updates.append(WorldChange(
                    "node_updated",
                    {"node_id": node_id, "visual_cues": new_cues},
                    source="runtime",
                ))
            old_node = before_nodes.get(node_id) or {}
            new_node = self.world.nodes.get(node_id) or {}
            # Placement and visibility are semantic runtime outputs too. They
            # must travel in the delta, otherwise the frontend applies the
            # new edge but keeps rendering the old transform.
            transform_keys = (
                "world_transform", "placement_transform", "storage_mode",
                "visibility", "collision_enabled", "support_surface",
                "placement_anchor", "placement_volume_anchor", "placement_volume_target",
                "request_queue", "requested_room",
            )
            changed_transform = {
                key: copy.deepcopy(new_node[key])
                for key in transform_keys
                if old_node.get(key) != new_node.get(key) and key in new_node
            }
            if "world_transform" in changed_transform:
                changed_transform["transform_space"] = "graphworld_z_up"
                changed_transform["transform_origin"] = "runtime"
            if changed_transform:
                node_updates.append(WorldChange(
                    "node_updated",
                    {"node_id": node_id, **changed_transform},
                    source="runtime",
                ))
            old_joints = self.world._joint_states_for(
                before_nodes.get(node_id) or {}, nodes=before_nodes, edges=self.before["edges"],
            )
            new_joints = self.world._joint_states_for(
                self.world.nodes.get(node_id) or {},
            )
            for joint_id in sorted(set(old_joints) | set(new_joints)):
                if old_joints.get(joint_id) != new_joints.get(joint_id):
                    joint_changes.append(WorldChange(
                        "joint_state_changed",
                        {
                            "node_id": node_id,
                            "joint_id": joint_id,
                            "before": copy.deepcopy(old_joints.get(joint_id)),
                            "after": copy.deepcopy(new_joints.get(joint_id)),
                        },
                        source="runtime",
                    ))
        before_edges = {_edge_key(edge): edge for edge in self.before["edges"]}
        after_edges = {_edge_key(edge): copy.deepcopy(edge) for edge in self.world.edges}
        old_events = self.before["world_state"].get("event_log") or []
        new_events = self.world.world_state.get("event_log") or []
        self.closed = True
        return WorldDelta(
            changes=tuple([*joint_changes, *node_updates]),
            nodes_added=nodes_added,
            state_changes=tuple(state_changes),
            edges_added=tuple(after_edges[key] for key in sorted(after_edges.keys() - before_edges.keys())),
            edges_removed=tuple(copy.deepcopy(before_edges[key]) for key in sorted(before_edges.keys() - after_edges.keys())),
            events=tuple(copy.deepcopy(new_events[len(old_events):])),
            nodes_removed=nodes_removed,
        )


class ActionExecutor:
    """Validate and execute canonical actions against one runtime world."""

    def __init__(self, world: "World"):
        self.world = world

    def execute(self, action: Action | Mapping[str, Any], *, step: int = 0) -> ActionResult:
        if isinstance(action, Action):
            action = action.to_dict()
        transaction = WorldTransaction(self.world)
        try:
            failures = tuple(apply_action_schema(self.world.state_for_rules(), action, step=step))
            if failures:
                transaction.rollback()
                return ActionResult(False, failures)
            return ActionResult(True, delta=transaction.commit())
        except Exception:
            transaction.rollback()
            raise

    def execute_definition(self, definition, bindings: Mapping[str, str], *, step: int = 0) -> ActionResult:
        """Execute a declarative ActionDefinition atomically."""
        transaction = WorldTransaction(self.world)
        try:
            failures = tuple(
                failure
                for requirement in definition.preconditions
                if (failure := requirement.check(transaction, bindings))
            )
            if failures:
                transaction.rollback()
                return ActionResult(False, failures)
            for effect in definition.effects:
                effect.apply(transaction, bindings)
            return ActionResult(True, delta=transaction.commit())
        except Exception:
            transaction.rollback()
            raise

    def run(self, operation: Callable[[dict[str, Any]], Any]) -> WorldDelta:
        transaction = WorldTransaction(self.world)
        try:
            operation(self.world.state_for_rules())
            return transaction.commit()
        except Exception:
            transaction.rollback()
            raise


__all__ = ["ActionExecutor", "ActionResult", "WorldDelta", "WorldTransaction"]
