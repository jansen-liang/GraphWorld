import * as THREE from "three";

export type SelectionVisuals = ReadonlyMap<string, THREE.Object3D>;

/** Selection is a local rendering concern and never changes backend state. */
export function updateSelectionVisibility(visuals: SelectionVisuals, selectedId: string): void {
  visuals.forEach((visual, id) => { visual.visible = id === selectedId; });
}
