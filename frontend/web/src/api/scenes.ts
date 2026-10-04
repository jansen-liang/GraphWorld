import { requestJson } from "./client";
import type { InteractionHit, SceneGraphResponse, SceneLayoutValidation, SceneRead, SceneVersionRead } from "../types/api";
import type { InputEventPayload } from "../protocol/events";

export interface SimulationSessionResponse {
  simulation_id: string;
  applied: boolean;
  action?: Record<string, unknown> | null;
  failures?: string[];
  delta?: Record<string, unknown>;
  snapshot: Record<string, unknown>;
}

export function startSceneSimulation(sourceJson: Record<string, unknown>, actorId = "") {
  return requestJson<SimulationSessionResponse>("/scene-simulation/start", { method: "POST", body: JSON.stringify({ source_json: sourceJson, actor_id: actorId }) });
}

export function dispatchSceneSimulation(simulationId: string, request: { input?: string; targetId?: string; direction?: [number, number]; elapsedSeconds?: number; hand?: "left" | "right"; hit?: InteractionHit; distanceM?: number; elapsedSteps?: number; event?: InputEventPayload }) {
  return requestJson<SimulationSessionResponse>("/scene-simulation/dispatch", {
    method: "POST",
    body: JSON.stringify({ simulation_id: simulationId, input: request.input ?? "interact_primary", target_id: request.targetId ?? "", direction: request.direction?.join(" ") ?? "", elapsed_seconds: request.elapsedSeconds ?? 0.1, hand: request.hand ?? "right", hit: request.hit ?? {}, distance_m: request.distanceM, elapsed_steps: request.elapsedSteps ?? 1, event: request.event }),
  });
}

export function stopSceneSimulation(simulationId: string) {
  return requestJson<void>(`/scene-simulation/${simulationId}`, { method: "DELETE" });
}

export interface ObjectCatalogEntry {
  semantic_type: string;
  name: string;
  name_cn: string;
  category: string;
  width_cm: number;
  depth_cm: number;
  height_cm: number;
  capabilities: string[];
  state_schema: Record<string, unknown>;
  default_states: Record<string, unknown>;
}

export function listObjectCatalog() {
  return requestJson<ObjectCatalogEntry[]>("/object-catalog");
}

export function listScenes() {
  return requestJson<SceneRead[]>("/scenes");
}

export function getScene(sceneId: string) {
  return requestJson<SceneRead>(`/scenes/${sceneId}`);
}

export function listSceneVersions(sceneId: string) {
  return requestJson<SceneVersionRead[]>(`/scenes/${sceneId}/versions`);
}

export function getSceneGraph(sceneVersionId: string) {
  return requestJson<SceneGraphResponse>(`/scene-versions/${sceneVersionId}/graph`);
}

export function validateSceneLayout(sceneVersionId: string, sourceJson: Record<string, unknown>) {
  return requestJson<SceneLayoutValidation>(`/scene-versions/${sceneVersionId}/layout/validate`, {
    method: "POST",
    body: JSON.stringify({ source_json: sourceJson }),
  });
}

export function publishSceneLayout(sceneVersionId: string, sourceJson: Record<string, unknown>) {
  return requestJson<SceneVersionRead>(`/scene-versions/${sceneVersionId}/layout/publish`, {
    method: "POST",
    body: JSON.stringify({
      source_json: sourceJson,
      description: "Saved from the scene builder.",
    }),
  });
}
