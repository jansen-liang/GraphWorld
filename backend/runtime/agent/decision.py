from __future__ import annotations

import copy
import json
import re
from typing import Any

from backend.core.assets.task_library import relevant_skills_for_nodes
from backend.runtime.engine import Orchestrator
from backend.tools.agent import llm_query

from .planning import plan


BAD_STATE_KEYS = {
    "is_dirty",
    "is_open",
    "is_rotten",
    "is_burnt",
    "is_wet",
    "is_full",
    "fill_level",
    "folded",
}
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


HOUSE_RULES = (
    "Prefer actions that directly fix bad states or restore objects toward their initial arrangement when known.",
    "Dirty objects can usually be restored with brush.",
    "Open doors and containers should be closed when they no longer need to stay open.",
    "Rotten or burnt food should use dispose_food; resolved node ids for trash_bin and garbage_station are provided by active_goal.",
    "Trash_bin holds at most 3 trashable food items; only rotten or burnt food belongs in it.",
    "When holding a trash_bin object, dump it only at the resolved garbage_station node id.",
    "When holding a cup with fill_level > 0 or is_full=true, dump it only at a resolved sink node id.",
    "Dirty clothes, towels, and blankets must use laundry_clothes; resolved washer, drying_rack, and wardrobe node ids are provided by active_goal.",
    "Hospital supply and cleaning work must follow active_goal skill node ids exactly; do not replace node ids with semantic_type names.",
    "Use pick before place; use move when the target needed for the next useful action is not nearby.",
    "For restore_initial_position, object and target must be real node ids from high_level_options; never invent node ids from semantic_type names.",
    "If the intended initial_parent is not visible, do not place the held object somewhere else; choose a move/open action that expands visibility toward the target room.",
)


def parse_action_index(text: str, fallback: int = 0) -> int:
    try:
        payload = json.loads(text)
        return int(payload.get("action_index", fallback))
    except Exception:
        decoder = json.JSONDecoder()
        valid_indices: list[int] = []
        for match in re.finditer(r"\{", text or ""):
            try:
                payload, _ = decoder.raw_decode((text or "")[match.start():])
                if isinstance(payload, dict) and "action_index" in payload:
                    valid_indices.append(int(payload.get("action_index", fallback)))
            except Exception:
                continue
        if valid_indices:
            return valid_indices[-1]
        match = re.search(r'"action_index"\s*:\s*(-?\d+)', text or "")
        if match:
            return int(match.group(1))
    return fallback


def parse_goal_review(text: str, allowed_tasks: list[str], active_task: str = "") -> dict[str, str]:
    allowed = set(allowed_tasks)
    fallback_task = active_task if active_task in allowed else (allowed_tasks[0] if allowed_tasks else "maintain_order")
    fallback = {"decision": "keep" if active_task else "switch", "high_level_task": fallback_task}
    try:
        payload = json.loads(text)
    except Exception:
        decoder = json.JSONDecoder()
        payload = None
        for match in re.finditer(r"\{", text or ""):
            try:
                candidate, _ = decoder.raw_decode((text or "")[match.start():])
            except Exception:
                continue
            if isinstance(candidate, dict) and (
                "decision" in candidate or "high_level_task" in candidate
            ):
                payload = candidate
        if payload is None:
            return fallback
    decision = str(payload.get("decision") or "").strip().lower()
    if decision not in {"keep", "switch", "finish", "drop"}:
        decision = fallback["decision"]
    task = str(payload.get("high_level_task") or "").strip()
    if decision == "keep":
        task = active_task or fallback_task
    if decision in {"finish", "drop"}:
        task = "maintain_order"
    if task not in allowed:
        task = fallback_task
        decision = "keep" if task == active_task and active_task else "switch"
    return {"decision": decision, "high_level_task": task}


def _compact_states(states: dict[str, Any]) -> dict[str, Any]:
    compact = {}
    for key in sorted(BAD_STATE_KEYS):
        if key not in states:
            continue
        value = states.get(key)
        if value in (False, None, "", 0, 0.0) and key not in {"fill_level", "folded"}:
            continue
        compact[key] = value
    return compact


def _node_index(observation: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item.get("id") or ""): item for item in observation.get("nodes") or [] if item.get("id")}


def _scene_node_index(scene: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not scene:
        return {}
    nodes = scene.get("nodes") if isinstance(scene.get("nodes"), list) else list((scene.get("node") or {}).values())
    return {str(item.get("id") or ""): item for item in nodes or [] if item.get("id")}


def _scene_edges(scene: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not scene:
        return []
    if isinstance(scene.get("edges"), list):
        return list(scene.get("edges") or [])
    if isinstance(scene.get("edge"), dict):
        return list((scene.get("edge") or {}).values())
    return []


def _room_of(node_id: str, nodes: dict[str, dict[str, Any]]) -> str:
    current = str(node_id or "")
    seen: set[str] = set()
    while current and current not in seen:
        seen.add(current)
        item = nodes.get(current) or {}
        if str(item.get("node_type") or "") == "room":
            return current
        current = str(item.get("parent") or "")
    return ""


def _robot_state(observation: dict[str, Any], nodes: dict[str, dict[str, Any]], agent_id: str) -> dict[str, Any]:
    robot = nodes.get(agent_id) or {}
    holding = ""
    for node_id, item in nodes.items():
        if str(item.get("parent") or "") == agent_id:
            holding = node_id
            break
    world = observation.get("world_state") or {}
    return {
        "step": world.get("step", 0),
        "room_or_parent": robot.get("parent", ""),
        "holding": holding,
        "visible_rooms": world.get("visible_rooms") or [],
    }


def _spatial_issues(
    nodes: dict[str, dict[str, Any]],
    initial_nodes: dict[str, dict[str, Any]],
    agent_id: str = "robot_01",
) -> list[dict[str, Any]]:
    issues = []
    for node_id, item in sorted(nodes.items()):
        if node_id == agent_id or str(item.get("node_type") or "") == "robot":
            continue
        initial = initial_nodes.get(node_id) or {}
        if str(initial.get("node_type") or "") != "movable_object":
            continue
        current_parent = str(item.get("parent") or "")
        initial_parent = str(initial.get("parent") or "")
        if not current_parent or not initial_parent or current_parent == initial_parent:
            continue
        issues.append(
            {
                "id": node_id,
                "semantic_type": item.get("semantic_type"),
                "current_parent": current_parent,
                "initial_parent": initial_parent,
                "initial_room": _room_of(initial_parent, initial_nodes),
            }
        )
    return issues[:20]


def _high_level_options(
    observation: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    initial_nodes: dict[str, dict[str, Any]],
    agent_id: str,
) -> list[str]:
    for node_id, item in sorted(nodes.items()):
        if str(item.get("parent") or "") != agent_id:
            continue
        states = item.get("states") or {}
        semantic = str(item.get("semantic_type") or node_id)
        if semantic in CLOTH_SEMANTICS and (
            states.get("is_dirty") is True or states.get("is_wet") is True or states.get("folded") is False
        ):
            return [f"laundry_clothes {node_id}"]
        if semantic == "food" and (states.get("is_rotten") is True or states.get("is_burnt") is True):
            return [f"dispose_food {node_id}"]
        if semantic == "cup" and (float(states.get("fill_level") or 0.0) > 0.0 or states.get("is_full") is True):
            return [f"empty_cup {node_id}"]
        initial_parent = str((initial_nodes.get(node_id) or {}).get("parent") or "")
        if initial_parent and initial_parent != agent_id:
            return [f"restore_initial_position {node_id} -> {initial_parent}"]

    options = ["maintain_order"]
    for issue in _spatial_issues(nodes, initial_nodes, agent_id):
        options.append(f"restore_initial_position {issue['id']} -> {issue['initial_parent']}")
    for node_id, item in sorted(nodes.items()):
        if node_id == agent_id or str(item.get("node_type") or "") == "robot":
            continue
        states = item.get("states") or {}
        semantic = str(item.get("semantic_type") or node_id)
        if states.get("is_rotten") is True or states.get("is_burnt") is True:
            options.append(f"dispose_food {node_id}")
            continue
        if semantic in CLOTH_SEMANTICS and (
            states.get("is_dirty") is True or states.get("is_wet") is True or states.get("folded") is False
        ):
            options.append(f"laundry_clothes {node_id}")
            continue
        if states.get("is_dirty") is True:
            options.append(f"clean {node_id}")
        if semantic == "cup" and (float(states.get("fill_level") or 0.0) > 0.0 or states.get("is_full") is True):
            options.append(f"empty_cup {node_id}")
        if states.get("is_open") is True:
            options.append(f"close {node_id}")
        if states.get("is_wet") is True:
            options.append(f"dry {node_id}")
        if states.get("folded") is False and semantic in {"clothes", "towel", "blanket"}:
            options.append(f"fold {node_id}")
    return options[:20]


def _initial_context(initial_scene: dict[str, Any] | None, observation: dict[str, Any], agent_id: str) -> dict[str, Any]:
    initial_nodes = _scene_node_index(initial_scene)
    if not initial_nodes:
        return {}
    current_nodes = _node_index(observation)
    issues = _spatial_issues(current_nodes, initial_nodes, agent_id)
    target_rooms = {str(issue.get("initial_room") or "") for issue in issues if issue.get("initial_room")}
    visible_rooms = {str(room_id) for room_id in (observation.get("world_state") or {}).get("visible_rooms") or []}
    relevant_rooms = target_rooms | visible_rooms
    room_edges = []
    for edge in _scene_edges(initial_scene):
        relation = str(edge.get("relation") or "")
        if relation not in {"connected", "connected_to", "next_to", "neighbour"}:
            continue
        source = str(edge.get("source_id") or "")
        target = str(edge.get("target_id") or "")
        if source in relevant_rooms or target in relevant_rooms:
            room_edges.append({"source": source, "target": target, "relation": relation})
    initial_locations = [
        {
            "id": issue["id"],
            "semantic_type": issue.get("semantic_type"),
            "initial_parent": issue["initial_parent"],
            "initial_room": issue["initial_room"],
        }
        for issue in issues
    ]
    interaction_targets = []
    for node_id, item in sorted(initial_nodes.items()):
        actions = [str(action) for action in item.get("interactive_actions") or []]
        if not actions:
            continue
        node_type = str(item.get("node_type") or "")
        if node_type not in {"fixed_object", "control_object", "room"}:
            continue
        room = _room_of(node_id, initial_nodes)
        if node_id not in visible_rooms and node_id not in target_rooms and room not in relevant_rooms:
            continue
        interaction_targets.append(
            {
                "id": node_id,
                "semantic_type": item.get("semantic_type"),
                "node_type": node_type,
                "room": room,
                "actions": actions,
            }
        )
    return {
        "visible_rooms": sorted(visible_rooms),
        "target_rooms": sorted(target_rooms),
        "room_edges": room_edges[:20],
        "initial_locations_for_current_issues": initial_locations[:12],
        "relevant_interaction_targets": interaction_targets[:30],
        "current_spatial_issues": issues[:12],
    }


def _compact_nodes(
    nodes: dict[str, dict[str, Any]],
    initial_nodes: dict[str, dict[str, Any]] | None = None,
    agent_id: str = "robot_01",
) -> list[dict[str, Any]]:
    initial_nodes = initial_nodes or {}
    spatial_issue_ids = {str(issue.get("id") or "") for issue in _spatial_issues(nodes, initial_nodes, agent_id)}
    compact_nodes = []
    for item in nodes.values():
        node_id = str(item.get("id") or "")
        states = item.get("states") or {}
        compact_states = _compact_states(states)
        actions = [str(action) for action in item.get("interactive_actions") or []]
        include = (
            node_id == agent_id
            or node_id in spatial_issue_ids
            or bool(compact_states)
            or any(action in {"dump", "brush", "fold", "open", "close"} for action in actions)
        )
        if not include:
            continue
        compact_nodes.append(
            {
                "id": node_id,
                "semantic_type": item.get("semantic_type"),
                "node_type": item.get("node_type"),
                "parent": item.get("parent"),
                "max_capacity": item.get("max_capacity", ""),
                "states": compact_states,
            }
        )
    return compact_nodes[:20]


def _candidate_hint(candidate: dict[str, Any], nodes: dict[str, dict[str, Any]]) -> str:
    action = str(candidate.get("action") or "")
    target_id = str(candidate.get("target") or "")
    object_id = str(candidate.get("object") or target_id)
    target = nodes.get(target_id) or {}
    obj = nodes.get(object_id) or {}
    target_semantic = str(target.get("semantic_type") or "")
    obj_semantic = str(obj.get("semantic_type") or "")
    obj_states = obj.get("states") or {}
    target_states = target.get("states") or {}
    if action == "brush" and target_states.get("is_dirty") is True:
        return "directly cleans a dirty target"
    if action == "close" and target_states.get("is_open") is True:
        return "closes an open target"
    if action == "fold":
        return "folds dry cloth if legal"
    if action == "pick" and (obj_states.get("is_rotten") is True or obj_states.get("is_burnt") is True):
        return "starts disposal of bad food"
    if action == "place" and target_semantic == "trash_bin":
        return "puts rotten/burnt food into trash bin"
    if action == "dump" and target_semantic == "garbage_station":
        return "empties trash bin and restores discarded contents"
    if action == "dump" and target_semantic == "sink":
        return "empties held cup into sink"
    if action == "move":
        return f"moves near {target_semantic or target_id} for a later action"
    if action == "pick":
        return f"picks up {obj_semantic or object_id} for a later place/dump action"
    return str(candidate.get("reason") or "")


def _candidate_rank(
    candidate: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    initial_nodes: dict[str, dict[str, Any]],
    holding: str,
    active_goal: dict[str, Any] | None,
    issue_ids: set[str],
    issue_current_parents: set[str],
    issue_current_rooms: set[str],
    issue_initial_parents: set[str],
    issue_initial_rooms: set[str],
) -> int:
    action = str(candidate.get("action") or "")
    target_id = str(candidate.get("target") or "")
    object_id = str(candidate.get("object") or target_id)
    target = nodes.get(target_id) or {}
    target_states = target.get("states") or {}
    if active_goal and str(active_goal.get("type") or "") == "skill" and str(active_goal.get("skill") or "") == "dispose_food":
        goal_object = str(active_goal.get("object") or "")
        phase = str(active_goal.get("phase") or "")
        trash_bin = str(active_goal.get("trash_bin") or "")
        trash_bin_home = str(active_goal.get("trash_bin_home") or "")
        garbage_station = str(active_goal.get("garbage_station") or "")
        goal_next_room = str(active_goal.get("next_room") or "")
        goal_robot_room = str(active_goal.get("robot_room") or "")
        goal_object_parent = str((nodes.get(goal_object) or {}).get("parent") or active_goal.get("object_parent") or "")
        goal_object_room = _room_of(goal_object_parent, nodes) if goal_object_parent else str(active_goal.get("object_room") or "")
        target_parent = str((nodes.get(target_id) or {}).get("parent") or "")
        target_semantic = str(target.get("semantic_type") or "").lower()
        connected_rooms = {str(room_id) for room_id in target.get("connected_rooms") or []}
        if (
            action == "open"
            and goal_robot_room
            and goal_next_room
            and str(target.get("door_kind") or "") == "structural"
            and {goal_robot_room, goal_next_room}.issubset(connected_rooms)
        ):
            return 136
        if phase == "collect_food":
            if holding == goal_object:
                if action == "place" and target_id == trash_bin:
                    return 140
                if action == "move" and target_id == trash_bin:
                    return 138
                if action == "move" and goal_next_room and target_id == goal_next_room:
                    return 137
            else:
                if action == "pick" and object_id == goal_object:
                    return 140
                if action == "move" and target_id == goal_object_parent:
                    return 138
                if action == "move" and goal_object_room and target_id == goal_object_room:
                    return 137
                if action == "move" and goal_next_room and target_id == goal_next_room:
                    return 136
        if phase in {"take_bin", "dump_bin"}:
            if holding == trash_bin:
                if action == "dump" and target_id == garbage_station:
                    return 140
                if action == "move" and target_id == garbage_station:
                    return 138
                if action == "move" and goal_next_room and target_id == goal_next_room:
                    return 137
            else:
                if action == "pick" and object_id == trash_bin:
                    return 140
                if action == "move" and target_id == trash_bin:
                    return 138
                if action == "move" and goal_next_room and target_id == goal_next_room:
                    return 137
        if phase == "return_bin":
            if holding == trash_bin:
                if action == "place" and target_id == trash_bin_home:
                    return 140
                if action == "move" and target_id == trash_bin_home:
                    return 138
                if action == "move" and goal_next_room and target_id == goal_next_room:
                    return 137
            else:
                if action == "pick" and object_id == trash_bin:
                    return 140
                if action == "move" and target_id == trash_bin:
                    return 138
                if action == "move" and goal_next_room and target_id == goal_next_room:
                    return 137
    if active_goal and str(active_goal.get("type") or "") == "skill" and str(active_goal.get("skill") or "") == "empty_cup":
        goal_object = str(active_goal.get("object") or "")
        sink = str(active_goal.get("sink") or active_goal.get("target") or "")
        goal_next_room = str(active_goal.get("next_room") or "")
        goal_robot_room = str(active_goal.get("robot_room") or "")
        goal_object_parent = str((nodes.get(goal_object) or {}).get("parent") or active_goal.get("object_parent") or "")
        goal_object_room = _room_of(goal_object_parent, nodes) if goal_object_parent else str(active_goal.get("object_room") or "")
        connected_rooms = {str(room_id) for room_id in target.get("connected_rooms") or []}
        if (
            action == "open"
            and goal_robot_room
            and goal_next_room
            and str(target.get("door_kind") or "") == "structural"
            and {goal_robot_room, goal_next_room}.issubset(connected_rooms)
        ):
            return 136
        if holding == goal_object:
            if action == "dump" and target_id == sink:
                return 140
            if action == "move" and target_id == sink:
                return 138
            if action == "move" and goal_next_room and target_id == goal_next_room:
                return 137
        else:
            if action == "pick" and object_id == goal_object:
                return 140
            if action == "move" and target_id == goal_object_parent:
                return 138
            if action == "move" and goal_object_room and target_id == goal_object_room:
                return 137
            if action == "move" and goal_next_room and target_id == goal_next_room:
                return 136
    if active_goal and str(active_goal.get("type") or "") == "skill" and str(active_goal.get("skill") or "") == "laundry_clothes":
        goal_object = str(active_goal.get("object") or "")
        phase = str(active_goal.get("phase") or "")
        washer = str(active_goal.get("washer") or "")
        washer_button = str(active_goal.get("washer_button") or f"{washer}_button")
        detergent_pool = str(active_goal.get("detergent_pool") or "")
        drying_rack = str(active_goal.get("drying_rack") or "")
        wardrobe = str(active_goal.get("wardrobe") or "")
        goal_next_room = str(active_goal.get("next_room") or "")
        goal_robot_room = str(active_goal.get("robot_room") or "")
        goal_object_parent = str((nodes.get(goal_object) or {}).get("parent") or active_goal.get("object_parent") or "")
        goal_object_room = _room_of(goal_object_parent, nodes) if goal_object_parent else str(active_goal.get("object_room") or "")
        target_parent = str((nodes.get(target_id) or {}).get("parent") or "")
        target_semantic = str(target.get("semantic_type") or "").lower()
        connected_rooms = {str(room_id) for room_id in target.get("connected_rooms") or []}
        if (
            action == "open"
            and goal_robot_room
            and goal_next_room
            and str(target.get("door_kind") or "") == "structural"
            and {goal_robot_room, goal_next_room}.issubset(connected_rooms)
        ):
            return 126
        if phase == "load_detergent":
            washer_open = bool((nodes.get(washer) or {}).get("states", {}).get("is_open", False))
            if not washer_open:
                if action == "open" and target_id == washer:
                    return 130
                if action == "open" and target_parent == washer and target_semantic == "door":
                    return 129
                if action == "move" and target_id == washer:
                    return 128
                if action == "move" and goal_next_room and target_id == goal_next_room:
                    return 126
            elif holding and str((nodes.get(holding) or {}).get("semantic_type") or "") in {"detergent", "laundry_detergent"}:
                if action == "place" and target_id == washer:
                    return 130
                if action == "move" and target_id == washer:
                    return 128
            elif action == "dispense" and target_id == detergent_pool:
                return 130
            elif action == "move" and target_id == detergent_pool:
                return 128
            elif action == "move" and goal_next_room and target_id == goal_next_room:
                return 126
        if phase == "wash_load":
            if holding == goal_object:
                if action == "place" and target_id == washer:
                    return 130
                if action == "open" and target_id == washer:
                    return 129
                if action == "open" and target_parent == washer and target_semantic == "door":
                    return 128
                if action == "move" and target_id == washer:
                    return 127
                if action == "move" and goal_next_room and target_id == goal_next_room:
                    return 126
            else:
                if action == "pick" and object_id == goal_object:
                    return 130
                if action == "move" and target_id == goal_object_parent:
                    return 128
                if action == "move" and goal_object_room and target_id == goal_object_room:
                    return 127
                if action == "move" and goal_next_room and target_id == goal_next_room:
                    return 126
        if phase == "start_washer":
            if action == "close" and target_id == washer:
                return 130
            if action == "close" and target_parent == washer and target_semantic == "door":
                return 129
            if action == "press" and target_id in {washer, washer_button}:
                return 128
            if action == "move" and target_id in {washer, washer_button}:
                return 127
            if action == "move" and goal_next_room and target_id == goal_next_room:
                return 126
        if phase == "dry":
            if holding == goal_object:
                if action == "place" and target_id == drying_rack:
                    return 130
                if action == "move" and target_id == drying_rack:
                    return 128
                if action == "move" and goal_next_room and target_id == goal_next_room:
                    return 127
            else:
                if action == "pick" and object_id == goal_object:
                    return 130
                if action == "open" and target_id == goal_object_parent:
                    return 129
                if action == "open" and target_parent == goal_object_parent and target_semantic == "door":
                    return 128
                if action == "move" and target_id == goal_object_parent:
                    return 127
                if action == "move" and goal_object_room and target_id == goal_object_room:
                    return 126
                if action == "move" and goal_next_room and target_id == goal_next_room:
                    return 125
        if phase == "fold":
            if action == "fold" and target_id == goal_object:
                return 130
            if action == "move" and target_id == goal_object_parent:
                return 128
            if action == "move" and goal_object_room and target_id == goal_object_room:
                return 127
            if action == "move" and goal_next_room and target_id == goal_next_room:
                return 126
        if phase == "store":
            if holding == goal_object:
                if action == "place" and target_id == wardrobe:
                    return 130
                if action == "open" and target_id == wardrobe:
                    return 129
                if action == "open" and target_parent == wardrobe and target_semantic == "door":
                    return 128
                if action == "move" and target_id == wardrobe:
                    return 127
                if action == "move" and goal_next_room and target_id == goal_next_room:
                    return 126
            else:
                if action == "pick" and object_id == goal_object:
                    return 130
                if action == "move" and target_id == goal_object_parent:
                    return 128
                if action == "move" and goal_object_room and target_id == goal_object_room:
                    return 127
                if action == "move" and goal_next_room and target_id == goal_next_room:
                    return 126
    if active_goal and str(active_goal.get("type") or "") == "skill" and str(active_goal.get("skill") or "") == "dishwash_dishes":
        goal_object = str(active_goal.get("object") or "")
        phase = str(active_goal.get("phase") or "")
        dishwasher = str(active_goal.get("dishwasher") or active_goal.get("target") or "")
        dishwasher_button = str(active_goal.get("dishwasher_button") or f"{dishwasher}_button")
        return_target = str(active_goal.get("return_target") or "")
        goal_next_room = str(active_goal.get("next_room") or "")
        goal_object_parent = str((nodes.get(goal_object) or {}).get("parent") or active_goal.get("object_parent") or "")
        goal_object_room = _room_of(goal_object_parent, nodes) if goal_object_parent else str(active_goal.get("object_room") or "")
        target_parent = str((nodes.get(target_id) or {}).get("parent") or "")
        target_semantic = str(target.get("semantic_type") or "").lower()
        if phase == "load":
            if holding == goal_object:
                if action == "place" and target_id == dishwasher:
                    return 130
                if action == "open" and target_id == dishwasher:
                    return 129
                if action == "open" and target_parent == dishwasher and target_semantic == "door":
                    return 128
                if action == "move" and target_id == dishwasher:
                    return 127
            else:
                if action == "pick" and object_id == goal_object:
                    return 130
                if action == "move" and target_id == goal_object_parent:
                    return 128
                if action == "move" and target_id == goal_object_room:
                    return 127
        if phase == "run":
            if action == "close" and target_id == dishwasher:
                return 130
            if action == "close" and target_parent == dishwasher and target_semantic == "door":
                return 129
            if action == "press" and target_id in {dishwasher, dishwasher_button}:
                return 128
            if action == "move" and target_id in {dishwasher, dishwasher_button}:
                return 127
        if phase == "washing_wait" and action == "move" and target_id == dishwasher:
            return 120
        if phase == "unload":
            if holding == goal_object:
                if action == "place" and target_id == return_target:
                    return 130
                if action == "move" and target_id == return_target:
                    return 128
            else:
                if action == "pick" and object_id == goal_object and target_id == dishwasher:
                    return 130
                if action == "open" and target_id == dishwasher:
                    return 129
                if action == "open" and target_parent == dishwasher and target_semantic == "door":
                    return 128
                if action == "move" and target_id == dishwasher:
                    return 127
        if action == "move" and goal_next_room and target_id == goal_next_room:
            return 126
    if active_goal and str(active_goal.get("type") or "") == "skill" and str(active_goal.get("skill") or "") == "heat_milk":
        goal_object = str(active_goal.get("object") or "")
        phase = str(active_goal.get("phase") or "")
        microwave = str(active_goal.get("microwave") or active_goal.get("target") or "")
        microwave_button = str(active_goal.get("microwave_button") or f"{microwave}_button")
        return_target = str(active_goal.get("return_target") or "")
        goal_object_parent = str((nodes.get(goal_object) or {}).get("parent") or active_goal.get("object_parent") or "")
        target_parent = str((nodes.get(target_id) or {}).get("parent") or "")
        target_semantic = str(target.get("semantic_type") or "").lower()
        if phase == "load":
            if holding == goal_object:
                if action == "place" and target_id == microwave:
                    return 130
                if action == "open" and target_id == microwave:
                    return 129
                if action == "open" and target_parent == microwave and target_semantic == "door":
                    return 128
                if action == "move" and target_id == microwave:
                    return 127
            else:
                if action == "pick" and object_id == goal_object:
                    return 130
                if action == "move" and target_id == goal_object_parent:
                    return 128
        if phase == "run":
            if action == "close" and target_id == microwave:
                return 130
            if action == "close" and target_parent == microwave and target_semantic == "door":
                return 129
            if action == "press" and target_id in {microwave, microwave_button}:
                return 128
            if action == "move" and target_id in {microwave, microwave_button}:
                return 127
        if phase == "waiting" and action == "move" and target_id == microwave:
            return 120
        if phase == "unload":
            if holding == goal_object:
                if action == "place" and target_id == return_target:
                    return 130
                if action == "move" and target_id == return_target:
                    return 128
            else:
                if action == "pick" and object_id == goal_object and target_id == microwave:
                    return 130
                if action == "open" and target_id == microwave:
                    return 129
                if action == "open" and target_parent == microwave and target_semantic == "door":
                    return 128
                if action == "move" and target_id == microwave:
                    return 127
    if active_goal and str(active_goal.get("type") or "") == "skill" and str(active_goal.get("skill") or "") == "cook_egg":
        egg_id = str(active_goal.get("input_object") or "")
        output_id = str(active_goal.get("output_id") or "")
        phase = str(active_goal.get("phase") or "")
        stove = str(active_goal.get("stove") or active_goal.get("target") or "")
        stove_button = str(active_goal.get("stove_button") or f"{stove}_button")
        return_target = str(active_goal.get("return_target") or "")
        target_parent = str((nodes.get(target_id) or {}).get("parent") or "")
        target_semantic = str(target.get("semantic_type") or "").lower()
        if phase == "prepare":
            if holding == egg_id:
                if action == "place" and target_id == stove:
                    return 130
                if action == "move" and target_id == stove:
                    return 128
            else:
                if action == "pick" and object_id == egg_id:
                    return 130
                if action == "move" and target_id == str((nodes.get(egg_id) or {}).get("parent") or ""):
                    return 128
        if phase == "cook":
            if action == "press" and target_id in {stove, stove_button}:
                return 130
            if action == "move" and target_id in {stove, stove_button}:
                return 128
        if phase == "waiting" and action == "move" and target_id == stove:
            return 120
        if phase == "serve":
            if holding == output_id:
                if action == "place" and target_id == return_target:
                    return 130
                if action == "move" and target_id == return_target:
                    return 128
            else:
                if action == "pick" and object_id == output_id and target_id == stove:
                    return 130
                if action == "open" and target_id == stove:
                    return 129
                if action == "open" and target_parent == stove and target_semantic == "door":
                    return 128
                if action == "move" and target_id == stove:
                    return 127
    if active_goal and str(active_goal.get("type") or "") == "skill" and str(active_goal.get("skill") or "") == "craft_sandwich":
        bread_id = str(active_goal.get("bread") or "")
        tomato_id = str(active_goal.get("tomato") or "")
        output_id = str(active_goal.get("output_id") or "")
        phase = str(active_goal.get("phase") or "")
        workbench = str(active_goal.get("workbench") or active_goal.get("target") or "")
        workbench_button = str(active_goal.get("workbench_button") or f"{workbench}_button")
        return_target = str(active_goal.get("return_target") or "")
        target_parent = str((nodes.get(target_id) or {}).get("parent") or "")
        target_semantic = str(target.get("semantic_type") or "").lower()
        if phase == "collect":
            missing = [item_id for item_id in (bread_id, tomato_id) if str((nodes.get(item_id) or {}).get("parent") or "") != workbench]
            if holding in missing:
                if action == "place" and target_id == workbench:
                    return 130
                if action == "move" and target_id == workbench:
                    return 128
            elif missing:
                next_item = missing[0]
                if action == "pick" and object_id == next_item:
                    return 130
                if action == "move" and target_id == str((nodes.get(next_item) or {}).get("parent") or ""):
                    return 128
        if phase == "craft":
            if action == "press" and target_id in {workbench, workbench_button}:
                return 130
            if action == "move" and target_id in {workbench, workbench_button}:
                return 128
        if phase == "waiting" and action == "move" and target_id == workbench:
            return 120
        if phase == "serve":
            if holding == output_id:
                if action == "place" and target_id == return_target:
                    return 130
                if action == "move" and target_id == return_target:
                    return 128
            else:
                if action == "pick" and object_id == output_id and target_id == workbench:
                    return 130
                if action == "move" and target_id == workbench:
                    return 127
    if active_goal and str(active_goal.get("type") or "") == "skill" and str(active_goal.get("skill") or "") == "assemble_product":
        component_a = str(active_goal.get("component_a") or "")
        component_b = str(active_goal.get("component_b") or "")
        output_id = str(active_goal.get("output_id") or "")
        phase = str(active_goal.get("phase") or "")
        line = str(active_goal.get("assembly_line") or active_goal.get("target") or "")
        line_button = str(active_goal.get("assembly_line_button") or f"{line}_button")
        return_target = str(active_goal.get("return_target") or "")
        target_parent = str((nodes.get(target_id) or {}).get("parent") or "")
        if phase == "collect":
            missing = [item_id for item_id in (component_a, component_b) if str((nodes.get(item_id) or {}).get("parent") or "") != line]
            if holding in missing:
                if action == "place" and target_id == line:
                    return 130
                if action == "move" and target_id == line:
                    return 128
            elif missing:
                next_item = missing[0]
                if action == "pick" and object_id == next_item:
                    return 130
                if action == "move" and target_id == str((nodes.get(next_item) or {}).get("parent") or ""):
                    return 128
        if phase == "run":
            if action == "press" and target_id in {line, line_button}:
                return 130
            if action == "move" and target_id in {line, line_button}:
                return 128
        if phase == "waiting" and action == "move" and target_id == line:
            return 120
        if phase == "inspect":
            if holding == output_id:
                if action == "place" and target_id == return_target:
                    return 130
                if action == "move" and target_id == return_target:
                    return 128
            else:
                if action == "pick" and object_id == output_id and target_id == line:
                    return 130
                if action == "move" and target_id == line:
                    return 127
    if active_goal and str(active_goal.get("type") or "") == "skill" and str(active_goal.get("skill") or "") == "brew_coffee":
        cup_id = str(active_goal.get("cup") or "")
        beans_id = str(active_goal.get("coffee_beans") or "")
        output_id = str(active_goal.get("output_id") or "")
        phase = str(active_goal.get("phase") or "")
        machine = str(active_goal.get("coffee_machine") or active_goal.get("target") or "")
        machine_button = str(active_goal.get("coffee_machine_button") or f"{machine}_button")
        return_target = str(active_goal.get("return_target") or "")
        target_parent = str((nodes.get(target_id) or {}).get("parent") or "")
        target_semantic = str(target.get("semantic_type") or "").lower()
        if phase == "prepare":
            missing = [item_id for item_id in (cup_id, beans_id) if str((nodes.get(item_id) or {}).get("parent") or "") != machine]
            if holding in missing:
                if action == "place" and target_id == machine:
                    return 130
                if action == "move" and target_id == machine:
                    return 128
            elif missing:
                next_item = missing[0]
                if action == "pick" and object_id == next_item:
                    return 130
                if action == "move" and target_id == str((nodes.get(next_item) or {}).get("parent") or ""):
                    return 128
        if phase == "run":
            if action == "press" and target_id in {machine, machine_button}:
                return 130
            if action == "move" and target_id in {machine, machine_button}:
                return 128
        if phase == "waiting" and action == "move" and target_id == machine:
            return 120
        if phase == "serve":
            if holding == cup_id:
                if action == "place" and target_id == return_target:
                    return 130
                if action == "move" and target_id == return_target:
                    return 128
            else:
                if action == "pick" and object_id == cup_id and target_id == machine:
                    return 130
                if action == "open" and target_id == machine:
                    return 129
                if action == "open" and target_parent == machine and target_semantic == "door":
                    return 128
                if action == "move" and target_id == machine:
                    return 127
    if active_goal and str(active_goal.get("type") or "") == "skill" and str(active_goal.get("skill") or "") == "print_document":
        printer = str(active_goal.get("printer") or active_goal.get("target") or "")
        printer_button = str(active_goal.get("printer_button") or f"{printer}_button")
        receipt_id = str(active_goal.get("receipt_id") or "")
        return_target = str(active_goal.get("return_target") or "")
        phase = str(active_goal.get("phase") or "")
        goal_next_room = str(active_goal.get("next_room") or "")
        if phase == "print" and action == "press" and target_id in {printer, printer_button}:
            return 130
        if phase == "print" and action == "move" and target_id in {printer, printer_button}:
            return 128
        if phase == "collect":
            if action == "pick" and object_id == receipt_id and target_id == printer:
                return 130
            if action == "move" and target_id == printer:
                return 128
        if phase == "place":
            if action == "place" and target_id == return_target:
                return 130
            if action == "move" and target_id == return_target:
                return 128
        if action == "move" and goal_next_room and target_id == goal_next_room:
            return 126
    if active_goal and str(active_goal.get("type") or "") == "skill" and str(active_goal.get("skill") or "") in HOSPITAL_RETURN_SKILLS:
        goal_object = str(active_goal.get("object") or "")
        goal_target = str(active_goal.get("target") or "")
        goal_next_room = str(active_goal.get("next_room") or "")
        goal_robot_room = str(active_goal.get("robot_room") or "")
        goal_object_parent = str((nodes.get(goal_object) or {}).get("parent") or active_goal.get("object_parent") or "")
        goal_object_room = _room_of(goal_object_parent, nodes) if goal_object_parent else str(active_goal.get("object_room") or "")
        target_parent = str((nodes.get(target_id) or {}).get("parent") or "")
        target_semantic = str(target.get("semantic_type") or "").lower()
        connected_rooms = {str(room_id) for room_id in target.get("connected_rooms") or []}
        if (
            action == "open"
            and goal_robot_room
            and goal_next_room
            and str(target.get("door_kind") or "") == "structural"
            and {goal_robot_room, goal_next_room}.issubset(connected_rooms)
        ):
            return 136
        if holding == goal_object:
            if action == "place" and target_id == goal_target:
                return 140
            if action == "open" and target_id == goal_target:
                return 139
            if action == "open" and target_parent == goal_target and target_semantic == "door":
                return 138
            if action == "move" and target_id == goal_target:
                return 137
            if action == "move" and goal_next_room and target_id == goal_next_room:
                return 136
        else:
            if action == "pick" and object_id == goal_object:
                return 140
            if action == "open" and target_id == goal_object_parent:
                return 139
            if action == "open" and target_parent == goal_object_parent and target_semantic == "door":
                return 138
            if action == "move" and target_id == goal_object_parent:
                return 137
            if action == "move" and goal_object_room and target_id == goal_object_room:
                return 136
            if action == "move" and goal_next_room and target_id == goal_next_room:
                return 135
    if active_goal and str(active_goal.get("type") or "") == "skill" and str(active_goal.get("skill") or "") in HOSPITAL_CLEAN_SKILLS:
        goal_target = str(active_goal.get("target") or active_goal.get("object") or "")
        goal_next_room = str(active_goal.get("next_room") or "")
        goal_robot_room = str(active_goal.get("robot_room") or "")
        connected_rooms = {str(room_id) for room_id in target.get("connected_rooms") or []}
        if (
            action == "open"
            and goal_robot_room
            and goal_next_room
            and str(target.get("door_kind") or "") == "structural"
            and {goal_robot_room, goal_next_room}.issubset(connected_rooms)
        ):
            return 136
        if action == "brush" and target_id == goal_target:
            return 140
        if action == "move" and target_id == goal_target:
            return 138
        if action == "move" and goal_next_room and target_id == goal_next_room:
            return 137
    if active_goal and str(active_goal.get("type") or "") == "restore_initial_position":
        goal_object = str(active_goal.get("object") or "")
        goal_target = str(active_goal.get("target") or "")
        goal_target_room = _room_of(goal_target, initial_nodes) if goal_target else ""
        goal_object_parent = str((nodes.get(goal_object) or {}).get("parent") or active_goal.get("object_parent") or "")
        goal_object_room = _room_of(goal_object_parent, nodes) if goal_object_parent else ""
        goal_object_room = goal_object_room or str(active_goal.get("object_room") or "")
        goal_next_room = str(active_goal.get("next_room") or "")
        goal_robot_room = str(active_goal.get("robot_room") or "")
        target_parent = str((nodes.get(target_id) or {}).get("parent") or "")
        target_semantic = str(target.get("semantic_type") or "").lower()
        connected_rooms = {str(room_id) for room_id in target.get("connected_rooms") or []}
        if (
            action == "open"
            and goal_robot_room
            and goal_next_room
            and str(target.get("door_kind") or "") == "structural"
            and {goal_robot_room, goal_next_room}.issubset(connected_rooms)
        ):
            return 116
        if holding == goal_object:
            if action == "place" and target_id == goal_target:
                return 120
            if action == "open" and target_id == goal_target:
                return 115
            if action == "open" and target_parent == goal_target and target_semantic == "door":
                return 114
            if action == "move" and target_id == goal_target:
                return 113
            if action == "move" and goal_target_room and target_id == goal_target_room:
                return 112
            if action == "move" and goal_next_room and target_id == goal_next_room:
                return 111
        else:
            if action == "pick" and object_id == goal_object:
                return 120
            if action == "move" and target_id == goal_object_parent:
                return 115
            if action == "move" and goal_object_room and target_id == goal_object_room:
                return 114
            if action == "move" and goal_next_room and target_id == goal_next_room:
                return 113

    if holding:
        initial_parent = str((initial_nodes.get(holding) or {}).get("parent") or "")
        initial_room = _room_of(initial_parent, initial_nodes) if initial_parent else ""
        target_parent = str((nodes.get(target_id) or {}).get("parent") or "")
        target_semantic = str(target.get("semantic_type") or "").lower()
        if action == "place" and target_id == initial_parent:
            return 100
        if action == "dump":
            return 95
        if action == "open" and target_id == initial_parent:
            return 94
        if action == "open" and target_parent == initial_parent and target_semantic == "door":
            return 93
        if action == "move" and target_id == initial_parent:
            return 92
        if action == "move" and initial_room and target_id == initial_room:
            return 91
        if action in {"open", "move"}:
            return 80
        if action == "place":
            return -100
    if action == "pick" and object_id in issue_ids:
        return 90
    if issue_ids and action == "move" and target_id in issue_current_parents:
        return 89
    if issue_ids and action == "move" and target_id in issue_current_rooms:
        return 88
    if issue_ids and action == "move" and target_id in issue_initial_parents:
        return 87
    if issue_ids and action == "move" and target_id in issue_initial_rooms:
        return 86
    if action == "brush" and target_states.get("is_dirty") is True:
        return 85
    if action == "close" and target_states.get("is_open") is True:
        return 55 if issue_ids else 75
    if action == "open":
        return 20
    if action == "move":
        return 60
    if action == "fold":
        return 55
    if action == "pick":
        return 40
    if action == "press":
        return -50
    return 0


def _ranked_prompt_candidates(
    candidates: list[dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
    initial_nodes: dict[str, dict[str, Any]],
    active_goal: dict[str, Any] | None = None,
    agent_id: str = "robot_01",
) -> list[tuple[int, int, dict[str, Any]]]:
    holding = ""
    for node_id, item in nodes.items():
        if str(item.get("parent") or "") == agent_id:
            holding = node_id
            break
    issues = _spatial_issues(nodes, initial_nodes, agent_id)
    issue_ids = {str(issue.get("id") or "") for issue in issues}
    issue_current_parents = {str(issue.get("current_parent") or "") for issue in issues if issue.get("current_parent")}
    issue_current_rooms = {_room_of(parent_id, nodes) for parent_id in issue_current_parents}
    issue_initial_parents = {str(issue.get("initial_parent") or "") for issue in issues if issue.get("initial_parent")}
    issue_initial_rooms = {str(issue.get("initial_room") or "") for issue in issues if issue.get("initial_room")}
    ranked = [
        (
            _candidate_rank(
                candidate,
                nodes,
                initial_nodes,
                holding,
                active_goal,
                issue_ids,
                issue_current_parents,
                {room_id for room_id in issue_current_rooms if room_id},
                issue_initial_parents,
                issue_initial_rooms,
            ),
            index,
            candidate,
        )
        for index, candidate in enumerate(candidates)
    ]
    ranked.sort(key=lambda item: (-item[0], item[1]))
    useful = [(score, index, candidate) for score, index, candidate in ranked if score > -100]
    return useful[:18] if useful else ranked[:18]


def _prompt_candidates(
    candidates: list[dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
    initial_nodes: dict[str, dict[str, Any]],
    active_goal: dict[str, Any] | None = None,
    agent_id: str = "robot_01",
) -> list[tuple[int, dict[str, Any]]]:
    return [
        (index, candidate)
        for _, index, candidate in _ranked_prompt_candidates(candidates, nodes, initial_nodes, active_goal, agent_id)
    ]


def _compact_candidates(
    candidates: list[dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
    initial_nodes: dict[str, dict[str, Any]],
    active_goal: dict[str, Any] | None = None,
    agent_id: str = "robot_01",
) -> list[dict[str, Any]]:
    compact = []
    for idx, candidate in _prompt_candidates(candidates, nodes, initial_nodes, active_goal, agent_id):
        payload = {
            "action_index": idx,
            "a": candidate.get("action"),
            "t": candidate.get("target"),
            "o": candidate.get("object", ""),
            "hint": _candidate_hint(candidate, nodes),
        }
        compact.append(payload)
    return compact


def llm_review_goal(
    observation: dict[str, Any],
    agent_model: str,
    *,
    initial_scene: dict[str, Any] | None = None,
    active_goal: dict[str, Any] | None = None,
    high_level_options: list[str] | None = None,
    recent_history: list[dict[str, Any]] | None = None,
    agent_id: str = "robot_01",
) -> tuple[dict[str, str], str]:
    nodes = _node_index(observation)
    initial_nodes = _scene_node_index(initial_scene)
    active_task = str((active_goal or {}).get("task") or "")
    options = []
    for task in [active_task, *(high_level_options or []), *_high_level_options(observation, nodes, initial_nodes, agent_id)]:
        if task and task not in options:
            options.append(task)
    if "maintain_order" not in options:
        options.insert(0, "maintain_order")
    prompt = {
        "task": "Review the active high-level goal before choosing an action. Decide whether to keep it, switch to another listed goal, finish it, or drop it.",
        "robot_state": _robot_state(observation, nodes, agent_id),
        "rules": [
            "Choose high_level_task only from high_level_options or active_goal.task.",
            "Use keep only if the active goal still matches the held object, object state, and recent progress.",
            "Use switch if recent actions repeat without progress or the held object no longer matches the active goal.",
            "Use finish or drop when the active goal is already satisfied, invalid, or no longer useful.",
        ],
        "active_goal": active_goal or {},
        "recent_history": (recent_history or [])[-10:],
        "high_level_options": options[:20],
        "visible_nodes": _compact_nodes(nodes, initial_nodes, agent_id),
        "response_format": {"decision": "keep|switch|finish|drop", "high_level_task": "exact listed option"},
    }
    answer = llm_query(
        system_prompt=(
            "Return only compact JSON with exactly two fields: "
            '{"decision": <keep|switch|finish|drop>, "high_level_task": <string>}. '
            "Do not include markdown, explanations, or thinking."
        ),
        user_query=json.dumps(prompt, ensure_ascii=True),
        agent=agent_model,
        timeout=180,
    )
    return parse_goal_review(answer, options[:20], active_task), answer


def llm_choose_action(
    candidates: list[dict[str, Any]],
    observation: dict[str, Any],
    agent_model: str,
    initial_scene: dict[str, Any] | None = None,
    active_goal: dict[str, Any] | None = None,
    agent_id: str = "robot_01",
) -> tuple[dict[str, Any], str]:
    if not candidates:
        raise ValueError("no legal action candidates")
    nodes = _node_index(observation)
    initial_nodes = _scene_node_index(initial_scene)
    prompt = {
        "task": "Restore the scene toward the initial good arrangement. Choose one high_level_task from high_level_options or active_goal.task, then one legal low_level action_index that advances it.",
        "robot_state": _robot_state(observation, nodes, agent_id),
        "rules": HOUSE_RULES,
        "active_goal": active_goal or {},
        "skills": relevant_skills_for_nodes(nodes, active_goal),
        "initial_context": _initial_context(initial_scene, observation, agent_id),
        "high_level_options": _high_level_options(observation, nodes, initial_nodes, agent_id),
        "visible_nodes": _compact_nodes(nodes, initial_nodes, agent_id),
        "candidates": _compact_candidates(candidates, nodes, initial_nodes, active_goal, agent_id),
        "response_format": {"high_level_task": "exact string from high_level_options or active_goal.task", "action_index": 0},
    }
    answer = llm_query(
        system_prompt=(
            "Return only compact JSON with exactly two fields: "
            '{"high_level_task": <string>, "action_index": <integer>}. '
            "Do not include markdown, explanations, or thinking."
        ),
        user_query=json.dumps(prompt, ensure_ascii=True),
        agent=agent_model,
        timeout=180,
    )
    index = parse_action_index(answer, 0)
    if index < 0 or index >= len(candidates):
        index = 0
    ranked = _ranked_prompt_candidates(candidates, nodes, initial_nodes, active_goal, agent_id)
    score_by_index = {candidate_index: score for score, candidate_index, _ in ranked}
    if ranked:
        best_score, best_index, _ = ranked[0]
        selected_score = score_by_index.get(index, -100)
        if (active_goal and best_score >= 110) or best_score - selected_score >= 20:
            index = best_index
    return candidates[index], answer


def llm_choose_reactive_action(
    candidates: list[dict[str, Any]],
    observation: dict[str, Any],
    agent_model: str,
    *,
    recent_scores: list[dict[str, Any]] | None = None,
    agent_id: str = "robot_01",
) -> tuple[dict[str, Any], str]:
    if not candidates:
        raise ValueError("no legal action candidates")
    nodes = _node_index(observation)
    prompt = {
        "role": "You are a maintenance robot in a changing human environment.",
        "task": "Choose one legal action that is likely to improve or preserve the world score. Use only local visible graph information and recent score changes.",
        "robot_state": _robot_state(observation, nodes, agent_id),
        "recent_scores": (recent_scores or [])[-10:],
        "visible_nodes": _compact_nodes(nodes, {}, agent_id),
        "candidates": _compact_candidates(candidates, nodes, {}, None, agent_id),
        "response_format": {"action_index": 0},
    }
    answer = llm_query(
        system_prompt=(
            "Return only compact JSON with exactly one field: "
            '{"action_index": <integer>}. '
            "Do not include markdown, explanations, or thinking."
        ),
        user_query=json.dumps(prompt, ensure_ascii=True),
        agent=agent_model,
        timeout=180,
    )
    index = parse_action_index(answer, 0)
    if index < 0 or index >= len(candidates):
        index = 0
    return candidates[index], answer


def ranked_rule_candidates(
    candidates: list[dict[str, Any]],
    observation: dict[str, Any],
    initial_scene: dict[str, Any] | None = None,
    active_goal: dict[str, Any] | None = None,
    agent_id: str = "robot_01",
) -> list[tuple[int, int, dict[str, Any]]]:
    nodes = _node_index(observation)
    initial_nodes = _scene_node_index(initial_scene)
    return _ranked_prompt_candidates(candidates, nodes, initial_nodes, active_goal, agent_id)


def fallback_choose_action(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    for action_name in ("brush", "close"):
        for candidate in candidates:
            if candidate.get("action") == action_name:
                return candidate
    return candidates[0]


def decide(memory: dict[str, Any], task: str = "maintain_order", agent_id: str = "robot_01") -> dict[str, Any]:
    candidates = plan(memory, task)
    if not candidates:
        return {}
    selected = max(candidates, key=lambda item: int(item.get("priority") or 0))
    action = {key: value for key, value in selected.items() if key != "priority"}
    action.setdefault("agent", agent_id)
    return action


def execute(orchestrator: Orchestrator, action: dict[str, Any], agent_id: str = "robot_01") -> dict[str, Any]:
    if not action:
        return orchestrator.step([], [])
    payload = copy.deepcopy(action)
    payload.setdefault("agent", agent_id)
    return orchestrator.step([payload], [])


__all__ = [
    "decide",
    "execute",
    "fallback_choose_action",
    "llm_choose_action",
    "parse_action_index",
    "ranked_rule_candidates",
]
