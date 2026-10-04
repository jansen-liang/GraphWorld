"""User-visible Home behavior contracts for the simplified world model."""

from backend.generation.assets.object_library import OBJECT_LIBRARY
from backend.generation.assets.object_library import materialize
from backend.runtime.input_adapter import resolve_interaction
from backend.runtime.action_executor import ActionExecutor
from backend.runtime.process_rules import advance_time
from backend.runtime.world import World
from backend.tests.core.scene_factory import scene_v2


def _home_graph(*objects: dict, edges: list[dict] | None = None) -> World:
    scene = {
        "nodes": [
            {"id": "room", "node_type": "room", "semantic_type": "room", "states": {}},
            {"id": "robot", "node_type": "agent", "parent": "room", "states": {}, "hand_count": 2},
            *objects,
        ],
        "edges": list(edges or []),
        "world_state": {},
    }
    materialize(scene)
    return World(scene_v2(scene))


def _act(graph: World, action: dict) -> None:
    result = ActionExecutor(graph).execute(action)
    assert result.ok, result.failures


def _interact(graph: World, target_id: str, *, hand: str = "right", input_name: str = "interact_primary") -> None:
    resolved = resolve_interaction(graph.state_for_rules(), {
        "actor_id": "robot", "target_id": target_id, "hand": hand, "input": input_name,
    })
    assert resolved.action is not None, resolved.failures
    _act(graph, resolved.action)


def _tick(graph: World, steps: int) -> None:
    ActionExecutor(graph).run(lambda state: advance_time(state, steps))


def test_laundry_closure_places_multiple_clothes_and_completes_cycle():
    washer = OBJECT_LIBRARY["washer"].instantiate("washer", host_id="room")
    first = OBJECT_LIBRARY["clothes"].instantiate(
        "shirt", host_id="robot", overrides={"states": {"is_dirty": True, "is_wet": False}}
    )
    second = OBJECT_LIBRARY["clothes"].instantiate(
        "pants", host_id="robot", overrides={"states": {"is_dirty": True, "is_wet": False}}
    )
    detergent = OBJECT_LIBRARY["laundry_detergent"].instantiate("detergent", host_id="washer")
    graph = _home_graph(washer, first, second, detergent)
    graph.move_node("shirt", "robot", "held_by")
    graph.move_node("pants", "robot", "held_by_left")

    _act(graph, {"agent": "robot", "action": "open", "target": "washer_door"})
    slot_id = "washer_slot_l1_c1"
    _act(graph, {"agent": "robot", "action": "place", "object": "shirt", "target": slot_id, "hand": "right"})
    _act(graph, {
        "agent": "robot", "action": "place", "object": "pants", "target": slot_id,
        "hand": "left", "volume_anchor": [0.7, 0.5, 0.5],
    })
    assert graph.parent_of["shirt"] == slot_id
    assert graph.parent_of["pants"] == slot_id

    _act(graph, {"agent": "robot", "action": "close", "target": "washer_door"})
    _act(graph, {"agent": "robot", "action": "press", "target": "washer"})
    assert graph.nodes["washer"]["states"]["is_running"] is True
    assert graph.nodes["washer"]["states"]["cycle_remaining"] == 3
    _tick(graph, 3)
    for item_id in ("shirt", "pants"):
        assert graph.nodes[item_id]["states"]["is_dirty"] is False
        assert graph.nodes[item_id]["states"]["is_wet"] is True


def test_light_interaction_toggles_on_and_off():
    graph = _home_graph(OBJECT_LIBRARY["room_light"].instantiate("light", host_id="room"))
    _interact(graph, "light")
    assert graph.nodes["light"]["states"]["is_on"] is True
    _interact(graph, "light")
    assert graph.nodes["light"]["states"]["is_on"] is False


def test_faucet_interaction_controls_sink_flow_and_water_level():
    graph = _home_graph(
        OBJECT_LIBRARY["faucet"].instantiate("faucet", host_id="room"),
        OBJECT_LIBRARY["sink"].instantiate("sink", host_id="room"),
        edges=[{"source_id": "faucet", "target_id": "sink", "relation": "controls"}],
    )
    _interact(graph, "faucet")
    assert graph.nodes["faucet"]["states"]["is_on"] is True
    assert graph.nodes["sink"]["states"]["water_flowing"] is True
    _tick(graph, 1)
    assert graph.nodes["sink"]["states"]["water_level"] > 0
    _interact(graph, "faucet")
    assert graph.nodes["sink"]["states"]["water_flowing"] is False


def test_left_and_right_pick_are_independent():
    graph = _home_graph(
        OBJECT_LIBRARY["clothes"].instantiate("shirt", host_id="room"),
        OBJECT_LIBRARY["towel"].instantiate("towel", host_id="room"),
    )
    _interact(graph, "shirt", hand="right", input_name="grab")
    _interact(graph, "towel", hand="left", input_name="grab")
    assert graph.parent_of["shirt"] == "robot"
    assert graph.relation_of["shirt"] == "held_by"
    assert graph.parent_of["towel"] == "robot"
    assert graph.relation_of["towel"] == "held_by_left"


def test_place_supports_rack_container_and_floor_release():
    rack = OBJECT_LIBRARY["rack"].instantiate("rack", host_id="room")
    cabinet = OBJECT_LIBRARY["cabinet"].instantiate("cabinet", host_id="room")
    graph = _home_graph(
        rack, cabinet,
        OBJECT_LIBRARY["shoes"].instantiate("first", host_id="robot"),
        OBJECT_LIBRARY["shoes"].instantiate("second", host_id="robot"),
        OBJECT_LIBRARY["shoes"].instantiate("third", host_id="robot"),
    )
    graph.move_node("first", "robot", "held_by")
    graph.move_node("second", "robot", "held_by_left")
    graph.move_node("third", "robot", "held_by_both")
    graph.nodes["cabinet"]["states"]["is_open"] = True

    _act(graph, {"agent": "robot", "action": "place", "object": "first", "target": "rack_slot_l1_c1"})
    _act(graph, {"agent": "robot", "action": "place", "object": "second", "target": "cabinet_slot_l1_c1", "hand": "left"})
    _act(graph, {"agent": "robot", "action": "release", "object": "third", "hand": "both"})
    assert graph.parent_of["first"] == "rack_slot_l1_c1"
    assert graph.parent_of["second"] == "cabinet_slot_l1_c1"
    assert graph.parent_of["third"] == "room"


def test_device_progress_starts_advances_and_can_be_stopped():
    graph = _home_graph(
        OBJECT_LIBRARY["washer"].instantiate("washer", host_id="room"),
        OBJECT_LIBRARY["laundry_detergent"].instantiate("detergent", host_id="washer"),
    )
    _act(graph, {"agent": "robot", "action": "press", "target": "washer_start_button"})
    assert graph.nodes["washer"]["states"]["cycle_remaining"] == 3
    _tick(graph, 1)
    assert graph.nodes["washer"]["states"]["cycle_remaining"] == 2
    _act(graph, {"agent": "robot", "action": "press", "target": "washer_start_button"})
    assert graph.nodes["washer"]["states"]["is_running"] is False
    assert graph.nodes["washer"]["states"]["cycle_remaining"] == 0
