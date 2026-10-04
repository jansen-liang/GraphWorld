import test from "node:test";
import assert from "node:assert/strict";
import { applySimulationDelta } from "../web/src/protocol/delta.ts";

test("simulation delta applies joint state changes without replacing the snapshot", () => {
  const scene = {
    revision: 3,
    nodes: [{ id: "machine", joint_states: { door: 0 } }],
    edges: [],
  };
  const applied = applySimulationDelta(scene, {
    base_revision: 3,
    revision: 4,
    changes: [{
      change_type: "joint_state_changed",
      payload: { node_id: "machine", joint_id: "door", before: 0, after: 1.57 },
    }],
  }, 3);

  assert.equal(applied, true);
  assert.equal(scene.nodes[0].joint_states.door, 1.57);
  assert.equal(scene.revision, 4);
});

test("simulation delta preserves the protocol coordinate system", () => {
  const scene = { nodes: [], edges: [], revision: 1 };
  assert.equal(applySimulationDelta(scene, {
    base_revision: 1,
    revision: 2,
    coordinate_system: { units: "m", handedness: "right", up_axis: "z", rotation: "quaternion_xyzw" },
  }, 1), true);
  assert.equal(scene.coordinate_system.up_axis, "z");
});

test("legacy agent movement delta is converted to protocol Z-up coordinates", () => {
  const scene = { nodes: [{ id: "agent" }], edges: [] };
  assert.equal(applySimulationDelta(scene, {
    base_revision: 0,
    revision: 1,
    changes: [{
      change_type: "node_updated",
      payload: { node_id: "agent", agent_state: { position: { x: 2, y: 1.6, z: 3 } } },
    }],
  }, 0), true);
  assert.deepEqual(scene.nodes[0].world_transform.position, [2, -3, 1.6]);
});

test("simulation delta adds nodes created by a process", () => {
  const scene = { nodes: [{ id: "machine" }], edges: [], revision: 4 };
  assert.equal(applySimulationDelta(scene, {
    base_revision: 4,
    revision: 5,
    nodes_added: [{ id: "coffee_5", node_type: "object", states: { temperature: "hot" } }],
    changes: [{
      change_type: "node_added",
      payload: { id: "coffee_5", node_type: "object", states: { temperature: "hot" } },
    }],
  }, 4), true);
  assert.deepEqual(scene.nodes.map((node) => node.id), ["machine", "coffee_5"]);
});
