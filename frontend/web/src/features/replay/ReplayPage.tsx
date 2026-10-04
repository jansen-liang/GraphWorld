import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Clock } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getReplay } from "../../api/runs";
import { SceneGraphCanvas } from "../scene-graph/SceneGraphCanvas";
import type { Observation, ReplayStepRead } from "../../types/api";

function asObservation(step: ReplayStepRead | undefined): Observation | null {
  const observation = step?.observation as Observation | undefined;
  if (!observation || !Array.isArray(observation.visible_nodes)) {
    return null;
  }
  return observation;
}

export function ReplayPage() {
  const { runId = "" } = useParams();
  const replay = useQuery({ queryKey: ["run-replay", runId], queryFn: () => getReplay(runId), enabled: Boolean(runId) });
  const [stepIndex, setStepIndex] = useState(0);
  const activeStep = replay.data?.steps[stepIndex];
  const observation = asObservation(activeStep);
  const maxStep = Math.max(0, (replay.data?.steps.length ?? 1) - 1);
  const eventCount = useMemo(() => activeStep?.events?.length ?? 0, [activeStep]);

  return (
    <section className="page full-height">
      <header className="page-header">
        <div>
          <p className="eyebrow">Replay</p>
          <h1>{runId}</h1>
        </div>
        <Link className="button" to={`/runs/${runId}`}>
          <ArrowLeft size={16} aria-hidden />
          Run
        </Link>
      </header>

      <div className="run-layout">
        <div className="graph-region">
          {observation ? (
            <SceneGraphCanvas nodes={observation.visible_nodes} edges={observation.visible_edges} memoryNodes={observation.memory_nodes} />
          ) : (
            <div className="empty-panel">No replay step selected.</div>
          )}
        </div>
        <aside className="inspector run-inspector">
          <div className="status-line">
            <Clock size={16} aria-hidden />
            <span>step {activeStep?.step_index ?? 0}</span>
          </div>
          <input
            className="timeline"
            type="range"
            min={0}
            max={maxStep}
            value={Math.min(stepIndex, maxStep)}
            onChange={(event) => setStepIndex(Number(event.target.value))}
          />
          <dl className="metric-grid">
            <div><dt>Actor</dt><dd>{activeStep?.actor_type ?? "-"}</dd></div>
            <div><dt>Events</dt><dd>{eventCount}</dd></div>
            <div><dt>Visible</dt><dd>{observation?.visible_nodes.length ?? 0}</dd></div>
            <div><dt>Actions</dt><dd>{activeStep?.candidate_actions.length ?? 0}</dd></div>
          </dl>
          <h2>Selected Action</h2>
          <div className="detail-block compact">
            <pre>{JSON.stringify(activeStep?.selected_action ?? {}, null, 2)}</pre>
          </div>
          <h2>Result</h2>
          <div className="detail-block compact">
            <pre>{JSON.stringify(activeStep?.action_result ?? {}, null, 2)}</pre>
          </div>
          <h2>Events</h2>
          <div className="detail-block compact">
            {activeStep?.events?.length ? (
              <pre>{JSON.stringify(activeStep.events, null, 2)}</pre>
            ) : (
              <span>No events at this step.</span>
            )}
          </div>
        </aside>
      </div>
    </section>
  );
}
