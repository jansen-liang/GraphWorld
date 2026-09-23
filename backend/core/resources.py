"""Finite resource pools and independent item instances."""

from __future__ import annotations

import copy
from typing import Any


SCENE_RESOURCE_POOL_SPECS: dict[str, tuple[dict[str, Any], ...]] = {
    "home": (
        {
            "id": "food_pool_fridge_kitchen",
            "name": "refrigerated food supply",
            "name_cn": "冰箱食物库存",
            "parent": "fridge_kitchen",
            "semantic_type": "food_dispenser",
            "instance_prefix": "food",
            "count": 6,
            "instance": {"semantic_type": "food", "states": {"is_rotten": False, "is_cooked": False}},
        },
        {
            "id": "detergent_pool_washer_bathroom",
            "name": "laundry detergent supply",
            "name_cn": "洗衣液库存",
            "parent": "washer_bathroom",
            "semantic_type": "detergent_dispenser",
            "instance_prefix": "detergent",
            "count": 3,
            "instance": {"semantic_type": "detergent", "states": {"amount": 1.0}},
        },
        {
            "id": "soap_pool_sink_bathroom",
            "name": "hand soap supply",
            "name_cn": "洗手液库存",
            "parent": "sink_bathroom",
            "semantic_type": "soap_dispenser",
            "instance_prefix": "soap",
            "count": 4,
            "instance": {"semantic_type": "soapbottle", "states": {"amount": 1.0}},
        },
        {
            "id": "detergent_pool_dishwasher_kitchen",
            "name": "dishwasher detergent supply",
            "name_cn": "洗碗机清洁剂库存",
            "parent": "dishwasher_kitchen",
            "semantic_type": "detergent_dispenser",
            "instance_prefix": "dishwasher_detergent",
            "count": 3,
            "instance": {"semantic_type": "dishwasher_detergent", "states": {"amount": 1.0}},
        },
    ),
    "office": (
        {
            "id": "paper_pool_printer_open_office",
            "name": "printer paper supply",
            "name_cn": "打印纸库存",
            "parent": "printer_open_office",
            "semantic_type": "paper_dispenser",
            "instance_prefix": "paper_pack",
            "count": 5,
            "instance": {"semantic_type": "paper_pack", "states": {"count": 1}},
        },
        {
            "id": "ink_pool_printer_open_office",
            "name": "printer ink supply",
            "name_cn": "墨盒库存",
            "parent": "printer_open_office",
            "semantic_type": "ink_dispenser",
            "instance_prefix": "ink_cartridge",
            "count": 2,
            "instance": {"semantic_type": "ink_cartridge", "states": {"amount": 1}},
        },
    ),
    "factory": (
        {
            "id": "component_a_pool_assembly_line",
            "name": "component A supply",
            "name_cn": "组件 A 库存",
            "parent": "assembly_line",
            "semantic_type": "component_a_dispenser",
            "instance_prefix": "component_a",
            "count": 4,
            "instance": {"semantic_type": "component_a", "states": {}},
        },
        {
            "id": "component_b_pool_assembly_line",
            "name": "component B supply",
            "name_cn": "组件 B 库存",
            "parent": "assembly_line",
            "semantic_type": "component_b_dispenser",
            "instance_prefix": "component_b",
            "count": 4,
            "instance": {"semantic_type": "component_b", "states": {}},
        },
    ),
}


def scene_resource_pool_specs(scene_kind: str, scene: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return materialized finite-resource sources valid for a scene.

    Specs are filtered by parent existence so optional room layouts do not gain
    dangling pools.  Runtime counters are intentionally not shared between
    calls; ``prepare_scene.ensure_node`` owns persistence of those counters.
    """
    nodes = scene.get("nodes") if isinstance(scene, dict) else None
    node_ids = {str(item.get("id")) for item in nodes or () if isinstance(item, dict)}
    result: list[dict[str, Any]] = []
    for spec in SCENE_RESOURCE_POOL_SPECS.get(str(scene_kind or "").lower(), ()):
        if node_ids and str(spec.get("parent") or "") not in node_ids:
            continue
        item = {
            "id": spec["id"],
            "name": spec["name"],
            "name_cn": spec["name_cn"],
            "node_type": "fixed_object",
            "semantic_type": spec["semantic_type"],
            "states": {},
            "parent": spec["parent"],
            "child": [],
            "interactive_actions": ["dispense"],
            "resource_pool": {
                "available_count": int(spec["count"]),
                "consumed_count": 0,
                "instance_prefix": spec["instance_prefix"],
                "semantic_type": spec["instance"].get("semantic_type", "resource"),
                "instance": copy.deepcopy(spec["instance"]),
            },
        }
        result.append(item)
    return result


def resource_pool(item: dict[str, Any]) -> dict[str, Any]:
    pool = item.get("resource_pool")
    return pool if isinstance(pool, dict) else {}


def available_count(item: dict[str, Any]) -> int:
    pool = resource_pool(item)
    value = pool.get("available_count", pool.get("count", 0))
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def can_dispense(item: dict[str, Any]) -> bool:
    return bool(resource_pool(item)) and available_count(item) > 0


def dispense_resource(state: dict[str, Any], source_id: str, actor_id: str) -> str | None:
    """Create one independent resource instance and attach it to the actor."""
    source = state.get("nodes", {}).get(str(source_id)) or {}
    if not can_dispense(source):
        return None
    pool = resource_pool(source)
    pool["available_count"] = available_count(source) - 1
    serial = int(pool.get("dispensed_count", 0) or 0) + 1
    pool["dispensed_count"] = serial
    base_id = str(pool.get("instance_prefix") or source.get("semantic_type") or "resource")
    instance_id = f"{source_id}_{base_id}_{serial}"
    while instance_id in state.get("nodes", {}):
        serial += 1
        pool["dispensed_count"] = serial
        instance_id = f"{source_id}_{base_id}_{serial}"
    template = pool.get("instance") if isinstance(pool.get("instance"), dict) else {}
    instance = copy.deepcopy(template)
    instance.setdefault("semantic_type", str(pool.get("semantic_type") or source.get("semantic_type") or "resource"))
    instance.setdefault("name", str(pool.get("name") or instance["semantic_type"]))
    instance.setdefault("name_cn", str(pool.get("name_cn") or instance["name"]))
    instance.setdefault("node_type", "movable_object")
    instance.setdefault("states", {})
    instance.setdefault("interactive_actions", ["pick", "place"])
    instance["id"] = instance_id
    instance["resource_instance_of"] = str(source_id)
    instance["parent"] = str(actor_id)
    instance["runtime_relation"] = "held_by"
    state.setdefault("nodes", {})[instance_id] = instance
    state.setdefault("parent_of", {})[instance_id] = str(actor_id)
    state.setdefault("relation_of", {})[instance_id] = "held_by"
    state.setdefault("world_state", {}).setdefault("event_log", []).append({
        "type": "resource_dispensed",
        "source_id": str(source_id),
        "instance_id": instance_id,
        "actor_id": str(actor_id),
        "remaining": available_count(source),
    })
    if available_count(source) == 0:
        state.setdefault("world_state", {}).setdefault("event_log", []).append({
            "type": "resource_depleted",
            "source_id": str(source_id),
            "resource_semantic_type": str(pool.get("semantic_type") or source.get("semantic_type") or "resource"),
        })
    return instance_id


__all__ = ["SCENE_RESOURCE_POOL_SPECS", "available_count", "can_dispense", "dispense_resource", "resource_pool", "scene_resource_pool_specs"]
