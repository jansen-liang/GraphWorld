import { useMemo, useRef, useState } from "react";

type RawNode = Record<string, unknown>;
type RawEdge = Record<string, unknown>;

export interface RoomGeometry {
  grid_x: number;
  grid_y: number;
  width_cells: number;
  depth_cells: number;
  x_cm?: number;
  y_cm?: number;
  z_cm?: number;
  width_cm?: number;
  depth_cm?: number;
  height_cm?: number;
}

export interface DoorPlacement {
  room_a_id: string;
  room_b_id: string;
  wall: "north" | "east" | "south" | "west";
  offset_cells: number;
  width_cells: number;
}

export interface ObjectPlacement {
  room_id: string;
  grid_x: number;
  grid_y: number;
  width_cells: number;
  depth_cells: number;
  rotation?: number;
  rotation_x?: number;
  rotation_y?: number;
  rotation_z?: number;
  layout_anchor?: string;
  placement_mode?: "contained" | "wall_mounted" | "surface";
  parent_object_id?: string;
  x_cm?: number;
  y_cm?: number;
  z_cm?: number;
  width_cm?: number;
  depth_cm?: number;
  height_cm?: number;
}

export interface FloorplanLayout {
  units: string;
  grid_size: number;
  rooms: Record<string, RoomGeometry>;
  doors: Record<string, DoorPlacement>;
  objects: Record<string, ObjectPlacement>;
}

interface FloorplanCanvasProps {
  nodes: RawNode[];
  edges: RawEdge[];
  layout: FloorplanLayout;
  selectedId: string;
  onSelect: (id: string) => void;
  onChange: (layout: FloorplanLayout) => void;
}

interface DragState {
  kind: "room" | "object";
  id: string;
  offsetX: number;
  offsetY: number;
}

interface WallSegment {
  wall: DoorPlacement["wall"];
  start: number;
  end: number;
}

const ROOM_COLORS = ["#e0f2fe", "#dcfce7", "#fef3c7", "#fce7f3", "#e0e7ff", "#cffafe", "#f3e8ff"];

function text(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function nodeName(node: RawNode | undefined): string {
  return text(node?.name_cn || node?.name || node?.id);
}

function nodeType(node: RawNode | undefined): string {
  return text(node?.node_type || node?.type);
}

function isCorridor(node: RawNode | undefined): boolean {
  return [node?.id, node?.name, node?.name_cn, node?.semantic_type, node?.room_type]
    .some((value) => text(value).toLowerCase().includes("corridor") || text(value).includes("走廊"));
}

function edgeValue(edge: RawEdge, key: "source" | "target" | "relation"): string {
  if (key === "source") return text(edge.source_id || edge.source);
  if (key === "target") return text(edge.target_id || edge.target);
  return text(edge.relation || edge.edge_type);
}

export function sharedWall(first: RoomGeometry, second: RoomGeometry): WallSegment | null {
  if (first.grid_x + first.width_cells === second.grid_x || second.grid_x + second.width_cells === first.grid_x) {
    const start = Math.max(first.grid_y, second.grid_y);
    const end = Math.min(first.grid_y + first.depth_cells, second.grid_y + second.depth_cells);
    if (end > start) return { wall: first.grid_x + first.width_cells === second.grid_x ? "east" : "west", start, end };
  }
  if (first.grid_y + first.depth_cells === second.grid_y || second.grid_y + second.depth_cells === first.grid_y) {
    const start = Math.max(first.grid_x, second.grid_x);
    const end = Math.min(first.grid_x + first.width_cells, second.grid_x + second.width_cells);
    if (end > start) return { wall: first.grid_y + first.depth_cells === second.grid_y ? "south" : "north", start, end };
  }
  return null;
}

function Opening({ room, wall, offset, width, door }: { room: RoomGeometry; wall: DoorPlacement["wall"]; offset: number; width: number; door: boolean }) {
  const vertical = wall === "east" || wall === "west";
  const x = wall === "east" ? room.grid_x + room.width_cells : wall === "west" ? room.grid_x : room.grid_x + offset;
  const y = wall === "south" ? room.grid_y + room.depth_cells : wall === "north" ? room.grid_y : room.grid_y + offset;
  const x2 = vertical ? x : x + width;
  const y2 = vertical ? y + width : y;
  const leafX = vertical ? x + (wall === "east" ? -width : width) : x;
  const leafY = vertical ? y : y + (wall === "south" ? -width : width);
  return <g className={door ? undefined : "floorplan-passage"}>
    <line x1={x} y1={y} x2={x2} y2={y2} stroke="#ffffff" strokeWidth="0.3" />
    {door && <>
      <line x1={x} y1={y} x2={leafX} y2={leafY} stroke="#0f766e" strokeWidth="0.13" />
      <circle cx={x} cy={y} r="0.12" fill="#0f766e" />
    </>}
  </g>;
}

export function FloorplanCanvas({ nodes, edges, layout, selectedId, onSelect, onChange }: FloorplanCanvasProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [drag, setDrag] = useState<DragState | null>(null);
  const nodeById = useMemo(() => new Map(nodes.map((node) => [text(node.id), node])), [nodes]);
  const roomEntries = Object.entries(layout.rooms);
  const bounds = useMemo(() => ({
    width: Math.max(20, ...roomEntries.map(([, room]) => room.grid_x + room.width_cells + 1)),
    depth: Math.max(16, ...roomEntries.map(([, room]) => room.grid_y + room.depth_cells + 1)),
  }), [roomEntries]);

  const openPassages = useMemo(() => edges.flatMap((edge) => {
    if (edgeValue(edge, "relation") !== "connected") return [];
    const sourceId = edgeValue(edge, "source");
    const targetId = edgeValue(edge, "target");
    const source = layout.rooms[sourceId];
    const target = layout.rooms[targetId];
    if (!source || !target || (!isCorridor(nodeById.get(sourceId)) && !isCorridor(nodeById.get(targetId)))) return [];
    const shared = sharedWall(source, target);
    if (!shared) return [];
    const width = Math.min(3, shared.end - shared.start);
    const origin = shared.wall === "east" || shared.wall === "west" ? source.grid_y : source.grid_x;
    return [{ room: source, wall: shared.wall, offset: shared.start - origin + Math.floor((shared.end - shared.start - width) / 2), width }];
  }), [edges, layout.rooms, nodeById]);

  function point(event: React.PointerEvent<SVGSVGElement | SVGGElement>) {
    const svg = svgRef.current;
    if (!svg) return { x: 0, y: 0 };
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const transformed = point.matrixTransform(svg.getScreenCTM()?.inverse());
    return { x: transformed.x, y: transformed.y };
  }

  function startRoomDrag(event: React.PointerEvent<SVGGElement>, id: string) {
    event.currentTarget.setPointerCapture(event.pointerId);
    const cursor = point(event);
    const room = layout.rooms[id];
    setDrag({ kind: "room", id, offsetX: cursor.x - room.grid_x, offsetY: cursor.y - room.grid_y });
    onSelect(id);
  }

  function startObjectDrag(event: React.PointerEvent<SVGGElement>, id: string) {
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    const cursor = point(event);
    const item = layout.objects[id];
    const room = layout.rooms[item.room_id];
    setDrag({ kind: "object", id, offsetX: cursor.x - room.grid_x - item.grid_x, offsetY: cursor.y - room.grid_y - item.grid_y });
    onSelect(id);
  }

  function move(event: React.PointerEvent<SVGSVGElement>) {
    if (!drag) return;
    const cursor = point(event);
    if (drag.kind === "room") {
      const room = layout.rooms[drag.id];
      onChange({
        ...layout,
        rooms: {
          ...layout.rooms,
          [drag.id]: { ...room, grid_x: Math.max(0, Math.round(cursor.x - drag.offsetX)), grid_y: Math.max(0, Math.round(cursor.y - drag.offsetY)) },
        },
      });
      return;
    }
    const item = layout.objects[drag.id];
    const room = layout.rooms[item.room_id];
    const wallMounted = item.placement_mode === "wall_mounted";
    const maxX = room.width_cells - (wallMounted ? 1 : item.width_cells);
    const maxY = room.depth_cells - (wallMounted ? 1 : item.depth_cells);
    const grid_x = Math.max(0, Math.min(maxX, Math.round(cursor.x - room.grid_x - drag.offsetX)));
    const grid_y = Math.max(0, Math.min(maxY, Math.round(cursor.y - room.grid_y - drag.offsetY)));
    const cellCm = Math.round((layout.grid_size || 0.1) * 100);
    onChange({
      ...layout,
      objects: {
        ...layout.objects,
        [drag.id]: {
          ...item,
          grid_x,
          grid_y,
          x_cm: Math.round((room.x_cm ?? room.grid_x * cellCm) + grid_x * cellCm),
          y_cm: Math.round((room.y_cm ?? room.grid_y * cellCm) + grid_y * cellCm),
        },
      },
    });
  }

  return <div className="floorplan-stage">
    <svg
      ref={svgRef}
      className="floorplan-canvas"
      viewBox={`0 0 ${bounds.width} ${bounds.depth}`}
      onPointerMove={move}
      onPointerUp={() => setDrag(null)}
      onPointerCancel={() => setDrag(null)}
      aria-label="Editable grid floor plan"
    >
      <defs>
        <pattern id="floor-grid" width="1" height="1" patternUnits="userSpaceOnUse">
          <path d="M 1 0 L 0 0 0 1" fill="none" stroke="#e2e8f0" strokeWidth="0.035" />
        </pattern>
      </defs>
      <rect width={bounds.width} height={bounds.depth} fill="url(#floor-grid)" />
      {roomEntries.map(([roomId, room], index) => {
        const selected = selectedId === roomId;
        const objects = Object.entries(layout.objects).filter(([, item]) => item.room_id === roomId);
        return <g key={roomId} onPointerDown={(event) => startRoomDrag(event, roomId)} className="floorplan-room">
          <rect
            x={room.grid_x}
            y={room.grid_y}
            width={room.width_cells}
            height={room.depth_cells}
            fill={ROOM_COLORS[index % ROOM_COLORS.length]}
            stroke={selected ? "#1d4ed8" : "#334155"}
            strokeWidth={selected ? "0.22" : "0.13"}
          />
          <text x={room.grid_x + 0.35} y={room.grid_y + 0.7} className="floorplan-room-label">
            {nodeName(nodeById.get(roomId)) || roomId}
          </text>
          <text x={room.grid_x + 0.35} y={room.grid_y + 1.18} className="floorplan-room-meta">
            {room.width_cells} x {room.depth_cells} cells
          </text>
          {objects.map(([objectId, item]) => {
            const node = nodeById.get(objectId);
            const active = selectedId === objectId;
            return <g key={objectId} onPointerDown={(event) => startObjectDrag(event, objectId)} className="floorplan-object">
              <rect
                x={room.grid_x + item.grid_x}
                y={room.grid_y + item.grid_y}
                width={item.width_cells}
                height={item.depth_cells}
                rx="0.08"
                fill={nodeType(node) === "movable_object" ? "#60a5fa" : "#ffffff"}
                stroke={active ? "#111827" : "#64748b"}
                strokeWidth={active ? "0.16" : "0.08"}
              />
              {item.width_cells >= 2 && item.depth_cells >= 1 && <text
                x={room.grid_x + item.grid_x + 0.16}
                y={room.grid_y + item.grid_y + 0.48}
                className="floorplan-object-label"
              >{nodeName(node) || objectId}</text>}
            </g>;
          })}
        </g>;
      })}
      {openPassages.map((passage, index) => <Opening key={`passage-${index}`} {...passage} door={false} />)}
      {Object.entries(layout.doors).map(([doorId, door]) => {
        const room = layout.rooms[door.room_a_id];
        if (!room) return null;
        return <g key={doorId} onPointerDown={(event) => { event.stopPropagation(); onSelect(doorId); }} className={selectedId === doorId ? "floorplan-door selected" : "floorplan-door"}>
          <Opening room={room} wall={door.wall} offset={door.offset_cells} width={door.width_cells} door />
        </g>;
      })}
    </svg>
    <div className="floorplan-scale">1 cell = {layout.grid_size} m</div>
  </div>;
}
