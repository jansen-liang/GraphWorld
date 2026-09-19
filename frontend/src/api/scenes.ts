import { requestJson } from "./client";
import type { SceneGraphResponse, SceneLayoutValidation, SceneRead, SceneVersionRead } from "../types/api";

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
      description: "Published from the 2D scene builder.",
    }),
  });
}
