from __future__ import annotations

from typing import Any

from backend.runtime.agent.decision import ranked_rule_candidates
from backend.runtime.scene_utils import node, parent_of, room_of


RULE_AGENT_MODES = ("nearest_repair", "human_blocking_first")


def room_distance(scene: dict[str, Any], start_room: str, target_room: str) -> int:
    if not start_room or not target_room:
        return 999
    if start_room == target_room:
        return 0
    graph: dict[str, set[str]] = {}
    for edge in scene.get("edges") or []:
        relation = str(edge.get("relation") or "").lower()
        if relation not in {"connected", "connected_to", "next_to", "neighbour"}:
            continue
        source = str(edge.get("source_id") or "")
        target = str(edge.get("target_id") or "")
        if source and target:
            graph.setdefault(source, set()).add(target)
            graph.setdefault(target, set()).add(source)
    queue: list[tuple[str, int]] = [(start_room, 0)]
    seen = {start_room}
    while queue:
        room_id, distance = queue.pop(0)
        for neighbor in sorted(graph.get(room_id, ())):
            if neighbor in seen:
                continue
            if neighbor == target_room:
                return distance + 1
            seen.add(neighbor)
            queue.append((neighbor, distance + 1))
    return 999


def candidate_room(scene: dict[str, Any], candidate: dict[str, Any]) -> str:
    target_id = str(candidate.get("target") or "")
    target_node = node(scene, target_id) or {}
    if str(target_node.get("node_type") or "") == "room":
        return target_id
    return room_of(scene, target_id)


def rule_rank_lookup(
    candidates: list[dict[str, Any]],
    observation: dict[str, Any],
    baseline: dict[str, Any],
    active_goal: dict[str, Any] | None,
    robot_id: str,
) -> dict[int, int]:
    ranked = ranked_rule_candidates(candidates, observation, baseline, active_goal, robot_id)
    return {id(candidate): score for score, _index, candidate in ranked}


def direct_repair_priority(
    scene: dict[str, Any],
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> int:
    action = str(candidate.get("action") or "")
    target_id = str(candidate.get("target") or "")
    object_id = str(candidate.get("object") or target_id)
    target = node(scene, target_id) or {}
    obj = node(scene, object_id) or {}
    baseline_obj = node(baseline, object_id) or {}
    states = target.get("states") or {}
    obj_states = obj.get("states") or {}
    if action == "brush" and states.get("is_dirty") is True:
        return 100
    if action == "close" and states.get("is_open") is True:
        return 90
    if action == "fold" and obj_states.get("folded") is False:
        return 85
    if action == "dump":
        return 80
    if action == "place" and parent_of(baseline, object_id) == target_id:
        return 75
    if action == "pick" and parent_of(scene, object_id) != parent_of(baseline, object_id):
        return 70
    if action == "move":
        return 50
    if action == "open":
        return 20
    return 0


def case_action_match_score(scene: dict[str, Any], case: dict[str, Any], candidate: dict[str, Any]) -> int:
    if str(case.get("status") or "") not in {"", "open"} or not bool(case.get("recoverable", False)):
        return 0
    action = str(candidate.get("action") or "")
    target_id = str(candidate.get("target") or "")
    object_id = str(candidate.get("object") or target_id)
    ids = {target_id, object_id}
    case_targets = {str(item) for item in case.get("blocking_target_ids") or [] if str(item)}
    for key in ("target", "parent"):
        value = str(case.get(key) or "")
        if value:
            case_targets.add(value)
    if ids & case_targets:
        return 120
    target = node(scene, target_id) or {}
    obj = node(scene, object_id) or {}
    semantics = {str(case.get("semantic_type") or "")}
    semantics.update(str(item) for item in case.get("semantic_types") or [] if str(item))
    semantics.discard("")
    if semantics and (
        str(target.get("semantic_type") or "") in semantics
        or str(obj.get("semantic_type") or "") in semantics
    ):
        if action in {"pick", "place", "brush", "close", "open", "press", "fold", "dump"}:
            return 95
    case_room = str(case.get("room") or "")
    if case_room and action == "move" and candidate_room(scene, candidate) == case_room:
        return 85
    if case_room and candidate_room(scene, candidate) == case_room:
        return 65
    return 0


def best_human_blocking_match(
    scene: dict[str, Any],
    blocking_cases: list[dict[str, Any]],
    candidate: dict[str, Any],
) -> int:
    scores = [case_action_match_score(scene, case, candidate) for case in blocking_cases]
    return max(scores) if scores else 0


def choose_rule_action(
    *,
    agent_mode: str,
    candidates: list[dict[str, Any]],
    observation: dict[str, Any],
    scene: dict[str, Any],
    baseline: dict[str, Any],
    active_goal: dict[str, Any] | None,
    blocking_cases: list[dict[str, Any]],
    robot_id: str,
) -> dict[str, Any]:
    if not candidates:
        raise ValueError("no legal action candidates")
    rank_by_id = rule_rank_lookup(candidates, observation, baseline, active_goal, robot_id)
    robot_room = room_of(scene, robot_id)

    if agent_mode == "human_blocking_first":
        scored = []
        for index, candidate in enumerate(candidates):
            scored.append(
                (
                    best_human_blocking_match(scene, blocking_cases, candidate),
                    direct_repair_priority(scene, baseline, candidate),
                    rank_by_id.get(id(candidate), 0),
                    -room_distance(scene, robot_room, candidate_room(scene, candidate)),
                    -index,
                    candidate,
                )
            )
        selected = max(scored, key=lambda item: item[:5])[-1]
        return {**selected, "reason": "human_blocking_first: prioritize open recoverable blocking cases"}

    if agent_mode == "nearest_repair":
        scored = []
        for index, candidate in enumerate(candidates):
            scored.append(
                (
                    direct_repair_priority(scene, baseline, candidate),
                    -room_distance(scene, robot_room, candidate_room(scene, candidate)),
                    rank_by_id.get(id(candidate), 0),
                    -index,
                    candidate,
                )
            )
        selected = max(scored, key=lambda item: item[:4])[-1]
        return {**selected, "reason": "nearest_repair: prioritize nearby direct repairs"}

    raise ValueError(f"unsupported rule baseline: {agent_mode}")
