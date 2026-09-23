from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from backend.runtime.scene_utils import node, room_of
from backend.runtime.agent.maintenance_goals import (
    HOSPITAL_CLEAN_SKILLS,
    HOSPITAL_RETURN_SKILLS,
    dispose_food_phase,
    empty_cup_phase,
    first_node_by_semantic,
    first_node_by_semantic_near,
    global_restore_goal,
    dishwasher_phase,
    heat_milk_phase,
    cook_egg_phase,
    craft_sandwich_phase,
    assemble_product_phase,
    brew_coffee_phase,
    laundry_phase,
    visible_print_goal,
    visible_dispose_food_goal,
    visible_dishwasher_goal,
    visible_heat_milk_goal,
    visible_cook_egg_goal,
    visible_craft_sandwich_goal,
    visible_assemble_product_goal,
    visible_brew_coffee_goal,
    visible_empty_cup_goal,
    visible_laundry_goal,
    visible_restore_goal,
)


GOAL_STATUS_ACTIVE = "active"
GOAL_STATUS_PAUSED = "paused"
GOAL_PRIORITY_BY_SKILL = {
    "dispose_food": 90,
    "empty_cup": 80,
    "water_plant": 75,
    "refill_vase": 70,
    "laundry_clothes": 60,
    "dishwash_dishes": 55,
    "heat_milk": 50,
}


def goal_checkpoint_id(goal: dict[str, Any]) -> str:
    """Return a stable identity for a goal across checkpoint reloads."""
    existing = str(goal.get("goal_id") or "").strip()
    if existing:
        return existing
    identity = {
        key: goal.get(key)
        for key in ("task", "skill", "object", "input_object", "bread", "tomato", "target", "return_target")
        if goal.get(key) not in (None, "")
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str)
    return f"goal_{hashlib.sha1(encoded.encode('utf-8')).hexdigest()[:16]}"


def goal_priority(goal: dict[str, Any]) -> int:
    explicit = goal.get("priority")
    if explicit is not None:
        try:
            return int(explicit)
        except (TypeError, ValueError):
            pass
    return GOAL_PRIORITY_BY_SKILL.get(str(goal.get("skill") or ""), 40)


def start_goal(goal: dict[str, Any], step: int) -> dict[str, Any]:
    updated = copy.deepcopy(goal)
    updated["goal_id"] = goal_checkpoint_id(updated)
    updated["status"] = GOAL_STATUS_ACTIVE
    updated["priority"] = goal_priority(updated)
    updated.setdefault("started_step", int(step))
    updated.setdefault("last_progress_step", int(step))
    updated.setdefault("resume_count", 0)
    updated.setdefault("preempted_at", None)
    updated.setdefault("preempt_reason", "")
    updated.setdefault("deadline_step", None)
    updated.setdefault("steps_without_progress", 0)
    return updated


def preempt_goal(goal: dict[str, Any], step: int, reason: str) -> dict[str, Any]:
    updated = start_goal(goal, int(goal.get("started_step") or step))
    updated["status"] = GOAL_STATUS_PAUSED
    updated["preempted_at"] = int(step)
    updated["preempt_reason"] = str(reason or "preempted")
    updated["last_checkpoint_step"] = int(step)
    return updated


def resume_goal(goal: dict[str, Any], step: int) -> dict[str, Any]:
    updated = start_goal(goal, int(goal.get("started_step") or step))
    updated["status"] = GOAL_STATUS_ACTIVE
    updated["resume_count"] = int(updated.get("resume_count") or 0) + 1
    updated["resumed_at"] = int(step)
    updated["preempt_reason"] = ""
    updated["last_progress_step"] = max(int(updated.get("last_progress_step") or step), int(step))
    return updated


def effective_goal_priority(goal: dict[str, Any], step: int) -> int:
    """Age paused goals so repeated preemption cannot starve them forever."""
    base = goal_priority(goal)
    if str(goal.get("status") or GOAL_STATUS_ACTIVE) != GOAL_STATUS_PAUSED:
        return base
    paused_at = int(goal.get("preempted_at") or goal.get("started_step") or step)
    age = max(0, int(step) - paused_at)
    return base + min(20, age // 5)

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
        visible_dishwasher_goal(observation, scene, step, baseline),
        visible_heat_milk_goal(observation, scene, step, baseline),
        visible_cook_egg_goal(observation, scene, step, baseline),
        visible_craft_sandwich_goal(observation, scene, step),
        visible_assemble_product_goal(observation, scene, step),
        visible_brew_coffee_goal(observation, scene, step),
        visible_print_goal(observation, scene, step, baseline),
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
    if str(updated.get("type") or "") == "skill" and skill == "dishwash_dishes":
        dishwasher = str(updated.get("dishwasher") or first_node_by_semantic(scene, {"dishwasher"}))
        return_target = str(updated.get("return_target") or "")
        updated["dishwasher"] = dishwasher
        updated["dishwasher_button"] = str(updated.get("dishwasher_button") or f"{dishwasher}_button")
        updated["return_target"] = return_target
        updated["target"] = dishwasher
        updated["phase"] = dishwasher_phase(scene, object_id, dishwasher, return_target)
        target_id = return_target if updated["phase"] == "unload" else dishwasher
    if str(updated.get("type") or "") == "skill" and skill == "heat_milk":
        microwave = str(updated.get("microwave") or first_node_by_semantic(scene, {"microwave"}))
        return_target = str(updated.get("return_target") or "")
        updated["microwave"] = microwave
        updated["microwave_button"] = str(updated.get("microwave_button") or f"{microwave}_button")
        updated["return_target"] = return_target
        updated["target"] = microwave
        updated["phase"] = heat_milk_phase(scene, object_id, microwave, return_target)
        target_id = return_target if updated["phase"] == "unload" else microwave
    if str(updated.get("type") or "") == "skill" and skill == "cook_egg":
        stove = str(updated.get("stove") or first_node_by_semantic(scene, {"stove"}))
        egg_id = str(updated.get("input_object") or "")
        return_target = str(updated.get("return_target") or "")
        output_id = str(updated.get("output_id") or "")
        if not output_id:
            outputs = [
                item for item in scene.get("nodes") or []
                if isinstance(item, dict)
                and str(item.get("semantic_type") or "") == "cooked_egg"
                and str(item.get("produced_by_device") or "") == stove
                and int(item.get("produced_at_step") or -1) >= int(updated.get("started_step") or 0)
            ]
            if outputs:
                outputs.sort(key=lambda item: str(item.get("id") or ""))
                output_id = str(outputs[-1].get("id") or "")
                updated["output_id"] = output_id
        updated["stove"] = stove
        updated["stove_button"] = str(updated.get("stove_button") or f"{stove}_button")
        updated["return_target"] = return_target
        updated["target"] = stove
        updated["phase"] = cook_egg_phase(scene, stove, output_id, egg_id)
        target_id = return_target if updated["phase"] == "serve" and output_id and str((node(scene, output_id) or {}).get("parent") or "") == robot_id else stove
    if str(updated.get("type") or "") == "skill" and skill == "craft_sandwich":
        workbench = str(updated.get("workbench") or first_node_by_semantic(scene, {"workbench"}))
        bread_id = str(updated.get("bread") or "")
        tomato_id = str(updated.get("tomato") or "")
        return_target = str(updated.get("return_target") or "")
        output_id = str(updated.get("output_id") or "")
        if not output_id:
            outputs = [
                item for item in scene.get("nodes") or []
                if isinstance(item, dict)
                and str(item.get("semantic_type") or "") == "sandwich"
                and str(item.get("produced_by_device") or "") == workbench
                and int(item.get("produced_at_step") or -1) >= int(updated.get("started_step") or 0)
            ]
            if outputs:
                outputs.sort(key=lambda item: str(item.get("id") or ""))
                output_id = str(outputs[-1].get("id") or "")
                updated["output_id"] = output_id
        updated["workbench"] = workbench
        updated["workbench_button"] = str(updated.get("workbench_button") or f"{workbench}_button")
        updated["return_target"] = return_target
        updated["target"] = workbench
        updated["phase"] = craft_sandwich_phase(scene, workbench, bread_id, tomato_id, output_id)
        target_id = return_target if updated["phase"] == "serve" and output_id and str((node(scene, output_id) or {}).get("parent") or "") == robot_id else workbench
    if str(updated.get("type") or "") == "skill" and skill == "assemble_product":
        line = str(updated.get("assembly_line") or first_node_by_semantic(scene, {"assembly_line"}))
        component_a = str(updated.get("component_a") or "")
        component_b = str(updated.get("component_b") or "")
        return_target = str(updated.get("return_target") or "")
        output_id = str(updated.get("output_id") or "")
        if not output_id:
            outputs = [
                item for item in scene.get("nodes") or []
                if isinstance(item, dict)
                and str(item.get("semantic_type") or "") == "finished_product"
                and str(item.get("produced_by_device") or "") == line
                and int(item.get("produced_at_step") or -1) >= int(updated.get("started_step") or 0)
            ]
            if outputs:
                outputs.sort(key=lambda item: str(item.get("id") or ""))
                output_id = str(outputs[-1].get("id") or "")
                updated["output_id"] = output_id
        updated["assembly_line"] = line
        updated["assembly_line_button"] = str(updated.get("assembly_line_button") or f"{line}_button")
        updated["return_target"] = return_target
        updated["target"] = line
        updated["phase"] = assemble_product_phase(scene, line, component_a, component_b, output_id)
        target_id = return_target if updated["phase"] == "inspect" and output_id and str((node(scene, output_id) or {}).get("parent") or "") == robot_id else line
    if str(updated.get("type") or "") == "skill" and skill == "brew_coffee":
        machine = str(updated.get("coffee_machine") or first_node_by_semantic(scene, {"coffeemachine", "coffee_machine"}))
        cup_id = str(updated.get("cup") or "")
        beans_id = str(updated.get("coffee_beans") or "")
        return_target = str(updated.get("return_target") or "")
        output_id = str(updated.get("output_id") or "")
        if not output_id:
            outputs = [
                item for item in scene.get("nodes") or []
                if isinstance(item, dict)
                and str(item.get("semantic_type") or "") == "coffee"
                and str(item.get("produced_by_device") or "") == machine
                and int(item.get("produced_at_step") or -1) >= int(updated.get("started_step") or 0)
            ]
            if outputs:
                outputs.sort(key=lambda item: str(item.get("id") or ""))
                output_id = str(outputs[-1].get("id") or "")
                updated["output_id"] = output_id
        updated["coffee_machine"] = machine
        updated["coffee_machine_button"] = str(updated.get("coffee_machine_button") or f"{machine}_button")
        updated["return_target"] = return_target
        updated["target"] = machine
        updated["phase"] = brew_coffee_phase(scene, machine, cup_id, beans_id, output_id)
        cup_parent = str((node(scene, cup_id) or {}).get("parent") or "")
        target_id = return_target if updated["phase"] == "serve" and output_id and cup_parent == robot_id else machine
    if str(updated.get("type") or "") == "skill" and skill == "print_document":
        printer = str(updated.get("printer") or first_node_by_semantic(scene, {"printer"}))
        return_target = str(updated.get("return_target") or "")
        updated["printer"] = printer
        updated["printer_button"] = str(updated.get("printer_button") or f"{printer}_button")
        updated["return_target"] = return_target
        receipts = [
            item for item in scene.get("nodes") or []
            if isinstance(item, dict)
            and str(item.get("semantic_type") or "") == "receipt"
            and str(item.get("parent") or "") == printer
        ]
        before = int(updated.get("receipt_count_before") or 0)
        before_ids = {str(item) for item in updated.get("receipt_ids_before") or []}
        new_receipts = [item for item in receipts if str(item.get("id") or "") not in before_ids]
        if len(receipts) > before and new_receipts and not updated.get("receipt_id"):
            new_receipts.sort(key=lambda item: str(item.get("id") or ""))
            updated["receipt_id"] = str(new_receipts[-1].get("id") or "")
        receipt_id = str(updated.get("receipt_id") or "")
        receipt_node = node(scene, receipt_id) or {}
        if receipt_id and str(receipt_node.get("parent") or "") == printer:
            updated["phase"] = "collect"
            target_id = printer
        elif receipt_id and str(receipt_node.get("parent") or "") == robot_id:
            updated["phase"] = "place"
            target_id = return_target
        else:
            updated["phase"] = "print"
            target_id = printer
        updated["target"] = target_id
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
    fields = ("object", "target", "return_target", "receipt_id", "food_home", "trash_bin", "trash_bin_home", "garbage_station", "sink", "washer", "drying_rack", "wardrobe")
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
    if str(goal.get("type") or "") == "skill" and str(goal.get("skill") or "") == "dishwash_dishes":
        states = object_node.get("states") or {}
        return bool(
            object_node
            and states.get("is_dirty") is not True
            and str(object_node.get("parent") or "") == str(goal.get("return_target") or goal.get("dishwasher") or "")
        )
    if str(goal.get("type") or "") == "skill" and str(goal.get("skill") or "") == "heat_milk":
        states = object_node.get("states") or {}
        return bool(
            object_node
            and str(states.get("temperature") or "") == "hot"
            and str(object_node.get("parent") or "") == str(goal.get("return_target") or "")
        )
    if str(goal.get("type") or "") == "skill" and str(goal.get("skill") or "") == "cook_egg":
        output_node = node(scene, str(goal.get("output_id") or "")) or {}
        return bool(
            output_node
            and str(output_node.get("semantic_type") or "") == "cooked_egg"
            and str(output_node.get("parent") or "") == str(goal.get("return_target") or "")
        )
    if str(goal.get("type") or "") == "skill" and str(goal.get("skill") or "") == "craft_sandwich":
        output_node = node(scene, str(goal.get("output_id") or "")) or {}
        return bool(
            output_node
            and str(output_node.get("semantic_type") or "") == "sandwich"
            and str(output_node.get("parent") or "") == str(goal.get("return_target") or "")
        )
    if str(goal.get("type") or "") == "skill" and str(goal.get("skill") or "") == "assemble_product":
        output_node = node(scene, str(goal.get("output_id") or "")) or {}
        return bool(
            output_node
            and str(output_node.get("semantic_type") or "") == "finished_product"
            and str(output_node.get("parent") or "") == str(goal.get("return_target") or "")
        )
    if str(goal.get("type") or "") == "skill" and str(goal.get("skill") or "") == "brew_coffee":
        output_node = node(scene, str(goal.get("output_id") or "")) or {}
        cup_node = node(scene, str(goal.get("cup") or "")) or {}
        return bool(
            output_node
            and str(output_node.get("semantic_type") or "") == "coffee"
            and str(output_node.get("parent") or "") == str(goal.get("cup") or "")
            and str(cup_node.get("parent") or "") == str(goal.get("return_target") or "")
        )
    if str(goal.get("type") or "") == "skill" and str(goal.get("skill") or "") == "print_document":
        receipt_id = str(goal.get("receipt_id") or "")
        receipt_node = node(scene, receipt_id) or {}
        return bool(
            receipt_node
            and str(receipt_node.get("semantic_type") or "") == "receipt"
            and str(receipt_node.get("parent") or "") == str(goal.get("return_target") or "")
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
    if skill == "cook_egg":
        claims.add(str(goal.get("stove") or goal.get("target") or ""))
        claims.add(str(goal.get("input_object") or ""))
        claims.add(str(goal.get("return_target") or ""))
    if skill == "craft_sandwich":
        claims.update({str(goal.get("workbench") or ""), str(goal.get("bread") or ""), str(goal.get("tomato") or ""), str(goal.get("return_target") or "")})
    if skill == "assemble_product":
        claims.update({str(goal.get("assembly_line") or ""), str(goal.get("component_a") or ""), str(goal.get("component_b") or ""), str(goal.get("return_target") or "")})
    if skill == "brew_coffee":
        claims.update({str(goal.get("coffee_machine") or ""), str(goal.get("cup") or ""), str(goal.get("coffee_beans") or ""), str(goal.get("return_target") or "")})
    if skill in HOSPITAL_RETURN_SKILLS | HOSPITAL_CLEAN_SKILLS:
        claims.add(str(goal.get("target") or ""))
    if str(goal.get("type") or "") == "restore_initial_position":
        claims.add(str(goal.get("target") or ""))
    return {claim for claim in claims if claim}


def goal_conflicts_with_claims(goal: dict[str, Any] | None, claimed: set[str]) -> bool:
    if not goal:
        return False
    return bool(active_goal_claims(goal) & claimed)


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
    goal = start_goal(goal, int(goal.get("started_step") or step))
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
    updated["status"] = GOAL_STATUS_ACTIVE
    return updated
