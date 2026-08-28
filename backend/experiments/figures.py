from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from backend.runtime.eval import build_matrix_snapshot


ACTION_CODES = {
    "move": 1,
    "pick": 2,
    "place": 3,
    "open": 4,
    "close": 5,
    "press": 6,
    "brush": 7,
    "fold": 8,
    "dump": 9,
}


def matrix_figure(scene: dict[str, Any], expected: tuple[str, ...], *, kind: str) -> plt.Figure:
    snapshot = build_matrix_snapshot(scene, expected)
    if kind == "state":
        data = []
        for row in snapshot.state_matrix:
            encoded = []
            for value in row:
                if value is None:
                    encoded.append(-1)
                elif isinstance(value, str):
                    encoded.append(0.5)
                else:
                    encoded.append(int(value))
            data = [*data, encoded]
        fig_width = max(7, len(snapshot.state_columns) * 0.55)
        fig_height = max(5, len(snapshot.node_ids) * 0.18)
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        image = ax.imshow(data, aspect="auto", vmin=-1, vmax=1, cmap="viridis")
        ax.set_xticks(range(len(snapshot.state_columns)))
        ax.set_xticklabels(snapshot.state_columns, rotation=90, fontsize=6)
        ax.set_yticks(range(len(snapshot.node_ids)))
        ax.set_yticklabels(snapshot.node_ids, fontsize=5)
        ax.set_title("state_matrix")
        fig.colorbar(image, ax=ax, fraction=0.018, pad=0.01)
    else:
        data = snapshot.node_relation_matrix
        size = len(snapshot.node_ids)
        fig_size = max(6, min(18, size * 0.22))
        fig, ax = plt.subplots(figsize=(fig_size, fig_size))
        ax.imshow(data, aspect="equal", vmin=0, vmax=1, cmap="Greys")
        ax.set_xticks(range(size))
        ax.set_xticklabels(snapshot.node_ids, rotation=90, fontsize=4)
        ax.set_yticks(range(size))
        ax.set_yticklabels(snapshot.node_ids, fontsize=4)
        ax.set_title("spatial_matrix")
    fig.tight_layout()
    return fig


def save_step_matrices(
    snapshot: Any,
    *,
    step: int,
    output_dir: Path,
) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"step_{step:04d}.json"
    payload = {
        "step": step,
        "node_ids": list(snapshot.node_ids),
        "movable_node_ids": list(snapshot.movable_node_ids),
        "state_columns": list(snapshot.state_columns),
        "state_matrix": [list(row) for row in snapshot.state_matrix],
        "node_relation_matrix": [list(row) for row in snapshot.node_relation_matrix],
        "human_events": list(snapshot.human_events),
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(out_path)


def build_room_index(scene: dict[str, Any]) -> dict[str, int]:
    rooms = sorted(
        str(item.get("id") or "")
        for item in scene.get("nodes") or []
        if str(item.get("node_type") or "") == "room" and str(item.get("id") or "")
    )
    return {room_id: index for index, room_id in enumerate(rooms)}


def build_trajectory_figure(
    replay_steps: list[dict[str, Any]],
    room_index_map: dict[str, int],
    *,
    kind: str,
) -> plt.Figure:
    xs = [int(step.get("episode_step") or index) for index, step in enumerate(replay_steps)]
    fig, ax = plt.subplots(figsize=(12, 4.5))
    if kind == "action":
        ys = [
            ACTION_CODES.get(str((step.get("action") or {}).get("action") or ""), -1)
            for step in replay_steps
        ]
        ax.plot(xs, ys, marker="o", markersize=3, linewidth=1.2, color="#1565c0")
        ax.set_yticks(list(ACTION_CODES.values()))
        ax.set_yticklabels(list(ACTION_CODES.keys()))
        ax.set_ylabel("action")
        ax.set_title("action_timeline")
    else:
        ys = [
            room_index_map.get(str((step.get("robot_state") or {}).get("room_id") or ""), -1)
            for step in replay_steps
        ]
        ax.plot(xs, ys, marker="o", markersize=3, linewidth=1.2, color="#2e7d32")
        ordered_rooms = sorted(room_index_map.items(), key=lambda item: item[1])
        ax.set_yticks([index for _, index in ordered_rooms])
        ax.set_yticklabels([room_id for room_id, _ in ordered_rooms])
        ax.set_ylabel("room")
        ax.set_title("room_timeline")
    ax.set_xlabel("step")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    return fig
