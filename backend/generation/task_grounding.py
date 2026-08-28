"""Ground domain task templates against one symbolic scene graph.

This module deliberately stops before PDDL.  A grounded task contains concrete
node ids; route feasibility is checked from graph connectivity, while action
ordering and state-transition feasibility remain the planner's job.
"""
from __future__ import annotations

from itertools import product
from typing import Any, Iterable


def _nodes(scene: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(node["id"]): node for node in scene.get("nodes", []) if node.get("id")}


def _rooms_graph(scene: dict[str, Any]) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for edge in scene.get("edges", []):
        if edge.get("relation") != "connected":
            continue
        a, b = str(edge.get("source_id")), str(edge.get("target_id"))
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set()).add(a)
    return graph


def _reachable(graph: dict[str, set[str]], start: str, goal: str) -> bool:
    if start == goal:
        return True
    seen = {start}
    queue = [start]
    while queue:
        current = queue.pop(0)
        for nxt in graph.get(current, ()):
            if nxt == goal:
                return True
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return False


def _parent(node: dict[str, Any]) -> str | None:
    value = node.get("parent")
    return str(value) if value else None


def _matches(node: dict[str, Any], query: dict[str, Any]) -> bool:
    if "semantic_type" in query and node.get("semantic_type") != query["semantic_type"]:
        return False
    if "family" in query and node.get("family") != query["family"]:
        return False
    if "portable" in query:
        portable = node.get("portable", node.get("is_movable", node.get("node_type") == "movable_object"))
        if bool(portable) != bool(query["portable"]):
            return False
    states = node.get("states") or {}
    for key, expected in (query.get("state") or {}).items():
        if states.get(key) != expected:
            return False
    capability = query.get("capability")
    if capability and capability not in set(node.get("capabilities") or []):
        return False
    return True


def resolve_query(scene: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    """Return node ids matching one parameter specification."""
    query = spec.get("object_query") or spec.get("node_query") or {}
    nodes = _nodes(scene)
    return [node_id for node_id, node in nodes.items() if _matches(node, query)]


def ground_template(scene: dict[str, Any], template: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve all parameter combinations and emit normalized task instances."""
    parameters = template.get("parameters") or {}
    names = list(parameters)
    choices = [resolve_query(scene, parameters[name]) for name in names]
    if not names or any(not values for values in choices):
        return []
    nodes = _nodes(scene)
    graph = _rooms_graph(scene)
    result = []
    for values in product(*choices):
        binding = dict(zip(names, values))
        locations = [_parent(nodes[node_id]) for node_id in values if _parent(nodes[node_id])]
        if locations and any(not _reachable(graph, locations[0], location) for location in locations[1:]):
            continue
        result.append({
            "task_id": template.get("task_id"),
            "family": template.get("family"),
            "binding": binding,
            "requirements": template.get("requirements") or {},
            "goal": template.get("goal") or [],
            "pddl": template.get("pddl") or {},
            "status": "grounded",
        })
    return result


def ground_templates(scene: dict[str, Any], templates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    instances: list[dict[str, Any]] = []
    for template in templates:
        instances.extend(ground_template(scene, template))
    return instances


__all__ = ["ground_template", "ground_templates", "resolve_query"]
