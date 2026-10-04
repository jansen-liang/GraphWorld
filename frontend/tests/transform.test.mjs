import test from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import { applyProtocolToThree, applyProtocolWorldToThree, protocolToThreePosition, threeToProtocolPosition } from "../web/src/protocol/transform.ts";

test("protocol Z-up position maps to Three Y-up and back", () => {
  const target = new THREE.Object3D();
  applyProtocolToThree(target, { position: [1, 2, 3], rotation: [0, 0, 0, 1], scale: [1, 1, 1] });
  assert.deepEqual(target.position.toArray(), [1, 3, -2]);
  assert.deepEqual(threeToProtocolPosition(target.position), [1, 2, 3]);
  assert.deepEqual(protocolToThreePosition([1, 2, 3]).toArray(), [1, 3, -2]);
});

test("protocol identity rotation remains a valid basis-converted quaternion", () => {
  const target = new THREE.Object3D();
  applyProtocolToThree(target, { rotation: [0, 0, 0, 1] });
  assert.ok(Math.abs(target.quaternion.length() - 1) < 1e-9);
  assert.ok(target.quaternion.angleTo(new THREE.Quaternion()) < 1e-9);
});

test("malformed transforms are rejected", () => {
  assert.throws(() => applyProtocolToThree(new THREE.Object3D(), { position: [1, 2] }), /requires/);
});

test("world transform is converted into a mounted object's local transform", () => {
  const parent = new THREE.Group();
  parent.position.set(2, 0, 0);
  const child = new THREE.Object3D();
  parent.add(child);
  applyProtocolWorldToThree(child, { position: [2, 0, 0], rotation: [0, 0, 0, 1], scale: [1, 1, 1] });
  assert.ok(child.position.length() < 1e-9);
});
