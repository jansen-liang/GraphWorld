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
  const inverse = host.quaternion.clone().invert();
  return {
    mesh,
    host,
    localPosition: mesh.position.clone().sub(host.position).applyQuaternion(inverse),
    localQuaternion: inverse.multiply(mesh.quaternion.clone()),
  };
}

export function createComposite(id: string, host: THREE.Object3D): CompositeObject {
  return { id, host, parts: [], joints: [] };
}

export function attachPart(composite: CompositeObject, mesh: THREE.Object3D): CompositePart {
  const part = localPart(mesh, composite.host);
  composite.parts.push(part);
  return part;
}

export function attachHinge(composite: CompositeObject, id: string, panel: THREE.Object3D, pivot: THREE.Group, travel: number): CompositeJoint {
  const joint: CompositeJoint = {
    id,
    kind: "hinge",
    mesh: panel,
    host: composite.host,
    pivot,
    localPosition: pivot.position.clone().sub(composite.host.position).applyQuaternion(composite.host.quaternion.clone().invert()),
    baseQuaternion: pivot.quaternion.clone(),
    axis: new THREE.Vector3(0, 1, 0),
    travel,
    progress: 0,
    open: false,
  };
  composite.joints.push(joint);
  return joint;
}

export function attachPrismatic(composite: CompositeObject, id: string, mesh: THREE.Object3D, travel: number): CompositeJoint {
  const joint: CompositeJoint = {
    id,
    kind: "prismatic",
    mesh,
    host: composite.host,
    localPosition: mesh.position.clone().sub(composite.host.position).applyQuaternion(composite.host.quaternion.clone().invert()),
    baseQuaternion: mesh.quaternion.clone(),
    axis: new THREE.Vector3(0, 0, -1),
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
      part.mesh.position.copy(composite.host.position).add(part.localPosition.clone().applyQuaternion(composite.host.quaternion));
      part.mesh.quaternion.copy(composite.host.quaternion).multiply(part.localQuaternion);
    });
    composite.joints.forEach((joint) => {
      const target = joint.open ? 1 : 0;
      joint.progress += (target - joint.progress) * delta;
      if (Math.abs(target - joint.progress) < 0.001) joint.progress = target;
      const hostOffset = joint.localPosition.clone().applyQuaternion(composite.host.quaternion);
      if (joint.kind === "hinge" && joint.pivot) {
        joint.pivot.position.copy(composite.host.position).add(hostOffset);
        joint.pivot.quaternion.copy(composite.host.quaternion).multiply(joint.baseQuaternion);
        joint.pivot.rotateY(joint.travel * joint.progress);
      } else {
        joint.mesh.position.copy(composite.host.position).add(hostOffset);
        joint.mesh.quaternion.copy(composite.host.quaternion).multiply(joint.baseQuaternion);
        joint.mesh.position.add(joint.axis.clone().applyQuaternion(composite.host.quaternion).normalize().multiplyScalar(joint.travel * joint.progress));
      }
    });
  });
}
