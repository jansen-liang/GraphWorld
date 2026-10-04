from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import deque
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCENE_DIR = ROOT / "backend" / "data" / "sg_output" / "simple_graph"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.generation.assets.npc_library import ROLE_SCHEDULES, get_default_npcs
from backend.core.state import DISCRETE_STATE_SPACE

BASE_SCENES = (
    "simple_home_1f",
    "simple_hospital_1f",
    "simple_supermarket_1f",
    "simple_office_1f",
    "simple_factory_1f",
)

PROFILES = ("compact_cleaning", "normal_logistics", "spread_device")

PARENT_RELATIONS = {"at", "in", "on", "near", "held_by", "inside", "contains", "belongs_to"}
ROOM_CONNECTIVITY_RELATIONS = {"connected", "next_to", "neighbour"}


def scene_type(scene_name: str) -> str:
    for item in ("hospital", "supermarket", "office", "factory"):
        if item in scene_name:
            return item
    return "home"


def nodes_by_id(scene: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(node.get("id")): node for node in scene.get("nodes") or [] if node.get("id")}


def node(scene: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    return nodes_by_id(scene).get(node_id)


def set_states(scene: dict[str, Any], node_id: str, **states: Any) -> None:
    invalid = sorted(set(states) - set(DISCRETE_STATE_SPACE))
    if invalid:
        raise ValueError(f"{node_id} uses states outside DISCRETE_STATE_SPACE: {invalid}")
    item = node(scene, node_id)
    if item is None:
        return
    item.setdefault("states", {}).update(states)


def set_parent(scene: dict[str, Any], node_id: str, parent_id: str) -> None:
    ids = nodes_by_id(scene)
    child = ids.get(str(node_id))
    parent = ids.get(str(parent_id))
    if child is None or parent is None:
        return
    relation = relation_for_parent(scene, child, parent)
    scene.setdefault("edges", [])[:] = [
        edge for edge in scene.get("edges") or []
        if not (str(edge.get("target_id") or "") == str(node_id) and str(edge.get("relation") or "") in PARENT_RELATIONS)
    ]
    scene["edges"].append(edge_shape(scene, str(parent_id), str(node_id), relation))


def ensure_node(scene: dict[str, Any], item: dict[str, Any]) -> None:
    item = copy.deepcopy(item)
    host_id = str(item.pop("host_id", "") or "")
    item["editor_id"] = str(item.get("id") or "")
    existing = node(scene, str(item["id"]))
    if existing:
        existing.update(item)
    else:
        scene.setdefault("nodes", []).append(item)
    if host_id:
        set_parent(scene, str(item["id"]), host_id)


def ensure_home_support_nodes(scene: dict[str, Any]) -> None:
    support_nodes = (
        {
            "id": "garbage_station_outside_home",
            "name": "garbage station",
            "name_cn": "垃圾处理站",
            "node_type": "object",
            "semantic_type": "garbage_station",
            "states": {},
            "host_id": "outside_home",
            "interactive_actions": ["move", "dump"],
        },
        {
            "id": "food_living_room",
            "name": "food",
            "name_cn": "food",
            "node_type": "object",
            "semantic_type": "food",
            "states": {"is_cooked": True, "is_rotten": False},
            "host_id": "fridge_kitchen",
            "interactive_actions": ["pick", "place"],
        },
        {
            "id": "plate_living_room",
            "name": "plate",
            "name_cn": "plate",
            "node_type": "object",
            "semantic_type": "plate",
            "states": {"is_dirty": False},
            "host_id": "dishwasher_kitchen",
            "interactive_actions": ["pick", "place", "brush"],
        },
        {
            "id": "cup_living_room",
            "name": "cup",
            "name_cn": "cup",
            "node_type": "object",
            "semantic_type": "cup",
            "states": {"is_dirty": False, "is_wet": False},
            "host_id": "dishwasher_kitchen",
            "interactive_actions": ["pick", "place", "brush"],
        },
    )
    for item in support_nodes:
        ensure_node(scene, item)


def normalize_room_parents(scene: dict[str, Any]) -> None:
    ids = nodes_by_id(scene)
    if "F1" not in ids:
        return
    for item in scene.get("nodes") or []:
        if str(item.get("node_type") or "") == "room" and not any(
            str(edge.get("target_id") or "") == str(item.get("id") or "")
            and str(edge.get("relation") or "") in PARENT_RELATIONS
            for edge in scene.get("edges") or []
        ):
            set_parent(scene, str(item["id"]), "F1")


def relation_for_parent(scene: dict[str, Any], child: dict[str, Any], parent: dict[str, Any]) -> str:
    child_type = str(child.get("node_type") or "")
    parent_type = str(parent.get("node_type") or "")
    child_sem = str(child.get("semantic_type") or "")
    parent_sem = str(parent.get("semantic_type") or "")
    if child_type == "room":
        return "contains"
    if child_type == "agent":
        return "at"
    if parent_type == "room":
        return "inside_room" if child_type == "object" else "in"
    if parent_sem in {"table", "counter", "shelf", "rack", "drying_rack", "desk", "bed"}:
        return "on"
    if child_sem in {"seat", "chair"}:
        return "near"
    return "in"


def edge_shape(scene: dict[str, Any], source: str, target: str, relation: str) -> dict[str, Any]:
    ids = nodes_by_id(scene)
    source_type = str((ids.get(source) or {}).get("node_type") or "")
    target_type = str((ids.get(target) or {}).get("node_type") or "")
    if relation in ROOM_CONNECTIVITY_RELATIONS:
        return {
            "source_id": source,
            "target_id": target,
            "edge_type": "structural_edge",
            "relation": "connected",
            "category": "structural",
            "properties": {},
        }
    if source_type == "object" and target_type == "room":
        edge_type = "room_floor_edge"
        category = "structural"
    elif target_type == "room":
        edge_type = "room_floor_edge"
        category = "structural"
    elif source_type == "room" and target_type == "object":
        edge_type = "object_edge"
        category = "structural"
    elif target_type in {"object", "agent"}:
        edge_type = "containment_edge"
        category = "containment"
    else:
        edge_type = "object_edge"
        category = "structural"
    return {
        "source_id": source,
        "target_id": target,
        "edge_type": edge_type,
        "relation": relation,
        "category": category,
        "properties": {},
    }


def rebuild_children_and_parent_edges(scene: dict[str, Any]) -> None:
    scene["nodes"] = [
        {key: value for key, value in item.items() if key not in {"parent", "child", "host_id", "floor_id", "runtime_relation"}}
        for item in scene.get("nodes") or []
    ]
    scene["edges"] = [
        edge for edge in scene.get("edges") or []
        if str(edge.get("source_id") or "") in nodes_by_id(scene)
        and str(edge.get("target_id") or "") in nodes_by_id(scene)
    ]


def set_room_connections(scene: dict[str, Any], pairs: list[tuple[str, str]] | None) -> None:
    if pairs is None:
        return
    scene["edges"] = [
        edge
        for edge in scene.get("edges") or []
        if str(edge.get("relation") or "").lower() not in ROOM_CONNECTIVITY_RELATIONS
    ]
    ids = nodes_by_id(scene)
    seen: set[tuple[str, str]] = set()
    for source, target in pairs:
        if source not in ids or target not in ids:
            continue
        key = tuple(sorted((source, target)))
        if key in seen:
            continue
        scene.setdefault("edges", []).append(edge_shape(scene, source, target, "connected"))
        seen.add(key)


ROOM_CONNECTIONS: dict[str, dict[str, list[tuple[str, str]] | None]] = {
    "home": {
        "compact_cleaning": [
            ("outside_home", "entrance"),
            ("entrance", "living_room"),
            ("living_room", "kitchen"),
            ("living_room", "bathroom"),
            ("living_room", "bedroom"),
            ("kitchen", "balcony"),
            ("bedroom", "bathroom"),
        ],
        "normal_logistics": None,
        "spread_device": [
            ("outside_home", "entrance"),
            ("entrance", "living_room"),
            ("living_room", "kitchen"),
            ("kitchen", "bathroom"),
            ("bathroom", "bedroom"),
            ("bedroom", "balcony"),
        ],
    },
    "hospital": {
        "compact_cleaning": [
            ("outside_home", "entrance"),
            ("entrance", "lobby"),
            ("lobby", "registration"),
            ("lobby", "waiting_area"),
            ("waiting_area", "outpatient_clinic_1"),
            ("outpatient_clinic_1", "treatment_room"),
            ("lobby", "pharmacy"),
            ("lobby", "staff_room"),
            ("lobby", "corridor_main"),
        ],
        "normal_logistics": None,
        "spread_device": [
            ("outside_home", "entrance"),
            ("entrance", "lobby"),
            ("lobby", "registration"),
            ("registration", "waiting_area"),
            ("waiting_area", "corridor_main"),
            ("corridor_main", "outpatient_clinic_1"),
            ("outpatient_clinic_1", "treatment_room"),
            ("treatment_room", "staff_room"),
            ("staff_room", "pharmacy"),
        ],
    },
    "supermarket": {
        "compact_cleaning": [
            ("outside_home", "entrance"),
            ("entrance", "checkout_area"),
            ("checkout_area", "produce_area"),
            ("checkout_area", "shelf_area"),
            ("checkout_area", "cold_storage"),
            ("checkout_area", "staff_room"),
        ],
        "normal_logistics": None,
        "spread_device": [
            ("outside_home", "entrance"),
            ("entrance", "produce_area"),
            ("produce_area", "shelf_area"),
            ("shelf_area", "checkout_area"),
            ("checkout_area", "staff_room"),
            ("staff_room", "cold_storage"),
        ],
    },
    "office": {
        "compact_cleaning": [
            ("outside_home", "entrance"),
            ("entrance", "open_office"),
            ("open_office", "meeting_room"),
            ("open_office", "pantry"),
            ("open_office", "manager_office"),
            ("open_office", "restroom"),
        ],
        "normal_logistics": None,
        "spread_device": [
            ("outside_home", "entrance"),
            ("entrance", "open_office"),
            ("open_office", "meeting_room"),
            ("meeting_room", "manager_office"),
            ("manager_office", "pantry"),
            ("pantry", "restroom"),
        ],
    },
    "factory": {
        "compact_cleaning": [
            ("outside_home", "entrance"),
            ("entrance", "workshop"),
            ("workshop", "assembly_line"),
            ("workshop", "warehouse"),
            ("workshop", "control_room"),
            ("workshop", "break_room"),
            ("break_room", "restroom"),
        ],
        "normal_logistics": None,
        "spread_device": [
            ("outside_home", "entrance"),
            ("entrance", "break_room"),
            ("break_room", "restroom"),
            ("restroom", "workshop"),
            ("workshop", "assembly_line"),
            ("assembly_line", "warehouse"),
            ("warehouse", "control_room"),
        ],
    },
}


def apply_cleaning_profile(scene: dict[str, Any], typ: str) -> None:
    add_stable_clean_denominator(scene)
    if typ == "home":
        for item in (
            "coffee_table_living_room",
            "sofa_living_room",
            "sink_bathroom",
            "sink_kitchen",
            "toilet_bathroom",
            "tv_living_room",
            "bench_entrance",
            "chair_balcony",
        ):
            set_states(scene, item, is_dirty=False)
    elif typ == "hospital":
        for item in (
            "bench_lobby",
            "counter_registration",
            "seats_waiting_area",
            "exam_bed_clinic_1",
            "treatment_bed_treatment_room",
            "medical_cart_treatment_room",
        ):
            set_states(scene, item, is_dirty=False)
        set_states(scene, "used_syringe_treatment_room", is_dirty=False)
    elif typ == "supermarket":
        for item in ("counter_checkout", "table_checkout", "shelf_produce", "shelf_dry_goods", "table_staff_room"):
            set_states(scene, item, is_dirty=False)
        set_states(scene, "trash_bin_checkout", is_dirty=False)
    elif typ == "office":
        for item in (
            "desk_open_office_1",
            "desk_open_office_2",
            "table_meeting_room",
            "counter_pantry",
            "desk_manager_office",
            "seat_meeting_room",
            "seat_open_office_1",
        ):
            set_states(scene, item, is_dirty=False)
    elif typ == "factory":
        for item in ("table_workshop", "machine_assembly_line", "machine_workshop", "table_break_room", "seat_break_room"):
            set_states(scene, item, is_dirty=False)


def add_stable_clean_denominator(scene: dict[str, Any]) -> None:
    excluded = {"button", "room_light", "door", "knob", "floor", "human", "robot"}
    for item in scene.get("nodes") or []:
        node_type = str(item.get("node_type") or "")
        semantic = str(item.get("semantic_type") or "")
        if node_type not in {"object", "agent"} or semantic in excluded:
            continue
        item.setdefault("states", {}).setdefault("is_dirty", False)


def apply_logistics_profile(scene: dict[str, Any], typ: str) -> None:
    apply_changed_state_tracking(scene, typ)
    add_logistics_support_denominator(scene, typ)
    if typ == "home":
        for item in ("clothes_bedroom_1", "clothes_bedroom_2", "clothes_bedroom_3"):
            set_states(scene, item, is_dirty=False, is_wet=False, folded=True)
        for item in ("shoes_entrance_1", "shoes_entrance_2", "shoes_entrance_3", "toothbrush_bathroom", "cup_bathroom"):
            set_states(scene, item, is_dirty=False, is_wet=False)
        set_states(scene, "dishwasher_kitchen", is_dirty=False, is_open=False, is_on=False)
        set_states(scene, "washer_bathroom", is_dirty=False, is_open=False, is_on=False)
    elif typ == "hospital":
        for item in (
            "prescription_sheet_clinic_1",
            "medical_form_registration",
            "medicine_box_pharmacy",
            "refrigerated_medicine_pharmacy",
            "clean_sheet_storage",
            "dirty_sheet_treatment_room",
            "wheelchair_entrance",
        ):
            set_states(scene, item, is_dirty=False, is_wet=False)
        set_states(scene, "medicine_fridge_pharmacy", is_open=False, is_on=True, temperature="cold")
        set_states(scene, "medical_waste_bin_treatment_room", fill_level=0.0, is_full=False, is_dirty=False)
        set_states(scene, "dirty_linen_bin_treatment_room", fill_level=0.0, is_full=False, is_dirty=False)
    elif typ == "supermarket":
        for item in ("cart_entrance", "box_shelf_stock", "box_cold_storage"):
            set_states(scene, item, is_dirty=False)
        for item in ("fruit_produce_1", "milk_cold_storage_1", "juice_cold_storage_1", "drink_shelf_1"):
            set_states(scene, item, is_rotten=False, temperature="cold" if "cold_storage" in item else "room")
        set_states(scene, "counter_checkout", is_dirty=False)
        set_states(scene, "display_checkout", is_on=False)
    elif typ == "office":
        set_states(scene, "report_open_office", is_dirty=False)
        set_states(scene, "cup_pantry", is_dirty=False, is_wet=False)
        for item in ("printer_open_office", "display_meeting_room", "computer_open_office_1", "computer_manager_office"):
            set_states(scene, item, is_on=False if item in {"printer_open_office", "display_meeting_room"} else True)
    elif typ == "factory":
        for item in ("safety_gear_entrance", "box_warehouse_1", "box_warehouse_2", "cart_warehouse", "toolkit_workshop", "quality_record_control"):
            set_states(scene, item, is_dirty=False)
        set_states(scene, "box_warehouse_1", is_full=False, fill_level=0.9)
        set_states(scene, "machine_assembly_line", is_on=False)
        set_states(scene, "display_control_room", is_on=False)


def add_logistics_support_denominator(scene: dict[str, Any], typ: str) -> None:
    stable_by_scene = {
        "home": ("cup_bathroom", "toothbrush_bathroom", "toothpaste_bathroom", "plate_living_room", "cup_living_room"),
        "hospital": ("medical_form_registration", "medicine_box_pharmacy", "wheelchair_entrance"),
        "supermarket": ("cart_entrance", "box_shelf_stock", "box_cold_storage"),
        "office": ("report_open_office", "cup_pantry", "book_meeting_room"),
        "factory": ("safety_gear_entrance", "box_warehouse_1", "toolkit_workshop", "quality_record_control"),
    }
    for node_id in stable_by_scene.get(typ, ()):
        set_states(scene, node_id, is_dirty=False)


def apply_device_profile(scene: dict[str, Any], typ: str) -> None:
    apply_changed_state_tracking(scene, typ)
    if typ == "home":
        for item in ("dishwasher_kitchen", "washer_bathroom"):
            set_states(scene, item, is_open=False, is_on=False, cycle_remaining=0)
    elif typ == "hospital":
        for item in ("computer_registration", "computer_clinic_1", "queue_screen_waiting_area", "printer_registration"):
            set_states(scene, item, is_on=False)
        set_states(scene, "medicine_fridge_pharmacy", is_open=False, is_on=True, temperature="cold")
    elif typ == "supermarket":
        set_states(scene, "fridge_cold_storage", is_open=False, is_on=True, fill_level=0.6, is_full=False)
        set_states(scene, "display_checkout", is_on=False)
        for item in ("milk_cold_storage_1", "juice_cold_storage_1"):
            set_states(scene, item, temperature="cold", is_rotten=False)
    elif typ == "office":
        set_states(scene, "display_meeting_room", is_on=False)
        set_states(scene, "printer_open_office", is_on=False)
    elif typ == "factory":
        set_states(scene, "machine_assembly_line", is_on=False, is_dirty=False)
        for item in ("display_control_room", "button_assembly_line", "button_control_room"):
            set_states(scene, item, is_on=False)


def apply_changed_state_tracking(scene: dict[str, Any], typ: str) -> None:
    if typ == "home":
        for item in ("clothes_bedroom_1", "clothes_bedroom_2", "clothes_bedroom_3"):
            set_states(scene, item, is_dirty=False, is_wet=False, folded=True)
        for item in ("shoes_entrance_1", "shoes_entrance_2", "shoes_entrance_3"):
            set_states(scene, item, is_dirty=False, is_wet=False)
        for item in ("sink_bathroom", "toilet_bathroom", "door_entrance"):
            set_states(scene, item, is_dirty=False)
        set_states(scene, "sink_bathroom", is_full=False, fill_level=0.0)
    elif typ == "hospital":
        for item in ("exam_bed_clinic_1", "treatment_bed_treatment_room", "seats_waiting_area"):
            set_states(scene, item, is_dirty=False)
        for item in ("dirty_sheet_treatment_room", "clean_sheet_storage", "used_syringe_treatment_room"):
            set_states(scene, item, is_dirty=False)
    elif typ == "supermarket":
        set_states(scene, "counter_checkout", is_dirty=False)
        set_states(scene, "table_checkout", is_dirty=False)
        set_states(scene, "trash_bin_checkout", fill_level=0.1, is_full=False)
        set_states(scene, "shelf_produce", fill_level=0.8, is_full=False)
    elif typ == "office":
        for item in ("desk_open_office_1", "table_meeting_room", "counter_pantry", "desk_manager_office"):
            set_states(scene, item, is_dirty=False)
        set_states(scene, "cup_pantry", is_dirty=False, is_wet=False)
    elif typ == "factory":
        for item in ("table_workshop", "table_break_room", "machine_assembly_line"):
            set_states(scene, item, is_dirty=False)
        set_states(scene, "cabinet_entrance", is_open=False)
        set_states(scene, "shelf_warehouse", fill_level=0.7)


def apply_profile(scene: dict[str, Any], profile: str) -> None:
    typ = scene_type(str(scene.get("scene_name") or ""))
    if typ == "home":
        ensure_home_support_nodes(scene)
    normalize_room_parents(scene)
    set_room_connections(scene, ROOM_CONNECTIONS[typ][profile])
    if profile == "compact_cleaning":
        apply_cleaning_profile(scene, typ)
    elif profile == "normal_logistics":
        apply_logistics_profile(scene, typ)
    elif profile == "spread_device":
        apply_device_profile(scene, typ)
    else:
        raise ValueError(f"unknown profile: {profile}")
    scene["variant_profile"] = profile
    scene["variant_axes"] = {"topology": profile.split("_", 1)[0], "object_task": profile.split("_", 1)[1]}
    rebuild_children_and_parent_edges(scene)


def collect_expected_event_refs(typ: str) -> set[str]:
    roles = {
        "home": ("resident_workday", "resident_weekend"),
        "hospital": ("patient", "doctor", "nurse"),
        "supermarket": ("customer", "cashier", "stocker"),
        "office": ("office_worker", "manager", "visitor"),
        "factory": ("factory_worker", "quality_inspector", "maintenance_worker"),
    }[typ]
    return {entry.activity for role in roles for entry in ROLE_SCHEDULES[role]}


def validate_scene(scene: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    ids = nodes_by_id(scene)
    node_ids = [str(item.get("id") or "") for item in scene.get("nodes") or []]
    if len(node_ids) != len(set(node_ids)):
        errors.append("duplicate node ids")
    for item in scene.get("nodes") or []:
        if {"parent", "child", "host_id", "floor_id", "runtime_relation"} & item.keys():
            errors.append(f"{item.get('id')} stores a relationship outside edges")
    for edge in scene.get("edges") or []:
        source = str(edge.get("source_id") or "")
        target = str(edge.get("target_id") or "")
        if source and source not in ids:
            errors.append(f"edge has missing source {source}")
        if target and target not in ids:
            errors.append(f"edge has missing target {target}")
    errors.extend(validate_room_connectivity(scene, ids))
    errors.extend(validate_event_refs(scene, ids))
    return sorted(set(errors))


def validate_room_connectivity(scene: dict[str, Any], ids: dict[str, dict[str, Any]]) -> list[str]:
    rooms = {node_id for node_id, item in ids.items() if str(item.get("node_type") or "") == "room"}
    graph = {room: set() for room in rooms}
    for edge in scene.get("edges") or []:
        if str(edge.get("relation") or "").lower() not in ROOM_CONNECTIVITY_RELATIONS:
            continue
        source = str(edge.get("source_id") or "")
        target = str(edge.get("target_id") or "")
        if source in rooms and target in rooms:
            graph[source].add(target)
            graph[target].add(source)
    if not rooms:
        return ["scene has no rooms"]
    start = "outside_home" if "outside_home" in rooms else sorted(rooms)[0]
    seen = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for nxt in graph[current]:
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    missing = sorted(rooms - seen)
    return [f"room connectivity misses {missing}"] if missing else []


def validate_event_refs(scene: dict[str, Any], ids: dict[str, dict[str, Any]]) -> list[str]:
    typ = scene_type(str(scene.get("scene_name") or ""))
    valid_virtual = {"human", "human_resident"}
    valid_virtual.update(spec["id"] for spec in get_default_npcs(typ))
    errors = []
    event_ids = collect_expected_event_refs(typ)
    from backend.generation.assets.npc_library import get_event_spec

    for event_id in sorted(event_ids):
        spec = get_event_spec(event_id)
        if not spec:
            errors.append(f"missing EventSpec {event_id}")
            continue
        refs = []
        for item in (*spec.preconditions, *spec.effects_on_success, *spec.effects_on_failure):
            refs.extend(
                str(value)
                for value in (
                    getattr(item, "target", ""),
                    getattr(item, "parent", ""),
                    getattr(item, "match_parent", ""),
                )
                if value
            )
            refs.extend(str(value) for value in (getattr(item, "parent_options", ()) or ()) if value)
        for ref in refs:
            if ref in valid_virtual:
                continue
            if ref and ref not in ids:
                errors.append(f"{event_id} references missing node {ref}")
    return errors


def build_variant(base_scene: str, profile: str) -> dict[str, Any]:
    source = SCENE_DIR / f"{base_scene}.json"
    scene = json.loads(source.read_text(encoding="utf-8"))
    scene = copy.deepcopy(scene)
    variant_id = f"{base_scene}__{profile}"
    scene["scene_name"] = variant_id
    if scene.get("scene_name_cn"):
        scene["scene_name_cn"] = f"{scene['scene_name_cn']} / {profile}"
    apply_profile(scene, profile)
    errors = validate_scene(scene)
    if errors:
        joined = "\n  - ".join(errors)
        raise RuntimeError(f"{variant_id} failed validation:\n  - {joined}")
    return scene


def write_variant(base_scene: str, profile: str, *, dry_run: bool = False) -> Path:
    scene = build_variant(base_scene, profile)
    target = SCENE_DIR / f"{scene['scene_name']}.json"
    if not dry_run:
        target.write_text(json.dumps(scene, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Build static scene graph difficulty variants.")
    parser.add_argument("--dry-run", action="store_true", help="Validate variants without writing JSON files.")
    args = parser.parse_args()
    outputs = []
    for base_scene in BASE_SCENES:
        for profile in PROFILES:
            outputs.append(write_variant(base_scene, profile, dry_run=args.dry_run))
    mode = "validated" if args.dry_run else "wrote"
    print(f"{mode} {len(outputs)} variants")
    for path in outputs:
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
