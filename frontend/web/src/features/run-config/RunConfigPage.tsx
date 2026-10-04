import { useMutation, useQuery } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../app/auth";
import { getSceneGraph, listScenes, listSceneVersions, startSceneSimulation } from "../../api/scenes";
import type { ControlMode } from "../../types/api";

export function RunConfigPage() {
  const navigate = useNavigate();
  const auth = useAuth();
  const [searchParams] = useSearchParams();
  const sceneVersionParam = searchParams.get("sceneVersionId") ?? "";
  const inferredSceneId = sceneVersionParam.split("__v")[0] || "simple_home_1f";
  const scenes = useQuery({ queryKey: ["scenes"], queryFn: listScenes });
  const [sceneId, setSceneId] = useState(inferredSceneId);
  const activeSceneId = sceneId || scenes.data?.[0]?.id || "";
  const versions = useQuery({
    queryKey: ["scene-versions", activeSceneId],
    queryFn: () => listSceneVersions(activeSceneId),
    enabled: Boolean(activeSceneId),
  });
  const [sceneVersionId, setSceneVersionId] = useState(sceneVersionParam);
  const activeVersionId = sceneVersionId || versions.data?.[0]?.id || "";
  const selectedGraph = useQuery({
    queryKey: ["scene-graph", activeVersionId],
    queryFn: () => getSceneGraph(activeVersionId),
    enabled: Boolean(activeVersionId),
  });
  const [controlMode, setControlMode] = useState<ControlMode>("human");
  const [maxSteps, setMaxSteps] = useState(20);
  const isUserMode = !auth.isAdmin;
  const selectedSummary = useMemo(
    () => versions.data?.find((version) => version.id === activeVersionId)?.graph_summary ?? {},
    [versions.data, activeVersionId],
  );

  const mutation = useMutation({
    mutationFn: async () => {
      const source = selectedGraph.data?.source_json;
      if (!source) throw new Error("Scene source is not ready");
      const actor = (source.nodes as Array<Record<string, unknown>> | undefined)?.find((node) => ["agent", "robot", "human"].includes(String(node.node_type ?? node.semantic_type ?? "").toLowerCase()));
      return startSceneSimulation(source, String(actor?.id ?? ""));
    },
    onSuccess: (session) => {
      sessionStorage.setItem("graphworld.simulation", JSON.stringify(session));
      navigate(`/scenes/${activeSceneId}/edit?version=${activeVersionId}&run=1`);
    },
  });

  useEffect(() => {
    if (!isUserMode) {
      return;
    }
    if (controlMode === "agent") {
      setControlMode("human");
    }
  }, [controlMode, isUserMode]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!activeVersionId) {
      return;
    }
    mutation.mutate();
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Run Configuration</p>
          <h1>New Run</h1>
        </div>
      </header>

      <form className="form-grid" onSubmit={submit}>
        <div className="mode-banner">
          <strong>{auth.isAdmin ? "Admin workspace" : "User workspace"}</strong>
          <span>Human control is available now. Agent control will be enabled later.</span>
        </div>
        <label>
          <span>Scene</span>
          <select
            value={activeSceneId}
            onChange={(event) => {
              setSceneId(event.target.value);
              setSceneVersionId("");
            }}
          >
            {scenes.data?.map((scene) => (
              <option key={scene.id} value={scene.id}>
                {scene.name || scene.id}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Scene Version</span>
          <select value={activeVersionId} onChange={(event) => setSceneVersionId(event.target.value)}>
            {versions.data?.map((version) => (
              <option key={version.id} value={version.id}>
                v{version.version} · {version.id}
              </option>
            ))}
          </select>
        </label>
        <fieldset className="form-section">
          <legend>Control Mode</legend>
          <div className="option-group">
            {(["human", "agent"] as ControlMode[]).map((mode) => {
              const disabled = mode === "agent";
              return (
                <button
                  key={mode}
                  className={controlMode === mode ? "option-button selected" : "option-button"}
                  type="button"
                  disabled={disabled}
                  title={disabled ? "Agent control is only available in admin mode." : mode}
                  onClick={() => setControlMode(mode)}
                >
                  <span>{mode}</span>
                </button>
              );
            })}
          </div>
        </fieldset>
        <label>
          <span>Max Steps</span>
          <input type="number" min={1} max={1600} value={maxSteps} disabled aria-disabled="true" onChange={(event) => setMaxSteps(Number(event.target.value))} />
        </label>
        <div className="summary-strip">
          <span>{String(selectedSummary.node_count ?? 0)} nodes</span>
          <span>{String(selectedSummary.edge_count ?? 0)} edges</span>
          <span>{String(selectedSummary.room_count ?? 0)} rooms</span>
        </div>
        {mutation.error && <div className="error-panel">{mutation.error.message}</div>}
        <button className="button primary submit-button" type="submit" disabled={!activeVersionId || mutation.isPending}>
          <Play size={16} aria-hidden />
          Start Run
        </button>
      </form>
    </section>
  );
}
