"""Relationship mutations with Edge as the only source of truth."""

from __future__ import annotations

from typing import Any

from .model import Edge, POSITION_RELATIONS


def move_relationship(state: dict[str, Any], node_id: str, parent_id: str, relation: str) -> None:
    """Replace one node's position edge and rebuild disposable indices."""
    graph = state.get("_graph")
    if graph is not None:
        graph.move_node(str(node_id), str(parent_id), str(relation))
        return

    edges = state.setdefault("edges", [])
    edges[:] = [
        edge for edge in edges
        if not (
            str(edge.get("target_id") or "") == str(node_id)
            and str(edge.get("relation") or "").lower() in POSITION_RELATIONS
        )
    ]
    edges.append(Edge(str(parent_id), str(node_id), str(relation), {"canonical": True}).to_dict())
    state.setdefault("parent_of", {})[str(node_id)] = str(parent_id)
    state.setdefault("relation_of", {})[str(node_id)] = str(relation)


__all__ = ["move_relationship"]
