from backend.core.action_schemas import apply_action_schema
from backend.core.composition import materialize_compositions
from backend.core.assets.object_library import OBJECT_LIBRARY
from backend.core.timed_transitions import advance_time


def _composite_state(host_type: str, item_type: str, *, item_states=None):
    host = OBJECT_LIBRARY[host_type].instantiate("host", parent="room")
    item = OBJECT_LIBRARY[item_type].instantiate("item", parent="robot", overrides={"states": item_states or {}})
    scene = {
        "nodes": [
            {"id": "room", "node_type": "room", "semantic_type": "room", "states": {}},
            {"id": "robot", "node_type": "robot", "parent": "room", "states": {}},
            host, item,
        ],
        "edges": [], "world_state": {},
    }
    materialize_compositions(scene)
    nodes = {str(node["id"]): node for node in scene["nodes"]}
    state = {
        "nodes": nodes,
        "parent_of": {node_id: str(node.get("parent") or "") for node_id, node in nodes.items() if node.get("parent")},
        "relation_of": {"robot": "at", "host": "in", "item": "held_by"},
        "room_of": {node_id: "room" for node_id in nodes},
        "control_edges": [edge for edge in scene["edges"] if edge.get("relation") == "controls"],
        "room_edges": [], "world_state": {},
    }
    return state, "host_slot_l1_c1"


def test_dirty_clothes_washing_closure_uses_relations_capabilities_and_time():
    washer = OBJECT_LIBRARY["washer"].instantiate("washer", parent="room")
    shirt = OBJECT_LIBRARY["clothes"].instantiate("shirt", parent="robot", overrides={"states": {"is_dirty": True, "is_wet": False}})
    detergent = OBJECT_LIBRARY["laundry_detergent"].instantiate("detergent", parent="washer")
    scene = {
        "nodes": [
            {"id": "room", "node_type": "room", "semantic_type": "room", "states": {}},
            {"id": "robot", "node_type": "robot", "parent": "room", "states": {}},
            washer, shirt, detergent,
        ],
        "edges": [],
        "world_state": {},
    }
    materialize_compositions(scene)
    nodes = {str(item["id"]): item for item in scene["nodes"]}
    slot_id = "washer_slot_l1_c1"
    assert slot_id in nodes
    state = {
        "nodes": nodes,
        "parent_of": {node_id: str(item.get("parent") or "") for node_id, item in nodes.items() if item.get("parent")},
        "relation_of": {"shirt": "held_by", "detergent": "in", slot_id: "in", "washer": "in", "robot": "at"},
        "room_of": {node_id: "room" for node_id in nodes},
        "control_edges": [], "room_edges": [], "world_state": {},
    }
    nodes["washer"]["states"]["is_open"] = False
    assert apply_action_schema(state, {"agent": "robot", "action": "open", "target": "washer_door"}) == ()
    assert apply_action_schema(state, {"agent": "robot", "action": "place", "object": "shirt", "target": slot_id}) == ()
    state["nodes"]["shirt"]["parent"] = slot_id
    state["parent_of"]["shirt"] = slot_id
    state["relation_of"]["shirt"] = "in"
    assert apply_action_schema(state, {"agent": "robot", "action": "close", "target": "washer_door"}) == ()
    assert apply_action_schema(state, {"agent": "robot", "action": "press", "target": "washer"}) == ()
    assert state["nodes"]["shirt"]["states"]["is_wet"] is True
    assert state["nodes"]["shirt"]["states"]["is_dirty"] is True
    advance_time(state, 3)
    assert state["nodes"]["shirt"]["states"]["is_dirty"] is False
    assert state["nodes"]["shirt"]["states"]["is_wet"] is True
    assert state["nodes"]["shirt"]["states"].get("cycle_remaining", 0) == 0


def test_running_device_door_is_locked_by_generic_parent_state():
    state = {
        "nodes": {
            "room": {"id": "room", "node_type": "room", "states": {}},
            "robot": {"id": "robot", "node_type": "robot", "parent": "room", "states": {}},
            "device": {"id": "device", "semantic_type": "microwave", "node_type": "fixed_object", "parent": "room", "states": {"is_running": True}},
            "door": {"id": "door", "semantic_type": "door", "node_type": "control_object", "parent": "device", "door_kind": "device", "interactive_actions": ["open", "close"], "states": {"is_open": False}},
        },
        "parent_of": {"robot": "room", "device": "room", "door": "device"},
        "relation_of": {}, "room_of": {"robot": "room", "device": "room", "door": "room"},
        "control_edges": [], "room_edges": [], "world_state": {},
    }
    assert apply_action_schema(state, {"agent": "robot", "action": "open", "target": "door"}) == ("device is running; door is locked: door",)


def test_refrigerator_internal_slot_requires_open_access_and_accepts_food():
    state, slot_id = _composite_state("refrigerator", "food")
    closed_failures = apply_action_schema(state, {"agent": "robot", "action": "place", "object": "item", "target": slot_id})
    assert any("container is closed" in failure for failure in closed_failures)
    assert apply_action_schema(state, {"agent": "robot", "action": "open", "target": "host_door"}) == ()
    assert apply_action_schema(state, {"agent": "robot", "action": "place", "object": "item", "target": slot_id}) == ()
    assert state["parent_of"]["item"] == slot_id
    assert state["relation_of"]["item"] == "in"


def test_microwave_rejects_non_cookable_and_completes_cookable_cycle():
    rejected, rejected_slot = _composite_state("microwave", "clothes")
    assert apply_action_schema(rejected, {"agent": "robot", "action": "open", "target": "host_door"}) == ()
    failures = apply_action_schema(rejected, {"agent": "robot", "action": "place", "object": "item", "target": rejected_slot})
    assert any("lacks required containment capability: cookable" in failure for failure in failures)

    state, slot_id = _composite_state("microwave", "food", item_states={"is_cooked": False, "temperature": "room"})
    assert apply_action_schema(state, {"agent": "robot", "action": "open", "target": "host_door"}) == ()
    assert apply_action_schema(state, {"agent": "robot", "action": "place", "object": "item", "target": slot_id}) == ()
    assert apply_action_schema(state, {"agent": "robot", "action": "close", "target": "host_door"}) == ()
    assert apply_action_schema(state, {"agent": "robot", "action": "press", "target": "host"}) == ()
    advance_time(state, 2)
    assert state["nodes"]["item"]["states"]["temperature"] == "hot"
    assert state["nodes"]["item"]["states"]["is_cooked"] is True


def test_drying_rack_slot_runs_declared_passive_drying_cycle():
    state, slot_id = _composite_state("drying_rack", "clothes", item_states={"is_wet": True})
    assert apply_action_schema(state, {"agent": "robot", "action": "place", "object": "item", "target": slot_id}) == ()
    advance_time(state, 6)
    assert state["nodes"]["item"]["states"]["is_wet"] is False
    assert state["world_state"]["event_log"][-1]["type"] == "drying_completed"
