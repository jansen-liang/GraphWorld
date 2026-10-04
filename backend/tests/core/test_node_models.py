from backend.core.node import AGENT, FLOOR, OBJECT, ROOM, Node


def test_node_factory_selects_four_domain_classes():
    assert isinstance(Node.from_dict({"id": "floor", "node_type": "floor"}), FLOOR)
    assert isinstance(Node.from_dict({"id": "room", "node_type": "room"}), ROOM)
    assert isinstance(Node.from_dict({"id": "item", "node_type": "object"}), OBJECT)
    assert isinstance(Node.from_dict({"id": "agent", "node_type": "agent"}), AGENT)


def test_floor_geometry_uses_its_grid_definition():
    floor = FLOOR("floor", geometry={"dimensions_m": [4, 3], "grid_size_m": 0.5})
    assert floor.area == 12
    assert floor.size.dimensions == (4.0, 3.0)
    assert floor.shape.kind == "rectangle"
    assert floor.transform.position == (0.0, 0.0, 0.0)
    assert floor.contains_point((3.9, 2.9))
    assert not floor.contains_point((4.1, 2.9))
    assert floor.grid_to_world((3, 2)) == (1.5, 1.0)
    assert floor.world_to_grid((1.6, 1.2)) == (3, 2)
    assert floor.is_valid_cell((7, 5))
    assert not floor.is_valid_cell((8, 5))


def test_object_and_agent_expose_domain_capabilities():
    item = OBJECT("cup", semantic_type="cup", capabilities=("pickable",), geometry={"dimensions_cm": [10, 8, 12]})
    container = OBJECT("washer", attributes={"accepted_capabilities": ["shirt"], "volume_capacity_cm3": 500})
    agent = AGENT("player", attributes={"hand_count": 1, "reach_distance_m": 1.4})

    assert item.is_pickable()
    assert item.volume() == 960
    assert container.accepts_semantic_type("shirt")
    assert not container.accepts_semantic_type("cup")
    assert container.volume_capacity() == 500
    assert agent.hand_names() == ("left",)
    assert agent.can_hold_with(1)
    assert not agent.can_hold_with(2)
    assert agent.reach_distance_m() == 1.4


def test_object_exposes_asset_and_process_references_without_extra_subclasses():
    item = OBJECT(
        "washer",
        attributes={
            "editable_source": {"kind": "box"},
            "visual_reference": "washer.glb",
            "collision_reference": "washer_collision",
            "process_bindings": [{"process": "wash", "duration": 3}],
        },
    )
    assert item.editable_source == {"kind": "box"}
    assert item.visual_reference == "washer.glb"
    assert item.collision_reference == "washer_collision"
    assert item.process_bindings == ({"process": "wash", "duration": 3},)


def test_room_environment_is_read_from_state():
    room = ROOM("kitchen", states={"temperature_c": 21, "environment": {"humidity": 0.4}}, geometry={"dimensions_m": [4, 3, 2.6]})
    assert room.area == 12
    assert room.size.dimensions == (4.0, 3.0, 2.6)
    assert room.environment("temperature_c") == 21
    assert room.environment("humidity") == 0.4
    assert room.has_environment_state("humidity")


def test_agent_exposes_the_same_structure_tree_query_as_objects():
    agent = AGENT("agent")
    tree = agent.part_tree({
        "nodes": [
            {"id": "agent", "node_type": "agent", "role": "root"},
            {"id": "left_hand", "node_type": "object", "role": "component", "owner_id": "agent"},
        ],
        "edges": [{
            "source_id": "agent", "target_id": "left_hand", "relation": "structure",
            "properties": {"parent": "agent", "child": "left_hand", "joint_type": "fixed"},
        }],
    })
    assert tree.root_id == "agent"
    assert tree.children("agent") == ("left_hand",)
    assert tree.validate() == ()


def test_agent_exposes_embodiment_and_control_profile_metadata():
    agent = AGENT("agent", attributes={"embodiment": {"hands": 2}, "control_profile": {"mode": "human"}})
    assert agent.embodiment == {"hands": 2}
    assert agent.control_profile == {"mode": "human"}
