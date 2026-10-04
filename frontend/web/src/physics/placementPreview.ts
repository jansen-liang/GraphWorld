import * as THREE from "three";

export interface SurfacePlacement {
  position: THREE.Vector3;
  fits: boolean;
}

/** Snap a held object's footprint onto a horizontal support surface. */
export function surfacePlacementPosition(
  hit: THREE.Vector3,
  surface: THREE.Box3,
  itemSize: THREE.Vector3,
  gridSize: number,
  clearance = 0,
): SurfacePlacement {
  const grid = Math.max(0.001, gridSize);
  const width = surface.max.x - surface.min.x;
  const depth = surface.max.z - surface.min.z;
  const fits = itemSize.x <= width && itemSize.z <= depth;
  const maxX = Math.max(surface.min.x, surface.max.x - itemSize.x / 2);
  const maxZ = Math.max(surface.min.z, surface.max.z - itemSize.z / 2);
  const minX = Math.min(maxX, surface.min.x + itemSize.x / 2);
  const minZ = Math.min(maxZ, surface.min.z + itemSize.z / 2);
  const snap = (value: number) => Math.round(value / grid) * grid;
  return {
    position: new THREE.Vector3(
      THREE.MathUtils.clamp(snap(hit.x), minX, maxX),
      surface.max.y + itemSize.y / 2 + clearance,
      THREE.MathUtils.clamp(snap(hit.z), minZ, maxZ),
    ),
    fits,
  };
}
