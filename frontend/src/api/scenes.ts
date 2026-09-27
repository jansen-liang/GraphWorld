import { requestJson } from "./client";
import type { InteractionHit, SceneGraphResponse, SceneInteractionResponse, SceneLayoutValidation, SceneRead, SceneVersionRead } from "../types/api";

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

export function simulateSceneInteraction(
  sourceJson: Record<string, unknown>,
  request: { actorId: string; targetId: string; hand: "left" | "right"; hit: InteractionHit; input?: "interact_primary" | "move" },
) {
  return requestJson<SceneInteractionResponse>("/scene-simulation/interactions", {
    method: "POST",
    body: JSON.stringify({
      source_json: sourceJson,
      actor_id: request.actorId,
      input: request.input ?? "interact_primary",
      target_id: request.targetId,
      distance_m: request.hit.distance_m,
      hit: request.hit,
      hand: request.hand,
    }),
  });
}

export function tickSceneSimulation(sourceJson: Record<string, unknown>, elapsedSteps = 1) {
  return requestJson<SceneInteractionResponse>("/scene-simulation/ticks", {
    method: "POST",
    body: JSON.stringify({ source_json: sourceJson, elapsed_steps: elapsedSteps }),
  });
}
