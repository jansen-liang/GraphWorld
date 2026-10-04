import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Pencil, Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getScene, getSceneGraph, listScenes, listSceneVersions } from "../../api/scenes";
import type { SceneVersionRead } from "../../types/api";
import { SceneGraphCanvas } from "../scene-graph/SceneGraphCanvas";
import { useSceneViewStore } from "../../stores/sceneViewStore";
import { useAuth } from "../../app/auth";

function sourceNodes(sourceJson: Record<string, unknown>): Record<string, unknown>[] {
  const nodes = sourceJson.nodes;
  return Array.isArray(nodes) ? (nodes as Record<string, unknown>[]) : [];
}

function sourceEdges(sourceJson: Record<string, unknown>): Record<string, unknown>[] {
  const edges = sourceJson.edges;
  return Array.isArray(edges) ? (edges as Record<string, unknown>[]) : [];
}

function nodeName(node: Record<string, unknown> | undefined) {
  if (!node) {
    return "";
  }
  return String(node.name_cn || node.name || node.id || "");
}

function nodeType(node: Record<string, unknown>) {
  return String(node.node_type || node.semantic_type || "");
}

function npcNodes(nodes: Record<string, unknown>[]) {
  return nodes.filter((node) => nodeType(node) === "human" || String(node.semantic_type || "") === "human");
}

function stateText(node: Record<string, unknown>, key: string) {
  const value = node[key];
  return typeof value === "string" && value ? value : "";
}

function snapshotLabel(version: SceneVersionRead) {
  const summary = version.graph_summary ?? {};
  const profile = summary.variant_profile;
  const axes = summary.variant_axes;
  if (typeof profile === "string" && profile) {
    return `Snapshot ${version.version} · ${profile}`;
  }
  if (axes && typeof axes === "object" && !Array.isArray(axes)) {
    const values = Object.values(axes).map(String).filter(Boolean);
    if (values.length) {
      return `Snapshot ${version.version} · ${values.join(" / ")}`;
    }
  }
  return `Snapshot ${version.version} · base scene`;
}

export function SceneDetailPage() {
  const { sceneId = "" } = useParams();
  const navigate = useNavigate();
  const auth = useAuth();
  const [versionId, setVersionId] = useState("");
  const selectedNodeId = useSceneViewStore((state) => state.selectedNodeId);
  const setSelectedNodeId = useSceneViewStore((state) => state.setSelectedNodeId);

  const scenes = useQuery({ queryKey: ["scenes"], queryFn: listScenes });
  const scene = useQuery({ queryKey: ["scene", sceneId], queryFn: () => getScene(sceneId), enabled: Boolean(sceneId) });
  const versions = useQuery({ queryKey: ["scene-versions", sceneId], queryFn: () => listSceneVersions(sceneId), enabled: Boolean(sceneId) });
  const versionIds = new Set(versions.data?.map((version) => version.id) ?? []);
  const activeVersionId = versionId && versionIds.has(versionId) ? versionId : versions.data?.[0]?.id || "";
  const graph = useQuery({
    queryKey: ["scene-graph", activeVersionId],
    queryFn: () => getSceneGraph(activeVersionId),
    enabled: Boolean(activeVersionId),
  });

  const nodes = useMemo(() => sourceNodes(graph.data?.source_json ?? {}), [graph.data]);
  const edges = useMemo(() => sourceEdges(graph.data?.source_json ?? {}), [graph.data]);
  const nodeById = useMemo(() => new Map(nodes.map((node) => [String(node.id || ""), node])), [nodes]);
  const npcs = useMemo(() => npcNodes(nodes), [nodes]);
  const selectedNode = nodes.find((node) => String(node.id) === selectedNodeId);
  const summary = versions.data?.find((version) => version.id === activeVersionId)?.graph_summary ?? {};

  useEffect(() => {
    setVersionId("");
    setSelectedNodeId("");
  }, [sceneId, setSelectedNodeId]);

  useEffect(() => {
    setSelectedNodeId("");
  }, [activeVersionId, setSelectedNodeId]);

  return (
    <section className="page full-height">
      <header className="page-header">
        <div>
          <p className="eyebrow">{scene.data?.domain || "Scene"}</p>
          <h1>{scene.data?.name || sceneId}</h1>
        </div>
        <div className="header-actions">
          <label className="header-select">
            <span>Scene</span>
            <select value={sceneId} onChange={(event) => navigate(`/scenes/${event.target.value}`)}>
              {scenes.data?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name || item.id}
                </option>
              ))}
            </select>
          </label>
          <label className="header-select">
            <span>Snapshot</span>
            <select value={activeVersionId} onChange={(event) => setVersionId(event.target.value)}>
              {versions.data?.map((version) => (
                <option key={version.id} value={version.id}>
                  {snapshotLabel(version)}
                </option>
              ))}
            </select>
          </label>
          {auth.isAdmin && (
            <Link className="button" to={`/scenes/${sceneId}/edit?version=${activeVersionId}`}>
              <Pencil size={16} aria-hidden />
              Edit 2D
            </Link>
          )}
          <Link className="button primary" to={`/runs/new?sceneVersionId=${activeVersionId}`}>
            <Play size={16} aria-hidden />
            Run
          </Link>
        </div>
      </header>

      <div className="split-view">
        <div className="graph-region">
          {graph.isLoading ? (
            <div className="empty-panel">Loading graph.</div>
          ) : (
            <SceneGraphCanvas nodes={nodes} edges={edges} selectedNodeId={selectedNodeId} onSelectNode={setSelectedNodeId} />
          )}
        </div>
        <aside className="inspector">
          <h2>Summary</h2>
          <dl className="metric-grid">
            <div><dt>Nodes</dt><dd>{String(summary.node_count ?? 0)}</dd></div>
            <div><dt>Edges</dt><dd>{String(summary.edge_count ?? 0)}</dd></div>
            <div><dt>Rooms</dt><dd>{String(summary.room_count ?? 0)}</dd></div>
            <div><dt>Floors</dt><dd>{String(summary.floor_count ?? 0)}</dd></div>
          </dl>
          <h2>NPCs</h2>
          {npcs.length ? (
            <div className="npc-list">
              {npcs.map((npc) => {
                const parent = String(npc.parent || "");
                const parentNode = nodeById.get(parent);
                return (
                  <div key={String(npc.id)} className="npc-card">
                    <div>
                      <strong>{nodeName(npc)}</strong>
                      <span>{stateText(npc, "role") || "npc"}</span>
                    </div>
                    <small>{stateText(npc, "current_activity") || "idle"}</small>
                    <small>{parentNode ? `@ ${nodeName(parentNode)}` : parent ? `@ ${parent}` : "location unknown"}</small>
                    {stateText(npc, "persona") && <small>{stateText(npc, "persona")}</small>}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="empty-panel compact">No NPCs in this snapshot.</div>
          )}
          <h2>Selected Node</h2>
          {selectedNode ? (
            <div className="detail-block">
              <strong>{nodeName(selectedNode)}</strong>
              <span>{String(selectedNode.node_type || "")} · {String(selectedNode.semantic_type || "")}</span>
              <pre>{JSON.stringify(selectedNode.states ?? {}, null, 2)}</pre>
            </div>
          ) : (
            <div className="empty-panel compact">Select a node.</div>
          )}
          <Link className="text-link" to="/runs/new">
            Configure another run <ArrowRight size={14} aria-hidden />
          </Link>
        </aside>
      </div>
    </section>
  );
}
