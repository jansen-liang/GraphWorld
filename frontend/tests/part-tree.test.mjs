import test from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import { applyRuntimeJointState, updateComposites } from "../web/src/features/scene-builder/compositeRuntime.ts";

test("runtime numeric joint state maps to normalized motion progress", () => {
  const joint = {
    id: "drawer",
    kind: "prismatic",
    mesh: new THREE.Group(),
    host: new THREE.Group(),
    localPosition: new THREE.Vector3(),
    baseQuaternion: new THREE.Quaternion(),
    axis: new THREE.Vector3(0, 0, 1),
    axisSpace: "local",
    travel: 0.4,
    progress: 0,
    open: false,
  };

  applyRuntimeJointState(joint, { position: 0.2 });
  assert.equal(joint.progressOverride, 0.5);
  assert.equal(joint.open, false);
});

test("runtime boolean joint state remains compatible with state cards", () => {
  const joint = {
    id: "door",
    kind: "hinge",
    mesh: new THREE.Group(),
    host: new THREE.Group(),
    localPosition: new THREE.Vector3(),
    baseQuaternion: new THREE.Quaternion(),
    axis: new THREE.Vector3(0, 1, 0),
    axisSpace: "local",
    travel: Math.PI / 2,
    progress: 0,
    open: false,
  };

  applyRuntimeJointState(joint, true);
  assert.equal(joint.progressOverride, undefined);
  assert.equal(joint.open, true);
});

test("structured runtime world transform becomes a joint animation target", () => {
  const joint = {
    id: "door",
    kind: "hinge",
    mesh: new THREE.Group(),
    host: new THREE.Group(),
    pivot: new THREE.Group(),
    localPosition: new THREE.Vector3(),
    baseQuaternion: new THREE.Quaternion(),
    axis: new THREE.Vector3(0, 1, 0),
    axisSpace: "local",
    travel: Math.PI / 2,
    progress: 0,
    open: false,
    runtimeTransform: { position: [1, 0, 0], rotation: [0, 0, 0, 1], scale: [1, 1, 1] },
  };
  const composite = { id: "machine", host: joint.host, parts: [], joints: [joint] };
  updateComposites([composite], 1);
  assert.equal(joint.pivot.position.x, 1);
});
