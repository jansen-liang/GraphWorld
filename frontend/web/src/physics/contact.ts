import type { InputEventPayload } from "../protocol/events";

export type ContactKind = "collision" | "support" | "drop" | "settle";

export interface PhysicsContact {
  kind: ContactKind;
  actor_id?: string;
  node_id: string;
  other_id?: string;
  point?: [number, number, number];
  normal?: [number, number, number];
  velocity?: [number, number, number];
  impact_speed?: number;
}

/** Convert a local physics result into the shared backend input-event shape. */
export function physicsEvent(contact: PhysicsContact, sequence: number, sessionId = ""): InputEventPayload {
  return {
    event_id: `physics_${Date.now()}_${sequence}`,
    session_id: sessionId,
    actor_id: contact.actor_id,
    sequence,
    timestamp: performance.now() / 1000,
    event_type: "physics",
    phase: "completed",
    payload: contact as unknown as Record<string, unknown>,
  };
}
