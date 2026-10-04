from backend.app.runtime.graphworld_adapter import GraphWorldAdapter as _GraphWorldAdapter, action_id
from backend.runtime.action_engine import apply_action_schema
from backend.runtime.world import World
from backend.tests.core.scene_factory import scene_v2


def GraphWorldAdapter(scene):
    return _GraphWorldAdapter(scene_v2(scene))


def _world(scene):
    return World(scene_v2(scene))


def _adapter() -> GraphWorldAdapter:
    return GraphWorldAdapter(
        {
            "scene_name": "elevator_candidates",
            "nodes": [
                {"id": "room_a", "node_type": "room", "semantic_type": "room", "states": {}},
                {"id": "room_b", "node_type": "room", "semantic_type": "room", "states": {}},
                {"id": "room_c", "node_type": "room", "semantic_type": "room", "states": {}},
                {
                    "id": "lift",
                    "node_type": "object",
                    "semantic_type": "elevator",
                    "parent": "room_a",
                    "interactive_actions": ["press"],
                    "served_rooms": ["room_a", "room_b", "room_c"],
                    "states": {"is_open": True, "is_running": False, "cycle_remaining": 0},
                },
                {
                    "id": "robot_01",
                    "node_type": "agent",
                    "semantic_type": "robot",
                    "parent": "lift",
                    "states": {},
                },
            ],
            "edges": [],
        }
    )


def test_elevator_candidates_keep_each_destination_and_round_trip_by_id():
    adapter = _adapter()
    orchestrator = adapter.orchestrator()
    candidates = adapter.candidate_payloads(orchestrator, visibility_mode="full")
    elevator_candidates = [
        item
        for item in candidates
        if item.get("action") == "press" and item.get("target") == "lift"
    ]

    assert {item.get("destination_room") for item in elevator_candidates} == {
        "room_a",
        "room_b",
        "room_c",
    }
    ids = {action_id(item) for item in elevator_candidates}
    assert len(ids) == 3
    for item in elevator_candidates:
        selected = adapter.candidate_by_id(
            orchestrator,
            visibility_mode="full",
            selected_action_id=action_id(item),
        )
        assert selected is not None
        assert selected["destination_room"] == item["destination_room"]
        assert item["action_contract"]["category"] == "manipulation"
    assert "target" in item["action_contract"]["parameters"]


def test_resource_pool_generates_dispense_candidate_and_creates_held_instance():
    adapter = GraphWorldAdapter(
        {
            "scene_name": "resource_candidates",
            "nodes": [
                {"id": "kitchen", "node_type": "room", "semantic_type": "room", "states": {}},
                {"id": "robot_01", "node_type": "agent", "semantic_type": "robot", "parent": "kitchen", "states": {}},
                {
                    "id": "snack_dispenser",
                    "node_type": "object",
                    "semantic_type": "dispenser",
                    "parent": "kitchen",
                    "interactive_actions": ["dispense"],
                    "resource_pool": {
                        "available_count": 2,
                        "instance_prefix": "snack",
                        "semantic_type": "snack",
                    },
                    "states": {},
                },
            ],
            "edges": [],
        }
    )
    orchestrator = adapter.orchestrator()
    candidates = adapter.candidate_payloads(orchestrator, visibility_mode="full")
    dispense = next(item for item in candidates if item["action"] == "dispense")
    assert dispense["target"] == "snack_dispenser"
    assert apply_action_schema(orchestrator.graph.state_for_rules(), dispense) == ()
    assert orchestrator.graph.node("snack_dispenser")["resource_pool"]["available_count"] == 1
    held = orchestrator.graph.held_by("robot_01")
    assert held.startswith("snack_dispenser_snack_")


def test_place_candidate_declares_surface_or_volume_geometry_hint():
    adapter = GraphWorldAdapter({
        "nodes": [
            {"id": "room", "node_type": "room", "semantic_type": "room", "states": {}},
            {"id": "robot_01", "node_type": "agent", "parent": "room", "states": {}},
            {"id": "table", "node_type": "object", "semantic_type": "table", "parent": "room", "interactive_actions": ["place"], "surface_size_cm": [100, 60], "states": {}},
            {"id": "slot", "node_type": "object", "semantic_type": "storage_slot", "parent": "room", "interactive_actions": ["place"], "interior_size_cm": [40, 30, 30], "states": {}},
            {"id": "cup", "node_type": "object", "semantic_type": "cup", "parent": "robot_01", "runtime_relation": "held_by", "states": {}},
        ],
        "edges": [],
    })
    orchestrator = adapter.orchestrator()
    candidates = [item for item in adapter.candidate_payloads(orchestrator, visibility_mode="full") if item.get("action") == "place"]
    hints = {item["target"]: item.get("placement_hint") for item in candidates}
    assert hints["table"] == "surface"
    assert hints["slot"] == "volume"
    table_candidate = next(item for item in candidates if item["target"] == "table")
    slot_candidate = next(item for item in candidates if item["target"] == "slot")
    assert table_candidate["surface_size_cm"] == [100, 60]
    assert slot_candidate["interior_size_cm"] == [40, 30, 30]


def test_laundry_goal_exposes_detergent_loading_phase_when_pool_is_available():
    from backend.runtime.agent.maintenance_goals import make_laundry_goal
    from backend.runtime.world import World

    scene = {"nodes": [
        {"id": "bathroom", "semantic_type": "room", "node_type": "room", "states": {}},
        {"id": "bedroom", "semantic_type": "room", "node_type": "room", "states": {}},
        {"id": "cloth", "semantic_type": "clothes", "parent": "room", "states": {"is_dirty": True}},
        {"id": "washer", "semantic_type": "washer", "parent": "bathroom", "states": {"is_open": True}},
        {"id": "detergent_pool", "semantic_type": "detergent_dispenser", "parent": "washer", "resource_pool": {"available_count": 2}},
        {"id": "drying_rack", "semantic_type": "drying_rack", "parent": "bathroom", "states": {}},
        {"id": "wardrobe", "semantic_type": "wardrobe", "parent": "bedroom", "states": {}},
    ]}
    goal = make_laundry_goal("cloth", 0, source="test", scene=_world(scene).to_scene())
    assert goal is not None
    assert goal["phase"] == "load_detergent"
    assert goal["detergent_pool"] == "detergent_pool"


def test_dishwasher_goal_requires_unloading_clean_dish_to_return_surface():
    from backend.runtime.agent.goal_lifecycle import active_goal_completed, refresh_active_goal_snapshot
    from backend.runtime.agent.maintenance_goals import make_dishwasher_goal

    scene = {"nodes": [
        {"id": "kitchen", "semantic_type": "room", "node_type": "room", "states": {}},
        {"id": "dishwasher", "semantic_type": "dishwasher", "parent": "kitchen", "states": {"is_running": False}},
        {"id": "plate", "semantic_type": "plate", "parent": "table", "states": {"is_dirty": True}},
        {"id": "table", "semantic_type": "table", "parent": "kitchen", "interactive_actions": ["place"], "surface_size_cm": [100, 60], "states": {}},
        {"id": "robot_01", "semantic_type": "robot", "parent": "kitchen", "states": {}},
    ]}
    graph = _world(scene)
    scene = graph.to_scene()
    baseline = _world(scene).to_scene()
    goal = make_dishwasher_goal("plate", 0, source="test", scene=scene, baseline=baseline)
    assert goal is not None and goal["phase"] == "load"
    graph.move_node("plate", "dishwasher", "in")
    graph.nodes["plate"]["states"]["is_dirty"] = False
    scene = graph.to_scene()
    refreshed = refresh_active_goal_snapshot(goal, scene, "robot_01")
    assert refreshed["phase"] == "unload"
    assert active_goal_completed(goal, scene) is False
    graph.move_node("plate", "table", "on")
    scene = graph.to_scene()
    assert active_goal_completed(goal, scene) is True


def test_heat_milk_goal_requires_unloading_hot_item_to_surface():
    from backend.runtime.agent.goal_lifecycle import active_goal_completed, refresh_active_goal_snapshot
    from backend.runtime.agent.maintenance_goals import make_heat_milk_goal

    scene = {"nodes": [
        {"id": "kitchen", "semantic_type": "room", "node_type": "room", "states": {}},
        {"id": "microwave", "semantic_type": "microwave", "parent": "kitchen", "states": {"is_running": False}},
        {"id": "milk", "semantic_type": "milk", "parent": "table", "states": {"temperature": "cold"}},
        {"id": "table", "semantic_type": "table", "parent": "kitchen", "interactive_actions": ["place"], "surface_size_cm": [100, 60], "states": {}},
        {"id": "robot_01", "semantic_type": "robot", "parent": "kitchen", "states": {}},
    ]}
    graph = _world(scene)
    scene = graph.to_scene()
    baseline = _world(scene).to_scene()
    goal = make_heat_milk_goal("milk", 0, source="test", scene=scene, baseline=baseline)
    assert goal is not None and goal["phase"] == "load"
    graph.move_node("milk", "microwave", "in")
    graph.nodes["milk"]["states"]["temperature"] = "hot"
    scene = graph.to_scene()
    refreshed = refresh_active_goal_snapshot(goal, scene, "robot_01")
    assert refreshed["phase"] == "unload"
    assert active_goal_completed(refreshed, scene) is False
    graph.move_node("milk", "table", "on")
    scene = graph.to_scene()
    assert active_goal_completed(refreshed, scene) is True


def test_cook_egg_goal_tracks_spawned_output_and_requires_serving():
    from backend.runtime.agent.goal_lifecycle import active_goal_completed, refresh_active_goal_snapshot
    from backend.runtime.agent.maintenance_goals import make_cook_egg_goal

    scene = {"nodes": [
        {"id": "kitchen", "semantic_type": "room", "node_type": "room", "states": {}},
        {"id": "stove", "semantic_type": "stove", "parent": "kitchen", "states": {"is_running": False}},
        {"id": "egg", "semantic_type": "egg", "parent": "table", "states": {}},
        {"id": "table", "semantic_type": "table", "parent": "kitchen", "interactive_actions": ["place"], "surface_size_cm": [100, 60], "states": {}},
        {"id": "robot_01", "semantic_type": "robot", "parent": "kitchen", "states": {}},
    ]}
    graph = _world(scene)
    scene = graph.to_scene()
    baseline = _world(scene).to_scene()
    goal = make_cook_egg_goal("egg", 0, source="test", scene=scene, baseline=baseline)
    assert goal is not None and goal["phase"] == "prepare"
    graph.move_node("egg", "stove", "in")
    graph.nodes["stove"]["states"]["is_running"] = True
    scene = graph.to_scene()
    refreshed = refresh_active_goal_snapshot(goal, scene, "robot_01")
    assert refreshed["phase"] == "waiting"
    graph.nodes["stove"]["states"]["is_running"] = False
    graph.nodes.pop("egg")
    graph.parent_of.pop("egg", None)
    graph.relation_of.pop("egg", None)
    graph.nodes["cooked_egg_3_5"] = {
        "id": "cooked_egg_3_5", "node_type": "object", "semantic_type": "cooked_egg",
        "produced_by_device": "stove", "produced_by_recipe": "stove", "produced_at_step": 3, "states": {"is_cooked": True},
    }
    graph.move_node("cooked_egg_3_5", "stove", "in")
    scene = graph.to_scene()
    refreshed = refresh_active_goal_snapshot(refreshed, scene, "robot_01")
    assert refreshed["phase"] == "serve"
    assert active_goal_completed(refreshed, scene) is False
    graph.move_node("cooked_egg_3_5", "table", "on")
    scene = graph.to_scene()
    assert active_goal_completed(refreshed, scene) is True


def test_craft_sandwich_goal_collects_inputs_and_serves_spawned_output():
    from backend.runtime.agent.goal_lifecycle import active_goal_completed, refresh_active_goal_snapshot
    from backend.runtime.agent.maintenance_goals import make_craft_sandwich_goal

    scene = {"nodes": [
        {"id": "kitchen", "semantic_type": "room", "node_type": "room", "states": {}},
        {"id": "bench", "semantic_type": "workbench", "parent": "kitchen", "states": {"is_running": False}},
        {"id": "bread", "semantic_type": "bread", "parent": "counter", "states": {}},
        {"id": "tomato", "semantic_type": "tomato", "parent": "counter", "states": {}},
        {"id": "counter", "semantic_type": "counter", "parent": "kitchen", "interactive_actions": ["place"], "surface_size_cm": [120, 60], "states": {}},
        {"id": "robot_01", "semantic_type": "robot", "parent": "kitchen", "states": {}},
    ]}
    graph = _world(scene)
    scene = graph.to_scene()
    goal = make_craft_sandwich_goal(0, source="test", scene=scene)
    assert goal is not None and goal["phase"] == "collect"
    graph.move_node("bread", "bench", "in")
    graph.move_node("tomato", "bench", "in")
    graph.nodes["bench"]["states"]["is_running"] = True
    scene = graph.to_scene()
    refreshed = refresh_active_goal_snapshot(goal, scene, "robot_01")
    assert refreshed["phase"] == "waiting"
    graph.nodes["bench"]["states"]["is_running"] = False
    graph.nodes["sandwich_4_7"] = {
        "id": "sandwich_4_7", "node_type": "object", "semantic_type": "sandwich",
        "produced_by_device": "bench", "produced_by_recipe": "workbench", "produced_at_step": 4, "states": {},
    }
    graph.move_node("sandwich_4_7", "bench", "in")
    scene = graph.to_scene()
    refreshed = refresh_active_goal_snapshot(refreshed, scene, "robot_01")
    assert refreshed["phase"] == "serve"
    graph.move_node("sandwich_4_7", "counter", "on")
    scene = graph.to_scene()
    assert active_goal_completed(refreshed, scene) is True


def test_assemble_product_goal_collects_components_and_inspects_output():
    from backend.runtime.agent.goal_lifecycle import active_goal_completed, refresh_active_goal_snapshot
    from backend.runtime.agent.maintenance_goals import make_assemble_product_goal

    scene = {"nodes": [
        {"id": "factory", "semantic_type": "room", "node_type": "room", "states": {}},
        {"id": "line", "semantic_type": "assembly_line", "parent": "factory", "states": {"is_running": False}},
        {"id": "component_a", "semantic_type": "component_a", "parent": "warehouse", "states": {}},
        {"id": "component_b", "semantic_type": "component_b", "parent": "warehouse", "states": {}},
        {"id": "warehouse", "semantic_type": "room", "node_type": "room", "states": {}},
        {"id": "inspection", "semantic_type": "inspection_surface", "parent": "factory", "interactive_actions": ["place"], "surface_size_cm": [120, 60], "states": {}},
        {"id": "robot_01", "semantic_type": "robot", "parent": "factory", "states": {}},
    ], "edges": [{"source_id": "warehouse", "target_id": "factory", "relation": "connected"}]}
    graph = _world(scene)
    scene = graph.to_scene()
    goal = make_assemble_product_goal(0, source="test", scene=scene)
    assert goal is not None and goal["phase"] == "collect"
    graph.move_node("component_a", "line", "in")
    graph.move_node("component_b", "line", "in")
    graph.nodes["line"]["states"]["is_running"] = True
    scene = graph.to_scene()
    refreshed = refresh_active_goal_snapshot(goal, scene, "robot_01")
    assert refreshed["phase"] == "waiting"
    graph.nodes["line"]["states"]["is_running"] = False
    graph.nodes["finished_product_4_8"] = {
        "id": "finished_product_4_8", "node_type": "object", "semantic_type": "finished_product",
        "produced_by_device": "line", "produced_by_recipe": "assembly_line", "produced_at_step": 4, "states": {},
    }
    graph.move_node("finished_product_4_8", "line", "in")
    scene = graph.to_scene()
    refreshed = refresh_active_goal_snapshot(refreshed, scene, "robot_01")
    assert refreshed["phase"] == "inspect"
    graph.move_node("finished_product_4_8", "inspection", "on")
    scene = graph.to_scene()
    assert active_goal_completed(refreshed, scene) is True


def test_brew_coffee_goal_keeps_output_inside_served_cup():
    from backend.runtime.agent.goal_lifecycle import active_goal_completed, refresh_active_goal_snapshot
    from backend.runtime.agent.maintenance_goals import make_brew_coffee_goal

    scene = {"nodes": [
        {"id": "kitchen", "semantic_type": "room", "node_type": "room", "states": {}},
        {"id": "machine", "semantic_type": "coffee_machine", "parent": "kitchen", "states": {"is_running": False, "water_level": 100}},
        {"id": "cup", "semantic_type": "cup", "parent": "table", "states": {}},
        {"id": "beans", "semantic_type": "coffee_beans", "parent": "table", "states": {}},
        {"id": "table", "semantic_type": "table", "parent": "kitchen", "interactive_actions": ["place"], "surface_size_cm": [100, 60], "states": {}},
        {"id": "robot_01", "semantic_type": "robot", "parent": "kitchen", "states": {}},
    ]}
    graph = _world(scene)
    scene = graph.to_scene()
    goal = make_brew_coffee_goal(0, source="test", scene=scene)
    assert goal is not None and goal["phase"] == "prepare"
    graph.move_node("cup", "machine", "in")
    graph.move_node("beans", "machine", "in")
    graph.nodes["machine"]["states"]["is_running"] = True
    scene = graph.to_scene()
    refreshed = refresh_active_goal_snapshot(goal, scene, "robot_01")
    assert refreshed["phase"] == "waiting"
    graph.nodes["machine"]["states"]["is_running"] = False
    graph.nodes["coffee_4_8"] = {
        "id": "coffee_4_8", "node_type": "object", "semantic_type": "coffee",
        "produced_by_device": "machine", "produced_by_recipe": "coffee_machine", "produced_at_step": 4, "states": {"temperature": "hot"},
    }
    graph.move_node("coffee_4_8", "cup", "in")
    scene = graph.to_scene()
    refreshed = refresh_active_goal_snapshot(refreshed, scene, "robot_01")
    assert refreshed["phase"] == "serve"
    graph.move_node("cup", "table", "on")
    scene = graph.to_scene()
    assert active_goal_completed(refreshed, scene) is True


def test_print_goal_uses_new_receipt_count_for_completion():
    from backend.runtime.agent.goal_lifecycle import active_goal_completed, refresh_active_goal_snapshot
    from backend.runtime.agent.maintenance_goals import make_print_goal

    scene = {"nodes": [
        {"id": "office", "semantic_type": "room", "node_type": "room", "states": {}},
        {"id": "printer", "semantic_type": "printer", "parent": "office", "states": {"count": 1, "amount": 1, "is_running": False}},
        {"id": "desk", "semantic_type": "desk", "parent": "office", "interactive_actions": ["place"], "surface_size_cm": [120, 60], "states": {}},
        {"id": "old_receipt", "semantic_type": "receipt", "parent": "printer", "states": {}},
    ]}
    graph = _world(scene)
    scene = graph.to_scene()
    goal = make_print_goal("printer", 0, source="test", scene=scene)
    assert goal is not None and goal["receipt_count_before"] == 1
    assert active_goal_completed(goal, scene) is False
    graph.nodes["new_receipt"] = {"id": "new_receipt", "node_type": "object", "semantic_type": "receipt", "states": {}}
    graph.move_node("new_receipt", "printer", "in")
    scene = graph.to_scene()
    refreshed = refresh_active_goal_snapshot(goal, scene, "robot_01")
    assert refreshed["phase"] == "collect"
    assert active_goal_completed(refreshed, scene) is False
    graph.nodes["robot_01"] = {"id": "robot_01", "node_type": "agent", "semantic_type": "robot", "states": {}}
    graph.move_node("new_receipt", "robot_01", "held_by")
    scene = graph.to_scene()
    refreshed = refresh_active_goal_snapshot(refreshed, scene, "robot_01")
    assert refreshed["phase"] == "place"
    graph.move_node("new_receipt", "desk", "on")
    scene = graph.to_scene()
    assert active_goal_completed(refreshed, scene) is True


def test_goal_checkpoint_identity_and_resume_preserve_phase():
    from backend.runtime.agent.goal_lifecycle import (
        effective_goal_priority,
        goal_checkpoint_id,
        preempt_goal,
        resume_goal,
        start_goal,
    )

    goal = start_goal({"task": "laundry_clothes", "skill": "laundry_clothes", "object": "shirt_01", "phase": "washing_wait"}, 4)
    assert goal["goal_id"] == goal_checkpoint_id(goal)
    assert goal["status"] == "active"
    paused = preempt_goal(goal, 9, "higher_priority_goal")
    assert paused["status"] == "paused"
    assert paused["preempt_reason"] == "higher_priority_goal"
    resumed = resume_goal(paused, 19)
    assert resumed["status"] == "active"
    assert resumed["goal_id"] == goal["goal_id"]
    assert resumed["resume_count"] == 1
    assert resumed["phase"] == "washing_wait"
    assert effective_goal_priority(paused, 109) > effective_goal_priority(goal, 109)
