from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Union

from backend.core.state import DISCRETE_STATE_SPACE, normalize_discrete_value


MatrixValue = Union[int, str, None]


@dataclass(frozen=True)
class MatrixSnapshot:
    node_ids: tuple[str, ...]
    movable_node_ids: tuple[str, ...]
    state_columns: tuple[str, ...]
    state_matrix: tuple[tuple[MatrixValue, ...], ...]
    node_relation_matrix: tuple[tuple[int, ...], ...]
    human_events: tuple[bool, ...]


def scene_nodes(scene: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(scene.get("nodes"), list):
        return list(scene.get("nodes") or [])
    if isinstance(scene.get("node"), dict):
        return list((scene.get("node") or {}).values())
    return []


def scene_edges(scene: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(scene.get("edges"), list):
        return list(scene.get("edges") or [])
    if isinstance(scene.get("edge"), dict):
        return list((scene.get("edge") or {}).values())
    return []


def _node_type_map(scene: dict[str, Any]) -> dict[str, str]:
    return {
        str(node.get("id") or ""): str(node.get("node_type") or "").lower()
        for node in scene_nodes(scene)
        if node.get("id")
    }


def _is_movable(node_types: dict[str, str], node_id: str) -> bool:
    return node_types.get(node_id) == "movable_object"


def build_state_matrix(
    scene: dict[str, Any],
    state_columns: tuple[str, ...] = DISCRETE_STATE_SPACE,
) -> tuple[tuple[str, ...], tuple[tuple[MatrixValue, ...], ...]]:
    nodes = sorted([node for node in scene_nodes(scene) if node.get("id")], key=lambda node: str(node.get("id") or ""))
    node_ids = tuple(str(node.get("id")) for node in nodes)
    rows: list[tuple[MatrixValue, ...]] = []
    for node in nodes:
        states = node.get("states") or {}
        row = tuple(
            normalize_discrete_value(state_name, states.get(state_name)) if state_name in states else None
            for state_name in state_columns
        )
        rows.append(row)
    return node_ids, tuple(rows)


def build_node_relation_matrix(scene: dict[str, Any], node_ids: tuple[str, ...]) -> tuple[tuple[int, ...], ...]:
    index = {node_id: idx for idx, node_id in enumerate(node_ids)}
    node_types = _node_type_map(scene)
    matrix = [[0 for _ in node_ids] for _ in node_ids]
    for edge in scene_edges(scene):
        source = str(edge.get("source_id") or "")
        target = str(edge.get("target_id") or "")
        if not (_is_movable(node_types, source) or _is_movable(node_types, target)):
            continue
        if source in index and target in index:
            matrix[index[source]][index[target]] = 1
    return tuple(tuple(row) for row in matrix)


def build_human_event_vector(scene: dict[str, Any], expected_events: tuple[str, ...]) -> tuple[bool, ...]:
    expected_set = set(expected_events)
    progress: list[bool] = []
    current_key: tuple[str, str] | None = None
    current_ok = True
    logs = (scene.get("world_state") or {}).get("event_log") or []
    for item in logs:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "") != "human_event":
            continue
        event_id = str(item.get("event") or item.get("activity") or "")
        if expected_set and event_id not in expected_set:
            continue
        key = (str(item.get("actor") or ""), event_id)
        if key != current_key:
            current_key = key
            current_ok = True
        current_ok = current_ok and bool(item.get("ok", True))
        if bool(item.get("period_end", False)):
            progress.append(current_ok)
            current_key = None
            current_ok = True
    return tuple(progress)


def build_matrix_snapshot(scene: dict[str, Any], expected_human_events: tuple[str, ...] = ()) -> MatrixSnapshot:
    node_types = _node_type_map(scene)
    node_ids, state_matrix = build_state_matrix(scene)
    return MatrixSnapshot(
        node_ids=node_ids,
        movable_node_ids=tuple(node_id for node_id in node_ids if _is_movable(node_types, node_id)),
        state_columns=DISCRETE_STATE_SPACE,
        state_matrix=state_matrix,
        node_relation_matrix=build_node_relation_matrix(scene, node_ids),
        human_events=build_human_event_vector(scene, expected_human_events),
    )


def state_distance(current: MatrixSnapshot, baseline: MatrixSnapshot) -> float:
    baseline_index = {node_id: idx for idx, node_id in enumerate(baseline.node_ids)}
    comparable = 0
    different = 0
    for current_idx, node_id in enumerate(current.node_ids):
        baseline_idx = baseline_index.get(node_id)
        if baseline_idx is None:
            continue
        for col_idx, value in enumerate(current.state_matrix[current_idx]):
            expected = baseline.state_matrix[baseline_idx][col_idx]
            if value is None or expected is None:
                continue
            comparable += 1
            different += int(value != expected)
    return different / comparable if comparable else 0.0


def relation_distance(current: MatrixSnapshot, baseline: MatrixSnapshot) -> float:
    baseline_movable = set(baseline.movable_node_ids)
    movable_ids = tuple(node_id for node_id in current.movable_node_ids if node_id in baseline_movable)
    if not movable_ids:
        return 0.0
    current_index = {node_id: idx for idx, node_id in enumerate(current.node_ids)}
    baseline_index = {node_id: idx for idx, node_id in enumerate(baseline.node_ids)}
    comparable = 0
    different = 0
    for target in movable_ids:
        comparable += 1
        current_target_idx = current_index[target]
        baseline_target_idx = baseline_index[target]
        current_parent_vector = tuple(
            current.node_relation_matrix[source_idx][current_target_idx] for source_idx in range(len(current.node_ids))
        )
        baseline_parent_vector = tuple(
            baseline.node_relation_matrix[source_idx][baseline_target_idx] for source_idx in range(len(baseline.node_ids))
        )
        different += int(current_parent_vector != baseline_parent_vector)
    return different / comparable if comparable else 0.0


def human_event_success_rate(snapshot: MatrixSnapshot, previous: MatrixSnapshot | None = None) -> float:
    if not snapshot.human_events:
        return 1.0 if previous is None else human_event_success_rate(previous, None)
    if previous is not None and len(snapshot.human_events) == len(previous.human_events):
        return human_event_success_rate(previous, None)
    if previous is not None and len(snapshot.human_events) < len(previous.human_events):
        return human_event_success_rate(previous, None)
    return sum(1 for ok in snapshot.human_events if ok) / len(snapshot.human_events)


def _state_improvement_count(previous: MatrixSnapshot, current: MatrixSnapshot, baseline: MatrixSnapshot) -> int:
    current_index = {node_id: idx for idx, node_id in enumerate(current.node_ids)}
    baseline_index = {node_id: idx for idx, node_id in enumerate(baseline.node_ids)}
    improved = 0
    for previous_idx, node_id in enumerate(previous.node_ids):
        current_idx = current_index.get(node_id)
        baseline_idx = baseline_index.get(node_id)
        if current_idx is None or baseline_idx is None:
            continue
        for col_idx, previous_value in enumerate(previous.state_matrix[previous_idx]):
            current_value = current.state_matrix[current_idx][col_idx]
            baseline_value = baseline.state_matrix[baseline_idx][col_idx]
            if previous_value is None or current_value is None or baseline_value is None:
                continue
            if previous_value != baseline_value and current_value == baseline_value:
                improved += 1
    return improved


def _relation_improvement_count(previous: MatrixSnapshot, current: MatrixSnapshot, baseline: MatrixSnapshot) -> int:
    previous_index = {node_id: idx for idx, node_id in enumerate(previous.node_ids)}
    current_index = {node_id: idx for idx, node_id in enumerate(current.node_ids)}
    baseline_index = {node_id: idx for idx, node_id in enumerate(baseline.node_ids)}
    baseline_movable = set(baseline.movable_node_ids)
    movable_ids = tuple(
        node_id for node_id in previous.movable_node_ids if node_id in current_index and node_id in baseline_index and node_id in baseline_movable
    )
    improved = 0
    for target in movable_ids:
        previous_target_idx = previous_index[target]
        current_target_idx = current_index[target]
        baseline_target_idx = baseline_index[target]
        previous_parent_vector = tuple(
            previous.node_relation_matrix[source_idx][previous_target_idx] for source_idx in range(len(previous.node_ids))
        )
        current_parent_vector = tuple(
            current.node_relation_matrix[source_idx][current_target_idx] for source_idx in range(len(current.node_ids))
        )
        baseline_parent_vector = tuple(
            baseline.node_relation_matrix[source_idx][baseline_target_idx] for source_idx in range(len(baseline.node_ids))
        )
        if previous_parent_vector != baseline_parent_vector and current_parent_vector == baseline_parent_vector:
            improved += 1
    return improved


def robot_improvement_score(
    previous: MatrixSnapshot | None,
    current: MatrixSnapshot,
    baseline: MatrixSnapshot,
) -> dict[str, float]:
    if previous is None:
        return {
            "robot_score": 0.0,
            "robot_state_improvements": 0,
            "robot_spatial_improvements": 0,
        }
    state_improvements = _state_improvement_count(previous, current, baseline)
    spatial_improvements = _relation_improvement_count(previous, current, baseline)
    raw_score = state_improvements * 0.04 + spatial_improvements * 0.02
    return {
        "robot_score": round(min(1.0, raw_score), 4),
        "robot_state_improvements": state_improvements,
        "robot_spatial_improvements": spatial_improvements,
    }


def matrix_score(
    current: MatrixSnapshot,
    baseline: MatrixSnapshot,
    previous: MatrixSnapshot | None = None,
    robot_current: MatrixSnapshot | None = None,
) -> dict[str, float]:
    state_delta = state_distance(current, baseline)
    relation_delta = relation_distance(current, baseline)
    event_success = human_event_success_rate(current, previous)
    scores = {
        "state_score": round(1.0 - state_delta, 4),
        "spatial_score": round(1.0 - relation_delta, 4),
        "human_event_score": round(event_success, 4),
        "final_score": round((1.0 - state_delta) * 0.45 + (1.0 - relation_delta) * 0.35 + event_success * 0.20, 4),
    }
    scores.update(robot_improvement_score(previous, robot_current or current, baseline))
    return scores


__all__ = [
    "MatrixSnapshot",
    "build_human_event_vector",
    "build_matrix_snapshot",
    "build_node_relation_matrix",
    "build_state_matrix",
    "human_event_success_rate",
    "matrix_score",
    "relation_distance",
    "robot_improvement_score",
    "scene_edges",
    "scene_nodes",
    "state_distance",
]
