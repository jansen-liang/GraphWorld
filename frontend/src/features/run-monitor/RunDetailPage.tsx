import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FastForward, PauseCircle, RotateCw, Square } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { advanceRun, applyAction, cancelRun, getMetrics, getRunCurrent, listRunSteps } from "../../api/runs";
import { CandidateActionPanel } from "../human-control/CandidateActionPanel";
import { MetricsPanel } from "../metrics/MetricsPanel";
import { SceneGraphCanvas } from "../scene-graph/SceneGraphCanvas";
import type { Observation } from "../../types/api";

function observationNodes(observation: Observation | null | undefined) {
  return observation?.visible_nodes ?? [];
}

function observationEdges(observation: Observation | null | undefined) {
  return observation?.visible_edges ?? [];
}

function isLiveStatus(status: string) {
  return status === "pending" || status === "running";
}

export function RunDetailPage() {
  const { runId = "" } = useParams();
  const queryClient = useQueryClient();
  const current = useQuery({
    queryKey: ["run-current", runId],
    queryFn: () => getRunCurrent(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) => {
      const status = query.state.data?.run.status ?? "";
      return isLiveStatus(status) ? 1800 : false;
    },
  });
  const steps = useQuery({
    queryKey: ["run-steps", runId],
    queryFn: () => listRunSteps(runId),
    enabled: Boolean(runId),
    refetchInterval: current.data && isLiveStatus(current.data.run.status) ? 2200 : false,
  });
  const metrics = useQuery({
    queryKey: ["run-metrics", runId],
    queryFn: () => getMetrics(runId),
    enabled: Boolean(runId),
  });

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["run-current", runId] });
    queryClient.invalidateQueries({ queryKey: ["run-steps", runId] });
    queryClient.invalidateQueries({ queryKey: ["run-metrics", runId] });
  }

  const actionMutation = useMutation({
    mutationFn: (action: { actionId: string; payload: Record<string, unknown> }) => applyAction(runId, action.actionId, action.payload),
    onSuccess: refresh,
  });
  const advanceMutation = useMutation({
    mutationFn: () => advanceRun(runId),
    onSuccess: refresh,
  });
  const cancelMutation = useMutation({
    mutationFn: () => cancelRun(runId),
    onSuccess: refresh,
  });

  const state = current.data;
  const observation = state?.observation ?? null;
  const isHuman = state?.run.control_mode === "human";
  const canAct = isHuman && state?.run.status === "waiting_for_human";
  const canAdvance = state && state.run.control_mode !== "human" && !["completed", "failed", "canceled"].includes(state.run.status);
  const latestStep = steps.data?.length ? steps.data[steps.data.length - 1] : undefined;
  const latestEvents = latestStep?.events ?? [];

  return (
    <section className="page full-height">
      <header className="page-header">
        <div>
          <p className="eyebrow">{state?.run.control_mode ?? "Run"} · {state?.run.visibility_mode ?? ""}</p>
          <h1>{runId}</h1>
        </div>
        <div className="header-actions">
          {canAdvance && (
            <button className="button" type="button" disabled={advanceMutation.isPending} onClick={() => advanceMutation.mutate()}>
              <FastForward size={16} aria-hidden />
              Advance
            </button>
          )}
          {state && !["completed", "failed", "canceled"].includes(state.run.status) && (
            <button className="button" type="button" disabled={cancelMutation.isPending} onClick={() => cancelMutation.mutate()}>
              <Square size={16} aria-hidden />
              Cancel
            </button>
          )}
          <Link className="button primary" to={`/runs/${runId}/replay`}>
            <RotateCw size={16} aria-hidden />
            Replay
          </Link>
        </div>
      </header>

      <div className="run-layout">
        <div className="graph-region">
          {current.isLoading ? (
            <div className="empty-panel">Loading run.</div>
          ) : (
            <SceneGraphCanvas
              nodes={observationNodes(observation)}
              edges={observationEdges(observation)}
              memoryNodes={observation?.memory_nodes ?? []}
            />
          )}
        </div>
        <aside className="inspector run-inspector">
          <div className="status-line">
            <span className={`status-pill ${state?.run.status ?? ""}`}>{state?.run.status ?? "loading"}</span>
            <span>step {state?.run.current_step ?? 0}</span>
          </div>
          <dl className="metric-grid">
            <div><dt>Visible</dt><dd>{observation?.visible_nodes.length ?? 0}</dd></div>
            <div><dt>Memory</dt><dd>{observation?.memory_nodes.length ?? 0}</dd></div>
            <div><dt>Actions</dt><dd>{state?.candidate_actions.length ?? 0}</dd></div>
            <div><dt>Steps</dt><dd>{steps.data?.length ?? 0}</dd></div>
          </dl>

          <h2>{isHuman ? "Human Actions" : "Run Control"}</h2>
          {isHuman ? (
            <CandidateActionPanel
              actions={state?.candidate_actions ?? []}
              disabled={!canAct || actionMutation.isPending}
              onSelect={(action, selectedPayload) => {
                const payload = selectedPayload ?? {};
                actionMutation.mutate({ actionId: action.action_id, payload });
              }}
            />
          ) : (
            <button className="wide-action" type="button" disabled={!canAdvance || advanceMutation.isPending} onClick={() => advanceMutation.mutate()}>
              <PauseCircle size={16} aria-hidden />
              Advance one step
            </button>
          )}

          <h2>Latest Result</h2>
          <div className={state?.latest_action_result?.ok === false ? "error-panel compact" : "detail-block compact"}>
            {state?.latest_action_result ? (
              <pre>{JSON.stringify(state.latest_action_result, null, 2)}</pre>
            ) : (
              <span>No action yet.</span>
            )}
          </div>

          <h2>Latest Events</h2>
          <div className="detail-block compact">
            {latestEvents.length ? (
              <pre>{JSON.stringify(latestEvents, null, 2)}</pre>
            ) : (
              <span>No events yet.</span>
            )}
          </div>

          <h2>Metrics</h2>
          <MetricsPanel metrics={metrics.data?.metrics ?? []} />
        </aside>
      </div>
    </section>
  );
}
