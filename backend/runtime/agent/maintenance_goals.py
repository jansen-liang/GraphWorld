from __future__ import annotations

from typing import Any

from backend.runtime.scene_utils import node, room_of, scene_type

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

def visible_restore_goal(observation: dict[str, Any], baseline: dict[str, Any], step: int) -> dict[str, Any] | None:
    baseline_nodes = {str(item.get("id") or ""): item for item in baseline.get("nodes") or [] if item.get("id")}
    current_nodes = {str(item.get("id") or ""): item for item in observation.get("nodes") or [] if item.get("id")}
    for node_id, current in sorted(current_nodes.items()):
        initial = baseline_nodes.get(node_id) or {}
        if str(initial.get("node_type") or "") != "movable_object":
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
        hospital_skill = hospital_skill_for_return_issue(node_id, current, initial)
        if hospital_skill:
            goal = make_hospital_return_goal(
                node_id,
                hospital_return_target(observation, baseline, node_id, hospital_skill) or initial_parent,
                hospital_skill,
                step,
                source="visible_hospital_supply_issue",
            )
            if goal:
                return goal
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
        return "dump_bin"
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
    if washer_id and parent != washer_id and _laundry_detergent_pool(scene, washer_id) and not _laundry_detergent_loaded(scene, washer_id):
        return "load_detergent"
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


def _laundry_detergent_pool(scene: dict[str, Any], washer_id: str) -> str:
    washer = node(scene, washer_id) or {}
    room_id = str(washer.get("room") or washer.get("room_id") or "")
    for item in scene.get("nodes") or []:
        if not isinstance(item, dict) or not item.get("resource_pool"):
            continue
        if str(item.get("semantic_type") or "") not in {"detergent_dispenser", "resource_dispenser"}:
            continue
        parent = str(item.get("parent") or "")
        if parent == washer_id or (room_id and str(item.get("room") or item.get("room_id") or "") == room_id):
            return str(item.get("id") or "")
    return ""


def _laundry_detergent_loaded(scene: dict[str, Any], washer_id: str) -> bool:
    return any(
        isinstance(item, dict)
        and str(item.get("parent") or "") == washer_id
        and str(item.get("semantic_type") or "") in {"detergent", "laundry_detergent"}
        for item in scene.get("nodes") or []
    )


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
        "detergent_pool": _laundry_detergent_pool(scene, washer),
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


def _dishwasher_return_target(
    scene: dict[str, Any],
    object_id: str,
    baseline: dict[str, Any] | None = None,
) -> str:
    """Resolve a stable place target for clean dishes after unloading."""
    initial_parent = str((node(baseline or {}, object_id) or {}).get("parent") or "")
    parent_node = node(scene, initial_parent) or {}
    if initial_parent and str(parent_node.get("node_type") or "") != "room":
        actions = {str(action) for action in parent_node.get("interactive_actions") or []}
        if "place" in actions or parent_node.get("surface_size_cm") or parent_node.get("support_surface_cm"):
            return initial_parent
    object_room = room_of(scene, object_id)
    for item in scene.get("nodes") or []:
        if not isinstance(item, dict) or room_of(scene, str(item.get("id") or "")) != object_room:
            continue
        if str(item.get("semantic_type") or "") not in {"table", "counter", "coffee_table", "desk", "shelf", "rack"}:
            continue
        actions = {str(action) for action in item.get("interactive_actions") or []}
        if "place" in actions or item.get("surface_size_cm") or item.get("support_surface_cm"):
            return str(item.get("id") or "")
    return ""


def dishwasher_phase(scene: dict[str, Any], object_id: str, dishwasher_id: str, return_target: str = "") -> str:
    item = node(scene, object_id) or {}
    states = item.get("states") or {}
    if states.get("is_dirty") is not True:
        return "unload" if str(item.get("parent") or "") == dishwasher_id and return_target else "done"
    if str(item.get("parent") or "") != dishwasher_id:
        return "load"
    dishwasher = node(scene, dishwasher_id) or {}
    return "washing_wait" if bool((dishwasher.get("states") or {}).get("is_running", False)) else "run"


def make_dishwasher_goal(
    object_id: str,
    step: int,
    *,
    source: str,
    scene: dict[str, Any],
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    dishwasher = first_node_by_semantic(scene, {"dishwasher"})
    if not dishwasher:
        return None
    return_target = _dishwasher_return_target(scene, object_id, baseline)
    if not return_target:
        return None
    phase = dishwasher_phase(scene, object_id, dishwasher, return_target)
    if phase == "done":
        return None
    return {
        "type": "skill",
        "skill": "dishwash_dishes",
        "task": f"dishwash_dishes {object_id}",
        "object": object_id,
        "target": dishwasher,
        "dishwasher": dishwasher,
        "dishwasher_button": f"{dishwasher}_button",
        "return_target": return_target,
        "phase": phase,
        "started_step": step,
        "last_progress_step": step,
        "steps_without_progress": 0,
        "source": source,
    }


def visible_dishwasher_goal(
    observation: dict[str, Any],
    scene: dict[str, Any],
    step: int,
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    for item in sorted(observation.get("nodes") or [], key=lambda node_item: str(node_item.get("id") or "")):
        if str(item.get("semantic_type") or "") not in {"bowl", "plate", "cup", "dish", "utensil"}:
            continue
        if (item.get("states") or {}).get("is_dirty") is True:
            return make_dishwasher_goal(
                str(item.get("id") or ""),
                step,
                source="visible_dirty_dish",
                scene=scene,
                baseline=baseline,
            )
    return None


def _heat_milk_return_target(
    scene: dict[str, Any],
    object_id: str,
    baseline: dict[str, Any] | None = None,
) -> str:
    initial_parent = str((node(baseline or {}, object_id) or {}).get("parent") or "")
    parent_node = node(scene, initial_parent) or {}
    if initial_parent and str(parent_node.get("node_type") or "") != "room":
        actions = {str(action) for action in parent_node.get("interactive_actions") or []}
        if "place" in actions or parent_node.get("surface_size_cm") or parent_node.get("support_surface_cm"):
            return initial_parent
    object_room = room_of(scene, object_id)
    for item in scene.get("nodes") or []:
        if not isinstance(item, dict) or room_of(scene, str(item.get("id") or "")) != object_room:
            continue
        if str(item.get("semantic_type") or "") not in {"table", "counter", "coffee_table", "desk", "shelf", "rack"}:
            continue
        actions = {str(action) for action in item.get("interactive_actions") or []}
        if "place" in actions or item.get("surface_size_cm") or item.get("support_surface_cm"):
            return str(item.get("id") or "")
    return ""


def heat_milk_phase(scene: dict[str, Any], object_id: str, microwave_id: str, return_target: str = "") -> str:
    item = node(scene, object_id) or {}
    states = item.get("states") or {}
    if str(states.get("temperature") or "") not in {"cold", "room"}:
        return "unload" if str(item.get("parent") or "") == microwave_id and return_target else "done"
    if str(item.get("parent") or "") != microwave_id:
        return "load"
    microwave = node(scene, microwave_id) or {}
    return "waiting" if bool((microwave.get("states") or {}).get("is_running", False)) else "run"


def make_heat_milk_goal(
    object_id: str,
    step: int,
    *,
    source: str,
    scene: dict[str, Any],
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    microwave = first_node_by_semantic(scene, {"microwave"})
    if not microwave:
        return None
    return_target = _heat_milk_return_target(scene, object_id, baseline)
    if not return_target:
        return None
    phase = heat_milk_phase(scene, object_id, microwave, return_target)
    if phase == "done":
        return None
    return {
        "type": "skill",
        "skill": "heat_milk",
        "task": f"heat_milk {object_id}",
        "object": object_id,
        "target": microwave,
        "microwave": microwave,
        "microwave_button": f"{microwave}_button",
        "return_target": return_target,
        "phase": phase,
        "started_step": step,
        "last_progress_step": step,
        "steps_without_progress": 0,
        "source": source,
    }


def visible_heat_milk_goal(
    observation: dict[str, Any],
    scene: dict[str, Any],
    step: int,
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    for item in sorted(observation.get("nodes") or [], key=lambda node_item: str(node_item.get("id") or "")):
        if str(item.get("semantic_type") or "") not in {"milk", "juice", "food", "drink", "water"}:
            continue
        if str((item.get("states") or {}).get("temperature") or "") in {"cold", "room"}:
            return make_heat_milk_goal(
                str(item.get("id") or ""),
                step,
                source="visible_cold_item",
                scene=scene,
                baseline=baseline,
            )
    return None


def _cook_return_target(scene: dict[str, Any], egg_id: str, baseline: dict[str, Any] | None = None) -> str:
    initial_parent = str((node(baseline or {}, egg_id) or {}).get("parent") or "")
    parent_node = node(scene, initial_parent) or {}
    if initial_parent and str(parent_node.get("node_type") or "") != "room":
        actions = {str(action) for action in parent_node.get("interactive_actions") or []}
        if "place" in actions or parent_node.get("surface_size_cm") or parent_node.get("support_surface_cm"):
            return initial_parent
    object_room = room_of(scene, egg_id)
    for item in scene.get("nodes") or []:
        if not isinstance(item, dict) or room_of(scene, str(item.get("id") or "")) != object_room:
            continue
        if str(item.get("semantic_type") or "") not in {"table", "counter", "coffee_table", "desk", "shelf", "rack"}:
            continue
        actions = {str(action) for action in item.get("interactive_actions") or []}
        if "place" in actions or item.get("surface_size_cm") or item.get("support_surface_cm"):
            return str(item.get("id") or "")
    return ""


def cook_egg_phase(scene: dict[str, Any], stove_id: str, output_id: str = "", egg_id: str = "") -> str:
    if output_id and node(scene, output_id):
        return "serve"
    stove = node(scene, stove_id) or {}
    if bool((stove.get("states") or {}).get("is_running", False)):
        return "waiting"
    if egg_id and str((node(scene, egg_id) or {}).get("parent") or "") == stove_id:
        return "cook"
    return "prepare"


def make_cook_egg_goal(
    egg_id: str,
    step: int,
    *,
    source: str,
    scene: dict[str, Any],
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    stove = first_node_by_semantic(scene, {"stove"})
    if not stove:
        return None
    return_target = _cook_return_target(scene, egg_id, baseline)
    if not return_target:
        return None
    phase = cook_egg_phase(scene, stove, egg_id=egg_id)
    return {
        "type": "skill",
        "skill": "cook_egg",
        "task": f"cook_egg {egg_id}",
        "object": stove,
        "input_object": egg_id,
        "target": stove,
        "stove": stove,
        "stove_button": f"{stove}_button",
        "return_target": return_target,
        "phase": phase,
        "started_step": step,
        "last_progress_step": step,
        "steps_without_progress": 0,
        "source": source,
    }


def visible_cook_egg_goal(
    observation: dict[str, Any],
    scene: dict[str, Any],
    step: int,
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    for item in sorted(observation.get("nodes") or [], key=lambda node_item: str(node_item.get("id") or "")):
        if str(item.get("semantic_type") or "") == "egg":
            return make_cook_egg_goal(str(item.get("id") or ""), step, source="visible_egg", scene=scene, baseline=baseline)
    return None


def _craft_return_target(scene: dict[str, Any], workbench_id: str) -> str:
    workbench_room = room_of(scene, workbench_id)
    for item in scene.get("nodes") or []:
        if not isinstance(item, dict) or room_of(scene, str(item.get("id") or "")) != workbench_room:
            continue
        if str(item.get("semantic_type") or "") not in {"table", "counter", "coffee_table", "desk", "shelf", "rack"}:
            continue
        actions = {str(action) for action in item.get("interactive_actions") or []}
        if "place" in actions or item.get("surface_size_cm") or item.get("support_surface_cm"):
            return str(item.get("id") or "")
    return ""


def craft_sandwich_phase(scene: dict[str, Any], workbench_id: str, bread_id: str, tomato_id: str, output_id: str = "") -> str:
    if output_id and node(scene, output_id):
        return "serve"
    workbench = node(scene, workbench_id) or {}
    if bool((workbench.get("states") or {}).get("is_running", False)):
        return "waiting"
    parents = {
        str((node(scene, bread_id) or {}).get("parent") or ""),
        str((node(scene, tomato_id) or {}).get("parent") or ""),
    }
    if parents == {workbench_id}:
        return "craft"
    return "collect"


def make_craft_sandwich_goal(
    step: int,
    *,
    source: str,
    scene: dict[str, Any],
) -> dict[str, Any] | None:
    workbench = first_node_by_semantic(scene, {"workbench"})
    if not workbench:
        return None
    bread = first_node_by_semantic(scene, {"bread"})
    tomato = first_node_by_semantic(scene, {"tomato"})
    if not bread or not tomato:
        return None
    return_target = _craft_return_target(scene, workbench)
    if not return_target:
        return None
    phase = craft_sandwich_phase(scene, workbench, bread, tomato)
    return {
        "type": "skill",
        "skill": "craft_sandwich",
        "task": f"craft_sandwich {workbench}",
        "object": workbench,
        "bread": bread,
        "tomato": tomato,
        "target": workbench,
        "workbench": workbench,
        "workbench_button": f"{workbench}_button",
        "return_target": return_target,
        "phase": phase,
        "started_step": step,
        "last_progress_step": step,
        "steps_without_progress": 0,
        "source": source,
    }


def visible_craft_sandwich_goal(
    observation: dict[str, Any],
    scene: dict[str, Any],
    step: int,
) -> dict[str, Any] | None:
    semantics = {str(item.get("semantic_type") or "") for item in observation.get("nodes") or []}
    if not {"bread", "tomato"}.issubset(semantics):
        return None
    return make_craft_sandwich_goal(step, source="visible_recipe_inputs", scene=scene)


def _assembly_return_target(scene: dict[str, Any], line_id: str) -> str:
    line_room = room_of(scene, line_id)
    for item in scene.get("nodes") or []:
        if not isinstance(item, dict) or room_of(scene, str(item.get("id") or "")) != line_room:
            continue
        if str(item.get("semantic_type") or "") not in {"table", "counter", "desk", "shelf", "rack", "inspection_surface"}:
            continue
        actions = {str(action) for action in item.get("interactive_actions") or []}
        if "place" in actions or item.get("surface_size_cm") or item.get("support_surface_cm"):
            return str(item.get("id") or "")
    return ""


def assemble_product_phase(scene: dict[str, Any], line_id: str, component_a: str, component_b: str, output_id: str = "") -> str:
    if output_id and node(scene, output_id):
        return "inspect"
    line = node(scene, line_id) or {}
    if bool((line.get("states") or {}).get("is_running", False)):
        return "waiting"
    parents = {
        str((node(scene, component_a) or {}).get("parent") or ""),
        str((node(scene, component_b) or {}).get("parent") or ""),
    }
    return "run" if parents == {line_id} else "collect"


def make_assemble_product_goal(step: int, *, source: str, scene: dict[str, Any]) -> dict[str, Any] | None:
    line = first_node_by_semantic(scene, {"assembly_line"})
    component_a = first_node_by_semantic(scene, {"component_a"})
    component_b = first_node_by_semantic(scene, {"component_b"})
    if not line or not component_a or not component_b:
        return None
    return_target = _assembly_return_target(scene, line)
    if not return_target:
        return None
    return {
        "type": "skill",
        "skill": "assemble_product",
        "task": f"assemble_product {line}",
        "object": line,
        "component_a": component_a,
        "component_b": component_b,
        "target": line,
        "assembly_line": line,
        "assembly_line_button": f"{line}_button",
        "return_target": return_target,
        "phase": assemble_product_phase(scene, line, component_a, component_b),
        "started_step": step,
        "last_progress_step": step,
        "steps_without_progress": 0,
        "source": source,
    }


def visible_assemble_product_goal(observation: dict[str, Any], scene: dict[str, Any], step: int) -> dict[str, Any] | None:
    semantics = {str(item.get("semantic_type") or "") for item in observation.get("nodes") or []}
    if not {"component_a", "component_b"}.issubset(semantics):
        return None
    return make_assemble_product_goal(step, source="visible_recipe_inputs", scene=scene)


def _coffee_return_target(scene: dict[str, Any], cup_id: str) -> str:
    initial_parent = str((node(scene, cup_id) or {}).get("parent") or "")
    parent_node = node(scene, initial_parent) or {}
    if initial_parent and str(parent_node.get("node_type") or "") != "room":
        actions = {str(action) for action in parent_node.get("interactive_actions") or []}
        if "place" in actions or parent_node.get("surface_size_cm") or parent_node.get("support_surface_cm"):
            return initial_parent
    room_id = room_of(scene, cup_id)
    for item in scene.get("nodes") or []:
        if not isinstance(item, dict) or room_of(scene, str(item.get("id") or "")) != room_id:
            continue
        if str(item.get("semantic_type") or "") not in {"table", "counter", "coffee_table", "desk", "shelf", "rack"}:
            continue
        actions = {str(action) for action in item.get("interactive_actions") or []}
        if "place" in actions or item.get("surface_size_cm") or item.get("support_surface_cm"):
            return str(item.get("id") or "")
    return ""


def brew_coffee_phase(scene: dict[str, Any], machine_id: str, cup_id: str, beans_id: str, output_id: str = "") -> str:
    if output_id and node(scene, output_id):
        return "serve"
    machine = node(scene, machine_id) or {}
    if bool((machine.get("states") or {}).get("is_running", False)):
        return "waiting"
    parents = {
        str((node(scene, cup_id) or {}).get("parent") or ""),
        str((node(scene, beans_id) or {}).get("parent") or ""),
    }
    return "run" if parents == {machine_id} else "prepare"


def make_brew_coffee_goal(step: int, *, source: str, scene: dict[str, Any]) -> dict[str, Any] | None:
    machine = first_node_by_semantic(scene, {"coffeemachine", "coffee_machine"})
    cup = first_node_by_semantic(scene, {"cup"})
    beans = first_node_by_semantic(scene, {"coffee_beans"})
    if not machine or not cup or not beans:
        return None
    machine_states = (node(scene, machine) or {}).get("states") or {}
    try:
        water_level = float(machine_states.get("water_level", 100.0 if machine_states.get("has_water") else 0.0) or 0.0)
    except (TypeError, ValueError):
        water_level = 0.0
    if water_level < 25.0:
        return None
    return_target = _coffee_return_target(scene, cup)
    if not return_target:
        return None
    return {
        "type": "skill",
        "skill": "brew_coffee",
        "task": f"brew_coffee {machine}",
        "object": machine,
        "cup": cup,
        "coffee_beans": beans,
        "target": machine,
        "coffee_machine": machine,
        "coffee_machine_button": f"{machine}_button",
        "return_target": return_target,
        "phase": brew_coffee_phase(scene, machine, cup, beans),
        "started_step": step,
        "last_progress_step": step,
        "steps_without_progress": 0,
        "source": source,
    }


def visible_brew_coffee_goal(observation: dict[str, Any], scene: dict[str, Any], step: int) -> dict[str, Any] | None:
    semantics = {str(item.get("semantic_type") or "") for item in observation.get("nodes") or []}
    if not {"cup", "coffee_beans"}.issubset(semantics):
        return None
    return make_brew_coffee_goal(step, source="visible_recipe_inputs", scene=scene)


def _print_return_target(
    scene: dict[str, Any],
    printer_id: str,
    baseline: dict[str, Any] | None = None,
) -> str:
    printer_room = room_of(scene, printer_id)
    preferred = str((node(baseline or {}, printer_id) or {}).get("output_surface") or "")
    candidates = []
    if preferred:
        candidates.append(preferred)
    candidates.extend(str(item.get("id") or "") for item in scene.get("nodes") or [] if isinstance(item, dict))
    for candidate_id in candidates:
        item = node(scene, candidate_id) or {}
        if not candidate_id or candidate_id == printer_id or room_of(scene, candidate_id) != printer_room:
            continue
        if str(item.get("semantic_type") or "") not in {"table", "counter", "desk", "shelf", "rack", "tray"}:
            continue
        actions = {str(action) for action in item.get("interactive_actions") or []}
        if "place" in actions or item.get("surface_size_cm") or item.get("support_surface_cm"):
            return candidate_id
    return ""


def make_print_goal(
    printer_id: str,
    step: int,
    *,
    source: str,
    scene: dict[str, Any],
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    printer = node(scene, printer_id) or {}
    states = printer.get("states") or {}
    if str(printer.get("semantic_type") or "") != "printer" or states.get("is_running", False):
        return None
    if float(states.get("count") or 0.0) < 1.0 or float(states.get("amount") or 0.0) < 1.0:
        return None
    return_target = _print_return_target(scene, printer_id, baseline)
    if not return_target:
        return None
    receipt_count = sum(
        1 for item in scene.get("nodes") or []
        if isinstance(item, dict) and str(item.get("semantic_type") or "") == "receipt" and str(item.get("parent") or "") == printer_id
    )
    receipt_ids_before = sorted(
        str(item.get("id") or "")
        for item in scene.get("nodes") or []
        if isinstance(item, dict)
        and str(item.get("semantic_type") or "") == "receipt"
        and str(item.get("parent") or "") == printer_id
        and item.get("id")
    )
    return {
        "type": "skill", "skill": "print_document", "task": f"print_document {printer_id}",
        "object": printer_id, "target": printer_id, "printer": printer_id,
        "printer_button": f"{printer_id}_button", "return_target": return_target, "phase": "print",
        "receipt_count_before": receipt_count, "receipt_ids_before": receipt_ids_before, "started_step": step,
        "last_progress_step": step, "steps_without_progress": 0, "source": source,
    }


def visible_print_goal(
    observation: dict[str, Any],
    scene: dict[str, Any],
    step: int,
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    for item in sorted(observation.get("nodes") or [], key=lambda node_item: str(node_item.get("id") or "")):
        if str(item.get("semantic_type") or "") == "printer":
            return make_print_goal(
                str(item.get("id") or ""),
                step,
                source="visible_print_supply",
                scene=scene,
                baseline=baseline,
            )
    return None


def hospital_skill_for_return_issue(node_id: str, current: dict[str, Any], initial: dict[str, Any]) -> str:
    semantic = str(current.get("semantic_type") or initial.get("semantic_type") or "")
    if semantic == "bed_sheet":
        states = current.get("states") or {}
        if states.get("is_dirty") is True:
            return "collect_dirty_linen"
        if node_id == "clean_sheet_storage" or states.get("is_dirty") is False:
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
