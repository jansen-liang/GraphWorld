import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { surfacePlacementPosition } from "../web/src/physics/placementPreview.ts";

const surface = new THREE.Box3(new THREE.Vector3(0, 0.7, 0), new THREE.Vector3(1, 0.8, 0.6));

test("surface placement snaps the item center to the support grid", () => {
  const placement = surfacePlacementPosition(
    new THREE.Vector3(0.537, 0.8, 0.337), surface, new THREE.Vector3(0.2, 0.1, 0.2), 0.1,
  );
  assert.equal(placement.fits, true);
  assert.ok(Math.abs(placement.position.x - 0.5) < 1e-9);
  assert.ok(Math.abs(placement.position.y - 0.856) < 1e-9);
  assert.ok(Math.abs(placement.position.z - 0.3) < 1e-9);
});

test("surface placement clamps an edge hit so the footprint stays on the surface", () => {
  const placement = surfacePlacementPosition(
    new THREE.Vector3(0.99, 0.8, 0.59), surface, new THREE.Vector3(0.2, 0.1, 0.2), 0.1,
  );
  assert.ok(Math.abs(placement.position.x - 0.9) < 1e-9);
  assert.ok(Math.abs(placement.position.y - 0.856) < 1e-9);
  assert.ok(Math.abs(placement.position.z - 0.5) < 1e-9);
});

test("surface placement marks an oversized footprint invalid", () => {
  const placement = surfacePlacementPosition(
    new THREE.Vector3(0.5, 0.8, 0.3), surface, new THREE.Vector3(1.2, 0.1, 0.7), 0.1,
  );
  assert.equal(placement.fits, false);
});
