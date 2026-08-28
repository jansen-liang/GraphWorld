from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.assets.object_library import build_object_node
from backend.core.nodes import Robot, Room
from backend.runtime.engine import Orchestrator


def make_world(*nodes: dict[str, Any], world_state: dict[str, Any] | None = None, edges: list[dict[str, Any]] | None = None) -> Orchestrator:
    return Orchestrator(
        {
            "scene_name": "timed_system_validation",
            "nodes": [Room("room").to_dict(), Robot("robot_01", parent="room").to_dict(), *nodes],
            "edges": edges or [],
            "world_state": world_state or {},
        }
    )


def act(runtime: Orchestrator, action: str, *, target: str = "", object_id: str = "") -> None:
    payload = {"action": action, "agent": "robot_01"}
    if target:
        payload["target"] = target
    if object_id:
        payload["object"] = object_id
    result = runtime.step([payload])["robot_actions"][0]
    assert result["ok"], result


def validate_refills() -> None:
    cases = (
        ("tissuebox", "tissue_refill", "count", 100),
        ("soapbottle", "soap_refill", "amount", 10),
        ("spraybottle", "water_refill", "uses_left", 5),
        ("peppershaker", "pepper_refill", "uses_left", 10),
        ("saltshaker", "salt_refill", "uses_left", 10),
        ("toothpaste", "toothpaste_refill", "uses_left", 20),
    )
    for target_type, supply_type, key, capacity in cases:
        target = build_object_node("target", target_type, parent="room", overrides={"states": {key: 0}})
        supply = build_object_node("supply", supply_type, parent="room")
        runtime = make_world(target, supply)
        act(runtime, "pick", object_id="supply")
        act(runtime, "refill", target="target", object_id="supply")
        assert runtime.graph.node("target")["states"][key] == capacity
        assert not runtime.graph.node("supply")


def validate_printer() -> None:
    printer = build_object_node("printer", "printer", parent="room", overrides={"states": {"count": 1, "amount": 1}})
    runtime = make_world(printer)
    act(runtime, "press", target="printer")
    runtime.step([])
    runtime.step([])
    assert runtime.graph.node("printer")["states"]["is_running"] is False
    assert len([node_id for node_id in runtime.graph.nodes if node_id.startswith("receipt_")]) == 1
    assert runtime.graph.world_state["processes"] == []


def validate_coffee() -> None:
    machine = build_object_node("machine", "coffeemachine", parent="room", overrides={"states": {"has_water": True}})
    cup = build_object_node("cup", "cup", parent="machine")
    beans = build_object_node("beans", "coffee_beans", parent="machine")
    runtime = make_world(machine, cup, beans)
    act(runtime, "press", target="machine")
    runtime.step([])
    runtime.step([])
    coffees = [node for node in runtime.graph.nodes.values() if node.get("semantic_type") == "coffee"]
    assert len(coffees) == 1 and coffees[0]["parent"] == "cup"
    assert not runtime.graph.node("beans")


def validate_drying() -> None:
    for weather, expected in (("sunny", 6), ("cloudy", 8), ("rainy", 12)):
        rack = build_object_node("rack", "rack", parent="room", overrides={"semantic_type": "drying_rack"})
        cloth = build_object_node("cloth", "clothes", parent="room", overrides={"states": {"is_wet": True, "folded": False}})
        runtime = make_world(rack, cloth, world_state={"weather": weather})
        act(runtime, "pick", object_id="cloth")
        act(runtime, "place", target="rack", object_id="cloth")
        assert runtime.graph.node("cloth")["states"]["cycle_remaining"] == expected - 1
        for _ in range(expected):
            runtime.step([])
        assert runtime.graph.node("cloth")["states"]["is_wet"] is False

    dryer = build_object_node("dryer", "clothesdryer", parent="room")
    cloth = build_object_node("cloth", "clothes", parent="room", overrides={"states": {"is_wet": True, "folded": False}})
    runtime = make_world(dryer, cloth)
    act(runtime, "pick", object_id="cloth")
    act(runtime, "open", target="dryer")
    act(runtime, "place", target="dryer", object_id="cloth")
    act(runtime, "close", target="dryer")
    act(runtime, "press", target="dryer")
    for _ in range(4):
        runtime.step([])
    assert runtime.graph.node("dryer")["states"]["is_running"] is False
    assert runtime.graph.node("cloth")["states"]["is_wet"] is False


def validate_sink_and_vase() -> None:
    sink = build_object_node("sink", "sink", parent="room")
    faucet = build_object_node("faucet", "faucet", parent="sink")
    vase = build_object_node("vase", "vase", parent="room")
    edge = {"source_id": "faucet", "target_id": "sink", "relation": "controls", "edge_type": "control_edge", "properties": {}}
    runtime = make_world(sink, faucet, vase, edges=[edge])
    act(runtime, "open", target="faucet")
    assert runtime.graph.node("sink")["states"]["has_water"] is True
    act(runtime, "pick", object_id="vase")
    act(runtime, "place", target="sink", object_id="vase")
    assert runtime.graph.node("vase")["states"]["has_water"] is True
    act(runtime, "close", target="faucet")
    assert runtime.graph.node("sink")["states"]["has_water"] is False


def validate_air_conditioner() -> None:
    conditioner = build_object_node("ac", "air_conditioner", parent="room")
    remote = build_object_node("remote", "remote", parent="room")
    edge = {"source_id": "remote", "target_id": "ac", "relation": "controls", "edge_type": "control_edge", "properties": {}}
    runtime = make_world(conditioner, remote, world_state={"temperature": "comfortable"}, edges=[edge])
    act(runtime, "press", target="remote")
    assert runtime.graph.world_state["room_temperature"]["room"] == "cold"
    act(runtime, "press", target="remote")
    assert runtime.graph.world_state["room_temperature"]["room"] == "room"


def validate_natural_changes() -> None:
    table = build_object_node("table", "table", parent="room", overrides={"states": {"is_dirty": False}})
    cold_cup = build_object_node("cold_cup", "cup", parent="room", overrides={"states": {"temperature": "cold"}})
    runtime = make_world(table, cold_cup, world_state={"natural_dirt_steps": 3})
    for _ in range(3):
        runtime.step([])
    assert runtime.graph.node("table")["states"]["is_dirty"] is True
    assert runtime.graph.node("cold_cup")["states"]["temperature"] == "room"


def main() -> int:
    validate_refills()
    validate_printer()
    validate_coffee()
    validate_drying()
    validate_sink_and_vase()
    validate_air_conditioner()
    validate_natural_changes()
    print("timed system validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
