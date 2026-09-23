import * as THREE from "three";

export type JointKind = "hinge" | "prismatic";

export interface CompositePart {
  mesh: THREE.Object3D;
  host: THREE.Object3D;
  localPosition: THREE.Vector3;
  localQuaternion: THREE.Quaternion;
}

export interface CompositeJoint {
  id: string;
  kind: JointKind;
  mesh: THREE.Object3D;
  host: THREE.Object3D;
  pivot?: THREE.Group;
  localPosition: THREE.Vector3;
  baseQuaternion: THREE.Quaternion;
  axis: THREE.Vector3;
  axisSpace: "local" | "world";
  travel: number;
  progress: number;
  open: boolean;
}

export interface CompositeObject {
  id: string;
  host: THREE.Object3D;
  parts: CompositePart[];
  joints: CompositeJoint[];
}

function localPart(mesh: THREE.Object3D, host: THREE.Object3D): CompositePart {
  host.updateMatrixWorld(true);
  const worldPosition = mesh.getWorldPosition(new THREE.Vector3());
  const worldQuaternion = mesh.getWorldQuaternion(new THREE.Quaternion());
  const localPosition = host.worldToLocal(worldPosition);
  const localQuaternion = host.getWorldQuaternion(new THREE.Quaternion()).invert().multiply(worldQuaternion);
  host.add(mesh);
  mesh.position.copy(localPosition);
  mesh.quaternion.copy(localQuaternion);
  return { mesh, host, localPosition: localPosition.clone(), localQuaternion: localQuaternion.clone() };
}

export function createComposite(id: string, host: THREE.Object3D): CompositeObject {
  return { id, host, parts: [], joints: [] };
}

export function attachPart(composite: CompositeObject, mesh: THREE.Object3D): CompositePart {
  const part = localPart(mesh, composite.host);
  composite.parts.push(part);
  return part;
}

export function attachLocalPart(composite: CompositeObject, mesh: THREE.Object3D): CompositePart {
  const localPosition = mesh.position.clone();
  const localQuaternion = mesh.quaternion.clone();
  composite.host.add(mesh);
  mesh.position.copy(localPosition);
  mesh.quaternion.copy(localQuaternion);
  const part = { mesh, host: composite.host, localPosition, localQuaternion };
  composite.parts.push(part);
  return part;
}

export function attachHinge(composite: CompositeObject, id: string, panel: THREE.Object3D, pivot: THREE.Group, travel: number, axisSpace: "local" | "world" = "local"): CompositeJoint {
  composite.host.updateMatrixWorld(true);
  const pivotWorldPosition = pivot.getWorldPosition(new THREE.Vector3());
  const pivotWorldQuaternion = pivot.getWorldQuaternion(new THREE.Quaternion());
  const localPosition = composite.host.worldToLocal(pivotWorldPosition);
  const localQuaternion = composite.host.getWorldQuaternion(new THREE.Quaternion()).invert().multiply(pivotWorldQuaternion);
  const parent = pivot.parent;
  parent?.remove(pivot);
  composite.host.add(pivot);
  pivot.position.copy(localPosition);
  pivot.quaternion.copy(localQuaternion);
  const joint: CompositeJoint = {
    id,
    kind: "hinge",
    mesh: panel,
    host: composite.host,
    pivot,
    localPosition: localPosition.clone(),
    baseQuaternion: localQuaternion.clone(),
    axis: new THREE.Vector3(0, 1, 0),
    axisSpace,
    travel,
    progress: 0,
    open: false,
  };
  composite.joints.push(joint);
  return joint;
}

export function attachPrismatic(composite: CompositeObject, id: string, mesh: THREE.Object3D, travel: number): CompositeJoint {
  const part = localPart(mesh, composite.host);
  const joint: CompositeJoint = {
    id,
    kind: "prismatic",
    mesh,
    host: composite.host,
    localPosition: part.localPosition,
    baseQuaternion: part.localQuaternion,
    axis: new THREE.Vector3(0, 0, -1),
    axisSpace: "local",
    travel,
    progress: 0,
    open: false,
  };
  composite.joints.push(joint);
  return joint;
}

export function updateComposites(composites: CompositeObject[], delta = 0.18): void {
  composites.forEach((composite) => {
    composite.parts.forEach((part) => {
      part.mesh.position.copy(part.localPosition);
      part.mesh.quaternion.copy(part.localQuaternion);
    });
    composite.joints.forEach((joint) => {
      const target = joint.open ? 1 : 0;
      joint.progress += (target - joint.progress) * delta;
      if (Math.abs(target - joint.progress) < 0.001) joint.progress = target;
      if (joint.kind === "hinge" && joint.pivot) {
        joint.pivot.position.copy(joint.localPosition);
        const axis = joint.axisSpace === "world"
          ? joint.pivot.worldToLocal(new THREE.Vector3().copy(joint.axis).add(joint.pivot.getWorldPosition(new THREE.Vector3()))).normalize()
          : joint.axis;
        joint.pivot.quaternion.copy(joint.baseQuaternion).multiply(new THREE.Quaternion().setFromAxisAngle(axis, joint.travel * joint.progress));
      } else {
        joint.mesh.position.copy(joint.localPosition).add(joint.axis.clone().multiplyScalar(joint.travel * joint.progress));
        joint.mesh.quaternion.copy(joint.baseQuaternion);
      }
    });
  });
}
