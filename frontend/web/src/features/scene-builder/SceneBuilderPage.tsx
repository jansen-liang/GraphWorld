import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Box, Check, CopyPlus, DoorOpen, Network, PanelsTopLeft, Save, Trash2, Warehouse } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { dispatchSceneSimulation, getScene, getSceneGraph, listObjectCatalog, listSceneVersions, publishSceneLayout, startSceneSimulation, stopSceneSimulation, validateSceneLayout } from "../../api/scenes";
import { useAuth } from "../../app/auth";
import type { SceneLayoutValidation } from "../../types/api";
import type { InteractionHit } from "../../types/api";
import type { InputEventPayload } from "../../protocol/events";
import { applySimulationDelta } from "../../protocol/delta";
import {
  FloorplanCanvas,
  sharedWall,
  type DoorPlacement,
  type FloorplanLayout,
  type ObjectPlacement,
  type RoomGeometry,
} from "./FloorplanCanvas";
import { Scene3DCanvas } from "./Scene3DCanvas";
import { SceneGraphCanvas } from "../scene-graph/SceneGraphCanvas";

type RawNode = Record<string, unknown>;
type RawEdge = Record<string, unknown>;

interface SceneSource extends Record<string, unknown> {
  nodes?: RawNode[];
  edges?: RawEdge[];
  layout?: FloorplanLayout;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function nodeName(node: RawNode | undefined): string {
  return text(node?.name_cn || node?.name || node?.id);
}

function nodeType(node: RawNode | undefined): string {
  return text(node?.node_type || node?.type);
}

function semanticType(node: RawNode | undefined): string {
  return text(node?.semantic_type);
}

function isRoom(node: RawNode): boolean {
  return nodeType(node) === "room" || semanticType(node) === "room";
}

function isCatalogObject(node: RawNode): boolean {
  return nodeType(node) === "object" && !["door", "button"].includes(semanticType(node));
}

function deepCopy<T>(value: T): T {
  return structuredClone(value);
}

function storedSimulationMatchesSource(stored: Record<string, unknown>, source: SceneSource | null): boolean {
  if (!source) return false;
  const snapshot = stored.snapshot;
  if (!snapshot || typeof snapshot !== "object") return false;
  const snapshotNodes = (snapshot as Record<string, unknown>).nodes;
  if (!Array.isArray(snapshotNodes)) return false;
  const sourceById = new Map((source.nodes ?? []).map((node) => [text(node.id), node]));
  const snapshotById = new Map(
    snapshotNodes
      .filter((item): item is RawNode => Boolean(item && typeof item === "object"))
      .map((item) => [text(item.id), item]),
  );
  // A stored run is reusable only when it was started from the same graph
  // topology. Comparing only shared nodes allowed a snapshot containing
  // generated elevator hall buttons to pass validation when the editor
  // source was an older graph without those nodes.
  if (snapshotById.size !== sourceById.size || [...snapshotById.keys()].some((id) => !sourceById.has(id))) return false;
  for (const item of snapshotNodes) {
    if (!item || typeof item !== "object") continue;
    const node = item as RawNode;
    const sourceNode = sourceById.get(text(node.id));
    if (!sourceNode) continue;
    if (JSON.stringify(sourceNode.states ?? {}) !== JSON.stringify(node.states ?? {})) return false;
  }
  return true;
}

function numberValue(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function uniqueNodeId(nodes: RawNode[], semantic: string, roomId: string): string {
  const base = `${semantic || "object"}_${roomId}`.replace(/[^a-zA-Z0-9_:-]+/g, "_");
  const ids = new Set(nodes.map((node) => text(node.id)));
  let counter = 1;
  while (ids.has(`${base}_${counter}`)) counter += 1;
  return `${base}_${counter}`;
}

function reconcileDoors(layout: FloorplanLayout): FloorplanLayout {
  const doors = Object.fromEntries(Object.entries(layout.doors).map(([doorId, door]) => {
    const roomA = layout.rooms[door.room_a_id];
    const roomB = layout.rooms[door.room_b_id];
    const shared = roomA && roomB ? sharedWall(roomA, roomB) : null;
    if (!shared) return [doorId, door];
    const width = Math.min(door.width_cells, shared.end - shared.start);
    const origin = shared.wall === "east" || shared.wall === "west" ? roomA.grid_y : roomA.grid_x;
    return [doorId, {
      ...door,
      wall: shared.wall,
      width_cells: width,
      offset_cells: shared.start - origin + Math.floor((shared.end - shared.start - width) / 2),
    }];
  }));
  return { ...layout, doors };
}

export function SceneBuilderPage() {
  const { sceneId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const auth = useAuth();
  const requestedVersionId = searchParams.get("version") ?? "";
  const autoStartSimulation = searchParams.get("run") === "1";
  const [draft, setDraft] = useState<SceneSource | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [validation, setValidation] = useState<SceneLayoutValidation | null>(null);
  const [view, setView] = useState<"2d" | "3d" | "graph">("2d");
  const [floorNumber, setFloorNumber] = useState(1);
  const [simulationActive, setSimulationActive] = useState(false);
  const simulationActiveRef = useRef(false);
  const draftRef = useRef<SceneSource | null>(null);
  const simulationIdRef = useRef("");
  const simulationSessionRef = useRef<Awaited<ReturnType<typeof startSceneSimulation>> | null>(null);
  const simulationStartRef = useRef<Promise<Awaited<ReturnType<typeof startSceneSimulation>>> | null>(null);
  // Immutable editor source for the current run. Runtime deltas may mutate
  // the live draft while playing, but must never become the next run's seed.
  const simulationSourceRef = useRef<SceneSource | null>(null);
  const simulationRevisionRef = useRef<number | null>(null);
  const interactionSequenceRef = useRef(0);
  const latestAppliedInteractionRef = useRef(0);
  // Key-down interactions and key-up hand releases must reach one simulation
  // session in order. React Query mutations otherwise run concurrently, so a
  // fast release can overtake the press that produced the interaction.
  const interactionQueueRef = useRef<Promise<unknown>>(Promise.resolve());
  const pendingSimulationSourceRef = useRef<SceneSource | null>(null);

  const scene = useQuery({ queryKey: ["scene", sceneId], queryFn: () => getScene(sceneId), enabled: Boolean(sceneId) });
  const versions = useQuery({ queryKey: ["scene-versions", sceneId], queryFn: () => listSceneVersions(sceneId), enabled: Boolean(sceneId) });
  const versionIds = new Set(versions.data?.map((version) => version.id) ?? []);
  const activeVersionId = requestedVersionId && versionIds.has(requestedVersionId) ? requestedVersionId : versions.data?.[0]?.id || "";
  const graph = useQuery({
    queryKey: ["scene-graph", activeVersionId],
    queryFn: () => getSceneGraph(activeVersionId),
    enabled: Boolean(activeVersionId),
  });
  const objectCatalog = useQuery({ queryKey: ["object-catalog"], queryFn: listObjectCatalog, enabled: auth.isAdmin });

  useEffect(() => {
    if (!graph.data) return;
    const next = deepCopy(graph.data.source_json as SceneSource);
    setDraft(next);
    draftRef.current = next;
    const rooms = (next.nodes ?? []).filter(isRoom);
    setSelectedId(text(rooms[0]?.id));
    setValidation(null);
  }, [graph.data]);
  useEffect(() => {
    if (autoStartSimulation) setView("3d");
  }, [autoStartSimulation]);

  const nodes = draft?.nodes ?? [];
  const edges = draft?.edges ?? [];
  const layout = draft?.layout;
  const nodeById = useMemo(() => new Map(nodes.map((node) => [text(node.id), node])), [nodes]);
  const rooms = useMemo(() => nodes.filter(isRoom), [nodes]);
  const floorNumbers = useMemo(() => {
    const values = new Set(rooms.map((room) => Number(layout?.rooms[text(room.id)]?.floor_number ?? room.floor_number ?? 1)));
    return [...values].filter(Number.isFinite).sort((a, b) => a - b);
  }, [rooms, layout?.rooms]);
  useEffect(() => {
    if (floorNumbers.length && !floorNumbers.includes(floorNumber)) setFloorNumber(floorNumbers[0]);
  }, [floorNumbers, floorNumber]);
  const selectedNode = nodeById.get(selectedId);
  const selectedIsElevatorCar = semanticType(selectedNode) === "elevator";
  const selectedRoomId = isRoom(selectedNode ?? {})
    ? selectedId
    : layout?.objects[selectedId]?.room_id ?? layout?.doors[selectedId]?.room_a_id ?? "";
  const selectedRoom = selectedRoomId ? nodeById.get(selectedRoomId) : undefined;
  const roomObjects = useMemo(
    () => Object.entries(layout?.objects ?? {}).filter(([id, item]) => item.room_id === selectedRoomId && semanticType(nodeById.get(id)) !== "elevator"),
    [layout?.objects, selectedRoomId, nodeById],
  );
  const catalog = useMemo(() => {
    const seen = new Set<string>();
    return nodes.filter((node) => {
      const semantic = semanticType(node);
      if (!isCatalogObject(node) || !semantic || seen.has(semantic)) return false;
      seen.add(semantic);
      return true;
    });
  }, [nodes]);
  const adjacency = useMemo(() => {
    if (!selectedRoomId) return [];
    return edges.flatMap((edge) => {
      const relation = text(edge.relation || edge.edge_type);
      const source = text(edge.source_id || edge.source);
      const target = text(edge.target_id || edge.target);
      if (relation !== "connected") return [];
      if (source === selectedRoomId) return [target];
      if (target === selectedRoomId) return [source];
      return [];
    });
  }, [edges, selectedRoomId]);
  const sharedDoors = useMemo(
    () => Object.entries(layout?.doors ?? {}).filter(([, door]) => door.room_a_id === selectedRoomId || door.room_b_id === selectedRoomId),
    [layout?.doors, selectedRoomId],
  );

  const validateMutation = useMutation({
    mutationFn: () => validateSceneLayout(activeVersionId, draft as Record<string, unknown>),
    onSuccess: setValidation,
  });
  const publishMutation = useMutation({
    mutationFn: () => publishSceneLayout(activeVersionId, draft as Record<string, unknown>),
    onSuccess: async (published) => {
      await queryClient.invalidateQueries({ queryKey: ["scene-versions", sceneId] });
      navigate(`/scenes/${sceneId}?version=${published.id}`);
    },
  });
  const interactionMutation = useMutation({
    mutationFn: (request: { targetId: string; hand: "left" | "right"; hit: InteractionHit; input?: "interact_primary" | "move" | "lower_hand"; roomId?: string; requestSeq?: number; event?: InputEventPayload }): Promise<any> => {
      request.requestSeq = ++interactionSequenceRef.current;
      if (!simulationActiveRef.current || !simulationIdRef.current) {
        return Promise.reject(new Error("simulation session is not active"));
      }
      return dispatchSceneSimulation(simulationIdRef.current, { input: request.input, targetId: request.targetId, hand: request.hand, hit: request.hit, distanceM: request.hit.distance_m, event: request.event });
    },
    onSuccess: (result, request) => {
      if (request.requestSeq && request.requestSeq < latestAppliedInteractionRef.current) return;
      latestAppliedInteractionRef.current = request.requestSeq || latestAppliedInteractionRef.current;
      console.info("Scene interaction result", {
        applied: result.applied,
        action: result.action,
        failures: result.failures,
        delta: result.delta,
      });
      if (!result.applied) {
        console.warn(`Scene interaction rejected: ${result.failures.join("; ")}`, result.action);
        return;
      }
      const source = result.snapshot as SceneSource;
      if (simulationActiveRef.current) {
        // Keep all references stable while Three.js owns the simulation.
        // Replacing draft/nodes tears down the canvas and releases pointer
        // lock; mutating the canonical snapshot in place keeps the live
        // renderer and the next session dispatch synchronized.
        const current = draftRef.current;
        if (current && applySimulationDelta(current, result.delta ?? {}, simulationRevisionRef.current)) {
          simulationRevisionRef.current = Number(result.delta?.revision ?? simulationRevisionRef.current);
          draftRef.current = current;
          // Delta application mutates the canonical draft in place. Trigger a
          // render as well so Three.js observes state-only changes such as a
          // hall button's is_on/is_pressed illumination; without this, the
          // live canvas keeps the pre-press node object snapshot until the
          // next tick.
          setDraft((previous) => previous ? { ...previous, nodes: [...(previous.nodes ?? [])] } : previous);
          // Three owns the live simulation scene. Do not replace the draft
          // object here: doing so remounts the canvas, resets the camera, and
          // restarts editor-only joint animation.
        } else if (current) {
          // A revision gap or legacy response requires the complete snapshot.
          const currentNodes = current.nodes ?? (current.nodes = []);
          const byId = new Map(currentNodes.map((node) => [text(node.id), node]));
          (source.nodes ?? []).forEach((nextNode) => {
            const existing = byId.get(text(nextNode.id));
            if (existing) Object.assign(existing, nextNode);
            else currentNodes.push(nextNode);
          });
          const currentEdges = current.edges ?? (current.edges = []);
          currentEdges.splice(0, currentEdges.length, ...(source.edges ?? []));
          if (source.world_state) current.world_state = source.world_state;
          // A functional setState updater can run after the next key event;
          // the ref is updated synchronously before any subsequent request.
          // Keep the live Three scene mounted while simulation owns rendering.
          simulationRevisionRef.current = Number(source.revision ?? simulationRevisionRef.current);
        } else {
          draftRef.current = source;
          setDraft(source);
          simulationRevisionRef.current = Number(source.revision ?? simulationRevisionRef.current);
        }
      } else {
        setDraft(source);
        draftRef.current = source;
      }
    },
    onError: (error) => console.error("Scene interaction request failed", error),
  });
  const tickMutation = useMutation({
    mutationFn: (): Promise<any> => {
      if (!simulationIdRef.current) return Promise.reject(new Error("simulation session is not active"));
      return dispatchSceneSimulation(simulationIdRef.current, { input: "tick" });
    },
    onSuccess: (result) => {
      const source = result.snapshot as SceneSource;
      if (simulationActiveRef.current) {
        setDraft((current) => {
          if (!current) return source;
          if (applySimulationDelta(current, result.delta ?? {}, simulationRevisionRef.current)) {
            simulationRevisionRef.current = Number(result.delta?.revision ?? simulationRevisionRef.current);
            draftRef.current = current;
            return { ...current };
          }
          const currentNodes = current.nodes ?? (current.nodes = []);
          const byId = new Map(currentNodes.map((node) => [text(node.id), node]));
          (source.nodes ?? []).forEach((nextNode) => {
            const existing = byId.get(text(nextNode.id));
            if (existing) Object.assign(existing, nextNode);
            else currentNodes.push(nextNode);
          });
          const currentEdges = current.edges ?? (current.edges = []);
          currentEdges.splice(0, currentEdges.length, ...(source.edges ?? []));
          if (source.world_state) current.world_state = source.world_state;
          draftRef.current = current;
          simulationRevisionRef.current = Number(source.revision ?? simulationRevisionRef.current);
          return { ...current };
        });
      } else {
        setDraft(source);
        draftRef.current = source;
      }
    },
  });
  const hasActiveProcess = nodes.some((node) => {
    const states = node.states as Record<string, unknown> | undefined;
    const transportActive = Array.isArray(node.request_queue) && node.request_queue.length > 0
      || ["moving", "opening", "dwelling", "closing"].includes(String(states?.motion_state || ""))
      || ["opening", "dwelling", "closing"].includes(String(states?.door_phase || ""));
    return Boolean(states?.is_running || states?.water_flowing || transportActive);
  });
  useEffect(() => {
    if (!simulationActiveRef.current || !hasActiveProcess || tickMutation.isPending) return;
    const timer = window.setInterval(() => tickMutation.mutate(), 1000);
    return () => window.clearInterval(timer);
  }, [hasActiveProcess, tickMutation.isPending, tickMutation]);

  function updateLayout(nextLayout: FloorplanLayout) {
    setDraft((current) => (current ? { ...current, layout: reconcileDoors(nextLayout) } : current));
    setValidation(null);
  }

  function updateRoom(roomId: string, patch: Partial<RoomGeometry>) {
    if (!layout) return;
    updateLayout({ ...layout, rooms: { ...layout.rooms, [roomId]: { ...layout.rooms[roomId], ...patch } } });
  }

  function updateObject(objectId: string, patch: Partial<ObjectPlacement>) {
    if (!layout) return;
    updateLayout({ ...layout, objects: { ...layout.objects, [objectId]: { ...layout.objects[objectId], ...patch } } });
  }

  const updatePlacementEdge = useCallback((objectId: string, parentId: string) => {
    setDraft((current) => {
      if (!current) return current;
      const next = deepCopy(current);
      if (!next.nodes?.some((entry) => text(entry.id) === objectId)) return current;
      next.edges = (next.edges ?? []).filter((edge) =>
        !(["at", "on", "in", "contains", "inside", "inside_room"].includes(text(edge.relation || edge.edge_type))
          && text(edge.target_id || edge.target) === objectId),
      );
      const parentIsRoom = isRoom(next.nodes?.find((entry) => text(entry.id) === parentId) ?? {});
      next.edges.push({
        category: parentIsRoom ? "structural" : "containment",
        relation: parentIsRoom ? "inside_room" : "on",
        edge_type: parentIsRoom ? "structural_edge" : "containment_edge",
        source_id: parentId,
        target_id: objectId,
        properties: {},
      });
      return next;
    });
  }, []);

  function placeObjectInRoom(objectId: string, roomId: string) {
    if (!draft || !layout || !layout.objects[objectId] || !layout.rooms[roomId]) return;
    const next = deepCopy(draft);
    next.edges = (next.edges ?? []).filter((edge) => {
      const target = text(edge.target_id || edge.target);
      const relation = text(edge.relation || edge.edge_type);
      return !(target === objectId && ["at", "inside_room", "on", "in", "inside", "contains"].includes(relation));
    });
    next.edges.push({ source_id: roomId, target_id: objectId, relation: "inside_room", edge_type: "structural_edge", category: "structural", properties: {} });
    const item = next.layout!.objects[objectId];
    next.layout!.objects[objectId] = { ...item, room_id: roomId, grid_x: 1, grid_y: 1 };
    setDraft(next);
    setValidation(null);
  }

  function addFromCatalog() {
    if (!draft || !layout || !selectedRoomId || !templateId) return;
    const template = nodeById.get(templateId);
    if (!template) return;
    const next = deepCopy(draft);
    const id = uniqueNodeId(next.nodes ?? [], semanticType(template), selectedRoomId);
    const clone = deepCopy(template);
    clone.id = id;
    delete clone.parent;
    delete clone.parent_id;
    delete clone.runtime_relation;
    delete clone.child;
    delete clone.inventory;
    (next.nodes ??= []).push(clone);
    (next.edges ??= []).push({
      source_id: selectedRoomId,
      target_id: id,
      relation: "inside_room",
      edge_type: "structural_edge",
      category: "structural",
      properties: {},
    });
    const templatePlacement = layout.objects[templateId];
    next.layout!.objects[id] = {
      room_id: selectedRoomId,
      grid_x: 1,
      grid_y: 1,
      width_cells: templatePlacement?.width_cells ?? (Array.isArray(template.capabilities) && template.capabilities.includes("pickable") ? 1 : 2),
      depth_cells: templatePlacement?.depth_cells ?? (Array.isArray(template.capabilities) && template.capabilities.includes("pickable") ? 1 : 2),
      rotation: 0,
    };
    setDraft(next);
    setSelectedId(id);
    setValidation(null);
  }

  function deleteSelectedNode() {
    if (!draft || !layout || !selectedNode || isRoom(selectedNode)) return;
    const removeIds = new Set<string>([selectedId]);
    const pending = [selectedId];
    while (pending.length) {
      const parentId = pending.pop()!;
      const children = edges.flatMap((edge) => {
        const relation = text(edge.relation || edge.edge_type);
        const source = text(edge.source_id || edge.source);
        return source === parentId && ["component_of", "part_of", "structure"].includes(relation)
          ? [text(edge.target_id || edge.target)]
          : [];
      });
      children.forEach((childId) => {
        if (!removeIds.has(childId)) {
          removeIds.add(childId);
          pending.push(childId);
        }
      });
    }
    const next = deepCopy(draft);
    next.nodes = (next.nodes ?? []).filter((node) => !removeIds.has(text(node.id)));
    next.edges = (next.edges ?? []).filter((edge) =>
      !removeIds.has(text(edge.source_id || edge.source))
      && !removeIds.has(text(edge.target_id || edge.target)));
    removeIds.forEach((id) => {
      delete next.layout!.objects[id];
      delete next.layout!.doors[id];
    });
    setDraft(next);
    setSelectedId(selectedRoomId);
    setValidation(null);
  }

  async function validateThenPublish() {
    if (!draft) return;
    const result = await validateMutation.mutateAsync();
    if (result.valid) publishMutation.mutate();
  }

  if (!auth.isAdmin) {
    return <section className="page"><div className="error-panel">Scene Builder requires an administrator account.</div></section>;
  }
  if (graph.isLoading || !draft || !layout) {
    return <section className="page"><div className="empty-panel">Loading scene builder.</div></section>;
  }

  return (
    <section className="page full-height scene-builder-page">
      <header className="page-header builder-header">
        <div>
          <p className="eyebrow">Scene Builder · {scene.data?.domain || "scene"}</p>
          <h1>{scene.data?.name || sceneId}</h1>
        </div>
        <div className="header-actions">
          <label className="header-select compact-select">
            <span>Source snapshot</span>
            <select value={activeVersionId} onChange={(event) => setSearchParams({ version: event.target.value })}>
              {versions.data?.map((version) => <option key={version.id} value={version.id}>Version {version.version}</option>)}
            </select>
          </label>
          <button className="button" type="button" onClick={() => validateMutation.mutate()} disabled={validateMutation.isPending}>
            <Check size={16} aria-hidden /> Validate
          </button>
          <button className="button primary" type="button" onClick={validateThenPublish} disabled={publishMutation.isPending || validateMutation.isPending}>
            <Save size={16} aria-hidden /> Save layout
          </button>
        </div>
      </header>

      {validation && (
        <div className={validation.valid ? "builder-validation valid" : "builder-validation invalid"}>
          {validation.valid ? <Check size={17} /> : <AlertTriangle size={17} />}
          <span>{validation.valid ? "Layout is valid and ready to publish." : validation.issues.join(" ")}</span>
        </div>
      )}
      {(validateMutation.error || publishMutation.error) && (
        <div className="error-panel compact">{(validateMutation.error || publishMutation.error)?.message}</div>
      )}

      <div className="scene-builder-layout">
        <aside className="builder-library">
          <div className="builder-panel-heading"><Warehouse size={16} /><strong>Rooms</strong></div>
          <div className="builder-room-list">
            {rooms.map((room) => {
              const id = text(room.id);
              const geometry = layout.rooms[id];
              return (
                <button key={id} className={selectedRoomId === id ? "builder-list-button selected" : "builder-list-button"} type="button" onClick={() => setSelectedId(id)}>
                  <span>{nodeName(room)}</span>
                  <small>{geometry ? `${geometry.width_cells} x ${geometry.depth_cells} cells` : "No layout"}</small>
                </button>
              );
            })}
          </div>

          <div className="builder-panel-heading"><Box size={16} /><strong>Objects in room</strong></div>
          <div className="builder-object-list">
            {roomObjects.map(([id]) => (
              <button key={id} className={selectedId === id ? "builder-list-button selected" : "builder-list-button"} type="button" onClick={() => setSelectedId(id)}>
                <span>{nodeName(nodeById.get(id))}</span><small>{semanticType(nodeById.get(id))}</small>
              </button>
            ))}
          </div>
          <button className="button builder-delete-button" type="button" onClick={deleteSelectedNode} disabled={!selectedNode || isRoom(selectedNode) || selectedIsElevatorCar}>
            <Trash2 size={15} /> Delete selected node
          </button>

          <div className="builder-catalog">
            <div className="catalog-heading"><strong>Object library</strong><small>{objectCatalog.data?.length ?? 0} specifications from PostgreSQL</small></div>
            <select aria-label="Browse object library" defaultValue="">
              <option value="">Browse catalog dimensions</option>
              {(objectCatalog.data ?? []).map((entry) => <option key={entry.semantic_type} value={entry.semantic_type}>{entry.name_cn || entry.name} · {entry.width_cm} x {entry.depth_cm} x {entry.height_cm} cm</option>)}
            </select>
            <label><span>Add from this scene</span>
              <select value={templateId} onChange={(event) => setTemplateId(event.target.value)}>
                <option value="">Select object template</option>
                {catalog.map((node) => <option key={text(node.id)} value={text(node.id)}>{nodeName(node)} · {semanticType(node)}</option>)}
              </select>
            </label>
            <button className="button" type="button" onClick={addFromCatalog} disabled={!templateId || !selectedRoomId}>
              <CopyPlus size={16} /> Add to room
            </button>
          </div>
        </aside>

        <main className="builder-canvas-region">
          <div className="builder-view-toolbar" role="tablist" aria-label="Scene view">
            <button className={view === "2d" ? "active" : ""} type="button" onClick={() => setView("2d")} role="tab" aria-selected={view === "2d"}><PanelsTopLeft size={15} /> 2D</button>
            <button className={view === "3d" ? "active" : ""} type="button" onClick={() => setView("3d")} role="tab" aria-selected={view === "3d"}><Box size={15} /> 3D</button>
            <button className={view === "graph" ? "active" : ""} type="button" onClick={() => setView("graph")} role="tab" aria-selected={view === "graph"}><Network size={15} /> Graph</button>
          </div>
          {view === "2d" && <>
            <div className="floor-switcher" role="tablist" aria-label="楼层">
              {floorNumbers.map((number) => <button key={number} type="button" className={floorNumber === number ? "active" : ""} onClick={() => setFloorNumber(number)} aria-selected={floorNumber === number}>{number}F</button>)}
            </div>
            <FloorplanCanvas nodes={nodes} edges={edges} layout={layout} floorNumber={floorNumber} selectedId={selectedId} onSelect={setSelectedId} onChange={updateLayout} />
          </>}
          {view === "3d" && <Scene3DCanvas autoStartSimulation={autoStartSimulation} nodes={nodes} edges={edges} layout={layout} selectedId={selectedId} onSelect={setSelectedId} onChange={updateLayout} onPlacementChange={updatePlacementEdge} catalog={objectCatalog.data ?? []} onSimulationInteraction={(request) => {
            const next = interactionQueueRef.current
              .catch(() => undefined)
              .then(() => interactionMutation.mutateAsync(request));
            interactionQueueRef.current = next.then(() => undefined, () => undefined);
            return next;
          }} onSimulationMove={(position, direction, elapsedSeconds, event) => {
            if (!simulationIdRef.current) return Promise.resolve();
            return dispatchSceneSimulation(simulationIdRef.current, { input: "movement_sample", position, physics: { direction, elapsed_seconds: elapsedSeconds }, elapsedSeconds, event }).then((result) => {
              const current = draftRef.current;
              const source = result.snapshot as SceneSource;
              if (!current) return result as unknown as Record<string, unknown>;
              if (applySimulationDelta(current, result.delta ?? {}, simulationRevisionRef.current)) {
                simulationRevisionRef.current = Number(result.delta?.revision ?? simulationRevisionRef.current);
                return result as unknown as Record<string, unknown>;
              }
              const worldState = source.world_state as Record<string, unknown> | undefined;
              if (worldState) current.world_state = worldState;
              simulationRevisionRef.current = Number(source.revision ?? simulationRevisionRef.current);
              draftRef.current = current;
              return result as unknown as Record<string, unknown>;
            });
          }} onSimulationEvent={(event) => {
            if (!simulationIdRef.current) return Promise.resolve();
            return dispatchSceneSimulation(simulationIdRef.current, { input: "input_event", event }) as unknown as Promise<Record<string, unknown>>;
          }} onSimulationStart={async () => {
            if (simulationSessionRef.current) return simulationSessionRef.current as unknown as Record<string, unknown>;
            if (simulationStartRef.current) return await simulationStartRef.current as unknown as Record<string, unknown>;
            if (!simulationSourceRef.current) {
              const source = draftRef.current ?? draft;
              simulationSourceRef.current = source ? deepCopy(source) : null;
            }
            const actorId = text(nodes.find((node) => {
            const type = nodeType(node).toLowerCase();
            const semantic = semanticType(node).toLowerCase();
            return ["agent", "robot", "human"].includes(type) || ["agent", "robot", "human"].includes(semantic);
            })?.id);
            const stored = sessionStorage.getItem("graphworld.simulation");
            const source = simulationSourceRef.current ?? draftRef.current ?? draft;
            let storedSession: Awaited<ReturnType<typeof startSceneSimulation>> | null = null;
            if (stored) {
              try {
                const parsed = JSON.parse(stored) as Record<string, unknown>;
                if (storedSimulationMatchesSource(parsed, source)) {
                  storedSession = parsed as unknown as Awaited<ReturnType<typeof startSceneSimulation>>;
                } else {
                  console.info("Discarding stale simulation session: runtime states differ from editor source");
                  sessionStorage.removeItem("graphworld.simulation");
                }
              } catch {
                sessionStorage.removeItem("graphworld.simulation");
              }
            }
            const startPromise = storedSession
              ? Promise.resolve(storedSession)
              : startSceneSimulation(source as Record<string, unknown>, actorId);
            simulationStartRef.current = startPromise;
            const result = await startPromise;
            simulationStartRef.current = null;
            sessionStorage.removeItem("graphworld.simulation");
            // Runtime preparation may materialize graph-backed objects and
            // their layout anchors (notably upper-floor hall buttons). The
            // renderer was already built from the editor draft, so merge the
            // authoritative startup layout before Run begins; merging nodes
            // alone leaves snapshot objects without Three.js meshes.
            const startupSnapshot = result.snapshot as Record<string, unknown>;
            const startupLayout = startupSnapshot.layout as FloorplanLayout | undefined;
            if (startupLayout && typeof startupLayout === "object") {
              const current = draftRef.current;
              if (current) {
                const next = deepCopy(current);
                next.layout = deepCopy(startupLayout);
                const startupNodes = startupSnapshot.nodes;
                if (Array.isArray(startupNodes)) {
                  const byId = new Map((next.nodes ?? []).map((node) => [text(node.id), node]));
                  for (const item of startupNodes) {
                    if (!item || typeof item !== "object") continue;
                    const node = item as RawNode;
                    const existing = byId.get(text(node.id));
                    if (existing) Object.assign(existing, deepCopy(node));
                    else {
                      next.nodes = [...(next.nodes ?? []), deepCopy(node)];
                      byId.set(text(node.id), next.nodes[next.nodes.length - 1]);
                    }
                  }
                }
                draftRef.current = next;
                setDraft(next);
              }
            }
            simulationSessionRef.current = result;
            simulationIdRef.current = result.simulation_id;
            simulationRevisionRef.current = Number(result.snapshot.revision ?? 0);
            return result as unknown as Record<string, unknown>;
          }} onSimulationActiveChange={(active) => {
            simulationActiveRef.current = active;
            setSimulationActive(active);
            if (!active && simulationIdRef.current) {
              const simulationId = simulationIdRef.current;
              simulationSessionRef.current = null;
              simulationIdRef.current = "";
              simulationRevisionRef.current = null;
              void stopSceneSimulation(simulationId);
            }
            if (!active && simulationSourceRef.current) {
              const source = deepCopy(simulationSourceRef.current);
              draftRef.current = source;
              setDraft(source);
              simulationSourceRef.current = null;
              simulationStartRef.current = null;
              simulationSessionRef.current = null;
              simulationRevisionRef.current = null;
            }
          }} />}
          {view === "graph" && <div className="builder-graph-stage"><SceneGraphCanvas nodes={nodes} edges={edges} selectedNodeId={selectedId} onSelectNode={setSelectedId} /></div>}
        </main>

        <aside className="builder-inspector">
          <div className="builder-panel-heading"><strong>Properties</strong></div>
          {selectedNode && isRoom(selectedNode) && layout.rooms[selectedId] && (
            <RoomInspector
              node={selectedNode}
              geometry={layout.rooms[selectedId]}
              gridSize={layout.grid_size}
              adjacency={adjacency.map((id) => nodeName(nodeById.get(id)) || id)}
              doors={sharedDoors.map(([id, door]) => ({
                id,
                wall: door.room_a_id === selectedId ? door.wall : ({ north: "south", east: "west", south: "north", west: "east" } as const)[door.wall],
                neighbor: nodeName(nodeById.get(door.room_a_id === selectedId ? door.room_b_id : door.room_a_id)),
              }))}
              onChange={(patch) => updateRoom(selectedId, patch)}
            />
          )}
          {selectedNode && !isRoom(selectedNode) && layout.objects[selectedId] && (
            <ObjectInspector
              node={selectedNode}
              placement={layout.objects[selectedId]}
              rooms={rooms}
              onChange={(patch) => updateObject(selectedId, patch)}
              onRoomChange={(roomId) => placeObjectInRoom(selectedId, roomId)}
            />
          )}
          {selectedNode && layout.doors[selectedId] && (
            <DoorInspector node={selectedNode} placement={layout.doors[selectedId]} nodeById={nodeById} />
          )}
          {!selectedNode && <div className="empty-panel compact">Select a room or object.</div>}
        </aside>
      </div>
    </section>
  );
}

function NumericField({ label, value, onChange, min = 0 }: { label: string; value: number; onChange: (value: number) => void; min?: number }) {
  return <label><span>{label}</span><input type="number" min={min} step="1" value={value} onChange={(event) => onChange(Math.round(numberValue(event.target.value, value)))} /></label>;
}

function RoomInspector({ node, geometry, gridSize, adjacency, doors, onChange }: {
  node: RawNode;
  geometry: RoomGeometry;
  gridSize: number;
  adjacency: string[];
  doors: Array<{ id: string; wall: string; neighbor: string }>;
  onChange: (patch: Partial<RoomGeometry>) => void;
}) {
  return <div className="builder-fields">
    <div className="inspector-title"><Warehouse size={17} /><div><strong>{nodeName(node)}</strong><small>{text(node.id)}</small></div></div>
    <div className="field-pair"><NumericField label="Grid column" value={geometry.grid_x} onChange={(grid_x) => onChange({ grid_x })} /><NumericField label="Grid row" value={geometry.grid_y} onChange={(grid_y) => onChange({ grid_y })} /></div>
    <div className="field-pair"><NumericField label="Width (cells)" value={geometry.width_cells} min={2} onChange={(width_cells) => onChange({ width_cells })} /><NumericField label="Depth (cells)" value={geometry.depth_cells} min={2} onChange={(depth_cells) => onChange({ depth_cells })} /></div>
    <dl className="builder-facts"><div><dt>Area</dt><dd>{(geometry.width_cells * geometry.depth_cells * gridSize * gridSize).toFixed(1)} m²</dd></div><div><dt>Doors</dt><dd>{doors.length} / 4</dd></div></dl>
    <div className="builder-readonly"><span>Adjacent rooms</span><strong>{adjacency.join(", ") || "None"}</strong></div>
    <div className="builder-readonly"><span>Shared doors</span><strong>{doors.map((door) => `${door.wall}: ${door.neighbor} (${door.id})`).join("; ") || "Open passage / none"}</strong></div>
  </div>;
}

function ObjectInspector({ node, placement, rooms, onChange, onRoomChange }: {
  node: RawNode;
  placement: ObjectPlacement;
  rooms: RawNode[];
  onChange: (patch: Partial<ObjectPlacement>) => void;
  onRoomChange: (roomId: string) => void;
}) {
  const states = node.states && typeof node.states === "object" ? node.states as Record<string, unknown> : {};
  const schema = node.state_schema && typeof node.state_schema === "object" ? node.state_schema as Record<string, unknown> : {};
  const stateEntries = Object.entries(schema).length ? Object.entries(schema) : Object.entries(states).map(([name, value]) => [name, { default_value: value }] as const);
  const capabilities = Array.isArray(node.capabilities) ? node.capabilities.map(String) : [];
  const worldX = placement.x_cm ?? placement.grid_x * 10;
  const worldY = placement.y_cm ?? placement.grid_y * 10;
  const worldZ = placement.z_cm ?? 0;
  const length = placement.width_cm ?? placement.width_cells * 10;
  const width = placement.depth_cm ?? placement.depth_cells * 10;
  const height = placement.height_cm ?? 80;
  const attributes = [
    ["Semantic type", semanticType(node) || "object"],
    ["Category", text(node.semantic_class || node.category) || "object"],
    ["Capabilities", capabilities.join(", ") || "None"],
    ["Size", `${placement.width_cells} x ${placement.depth_cells} cells`],
  ];
  return <div className="builder-fields">
    <div className="inspector-title"><DoorOpen size={17} /><div><strong>{nodeName(node)}</strong><small>{semanticType(node)} · {nodeType(node)}</small></div></div>
    <label><span>Room</span><select value={placement.room_id} onChange={(event) => onRoomChange(event.target.value)}>{rooms.map((room) => <option key={text(room.id)} value={text(room.id)}>{nodeName(room)}</option>)}</select></label>
    <div className="inspector-section-title">World position (m)</div>
    <div className="field-triplet"><MetricField label="X" value={worldX} onChange={(x_cm) => onChange({ x_cm })} /><MetricField label="Y" value={worldY} onChange={(y_cm) => onChange({ y_cm })} /><MetricField label="Z" value={worldZ} onChange={(z_cm) => onChange({ z_cm })} /></div>
    <div className="inspector-section-title">Dimensions (m)</div>
    <div className="field-triplet"><MetricField label="Length" value={length} onChange={(width_cm) => onChange({ width_cm })} /><MetricField label="Width" value={width} onChange={(depth_cm) => onChange({ depth_cm })} /><MetricField label="Height" value={height} onChange={(height_cm) => onChange({ height_cm })} /></div>
    <div className="inspector-section-title">Attributes</div>
    <dl className="builder-facts inspector-facts">{attributes.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    <div className="inspector-section-title">States</div>
    {stateEntries.length ? <div className="state-list">{stateEntries.map(([name, definition]) => {
      const detail = definition && typeof definition === "object" ? definition as Record<string, unknown> : {};
      const current = states[name];
      const fallback = detail.default_value ?? detail.positive_value ?? current ?? "-";
      return <div className="state-row" key={name}><span>{name}</span><strong>{formatInspectorValue(current ?? fallback)}</strong><small>default: {formatInspectorValue(fallback)}</small></div>;
    })}</div> : <div className="builder-readonly"><span>State schema</span><strong>No declared states</strong></div>}
  </div>;
}

function MetricField({ label, value, onChange }: { label: string; value: number; onChange: (valueCm: number) => void }) {
  return <label><span>{label}</span><input type="number" min={0} step="0.01" value={(value / 100).toFixed(2)} onChange={(event) => onChange(Math.max(0, Number(event.target.value) * 100 || 0))} /></label>;
}

function formatInspectorValue(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value);
}

function DoorInspector({ node, placement, nodeById }: {
  node: RawNode;
  placement: DoorPlacement;
  nodeById: Map<string, RawNode>;
}) {
  return <div className="builder-fields">
    <div className="inspector-title"><DoorOpen size={17} /><div><strong>{nodeName(node)}</strong><small>Shared door node</small></div></div>
    <div className="builder-readonly"><span>Connects</span><strong>{nodeName(nodeById.get(placement.room_a_id))} ↔ {nodeName(nodeById.get(placement.room_b_id))}</strong></div>
    <dl className="builder-facts"><div><dt>Wall</dt><dd>{placement.wall}</dd></div><div><dt>Width</dt><dd>{placement.width_cells} cells</dd></div></dl>
    <div className="builder-readonly"><span>Graph semantics</span><strong>One Door Node with two connects edges</strong></div>
  </div>;
}
