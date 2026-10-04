import * as THREE from "three";

/** Return the nearest collision distance, excluding the object being inspected. */
export function nearestBlockerDistance(
  ray: THREE.Ray,
  collisionMeshes: readonly THREE.Mesh[],
  ignored?: THREE.Object3D,
): number | undefined {
  const raycaster = new THREE.Raycaster(ray.origin, ray.direction);
  const hit = raycaster.intersectObjects(collisionMeshes as THREE.Mesh[], false)
    .find((candidate) => candidate.object !== ignored);
  return hit?.distance;
}

export function isOccluded(
  camera: THREE.Vector3,
  target: THREE.Vector3,
  collisionMeshes: readonly THREE.Mesh[],
  ignored?: THREE.Object3D,
  padding = 0.04,
): boolean {
  const direction = target.clone().sub(camera);
  const distance = direction.length();
  if (distance <= 1e-6) return false;
  const blockerDistance = nearestBlockerDistance(
    new THREE.Ray(camera, direction.normalize()),
    collisionMeshes,
    ignored,
  );
  return blockerDistance != null && blockerDistance < distance - padding;
}

/** Lightweight XZ capsule prediction for first-person movement. */
export function canMoveCapsule(
  position: THREE.Vector3,
  delta: THREE.Vector3,
  radius: number,
  blockers: readonly THREE.Mesh[],
  height = 1.7,
): boolean {
  const capsuleRadius = Math.max(0.05, radius);
  const distance = Math.hypot(delta.x, delta.z);
  const sampleSpacing = Math.max(0.025, capsuleRadius * 0.4);
  const sampleCount = Math.max(1, Math.ceil(distance / sampleSpacing));
  const capsuleBottom = position.y - Math.max(0, height - 0.1);
  const capsuleTop = position.y + 0.05;
  for (const mesh of blockers) {
    if (!mesh.visible || mesh.userData.collisionEnabled === false) continue;
    const bounds = new THREE.Box3().setFromObject(mesh);
    if (capsuleTop <= bounds.min.y || capsuleBottom >= bounds.max.y) continue;
    for (let index = 0; index <= sampleCount; index += 1) {
      const fraction = index / sampleCount;
      const x = position.x + delta.x * fraction;
      const z = position.z + delta.z * fraction;
      const nearestX = THREE.MathUtils.clamp(x, bounds.min.x, bounds.max.x);
      const nearestZ = THREE.MathUtils.clamp(z, bounds.min.z, bounds.max.z);
      const dx = x - nearestX;
      const dz = z - nearestZ;
      if (dx * dx + dz * dz < capsuleRadius * capsuleRadius) return false;
    }
  }
  return true;
}
