from __future__ import annotations

import copy
from typing import Any

from backend.core.assets.npc_library import get_default_npcs
from backend.core.resources import scene_resource_pool_specs
from backend.runtime.scene_utils import node, scene_type


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
        for key, value in item.items():
            if key in {"child", "resource_pool"}:
                continue
            existing[key] = value
        if isinstance(item.get("resource_pool"), dict):
            current_pool = existing.setdefault("resource_pool", {})
            for key, value in item["resource_pool"].items():
                if key in {"available_count", "dispensed_count", "consumed_count"} and key in current_pool:
                    continue
                current_pool[key] = copy.deepcopy(value)
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
    scene["world_state"].setdefault("room_humidity", {})
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
        support_nodes.extend(
            [
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
            ]
        )
    support_nodes.extend(scene_resource_pool_specs(scene_type(scene), scene))
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
