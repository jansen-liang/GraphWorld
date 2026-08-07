from __future__ import annotations

import argparse
import contextlib
import copy
import csv
import io
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from tensorboard.compat.proto import event_pb2, summary_pb2, tensor_pb2, tensor_shape_pb2, types_pb2
from tensorboard.summary.writer.event_file_writer import EventFileWriter
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.assets.npc_library import get_default_npcs, get_event_spec, planned_activity
from backend.runtime.agent import (
    candidate_actions,
    fallback_choose_action,
    held_object,
    llm_choose_action,
    llm_choose_reactive_action,
    llm_review_goal,
    perceive,
    reflect,
    remember,
)
from backend.runtime.agent.decision import (
    HOUSE_RULES as ENGINE_HOUSE_RULES,
    _compact_candidates as engine_compact_candidates,
    _compact_nodes as engine_compact_nodes,
    _high_level_options as engine_high_level_options,
    _initial_context as engine_initial_context,
    _node_index as engine_node_index,
    _ranked_prompt_candidates as engine_ranked_prompt_candidates,
    _robot_state as engine_robot_state,
    _scene_node_index as engine_scene_node_index,
    critical_state_deviations as engine_critical_state_deviations,
    parse_action_index as engine_parse_action_index,
    relevant_skills_for_nodes as engine_relevant_skills_for_nodes,
)
from backend.runtime.agent.yuling import yuling_agent, DeployLoop
from backend.runtime.agent.efe_agent.efe_core import EfeLoop

# Prompt builders to align yuling_agent's prompt with llm_choose_action.
_ENGINE_BUILDERS: dict[str, Any] = {
    "_node_index":            engine_node_index,
    "_scene_node_index":      engine_scene_node_index,
    "_robot_state":           engine_robot_state,
    "_initial_context":       engine_initial_context,
    "_high_level_options":    engine_high_level_options,
    "_compact_nodes":         engine_compact_nodes,
    "_compact_candidates":    engine_compact_candidates,
    "critical_state_deviations": engine_critical_state_deviations,
    "relevant_skills_for_nodes": engine_relevant_skills_for_nodes,
    "HOUSE_RULES":            ENGINE_HOUSE_RULES,
    "_ranked_prompt_candidates": engine_ranked_prompt_candidates,
    "parse_action_index":     engine_parse_action_index,
}
from backend.runtime.engine import Orchestrator
from backend.runtime.eval import build_matrix_snapshot, matrix_score
from backend.tools.agent import llm_query, resolved_agent_config

from backend.runtime.agent.retrospective_memory import (
    RecentEventsBuffer,
    record_events_from_step_result,
    update_segment_starts,
)


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
SCENE_DIR = DATA_DIR / "sg_output" / "simple_graph"
SCENE_PATH = SCENE_DIR / "simple_home_1f.json"
LEGACY_REPLAY_DIR = DATA_DIR / "replay_logs"
TENSORBOARD_DIR = DATA_DIR / "tensorboard"
EXPERIMENT_DIR = DATA_DIR / "experiments"

SCORE_KEYS = ("final_score", "state_score", "spatial_score", "human_event_score")
INSTANT_SCORE_KEYS = ("instant_final_score", "instant_state_score", "instant_spatial_score")
AVG_SCORE_KEYS = ("avg_final_score", "avg_state_score", "avg_spatial_score")
CLOTH_SEMANTICS = {"clothes", "towel", "blanket"}
HOSPITAL_RETURN_SKILLS = {
    "replenish_prescription_sheet",
    "replenish_medicine_box",
    "return_refrigerated_medicine",
    "clean_medical_waste",
    "collect_dirty_linen",
    "restock_clean_sheet",
    "return_wheelchair",
}
HOSPITAL_CLEAN_SKILLS = {"clean_waiting_area", "clean_exam_bed"}
HOSPITAL_SKILL_BY_SEMANTIC = {
    "prescription_sheet": "replenish_prescription_sheet",
    "medicine_box": "replenish_medicine_box",
    "refrigerated_medicine": "return_refrigerated_medicine",
    "medical_waste": "clean_medical_waste",
    "wheelchair": "return_wheelchair",
}
HOSPITAL_MANAGED_SEMANTICS = {
    *HOSPITAL_SKILL_BY_SEMANTIC.keys(),
    "bed_sheet",
}
HOSPITAL_SKILL_PRIORITY = {
    "replenish_prescription_sheet": 0,
    "return_refrigerated_medicine": 1,
    "replenish_medicine_box": 2,
    "restock_clean_sheet": 3,
    "clean_medical_waste": 4,
    "collect_dirty_linen": 5,
    "return_wheelchair": 6,
    "clean_waiting_area": 7,
    "clean_exam_bed": 8,
}
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


def _blocking_targets_satisfied(case: dict[str, Any], scene: dict[str, Any]) -> bool:
    nodes = {str(node.get("id") or ""): node for node in scene.get("nodes") or [] if node.get("id")}
    parent_of = {str(node.get("id") or ""): str(node.get("parent") or "") for node in scene.get("nodes") or [] if node.get("id")}
    target = str(case.get("target") or "")
    parent = str(case.get("parent") or "")
    states = dict(case.get("states") or {})
    room = str(case.get("room") or "")
    relation_not = str(case.get("relation_not") or "")
    semantic_type = str(case.get("semantic_type") or "")
    semantic_types = {str(item) for item in case.get("semantic_types") or [] if str(item)}

    def node_matches(node_id: str) -> bool:
        node = nodes.get(node_id) or {}
        if not node:
            return False
        if target and node_id != target:
            return False
        if semantic_type and str(node.get("semantic_type") or "") != semantic_type:
            return False
        if semantic_types and str(node.get("semantic_type") or "") not in semantic_types:
            return False
        if parent and parent_of.get(node_id) != parent:
            return False
        if room and room_of(scene, node_id) != room:
            return False
        if relation_not and relation_of(scene, node_id) == relation_not:
            return False
        node_states = node.get("states") or {}
        return all(node_states.get(key) == value for key, value in states.items())

    target_ids = [str(item) for item in case.get("blocking_target_ids") or [] if str(item)]
    if target_ids:
        return any(node_matches(node_id) for node_id in target_ids)

    if semantic_types:
        available = {
            str(node.get("semantic_type") or "")
            for node_id, node in nodes.items()
            if not room or room_of(scene, node_id) == room
        }
        return semantic_types.issubset(available)

    return any(node_matches(node_id) for node_id in nodes)


def update_blocking_cases(
    cases: list[dict[str, Any]],
    current_scene: dict[str, Any],
    actions: list[dict[str, Any]],
    step: int,
) -> None:
    primary_action = actions[0] if actions else {}
    resolution_action = f"{primary_action.get('action', '')}:{primary_action.get('target', '')}"
    for case in cases:
        if str(case.get("status") or "") != "open":
            continue
        if not bool(case.get("recoverable", False)):
            continue
        if _blocking_targets_satisfied(case, current_scene):
            case["status"] = "resolved"
            case["resolved_step"] = step
            case["resolved_by_robot"] = bool(actions)
            case["resolution_action"] = resolution_action


def finalize_blocking_case_outcomes(
    cases: list[dict[str, Any]],
    human_events: list[dict[str, Any]],
) -> None:
    event_outcomes = {str(item.get("event") or ""): bool(item.get("ok", False)) for item in human_events if item.get("event")}
    for case in cases:
        if str(case.get("status") or "") != "resolved":
            continue
        event_id = str(case.get("event_id") or "")
        if event_id in event_outcomes and event_outcomes[event_id]:
            case["status"] = "closed_success"


class TensorBoardWriter:
    def __init__(self, log_dir: Path | str) -> None:
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._writer = EventFileWriter(str(self._log_dir))
        self._disabled = False
        self._warned = False

    def _disable(self, exc: Exception) -> None:
        if self._disabled:
            return
        self._disabled = True
        if not self._warned:
            tqdm.write(f"tensorboard disabled for {self._log_dir}: {exc}")
            self._warned = True
        with contextlib.suppress(Exception):
            self._writer.close()

    def _add_event(self, event: event_pb2.Event) -> None:
        if self._disabled:
            return
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            self._writer.add_event(event)
        except Exception as exc:
            self._disable(exc)

    def add_scalar(self, tag: str, value: float, step: int) -> None:
        summary = summary_pb2.Summary(
            value=[summary_pb2.Summary.Value(tag=tag, simple_value=float(value))]
        )
        self._add_event(event_pb2.Event(wall_time=time.time(), step=int(step), summary=summary))

    def add_text(self, tag: str, text: str, step: int = 0) -> None:
        metadata = summary_pb2.SummaryMetadata(
            plugin_data=summary_pb2.SummaryMetadata.PluginData(plugin_name="text")
        )
        tensor = tensor_pb2.TensorProto(
            dtype=types_pb2.DT_STRING,
            string_val=[text.encode("utf-8")],
            tensor_shape=tensor_shape_pb2.TensorShapeProto(dim=[tensor_shape_pb2.TensorShapeProto.Dim(size=1)]),
        )
        summary = summary_pb2.Summary(
            value=[summary_pb2.Summary.Value(tag=tag, metadata=metadata, tensor=tensor)]
        )
        self._add_event(event_pb2.Event(wall_time=time.time(), step=int(step), summary=summary))

    def add_figure(self, tag: str, fig: plt.Figure, step: int = 0) -> None:
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=140)
        image = summary_pb2.Summary.Image(
            encoded_image_string=buffer.getvalue(),
            height=int(fig.bbox.bounds[3]),
            width=int(fig.bbox.bounds[2]),
            colorspace=4,
        )
        summary = summary_pb2.Summary(value=[summary_pb2.Summary.Value(tag=tag, image=image)])
        self._add_event(event_pb2.Event(wall_time=time.time(), step=int(step), summary=summary))

    def flush(self) -> None:
        if self._disabled:
            return
        try:
            self._writer.flush()
        except Exception as exc:
            self._disable(exc)

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._writer.close()


def _slug(value: str | None) -> str:
    text = str(value or "").strip().lower()
    cleaned: list[str] = []
    for ch in text:
        cleaned.append(ch if ch.isalnum() else "_")
    slug = "".join(cleaned).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "unknown"


def canonical_model_label(agent_model: str | None) -> str:
    model = str(agent_model or "").strip()
    if not model:
        return "unknown_model"
    if model == "npc_only_baseline":
        return "npc_only_baseline"
    return _slug(model.replace(":", "-").replace(".", "_"))


def canonical_run_group(
    scene_id: str,
    experiment_type: str,
    agent_model: str | None,
    steps: int,
    robots: int,
    humans: int,
    schedule_mode: str = "fixed",
    schedule_seed: int = 0,
) -> str:
    parts = [
        f"exp_{_slug(experiment_type)}",
        f"steps_{int(steps)}",
        f"robots_{int(robots)}",
        f"humans_{int(humans)}",
        f"model_{canonical_model_label(agent_model)}",
    ]
    if str(schedule_mode or "fixed") != "fixed":
        parts.append(f"schedule_{_slug(schedule_mode)}")
        parts.append(f"seed_{int(schedule_seed)}")
    return "__".join(
        parts
    )


def canonical_experiment_group(
    scene_id: str,
    steps: int,
    robots: int,
    humans: int,
    agent_model: str | None,
    schedule_mode: str = "fixed",
    schedule_seed: int = 0,
) -> str:
    parts = [
        f"steps_{int(steps)}",
        f"robots_{int(robots)}",
        f"humans_{int(humans)}",
        f"model_{canonical_model_label(agent_model)}",
    ]
    if str(schedule_mode or "fixed") != "fixed":
        parts.append(f"schedule_{_slug(schedule_mode)}")
        parts.append(f"seed_{int(schedule_seed)}")
    return "__".join(parts)


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]


def clean_old_outputs() -> None:
    for folder in (TENSORBOARD_DIR, EXPERIMENT_DIR):
        folder.mkdir(parents=True, exist_ok=True)
        for item in folder.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)
    if LEGACY_REPLAY_DIR.exists():
        for item in LEGACY_REPLAY_DIR.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            LEGACY_REPLAY_DIR.rmdir()


def node(scene: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    for item in scene.get("nodes") or []:
        if item.get("id") == node_id:
            return item
    return None


def add_child(scene: dict[str, Any], parent_id: str, child_id: str) -> None:
    parent = node(scene, parent_id)
    if not parent:
        return
    children = parent.setdefault("child", [])
    if child_id not in children:
        children.append(child_id)


def ensure_node(scene: dict[str, Any], item: dict[str, Any]) -> None:
    existing = node(scene, str(item["id"]))
    if existing:
        existing.update({key: value for key, value in item.items() if key not in {"child"}})
        if item.get("child") is not None:
            existing["child"] = item["child"]
    else:
        scene.setdefault("nodes", []).append(item)
    parent_id = str(item.get("parent") or "")
    if parent_id:
        add_child(scene, parent_id, str(item["id"]))


def ensure_edge(scene: dict[str, Any], source_id: str, target_id: str, relation: str) -> None:
    for edge in scene.setdefault("edges", []):
        if edge.get("source_id") == source_id and edge.get("target_id") == target_id and edge.get("relation") == relation:
            return
    scene["edges"].append(
        {
            "source_id": source_id,
            "target_id": target_id,
            "edge_type": "runtime_seed_edge",
            "relation": relation,
            "category": "runtime_seed",
            "properties": {},
        }
    )


def robot_ids(robot_count: int) -> tuple[str, ...]:
    return tuple(f"robot_{index:02d}" for index in range(1, max(0, int(robot_count)) + 1))


def human_ids(human_count: int) -> tuple[str, ...]:
    count = max(0, int(human_count))
    return tuple("human_resident" if index == 1 else f"human_resident_{index:02d}" for index in range(1, count + 1))


def scene_type(scene: dict[str, Any]) -> str:
    name = str(scene.get("scene_name") or "")
    if "hospital" in name:
        return "hospital"
    if "supermarket" in name:
        return "supermarket"
    if "office" in name:
        return "office"
    if "factory" in name:
        return "factory"
    return "home"


def actor_specs_for_scene(scene: dict[str, Any], human_count: int) -> list[dict[str, str]]:
    if scene_type(scene) == "hospital":
        defaults = get_default_npcs("hospital")
        return defaults[: max(0, int(human_count))]
    if scene_type(scene) == "supermarket":
        defaults = get_default_npcs("supermarket")
        return defaults[: max(0, int(human_count))]
    if scene_type(scene) == "office":
        defaults = get_default_npcs("office")
        return defaults[: max(0, int(human_count))]
    if scene_type(scene) == "factory":
        defaults = get_default_npcs("factory")
        return defaults[: max(0, int(human_count))]
    return [
        {
            "id": human_id,
            "name": "resident",
            "name_cn": "resident",
            "role": "resident",
            "parent": "bed_bedroom",
            "room": "bedroom",
            "activity": "sleeping",
            "persona": "weekday_office_worker",
        }
        for human_id in human_ids(human_count)
    ]


def prepare_scene(raw_scene: dict[str, Any], robot_count: int, human_count: int) -> dict[str, Any]:
    scene = copy.deepcopy(raw_scene)
    scene.setdefault("world_state", {}).setdefault("step", 0)
    scene["world_state"].setdefault("time_min", 360)
    scene["world_state"].setdefault("minutes_per_step", 10)
    scene["world_state"].setdefault("day", 1)
    if scene_type(scene) in {"home", "supermarket", "office", "factory"}:
        for spec in actor_specs_for_scene(scene, human_count):
            human_id = str(spec["id"])
            parent_id = str(spec.get("parent") or "outside_home")
            ensure_node(
                scene,
                {
                    "id": human_id,
                    "name": spec.get("name", "human"),
                    "name_cn": spec.get("name_cn", spec.get("name", "human")),
                    "node_type": "human",
                    "semantic_type": "human",
                    "role": spec.get("role", "resident"),
                    "persona": spec.get("persona", ""),
                    "current_activity": spec.get("activity", ""),
                    "states": {},
                    "parent": parent_id,
                    "child": [],
                    "interactive_actions": [],
                },
            )
            ensure_edge(scene, parent_id, human_id, "at")
    for robot_id in robot_ids(robot_count):
        if scene_type(scene) == "hospital":
            robot_parent = "lobby"
        elif scene_type(scene) == "supermarket":
            robot_parent = "entrance"
        elif scene_type(scene) in {"office", "factory"}:
            robot_parent = "entrance"
        else:
            robot_parent = "living_room"
        ensure_node(
            scene,
            {
                "id": robot_id,
                "name": "robot",
                "name_cn": "robot",
                "node_type": "robot",
                "semantic_type": "robot",
                "states": {},
                "parent": robot_parent,
                "child": [],
                "interactive_actions": [],
            },
        )
        ensure_edge(scene, robot_parent, robot_id, "at")
    support_nodes = []
    if scene_type(scene) == "home":
        support_nodes.extend([
        {
            "id": "garbage_station_outside_home",
            "name": "garbage station",
            "name_cn": "垃圾处理站",
            "node_type": "fixed_object",
            "semantic_type": "garbage_station",
            "states": {},
            "parent": "outside_home",
            "child": [],
            "interactive_actions": ["move", "dump"],
        },
        {
            "id": "trash_bin_living_room",
            "name": "trash bin",
            "name_cn": "trash bin",
            "node_type": "movable_object",
            "semantic_type": "trash_bin",
            "states": {"is_dirty": False},
            "parent": "living_room",
            "child": [],
            "interactive_actions": ["pick", "place"],
            "max_capacity": 3,
        },
        {
            "id": "food_living_room",
            "name": "food",
            "name_cn": "food",
            "node_type": "movable_object",
            "semantic_type": "food",
            "states": {"is_cooked": True, "is_rotten": False},
            "parent": "fridge_kitchen",
            "child": [],
            "interactive_actions": ["pick", "place"],
        },
        {
            "id": "plate_living_room",
            "name": "plate",
            "name_cn": "plate",
            "node_type": "movable_object",
            "semantic_type": "plate",
            "states": {"is_dirty": False},
            "parent": "dishwasher_kitchen",
            "child": [],
            "interactive_actions": ["pick", "place", "brush"],
        },
        {
            "id": "cup_living_room",
            "name": "cup",
            "name_cn": "cup",
            "node_type": "movable_object",
            "semantic_type": "cup",
            "states": {"is_dirty": False, "is_wet": False},
            "parent": "dishwasher_kitchen",
            "child": [],
            "interactive_actions": ["pick", "place", "brush"],
        },
        ])
    for item in support_nodes:
        ensure_node(scene, item)
        ensure_edge(scene, str(item["parent"]), str(item["id"]), "in")
    for item in scene.get("nodes") or []:
        if str(item.get("semantic_type") or "") == "sink":
            actions = item.setdefault("interactive_actions", [])
            if "dump" not in actions:
                actions.append("dump")
    return scene


def prepare_home_scene(raw_scene: dict[str, Any], robot_count: int, human_count: int) -> dict[str, Any]:
    return prepare_scene(raw_scene, robot_count=robot_count, human_count=human_count)


def planned_event_for_actor(scene: dict[str, Any], actor: dict[str, Any], step: int) -> str:
    world = scene.get("world_state") or {}
    schedule_mode = str(world.get("schedule_mode") or "fixed")
    elapsed_minute = step * int(world.get("minutes_per_step") or 10)
    start_minute = int(world.get("time_min") or 0)
    absolute_minute = start_minute + elapsed_minute
    if schedule_mode == "fixed":
        minute = absolute_minute
        day = int(world.get("day") or 1)
    else:
        minute = absolute_minute % (24 * 60)
        day = int(world.get("day") or 1) + absolute_minute // (24 * 60)
    schedule_seed = int(world.get("schedule_seed") or 0)
    role = str(actor.get("role") or (actor.get("states") or {}).get("role") or "resident")
    _, _, activity = planned_activity(
        role,
        minute,
        day,
        schedule_mode=schedule_mode,
        schedule_seed=schedule_seed,
        actor_id=str(actor.get("id") or ""),
    )
    return activity


def planned_event_for_step(scene: dict[str, Any], step: int) -> str:
    actors = [node for node in scene.get("nodes") or [] if str(node.get("node_type") or "") == "human"]
    if not actors:
        return ""
    return planned_event_for_actor(scene, actors[0], step)


def planned_events_for_step(scene: dict[str, Any], step: int) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for actor in scene.get("nodes") or []:
        if str(actor.get("node_type") or "") != "human":
            continue
        actor_id = str(actor.get("id") or "")
        if not actor_id:
            continue
        event_id = planned_event_for_actor(scene, actor, step)
        previous_id = planned_event_for_actor(scene, actor, step - 1) if step > 0 else ""
        next_id = planned_event_for_actor(scene, actor, step + 1)
        events.append(
            {
                "event": event_id,
                "actor": actor_id,
                "period_start": step == 0 or previous_id != event_id,
                "period_end": next_id != event_id,
            }
        )
    return events


def expected_events(scene: dict[str, Any], steps: int) -> tuple[str, ...]:
    if not any(str(node.get("node_type") or "") == "human" for node in scene.get("nodes") or []):
        return ()
    events = []
    for step in range(steps):
        for event in planned_events_for_step(scene, step):
            event_id = str(event.get("event") or "")
            if event_id and event_id not in events:
                events.append(event_id)
    return tuple(events)


def score_scene(
    scene: dict[str, Any],
    baseline: dict[str, Any],
    previous: dict[str, Any],
    expected: tuple[str, ...],
    robot_scene: dict[str, Any],
) -> dict[str, float]:
    return matrix_score(
        build_matrix_snapshot(scene, expected),
        build_matrix_snapshot(baseline, expected),
        build_matrix_snapshot(previous, expected),
        build_matrix_snapshot(robot_scene, expected),
    )


def write_json_array(path: Path, rows: list[dict[str, Any]], *, desc: str) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write("[\n")
        for index, row in enumerate(tqdm(rows, desc=desc, unit="row", dynamic_ncols=True)):
            if index:
                handle.write(",\n")
            handle.write(json.dumps(row, ensure_ascii=False))
        handle.write("\n]\n")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False))
        handle.write("\n")


def append_csv_row(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not path.exists() or path.stat().st_size == 0
    fieldnames = list(row.keys())
    existing_rows: list[dict[str, str]] = []
    if not needs_header:
        with path.open(newline="", encoding="utf-8") as existing:
            reader = csv.DictReader(existing)
            old_fieldnames = list(reader.fieldnames or [])
            if old_fieldnames and any(key not in old_fieldnames for key in row):
                existing_rows = list(reader)
                fieldnames = old_fieldnames + [key for key in row if key not in old_fieldnames]
                needs_header = True
            elif old_fieldnames:
                fieldnames = old_fieldnames
    if existing_rows:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer_csv = csv.DictWriter(handle, fieldnames=fieldnames)
            writer_csv.writeheader()
            writer_csv.writerows(existing_rows)
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer_csv = csv.DictWriter(handle, fieldnames=fieldnames)
        if needs_header and not existing_rows:
            writer_csv.writeheader()
        writer_csv.writerow(row)


def write_csv_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer_csv = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer_csv.writeheader()
        writer_csv.writerows(rows)


def write_jsonl_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def convert_jsonl_to_json_array(jsonl_path: Path, json_path: Path, *, desc: str) -> int:
    if not jsonl_path.exists():
        json_path.write_text("[]\n", encoding="utf-8")
        return 0
    count = 0
    with jsonl_path.open("r", encoding="utf-8") as source, json_path.open("w", encoding="utf-8") as target:
        target.write("[\n")
        for line in tqdm(source, desc=desc, unit="row", dynamic_ncols=True):
            line = line.strip()
            if not line:
                continue
            if count:
                target.write(",\n")
            target.write(line)
            count += 1
        target.write("\n]\n")
    return count


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # Windows: os.replace may fail with PermissionError if target is locked.
    # Retry a few times with a brief sleep.
    for attempt in range(5):
        try:
            tmp_path.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.1)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def room_of(scene: dict[str, Any], node_id: str) -> str:
    current_id = str(node_id or "")
    visited: set[str] = set()
    while current_id and current_id not in visited:
        visited.add(current_id)
        item = node(scene, current_id)
        if not item:
            return ""
        node_type = str(item.get("node_type") or "")
        if node_type == "room":
            return current_id
        current_id = str(item.get("parent") or "")
    return ""


def relation_of(scene: dict[str, Any], node_id: str) -> str:
    item = node(scene, node_id)
    if not item:
        return ""
    runtime_relation = str(item.get("runtime_relation") or "")
    if runtime_relation:
        return runtime_relation
    parent_id = str(item.get("parent") or "")
    if not parent_id:
        return ""
    for edge in scene.get("edges") or []:
        if str(edge.get("source_id") or "") != parent_id:
            continue
        if str(edge.get("target_id") or "") != str(node_id or ""):
            continue
        relation = str(edge.get("relation") or "")
        if relation:
            return relation
    return "in"


def visible_restore_goal(observation: dict[str, Any], baseline: dict[str, Any], step: int) -> dict[str, Any] | None:
    baseline_nodes = {str(item.get("id") or ""): item for item in baseline.get("nodes") or [] if item.get("id")}
    current_nodes = {str(item.get("id") or ""): item for item in observation.get("nodes") or [] if item.get("id")}
    for node_id, current in sorted(current_nodes.items()):
        initial = baseline_nodes.get(node_id) or {}
        if str(initial.get("node_type") or "") != "movable_object":
            continue
        current_parent = str(current.get("parent") or "")
        initial_parent = str(initial.get("parent") or "")
        if not current_parent or not initial_parent:
            continue
        hospital_skill = hospital_skill_for_return_issue(node_id, current, initial)
        if hospital_skill:
            target_id = hospital_return_target(
                observation, baseline, node_id, hospital_skill) or initial_parent
            if current_parent == target_id:
                continue
            goal = make_hospital_return_goal(
                node_id, target_id, hospital_skill, step,
                source="visible_hospital_supply_issue",
            )
            if goal:
                return goal
            continue
        semantic = str(current.get("semantic_type") or initial.get("semantic_type") or "")
        if scene_type(baseline) == "hospital" and semantic in HOSPITAL_MANAGED_SEMANTICS:
            continue
        if current_parent == initial_parent:
            continue
        current_parent_node = current_nodes.get(current_parent) or {}
        if str(current_parent_node.get("node_type") or "") == "human":
            parent_states = current_parent_node.get("states") or {}
            if parent_states.get("checked_out") is not True:
                continue
        return make_restore_goal(node_id, initial_parent, step, source="visible_spatial_issue")
    return None


def make_restore_goal(object_id: str, target_id: str, step: int, *, source: str) -> dict[str, Any]:
    task = f"restore_initial_position {object_id} -> {target_id}"
    return {
        "type": "restore_initial_position",
        "task": task,
        "object": object_id,
        "target": target_id,
        "started_step": step,
        "last_progress_step": step,
        "steps_without_progress": 0,
        "source": source,
    }


def first_node_by_semantic(scene: dict[str, Any], semantics: set[str], *, room: str = "") -> str:
    for item in scene.get("nodes") or []:
        if str(item.get("semantic_type") or "") not in semantics:
            continue
        if room and room_of(scene, str(item.get("id") or "")) != room:
            continue
        return str(item.get("id") or "")
    return ""


def first_node_by_semantic_near(scene: dict[str, Any], semantics: set[str], *, preferred_room: str = "") -> str:
    if preferred_room:
        near = first_node_by_semantic(scene, semantics, room=preferred_room)
        if near:
            return near
    return first_node_by_semantic(scene, semantics)


def dispose_food_phase(
    scene: dict[str, Any],
    object_id: str,
    trash_bin_id: str = "",
    robot_id: str = "robot_01",
    trash_bin_home: str = "",
) -> str:
    item = node(scene, object_id) or {}
    states = item.get("states") or {}
    if not (states.get("is_rotten") is True or states.get("is_burnt") is True):
        if trash_bin_id and trash_bin_home and str((node(scene, trash_bin_id) or {}).get("parent") or "") != trash_bin_home:
            return "return_bin"
        return "done"
    if trash_bin_id and str(item.get("parent") or "") == trash_bin_id:
        return "dump_bin" if str((node(scene, trash_bin_id) or {}).get("parent") or "") == robot_id else "take_bin"
    if trash_bin_id and str((node(scene, trash_bin_id) or {}).get("parent") or "") == robot_id:
        return "return_bin"
    return "collect_food"


def make_dispose_food_goal(
    object_id: str,
    step: int,
    *,
    source: str,
    scene: dict[str, Any],
    robot_id: str = "robot_01",
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    object_room = room_of(scene, object_id)
    trash_bin = first_node_by_semantic_near(scene, {"trash_bin"}, preferred_room=object_room)
    garbage_station = first_node_by_semantic(scene, {"garbage_station"})
    if not trash_bin or not garbage_station:
        return None
    baseline_bin = node(baseline or {}, trash_bin) or {}
    baseline_food = node(baseline or {}, object_id) or {}
    trash_bin_home = str(baseline_bin.get("parent") or (node(scene, trash_bin) or {}).get("parent") or "")
    food_home = str(baseline_food.get("parent") or first_node_by_semantic(scene, {"refrigerator", "fridge"}))
    phase = dispose_food_phase(scene, object_id, trash_bin, robot_id, trash_bin_home)
    if phase == "done":
        return None
    return {
        "type": "skill",
        "skill": "dispose_food",
        "task": f"dispose_food {object_id} -> {garbage_station}",
        "object": object_id,
        "target": garbage_station,
        "food_home": food_home,
        "trash_bin": trash_bin,
        "trash_bin_home": trash_bin_home,
        "garbage_station": garbage_station,
        "phase": phase,
        "started_step": step,
        "last_progress_step": step,
        "steps_without_progress": 0,
        "source": source,
    }


def visible_dispose_food_goal(
    observation: dict[str, Any],
    scene: dict[str, Any],
    step: int,
    robot_id: str = "robot_01",
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    for item in sorted(observation.get("nodes") or [], key=lambda node_item: str(node_item.get("id") or "")):
        if str(item.get("semantic_type") or "") != "food":
            continue
        states = item.get("states") or {}
        if states.get("is_rotten") is True or states.get("is_burnt") is True:
            return make_dispose_food_goal(
                str(item.get("id") or ""),
                step,
                source="visible_bad_food",
                scene=scene,
                robot_id=robot_id,
                baseline=baseline,
            )
    return None


def empty_cup_phase(scene: dict[str, Any], object_id: str) -> str:
    item = node(scene, object_id) or {}
    states = item.get("states") or {}
    if float(states.get("fill_level") or 0.0) <= 0.0 and states.get("is_full") is not True:
        return "done"
    return "dump_cup"


def make_empty_cup_goal(object_id: str, step: int, *, source: str, scene: dict[str, Any]) -> dict[str, Any] | None:
    object_room = room_of(scene, object_id)
    sink = first_node_by_semantic_near(scene, {"sink"}, preferred_room=object_room)
    if not sink:
        return None
    phase = empty_cup_phase(scene, object_id)
    if phase == "done":
        return None
    return {
        "type": "skill",
        "skill": "empty_cup",
        "task": f"empty_cup {object_id} -> {sink}",
        "object": object_id,
        "target": sink,
        "sink": sink,
        "phase": phase,
        "started_step": step,
        "last_progress_step": step,
        "steps_without_progress": 0,
        "source": source,
    }


def visible_empty_cup_goal(observation: dict[str, Any], scene: dict[str, Any], step: int) -> dict[str, Any] | None:
    for item in sorted(observation.get("nodes") or [], key=lambda node_item: str(node_item.get("id") or "")):
        if str(item.get("semantic_type") or "") != "cup":
            continue
        states = item.get("states") or {}
        if float(states.get("fill_level") or 0.0) > 0.0 or states.get("is_full") is True:
            return make_empty_cup_goal(str(item.get("id") or ""), step, source="visible_full_cup", scene=scene)
    return None


def laundry_phase(scene: dict[str, Any], object_id: str, washer_id: str = "", wardrobe_id: str = "") -> str:
    item = node(scene, object_id) or {}
    states = item.get("states") or {}
    parent = str(item.get("parent") or "")
    if states.get("is_dirty") is True:
        if washer_id and parent == washer_id:
            washer = node(scene, washer_id) or {}
            return "washing_wait" if bool((washer.get("states") or {}).get("is_on", False)) else "start_washer"
        return "wash_load"
    if states.get("is_wet") is True:
        return "dry"
    if states.get("folded") is False:
        return "fold"
    if wardrobe_id and parent != wardrobe_id:
        return "store"
    return "done"


def make_laundry_goal(object_id: str, step: int, *, source: str, scene: dict[str, Any]) -> dict[str, Any] | None:
    washer = first_node_by_semantic(scene, {"washer", "washing_machine"})
    drying_rack = first_node_by_semantic(scene, {"drying_rack"})
    wardrobe = first_node_by_semantic(scene, {"cabinet"}, room="bedroom") or first_node_by_semantic(scene, {"wardrobe"}, room="bedroom")
    if not washer or not drying_rack or not wardrobe:
        return None
    phase = laundry_phase(scene, object_id, washer, wardrobe)
    if phase == "done":
        return None
    return {
        "type": "skill",
        "skill": "laundry_clothes",
        "task": f"laundry_clothes {object_id} -> {wardrobe}",
        "object": object_id,
        "target": wardrobe,
        "washer": washer,
        "washer_button": f"{washer}_button",
        "drying_rack": drying_rack,
        "wardrobe": wardrobe,
        "phase": phase,
        "started_step": step,
        "last_progress_step": step,
        "steps_without_progress": 0,
        "source": source,
    }


def visible_laundry_goal(observation: dict[str, Any], scene: dict[str, Any], step: int) -> dict[str, Any] | None:
    for item in sorted(observation.get("nodes") or [], key=lambda node_item: str(node_item.get("id") or "")):
        if str(item.get("semantic_type") or "") not in CLOTH_SEMANTICS:
            continue
        states = item.get("states") or {}
        if states.get("is_dirty") is True or states.get("is_wet") is True or states.get("folded") is False:
            return make_laundry_goal(str(item.get("id") or ""), step, source="visible_laundry_issue", scene=scene)
    return None


def hospital_skill_for_return_issue(node_id: str, current: dict[str, Any], initial: dict[str, Any]) -> str:
    semantic = str(current.get("semantic_type") or initial.get("semantic_type") or "")
    if semantic == "bed_sheet":
        states = current.get("states") or {}
        if states.get("is_dirty") is True:
            return "collect_dirty_linen"
        if node_id == "clean_sheet_storage":
            return "restock_clean_sheet"
        return ""
    return HOSPITAL_SKILL_BY_SEMANTIC.get(semantic, "")


def hospital_return_target(scene: dict[str, Any], baseline: dict[str, Any], object_id: str, skill: str) -> str:
    initial = node(baseline, object_id) or {}
    if skill == "clean_medical_waste":
        return first_node_by_semantic(scene, {"medical_waste_bin"}) or str(initial.get("parent") or "")
    if skill == "collect_dirty_linen":
        return first_node_by_semantic(scene, {"dirty_linen_bin", "linen_bin"}) or str(initial.get("parent") or "")
    if skill == "restock_clean_sheet":
        return first_node_by_semantic(scene, {"supply_cabinet"}) or str(initial.get("parent") or "")
    return str(initial.get("parent") or "")


def make_hospital_return_goal(
    object_id: str,
    target_id: str,
    skill: str,
    step: int,
    *,
    source: str,
) -> dict[str, Any] | None:
    if not object_id or not target_id or skill not in HOSPITAL_RETURN_SKILLS:
        return None
    return {
        "type": "skill",
        "skill": skill,
        "task": f"{skill} {object_id} -> {target_id}",
        "object": object_id,
        "target": target_id,
        "phase": "return_item",
        "started_step": step,
        "last_progress_step": step,
        "steps_without_progress": 0,
        "source": source,
    }


def make_hospital_clean_goal(target_id: str, skill: str, step: int, *, source: str) -> dict[str, Any] | None:
    if not target_id or skill not in HOSPITAL_CLEAN_SKILLS:
        return None
    return {
        "type": "skill",
        "skill": skill,
        "task": f"{skill} {target_id}",
        "object": target_id,
        "target": target_id,
        "phase": "clean_surface",
        "started_step": step,
        "last_progress_step": step,
        "steps_without_progress": 0,
        "source": source,
    }


def hospital_issue_goal(scene: dict[str, Any], baseline: dict[str, Any], robot_id: str, step: int) -> dict[str, Any] | None:
    if scene_type(scene) != "hospital":
        return None
    baseline_nodes = {str(item.get("id") or ""): item for item in baseline.get("nodes") or [] if item.get("id")}
    current_nodes = {str(item.get("id") or ""): item for item in scene.get("nodes") or [] if item.get("id")}
    robot_room = room_of(scene, robot_id)
    candidates: list[tuple[int, int, str, dict[str, Any]]] = []
    for node_id, current in sorted(current_nodes.items()):
        states = current.get("states") or {}
        semantic = str(current.get("semantic_type") or "")
        if node_id == "seats_waiting_area" and states.get("is_dirty") is True:
            priority = 5 if room_of(scene, node_id) == robot_room else 25
            goal = make_hospital_clean_goal(node_id, "clean_waiting_area", step, source="global_hospital_dirty_surface")
            if goal:
                candidates.append((priority, HOSPITAL_SKILL_PRIORITY["clean_waiting_area"], node_id, goal))
        if semantic == "bed" and states.get("is_dirty") is True:
            priority = 5 if room_of(scene, node_id) == robot_room else 25
            goal = make_hospital_clean_goal(node_id, "clean_exam_bed", step, source="global_hospital_dirty_bed")
            if goal:
                candidates.append((priority, HOSPITAL_SKILL_PRIORITY["clean_exam_bed"], node_id, goal))
        initial = baseline_nodes.get(node_id) or {}
        skill = hospital_skill_for_return_issue(node_id, current, initial)
        if not skill:
            continue
        current_parent = str(current.get("parent") or "")
        initial_parent = str(initial.get("parent") or "")
        target_id = hospital_return_target(scene, baseline, node_id, skill) or initial_parent
        if not current_parent or not target_id or current_parent == target_id:
            continue
        current_parent_node = node(scene, current_parent) or {}
        if str(current_parent_node.get("node_type") or "") == "human":
            parent_states = current_parent_node.get("states") or {}
            if parent_states.get("checked_out") is not True:
                continue
        current_room = room_of(scene, current_parent)
        initial_room = room_of(scene, target_id) or room_of(baseline, initial_parent)
        priority = 40
        if current_parent == robot_id:
            priority = 0
        elif current_room == robot_room:
            priority = 10
        elif initial_room == robot_room:
            priority = 20
        elif current_room:
            priority = 30
        goal = make_hospital_return_goal(node_id, target_id, skill, step, source="global_hospital_supply_issue")
        if goal:
            candidates.append((priority, HOSPITAL_SKILL_PRIORITY.get(skill, 99), node_id, goal))
    if not candidates:
        return None
    _, _, _, goal = min(candidates, key=lambda item: (item[0], item[1], item[2]))
    return goal


def global_restore_goal(scene: dict[str, Any], baseline: dict[str, Any], robot_id: str, step: int) -> dict[str, Any] | None:
    baseline_nodes = {str(item.get("id") or ""): item for item in baseline.get("nodes") or [] if item.get("id")}
    current_nodes = {str(item.get("id") or ""): item for item in scene.get("nodes") or [] if item.get("id")}
    robot_room = room_of(scene, robot_id)
    hospital_goal = hospital_issue_goal(scene, baseline, robot_id, step)
    if hospital_goal:
        return hospital_goal
    dispose_candidates: list[tuple[int, str]] = []
    for node_id, current in sorted(current_nodes.items()):
        if str(current.get("semantic_type") or "") != "food":
            continue
        states = current.get("states") or {}
        if not (states.get("is_rotten") is True or states.get("is_burnt") is True):
            continue
        current_parent = str(current.get("parent") or "")
        current_parent_node = node(scene, current_parent) or {}
        if str(current_parent_node.get("node_type") or "") == "human":
            continue
        current_room = room_of(scene, current_parent)
        priority = 10 if current_room == robot_room else 30
        if current_parent == robot_id:
            priority = 0
        dispose_candidates.append((priority, node_id))
    if dispose_candidates:
        _, object_id = min(dispose_candidates)
        goal = make_dispose_food_goal(object_id, step, source="global_bad_food", scene=scene, robot_id=robot_id, baseline=baseline)
        if goal:
            return goal
    cup_candidates: list[tuple[int, str]] = []
    for node_id, current in sorted(current_nodes.items()):
        if str(current.get("semantic_type") or "") != "cup":
            continue
        states = current.get("states") or {}
        if not (float(states.get("fill_level") or 0.0) > 0.0 or states.get("is_full") is True):
            continue
        current_parent = str(current.get("parent") or "")
        current_room = room_of(scene, current_parent)
        priority = 10 if current_room == robot_room else 30
        if current_parent == robot_id:
            priority = 0
        cup_candidates.append((priority, node_id))
    if cup_candidates:
        _, object_id = min(cup_candidates)
        goal = make_empty_cup_goal(object_id, step, source="global_full_cup", scene=scene)
        if goal:
            return goal
    laundry_candidates: list[tuple[int, str]] = []
    for node_id, current in sorted(current_nodes.items()):
        if str(current.get("semantic_type") or "") not in CLOTH_SEMANTICS:
            continue
        states = current.get("states") or {}
        if not (states.get("is_dirty") is True or states.get("is_wet") is True or states.get("folded") is False):
            continue
        current_parent = str(current.get("parent") or "")
        current_parent_node = node(scene, current_parent) or {}
        if str(current_parent_node.get("node_type") or "") == "human":
            continue
        current_room = room_of(scene, current_parent)
        priority = 10 if current_room == robot_room else 30
        if current_parent == robot_id:
            priority = 0
        laundry_candidates.append((priority, node_id))
    if laundry_candidates:
        _, object_id = min(laundry_candidates)
        goal = make_laundry_goal(object_id, step, source="global_laundry_issue", scene=scene)
        if goal:
            return goal
    candidates: list[tuple[int, str, str]] = []
    for node_id, current in sorted(current_nodes.items()):
        initial = baseline_nodes.get(node_id) or {}
        if str(initial.get("node_type") or "") != "movable_object":
            continue
        # State-dependent hospital workflows own these objects.  Falling
        # through to baseline restore would undo collect_dirty_linen or
        # restock_clean_sheet on the next goal selection.
        semantic = str(current.get("semantic_type") or initial.get("semantic_type") or "")
        if scene_type(scene) == "hospital" and semantic in HOSPITAL_MANAGED_SEMANTICS:
            continue
        current_parent = str(current.get("parent") or "")
        initial_parent = str(initial.get("parent") or "")
        if not current_parent or not initial_parent or current_parent == initial_parent:
            continue
        current_parent_node = node(scene, current_parent) or {}
        if str(current_parent_node.get("node_type") or "") == "human":
            continue
        current_room = room_of(scene, current_parent)
        initial_room = room_of(baseline, initial_parent)
        priority = 50
        if current_parent == robot_id:
            priority = 0
        elif current_room == robot_room:
            priority = 10
        elif initial_room == robot_room:
            priority = 20
        elif current_room:
            priority = 30
        candidates.append((priority, node_id, initial_parent))
    if not candidates:
        return None
    _, object_id, target_id = min(candidates)
    return make_restore_goal(object_id, target_id, step, source="global_spatial_issue")


def candidate_goal_options(
    scene: dict[str, Any],
    baseline: dict[str, Any],
    observation: dict[str, Any],
    robot_id: str,
    step: int,
    claimed_goal_nodes: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    claimed_goal_nodes = claimed_goal_nodes or set()
    goals: list[dict[str, Any] | None] = [
        global_restore_goal(scene, baseline, robot_id, step),
        visible_dispose_food_goal(observation, scene, step, robot_id, baseline),
        visible_empty_cup_goal(observation, scene, step),
        visible_laundry_goal(observation, scene, step),
        visible_restore_goal(observation, baseline, step),
    ]
    options: dict[str, dict[str, Any]] = {}
    for goal in goals:
        if not goal or goal_conflicts_with_claims(goal, claimed_goal_nodes):
            continue
        refreshed = refresh_active_goal_snapshot(goal, scene, robot_id)
        if not active_goal_ids_valid(refreshed, scene):
            continue
        task = str(refreshed.get("task") or "")
        if task and task not in options:
            options[task] = refreshed
    return options


def next_room_toward(scene: dict[str, Any], start_room: str, target_room: str) -> str:
    if not start_room or not target_room or start_room == target_room:
        return ""
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
    queue: list[tuple[str, list[str]]] = [(start_room, [start_room])]
    seen = {start_room}
    while queue:
        room_id, path = queue.pop(0)
        for neighbor in sorted(graph.get(room_id, ())):
            if neighbor in seen:
                continue
            next_path = [*path, neighbor]
            if neighbor == target_room:
                return next_path[1] if len(next_path) > 1 else ""
            seen.add(neighbor)
            queue.append((neighbor, next_path))
    return ""


def refresh_active_goal_snapshot(goal: dict[str, Any], scene: dict[str, Any], robot_id: str) -> dict[str, Any]:
    updated = copy.deepcopy(goal)
    object_id = str(updated.get("object") or "")
    object_node = node(scene, object_id) or {}
    robot_node = node(scene, robot_id) or {}
    target_id = str(updated.get("target") or "")
    skill = str(updated.get("skill") or "")
    destination_room_override = ""
    if str(updated.get("type") or "") == "skill" and skill == "dispose_food":
        trash_bin = str(updated.get("trash_bin") or first_node_by_semantic_near(scene, {"trash_bin"}, preferred_room=room_of(scene, object_id)))
        garbage_station = str(updated.get("garbage_station") or first_node_by_semantic(scene, {"garbage_station"}))
        updated["trash_bin"] = trash_bin
        updated["garbage_station"] = garbage_station
        updated["target"] = garbage_station
        trash_bin_home = str(updated.get("trash_bin_home") or (node(scene, trash_bin) or {}).get("parent") or "")
        updated["trash_bin_home"] = trash_bin_home
        updated["phase"] = dispose_food_phase(scene, object_id, trash_bin, robot_id, trash_bin_home)
        phase = str(updated.get("phase") or "")
        target_by_phase = {
            "collect_food": trash_bin,
            "take_bin": trash_bin,
            "dump_bin": garbage_station,
            "return_bin": trash_bin_home,
        }
        target_id = target_by_phase.get(phase, garbage_station)
        if phase == "collect_food":
            destination_room_override = room_of(scene, trash_bin) if str(object_node.get("parent") or "") == robot_id else room_of(scene, object_id)
        elif phase == "take_bin":
            destination_room_override = room_of(scene, trash_bin)
        elif phase == "dump_bin":
            destination_room_override = room_of(scene, garbage_station)
        elif phase == "return_bin":
            destination_room_override = room_of(scene, trash_bin_home)
    if str(updated.get("type") or "") == "skill" and skill == "empty_cup":
        sink = str(updated.get("sink") or first_node_by_semantic_near(scene, {"sink"}, preferred_room=room_of(scene, object_id)))
        updated["sink"] = sink
        updated["target"] = sink
        updated["phase"] = empty_cup_phase(scene, object_id)
        target_id = sink
        if str(object_node.get("parent") or "") == robot_id:
            destination_room_override = room_of(scene, sink)
    if str(updated.get("type") or "") == "skill" and skill == "laundry_clothes":
        washer = str(updated.get("washer") or first_node_by_semantic(scene, {"washer", "washing_machine"}))
        drying_rack = str(updated.get("drying_rack") or first_node_by_semantic(scene, {"drying_rack"}))
        wardrobe = str(updated.get("wardrobe") or first_node_by_semantic(scene, {"cabinet"}, room="bedroom") or first_node_by_semantic(scene, {"wardrobe"}, room="bedroom"))
        updated["washer"] = washer
        updated["washer_button"] = str(updated.get("washer_button") or f"{washer}_button")
        updated["drying_rack"] = drying_rack
        updated["wardrobe"] = wardrobe
        updated["target"] = wardrobe
        updated["phase"] = laundry_phase(scene, object_id, washer, wardrobe)
        target_by_phase = {
            "wash_load": washer,
            "start_washer": washer,
            "washing_wait": washer,
            "dry": drying_rack,
            "fold": object_id,
            "store": wardrobe,
        }
        target_id = target_by_phase.get(str(updated.get("phase") or ""), wardrobe)
    if str(updated.get("type") or "") == "skill" and skill in HOSPITAL_RETURN_SKILLS:
        target_id = str(updated.get("target") or "")
        updated["phase"] = "done" if object_node and str(object_node.get("parent") or "") == target_id else "return_item"
        if str(object_node.get("parent") or "") == robot_id:
            destination_room_override = room_of(scene, target_id)
    if str(updated.get("type") or "") == "skill" and skill in HOSPITAL_CLEAN_SKILLS:
        target_id = str(updated.get("target") or object_id)
        target_node = node(scene, target_id) or {}
        target_states = target_node.get("states") or {}
        updated["phase"] = (
            "clean_surface"
            if target_states.get("is_dirty") is True
            else "done"
        )
        destination_room_override = room_of(scene, target_id)
    updated["object_parent"] = str(object_node.get("parent") or "")
    updated["object_room"] = room_of(scene, object_id)
    updated["target_room"] = room_of(scene, target_id)
    updated["robot_parent"] = str(robot_node.get("parent") or "")
    updated["robot_room"] = room_of(scene, robot_id)
    destination_room = destination_room_override or (updated["target_room"] if updated["object_parent"] == robot_id else updated["object_room"])
    updated["next_room"] = next_room_toward(scene, updated["robot_room"], destination_room)
    return updated


def active_goal_ids_valid(goal: dict[str, Any] | None, scene: dict[str, Any]) -> bool:
    if not goal:
        return False
    node_ids = {str(item.get("id") or "") for item in scene.get("nodes") or [] if item.get("id")}
    fields = ("object", "target", "food_home", "trash_bin", "trash_bin_home", "garbage_station", "sink", "washer", "drying_rack", "wardrobe")
    return all(str(goal.get(field) or "") in node_ids for field in fields if goal.get(field))


def active_goal_completed(goal: dict[str, Any] | None, scene: dict[str, Any]) -> bool:
    if not goal:
        return False
    if not active_goal_ids_valid(goal, scene):
        return True
    object_node = node(scene, str(goal.get("object") or "")) or {}
    if str(goal.get("type") or "") == "skill" and str(goal.get("skill") or "") == "laundry_clothes":
        states = object_node.get("states") or {}
        return bool(
            object_node
            and str(object_node.get("parent") or "") == str(goal.get("wardrobe") or goal.get("target") or "")
            and states.get("is_dirty") is False
            and states.get("is_wet") is False
            and states.get("folded") is True
        )
    if str(goal.get("type") or "") == "skill" and str(goal.get("skill") or "") == "dispose_food":
        states = object_node.get("states") or {}
        trash_bin_node = node(scene, str(goal.get("trash_bin") or "")) or {}
        return bool(
            object_node
            and str(object_node.get("parent") or "") == str(goal.get("food_home") or "")
            and str(trash_bin_node.get("parent") or "") == str(goal.get("trash_bin_home") or "")
            and states.get("is_rotten") is False
            and states.get("is_burnt") is False
        )
    if str(goal.get("type") or "") == "skill" and str(goal.get("skill") or "") == "empty_cup":
        states = object_node.get("states") or {}
        return bool(object_node and float(states.get("fill_level") or 0.0) <= 0.0 and states.get("is_full") is not True)
    if str(goal.get("type") or "") == "skill" and str(goal.get("skill") or "") in HOSPITAL_RETURN_SKILLS:
        return bool(object_node and str(object_node.get("parent") or "") == str(goal.get("target") or ""))
    if str(goal.get("type") or "") == "skill" and str(goal.get("skill") or "") in HOSPITAL_CLEAN_SKILLS:
        target_node = node(scene, str(goal.get("target") or goal.get("object") or "")) or {}
        states = target_node.get("states") or {}
        return bool(target_node and states.get("is_dirty") is not True)
    return bool(object_node and str(object_node.get("parent") or "") == str(goal.get("target") or ""))


def active_goal_claims(goal: dict[str, Any] | None) -> set[str]:
    if not goal:
        return set()
    claims = {str(goal.get("object") or "")}
    skill = str(goal.get("skill") or "")
    if skill == "dispose_food":
        claims.add(str(goal.get("trash_bin") or ""))
    if skill == "empty_cup":
        claims.add(str(goal.get("sink") or goal.get("target") or ""))
    if skill == "laundry_clothes":
        claims.add(str(goal.get("washer") or ""))
        claims.add(str(goal.get("drying_rack") or ""))
        claims.add(str(goal.get("wardrobe") or goal.get("target") or ""))
    if skill in HOSPITAL_RETURN_SKILLS | HOSPITAL_CLEAN_SKILLS:
        claims.add(str(goal.get("target") or ""))
    if str(goal.get("type") or "") == "restore_initial_position":
        claims.add(str(goal.get("target") or ""))
    return {claim for claim in claims if claim}


def goal_conflicts_with_claims(goal: dict[str, Any] | None, claimed: set[str]) -> bool:
    if not goal:
        return False
    return bool(active_goal_claims(goal) & claimed)


def action_conflict_key(action: dict[str, Any]) -> tuple[str, str]:
    action_name = str(action.get("action") or "")
    target_id = str(action.get("target") or "")
    object_id = str(action.get("object") or "")
    if action_name == "pick" and object_id:
        return ("object", object_id)
    if action_name == "place" and object_id:
        return ("object", object_id)
    if action_name in {"brush", "fold", "dump", "open", "close", "press"} and target_id:
        return ("target", target_id)
    return ("", "")


def choose_non_conflicting_action(candidates: list[dict[str, Any]], blocked_keys: set[tuple[str, str]]) -> dict[str, Any] | None:
    for preferred_action in ("move", "open", "close"):
        for candidate in candidates:
            if str(candidate.get("action") or "") != preferred_action:
                continue
            key = action_conflict_key(candidate)
            if not key[0] or key not in blocked_keys:
                replacement = copy.deepcopy(candidate)
                replacement["reason"] = f"conflict fallback: choose non-conflicting {preferred_action}"
                return replacement
    for candidate in candidates:
        key = action_conflict_key(candidate)
        if not key[0] or key not in blocked_keys:
            replacement = copy.deepcopy(candidate)
            replacement["reason"] = "conflict fallback: choose non-conflicting action"
            return replacement
    return None


def resolve_robot_action_conflicts(
    actions: list[dict[str, Any]],
    candidates_by_robot: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    used_keys: set[tuple[str, str]] = set()
    resolved: list[dict[str, Any]] = []
    for action in actions:
        robot_id = str(action.get("agent") or "")
        key = action_conflict_key(action)
        if key[0] and key in used_keys:
            replacement = choose_non_conflicting_action(candidates_by_robot.get(robot_id) or [], used_keys)
            if replacement:
                action = replacement
                key = action_conflict_key(action)
        resolved.append(action)
        if key[0]:
            used_keys.add(key)
    return resolved


def update_active_goal(
    goal: dict[str, Any] | None,
    scene: dict[str, Any],
    robot_id: str,
    action: dict[str, Any],
    action_result: dict[str, Any],
    step: int,
    *,
    max_stale_steps: int = 12,
) -> dict[str, Any] | None:
    if not goal:
        return None
    if active_goal_completed(goal, scene):
        return None
    before_object_parent = str(goal.get("object_parent") or "")
    before_robot_parent = str(goal.get("robot_parent") or "")
    before_robot_room = str(goal.get("robot_room") or "")
    updated = refresh_active_goal_snapshot(goal, scene, robot_id)
    if not active_goal_ids_valid(updated, scene):
        return None
    meaningful_action = str(action.get("action") or "") in {"pick", "place", "brush", "dump", "fold", "press"}
    action_ok = bool(action_result.get("ok", action.get("legal", True)))
    progressed = (
        str(updated.get("object_parent") or "") != before_object_parent
        or str(updated.get("robot_parent") or "") != before_robot_parent
        or str(updated.get("robot_room") or "") != before_robot_room
        or (action_ok and meaningful_action)
    )
    if progressed:
        updated["last_progress_step"] = step
        updated["steps_without_progress"] = 0
    else:
        updated["steps_without_progress"] = int(updated.get("steps_without_progress") or 0) + 1
    if int(updated.get("steps_without_progress") or 0) >= max_stale_steps:
        return None
    return updated


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


def check_llm_agent(agent_model: str, timeout: float = 30.0) -> tuple[bool, str]:
    try:
        cfg = resolved_agent_config(agent_model)
    except Exception:
        return False, f"unsupported agent: {agent_model}"
    served_name = str(cfg.get("model") or agent_model)
    if cfg.get("type") != "openai":
        return True, served_name
    base_url = str(cfg.get("base_url") or "").rstrip("/")
    if not base_url:
        return False, f"missing base_url for agent: {agent_model}"
    try:
        health_url = base_url.rsplit("/v1", 1)[0] + "/health"
        request = urllib.request.Request(health_url)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=timeout) as response:
            response.read()
        return True, served_name
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def require_llm_agent(agent_model: str) -> str:
    model_ok, model_status = check_llm_agent(agent_model)
    if not model_ok:
        raise RuntimeError(f"LLM agent is required but unavailable: {model_status}")
    return model_status


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


def checkpoint_payload(
    *,
    scene_id: str,
    run_id: str,
    experiment_name: str,
    step: int,
    steps: int,
    robot_count: int,
    human_count: int,
    agent_model: str,
    agent_mode: str,
    efe_goal_authority: str,
    efe_candidate_source: str,
    efe_explore_navigation: str,
    efe_mode: str,
    efe_goal_b_learning: bool,
    use_llm: bool,
    schedule_mode: str,
    schedule_seed: int,
    current_scene: dict[str, Any],
    baseline_scene: dict[str, Any],
    memories: dict[str, dict[str, Any] | None],
    active_goals: dict[str, dict[str, Any] | None],
    recent_histories: dict[str, list[dict[str, Any]]],
    recent_score_records: list[dict[str, Any]],
    last_record: dict[str, Any],
    cumulative_state_score: float,
    cumulative_spatial_score: float,
    blocking_cases: list[dict[str, Any]],
    human_blocking_total: int,
    human_blocking_recovered: int,
    matrix_paths: list[str],
    metrics_csv: Path,
    replay_jsonl: Path,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "scene_id": scene_id,
        "run_id": run_id,
        "experiment": experiment_name,
        "next_step": int(step) + 1,
        "requested_steps": int(steps),
        "robot_count": int(robot_count),
        "human_count": int(human_count),
        "agent_model": agent_model,
        "agent_mode": agent_mode,
        "efe_goal_authority": efe_goal_authority if agent_mode == "efe" else "",
        "efe_candidate_source": efe_candidate_source if agent_mode == "efe" else "",
        "efe_explore_navigation": (
            efe_explore_navigation if agent_mode == "efe" else ""
        ),
        "efe_mode": efe_mode if agent_mode == "efe" else "",
        "efe_goal_b_learning": (
            bool(efe_goal_b_learning) if agent_mode == "efe" else False
        ),
        "use_llm": bool(use_llm),
        "schedule_mode": schedule_mode,
        "schedule_seed": int(schedule_seed),
        "current_scene": current_scene,
        "baseline_scene": baseline_scene,
        "memories": memories,
        "active_goals": active_goals,
        "recent_histories": recent_histories,
        "recent_score_records": recent_score_records,
        "last_record": last_record,
        "cumulative_state_score": cumulative_state_score,
        "cumulative_spatial_score": cumulative_spatial_score,
        "blocking_cases": blocking_cases,
        "human_blocking_total": int(human_blocking_total),
        "human_blocking_recovered": int(human_blocking_recovered),
        "matrix_paths": matrix_paths,
        "metrics_csv": str(metrics_csv),
        "replay_jsonl": str(replay_jsonl),
        "updated_at": time.time(),
    }


def find_resume_candidates() -> list[Path]:
    candidates: list[Path] = []
    if not EXPERIMENT_DIR.exists():
        return candidates
    for checkpoint in EXPERIMENT_DIR.glob("*/*/*/*/checkpoint.json"):
        run_dir = checkpoint.parent.parent
        if (run_dir / "summary.json").exists():
            continue
        candidates.append(run_dir)
    return sorted(set(candidates), key=lambda path: path.stat().st_mtime, reverse=True)


def resolve_resume_run(value: str) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise RuntimeError("--resume-run requires a run directory or run_id")
    path = Path(raw).expanduser()
    if path.exists():
        path = path.resolve()
        if (path / "summary.json").exists():
            raise RuntimeError(f"run is already complete: {path}")
        if list(path.glob("*/checkpoint.json")):
            return path
        raise RuntimeError(f"no checkpoint.json found under run directory: {path}")
    matches = [candidate for candidate in find_resume_candidates() if candidate.name == raw]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise RuntimeError(f"no resumable run found for: {raw}")
    raise RuntimeError(f"ambiguous run_id {raw}: " + ", ".join(str(path) for path in matches))


def print_resume_candidates() -> None:
    candidates = find_resume_candidates()
    if not candidates:
        print("No resumable runs found.")
        return
    print("Resumable runs:")
    for index, run_dir in enumerate(candidates, start=1):
        checkpoints = []
        for checkpoint in sorted(run_dir.glob("*/checkpoint.json")):
            payload = load_json(checkpoint)
            checkpoints.append(
                f"{checkpoint.parent.name}: next_step={payload.get('next_step')}/{payload.get('requested_steps')}"
            )
        print(f"{index}. {run_dir}")
        print(f"   run_id={run_dir.name}")
        print(f"   checkpoints={'; '.join(checkpoints)}")
    print("\nUse --resume --resume-run <run_id-or-run_dir> to continue one of them.")


def load_run_checkpoints(run_dir: Path) -> dict[str, dict[str, Any]]:
    checkpoints: dict[str, dict[str, Any]] = {}
    for checkpoint in sorted(run_dir.glob("*/checkpoint.json")):
        checkpoints[checkpoint.parent.name] = load_json(checkpoint)
    if not checkpoints:
        raise RuntimeError(f"no checkpoint.json found under run directory: {run_dir}")
    return checkpoints


def run_episode(
    raw_scene: dict[str, Any],
    *,
    scene_id: str,
    steps: int,
    robot_count: int,
    human_count: int,
    run_id: str,
    agent_model: str,
    use_llm: bool,
    agent_mode: str,
    expected: tuple[str, ...],
    output_dir: Path,
    matrix_viz: bool,
    replay_scene_interval: int = 1,
    metric_log_interval: int = 1,
    schedule_mode: str = "fixed",
    schedule_seed: int = 0,
    efe_goal_authority: str = "current",
    efe_candidate_source: str = "hybrid",
    efe_explore_navigation: str = "v1",
    efe_mode: str = "generative",
    efe_goal_b_learning: bool = True,
    resume: bool = False,
) -> dict[str, Any]:
    scene = prepare_scene(raw_scene, robot_count=robot_count, human_count=human_count)
    scene.setdefault("world_state", {})["schedule_mode"] = schedule_mode
    scene.setdefault("world_state", {})["schedule_seed"] = int(schedule_seed)
    baseline = copy.deepcopy(scene)
    room_index_map = build_room_index(scene)
    orchestrator = Orchestrator(scene)
    memories: dict[str, dict[str, Any] | None] = {robot_id: None for robot_id in robot_ids(robot_count)}
    active_goals: dict[str, dict[str, Any] | None] = {robot_id: None for robot_id in robot_ids(robot_count)}
    recent_histories: dict[str, list[dict[str, Any]]] = {robot_id: [] for robot_id in robot_ids(robot_count)}
    recent_score_records: list[dict[str, Any]] = []
    _recent_events_buffer = RecentEventsBuffer(max_size=5)
    _segment_start: dict[str, int] = {}
    last_record: dict[str, Any] = {}
    cumulative_state_score = 0.0
    cumulative_spatial_score = 0.0
    blocking_cases: list[dict[str, Any]] = []
    human_blocking_total = 0
    human_blocking_recovered = 0
    experiment_name = "with_robot" if robot_count else "no_robot"
    experiment_output_dir = output_dir / experiment_name
    experiment_output_dir.mkdir(parents=True, exist_ok=True)
    matrix_output_dir = experiment_output_dir / "matrices"
    planning_label = (
        f"{agent_mode}__authority_{efe_goal_authority}__candidates_{efe_candidate_source}"
        if agent_mode == "efe" else agent_mode
    )
    model_name = (
        f"{agent_model}__{planning_label}"
        if robot_count and use_llm
        else ("heuristic" if robot_count else "npc_only_baseline")
    )
    tb_dir = TENSORBOARD_DIR / _slug(scene_id) / canonical_run_group(
        scene_id,
        experiment_name,
        model_name,
        steps,
        robot_count,
        human_count,
        schedule_mode,
        schedule_seed,
    ) / run_id
    tb_dir.mkdir(parents=True, exist_ok=True)
    writer = TensorBoardWriter(tb_dir)
    replay_path = experiment_output_dir / "replay.json"
    replay_jsonl_path = experiment_output_dir / "replay.jsonl"
    csv_path = experiment_output_dir / "metrics.csv"
    checkpoint_path = experiment_output_dir / "checkpoint.json"
    model_ok = bool(robot_count and use_llm)
    model_status = require_llm_agent(agent_model) if model_ok else "not_used"
    previous_snapshot = build_matrix_snapshot(orchestrator.graph.to_scene(), expected)
    baseline_snapshot = build_matrix_snapshot(baseline, expected)
    matrix_paths: list[str] = []
    replay_scene_interval = max(0, int(replay_scene_interval))
    metric_log_interval = max(1, int(metric_log_interval))
    start_step = 0
    if resume and checkpoint_path.exists():
        checkpoint = load_json(checkpoint_path)
        checkpoint_experiment = str(checkpoint.get("experiment") or "")
        if checkpoint_experiment != experiment_name:
            raise RuntimeError(f"checkpoint experiment mismatch: {checkpoint_experiment} != {experiment_name}")
        start_step = int(checkpoint.get("next_step") or 0)
        if start_step > int(steps):
            raise RuntimeError(f"checkpoint next_step={start_step} exceeds requested steps={steps}")
        baseline = copy.deepcopy(checkpoint.get("baseline_scene") or baseline)
        scene = copy.deepcopy(checkpoint.get("current_scene") or scene)
        orchestrator = Orchestrator(scene)
        room_index_map = build_room_index(baseline)
        memories = copy.deepcopy(checkpoint.get("memories") or memories)
        active_goals = copy.deepcopy(checkpoint.get("active_goals") or active_goals)
        recent_histories = copy.deepcopy(checkpoint.get("recent_histories") or recent_histories)
        legacy_records = copy.deepcopy(checkpoint.get("records") or [])
        legacy_replay_steps = copy.deepcopy(checkpoint.get("replay_steps") or [])
        if legacy_records and not csv_path.exists():
            write_csv_rows(csv_path, legacy_records)
        if legacy_replay_steps and not replay_jsonl_path.exists():
            write_jsonl_rows(replay_jsonl_path, legacy_replay_steps)
        recent_score_records = copy.deepcopy(checkpoint.get("recent_score_records") or legacy_records[-10:])
        last_record = copy.deepcopy(checkpoint.get("last_record") or (legacy_records[-1] if legacy_records else {}))
        cumulative_state_score = float(checkpoint.get("cumulative_state_score") or 0.0)
        cumulative_spatial_score = float(checkpoint.get("cumulative_spatial_score") or 0.0)
        blocking_cases = copy.deepcopy(checkpoint.get("blocking_cases") or blocking_cases)
        human_blocking_total = int(
            checkpoint.get(
                "human_blocking_total",
                (last_record or {}).get("human_blocking_total", human_blocking_total),
            )
            or 0
        )
        human_blocking_recovered = int(
            checkpoint.get(
                "human_blocking_recovered",
                (last_record or {}).get("human_blocking_recovered", human_blocking_recovered),
            )
            or 0
        )
        matrix_paths = list(checkpoint.get("matrix_paths") or [])
        previous_snapshot = build_matrix_snapshot(orchestrator.graph.to_scene(), expected)
        baseline_snapshot = build_matrix_snapshot(baseline, expected)
        tqdm.write(f"{experiment_name}: resuming {run_id} from step {start_step}/{steps}")
    elif resume:
        tqdm.write(f"{experiment_name}: no checkpoint found, starting from step 0")
    # --- DeployLoop instances (yuling_deploy mode) ---
    deploy_loops: dict[str, Any] = {}
    if agent_mode == "yuling_deploy":
        for robot_id in robot_ids(robot_count):
            deploy_loops[robot_id] = DeployLoop(
                baseline, agent_id=robot_id, agent_model=agent_model,
                llm_fn=llm_query if use_llm else None,
            )

    # --- EfeLoop instances (efe mode) ---
    efe_loops: dict[str, Any] = {}
    if agent_mode == "efe":
        for robot_id in robot_ids(robot_count):
            efe_loops[robot_id] = EfeLoop(
                baseline, agent_id=robot_id, agent_model=agent_model,
                total_steps=steps,
                efe_mode=efe_mode,
                goal_authority=efe_goal_authority,
                candidate_source=efe_candidate_source,
                explore_navigation=efe_explore_navigation,
                selection_seed=schedule_seed,
                goal_outcome_learning=efe_goal_b_learning,
                engine_ranked_fn=engine_ranked_prompt_candidates,
                engine_node_index_fn=engine_node_index,
                engine_scene_node_index_fn=engine_scene_node_index,
            )

    for step in tqdm(range(start_step, steps), desc=experiment_name, unit="step", dynamic_ncols=True):
        schedule_scene = orchestrator.graph.to_scene()
        event_id = planned_event_for_step(schedule_scene, step)
        human_events = planned_events_for_step(schedule_scene, step)
        update_segment_starts(human_events, _segment_start, step)
        actions: list[dict[str, Any]] = []
        candidates_by_robot: dict[str, list[dict[str, Any]]] = {}
        llm_answers: dict[str, str] = {}
        goal_review_answers: dict[str, str] = {}
        efe_step_diagnostics: dict[str, dict[str, Any]] = {}
        observations: dict[str, dict[str, Any]] = {}
        claimed_goal_nodes: set[str] = set()
        for robot_id in robot_ids(robot_count):
            claimed_goal_nodes.update(
                claim
                for other_robot_id, goal in active_goals.items()
                if other_robot_id != robot_id
                for claim in active_goal_claims(goal)
            )
            if agent_mode in {"single_round", "goal_review", "yuling", "yuling_deploy"} and active_goals.get(robot_id) is None:
                proposed_goal = global_restore_goal(orchestrator.graph.to_scene(), baseline, robot_id, step)
                if proposed_goal and not goal_conflicts_with_claims(proposed_goal, claimed_goal_nodes):
                    active_goals[robot_id] = refresh_active_goal_snapshot(proposed_goal, orchestrator.graph.to_scene(), robot_id)
            observation = perceive(orchestrator, robot_id)
            observations[robot_id] = observation
            memories[robot_id] = remember(memories.get(robot_id), observation)
            # --- efe mode: EfeLoop memory update ---
            if agent_mode == "efe":
                el = efe_loops[robot_id]
                el.update_memory(observation, step)
            # --- yuling_deploy: RobotMemory + goal inference ---
            if agent_mode == "yuling_deploy":
                dl = deploy_loops[robot_id]
                dl.step_counter = step
                dl.memory.update(observation, step)
                # Goal completion / stuck checks use known_world (actual seen
                # state); new goal inference uses full_scene (god-view in sim).
                dl._update_goal(
                    dl.memory.get_known_scene(),
                    full_scene=orchestrator.graph.to_scene(),
                )
            if agent_mode in {"single_round", "goal_review", "yuling", "yuling_deploy"} and active_goals.get(robot_id) is None:
                proposed_goal = visible_dispose_food_goal(observation, orchestrator.graph.to_scene(), step, robot_id, baseline)
                if proposed_goal and goal_conflicts_with_claims(proposed_goal, claimed_goal_nodes):
                    proposed_goal = None
                if not proposed_goal:
                    proposed_goal = visible_empty_cup_goal(observation, orchestrator.graph.to_scene(), step)
                    if proposed_goal and goal_conflicts_with_claims(proposed_goal, claimed_goal_nodes):
                        proposed_goal = None
                if not proposed_goal:
                    proposed_goal = visible_laundry_goal(observation, orchestrator.graph.to_scene(), step)
                    if proposed_goal and goal_conflicts_with_claims(proposed_goal, claimed_goal_nodes):
                        proposed_goal = None
                if not proposed_goal:
                    proposed_goal = visible_restore_goal(observation, baseline, step)
                    if proposed_goal and goal_conflicts_with_claims(proposed_goal, claimed_goal_nodes):
                        proposed_goal = None
                if proposed_goal:
                    active_goals[robot_id] = refresh_active_goal_snapshot(proposed_goal, orchestrator.graph.to_scene(), robot_id)
            if use_llm and agent_mode == "goal_review":
                goal_options = candidate_goal_options(
                    orchestrator.graph.to_scene(),
                    baseline,
                    observation,
                    robot_id,
                    step,
                    claimed_goal_nodes,
                )
                high_level_options = ["maintain_order"]
                active_task = str((active_goals.get(robot_id) or {}).get("task") or "")
                if active_task:
                    high_level_options.append(active_task)
                high_level_options.extend(task for task in goal_options if task not in high_level_options)
                review, review_answer = llm_review_goal(
                    observation,
                    agent_model,
                    initial_scene=baseline,
                    active_goal=active_goals.get(robot_id),
                    high_level_options=high_level_options,
                    recent_history=recent_histories.get(robot_id, []),
                    agent_id=robot_id,
                )
                goal_review_answers[robot_id] = review_answer
                decision = str(review.get("decision") or "")
                reviewed_task = str(review.get("high_level_task") or "")
                if decision in {"finish", "drop"} or reviewed_task == "maintain_order":
                    active_goals[robot_id] = None
                elif decision == "switch":
                    active_goals[robot_id] = goal_options.get(reviewed_task)
                elif active_goals.get(robot_id):
                    active_goals[robot_id] = refresh_active_goal_snapshot(
                        active_goals[robot_id],
                        orchestrator.graph.to_scene(),
                        robot_id,
                    )
            claimed_goal_nodes.update(active_goal_claims(active_goals.get(robot_id)))
            candidates = candidate_actions(orchestrator, observation, robot_id)
            if not candidates:
                raise RuntimeError(
                    f"no legal candidates for {robot_id} at step {step}; "
                    f"room={orchestrator.graph.room_of.get(robot_id)}; "
                    f"parent={orchestrator.graph.parent_of.get(robot_id)}; "
                    f"visible={len(observation.get('nodes') or [])}"
                )
            candidates_by_robot[robot_id] = candidates
            # --- efe mode: EFE-driven decision ---
            if agent_mode == "efe":
                el = efe_loops[robot_id]
                full_scene = orchestrator.graph.to_scene()
                # Local deviations only — EFE scores what's visible.
                # (global caused score regression; needs separate investigation.)
                deviations = engine_critical_state_deviations(
                    observation, baseline, robot_id
                )
                # In EFE mode the pipeline is a fresh candidate proposer, not
                # a second persistent goal owner.  EfeLoop alone owns commit,
                # completion, failure and cooldown.
                pipeline_goals = list(candidate_goal_options(
                    full_scene, baseline, observation, robot_id, step,
                    claimed_goal_nodes,
                ).values())
                efe_result = el.step(
                    observation, candidates, step,
                    deviations=deviations,
                    active_goal=None,
                    pipeline_goals=pipeline_goals,
                    world_scene=full_scene,
                    recent_events=_recent_events_buffer.recent_text(),
                    llm_fn=llm_query if use_llm else None,
                )
                action = efe_result["action"]
                llm_answer = efe_result.get("llm_response", "")
                llm_answers[robot_id] = llm_answer
                efe_step_diagnostics[robot_id] = {
                    "step": efe_result.get("authority_step", {}),
                    "cumulative": efe_result.get("authority_diagnostics", {}),
                }
                if not action:
                    action = fallback_choose_action(candidates)
                actions.append(action)
                continue
            if use_llm:
                if agent_mode == "reactive":
                    recent_scores = [
                        {
                            "step": int(record.get("step") or 0),
                            "final_score": record.get("final_score"),
                            "state_score": record.get("state_score"),
                            "spatial_score": record.get("spatial_score"),
                            "human_event_score": record.get("human_event_score"),
                        }
                        for record in recent_score_records[-10:]
                    ]
                    action, llm_answer = llm_choose_reactive_action(
                        candidates,
                        observation,
                        agent_model,
                        recent_scores=recent_scores,
                        agent_id=robot_id,
                    )
                elif agent_mode == "yuling":
                    yuling_result = yuling_agent(
                        initial_scene=baseline,
                        observation=observation,
                        candidates=candidates,
                        # deviations auto-computed from observation (mirrors
                        # llm_choose_action).  In deployment, human reports
                        # provide the deviations signal instead.
                        goal="",
                        active_goal=active_goals.get(robot_id),
                        recent_events=_recent_events_buffer.recent_text(),
                        agent_id=robot_id,
                        agent_model=agent_model,
                        llm_fn=llm_query,
                        _engine_builders=_ENGINE_BUILDERS,
                    )
                    action = yuling_result["action"]
                    llm_answer = yuling_result["llm_response"]
                elif agent_mode == "yuling_deploy":
                    dl = deploy_loops[robot_id]
                    dl.llm_fn = llm_query
                    # Use same deviations source as yuling mode (auto from
                    # perceive) to isolate goal inference as the only variable.
                    deviations = None  # yuling_agent auto-computes
                    yuling_result = yuling_agent(
                        initial_scene=baseline,
                        observation=observation,
                        candidates=candidates,
                        deviations=deviations,
                        goal="",
                        active_goal=dl.active_goal,
                        recent_events=_recent_events_buffer.recent_text(),
                        agent_id=robot_id,
                        agent_model=agent_model,
                        llm_fn=llm_query,
                        _engine_builders=_ENGINE_BUILDERS,
                    )
                    action = yuling_result["action"]
                    llm_answer = yuling_result["llm_response"]
                    # Track holding for next step's candidate generation
                    if action:
                        dl.holding = dl._infer_holding(action, observation)
                        dl._track_progress(action, observation)
                else:
                    action, llm_answer = llm_choose_action(
                        candidates,
                        observation,
                        agent_model,
                        baseline,
                        active_goal=active_goals.get(robot_id),
                        recent_events=_recent_events_buffer.recent_text() if agent_mode == "goal_review" else "",
                        agent_id=robot_id,
                    )
                llm_answers[robot_id] = llm_answer
            else:
                action = fallback_choose_action(candidates)
            actions.append(action)
        actions = resolve_robot_action_conflicts(actions, candidates_by_robot)
        result = orchestrator.step(
            robot_actions=actions,
            human_events=human_events,
            capture_robot_scene=bool(robot_count),
            capture_scene=False,
        )
        record_events_from_step_result(
            _recent_events_buffer, human_events,
            result.get("human_events") or [], _segment_start, step,
        )
        for robot_id in robot_ids(robot_count):
            memories[robot_id] = reflect(memories.get(robot_id), result)
        current = orchestrator.graph.to_scene()
        new_blocking_cases: list[dict[str, Any]] = []
        for event_result in result.get("human_events") or []:
            for case in event_result.get("blocking_cases") or []:
                new_blocking_cases.append(copy.deepcopy(case))
        if new_blocking_cases:
            blocking_cases.extend(new_blocking_cases)
            human_blocking_total += sum(1 for case in new_blocking_cases if bool(case.get("recoverable", False)))
        action_results = {
            robot_id: copy.deepcopy(action_result)
            for robot_id, action_result in zip(robot_ids(robot_count), result.get("robot_actions") or [])
        }
        actions_by_robot = {str(action.get("agent") or ""): action for action in actions}
        for robot_id in robot_ids(robot_count):
            active_goals[robot_id] = update_active_goal(
                active_goals.get(robot_id),
                current,
                robot_id,
                actions_by_robot.get(robot_id, {}),
                action_results.get(robot_id, {}),
                step,
            )
        current_snapshot = build_matrix_snapshot(current, expected)
        robot_snapshot = build_matrix_snapshot(result["robot_scene"], expected) if robot_count else current_snapshot
        instant_metrics = matrix_score(current_snapshot, baseline_snapshot, previous_snapshot, robot_snapshot)
        instant_metrics.pop("robot_score", None)
        instant_state_score = float(instant_metrics["state_score"])
        instant_spatial_score = float(instant_metrics["spatial_score"])
        human_event_score = float(instant_metrics["human_event_score"])
        instant_final_score = round(
            instant_state_score * 0.45 + instant_spatial_score * 0.35 + human_event_score * 0.20,
            4,
        )
        cumulative_state_score += instant_state_score
        cumulative_spatial_score += instant_spatial_score
        avg_state_score = round(cumulative_state_score / (step + 1), 4)
        avg_spatial_score = round(cumulative_spatial_score / (step + 1), 4)
        avg_final_score = round(
            avg_state_score * 0.45
            + avg_spatial_score * 0.35
            + human_event_score * 0.20,
            4,
        )
        metrics = {
            "final_score": avg_final_score,
            "state_score": avg_state_score,
            "spatial_score": avg_spatial_score,
            "human_event_score": round(human_event_score, 4),
            "instant_final_score": instant_final_score,
            "instant_state_score": round(instant_state_score, 4),
            "instant_spatial_score": round(instant_spatial_score, 4),
            "avg_final_score": avg_final_score,
            "avg_state_score": avg_state_score,
            "avg_spatial_score": avg_spatial_score,
            "robot_state_improvements": instant_metrics.get("robot_state_improvements", 0),
            "robot_spatial_improvements": instant_metrics.get("robot_spatial_improvements", 0),
            "human_blocking_total": human_blocking_total,
            "human_blocking_recovered": human_blocking_recovered,
            "human_blocking_recovery_rate": round(
                human_blocking_recovered / human_blocking_total, 4
            )
            if human_blocking_total
            else 0.0,
        }
        previous_snapshot = current_snapshot
        primary_action = actions[0] if actions else {}
        action_name = str(primary_action.get("action") or "")
        before_resolved = sum(1 for case in blocking_cases if str(case.get("status") or "") in {"resolved", "closed_success"})
        update_blocking_cases(blocking_cases, current, actions, step)
        finalize_blocking_case_outcomes(blocking_cases, result.get("human_events") or [])
        after_resolved = sum(1 for case in blocking_cases if str(case.get("status") or "") in {"resolved", "closed_success"})
        human_blocking_recovered += max(0, after_resolved - before_resolved)
        metrics["human_blocking_total"] = human_blocking_total
        metrics["human_blocking_recovered"] = human_blocking_recovered
        metrics["human_blocking_recovery_rate"] = (
            round(human_blocking_recovered / human_blocking_total, 4) if human_blocking_total else 0.0
        )
        for robot_id in robot_ids(robot_count):
            action_for_robot = actions_by_robot.get(robot_id, {})
            history = recent_histories.setdefault(robot_id, [])
            history.append(
                {
                    "step": step,
                    "room": room_of(current, robot_id),
                    "holding": held_object(orchestrator, robot_id),
                    "active_goal": str((active_goals.get(robot_id) or {}).get("task") or ""),
                    "action": action_for_robot.get("action", ""),
                    "target": action_for_robot.get("target", ""),
                    "object": action_for_robot.get("object", ""),
                    "final_score": float(metrics["final_score"]),
                    "state_score": float(metrics["state_score"]),
                    "spatial_score": float(metrics["spatial_score"]),
                    "human_event_score": float(metrics["human_event_score"]),
                }
            )
            del history[:-10]
        if step % metric_log_interval == 0 or step + 1 == steps:
            for key in SCORE_KEYS:
                writer.add_scalar(f"scores/{key}", float(metrics[key]), step)
            for key in INSTANT_SCORE_KEYS:
                writer.add_scalar(f"scores/{key}", float(metrics[key]), step)
            for key in AVG_SCORE_KEYS:
                writer.add_scalar(f"scores/{key}", float(metrics[key]), step)
            writer.add_scalar("actions/action_code", ACTION_CODES.get(action_name, -1), step)
        if matrix_viz:
            matrix_paths.append(
                save_step_matrices(
                    current_snapshot,
                    step=step,
                    output_dir=matrix_output_dir,
                )
            )
        row = {
            "step": step,
            "experiment": experiment_name,
            "event": event_id,
            "action": action_name,
            "target": primary_action.get("target", ""),
            "action_reason": primary_action.get("reason", ""),
            "action_legal": all(bool(action.get("legal", True)) for action in actions) if actions else True,
            "validation_failures": json.dumps(
                {str(action.get("agent") or ""): action.get("validation_failures", []) for action in actions},
                ensure_ascii=False,
            ),
            "llm_answer": json.dumps(llm_answers, ensure_ascii=False),
            "goal_review": json.dumps(goal_review_answers, ensure_ascii=False),
            "active_goal": json.dumps(active_goals, ensure_ascii=False),
            "efe_goal_authority": efe_goal_authority if agent_mode == "efe" else "",
            "efe_authority_diagnostics": json.dumps(
                efe_step_diagnostics, ensure_ascii=False, sort_keys=True),
            **metrics,
        }
        append_csv_row(csv_path, row)
        recent_score_records.append(row)
        del recent_score_records[:-10]
        last_record = row
        primary_robot = robot_ids(robot_count)[0] if robot_count else ""
        robot_room = room_of(current, primary_robot) if primary_robot else ""
        if primary_robot and robot_room:
            writer.add_scalar("trajectory/room_index", room_index_map.get(robot_room, -1), step)
        include_scene = replay_scene_interval > 0 and (step % replay_scene_interval == 0 or step + 1 == steps)
        replay_row = {
            "episode_step": step,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reasoning": json.dumps(llm_answers, ensure_ascii=False) if robot_count else "npc_only_baseline",
            "goal_review": json.dumps(goal_review_answers, ensure_ascii=False) if robot_count else "",
            "planner": {
                "mode": "llm" if robot_count and use_llm and model_ok else ("heuristic" if robot_count else "npc_only_baseline"),
                "event": event_id,
            },
            "action": copy.deepcopy(primary_action),
            "robot_actions": copy.deepcopy(actions),
            "ok": all(bool(action.get("legal", True)) for action in actions) if actions else True,
            "failed_preconds": {
                str(action.get("agent") or ""): copy.deepcopy(action.get("validation_failures") or [])
                for action in actions
            },
            "blocking_cases": copy.deepcopy(blocking_cases),
            "observation": copy.deepcopy(observations),
            "memory_before": {},
            "memory_after": copy.deepcopy(memories),
            "active_goals": copy.deepcopy(active_goals),
            "efe_authority_diagnostics": copy.deepcopy(efe_step_diagnostics),
            "event_log": copy.deepcopy(human_events),
            "scene_metrics": {
                "world_metrics": {
                    "world_score": float(metrics["final_score"]),
                    "human_score": float(metrics["human_event_score"]),
                },
                "top_issues": [],
            },
            "world_score": float(metrics["final_score"]),
            "scene": copy.deepcopy(current) if include_scene else {},
            "robot_state": {
                "room_id": robot_room,
                "holding": held_object(orchestrator, primary_robot) if primary_robot else "",
            },
            "robot_states": {
                robot_id: {
                    "room_id": room_of(current, robot_id),
                    "holding": held_object(orchestrator, robot_id),
                }
                for robot_id in robot_ids(robot_count)
            },
        }
        append_jsonl(replay_jsonl_path, replay_row)
        write_json_atomic(
            checkpoint_path,
            checkpoint_payload(
                scene_id=scene_id,
                run_id=run_id,
                experiment_name=experiment_name,
                step=step,
                steps=steps,
                robot_count=robot_count,
                human_count=human_count,
                agent_model=agent_model,
                agent_mode=agent_mode,
                efe_goal_authority=efe_goal_authority,
                efe_candidate_source=efe_candidate_source,
                efe_explore_navigation=efe_explore_navigation,
                efe_mode=efe_mode,
                efe_goal_b_learning=efe_goal_b_learning,
                use_llm=use_llm,
                schedule_mode=schedule_mode,
                schedule_seed=schedule_seed,
                current_scene=current,
                baseline_scene=baseline,
                memories=memories,
                active_goals=active_goals,
                recent_histories=recent_histories,
                recent_score_records=recent_score_records,
                last_record=last_record,
                cumulative_state_score=cumulative_state_score,
                cumulative_spatial_score=cumulative_spatial_score,
                blocking_cases=blocking_cases,
                human_blocking_total=human_blocking_total,
                human_blocking_recovered=human_blocking_recovered,
                matrix_paths=matrix_paths,
                metrics_csv=csv_path,
                replay_jsonl=replay_jsonl_path,
            ),
        )
    writer.add_text(
        "trajectory/room_index_map",
        "\n".join(f"{index}: {room_id}" for room_id, index in sorted(room_index_map.items(), key=lambda item: item[1])),
        0,
    )
    tqdm.write(f"{experiment_name}: flushing tensorboard")
    writer.flush()
    writer.close()
    tqdm.write(f"{experiment_name}: writing replay to {replay_path}")
    replay_count = convert_jsonl_to_json_array(replay_jsonl_path, replay_path, desc=f"{experiment_name} replay")
    return {
        "experiment": experiment_name,
        "records": [last_record] if last_record else [],
        "tensorboard_log_dir": str(tb_dir),
        "replay_path": str(replay_path),
        "metrics_csv": str(csv_path),
        "matrix_dir": str(matrix_output_dir) if matrix_viz else "",
        "matrix_count": len(matrix_paths),
        "replay_count": replay_count,
        "model_ok": model_ok,
        "model_status": model_status,
        "efe_goal_authority": efe_goal_authority if agent_mode == "efe" else "",
        "efe_candidate_source": efe_candidate_source if agent_mode == "efe" else "",
        "efe_explore_navigation": (
            efe_explore_navigation if agent_mode == "efe" else ""
        ),
        "efe_mode": efe_mode if agent_mode == "efe" else "",
        "efe_goal_b_learning": (
            bool(efe_goal_b_learning) if agent_mode == "efe" else False
        ),
        "efe_authority_diagnostics": {
            robot_id: loop.authority_diagnostics()
            for robot_id, loop in efe_loops.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", default="simple_home_1f")
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--agent-model", default="vllm-qwen3.5-4b")
    parser.add_argument("--robots", type=int, default=1)
    parser.add_argument("--humans", type=int, default=1)
    parser.add_argument("--no-clean", action="store_true")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--goal-review", choices=("on", "off"), default="on")
    parser.add_argument("--agent-mode", choices=("reactive", "single_round", "goal_review", "yuling", "yuling_deploy", "efe"), default="")
    parser.add_argument("--only", choices=("both", "no_robot", "with_robot"), default="both")
    parser.add_argument("--matrix-viz", action="store_true")
    parser.add_argument("--replay-scene-interval", type=int, default=1)
    parser.add_argument("--metric-log-interval", type=int, default=1)
    parser.add_argument("--schedule-mode", choices=("fixed", "calendar", "stochastic"), default="fixed")
    parser.add_argument("--schedule-seed", type=int, default=0)
    parser.add_argument(
        "--efe-goal-authority",
        choices=("current", "efe_all", "rule_all", "random_all"),
        default="current",
        help="Who owns high-level goal selection in --agent-mode efe.",
    )
    parser.add_argument(
        "--efe-candidate-source", choices=("hybrid", "skill_only"),
        default="hybrid",
        help="Use skill/pipeline goals only for deterministic authority ablations.",
    )
    parser.add_argument(
        "--efe-explore-navigation", choices=("v1", "llm"), default="v1",
        help=("Low-level executor for explore Goals. v1 uses deterministic "
              "BFS navigation; llm keeps the original LLM-selected action."),
    )
    parser.add_argument(
        "--efe-mode",
        choices=("phase1", "generative", "goal_conditioned",
                 "goal_conditioned_b"),
        default=os.environ.get("EFE_MODE", "generative"),
        help="EFE scoring model; goal_conditioned_b learns structured B.",
    )
    parser.add_argument(
        "--efe-goal-b-learning", choices=("on", "off"), default=None,
        help=("Enable/disable Goal-conditioned B updates. If omitted, keeps "
              "the EFE_GOAL_B_LEARNING environment-variable behavior."),
    )
    parser.add_argument(
        "--output-root", default="",
        help="Optional experiment root; defaults to backend/data/experiments.",
    )
    parser.add_argument("--resume", action="store_true", help="List resumable interrupted runs, or resume --resume-run.")
    parser.add_argument("--resume-run", default="", help="Run id or run directory to continue when --resume is set.")
    args = parser.parse_args()
    if args.resume and not str(args.resume_run or "").strip():
        print_resume_candidates()
        return
    agent_mode = str(args.agent_mode or "").strip() or ("goal_review" if args.goal_review == "on" else "single_round")
    agent_model = str(args.agent_model)
    scene_id = str(args.scene or "simple_home_1f").removesuffix(".json")
    steps = int(args.steps)
    robots = max(0, int(args.robots))
    humans = max(0, int(args.humans))
    schedule_mode = str(args.schedule_mode or "fixed")
    schedule_seed = int(args.schedule_seed)
    efe_goal_authority = str(args.efe_goal_authority)
    efe_candidate_source = str(args.efe_candidate_source)
    efe_explore_navigation = str(args.efe_explore_navigation)
    efe_mode = str(args.efe_mode)
    efe_goal_b_learning = (
        str(args.efe_goal_b_learning) == "on"
        if args.efe_goal_b_learning is not None
        else os.environ.get(
            "EFE_GOAL_B_LEARNING",
            os.environ.get("EFE_GOAL_OUTCOME_LEARNING", "1"),
        ) != "0"
    )
    group_robots = 0 if args.only == "no_robot" else robots
    resume_checkpoints: dict[str, dict[str, Any]] = {}
    if args.resume:
        output_dir = resolve_resume_run(str(args.resume_run))
        resume_checkpoints = load_run_checkpoints(output_dir)
        first_checkpoint = next(iter(resume_checkpoints.values()))
        run_id = output_dir.name
        experiment_group = output_dir.parent.name
        scene_id = str(first_checkpoint.get("scene_id") or scene_id)
        steps = int(first_checkpoint.get("requested_steps") or steps)
        robots = int(first_checkpoint.get("robot_count") or robots)
        humans = int(first_checkpoint.get("human_count") or humans)
        agent_model = str(first_checkpoint.get("agent_model") or agent_model)
        agent_mode = str(first_checkpoint.get("agent_mode") or agent_mode)
        efe_goal_authority = str(
            first_checkpoint.get("efe_goal_authority") or efe_goal_authority)
        efe_candidate_source = str(
            first_checkpoint.get("efe_candidate_source") or efe_candidate_source)
        efe_explore_navigation = str(
            first_checkpoint.get("efe_explore_navigation")
            or efe_explore_navigation)
        efe_mode = str(first_checkpoint.get("efe_mode") or efe_mode)
        if "efe_goal_b_learning" in first_checkpoint:
            efe_goal_b_learning = bool(
                first_checkpoint.get("efe_goal_b_learning"))
        schedule_mode = str(first_checkpoint.get("schedule_mode") or schedule_mode)
        schedule_seed = int(first_checkpoint.get("schedule_seed") or schedule_seed)
        if "with_robot" in resume_checkpoints:
            robots = int(resume_checkpoints["with_robot"].get("robot_count") or robots)
            group_robots = robots
        else:
            group_robots = 0
    else:
        if not args.no_clean:
            clean_old_outputs()
        experiment_model = (
            "npc_only_baseline"
            if group_robots == 0
            else (
                "heuristic"
                if args.no_llm
                else (
                    f"{agent_model}__{agent_mode}__authority_{efe_goal_authority}"
                    f"__candidates_{efe_candidate_source}"
                    if agent_mode == "efe" else f"{agent_model}__{agent_mode}"
                )
            )
        )
        experiment_group = canonical_experiment_group(
            scene_id,
            steps,
            group_robots,
            humans,
            experiment_model,
            schedule_mode,
            schedule_seed,
        )
        run_id = utc_run_id()
        experiment_root = (
            Path(args.output_root).expanduser().resolve()
            if str(args.output_root or "").strip() else EXPERIMENT_DIR
        )
        output_dir = experiment_root / _slug(scene_id) / experiment_group / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    scene_path = SCENE_DIR / f"{scene_id}.json"
    raw_scene = json.loads(scene_path.read_text(encoding="utf-8"))
    expected_scene = prepare_scene(raw_scene, robot_count=robots, human_count=humans)
    expected_scene.setdefault("world_state", {})["schedule_mode"] = schedule_mode
    expected_scene.setdefault("world_state", {})["schedule_seed"] = int(schedule_seed)
    expected = expected_events(expected_scene, steps)
    results = []
    should_run_no_robot = args.only in {"both", "no_robot"}
    should_run_with_robot = args.only in {"both", "with_robot"}
    if args.resume:
        checkpoint_experiments = set(resume_checkpoints)
        if args.only == "both":
            should_run_no_robot = "no_robot" in checkpoint_experiments
            should_run_with_robot = "with_robot" in checkpoint_experiments
        else:
            requested_experiment = "no_robot" if args.only == "no_robot" else "with_robot"
            if requested_experiment not in checkpoint_experiments:
                raise RuntimeError(
                    f"requested --only {args.only}, but checkpoint has {sorted(checkpoint_experiments)}"
                )
    if should_run_no_robot:
        results.append(
            run_episode(
                raw_scene,
                scene_id=scene_id,
                steps=steps,
                robot_count=0,
                human_count=humans,
                run_id=run_id,
                agent_model=agent_model,
                use_llm=False,
                agent_mode="no_robot",
                expected=expected,
                output_dir=output_dir,
                matrix_viz=args.matrix_viz,
                replay_scene_interval=args.replay_scene_interval,
                metric_log_interval=args.metric_log_interval,
                schedule_mode=schedule_mode,
                schedule_seed=schedule_seed,
                efe_goal_authority=efe_goal_authority,
                efe_candidate_source=efe_candidate_source,
                efe_explore_navigation=efe_explore_navigation,
                efe_mode=efe_mode,
                efe_goal_b_learning=efe_goal_b_learning,
                resume=args.resume,
            )
        )
    if should_run_with_robot:
        results.append(
            run_episode(
                raw_scene,
                scene_id=scene_id,
                steps=steps,
                robot_count=robots,
                human_count=humans,
                run_id=run_id,
                agent_model=agent_model,
                use_llm=bool(resume_checkpoints.get("with_robot", {}).get("use_llm", not args.no_llm)) if args.resume else not args.no_llm,
                agent_mode=agent_mode,
                expected=expected,
                output_dir=output_dir,
                matrix_viz=args.matrix_viz,
                replay_scene_interval=args.replay_scene_interval,
                metric_log_interval=args.metric_log_interval,
                schedule_mode=schedule_mode,
                schedule_seed=schedule_seed,
                efe_goal_authority=efe_goal_authority,
                efe_candidate_source=efe_candidate_source,
                efe_explore_navigation=efe_explore_navigation,
                efe_mode=efe_mode,
                efe_goal_b_learning=efe_goal_b_learning,
                resume=args.resume,
            )
        )
    summary = {
        "run_id": run_id,
        "scene": scene_id,
        "experiment_group": experiment_group,
        "steps": steps,
        "agent_model": agent_model,
        "agent_mode": agent_mode,
        "efe_goal_authority": efe_goal_authority if agent_mode == "efe" else "",
        "efe_candidate_source": efe_candidate_source if agent_mode == "efe" else "",
        "efe_explore_navigation": (
            efe_explore_navigation if agent_mode == "efe" else ""
        ),
        "efe_mode": efe_mode if agent_mode == "efe" else "",
        "efe_goal_b_learning": (
            efe_goal_b_learning if agent_mode == "efe" else False
        ),
        "goal_review": args.goal_review,
        "retrospective_memory": True,
        "schedule_mode": schedule_mode,
        "schedule_seed": schedule_seed,
        "robots": group_robots,
        "humans": humans,
        "expected_events": expected,
        "created_at": time.time(),
        "runs": [
            {key: value for key, value in result.items() if key != "records"}
            | {
                "final_metrics": {score_key: result["records"][-1][score_key] for score_key in SCORE_KEYS},
                "final_instant_metrics": {
                    score_key: result["records"][-1][score_key]
                    for score_key in INSTANT_SCORE_KEYS
                    if score_key in result["records"][-1]
                },
                "final_avg_metrics": {
                    score_key: result["records"][-1][score_key]
                    for score_key in AVG_SCORE_KEYS
                    if score_key in result["records"][-1]
                },
                "final_blocking_metrics": {
                    "human_blocking_total": result["records"][-1].get("human_blocking_total", 0),
                    "human_blocking_recovered": result["records"][-1].get("human_blocking_recovered", 0),
                    "human_blocking_recovery_rate": result["records"][-1].get("human_blocking_recovery_rate", 0.0),
                },
            }
            for result in results
        ],
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
