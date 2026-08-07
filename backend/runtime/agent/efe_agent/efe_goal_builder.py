"""efe_goal_builder — skill-goal construction for the EFE agent.

Ports the experiment pipeline's goal detectors/builders (from run_experiment.py)
into the EFE package so the EFE loop can generate its own skill goals with full
execution detail (phase, resolved node ids) instead of depending on the
experiment pipeline to supply an active_goal.

These are the pipeline's goal types:
  - restore_initial_position  (movable object moved from baseline parent)
  - skill/dispose_food        (rotten/burnt food → trash_bin → garbage_station)
  - skill/empty_cup           (full cup → sink)
  - skill/laundry_clothes     (dirty/wet/unfolded cloth → washer → dry → fold → wardrobe)
  - skill/hospital_*          (hospital supply returns / cleaning)

Every builder returns a goal dict with the same fields the pipeline produces
(phase, trash_bin, sink, washer, ...) so that the ranker in decision.py can
score actions against them.
"""

from __future__ import annotations

import copy
from typing import Any


# ============================================================
# constants (ported from run_experiment.py)
# ============================================================

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


# ============================================================
# scene helpers
# ============================================================

def node(scene: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    for item in scene.get("nodes") or []:
        if item.get("id") == node_id:
            return item
    return None


def room_of(scene: dict[str, Any], node_id: str) -> str:
    current_id = str(node_id or "")
    visited: set[str] = set()
    while current_id and current_id not in visited:
        visited.add(current_id)
        item = node(scene, current_id)
        if not item:
            return ""
        if str(item.get("node_type") or "") == "room":
            return current_id
        current_id = str(item.get("parent") or "")
    return ""


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


# ============================================================
# goal builders (ported 1:1 from run_experiment.py)
# ============================================================

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
        # A new food issue may appear while the robot is returning an empty
        # bin from a previous disposal.  The food is not inside the held bin,
        # so going back to the garbage station cannot advance the workflow.
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


def hospital_skill_for_return_issue(node_id: str, current: dict[str, Any], initial: dict[str, Any]) -> str:
    semantic = str(current.get("semantic_type") or initial.get("semantic_type") or "")
    if semantic == "bed_sheet":
        states = current.get("states") or {}
        if states.get("is_dirty") is True:
            return "collect_dirty_linen"
        # Only the designated spare sheet belongs in the supply cabinet.
        # The clean sheet installed on the treatment bed is already in a valid
        # in-use state; treating every clean bed_sheet as stock creates a
        # bed <-> cabinet restore loop with the baseline-position goal.
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


# ============================================================
# detectors — visible subset (based on observation)
# ============================================================

def visible_restore_goals(observation: dict[str, Any], baseline: dict[str, Any], step: int) -> list[dict[str, Any]]:
    baseline_nodes = {str(item.get("id") or ""): item for item in baseline.get("nodes") or [] if item.get("id")}
    current_nodes = {str(item.get("id") or ""): item for item in observation.get("nodes") or [] if item.get("id")}
    goals: list[dict[str, Any]] = []
    for node_id, current in sorted(current_nodes.items()):
        initial = baseline_nodes.get(node_id) or {}
        if str(initial.get("node_type") or "") != "movable_object":
            continue
        semantic = str(current.get("semantic_type") or initial.get("semantic_type") or "")
        # Hospital lifecycle objects have task-defined destinations that may
        # intentionally differ from their baseline parent.  Letting generic
        # restore own them creates bed <-> linen-bin/cabinet reversal loops.
        if scene_type(baseline) == "hospital" and semantic in HOSPITAL_MANAGED_SEMANTICS:
            continue
        current_parent = str(current.get("parent") or "")
        initial_parent = str(initial.get("parent") or "")
        if not current_parent or not initial_parent or current_parent == initial_parent:
            continue
        current_parent_node = current_nodes.get(current_parent) or {}
        if str(current_parent_node.get("node_type") or "") == "human":
            parent_states = current_parent_node.get("states") or {}
            if parent_states.get("checked_out") is not True:
                continue
        goals.append(make_restore_goal(node_id, initial_parent, step, source="visible_spatial_issue"))
    return goals


def visible_dispose_food_goals(observation: dict[str, Any], scene: dict[str, Any], step: int, baseline: dict[str, Any]) -> list[dict[str, Any]]:
    goals: list[dict[str, Any]] = []
    for item in sorted(observation.get("nodes") or [], key=lambda node_item: str(node_item.get("id") or "")):
        if str(item.get("semantic_type") or "") != "food":
            continue
        states = item.get("states") or {}
        if states.get("is_rotten") is True or states.get("is_burnt") is True:
            goal = make_dispose_food_goal(str(item.get("id") or ""), step, source="visible_bad_food", scene=scene, baseline=baseline)
            if goal:
                goals.append(goal)
    return goals


def visible_empty_cup_goals(observation: dict[str, Any], scene: dict[str, Any], step: int) -> list[dict[str, Any]]:
    goals: list[dict[str, Any]] = []
    for item in sorted(observation.get("nodes") or [], key=lambda node_item: str(node_item.get("id") or "")):
        if str(item.get("semantic_type") or "") != "cup":
            continue
        states = item.get("states") or {}
        if float(states.get("fill_level") or 0.0) > 0.0 or states.get("is_full") is True:
            goal = make_empty_cup_goal(str(item.get("id") or ""), step, source="visible_full_cup", scene=scene)
            if goal:
                goals.append(goal)
    return goals


def visible_laundry_goals(observation: dict[str, Any], scene: dict[str, Any], step: int) -> list[dict[str, Any]]:
    goals: list[dict[str, Any]] = []
    for item in sorted(observation.get("nodes") or [], key=lambda node_item: str(node_item.get("id") or "")):
        if str(item.get("semantic_type") or "") not in CLOTH_SEMANTICS:
            continue
        states = item.get("states") or {}
        if states.get("is_dirty") is True or states.get("is_wet") is True or states.get("folded") is False:
            goal = make_laundry_goal(str(item.get("id") or ""), step, source="visible_laundry_issue", scene=scene)
            if goal:
                goals.append(goal)
    return goals


def visible_hospital_goals(
    observation: dict[str, Any],
    scene: dict[str, Any],
    baseline: dict[str, Any],
    robot_id: str,
    step: int,
) -> list[dict[str, Any]]:
    if scene_type(scene) != "hospital":
        return []
    baseline_nodes = {str(item.get("id") or ""): item for item in baseline.get("nodes") or [] if item.get("id")}
    current_nodes = {str(item.get("id") or ""): item for item in observation.get("nodes") or [] if item.get("id")}
    robot_room = room_of(scene, robot_id)
    goals: list[dict[str, Any]] = []
    for node_id, current in sorted(current_nodes.items()):
        states = current.get("states") or {}
        semantic = str(current.get("semantic_type") or "")
        if node_id == "seats_waiting_area" and states.get("is_dirty") is True:
            goal = make_hospital_clean_goal(node_id, "clean_waiting_area", step, source="visible_hospital_dirty_surface")
            if goal:
                goals.append(goal)
        if semantic == "bed" and states.get("is_dirty") is True:
            goal = make_hospital_clean_goal(node_id, "clean_exam_bed", step, source="visible_hospital_dirty_bed")
            if goal:
                goals.append(goal)
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
        goal = make_hospital_return_goal(node_id, target_id, skill, step, source="visible_hospital_supply_issue")
        if goal:
            goals.append(goal)
    return goals


def build_skill_goals(
    observation: dict[str, Any],
    scene: dict[str, Any],
    baseline: dict[str, Any],
    robot_id: str = "robot_01",
    step: int = 0,
) -> list[dict[str, Any]]:
    """Generate all visible skill/restore goals as EFE candidates.

    Returns a list of goal dicts (possibly empty), each carrying the full
    execution detail (phase, resolved node ids) the pipeline provides.
    """
    specialized: list[dict[str, Any]] = []
    specialized.extend(visible_dispose_food_goals(observation, scene, step, baseline))
    specialized.extend(visible_empty_cup_goals(observation, scene, step))
    specialized.extend(visible_laundry_goals(observation, scene, step))
    specialized.extend(visible_hospital_goals(
        observation, scene, baseline, robot_id, step))
    owned_objects = {
        str(goal.get("object") or "") for goal in specialized
        if str(goal.get("object") or "")
    }
    restores = [
        goal for goal in visible_restore_goals(observation, baseline, step)
        if str(goal.get("object") or "") not in owned_objects
    ]
    return [*specialized, *restores]


def goal_still_needed(goal: dict[str, Any],
                      observation: dict[str, Any],
                      scene: dict[str, Any],
                      baseline: dict[str, Any],
                      robot_id: str = "robot_01",
                      step: int = 0) -> bool | None:
    """Rebuild this goal's own detector and ask whether the issue it targets
    still exists.

    Returns True/False, or None for goal types that cannot be verified this way
    (the caller then falls back to the visible deviation list).  Used for two
    things:
      - honest completion: a skill/restore goal is *done* when the world no
        longer exhibits the issue (e.g. the cup's fill_level hit 0), not when
        some target id leaves the deviation list;
      - stale-goal filtering: a pipeline active_goal whose issue is already
        resolved must not be re-committed (it would win on G and thrash).
    """
    gtype = str(goal.get("type") or "")
    obj = str(goal.get("object") or "")
    if gtype == "restore_initial_position":
        current = node(scene, obj)
        target = str(goal.get("target") or "")
        if current is not None and target:
            return str(current.get("parent") or "") != target
        return None
    if gtype == "skill":
        skill = str(goal.get("skill") or "")
        refreshed = refresh_goal_snapshot(goal, scene, robot_id)
        if str(refreshed.get("phase") or "") == "done":
            return False
        fresh = build_skill_goals(observation, scene, baseline, robot_id, step)
        if any(str(g.get("skill") or "") == skill
               and str(g.get("object") or "") == obj for g in fresh):
            return True
        # If the full current scene contains the object/target, absence from
        # the visible detector is evidence only when the refreshed phase says
        # done.  Otherwise remain conservative under partial observability.
        return None
    return None


# ============================================================
# snapshot refresh — fill navigation fields on any goal
# ============================================================

def refresh_goal_snapshot(goal: dict[str, Any], scene: dict[str, Any], robot_id: str) -> dict[str, Any]:
    """Port of refresh_active_goal_snapshot: add object_room / robot_room /
    target_room / next_room / phase (recomputed) so the ranker's navigation
    and door-opening logic has what it needs."""
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
