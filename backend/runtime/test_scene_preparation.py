import json

from backend.app.runtime.graphworld_adapter import GraphWorldAdapter
from backend.runtime.scene_preparation import prepare_scene


def _home_scene() -> dict:
    with open("backend/data/sg_output/simple_graph/simple_home_1f.json", encoding="utf-8") as file:
        return json.load(file)


def test_home_preparation_adds_idempotent_refrigerated_food_pool():
    prepared = prepare_scene(_home_scene(), robot_count=1, human_count=0)
    prepared_again = prepare_scene(prepared, robot_count=1, human_count=0)
    pools = [node for node in prepared_again["nodes"] if node.get("id") == "food_pool_fridge_kitchen"]

    assert len(pools) == 1
    assert pools[0]["parent"] == "fridge_kitchen"
    assert pools[0]["resource_pool"]["available_count"] == 6
    assert pools[0]["resource_pool"]["instance"]["states"] == {"is_rotten": False, "is_cooked": False}
    assert prepared["world_state"]["room_humidity"] == {}


def test_home_preparation_materializes_catalog_resource_pools_only_for_existing_parents():
    prepared = prepare_scene(_home_scene(), robot_count=1, human_count=0)
    by_id = {str(node.get("id")): node for node in prepared["nodes"]}
    assert by_id["detergent_pool_washer_bathroom"]["parent"] == "washer_bathroom"
    assert by_id["detergent_pool_washer_bathroom"]["resource_pool"]["available_count"] == 3
    assert by_id["soap_pool_sink_bathroom"]["resource_pool"]["available_count"] == 4
    assert by_id["detergent_pool_dishwasher_kitchen"]["parent"] == "dishwasher_kitchen"
    assert by_id["detergent_pool_dishwasher_kitchen"]["resource_pool"]["available_count"] == 3

    scene_without_washer = _home_scene()
    scene_without_washer["nodes"] = [node for node in scene_without_washer["nodes"] if node.get("id") != "washer_bathroom"]
    prepared_without_washer = prepare_scene(scene_without_washer, robot_count=1, human_count=0)
    assert not any(node.get("id") == "detergent_pool_washer_bathroom" for node in prepared_without_washer["nodes"])


def test_office_preparation_materializes_printer_supply_pools():
    scene = {
        "scene_name": "simple_office_1f",
        "nodes": [
            {"id": "office", "node_type": "room", "semantic_type": "room", "states": {}},
            {"id": "printer_open_office", "node_type": "fixed_object", "semantic_type": "printer", "parent": "office", "states": {}},
        ],
        "edges": [],
    }
    prepared = prepare_scene(scene, robot_count=0, human_count=0)
    by_id = {str(node.get("id")): node for node in prepared["nodes"]}
    assert by_id["paper_pool_printer_open_office"]["resource_pool"]["available_count"] == 5
    assert by_id["ink_pool_printer_open_office"]["resource_pool"]["available_count"] == 2


def test_factory_preparation_materializes_assembly_component_pools():
    scene = {
        "scene_name": "simple_factory_1f",
        "nodes": [
            {"id": "factory", "node_type": "room", "semantic_type": "room", "states": {}},
            {"id": "assembly_line", "node_type": "fixed_object", "semantic_type": "assembly_line", "parent": "factory", "states": {}},
        ],
        "edges": [],
    }
    prepared = prepare_scene(scene, robot_count=0, human_count=0)
    by_id = {str(node.get("id")): node for node in prepared["nodes"]}
    assert by_id["component_a_pool_assembly_line"]["resource_pool"]["available_count"] == 4
    assert by_id["component_b_pool_assembly_line"]["resource_pool"]["available_count"] == 4


def test_repreparing_home_does_not_restore_consumed_resource_inventory():
    prepared = prepare_scene(_home_scene(), robot_count=1, human_count=0)
    pool = next(node for node in prepared["nodes"] if node.get("id") == "food_pool_fridge_kitchen")
    pool["resource_pool"]["available_count"] = 2
    pool["resource_pool"]["dispensed_count"] = 4
    pool["resource_pool"]["consumed_count"] = 1

    reprepared = prepare_scene(prepared, robot_count=1, human_count=0)
    pool_again = next(node for node in reprepared["nodes"] if node.get("id") == "food_pool_fridge_kitchen")

    assert pool_again["resource_pool"]["available_count"] == 2
    assert pool_again["resource_pool"]["dispensed_count"] == 4
    assert pool_again["resource_pool"]["consumed_count"] == 1


def test_prepared_food_pool_generates_dispense_candidate_when_fridge_is_accessible():
    prepared = prepare_scene(_home_scene(), robot_count=1, human_count=0)
    by_id = {str(node.get("id")): node for node in prepared["nodes"]}
    by_id["robot_01"]["parent"] = "kitchen"
    by_id["fridge_kitchen"]["states"]["is_open"] = True
    adapter = GraphWorldAdapter(prepared)
    orchestrator = adapter.orchestrator()

    candidates = adapter.candidate_payloads(orchestrator, visibility_mode="full")

    assert any(
        candidate["action"] == "dispense" and candidate["target"] == "food_pool_fridge_kitchen"
        for candidate in candidates
    )


def test_fog_of_war_distinguishes_unknown_stale_and_occluded_nodes():
    from backend.runtime.engine import Orchestrator

    scene = {
        "nodes": [
            {"id": "room_a", "node_type": "room", "semantic_type": "room", "states": {}},
            {"id": "room_b", "node_type": "room", "semantic_type": "room", "states": {}},
            {"id": "door_ab", "node_type": "fixed_object", "semantic_type": "door", "door_kind": "structural", "connected_rooms": ["room_a", "room_b"], "states": {"is_open": False}},
            {"id": "cabinet", "node_type": "fixed_object", "semantic_class": "container", "semantic_type": "cabinet", "parent": "room_a", "blocks_containment": True, "states": {"is_open": False}},
            {"id": "hidden_box", "node_type": "movable_object", "semantic_type": "box", "parent": "cabinet", "states": {}},
            {"id": "remote_box", "node_type": "movable_object", "semantic_type": "box", "parent": "room_b", "states": {}},
            {"id": "robot_01", "node_type": "robot", "semantic_type": "robot", "parent": "room_a", "states": {}},
        ],
        "edges": [{"source_id": "room_a", "target_id": "room_b", "relation": "connected"}],
    }
    orchestrator = Orchestrator(scene)
    first = orchestrator.perception.robot_view("robot_01")
    statuses = first["world_state"]["observation_status_by_node"]
    assert statuses["hidden_box"] == "occluded"
    assert statuses["remote_box"] == "unknown"
    assert "hidden_box" not in {item["id"] for item in first["nodes"]}

    orchestrator.graph.node("cabinet")["states"]["is_open"] = True
    second = orchestrator.perception.robot_view("robot_01")
    assert second["world_state"]["observation_status_by_node"]["hidden_box"] == "visible"
    orchestrator.graph.node("cabinet")["states"]["is_open"] = False
    orchestrator.environment.advance_time()
    third = orchestrator.perception.robot_view("robot_01")
    assert third["world_state"]["observation_status_by_node"]["hidden_box"] == "stale"
    assert third["world_state"]["last_seen_step_by_node"]["hidden_box"] == 0
