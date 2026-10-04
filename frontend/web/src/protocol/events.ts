export type InputPhase = "pressed" | "released" | "sampled" | "completed";
export type InputEventType = "key" | "pointer_interact" | "movement" | "physics";

export interface InputEventPayload {
  event_id: string;
  session_id?: string;
  actor_id?: string;
  sequence: number;
  timestamp: number;
  event_type: InputEventType;
  phase: InputPhase;
  payload: Record<string, unknown>;
}

export function inputEvent(eventType: InputEventType, phase: InputPhase, sequence: number, payload: Record<string, unknown> = {}, sessionId = "", actorId = ""): InputEventPayload {
  return { event_id: `web_${Date.now()}_${sequence}`, session_id: sessionId, actor_id: actorId, sequence, timestamp: performance.now() / 1000, event_type: eventType, phase, payload };
}
