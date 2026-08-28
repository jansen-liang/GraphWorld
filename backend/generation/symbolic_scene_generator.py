"""Deterministic symbolic scene-graph generator.

This is the first dataset-generation stage: topology and semantic placement
only. Geometry, rendering, and PDDL task validation are intentionally separate.
"""
from __future__ import annotations

import random
from typing import Any

from backend.core.assets.object_library import build_object_node
from backend.core.nodes import Floor, Human, Room
from backend.core.assets.room_library import room_types_for_scene


DOMAIN_PROFILES: dict[str, dict[str, Any]] = {
    "home": {
        "required": ["entrance", "living_room", "kitchen", "bathroom"],
        "optional": ["bedroom", "balcony"],
        "fixtures": {
            "entrance": ["room_light", "shoe_rack"],
            "living_room": ["room_light", "sofa", "table", "television"],
            "kitchen": ["room_light", "sink", "faucet", "refrigerator", "stove", "microwave"],
            "bathroom": ["room_light", "sink", "faucet", "toilet", "shower"],
            "bedroom": ["room_light", "bed", "wardrobe"],
            "balcony": ["room_light", "drying_rack"],
        },
        "movables": {"living_room": ["remote", "book", "plant"], "kitchen": ["plate", "bowl", "mug", "food"], "bedroom": ["clothes"], "balcony": ["clothes"]},
    },
    "office": {
        "required": ["entrance", "open_office", "meeting_room", "pantry", "restroom"],
        "optional": ["manager_office"],
        "fixtures": {r: ["door", "room_light"] for r in ("open_office", "meeting_room", "pantry", "restroom", "manager_office")},
        "movables": {"open_office": ["computer", "printer", "stationery"], "meeting_room": ["chair", "table"], "pantry": ["mug", "plate"]},
    },
    "hospital": {
        "required": ["entrance", "lobby", "waiting_area", "outpatient_clinic", "treatment_room", "pharmacy"],
        "optional": ["staff_room"],
        "fixtures": {r: ["door", "room_light"] for r in ("lobby", "waiting_area", "outpatient_clinic", "treatment_room", "pharmacy", "staff_room")},
        "movables": {"waiting_area": ["chair"], "treatment_room": ["bed", "medical_cart"], "pharmacy": ["medicine_box", "prescription_sheet"]},
    },
    "supermarket": {
        "required": ["entrance", "produce_area", "shelf_area", "checkout_area", "cold_storage"],
        "optional": ["warehouse"],
        "fixtures": {r: ["door", "room_light"] for r in ("entrance", "produce_area", "shelf_area", "checkout_area", "cold_storage", "warehouse")},
        "movables": {"produce_area": ["fruit", "vegetable"], "shelf_area": ["box", "cart"], "checkout_area": ["receipt"], "cold_storage": ["milk", "juice"]},
    },
    "factory": {
        "required": ["entrance", "warehouse", "assembly_line", "control_room", "workshop"],
        "optional": ["break_room", "receiving_dock"],
        "fixtures": {r: ["door", "room_light"] for r in ("warehouse", "assembly_line", "control_room", "workshop", "break_room", "receiving_dock")},
        "movables": {"warehouse": ["box", "cart"], "assembly_line": ["machine", "toolkit"], "workshop": ["box", "toolkit"]},
    },
}


def _edge(source: str, target: str, relation: str, *, edge_type: str = "object_edge", category: str = "physical") -> dict[str, Any]:
    return {"source_id": source, "target_id": target, "edge_type": edge_type, "relation": relation, "category": category, "properties": {}}


def generate_scene(domain: str, *, seed: int = 0, optional_rooms: int = 0, npc_count: int = 0) -> dict[str, Any]:
    domain = str(domain).lower()
    if domain not in DOMAIN_PROFILES:
        raise ValueError(f"unknown scene domain: {domain}")
    profile = DOMAIN_PROFILES[domain]
    allowed = set(room_types_for_scene(domain))
    rng = random.Random(seed)
    room_types = list(profile["required"])
    for room_type in profile.get("optional", ()):
        if room_type in allowed and len(room_types) < len(profile["required"]) + optional_rooms and rng.random() < 0.8:
            room_types.append(room_type)
    floor = Floor("floor_1", parent=None).to_dict()
    nodes: list[dict[str, Any]] = [floor]
    room_ids: list[str] = []
    for index, room_type in enumerate(room_types, 1):
        room_id = f"{room_type}_{index}"
        room_ids.append(room_id)
        nodes.append(Room(room_id, semantic_type=room_type, name=room_type, name_cn=room_type, parent="floor_1").to_dict())
    edges: list[dict[str, Any]] = []
    for room_id in room_ids:
        edges.append(_edge("floor_1", room_id, "belongs_to", edge_type="room_floor_edge"))
    for left, right in zip(room_ids, room_ids[1:]):
        edges.append(_edge(left, right, "connected", edge_type="room_edge", category="physical"))
        door_id = f"door_{left}_{right}"
        door = build_object_node(door_id, "door", parent=left)
        door["connected_rooms"] = [left, right]
        door["door_kind"] = "structural"
        door["blocks_navigation"] = True
        door["blocks_visibility"] = True
        nodes.append(door)
        edges.append(_edge(left, door_id, "contains"))
    counters: dict[str, int] = {}
    for room_id, room_type in zip(room_ids, room_types):
        for object_type in profile.get("fixtures", {}).get(room_type, []):
            if object_type == "door":
                # Structural doors are generated from room adjacency below.
                continue
            counters[object_type] = counters.get(object_type, 0) + 1
            object_id = f"{object_type}_{room_type}_{counters[object_type]}"
            item = build_object_node(object_id, object_type, parent=room_id)
            nodes.append(item)
            edges.append(_edge(room_id, object_id, "contains"))
        for object_type in profile.get("movables", {}).get(room_type, []):
            counters[object_type] = counters.get(object_type, 0) + 1
            object_id = f"{object_type}_{room_type}_{counters[object_type]}"
            item = build_object_node(object_id, object_type, parent=room_id)
            nodes.append(item)
            edges.append(_edge(room_id, object_id, "in"))
    for index in range(npc_count):
        room_id = room_ids[index % len(room_ids)]
        human = Human(f"human_{index + 1}", parent=room_id).to_dict()
        human["is_npc"] = True
        nodes.append(human)
        edges.append(_edge(room_id, human["id"], "at"))
    return {
        "scene_name": f"generated_{domain}_{seed}",
        "scene_domain": domain,
        "generator_version": "symbolic_scene_generator.v1",
        "seed": seed,
        "floorplan_template": f"{domain}_chain_v1",
        "nodes": nodes,
        "edges": edges,
        "generation": {"domain": domain, "room_types": room_types, "npc_count": npc_count},
    }


__all__ = ["DOMAIN_PROFILES", "generate_scene"]
