import * as THREE from "three";

export interface ProtocolTransform {
  position?: [number, number, number] | number[];
  rotation?: [number, number, number, number] | number[];
  scale?: [number, number, number] | number[];
}

/**
 * Convert the engine-independent GraphWorld transform (right-handed Z-up)
 * into Three.js' native right-handed Y-up basis.
 *
 * This adapter is deliberately explicit. Core/runtime never receives Three.js
 * coordinates, and callers can keep legacy layout rendering separate until a
 * scene has been migrated to the protocol transform contract.
 */
export function protocolToThreeTransform(value: ProtocolTransform | null | undefined): THREE.Object3D {
  const transform = new THREE.Object3D();
  applyProtocolToThree(transform, value);
  return transform;
}

export function applyProtocolToThree(target: THREE.Object3D, value: ProtocolTransform | null | undefined): void {
  const position = value?.position ?? [0, 0, 0];
  const rotation = value?.rotation ?? [0, 0, 0, 1];
  const scale = value?.scale ?? [1, 1, 1];
  if (position.length !== 3 || rotation.length !== 4 || scale.length !== 3) {
    throw new Error("ProtocolTransform requires position[3], rotation[4], and scale[3]");
  }

  // Basis conversion is the proper rotation that maps protocol Z-up to
  // Three.js Y-up: protocol (x, y, z) becomes Three (x, z, -y).
  target.position.set(Number(position[0]), Number(position[2]), -Number(position[1]));
  target.scale.set(Number(scale[0]), Number(scale[2]), Number(scale[1]));

  const protocolQuaternion = new THREE.Quaternion(
    Number(rotation[0]), Number(rotation[1]), Number(rotation[2]), Number(rotation[3]),
  ).normalize();
  const basis = new THREE.Matrix4().makeRotationX(Math.PI / 2);
  const basisQuaternion = new THREE.Quaternion().setFromRotationMatrix(basis);
  target.quaternion.copy(basisQuaternion).multiply(protocolQuaternion).multiply(basisQuaternion.invert());
}

/** Apply a protocol-space world transform to an object already mounted below a parent. */
export function applyProtocolWorldToThree(target: THREE.Object3D, value: ProtocolTransform | null | undefined): void {
  const world = protocolToThreeTransform(value);
  const worldPosition = world.position.clone();
  const worldQuaternion = world.quaternion.clone();
  const worldScale = world.scale.clone();
  const parent = target.parent;
  if (!parent) {
    target.position.copy(worldPosition);
    target.quaternion.copy(worldQuaternion);
    target.scale.copy(worldScale);
    return;
  }
  parent.updateMatrixWorld(true);
  target.position.copy(parent.worldToLocal(worldPosition));
  target.quaternion.copy(parent.getWorldQuaternion(new THREE.Quaternion()).invert().multiply(worldQuaternion));
  const parentScale = parent.getWorldScale(new THREE.Vector3());
  target.scale.set(
    Math.abs(parentScale.x) > 1e-9 ? worldScale.x / parentScale.x : worldScale.x,
    Math.abs(parentScale.y) > 1e-9 ? worldScale.y / parentScale.y : worldScale.y,
    Math.abs(parentScale.z) > 1e-9 ? worldScale.z / parentScale.z : worldScale.z,
  );
}

export function threeToProtocolPosition(value: THREE.Vector3): [number, number, number] {
  return [value.x, -value.z, value.y];
}

export function protocolToThreePosition(value: readonly [number, number, number] | number[]): THREE.Vector3 {
  if (value.length !== 3) throw new Error("Protocol position requires three values");
  return new THREE.Vector3(Number(value[0]), Number(value[2]), -Number(value[1]));
}
