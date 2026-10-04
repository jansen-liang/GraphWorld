from backend.generation.assets.object_library import OBJECT_LIBRARY
from backend.runtime.process_rules import advance_time


def _state(*items):
    nodes = {str(item["id"]): item for item in items}
    parent_of = {
        key: str(value.get("parent") or value.get("host_id"))
        for key, value in nodes.items()
        if value.get("parent") or value.get("host_id")
    }
    return {
        "nodes": nodes,
        "parent_of": parent_of,
        "relation_of": {},
        "room_of": {},
        "control_edges": [],
        "world_state": {},
    }


def test_process_and_support_profiles_are_runtime_data_not_semantic_switches():
    washer = OBJECT_LIBRARY["washer"].instantiate("machine", host_id="room")
    rack = OBJECT_LIBRARY["drying_rack"].instantiate("support", host_id="room")
    shirt = OBJECT_LIBRARY["clothes"].instantiate(
        "shirt", host_id="support", overrides={"states": {"is_wet": True, "is_dirty": True}}
    )
    state = _state(
        {"id": "room", "node_type": "room", "semantic_type": "room", "states": {}},
        washer,
        rack,
        shirt,
    )
    assert washer["process_duration_steps"] == 3
    assert rack["contained_process_duration_steps"] == 6
    advance_time(state, 6)
    assert state["nodes"]["shirt"]["states"]["is_wet"] is False


def test_perishable_progresses_from_fresh_to_spoiled_to_rotten():
    food = OBJECT_LIBRARY["food"].instantiate("food", host_id="room")
    state = _state(
        {"id": "room", "node_type": "room", "semantic_type": "room", "states": {}},
        food,
    )
    advance_time(state, 73)
    assert state["nodes"]["food"]["states"]["is_spoiled"] is True
    assert state["nodes"]["food"]["states"]["is_rotten"] is False
    advance_time(state, 71)
    assert state["nodes"]["food"]["states"]["is_rotten"] is True
    assert state["nodes"]["food"]["states"]["freshness"] == 0.0
