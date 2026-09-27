"""Single mutation pipeline for actions, rules, and systems."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable

from .actions import apply_action_schema
from .world_graph import WorldGraph


@dataclass(frozen=True)
class WorldDelta:
    state_changes: tuple[dict[str, Any], ...] = ()
    edges_added: tuple[dict[str, Any], ...] = ()
    edges_removed: tuple[dict[str, Any], ...] = ()
    events: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_changes": copy.deepcopy(list(self.state_changes)),
            "edges_added": copy.deepcopy(list(self.edges_added)),
            "edges_removed": copy.deepcopy(list(self.edges_removed)),
            "events": copy.deepcopy(list(self.events)),
        }


@dataclass(frozen=True)
class MutationResult:
    ok: bool
    failures: tuple[str, ...] = ()
    delta: WorldDelta = field(default_factory=WorldDelta)


def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
    return (str(edge.get("source_id") or ""), str(edge.get("relation") or ""), str(edge.get("target_id") or ""))


class MutationPipeline:
    def __init__(self, graph: WorldGraph):
        self.graph = graph

    def _capture(self) -> dict[str, Any]:
        return {
            "states": {node_id: copy.deepcopy(item.get("states") or {}) for node_id, item in self.graph.nodes.items()},
            "edges": {_edge_key(edge): copy.deepcopy(edge) for edge in self.graph.edges},
            "event_count": len(self.graph.world_state.get("event_log") or []),
        }

    def _delta(self, before: dict[str, Any]) -> WorldDelta:
        state_changes: list[dict[str, Any]] = []
        before_states = before["states"]
        for node_id in sorted(set(before_states) | set(self.graph.nodes)):
            old = before_states.get(node_id, {})
            new = (self.graph.nodes.get(node_id) or {}).get("states") or {}
            for state_name in sorted(set(old) | set(new)):
                if old.get(state_name) != new.get(state_name):
                    state_changes.append({"node_id": node_id, "state": state_name, "before": old.get(state_name), "after": new.get(state_name)})
        after_edges = {_edge_key(edge): copy.deepcopy(edge) for edge in self.graph.edges}
        before_edges = before["edges"]
        events = (self.graph.world_state.get("event_log") or [])[before["event_count"]:]
        return WorldDelta(
            state_changes=tuple(state_changes),
            edges_added=tuple(after_edges[key] for key in sorted(after_edges.keys() - before_edges.keys())),
            edges_removed=tuple(before_edges[key] for key in sorted(before_edges.keys() - after_edges.keys())),
            events=tuple(copy.deepcopy(events)),
        )

    def apply_action(self, action: dict[str, Any], *, step: int = 0) -> MutationResult:
        before = self._capture()
        failures = tuple(apply_action_schema(self.graph.state_for_rules(), action, step=step))
        if failures:
            return MutationResult(False, failures)
        self.graph.commit_relationship_indices()
        return MutationResult(True, delta=self._delta(before))

    def run_system(self, operation: Callable[[dict[str, Any]], Any]) -> WorldDelta:
        before = self._capture()
        operation(self.graph.state_for_rules())
        self.graph.commit_relationship_indices()
        return self._delta(before)


__all__ = ["MutationPipeline", "MutationResult", "WorldDelta"]
