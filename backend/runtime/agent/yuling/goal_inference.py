"""Rule-based goal inference for robot deployment.

Faithful port of the simulation's goal-selection logic from run_experiment.py.
Scans the scene graph against skill triggers, resolves concrete target nodes,
determines the current phase for multi-step skills, and outputs structured
goal dicts that yuling_agent's ranker and prompt builder consume directly.

Usage:
    from goal_inference import infer_active_goal, active_goal_completed

    goal = infer_active_goal(observation, baseline, agent_id="robot_01")
    if goal:
        ...  # pass to yuling_agent as active_goal=
    if active_goal_completed(goal, observation):
        goal = None  # done, next step will propose a new one

Dependencies:
    None — only Python stdlib.
"""

from __future__ import annotations

from typing import Any

# ============================================================
# Domain constants
# ============================================================

CLOTH_SEMANTICS: frozenset[str] = frozenset({"clothes", "towel", "blanket"})

HOSPITAL_RETURN_SKILLS: frozenset[str] = frozenset({
    "replenish_prescription_sheet",
    "replenish_medicine_box",
    "return_refrigerated_medicine",
    "clean_medical_waste",
    "collect_dirty_linen",
    "restock_clean_sheet",
    "return_wheelchair",
})

HOSPITAL_CLEAN_SKILLS: frozenset[str] = frozenset({"clean_waiting_area", "clean_exam_bed"})

HOSPITAL_SKILL_BY_SEMANTIC: dict[str, str] = {
    "prescription_sheet": "replenish_prescription_sheet",
    "medicine_box": "replenish_medicine_box",
    "refrigerated_medicine": "return_refrigerated_medicine",
    "medical_waste": "clean_medical_waste",
    "wheelchair": "return_wheelchair",
}

HOSPITAL_SKILL_PRIORITY: dict[str, int] = {
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
# Node / room helpers  (ports from run_experiment.py)
# ============================================================

def _node(scene: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    for item in scene.get("nodes") or []:
        if item.get("id") == node_id:
            return item
    return None


def _room_of(scene: dict[str, Any], node_id: str) -> str:
    """Walk parent chain to find the containing room."""
    current_id = str(node_id or "")
    visited: set[str] = set()
    while current_id and current_id not in visited:
        visited.add(current_id)
        item = _node(scene, current_id)
        if not item:
            return ""
        if str(item.get("node_type") or "") == "room":
            return current_id
        current_id = str(item.get("parent") or "")
    return ""


def _scene_type(scene: dict[str, Any]) -> str:
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


def _node_index(scene: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id") or ""): item
        for item in scene.get("nodes") or []
        if item.get("id")
    }


# ============================================================
# Semantic search helpers
# ============================================================

def _first_node_by_semantic(
    scene: dict[str, Any],
    semantics: set[str],
    *,
    room: str = "",
) -> str:
    for item in scene.get("nodes") or []:
        if str(item.get("semantic_type") or "") not in semantics:
            continue
        if room and _room_of(scene, str(item.get("id") or "")) != room:
            continue
        return str(item.get("id") or "")
    return ""


def _first_node_by_semantic_near(
    scene: dict[str, Any],
    semantics: set[str],
    *,
    preferred_room: str = "",
) -> str:
    if preferred_room:
        near = _first_node_by_semantic(scene, semantics, room=preferred_room)
        if near:
            return near
    return _first_node_by_semantic(scene, semantics)


def _find_structural(
    scene: dict[str, Any],
    baseline: dict[str, Any] | None,
    semantics: set[str],
    *,
    room: str = "",
) -> str:
    """Search *scene* first; fall back to *baseline* for structural nodes.

    Structural nodes (washer, sink, trash_bin, etc.) exist in the baseline
    regardless of whether the robot has visited their room.  The baseline
    represents the building floorplan — the robot should know where the
    laundry room is even if it hasn't been there yet.
    """
    result = _first_node_by_semantic(scene, semantics, room=room)
    if not result and baseline is not None:
        result = _first_node_by_semantic(baseline, semantics, room=room)
    return result


def _find_structural_near(
    scene: dict[str, Any],
    baseline: dict[str, Any] | None,
    semantics: set[str],
    *,
    preferred_room: str = "",
) -> str:
    """Like ``_first_node_by_semantic_near`` but with baseline fallback."""
    if preferred_room:
        near = _find_structural(scene, baseline, semantics, room=preferred_room)
        if near:
            return near
    return _find_structural(scene, baseline, semantics)


# ============================================================
# Phase computation  (ports from run_experiment.py)
# ============================================================

def _dispose_food_phase(
    scene: dict[str, Any],
    object_id: str,
    trash_bin_id: str,
    robot_id: str,
    trash_bin_home: str,
) -> str:
    item = _node(scene, object_id) or {}
    trash_bin = _node(scene, trash_bin_id) or {}
    parent = str(item.get("parent") or "")
    bin_parent = str(trash_bin.get("parent") or "")
    if parent != trash_bin_id:
        # If bin is at home but not holding food, we need to collect
        return "collect_food"
    if bin_parent != robot_id:
        # food is in bin, bin is not being held
        return "take_bin"
    # robot holds bin with food inside
    return "dump_bin"
    # Note: "return_bin" phase is handled by refresh_active_goal_snapshot,
    # not needed at proposal time.


def _empty_cup_phase(scene: dict[str, Any], object_id: str) -> str:
    item = _node(scene, object_id) or {}
    states = item.get("states") or {}
    if float(states.get("fill_level") or 0.0) <= 0.0 and states.get("is_full") is not True:
        return "done"
    return "dump_cup"


def _laundry_phase(
    scene: dict[str, Any],
    object_id: str,
    washer_id: str = "",
    wardrobe_id: str = "",
) -> str:
    item = _node(scene, object_id) or {}
    states = item.get("states") or {}
    parent = str(item.get("parent") or "")
    if states.get("is_dirty") is True:
        if washer_id and parent == washer_id:
            washer = _node(scene, washer_id) or {}
            return "washing_wait" if bool((washer.get("states") or {}).get("is_on", False)) else "start_washer"
        return "wash_load"
    if states.get("is_wet") is True:
        return "dry"
    if states.get("folded") is False:
        return "fold"
    if wardrobe_id and parent != wardrobe_id:
        return "store"
    return "done"


# ============================================================
# Goal makers  (ports from run_experiment.py)
# ============================================================

def _make_dispose_food_goal(
    object_id: str,
    step: int,
    *,
    source: str,
    scene: dict[str, Any],
    robot_id: str,
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    object_room = _room_of(scene, object_id)
    _bl = baseline  # short alias
    trash_bin = _find_structural_near(scene, _bl, {"trash_bin"}, preferred_room=object_room)
    garbage_station = _find_structural(scene, _bl, {"garbage_station"})
    if not trash_bin or not garbage_station:
        return None
    baseline_bin = _node(_bl or {}, trash_bin) or {}
    baseline_food = _node(_bl or {}, object_id) or {}
    trash_bin_home = str(
        baseline_bin.get("parent")
        or (_node(scene, trash_bin) or {}).get("parent")
        or ""
    )
    food_home = str(
        baseline_food.get("parent")
        or _find_structural(scene, _bl, {"refrigerator", "fridge"})
    )
    phase = _dispose_food_phase(scene, object_id, trash_bin, robot_id, trash_bin_home)
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


def _make_empty_cup_goal(
    object_id: str,
    step: int,
    *,
    source: str,
    scene: dict[str, Any],
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    object_room = _room_of(scene, object_id)
    sink = _find_structural_near(scene, baseline, {"sink"}, preferred_room=object_room)
    if not sink:
        return None
    phase = _empty_cup_phase(scene, object_id)
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


def _make_laundry_goal(
    object_id: str,
    step: int,
    *,
    source: str,
    scene: dict[str, Any],
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    _bl = baseline
    washer = _find_structural(scene, _bl, {"washer", "washing_machine"})
    drying_rack = _find_structural(scene, _bl, {"drying_rack"})
    wardrobe = (
        _find_structural(scene, _bl, {"cabinet"}, room="bedroom")
        or _find_structural(scene, _bl, {"wardrobe"}, room="bedroom")
    )
    if not washer or not drying_rack or not wardrobe:
        return None
    phase = _laundry_phase(scene, object_id, washer, wardrobe)
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


def _make_restore_goal(
    object_id: str,
    target_id: str,
    step: int,
    *,
    source: str,
) -> dict[str, Any]:
    return {
        "type": "restore_initial_position",
        "task": f"restore_initial_position {object_id} -> {target_id}",
        "object": object_id,
        "target": target_id,
        "started_step": step,
        "last_progress_step": step,
        "steps_without_progress": 0,
        "source": source,
    }


def _make_hospital_return_goal(
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


def _make_hospital_clean_goal(
    target_id: str,
    skill: str,
    step: int,
    *,
    source: str,
) -> dict[str, Any] | None:
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
# Hospital matching helpers
# ============================================================

def _hospital_skill_for_return_issue(
    node_id: str,
    current: dict[str, Any],
    initial: dict[str, Any],
) -> str:
    semantic = str(current.get("semantic_type") or initial.get("semantic_type") or "")
    if semantic == "bed_sheet":
        states = current.get("states") or {}
        if states.get("is_dirty") is True:
            return "collect_dirty_linen"
        if node_id == "clean_sheet_storage":
            return "restock_clean_sheet"
        return ""
    return HOSPITAL_SKILL_BY_SEMANTIC.get(semantic, "")


def _hospital_return_target(
    scene: dict[str, Any],
    baseline: dict[str, Any],
    object_id: str,
    skill: str,
) -> str:
    initial = _node(baseline, object_id) or {}
    if skill == "clean_medical_waste":
        return _find_structural(scene, baseline, {"medical_waste_bin"}) or str(initial.get("parent") or "")
    if skill == "collect_dirty_linen":
        return _find_structural(scene, baseline, {"dirty_linen_bin", "linen_bin"}) or str(initial.get("parent") or "")
    if skill == "restock_clean_sheet":
        return _find_structural(scene, baseline, {"supply_cabinet"}) or str(initial.get("parent") or "")
    return str(initial.get("parent") or "")


def _hospital_issue_goal(
    scene: dict[str, Any],
    baseline: dict[str, Any],
    robot_id: str,
    step: int,
) -> dict[str, Any] | None:
    if _scene_type(scene) != "hospital":
        return None
    baseline_nodes = _node_index(baseline)
    current_nodes = _node_index(scene)
    robot_room = _room_of(scene, robot_id)
    candidates: list[tuple[int, int, str, dict[str, Any]]] = []

    for node_id, current in sorted(current_nodes.items()):
        states = current.get("states") or {}
        semantic = str(current.get("semantic_type") or "")

        # Hospital clean skills
        if node_id == "seats_waiting_area" and states.get("is_dirty") is True:
            priority = 5 if _room_of(scene, node_id) == robot_room else 25
            goal = _make_hospital_clean_goal(node_id, "clean_waiting_area", step, source="hospital_dirty_surface")
            if goal:
                candidates.append((priority, HOSPITAL_SKILL_PRIORITY["clean_waiting_area"], node_id, goal))
        if semantic == "bed" and states.get("is_dirty") is True:
            priority = 5 if _room_of(scene, node_id) == robot_room else 25
            goal = _make_hospital_clean_goal(node_id, "clean_exam_bed", step, source="hospital_dirty_bed")
            if goal:
                candidates.append((priority, HOSPITAL_SKILL_PRIORITY["clean_exam_bed"], node_id, goal))

        # Hospital return skills
        initial = baseline_nodes.get(node_id) or {}
        skill = _hospital_skill_for_return_issue(node_id, current, initial)
        if not skill:
            continue
        current_parent = str(current.get("parent") or "")
        initial_parent = str(initial.get("parent") or "")
        target_id = _hospital_return_target(scene, baseline, node_id, skill) or initial_parent
        if not current_parent or not target_id or current_parent == target_id:
            continue
        current_parent_node = _node(scene, current_parent) or {}
        if str(current_parent_node.get("node_type") or "") == "human":
            parent_states = current_parent_node.get("states") or {}
            if parent_states.get("checked_out") is not True:
                continue
        current_room = _room_of(scene, current_parent)
        initial_room = _room_of(scene, target_id) or _room_of(baseline, initial_parent)
        priority = 40
        if current_parent == robot_id:
            priority = 0
        elif current_room == robot_room:
            priority = 10
        elif initial_room == robot_room:
            priority = 20
        elif current_room:
            priority = 30
        goal = _make_hospital_return_goal(node_id, target_id, skill, step, source="hospital_supply_issue")
        if goal:
            candidates.append((priority, HOSPITAL_SKILL_PRIORITY.get(skill, 99), node_id, goal))

    if not candidates:
        return None
    _, _, _, goal = min(candidates, key=lambda item: (item[0], item[1], item[2]))
    return goal


# ============================================================
# Main: infer active goal  (port of global_restore_goal)
# ============================================================

def infer_active_goal(
    observation: dict[str, Any],
    baseline: dict[str, Any],
    agent_id: str = "robot_01",
    step: int = 0,
) -> dict[str, Any] | None:
    """Propose the highest-priority active goal by scanning the full scene.

    Priority order (first match wins within each category):
      1. Hospital issue (if scene is a hospital)
      2. dispose_food  — rotten or burnt food visible
      3. empty_cup     — cup with liquid visible
      4. laundry       — dirty / wet / unfolded cloth visible
      5. restore       — any movable object displaced from its baseline position

    Within each category, candidate objects are scored by proximity to the
    robot (0 = robot holds it, 10 = same room, 30 = different room). The
    closest candidate wins.

    When *observation* is built from ``RobotMemory.get_known_scene()``, the
    robot sees all nodes it has ever observed (not just the current view),
    which makes goal inference persistent across rooms.

    Structural nodes (washer, sink, trash_bin, etc.) are first searched in
    *observation* and then fall back to *baseline* so the robot can plan
    routes to rooms it hasn't visited yet.

    Returns:
        Structured goal dict, or None if nothing needs attention.
    """
    baseline_nodes = _node_index(baseline)
    current_nodes = _node_index(observation)
    robot_room = _room_of(observation, agent_id)

    # --- 0. Hospital scene ---
    hospital_goal = _hospital_issue_goal(observation, baseline, agent_id, step)
    if hospital_goal:
        return hospital_goal

    # --- 1. dispose_food ---
    dispose_candidates: list[tuple[int, str]] = []
    for node_id, current in sorted(current_nodes.items()):
        if str(current.get("semantic_type") or "") != "food":
            continue
        states = current.get("states") or {}
        if not (states.get("is_rotten") is True or states.get("is_burnt") is True):
            continue
        current_parent = str(current.get("parent") or "")
        current_parent_node = _node(observation, current_parent) or {}
        if str(current_parent_node.get("node_type") or "") == "human":
            continue
        current_room = _room_of(observation, current_parent)
        priority = 10 if current_room == robot_room else 30
        if current_parent == agent_id:
            priority = 0
        dispose_candidates.append((priority, node_id))
    if dispose_candidates:
        _, object_id = min(dispose_candidates)
        goal = _make_dispose_food_goal(
            object_id, step, source="bad_food", scene=observation,
            robot_id=agent_id, baseline=baseline,
        )
        if goal:
            return goal

    # --- 2. empty_cup ---
    cup_candidates: list[tuple[int, str]] = []
    for node_id, current in sorted(current_nodes.items()):
        if str(current.get("semantic_type") or "") != "cup":
            continue
        states = current.get("states") or {}
        if not (float(states.get("fill_level") or 0.0) > 0.0 or states.get("is_full") is True):
            continue
        current_parent = str(current.get("parent") or "")
        current_room = _room_of(observation, current_parent)
        priority = 10 if current_room == robot_room else 30
        if current_parent == agent_id:
            priority = 0
        cup_candidates.append((priority, node_id))
    if cup_candidates:
        _, object_id = min(cup_candidates)
        goal = _make_empty_cup_goal(object_id, step, source="full_cup", scene=observation, baseline=baseline)
        if goal:
            return goal

    # --- 3. laundry ---
    laundry_candidates: list[tuple[int, str]] = []
    for node_id, current in sorted(current_nodes.items()):
        if str(current.get("semantic_type") or "") not in CLOTH_SEMANTICS:
            continue
        states = current.get("states") or {}
        if not (states.get("is_dirty") is True or states.get("is_wet") is True or states.get("folded") is False):
            continue
        current_parent = str(current.get("parent") or "")
        current_parent_node = _node(observation, current_parent) or {}
        if str(current_parent_node.get("node_type") or "") == "human":
            continue
        current_room = _room_of(observation, current_parent)
        priority = 10 if current_room == robot_room else 30
        if current_parent == agent_id:
            priority = 0
        laundry_candidates.append((priority, node_id))
    if laundry_candidates:
        _, object_id = min(laundry_candidates)
        goal = _make_laundry_goal(object_id, step, source="laundry_issue", scene=observation, baseline=baseline)
        if goal:
            return goal

    # --- 4. restore_initial_position ---
    candidates: list[tuple[int, str, str]] = []
    for node_id, current in sorted(current_nodes.items()):
        initial = baseline_nodes.get(node_id) or {}
        if str(initial.get("node_type") or "") != "movable_object":
            continue
        if _scene_type(observation) == "hospital" and \
                _hospital_skill_for_return_issue(node_id, current, initial):
            continue
        current_parent = str(current.get("parent") or "")
        initial_parent = str(initial.get("parent") or "")
        if not current_parent or not initial_parent or current_parent == initial_parent:
            continue
        current_parent_node = _node(observation, current_parent) or {}
        if str(current_parent_node.get("node_type") or "") == "human":
            continue
        current_room = _room_of(observation, current_parent)
        initial_room = _room_of(baseline, initial_parent)
        priority = 50
        if current_parent == agent_id:
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
    return _make_restore_goal(object_id, target_id, step, source="spatial_issue")


# ============================================================
# Goal lifecycle: validation & completion
# ============================================================

def active_goal_ids_valid(
    goal: dict[str, Any] | None,
    scene: dict[str, Any],
) -> bool:
    """Check that all node IDs referenced by the goal still exist."""
    if not goal:
        return False
    node_ids = {str(item.get("id") or "") for item in scene.get("nodes") or [] if item.get("id")}

    # Explore / explore_revisit goals target rooms that may not be in the
    # current scene yet — that's the whole point of exploring.  Skip the
    # validity check for these goal types.
    goal_type = str(goal.get("type") or "")
    if goal_type in ("explore", "explore_revisit"):
        return True

    fields = (
        "object", "target", "food_home", "trash_bin", "trash_bin_home",
        "garbage_station", "sink", "washer", "drying_rack", "wardrobe",
    )
    return all(
        str(goal.get(field) or "") in node_ids
        for field in fields
        if goal.get(field)
    )


def active_goal_completed(
    goal: dict[str, Any] | None,
    scene: dict[str, Any],
) -> bool:
    """Check whether the active goal has been achieved.

    Returns True if the goal is done (should be cleared) or if all
    referenced nodes no longer exist (state changed underneath us).
    """
    if not goal:
        return False
    if not active_goal_ids_valid(goal, scene):
        return True  # nodes disappeared → goal is moot

    object_node = _node(scene, str(goal.get("object") or "")) or {}
    goal_type = str(goal.get("type") or "")
    skill = str(goal.get("skill") or "")

    # Explore goals: complete when the target room has been reached (its
    # node is now in the scene, which it wasn't before visiting).
    if goal_type in ("explore", "explore_revisit"):
        node_ids = {str(item.get("id") or "") for item in scene.get("nodes") or [] if item.get("id")}
        return str(goal.get("target") or "") in node_ids

    # --- laundry_clothes: in wardrobe, clean, dry, folded ---
    if goal_type == "skill" and skill == "laundry_clothes":
        states = object_node.get("states") or {}
        return bool(
            object_node
            and str(object_node.get("parent") or "") == str(goal.get("wardrobe") or goal.get("target") or "")
            and states.get("is_dirty") is False
            and states.get("is_wet") is False
            and states.get("folded") is True
        )

    # --- dispose_food: food restored to home, trash_bin returned home ---
    if goal_type == "skill" and skill == "dispose_food":
        states = object_node.get("states") or {}
        trash_bin_node = _node(scene, str(goal.get("trash_bin") or "")) or {}
        return bool(
            object_node
            and str(object_node.get("parent") or "") == str(goal.get("food_home") or "")
            and str(trash_bin_node.get("parent") or "") == str(goal.get("trash_bin_home") or "")
            and states.get("is_rotten") is False
            and states.get("is_burnt") is False
        )

    # --- empty_cup: cup is empty ---
    if goal_type == "skill" and skill == "empty_cup":
        states = object_node.get("states") or {}
        return bool(
            object_node
            and float(states.get("fill_level") or 0.0) <= 0.0
            and states.get("is_full") is not True
        )

    # --- hospital return: object is back at target ---
    if goal_type == "skill" and skill in HOSPITAL_RETURN_SKILLS:
        return bool(
            object_node
            and str(object_node.get("parent") or "") == str(goal.get("target") or "")
        )

    # --- hospital clean: target is no longer dirty ---
    if goal_type == "skill" and skill in HOSPITAL_CLEAN_SKILLS:
        target_node = _node(scene, str(goal.get("target") or goal.get("object") or "")) or {}
        states = target_node.get("states") or {}
        return bool(target_node and states.get("is_dirty") is not True)

    # --- restore_initial_position (and generic): object is back at target ---
    return bool(
        object_node
        and str(object_node.get("parent") or "") == str(goal.get("target") or "")
    )


# ============================================================
# Navigation helpers
# ============================================================


def _next_room_toward(
    scene: dict[str, Any],
    start_room: str,
    target_room: str,
) -> str:
    """BFS: return the first neighbour on the shortest path from
    *start_room* to *target_room*, or "" if unreachable."""
    if not start_room or not target_room or start_room == target_room:
        return ""
    graph: dict[str, set[str]] = {}
    for edge in scene.get("edges") or []:
        relation = str(edge.get("relation") or "").lower()
        if relation not in {"connected", "connected_to", "next_to", "neighbour"}:
            continue
        src = str(edge.get("source_id") or "")
        tgt = str(edge.get("target_id") or "")
        if src and tgt:
            graph.setdefault(src, set()).add(tgt)
            graph.setdefault(tgt, set()).add(src)
    queue: list[tuple[str, list[str]]] = [(start_room, [start_room])]
    seen = {start_room}
    while queue:
        room, path = queue.pop(0)
        for neighbor in sorted(graph.get(room, ())):
            if neighbor in seen:
                continue
            next_path = [*path, neighbor]
            if neighbor == target_room:
                return next_path[1] if len(next_path) > 1 else ""
            seen.add(neighbor)
            queue.append((neighbor, next_path))
    return ""


# ============================================================
# Goal enrichment (ports refresh_active_goal_snapshot)
# ============================================================


def refresh_active_goal_snapshot(
    goal: dict[str, Any],
    scene: dict[str, Any],
    robot_id: str,
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Enrich *goal* with per-step navigation fields.

    Adds ``object_parent``, ``object_room``, ``robot_room``,
    ``next_room``, and resolves phase / structural IDs, so that
    the ranker can score intermediate navigation actions.
    """
    import copy
    updated = copy.deepcopy(goal)
    object_id = str(updated.get("object") or "")
    object_node = _node(scene, object_id) or {}
    robot_node = _node(scene, robot_id) or {}
    target_id = str(updated.get("target") or "")
    skill = str(updated.get("skill") or "")
    destination_room_override = ""

    _bl = baseline  # short alias for structural fallback

    # --- dispose_food ---
    if str(updated.get("type") or "") == "skill" and skill == "dispose_food":
        trash_bin = str(
            updated.get("trash_bin")
            or _find_structural_near(scene, _bl, {"trash_bin"}, preferred_room=_room_of(scene, object_id))
        )
        garbage_station = str(
            updated.get("garbage_station")
            or _find_structural(scene, _bl, {"garbage_station"})
        )
        updated["trash_bin"] = trash_bin
        updated["garbage_station"] = garbage_station
        updated["target"] = garbage_station
        trash_bin_home = str(
            updated.get("trash_bin_home")
            or (_node(scene, trash_bin) or {}).get("parent") or ""
        )
        updated["trash_bin_home"] = trash_bin_home
        updated["phase"] = _dispose_food_phase(scene, object_id, trash_bin, robot_id, trash_bin_home)
        phase = str(updated.get("phase") or "")
        target_by_phase = {
            "collect_food": trash_bin,
            "take_bin": trash_bin,
            "dump_bin": garbage_station,
            "return_bin": trash_bin_home,
        }
        target_id = target_by_phase.get(phase, garbage_station)
        if phase == "collect_food":
            destination_room_override = (
                _room_of(scene, trash_bin)
                if str(object_node.get("parent") or "") == robot_id
                else _room_of(scene, object_id)
            )
        elif phase == "take_bin":
            destination_room_override = _room_of(scene, trash_bin)
        elif phase == "dump_bin":
            destination_room_override = _room_of(scene, garbage_station)
        elif phase == "return_bin":
            destination_room_override = _room_of(scene, trash_bin_home)

    # --- empty_cup ---
    if str(updated.get("type") or "") == "skill" and skill == "empty_cup":
        sink = str(
            updated.get("sink")
            or _find_structural_near(scene, _bl, {"sink"}, preferred_room=_room_of(scene, object_id))
        )
        updated["sink"] = sink
        updated["target"] = sink
        updated["phase"] = _empty_cup_phase(scene, object_id)
        target_id = sink
        if str(object_node.get("parent") or "") == robot_id:
            destination_room_override = _room_of(scene, sink)

    # --- laundry_clothes ---
    if str(updated.get("type") or "") == "skill" and skill == "laundry_clothes":
        washer = str(
            updated.get("washer")
            or _find_structural(scene, _bl, {"washer", "washing_machine"})
        )
        drying_rack = str(
            updated.get("drying_rack")
            or _find_structural(scene, _bl, {"drying_rack"})
        )
        wardrobe = str(
            updated.get("wardrobe")
            or _find_structural(scene, _bl, {"cabinet"}, room="bedroom")
            or _find_structural(scene, _bl, {"wardrobe"}, room="bedroom")
        )
        updated["washer"] = washer
        updated["washer_button"] = str(updated.get("washer_button") or f"{washer}_button")
        updated["drying_rack"] = drying_rack
        updated["wardrobe"] = wardrobe
        updated["target"] = wardrobe
        updated["phase"] = _laundry_phase(scene, object_id, washer, wardrobe)
        target_by_phase = {
            "wash_load": washer,
            "start_washer": washer,
            "washing_wait": washer,
            "dry": drying_rack,
            "fold": object_id,
            "store": wardrobe,
        }
        target_id = target_by_phase.get(str(updated.get("phase") or ""), wardrobe)

    # --- hospital return ---
    if str(updated.get("type") or "") == "skill" and skill in HOSPITAL_RETURN_SKILLS:
        target_id = str(updated.get("target") or "")
        updated["phase"] = (
            "done"
            if object_node and str(object_node.get("parent") or "") == target_id
            else "return_item"
        )
        if str(object_node.get("parent") or "") == robot_id:
            destination_room_override = _room_of(scene, target_id)

    # --- hospital clean ---
    if str(updated.get("type") or "") == "skill" and skill in HOSPITAL_CLEAN_SKILLS:
        target_id = str(updated.get("target") or object_id)
        target_node = _node(scene, target_id) or {}
        target_states = target_node.get("states") or {}
        updated["phase"] = (
            "clean_surface" if target_states.get("is_dirty") is True else "done"
        )
        destination_room_override = _room_of(scene, target_id)

    # --- navigation fields (common) ---
    updated["object_parent"] = str(object_node.get("parent") or "")
    updated["object_room"] = _room_of(scene, object_id)
    updated["target_room"] = _room_of(scene, target_id)
    updated["robot_parent"] = str(robot_node.get("parent") or "")
    updated["robot_room"] = _room_of(scene, robot_id)
    destination_room = destination_room_override or (
        updated["target_room"]
        if updated["object_parent"] == robot_id
        else updated["object_room"]
    )
    updated["next_room"] = _next_room_toward(scene, updated["robot_room"], destination_room)
    return updated


__all__ = [
    "infer_active_goal",
    "active_goal_ids_valid",
    "active_goal_completed",
    "refresh_active_goal_snapshot",
]
