import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Box, Check, CopyPlus, DoorOpen, Network, PanelsTopLeft, Save, Warehouse } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { getScene, getSceneGraph, listObjectCatalog, listSceneVersions, publishSceneLayout, validateSceneLayout } from "../../api/scenes";
import { useAuth } from "../../app/auth";
import type { InteractionHit, SceneLayoutValidation } from "../../types/api";
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
  return text(node?.semantic_type || node?.object_type);
}

function isRoom(node: RawNode): boolean {
  return nodeType(node) === "room" || semanticType(node) === "room";
}

function isCatalogObject(node: RawNode): boolean {
  return ["fixed_object", "movable_object"].includes(nodeType(node)) && !["door", "button"].includes(semanticType(node));
}

function deepCopy<T>(value: T): T {
  return structuredClone(value);
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
  const [draft, setDraft] = useState<SceneSource | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [validation, setValidation] = useState<SceneLayoutValidation | null>(null);
  const [view, setView] = useState<"2d" | "3d" | "graph">("2d");
  const [lastInteractionHit, setLastInteractionHit] = useState<InteractionHit | null>(null);

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
    const rooms = (next.nodes ?? []).filter(isRoom);
    setSelectedId(text(rooms[0]?.id));
    setValidation(null);
  }, [graph.data]);

  const nodes = draft?.nodes ?? [];
  const edges = draft?.edges ?? [];
  const layout = draft?.layout;
  const nodeById = useMemo(() => new Map(nodes.map((node) => [text(node.id), node])), [nodes]);
  const rooms = useMemo(() => nodes.filter(isRoom), [nodes]);
  const selectedNode = nodeById.get(selectedId);
  const selectedRoomId = isRoom(selectedNode ?? {})
    ? selectedId
    : layout?.objects[selectedId]?.room_id ?? layout?.doors[selectedId]?.room_a_id ?? "";
  const selectedRoom = selectedRoomId ? nodeById.get(selectedRoomId) : undefined;
  const roomObjects = useMemo(
    () => Object.entries(layout?.objects ?? {}).filter(([, item]) => item.room_id === selectedRoomId),
    [layout?.objects, selectedRoomId],
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

  function placeObjectInRoom(objectId: string, roomId: string) {
    if (!draft || !layout || !layout.objects[objectId] || !layout.rooms[roomId]) return;
    const next = deepCopy(draft);
    const node = (next.nodes ?? []).find((item) => text(item.id) === objectId);
    const previousParent = text(node?.parent);
    if (node) node.parent = roomId;
    for (const candidate of next.nodes ?? []) {
      if (!Array.isArray(candidate.child)) continue;
      const children = candidate.child.filter((child) => text(child) !== objectId);
      if (text(candidate.id) === roomId && !children.includes(objectId)) children.push(objectId);
      candidate.child = children;
    }
    let replaced = false;
    next.edges = (next.edges ?? []).map((edge) => {
      const target = text(edge.target_id || edge.target);
      const source = text(edge.source_id || edge.source);
      const relation = text(edge.relation || edge.edge_type);
      if (target === objectId && source === previousParent && ["inside_room", "on", "in", "inside"].includes(relation)) {
        replaced = true;
        return { ...edge, source_id: roomId, target_id: objectId, relation: "inside_room", edge_type: "structural_edge" };
      }
      return edge;
    });
    if (!replaced) {
      next.edges.push({ source_id: roomId, target_id: objectId, relation: "inside_room", edge_type: "structural_edge", category: "structural", properties: {} });
    }
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
    clone.parent = selectedRoomId;
    clone.child = [];
    (next.nodes ??= []).push(clone);
    const room = next.nodes.find((node) => text(node.id) === selectedRoomId);
    if (room) {
      const children = Array.isArray(room.child) ? [...room.child] : [];
      children.push(id);
      room.child = children;
    }
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
      width_cells: templatePlacement?.width_cells ?? (nodeType(template) === "movable_object" ? 1 : 2),
      depth_cells: templatePlacement?.depth_cells ?? (nodeType(template) === "movable_object" ? 1 : 2),
      rotation: 0,
    };
    setDraft(next);
    setSelectedId(id);
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
            {lastInteractionHit && <span className="builder-hit-readout" title="Latest Three.js raycast hit">hit: {lastInteractionHit.node_id}{lastInteractionHit.surface_uv ? ` · UV ${lastInteractionHit.surface_uv.map((value) => value.toFixed(2)).join(",")}` : ""}</span>}
          </div>
          {view === "2d" && <FloorplanCanvas nodes={nodes} edges={edges} layout={layout} selectedId={selectedId} onSelect={setSelectedId} onChange={updateLayout} />}
          {view === "3d" && <Scene3DCanvas nodes={nodes} layout={layout} selectedId={selectedId} onSelect={setSelectedId} onChange={updateLayout} catalog={objectCatalog.data ?? []} onInteractionHit={setLastInteractionHit} />}
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
