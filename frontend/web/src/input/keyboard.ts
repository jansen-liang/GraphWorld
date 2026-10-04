export type Hand = "left" | "right";
export type MovementKey = "KeyW" | "KeyA" | "KeyS" | "KeyD";

export function handForKey(code: string): Hand | null {
  return code === "KeyQ" ? "left" : code === "KeyE" ? "right" : null;
}

export function isMovementKey(code: string): code is MovementKey {
  return ["KeyW", "KeyA", "KeyS", "KeyD"].includes(code);
}

export function movementAxes(keys: ReadonlySet<string>): [number, number] {
  return [Number(keys.has("KeyD")) - Number(keys.has("KeyA")), Number(keys.has("KeyW")) - Number(keys.has("KeyS"))];
}
