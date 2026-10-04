from __future__ import annotations

import pytest

from backend.core.articulation import part_tree_from_edges
from backend.core.action import Action
from backend.core.changes import JointState, WorldChange, WorldSnapshot
from backend.core.input_event import InputEvent, InteractEvent
from backend.core.node import Node
from backend.core.process import Process
from backend.core.rule import Rule
from backend.core.requirement import StateRequirement
from backend.core.effect import StateEffect
from backend.core.transform import Transform
from backend.core.state import BooleanState, ContinuousState, DiscreteStateValue, ResourceState, StateSet
from backend.core.edge import Edge, SpatialRelation, create_edge
from backend.runtime.scene_schema import validate_canonical_scene


def test_transform_normalizes_quaternion_and_uses_z_up_protocol() -> None:
    transform = Transform.from_dict({"position": [1, 2, 3], "rotation": [0, 0, 0, 2]})
    assert transform.position == (1.0, 2.0, 3.0)
    assert transform.rotation == (0.0, 0.0, 0.0, 1.0)


def test_part_tree_requires_single_parent_and_rejects_cycles() -> None:
    nodes = [
        {"id": "machine", "node_type": "object", "role": "root"},
        {"id": "door", "node_type": "object", "role": "component", "owner_id": "machine"},
        {"id": "hinge", "node_type": "object", "role": "component", "owner_id": "machine"},
    ]
    edges = [
        {"id": "j1", "relation": "structure", "properties": {"parent": "machine", "child": "door", "joint_type": "revolute"}},
        {"id": "j2", "relation": "structure", "properties": {"parent": "door", "child": "hinge", "joint_type": "fixed"}},
        {"id": "j3", "relation": "structure", "properties": {"parent": "hinge", "child": "door", "joint_type": "fixed"}},
    ]
    tree = part_tree_from_edges("machine", nodes, edges)
    assert any("multiple parents" in issue for issue in tree.validate())
    assert any("structure cycle" in issue for issue in tree.validate())


def test_part_tree_rejects_unknown_joint_type():
    tree = part_tree_from_edges(
        "machine",
        [{"id": "machine"}, {"id": "part", "owner_id": "machine"}],
        [{"relation": "structure", "properties": {"parent": "machine", "child": "part", "joint_type": "spring"}}],
    )
    assert any("unsupported joint type" in issue for issue in tree.validate())


def test_node_from_dict_preserves_role() -> None:
    node = Node.from_dict({"id": "drawer", "node_type": "object", "role": "component"})
    assert node.role == "component"


def test_world_change_rejects_unknown_type() -> None:
    with pytest.raises(ValueError):
        WorldChange("unknown")


def test_edge_can_reference_component_links_without_breaking_node_endpoints() -> None:
    edge = Edge.from_dict({
        "source_id": "clothes",
        "target_id": "washer",
        "source_link_id": "clothes.root",
        "target_link_id": "washer.drum",
        "relation": "in",
    })
    assert edge.target_link_id == "washer.drum"
    assert Edge.from_dict(edge.to_dict()).to_dict()["source_link_id"] == "clothes.root"
    structure = create_edge("machine", "door", SpatialRelation.STRUCTURE, target_link_id="door.panel", properties={"parent": "machine", "child": "door"})
    assert structure.is_structure
    assert structure.target_link_id == "door.panel"


def test_snapshot_and_joint_state_are_serializable_protocol_records() -> None:
    joint = JointState("door_joint", position=0.5, motion_status="moving")
    snapshot = WorldSnapshot("sim", "home", 2, 1.5, nodes=({"id": "door"},))
    assert joint.to_dict()["motion_status"] == "moving"
    assert snapshot.to_dict()["nodes"] == [{"id": "door"}]


def test_process_is_time_bounded_and_interruption_is_explicit() -> None:
    process = Process("wash-1", "washer", duration=10)
    assert not process.advance(4)
    assert process.status == "running"
    process.interrupt("user_stop")
    assert process.status == "interrupted"
    assert process.progress == 0.4


def test_input_event_has_explicit_phase_and_sequence() -> None:
    event = InputEvent.from_dict({
        "event_id": "evt-1",
        "session_id": "sim-1",
        "actor_id": "robot",
        "sequence": 3,
        "timestamp": 1.5,
        "event_type": "key",
        "phase": "pressed",
        "payload": {"code": "KeyQ"},
    })
    assert event.to_dict()["payload"]["code"] == "KeyQ"


def test_interact_event_and_action_keep_link_and_hit_fields_explicit() -> None:
    event = InteractEvent("agent", target_node_id="washer", target_link_id="drum", hit_point=(1.0, 2.0, 3.0))
    assert event.to_dict()["target_link_id"] == "drum"
    action = Action.from_dict({
        "action": "place", "agent": "agent", "target": "washer", "object": "shirt",
        "target_link_id": "drum", "hand": "right", "hit_point": [1, 2, 3],
    })
    assert action.to_dict()["target_link_id"] == "drum"
    assert action.hit_point == (1.0, 2.0, 3.0)


def test_state_cards_validate_and_report_local_changes() -> None:
    states = StateSet([
        BooleanState("is_open", False),
        ContinuousState("temperature", 20.0),
        DiscreteStateValue("mode", "low", ("off", "low", "high")),
        ResourceState("water", 2.0, capacity=5.0, unit="l"),
    ])
    change = states.set("is_open", True)
    assert change.to_dict() == {"state": "is_open", "before": False, "after": True}
    with pytest.raises(ValueError):
        states.set("mode", "invalid")
    with pytest.raises(ValueError):
        states.set("water", 6.0)


def test_rule_is_serializable_and_matches_without_mutating_context() -> None:
    class Context:
        def node(self, node_id):
            return {"states": {"is_open": False}}

    rule = Rule(
        "open-event", "state_changed",
        conditions=(StateRequirement("target", "is_open", False),),
        effects=(StateEffect("target", "is_open", True),),
    )
    assert rule.matches(Context(), {"target": "door"})
    assert rule.to_dict()["effects"][0]["type"] == "state"


def test_canonical_scene_validates_structure_edges_as_single_parent_asset_tree() -> None:
    scene = {
        "schema_version": 2,
        "id_namespace": "editor",
        "nodes": [
            {"id": "machine", "node_type": "object", "role": "root"},
            {"id": "door", "node_type": "object", "role": "component", "owner_id": "machine"},
        ],
        "edges": [{
            "id": "machine-door",
            "source_id": "machine",
            "target_id": "door",
            "relation": "structure",
            "properties": {"parent": "machine", "child": "door", "joint_type": "revolute"},
        }],
    }
    assert validate_canonical_scene(scene)["nodes"][1]["role"] == "component"


def test_canonical_scene_rejects_cross_asset_structure_edges_and_cycles() -> None:
    base = {
        "schema_version": 2,
        "id_namespace": "editor",
        "nodes": [
            {"id": "a", "node_type": "object", "role": "root"},
            {"id": "a1", "node_type": "object", "role": "component", "owner_id": "a"},
            {"id": "b", "node_type": "object", "role": "root"},
        ],
        "edges": [{
            "source_id": "a", "target_id": "a1", "relation": "structure",
            "properties": {"parent": "a", "child": "a1", "joint_type": "fixed"},
        }],
    }
    cross_asset = {**base, "edges": [{
        "source_id": "a", "target_id": "a1", "relation": "structure",
        "properties": {"parent": "b", "child": "a1", "joint_type": "fixed"},
    }]}
    with pytest.raises(ValueError, match="cross object assets"):
        validate_canonical_scene(cross_asset)
    cycle = {**base, "edges": [
        {"source_id": "a1", "target_id": "a2", "relation": "structure", "properties": {"parent": "a1", "child": "a2"}},
        {"source_id": "a2", "target_id": "a1", "relation": "structure", "properties": {"parent": "a2", "child": "a1"}},
    ], "nodes": [
        *base["nodes"],
        {"id": "a2", "node_type": "object", "role": "component", "owner_id": "a"},
    ]}
    with pytest.raises(ValueError, match="cycle"):
        validate_canonical_scene(cycle)
