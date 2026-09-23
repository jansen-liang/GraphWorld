from __future__ import annotations

from typing import Any


TASK_SKILLS: tuple[dict[str, Any], ...] = (
    {
        "name": "dispose_food",
        "trigger": "food is_rotten=true or is_burnt=true",
        "goal": "food is moved through trash_bin to garbage_station, food is restored, and trash_bin is returned home",
        "phases": [
            {
                "phase": "collect_food",
                "if": "bad food is not in trash_bin",
                "next": "pick food, place food in resolved trash_bin node id",
            },
            {
                "phase": "take_bin",
                "if": "bad food is already in trash_bin",
                "next": "pick trash_bin",
            },
            {
                "phase": "dump_bin",
                "if": "robot holds trash_bin",
                "next": "move to resolved garbage_station node id, dump trash_bin; food refreshes to fridge",
            },
            {
                "phase": "return_bin",
                "if": "trash_bin is not back at its resolved home node id",
                "next": "move back to trash_bin_home, place trash_bin there",
            },
        ],
    },
    {
        "name": "empty_cup",
        "trigger": "cup fill_level>0 or is_full=true",
        "goal": "cup fill_level=0 and is_full=false",
        "phases": [
            {
                "phase": "dump_cup",
                "if": "cup contains liquid",
                "next": "pick cup, move to resolved sink node id, dump cup into sink",
            },
        ],
    },
    {
        "name": "water_plant",
        "trigger": "plant vitality is below 1 or plant is_wilted=true",
        "goal": "plant is watered and vitality is restored above zero",
        "phases": [
            {"phase": "fill", "next": "fill wateringcan at a sink or use an available filled wateringcan"},
            {"phase": "water", "next": "carry wateringcan to plant or vase and dump water"},
            {"phase": "recover", "next": "plant vitality increases and wilted state clears"},
        ],
    },
    {
        "name": "refill_vase",
        "trigger": "vase has_water=false while containing a flower or plant",
        "goal": "vase has_water=true and contained flower remains hydrated",
        "phases": [
            {"phase": "fill", "next": "fill wateringcan at a sink or obtain a filled wateringcan"},
            {"phase": "pour", "next": "carry wateringcan to vase and dump water into it"},
            {"phase": "stabilize", "next": "contained flower vitality can recover on later timed transitions"},
        ],
    },
    {
        "name": "laundry_clothes",
        "trigger": "cloth is_dirty=true or is_wet=true or folded=false",
        "goal": "cloth is in wardrobe and is_dirty=false and is_wet=false and folded=true",
        "phases": [
            {
                "phase": "load_detergent",
                "if": "a finite detergent source is available and washer has no detergent instance",
                "next": "dispense or pick detergent, then place one detergent instance in the washer",
            },
            {
                "phase": "wash_load",
                "if": "cloth is_dirty=true and cloth is not in washer",
                "next": "pick cloth, open washer, place cloth in washer",
            },
            {
                "phase": "start_washer",
                "if": "cloth is_dirty=true and cloth is in washer and washer is not running",
                "next": "close washer, then press washer or washer_button",
            },
            {
                "phase": "dry",
                "if": "cloth is_wet=true",
                "next": "pick cloth from washer, place cloth on drying_rack, wait until dry",
            },
            {
                "phase": "fold",
                "if": "cloth is_dirty=false and is_wet=false and folded=false",
                "next": "fold cloth",
            },
            {
                "phase": "store",
                "if": "cloth is clean, dry, folded, and not in wardrobe",
                "next": "pick cloth, open wardrobe, place cloth in wardrobe, close wardrobe",
            },
        ],
    },
    {
        "name": "dishwash_dishes",
        "trigger": "dishwasher is idle and contains dirty dishes",
        "goal": "contained dishes are clean and dry after the dishwasher cycle",
        "phases": [
            {"phase": "load", "next": "place dirty dishes in the dishwasher and close its door"},
            {"phase": "run", "next": "press dishwasher or dishwasher_button and wait for completion"},
            {"phase": "unload", "next": "open dishwasher and place clean dishes at their requested storage surface"},
        ],
    },
    {
        "name": "flush_toilet",
        "trigger": "toilet is_dirty=true",
        "goal": "toilet is_dirty=false",
        "phases": [
            {"phase": "reach_control", "next": "move to toilet_flush_button or toilet"},
            {"phase": "flush", "next": "press toilet_flush_button; toilet becomes clean"},
        ],
    },
    {
        "name": "heat_milk",
        "trigger": "milk temperature is cold or room",
        "goal": "milk temperature=hot and milk remains in a reachable container",
        "phases": [
            {"phase": "load", "next": "open microwave, place milk in microwave, close microwave"},
            {"phase": "run", "next": "press microwave_button and wait for cycle completion"},
            {"phase": "unload", "next": "open microwave, pick hot milk, place it at the requested surface"},
        ],
    },
    {
        "name": "brew_coffee",
        "trigger": "coffee machine has water, coffee_beans, and cup and is not running",
        "goal": "a coffee output is produced in the cup",
        "phases": [
            {"phase": "prepare", "next": "place coffee_beans and cup in coffee machine; fill water"},
            {"phase": "run", "next": "press coffee machine and wait for timed process"},
            {"phase": "serve", "next": "pick or place the cup with the generated coffee"},
        ],
    },
    {
        "name": "craft_sandwich",
        "trigger": "workbench has bread and tomato and is not running",
        "goal": "a sandwich output is produced and available on the workbench",
        "phases": [
            {"phase": "collect", "next": "dispense or pick bread and tomato"},
            {"phase": "prepare", "next": "place bread and tomato on workbench"},
            {"phase": "craft", "next": "press workbench and wait for completion"},
            {"phase": "serve", "next": "pick the generated sandwich and place it at the requested surface"},
        ],
    },
    {
        "name": "cook_egg",
        "trigger": "stove has an egg and is not running",
        "goal": "cooked_egg is produced at the stove",
        "phases": [
            {"phase": "prepare", "next": "place an egg on the stove"},
            {"phase": "cook", "next": "press stove and wait for the timed cooking cycle"},
            {"phase": "serve", "next": "pick cooked_egg and place it at the requested surface"},
        ],
    },
    {
        "name": "print_document",
        "trigger": "printer is idle and has paper and ink",
        "goal": "a new receipt is produced, collected, and placed on a compatible surface",
        "phases": [
            {"phase": "check_supplies", "next": "verify printer count and amount are both at least one"},
            {"phase": "print", "next": "press printer and wait for the timed process"},
            {"phase": "collect", "next": "pick the generated receipt from the printer"},
            {"phase": "place", "next": "place the receipt on the requested compatible surface"},
        ],
    },
    {
        "name": "assemble_product",
        "trigger": "assembly_line is not running and component_a/component_b are available either in its input buffer or at an upstream station",
        "goal": "finished_product is produced and available at the assembly line",
        "phases": [
            {"phase": "collect", "next": "locate component_a and component_b in warehouse or upstream station"},
            {"phase": "transit", "next": "pick each component, move through the permitted room path, and keep it attached to the agent or cart"},
            {"phase": "load", "next": "place both components in the assembly_line input buffer"},
            {"phase": "run", "next": "press assembly_line and wait for completion"},
            {"phase": "inspect", "next": "pick the finished_product and place it at the inspection surface"},
        ],
    },
    {
        "name": "restock_cabinet",
        "trigger": "required item is missing from a cabinet storage slot",
        "goal": "required item is placed in a valid cabinet slot without overlap",
        "phases": [
            {"phase": "collect", "next": "dispense or pick the required item"},
            {"phase": "access", "next": "open cabinet or drawer"},
            {"phase": "store", "next": "place item in a compatible storage slot and close the compartment"},
        ],
    },
    {
        "name": "access_control_delivery",
        "trigger": "delivery item is waiting at a controlled entrance",
        "goal": "item crosses the access-controlled door and reaches the receiving area",
        "phases": [
            {"phase": "authenticate", "next": "use access control button or badge"},
            {"phase": "transit", "next": "open door, move through doorway, close door"},
            {"phase": "deliver", "next": "place item at the receiving surface"},
        ],
    },
    {
        "name": "replenish_prescription_sheet",
        "trigger": "prescription_sheet is in prescription_return_lobby or otherwise not back at outpatient clinic desk/room",
        "goal": "blank prescription sheet is restored to its initial outpatient clinic location",
        "phases": [{"phase": "return_item", "next": "pick prescription_sheet from the return tray, move to outpatient clinic, place it at its initial parent"}],
    },
    {
        "name": "replenish_medicine_box",
        "trigger": "medicine_box is in supply_zone_lobby or otherwise not back in pharmacy",
        "goal": "medicine_box is restored to pharmacy so the next patient can get medicine",
        "phases": [{"phase": "return_item", "next": "pick medicine_box from the lobby supply zone, move to pharmacy, place it at its initial parent"}],
    },
    {
        "name": "return_refrigerated_medicine",
        "trigger": "refrigerated_medicine is in supply_zone_lobby or otherwise not back in medicine_fridge",
        "goal": "refrigerated medicine is restored to medicine_fridge",
        "phases": [{"phase": "return_item", "next": "pick refrigerated_medicine from the lobby supply zone, open medicine_fridge if needed, place it in medicine_fridge, close it"}],
    },
    {
        "name": "clean_medical_waste",
        "trigger": "medical_waste is outside medical_waste_bin",
        "goal": "medical waste is placed in medical_waste_bin",
        "phases": [{"phase": "return_item", "next": "pick medical_waste and place it in medical_waste_bin"}],
    },
    {
        "name": "collect_dirty_linen",
        "trigger": "dirty bed_sheet is outside linen_bin",
        "goal": "dirty bed sheet is placed in dirty_linen_bin",
        "phases": [{"phase": "return_item", "next": "pick dirty bed sheet and place it in dirty_linen_bin"}],
    },
    {
        "name": "restock_clean_sheet",
        "trigger": "clean bed_sheet is not in supply_cabinet",
        "goal": "clean bed sheet is restored to supply_cabinet for the next bed change",
        "phases": [{"phase": "return_item", "next": "pick clean bed sheet and place it in supply_cabinet"}],
    },
    {
        "name": "return_wheelchair",
        "trigger": "wheelchair is not at entrance",
        "goal": "wheelchair is restored to its initial entrance location",
        "phases": [{"phase": "return_item", "next": "pick or move wheelchair back to its initial parent"}],
    },
    {
        "name": "clean_waiting_area",
        "trigger": "waiting area seats are dirty",
        "goal": "waiting area seats are clean",
        "phases": [{"phase": "clean_surface", "next": "move to seats_waiting_area and brush it"}],
    },
    {
        "name": "clean_exam_bed",
        "trigger": "exam bed is dirty",
        "goal": "exam bed is clean",
        "phases": [{"phase": "clean_surface", "next": "move to exam_bed and brush it"}],
    },
)


SKILLS_BY_NAME = {str(skill["name"]): skill for skill in TASK_SKILLS}


def relevant_skills_for_nodes(nodes: dict[str, dict[str, Any]], active_goal: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if active_goal and active_goal.get("skill") in SKILLS_BY_NAME:
        return [SKILLS_BY_NAME[str(active_goal.get("skill"))]]
    relevant: list[dict[str, Any]] = []
    assembly_line_available_parts = {
        str(item.get("semantic_type") or "")
        for item in nodes.values()
        if str(item.get("semantic_type") or "") in {"component_a", "component_b"}
    }
    vase_ids_with_flower: set[str] = {
        str(item.get("parent") or "")
        for item in nodes.values()
        if str(item.get("semantic_type") or "") in {"flower", "plant"} and item.get("parent")
    }
    for item in nodes.values():
        semantic = str(item.get("semantic_type") or "")
        states = item.get("states") or {}
        if semantic == "food" and (states.get("is_rotten") is True or states.get("is_burnt") is True):
            relevant.append(SKILLS_BY_NAME["dispose_food"])
        if semantic == "cup" and (float(states.get("fill_level") or 0.0) > 0.0 or states.get("is_full") is True):
            relevant.append(SKILLS_BY_NAME["empty_cup"])
        if semantic in {"plant", "flower"} and (
            bool(states.get("is_wilted", False)) or float(states.get("vitality", 1.0) or 0.0) < 1.0
        ):
            relevant.append(SKILLS_BY_NAME["water_plant"])
        if semantic == "vase" and str(item.get("id") or "") in vase_ids_with_flower and not bool(states.get("has_water", False)):
            relevant.append(SKILLS_BY_NAME["refill_vase"])
        if semantic in {"clothes", "towel", "blanket"} and (
            states.get("is_dirty") is True or states.get("is_wet") is True or states.get("folded") is False
        ):
            relevant.append(SKILLS_BY_NAME["laundry_clothes"])
        if semantic == "dishwasher" and not states.get("is_running", False):
            children = [
                child for child in nodes.values()
                if str(child.get("parent") or "") == str(item.get("id") or "")
            ]
            if any(
                str(child.get("semantic_type") or "") in {"bowl", "plate", "cup", "dish", "utensil"}
                and (child.get("states") or {}).get("is_dirty") is True
                for child in children
            ):
                relevant.append(SKILLS_BY_NAME["dishwash_dishes"])
        if semantic == "toilet" and states.get("is_dirty") is True:
            relevant.append(SKILLS_BY_NAME["flush_toilet"])
        if semantic in {"milk", "juice"} and states.get("temperature") in {"cold", "room"}:
            relevant.append(SKILLS_BY_NAME["heat_milk"])
        if semantic in {"coffeemachine", "coffee_machine"} and not states.get("is_running", False):
            relevant.append(SKILLS_BY_NAME["brew_coffee"])
        if semantic == "workbench" and not states.get("is_running", False):
            relevant.append(SKILLS_BY_NAME["craft_sandwich"])
        if semantic == "stove" and not states.get("is_running", False):
            children = {str(child.get("semantic_type") or "") for child in nodes.values() if str(child.get("parent") or "") == str(item.get("id") or "")}
            if "egg" in children:
                relevant.append(SKILLS_BY_NAME["cook_egg"])
        if semantic == "printer" and not states.get("is_running", False):
            if float(states.get("count") or 0.0) >= 1.0 and float(states.get("amount") or 0.0) >= 1.0:
                relevant.append(SKILLS_BY_NAME["print_document"])
        if semantic == "assembly_line" and not states.get("is_running", False):
            # Task discovery includes upstream inventory. The process layer
            # still requires both parts to be physically placed in the line.
            if {"component_a", "component_b"}.issubset(assembly_line_available_parts):
                relevant.append(SKILLS_BY_NAME["assemble_product"])
        if semantic == "prescription_sheet":
            relevant.append(SKILLS_BY_NAME["replenish_prescription_sheet"])
        if semantic == "medicine_box":
            relevant.append(SKILLS_BY_NAME["replenish_medicine_box"])
        if semantic == "refrigerated_medicine":
            relevant.append(SKILLS_BY_NAME["return_refrigerated_medicine"])
        if semantic == "medical_waste":
            relevant.append(SKILLS_BY_NAME["clean_medical_waste"])
        if semantic == "bed_sheet":
            relevant.append(SKILLS_BY_NAME["collect_dirty_linen"])
            relevant.append(SKILLS_BY_NAME["restock_clean_sheet"])
        if semantic == "wheelchair":
            relevant.append(SKILLS_BY_NAME["return_wheelchair"])
        if str(item.get("id") or "") == "seats_waiting_area" and states.get("is_dirty") is True:
            relevant.append(SKILLS_BY_NAME["clean_waiting_area"])
        if semantic == "bed" and states.get("is_dirty") is True:
            relevant.append(SKILLS_BY_NAME["clean_exam_bed"])
    deduped = {str(skill["name"]): skill for skill in relevant}
    return list(deduped.values())


__all__ = ["TASK_SKILLS", "relevant_skills_for_nodes"]
