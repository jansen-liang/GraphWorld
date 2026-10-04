import * as THREE from "three";

export function normalizedPointer(event: Pick<PointerEvent, "clientX" | "clientY">, element: HTMLElement): THREE.Vector2 {
  const rect = element.getBoundingClientRect();
  return new THREE.Vector2(
    ((event.clientX - rect.left) / Math.max(1, rect.width)) * 2 - 1,
    -((event.clientY - rect.top) / Math.max(1, rect.height)) * 2 + 1,
  );
}

export function setRayFromPointer(
  raycaster: THREE.Raycaster,
  camera: THREE.Camera,
  pointer: THREE.Vector2,
): THREE.Raycaster {
  raycaster.setFromCamera(pointer, camera);
  return raycaster;
}
