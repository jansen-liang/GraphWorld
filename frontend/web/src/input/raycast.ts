import * as THREE from "three";
import type { InteractionHit } from "../types/api";

export interface RaycastSelectionOptions {
  objectMeshes: ReadonlyMap<string, THREE.Mesh>;
}

/** Return the graph node id represented by a rendered object or its parent. */
export function objectIdForHit(object: THREE.Object3D, objectMeshes: ReadonlyMap<string, THREE.Mesh>): string {
  let current: THREE.Object3D | null = object;
  while (current) {
    const id = String(current.userData.id || "");
    if (id && objectMeshes.has(id)) return id;
    current = current.parent;
  }
  return "";
}

function text(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function isActionableComponent(object: THREE.Object3D): boolean {
  const role = text(object.userData.componentRole);
  return role === "sink_drain"
    || role === "faucet"
    || role === "storage_slot"
    || role === "door"
    || role.startsWith("drawer")
    || role.includes("button");
}

function hostIdForComponent(object: THREE.Object3D, objectMeshes: ReadonlyMap<string, THREE.Mesh>): string {
  // Components may be nested below a pivot/group. Walk up until the host id
  // is found instead of relying on the generated child mesh's own metadata.
  let current: THREE.Object3D | null = object;
  while (current) {
    const host = text(current.userData.hostId);
    if (host) return host;
    const id = text(current.userData.id);
    if (id && objectMeshes.has(id)) return id;
    current = current.parent;
  }
  return text(object.userData.id);
}

/** Pick an interaction target while preserving actionable component priority. */
export function chooseSimulationHit(
  hits: THREE.Intersection<THREE.Object3D>[],
  options: RaycastSelectionOptions,
): THREE.Intersection<THREE.Object3D> | undefined {
  // Prefer an explicitly pickable graph object over a nearer opaque host
  // shell. Contents such as clothes may be visually inside a cabinet; the
  // actionable object remains targetable when its mesh is in the ray.
  const pickableHit = hits.find((candidate) =>
    Boolean(candidate.object.userData.pickable) && objectIdForHit(candidate.object, options.objectMeshes),
  );
  const objectHit = pickableHit ?? hits.find((candidate) => objectIdForHit(candidate.object, options.objectMeshes));
  const componentHit = hits.find((candidate) => {
    if (!isActionableComponent(candidate.object)) return false;
    if (!objectHit) return true;
    const hostId = hostIdForComponent(candidate.object, options.objectMeshes);
    const objectId = text(objectHit.object.userData.id);
    // A door/drawer can be far from its host after opening. It remains the
    // canonical interaction target even when the transparent host box is
    // closer to the ray, so never use a distance cutoff for same-host parts.
    return hostId === objectId || candidate.distance <= objectHit.distance + 0.25;
  });
  return componentHit
    ?? objectHit
    ?? hits.find((candidate) => Boolean(candidate.object.userData.simulationSurface));
}

function volumeUvForHit(hit: THREE.Intersection<THREE.Object3D>): [number, number, number] | undefined {
  const mesh = hit.object as THREE.Mesh;
  if (!mesh.geometry || !("boundingBox" in mesh.geometry)) return undefined;
  if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox();
  const bounds = mesh.geometry.boundingBox;
  if (!bounds) return undefined;
  const localPoint = mesh.worldToLocal(hit.point.clone());
  return [
    THREE.MathUtils.clamp((localPoint.x - bounds.min.x) / Math.max(1e-6, bounds.max.x - bounds.min.x), 0, 1),
    THREE.MathUtils.clamp((localPoint.y - bounds.min.y) / Math.max(1e-6, bounds.max.y - bounds.min.y), 0, 1),
    THREE.MathUtils.clamp((localPoint.z - bounds.min.z) / Math.max(1e-6, bounds.max.z - bounds.min.z), 0, 1),
  ];
}

/** Convert a Three.js intersection into the backend InteractionHit wire shape. */
export function interactionHitFromIntersection(
  hit: THREE.Intersection<THREE.Object3D>,
  targetId: string,
  roomId: string | undefined,
  raycaster: THREE.Raycaster,
): InteractionHit {
  const normal = hit.face?.normal?.clone().transformDirection(hit.object.matrixWorld) ?? new THREE.Vector3(0, 1, 0);
  const volumeUv = volumeUvForHit(hit);
  return {
    node_id: targetId,
    ...(text(hit.object.userData.componentId) ? { link_id: text(hit.object.userData.componentId) } : {}),
    ...(roomId ? { room_id: roomId } : {}),
    ...(hit.uv ? { surface_uv: [hit.uv.x, hit.uv.y] as [number, number] } : {}),
    ...(volumeUv ? { volume_uv: volumeUv } : {}),
    point_cm: [hit.point.x * 100, hit.point.y * 100, hit.point.z * 100],
    normal: [normal.x, normal.y, normal.z],
    ray_origin: [raycaster.ray.origin.x, raycaster.ray.origin.y, raycaster.ray.origin.z],
    ray_direction: [raycaster.ray.direction.x, raycaster.ray.direction.y, raycaster.ray.direction.z],
    distance_m: hit.distance,
  };
}
