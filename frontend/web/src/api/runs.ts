import { requestJson } from "./client";
import type { ReplayResponse, ReplayStepRead, RunCreate, RunCurrentResponse, RunMetricsResponse, RunRead } from "../types/api";

export function createRun(payload: RunCreate) {
  return requestJson<RunCurrentResponse>("/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getRun(runId: string) {
  return requestJson<RunRead>(`/runs/${runId}`);
}

export function listRuns() {
  return requestJson<RunRead[]>("/runs");
}

export function getRunCurrent(runId: string) {
  return requestJson<RunCurrentResponse>(`/runs/${runId}/current`);
}

export function applyAction(runId: string, actionId: string, payload: Record<string, unknown> = {}) {
  return requestJson<RunCurrentResponse>(`/runs/${runId}/actions`, {
    method: "POST",
    body: JSON.stringify({ action_id: actionId, payload }),
  });
}

export function advanceRun(runId: string) {
  return requestJson<RunCurrentResponse>(`/runs/${runId}/advance`, { method: "POST" });
}

export function cancelRun(runId: string) {
  return requestJson<RunRead>(`/runs/${runId}/cancel`, { method: "POST" });
}

export function listRunSteps(runId: string) {
  return requestJson<ReplayStepRead[]>(`/runs/${runId}/steps`);
}

export function getReplay(runId: string) {
  return requestJson<ReplayResponse>(`/runs/${runId}/replay`);
}

export function getMetrics(runId: string) {
  return requestJson<RunMetricsResponse>(`/runs/${runId}/metrics`);
}
