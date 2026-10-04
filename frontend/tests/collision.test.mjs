import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { canMoveCapsule } from "../web/src/physics/collision.ts";

function box(position, size, { visible = true, collisionEnabled = true } = {}) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size), new THREE.MeshBasicMaterial());
  mesh.position.set(...position);
  mesh.visible = visible;
  mesh.userData.collisionEnabled = collisionEnabled;
  mesh.updateMatrixWorld(true);
  return mesh;
}

test("capsule movement passes through free space and collides with a wall", () => {
  const wall = box([1, 1, 0], [0.1, 2, 4]);
  const start = new THREE.Vector3(0, 1.6, 0);
  assert.equal(canMoveCapsule(start, new THREE.Vector3(0.2, 0, 0), 0.28, [wall]), true);
  assert.equal(canMoveCapsule(start, new THREE.Vector3(1.2, 0, 0), 0.28, [wall]), false);
});

test("capsule detects rounded corners and ignores vertically separated obstacles", () => {
  const corner = box([0.4, 1, 0.4], [0.2, 2, 0.2]);
  assert.equal(canMoveCapsule(new THREE.Vector3(0.12, 1.6, 0.12), new THREE.Vector3(0, 0, 0), 0.28, [corner]), false);
  const overhead = box([0, 2.2, 0], [2, 0.2, 2]);
  assert.equal(canMoveCapsule(new THREE.Vector3(0, 1.6, 0), new THREE.Vector3(0.2, 0, 0), 0.28, [overhead]), true);
});

test("opened or hidden door proxies no longer block movement", () => {
  const closedDoor = box([0.5, 1, 0], [0.1, 2, 1]);
  const start = new THREE.Vector3(0, 1.6, 0);
  const step = new THREE.Vector3(0.2, 0, 0);
  assert.equal(canMoveCapsule(start, step, 0.28, [closedDoor]), false);
  closedDoor.userData.collisionEnabled = false;
  assert.equal(canMoveCapsule(start, step, 0.28, [closedDoor]), true);
  closedDoor.userData.collisionEnabled = true;
  closedDoor.visible = false;
  assert.equal(canMoveCapsule(start, step, 0.28, [closedDoor]), true);
});
