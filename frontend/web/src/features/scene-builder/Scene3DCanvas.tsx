import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import RAPIER from "@dimforge/rapier3d-compat";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { TransformControls } from "three/examples/jsm/controls/TransformControls.js";
import { Eye, EyeOff, Layers3, X } from "lucide-react";
import type { FloorplanLayout } from "./FloorplanCanvas";
import type { ObjectCatalogEntry } from "../../api/scenes";
import type { InteractionHit } from "../../types/api";
import { applyRuntimeJointState, attachHinge, attachLocalPart, attachPart, attachPrismatic, createComposite, updateComposites, type CompositeObject } from "../../rendering/partTree";
import { handForKey, isMovementKey, movementAxes } from "../../input/keyboard";
import { chooseSimulationHit, interactionHitFromIntersection, objectIdForHit } from "../../input/raycast";
import { normalizedPointer, setRayFromPointer } from "../../input/pointer";
import { isOccluded } from "../../physics/collision";
import { surfacePlacementPosition } from "../../physics/placementPreview";
import { updateVisualEffects, visualCuesOf, type VisualEffect } from "../../rendering/effects";
import { updateSelectionVisibility } from "../../rendering/highlight";
import { inputEvent, type InputEventPayload } from "../../protocol/events";
import { applyProtocolToThree, applyProtocolWorldToThree } from "../../protocol/transform";

type RawNode = Record<string, unknown>;

interface Scene3DCanvasProps {
  nodes: RawNode[];
  edges: RawNode[];
  layout: FloorplanLayout;
  selectedId: string;
  onSelect: (id: string) => void;
  onChange: (layout: FloorplanLayout) => void;
  onPlacementChange?: (objectId: string, parentId: string) => void;
  catalog: ObjectCatalogEntry[];
  onInteractionHit?: (hit: InteractionHit) => void;
  onSimulationInteraction: (request: { targetId: string; hand: "left" | "right"; hit: InteractionHit; input?: "interact_primary" | "move" | "lower_hand"; roomId?: string; event?: InputEventPayload }) => Promise<unknown> | void;
  onSimulationMove: (position: { x: number; y: number; z: number }, direction: [number, number], elapsedSeconds: number, event?: InputEventPayload) => Promise<Record<string, unknown> | void>;
  onSimulationEvent?: (event: InputEventPayload) => Promise<Record<string, unknown> | void>;
  onSimulationActiveChange?: (active: boolean) => void;
  onSimulationStart?: () => Promise<Record<string, unknown> | void>;
  autoStartSimulation?: boolean;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function semantic(node: RawNode | undefined): string {
  return text(node?.semantic_type).toLowerCase();
}

function nodeName(node: RawNode | undefined): string {
  return text(node?.name_cn || node?.name || node?.id);
}

function objectCategory(node: RawNode | undefined): string {
  const value = text(node?.semantic_class || node?.category).toLowerCase();
  if (["appliance", "equipment", "machine"].includes(value)) return "appliance";
  if (["furniture", "storage"].includes(value)) return "furniture";
  if (["container"].includes(value)) return "container";
  if (["consumable", "food", "product"].includes(value)) return "consumable";
  if (["food", "vegetable", "fruit", "drink", "juice", "milk", "egg", "bread", "tissue", "tissuebox"].includes(semantic(node))) return "consumable";
  if (["tool"].includes(value)) return "tool";
  if (["personal_item", "document"].includes(value)) return "personal";
  if (["control"].includes(value)) return "control";
  return "object";
}

const CATEGORY_COLORS: Record<string, number> = {
  appliance: 0x0f766e,
  furniture: 0x2563eb,
  container: 0x7c3aed,
  consumable: 0xf59e0b,
  tool: 0xdc2626,
  personal: 0xdb2777,
  control: 0x64748b,
  object: 0x475569,
};

const CATEGORY_LABELS: Array<[string, string]> = [
  ["appliance", "Appliance"],
  ["furniture", "Furniture"],
  ["container", "Container"],
  ["consumable", "Consumable"],
  ["tool", "Tool"],
  ["personal", "Personal item"],
  ["control", "Control"],
  ["object", "Object"],
];

function colorFor(index: number): number {
  return [0x3b82f6, 0x10b981, 0xf59e0b, 0xec4899, 0x8b5cf6, 0x06b6d4][index % 6];
}

function normalizeQuarterTurn(radians: number): number {
  return ((Math.round(radians / (Math.PI / 2)) % 4) + 4) % 4;
}

type WallSide = "north" | "east" | "south" | "west";
const OPPOSITE_WALL: Record<WallSide, WallSide> = { north: "south", east: "west", south: "north", west: "east" };

export function Scene3DCanvas({ nodes, edges, layout, selectedId, onSelect, onChange, onPlacementChange, catalog, onInteractionHit, onSimulationInteraction, onSimulationMove, onSimulationEvent, onSimulationStart, onSimulationActiveChange, autoStartSimulation = false }: Scene3DCanvasProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const selectRef = useRef(onSelect);
  const changeRef = useRef(onChange);
  const placementChangeRef = useRef(onPlacementChange);
  const simulationInteractionRef = useRef(onSimulationInteraction);
  const simulationMoveRef = useRef(onSimulationMove);
  const pendingSimulationLayoutRef = useRef<FloorplanLayout | null>(null);
  const cameraStateRef = useRef<{ position: THREE.Vector3; target: THREE.Vector3 } | null>(null);
  const simulationStateRef = useRef<{ player: THREE.Vector3; yaw: number; pitch: number; roomId: string; moving: boolean } | null>(null);
  const selectionVisualsRef = useRef(new Map<string, THREE.Object3D>());
  const transformControlsRef = useRef<TransformControls | null>(null);
  const rotationControlsRef = useRef<TransformControls | null>(null);
  const objectMeshesRef = useRef(new Map<string, THREE.Mesh>());
  const sceneRef = useRef<THREE.Scene | null>(null);
  const simulationActiveRef = useRef(false);
  const simulationControllerRef = useRef<{ start: () => void; stop: () => void } | null>(null);
  const lastMoveRequestRef = useRef(0);
  // Keep at most one movement request in flight. A promise chain can build up
  // stale 100 ms samples when the API is slower than the sampling interval,
  // which makes authoritative responses visibly jump backwards.
  const moveInFlightRef = useRef(false);
  const movementBarrierRef = useRef<Promise<void>>(Promise.resolve());
  const pendingMoveRef = useRef<{ direction: [number, number]; elapsed: number } | null>(null);
  const inputSequenceRef = useRef(0);
  const selectedIdRef = useRef(selectedId);
  const [labelsVisible, setLabelsVisible] = useState(true);
  const [simulationActive, setSimulationActive] = useState(false);
  const [pointerLocked, setPointerLocked] = useState(false);
  const [heldObjectLabel, setHeldObjectLabel] = useState("");
  const [slotHint, setSlotHint] = useState<{ count: number; capacity: number } | null>(null);
  const slotHintKeyRef = useRef("");
  const [statusCardId, setStatusCardId] = useState("");
  const [viewMode, setViewMode] = useState<"first" | "third">("first");
  const [layersOpen, setLayersOpen] = useState(false);
  const [layerVisibility, setLayerVisibility] = useState({ labels: true, floor: true, objects: true });
  const viewModeRef = useRef(viewMode);
  const handsRef = useRef({ left: false, right: false });
  selectRef.current = onSelect;
  changeRef.current = onChange;
  placementChangeRef.current = onPlacementChange;
  simulationInteractionRef.current = onSimulationInteraction;
  simulationMoveRef.current = onSimulationMove;
  selectedIdRef.current = selectedId;
  viewModeRef.current = viewMode;

  useEffect(() => {
    const transform = transformControlsRef.current;
    const rotation = rotationControlsRef.current;
    if (transform) transform.setMode("translate");
    if (rotation) rotation.setMode("rotate");
  });

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    scene.traverse((item) => {
      const layer = String(item.userData.layer || "");
      if (layer === "labels") item.visible = layerVisibility.labels;
      else if (layer === "floor") item.visible = layerVisibility.floor;
      else if (layer === "objects") item.visible = layerVisibility.objects;
    });
  }, [layerVisibility]);

  useEffect(() => {
    updateSelectionVisibility(selectionVisualsRef.current, selectedId);
    const transform = transformControlsRef.current;
    const rotation = rotationControlsRef.current;
    if (!transform || simulationActiveRef.current) return;
    const selectedMesh = objectMeshesRef.current.get(selectedId);
    if (selectedMesh && semantic(nodes.find((node) => text(node.id) === selectedId)) !== "elevator") {
      transform.attach(selectedMesh);
      rotation?.attach(selectedMesh);
    } else {
      transform.detach();
      rotation?.detach();
    }
  }, [selectedId, nodes]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const scene = new THREE.Scene();
    sceneRef.current = scene;
    scene.background = new THREE.Color(0xf1f5f9);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x64748b, 2.2));
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.5);
    keyLight.position.set(8, 14, 10);
    scene.add(keyLight);

    // A slightly wider first-person field of view keeps the player from
    // feeling boxed in inside rooms and the elevator cabin.
    const camera = new THREE.PerspectiveCamera(60, 1, 0.05, 500);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(host.clientWidth, host.clientHeight);
    renderer.shadowMap.enabled = true;
    host.replaceChildren(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = false;
    controls.maxPolarAngle = Math.PI / 2.02;
    // Keep selection and camera navigation on separate mouse gestures:
    // left = select/drag, middle = orbit, wheel = zoom, right = pan.
    controls.mouseButtons.LEFT = -1 as unknown as THREE.MOUSE;
    controls.mouseButtons.MIDDLE = THREE.MOUSE.ROTATE;
    controls.mouseButtons.RIGHT = THREE.MOUSE.PAN;
    controls.enablePan = true;
    const interactive: THREE.Object3D[] = [];
    const collisionMeshes: THREE.Mesh[] = [];
    const elevatorCollisionMeshes = new Set<THREE.Mesh>();
    type RapierRuntime = {
      world: RAPIER.World;
      controller: ReturnType<RAPIER.World["createCharacterController"]>;
      collider: ReturnType<RAPIER.World["createCollider"]>;
      playerBody: ReturnType<RAPIER.World["createRigidBody"]>;
      staticBody: ReturnType<RAPIER.World["createRigidBody"]>;
      staticColliders: Map<THREE.Mesh, ReturnType<RAPIER.World["createCollider"]>>;
      elevatorBody: ReturnType<RAPIER.World["createRigidBody"]> | null;
      elevatorColliders: Map<THREE.Mesh, ReturnType<RAPIER.World["createCollider"]>>;
      disposed: boolean;
    };
    let rapierRuntime: RapierRuntime | null = null;
    let rapierInitCancelled = false;
    let effectDisposed = false;
    let lastCollisionLogAt = 0;
    const objectMeshes = new Map<string, THREE.Mesh>();
    const objectLabels = new Map<string, THREE.Sprite>();
    const animatedMeshes = new Map<string, { mesh: THREE.Mesh; base: THREE.Vector3; baseRotation: THREE.Euler }>();
    const elevatorButtonMeshes = new Map<string, THREE.Mesh>();
    const effectMeshes: VisualEffect[] = [];
    // Placement preview is renderer-only.  The backend remains authoritative
    // for the resulting edge and transform after the interaction is submitted.
    let placementPreview: THREE.Mesh | null = null;
    let placementHighlight: THREE.BoxHelper | null = null;
    let interactionHighlight: THREE.BoxHelper | null = null;
    let placementPreviewObject = "";
    let placementPreviewAnchor: [number, number] | null = null;
    let lastDebugHitId = "";
    let lastDebugColliderId = "";
    let lastDoorCollisionDebug = "";
    const composites: CompositeObject[] = [];
    const componentVisuals = new Map<string, THREE.Object3D>();
    const componentJointTypes = new Map<string, string>();
    const waterMeshes = new Map<string, THREE.Mesh>();
    const detergentVisuals = new Map<string, { bottle: THREE.Object3D; liquid: THREE.Mesh }>();
    const lightMeshes = new Map<string, THREE.PointLight>();
    const placedContents = new Map<string, number>();
    const receptacleContents = new Map<string, string[]>();
    const controlTargets = new Map<string, string[]>();
    const faucetsBySink = new Map<string, RawNode[]>();
    const storageSlotsByHost = new Map<string, string[]>();
    // Diagnostic metadata for tracing unexpected elevator geometry.  Keep
    // this renderer-only: it does not affect interaction or collision logic.
    const markElevatorMesh = (mesh: THREE.Object3D, debugSource: string, nodeId: string) => {
      mesh.userData.debugSource = debugSource;
      mesh.userData.debugNodeId = nodeId;
      mesh.userData.debugBounds = () => {
        const box = new THREE.Box3().setFromObject(mesh);
        return {
          min: box.min.toArray().map((value) => Number(value.toFixed(4))),
          max: box.max.toArray().map((value) => Number(value.toFixed(4))),
        };
      };
    };
    const logElevatorMesh = (mesh: THREE.Object3D, label = "Elevator mesh") => {
      const debugBounds = mesh.userData.debugBounds;
      console.debug(label, {
        name: mesh.name,
        id: mesh.userData.id,
        componentId: mesh.userData.componentId,
        debugSource: mesh.userData.debugSource,
        debugNodeId: mesh.userData.debugNodeId,
        visible: mesh.visible,
        collisionEnabled: mesh.userData.collisionEnabled,
        bounds: typeof debugBounds === "function" ? debugBounds() : undefined,
        parent: mesh.parent?.name,
      });
    };
    edges.forEach((edge) => {
      const relation = text(edge.relation || edge.edge_type);
      const source = text(edge.source_id || edge.source);
      const target = text(edge.target_id || edge.target);
      if (["contains", "inside"].includes(relation)) {
        receptacleContents.set(source, [...(receptacleContents.get(source) ?? []), target]);
      }
      // Runtime placement stores containment as item -> container (`in`),
      // while older prepared scenes use container -> item (`contains`). Keep
      // one renderer-side lookup so visual contents work for both forms.
      if (["in", "inside"].includes(relation)) {
        receptacleContents.set(target, [...(receptacleContents.get(target) ?? []), source]);
      }
      if (["component_of", "structure"].includes(relation) && semantic(nodes.find((node) => text(node.id) === target)) === "storage_slot") {
        storageSlotsByHost.set(source, [...(storageSlotsByHost.get(source) ?? []), target]);
      }
      if (relation !== "controls") return;
      controlTargets.set(source, [...(controlTargets.get(source) ?? []), target]);
      if (semantic(nodes.find((node) => text(node.id) === source)) === "faucet") {
        faucetsBySink.set(target, [...(faucetsBySink.get(target) ?? []), nodes.find((node) => text(node.id) === source)!]);
      }
    });
    const actorIds = new Set(nodes.filter((node) => text(node.node_type) === "agent").map((node) => text(node.id)));
    const actorId = actorIds.values().next().value as string | undefined;
    const positionParents = new Map(edges.flatMap((edge) => {
      const relation = text(edge.relation || edge.edge_type);
      return ["at", "in", "on", "inside", "inside_room", "contains", "held_by", "held_by_left", "held_by_right", "held_by_both"].includes(relation)
        ? [[text(edge.target_id || edge.target), text(edge.source_id || edge.source)] as const]
        : [];
    }));
    const roomFor = (nodeId: string) => {
      let current = nodeId;
      const seen = new Set<string>();
      while (current && !seen.has(current)) {
        seen.add(current);
        if (text(nodes.find((candidate) => text(candidate.id) === current)?.node_type) === "room") return current;
        current = positionParents.get(current) ?? "";
      }
      return "";
    };
    const actorRoomId = actorId ? roomFor(actorId) : "";
    const heldByHand: { left: string | null; right: string | null } = { left: null, right: null };
    edges.forEach((edge) => {
      const relation = text(edge.relation || edge.edge_type);
      const source = text(edge.source_id || edge.source);
      const target = text(edge.target_id || edge.target);
      if (!actorIds.has(source)) return;
      if (["held_by", "held_by_right"].includes(relation)) heldByHand.right = target;
      if (relation === "held_by_left") heldByHand.left = target;
      if (relation === "held_by_both") heldByHand.left = heldByHand.right = target;
    });
    const heldIds = new Set([heldByHand.left, heldByHand.right].filter((id): id is string => Boolean(id)));
    let activeInteractionHand: "left" | "right" = "right";
    const transformControls = new TransformControls(camera, renderer.domElement);
    transformControls.setMode("translate");
    transformControls.setSpace("world");
    transformControls.setSize(0.8);
    transformControlsRef.current = transformControls;
    const rotationControls = new TransformControls(camera, renderer.domElement);
    rotationControls.setMode("rotate");
    rotationControls.setSpace("world");
    rotationControls.setSize(0.95);
    rotationControls.setRotationSnap(Math.PI / 2);
    rotationControls.showX = true;
    rotationControls.showY = true;
    rotationControls.showZ = true;
    rotationControlsRef.current = rotationControls;
    objectMeshesRef.current = objectMeshes;
    scene.add(transformControls.getHelper());
    scene.add(rotationControls.getHelper());
    transformControls.setRotationSnap(Math.PI / 2);
    camera.layers.enable(1);
    if (!labelsVisible) camera.layers.disable(1);
    const dragState = { id: "", roomId: "", gridX: 0, gridY: 0, pointerId: -1, moved: false, hit: false, startX: 0, startY: 0 };
    const nodeById = new Map(nodes.map((node) => [text(node.id), node]));
    const componentNodesByHost = new Map<string, RawNode[]>();
    const componentHostById = new Map<string, string>();
    const componentNodeIds = new Set<string>();
    edges.forEach((edge) => {
      const relation = text(edge.relation || edge.edge_type);
      if (!new Set(["component_of", "part_of", "structure"]).has(relation)) return;
      const hostId = text(edge.source_id || edge.source);
      const componentId = text(edge.target_id || edge.target);
      const component = nodeById.get(componentId);
      if (!hostId || !component) return;
      componentHostById.set(componentId, hostId);
      componentNodeIds.add(componentId);
      const properties = edge.properties && typeof edge.properties === "object" ? edge.properties as RawNode : {};
      componentJointTypes.set(componentId, text(properties.joint_type || "fixed").toLowerCase());
      componentNodesByHost.set(hostId, [...(componentNodesByHost.get(hostId) ?? []), component]);
    });
    faucetsBySink.forEach((faucets, sinkId) => {
      faucets.forEach((faucet) => componentNodeIds.add(text(faucet.id)));
      componentNodesByHost.set(sinkId, [...(componentNodesByHost.get(sinkId) ?? []), ...faucets]);
    });
    const catalogByType = new Map(catalog.map((entry) => [entry.semantic_type.toLowerCase(), entry]));
    const roomEntries = Object.entries(layout.rooms);
    selectionVisualsRef.current.clear();
    const cell = layout.grid_size || 0.5;
    transformControls.setTranslationSnap(cell);
    // Storey pitch equals the room height: the next floor slab is the
    // previous floor's ceiling, with no inter-floor gap.
    const roomHeight = 3.2;
    const slabThickness = 0.12;
    const floorElevation = (room: { floor_number?: number }) => Math.max(0, Number(room.floor_number ?? 1) - 1) * 3.2;
    const allWidth = Math.max(...roomEntries.map(([, room]) => (room.grid_x + room.width_cells) * cell), 8);
    const allDepth = Math.max(...roomEntries.map(([, room]) => (room.grid_y + room.depth_cells) * cell), 6);

    // Floors and ceilings are the same editor layer.  The ceiling of one
    // storey is geometrically coincident with the floor level above it, so
    // both surfaces are controlled by the single "地板层" switch.
    roomEntries.forEach(([roomId, room]) => {
      // The elevator shaft is a continuous vertical room. Its upper levels
      // are represented by the per-storey slabs with a car-sized opening
      // below, so a generic full-room ceiling here would seal the 2F/3F
      // openings again.
      if (semantic(nodeById.get(roomId)) === "elevator_shaft") return;
      const ceiling = new THREE.Mesh(
        new THREE.BoxGeometry(room.width_cells * cell, slabThickness, room.depth_cells * cell),
        new THREE.MeshStandardMaterial({
          color: 0xcbd5e1,
          roughness: 0.96,
          transparent: true,
          opacity: 0.55,
          depthWrite: true,
          side: THREE.DoubleSide,
        }),
      );
      ceiling.position.set(
        (room.grid_x + room.width_cells / 2) * cell,
        roomHeight + floorElevation(room) + slabThickness / 2,
        (room.grid_y + room.depth_cells / 2) * cell,
      );
      ceiling.userData.layer = "floor";
      ceiling.visible = layerVisibility.floor;
      scene.add(ceiling);
    });

    const grid = new THREE.GridHelper(Math.max(allWidth, allDepth) + 2, Math.ceil(Math.max(allWidth, allDepth) / cell), 0x94a3b8, 0xcbd5e1);
    grid.position.set((allWidth - 1) / 2, -0.035, (allDepth - 1) / 2);
    scene.add(grid);
    grid.userData.layer = "floor";
    grid.visible = layerVisibility.floor;

    const wallKeys = new Set<string>();
    const wallMaterial = () => new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.9, metalness: 0.01 });
    const effectiveDoorWidthCells = (door: RawNode) => {
      const doorNode = nodeById.get(text(door.id));
      return text(doorNode?.door_kind) === "elevator_hall" ? Math.max(18, Number(door.width_cells) || 0) : Number(door.width_cells) || 0;
    };
    const wallOpenings = (roomId: string, wall: WallSide): Array<[number, number]> => {
      const openings: Array<[number, number]> = [];
      Object.entries(layout.doors).forEach(([doorId, door]) => {
        const roomA = layout.rooms[door.room_a_id];
        const roomB = layout.rooms[door.room_b_id];
        if (!roomA || !roomB) return;
        const side = door.room_a_id === roomId ? door.wall : door.room_b_id === roomId ? OPPOSITE_WALL[door.wall] : null;
        if (side !== wall) return;
        const horizontal = wall === "north" || wall === "south";
        // Door offsets are authored relative to room_a.  A shared wall is
        // rendered from both rooms, but its opening is one global interval;
        // recomputing the offset from room_b shifts the cut and leaves a
        // collision wall across the visible doorway.
        const origin = horizontal ? roomA.grid_x : roomA.grid_y;
        const start = (origin + door.offset_cells) * cell;
        openings.push([
          start,
          start + effectiveDoorWidthCells({ ...door, id: doorId } as unknown as RawNode) * cell,
        ]);
      });
      // Merge overlapping openings before generating wall segments. Without
      // this, interleaved cuts can create a short wall sliver in the doorway.
      return openings
        .sort((first, second) => first[0] - second[0])
        .reduce<Array<[number, number]>>((merged, current) => {
          const previous = merged[merged.length - 1];
          if (previous && current[0] <= previous[1]) {
            previous[1] = Math.max(previous[1], current[1]);
          } else {
            merged.push([...current]);
          }
          return merged;
        }, []);
    };
    const addWallSegments = (roomId: string, side: WallSide, selected: boolean, elevationOverride?: number) => {
      const room = layout.rooms[roomId];
      const horizontal = side === "north" || side === "south";
      const axisStart = (horizontal ? room.grid_x : room.grid_y) * cell;
      const axisEnd = axisStart + (horizontal ? room.width_cells : room.depth_cells) * cell;
      const boundary = (horizontal ? room.grid_y : room.grid_x) * cell + (side === "south" || side === "east" ? (horizontal ? room.depth_cells : room.width_cells) * cell : 0);
      const openings = wallOpenings(roomId, side);
      const clippedOpenings = openings
        .map(([start, end]) => [Math.max(axisStart, start), Math.min(axisEnd, end)] as [number, number])
        .filter(([start, end]) => end - start > 0.01);
      const elevation = elevationOverride ?? floorElevation(room);
      const addWall = (start: number, end: number, bottom: number, top: number, suffix: string) => {
        if (end - start <= 0.01 || top - bottom <= 0.01) return;
        const key = `${elevation.toFixed(3)}:${horizontal ? "h" : "v"}:${boundary.toFixed(3)}:${start.toFixed(3)}:${end.toFixed(3)}:${bottom.toFixed(3)}:${top.toFixed(3)}:${suffix}`;
        if (wallKeys.has(key)) return;
        wallKeys.add(key);
        const length = end - start;
        const wall = new THREE.Mesh(
          horizontal ? new THREE.BoxGeometry(length, top - bottom, 0.1) : new THREE.BoxGeometry(0.1, top - bottom, length),
          wallMaterial(),
        );
        wall.position.set(
          horizontal ? (start + end) / 2 : boundary,
          elevation + bottom + (top - bottom) / 2,
          horizontal ? boundary : (start + end) / 2,
        );
        wall.userData.layer = "objects";
        if (semantic(nodeById.get(roomId)) === "elevator_shaft") {
          wall.userData.debugSource = `elevator_shaft.wall.${roomId}.${side}`;
          wall.userData.debugNodeId = roomId;
        }
        scene.add(wall);
        collisionMeshes.push(wall);
      };
      // Generate the wall around each opening, leaving only the door-sized
      // clear span.  The old implementation removed the entire wall height
      // for every opening, which incorrectly deleted the lintel above doors.
      let cursor = axisStart;
      clippedOpenings.forEach(([start, end], index) => {
        addWall(cursor, start, 0, roomHeight, `side-before-${index}`);
        addWall(start, end, 2.1, roomHeight, `lintel-${index}`);
        cursor = Math.max(cursor, end);
      });
      addWall(cursor, axisEnd, 0, roomHeight, "side-after");
    };

    roomEntries.forEach(([roomId, room], index) => {
      const width = room.width_cells * cell;
      const depth = room.depth_cells * cell;
      const x = (room.grid_x + room.width_cells / 2) * cell;
      const z = (room.grid_y + room.depth_cells / 2) * cell;
      const elevation = floorElevation(room);
      const floorMaterial = new THREE.MeshStandardMaterial({ color: colorFor(index), transparent: true, opacity: selectedId === roomId ? 0.58 : 0.45, depthWrite: true, side: THREE.DoubleSide });
      const isShaft = semantic(nodeById.get(roomId)) === "elevator_shaft";
      if (!isShaft) {
        // Each ordinary room owns a complete floor slab. Its top is exactly
        // the room elevation, so adjacent storeys share the same surface.
        const roomMesh = new THREE.Mesh(new THREE.BoxGeometry(width, slabThickness, depth), floorMaterial);
        roomMesh.position.set(x, elevation - slabThickness / 2, z);
        roomMesh.userData = { id: roomId, simulationSurface: true, layer: "floor" };
        roomMesh.visible = layerVisibility.floor;
        scene.add(roomMesh);
        interactive.push(roomMesh);
        collisionMeshes.push(roomMesh);
      } else {
        // The shaft floor is an opening, not a solid slab. Leave exactly the
        // car floor footprint clear and retain four slabs around it for the
        // visible floor thickness and collision boundary. Do not use a ratio
        // of the shaft size: the opening must match the actual car floor.
        const carPlacement = layout.objects?.elevator_car_outside_home;
        const openingWidth = Number(carPlacement?.width_cm) > 0
          ? Number(carPlacement.width_cm) / 100 * 0.9
          : width * 0.9;
        const openingDepth = Number(carPlacement?.depth_cm) > 0
          ? Number(carPlacement.depth_cm) / 100 * 0.9
          : depth * 0.9;
        const x0 = x - width / 2;
        const z0 = z - depth / 2;
        const pieces: Array<[number, number, number, number]> = [
          [width, (depth - openingDepth) / 2, x, z0 + (depth - openingDepth) / 4],
          [width, (depth - openingDepth) / 2, x, z0 + depth - (depth - openingDepth) / 4],
          [(width - openingWidth) / 2, openingDepth, x0 + (width - openingWidth) / 4, z],
          [(width - openingWidth) / 2, openingDepth, x0 + width - (width - openingWidth) / 4, z],
        ];
        // The shaft is one vertical Room, but every served storey has its
        // own floor slab around the same car-sized opening.  Reuse the exact
        // footprint at each elevation so upper-floor slabs cannot block the
        // car or leave a solid floor across the shaft.
        for (let storey = 1; storey <= 3; storey += 1) {
          const storeyElevation = (storey - 1) * roomHeight;
          pieces.forEach(([pieceWidth, pieceDepth, pieceX, pieceZ], pieceIndex) => {
            if (pieceWidth <= 0 || pieceDepth <= 0) return;
            const slab = new THREE.Mesh(new THREE.BoxGeometry(pieceWidth, slabThickness, pieceDepth), floorMaterial.clone());
            slab.position.set(pieceX, storeyElevation - slabThickness / 2, pieceZ);
            slab.userData = { id: `${roomId}.floor.f${storey}.${pieceIndex}`, simulationSurface: true, layer: "floor", debugSource: "elevator_shaft.floor", debugNodeId: roomId };
            slab.visible = layerVisibility.floor;
            scene.add(slab);
            collisionMeshes.push(slab);
          });
        }
      }
      if (semantic(nodeById.get(roomId)) === "elevator_shaft") {
        // The shaft is one vertical Room. Render its wall segments once per
        // served storey so every hall door cuts a real opening in the shell.
        for (let storey = 1; storey <= 3; storey += 1) {
          const elevation = (storey - 1) * roomHeight;
          addWallSegments(roomId, "north", false, elevation);
          addWallSegments(roomId, "east", false, elevation);
          addWallSegments(roomId, "south", false, elevation);
          addWallSegments(roomId, "west", false, elevation);
        }
      }
      {
        const highlight = new THREE.Mesh(
          new THREE.BoxGeometry(width, 0.04, depth),
          new THREE.MeshBasicMaterial({ color: 0x2563eb, transparent: true, opacity: 0.2, depthWrite: false, side: THREE.DoubleSide }),
        );
        highlight.userData.layer = "floor";
        highlight.position.set(x, 0.05 + elevation, z);
        highlight.visible = selectedId === roomId && layerVisibility.floor;
        scene.add(highlight);
        selectionVisualsRef.current.set(roomId, highlight);
      }
      if (semantic(nodeById.get(roomId)) !== "elevator_shaft") {
        addWallSegments(roomId, "north", selectedId === roomId);
        addWallSegments(roomId, "east", selectedId === roomId);
        addWallSegments(roomId, "south", selectedId === roomId);
        addWallSegments(roomId, "west", selectedId === roomId);
      }
      const label = makeLabel(nodeName(nodeById.get(roomId)) || roomId);
      label.layers.set(1);
      label.userData.layer = "labels";
      label.position.set(room.grid_x * cell + 0.12, 0.04 + elevation, room.grid_y * cell + 0.12);
      scene.add(label);
    });

    Object.entries(layout.doors).forEach(([doorId, door]) => {
      const room = layout.rooms[door.room_a_id];
      if (!room) return;
      const elevation = floorElevation(room);
      const horizontal = door.wall === "north" || door.wall === "south";
      const width = effectiveDoorWidthCells({ ...door, id: doorId } as RawNode) * cell;
      const axisStart = (horizontal ? room.grid_x : room.grid_y) * cell + door.offset_cells * cell;
      const boundary = (horizontal ? room.grid_y : room.grid_x) * cell + (door.wall === "south" || door.wall === "east" ? (horizontal ? room.depth_cells : room.width_cells) * cell : 0);
      const doorRoot = new THREE.Group();
      doorRoot.position.set(horizontal ? axisStart : boundary, elevation, horizontal ? boundary : axisStart);
      const hinge = new THREE.Group();
      hinge.position.set(0, 0, 0);
      // The panel geometry is already aligned with the wall plane: horizontal
      // doors use X as their span and vertical doors use Z.  The closed pose
      // is therefore the hinge identity.  Pre-rotating here made the stored
      // base quaternion an open pose, reversing is_open visual semantics.
      hinge.rotation.y = 0;
      const doorNode = nodeById.get(doorId);
      const isElevatorHallDoor = text(doorNode?.door_kind) === "elevator_hall";
      if (isElevatorHallDoor) {
        const material = new THREE.MeshStandardMaterial({ color: 0x0f766e, roughness: 0.65, metalness: 0.25 });
        const left = new THREE.Mesh(horizontal ? new THREE.BoxGeometry(width / 2 - 0.01, 2.1, 0.05) : new THREE.BoxGeometry(0.05, 2.1, width / 2 - 0.01), material);
        const right = left.clone();
        left.position.set(horizontal ? width * 0.25 : 0, 1.05, horizontal ? 0 : width * 0.25);
        right.position.set(horizontal ? width * 0.75 : 0, 1.05, horizontal ? 0 : width * 0.75);
        left.userData = { id: doorId, componentId: `${doorId}.left`, componentRole: "door", jointType: "prismatic", layer: "objects" };
        right.userData = { id: doorId, componentId: `${doorId}.right`, componentRole: "door", jointType: "prismatic", layer: "objects" };
        markElevatorMesh(left, "elevator_hall_door.left", doorId);
        markElevatorMesh(right, "elevator_hall_door.right", doorId);
        doorRoot.add(left, right);
        const composite = createComposite(doorId, doorRoot);
        // Each half-panel must clear the complete opening. Its centre starts
        // at one quarter of the opening and travels half the opening width.
        const halfPanelTravel = width / 2;
        attachPrismatic(composite, `${doorId}.left`, left, halfPanelTravel, horizontal ? new THREE.Vector3(-1, 0, 0) : new THREE.Vector3(0, 0, -1));
        attachPrismatic(composite, `${doorId}.right`, right, halfPanelTravel, horizontal ? new THREE.Vector3(1, 0, 0) : new THREE.Vector3(0, 0, 1));
        scene.add(doorRoot);
        // Hall doors are controlled by the elevator process. They are visual
        // and physical targets, but never direct user interaction targets.
        collisionMeshes.push(left, right);
        composites.push(composite);
        return;
      }
      const panel = new THREE.Mesh(horizontal ? new THREE.BoxGeometry(width, 2.1, 0.05) : new THREE.BoxGeometry(0.05, 2.1, width), new THREE.MeshStandardMaterial({ color: 0x0f766e, roughness: 0.7 }));
      panel.position.set(horizontal ? width / 2 : 0, 1.05, horizontal ? 0 : width / 2);
      panel.userData = { id: doorId, componentId: doorId, componentRole: "door", doorKind: "structural" };
      panel.userData.layer = "objects";
      hinge.add(panel);
      const hingePin = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 2.1, 10), new THREE.MeshStandardMaterial({ color: 0x334155 }));
      hingePin.position.y = 1.05;
      hinge.add(hingePin);
      doorRoot.add(hinge);
      scene.add(doorRoot);
      interactive.push(panel);
      // Keep the panel in the collision index, but mark it as a door so the
      // movement test can ignore it while its canonical is_open state is true.
      panel.userData.blocksNavigation = true;
      collisionMeshes.push(panel);
      const composite = createComposite(doorId, doorRoot);
      attachHinge(composite, doorId, panel, hinge, door.wall === "east" || door.wall === "north" ? -Math.PI / 2 : Math.PI / 2);
      composites.push(composite);
    });

    Object.entries(layout.objects).forEach(([objectId, item]) => {
      const room = layout.rooms[item.room_id];
      if (!room) return;
      const elevation = floorElevation(room);
      const node = nodeById.get(objectId);
      if (componentNodeIds.has(objectId)) return;
      const catalogEntry = catalogByType.get(semantic(node));
      const [catalogWidthCm, catalogDepthCm, catalogHeightCm] = catalogEntry
        ? [catalogEntry.width_cm, catalogEntry.depth_cm, catalogEntry.height_cm]
        : [item.width_cm ?? Math.max(1, item.width_cells * cell * 100), item.depth_cm ?? Math.max(1, item.depth_cells * cell * 100), item.height_cm ?? 80];
      // Layout dimensions are authoritative for authored compound assets such
      // as the elevator car. Catalog dimensions are only defaults.
      const widthCm = item.width_cm ?? catalogWidthCm;
      const depthCm = item.depth_cm ?? catalogDepthCm;
      const heightCm = item.height_cm ?? catalogHeightCm;
      const componentHost = componentHostById.get(objectId) ?? "";
      const componentRole = text(node?.component_role);
      const isGraphComponent = Boolean(componentHost);
      const width = (isGraphComponent ? item.width_cm ?? widthCm : widthCm) / 100;
      const depth = (isGraphComponent ? item.depth_cm ?? depthCm : depthCm) / 100;
      const height = (isGraphComponent ? item.height_cm ?? heightCm : heightCm) / 100;
      const placementMode = item.placement_mode;
      const parentMesh = item.parent_object_id ? objectMeshes.get(item.parent_object_id) : undefined;
      const parentHeight = parentMesh?.geometry.boundingBox ? parentMesh.geometry.boundingBox.max.y - parentMesh.geometry.boundingBox.min.y : 0.8;
      const baseHeight = placementMode === "contained"
          ? Math.max(0.02 + elevation, (parentMesh?.position.y ?? parentHeight + elevation) - parentHeight / 2 + 0.03)
          : elevation;
      let x = ((item.x_cm ?? ((room.grid_x + item.grid_x) * cell * 100)) / 100) + width / 2;
      let z = ((item.y_cm ?? ((room.grid_y + item.grid_y) * cell * 100)) / 100) + depth / 2;
      // The elevator car is positioned in the centre of its shaft Room. The
      // generated layout anchor is a grid cell origin, while the Room is the
      // authoritative spatial container.
      if (semantic(node) === "elevator" && item.room_id) {
        x = (room.grid_x + room.width_cells / 2) * cell;
        z = (room.grid_y + room.depth_cells / 2) * cell;
      }
      const hostRotation = Number(item.rotation_y ?? item.rotation ?? 0) * Math.PI / 2;
      const elevatorFloorThickness = semantic(node) === "elevator"
        ? Math.min(0.06, Math.min(width, depth) * 0.08)
        : 0;
      const worldPointForHost = (px: number, py: number, pz: number) =>
        new THREE.Vector3(px - x, py - (baseHeight + (item.z_cm ?? 0) / 100 + height / 2), pz - z)
          .applyAxisAngle(new THREE.Vector3(0, 1, 0), hostRotation)
          .add(new THREE.Vector3(x, baseHeight + (item.z_cm ?? 0) / 100 + height / 2, z));
      const selected = selectedId === objectId;
      const states = node?.states as Record<string, unknown> | undefined;
      const structureValue = node?.structure ?? node?.composition;
      const composition = structureValue && typeof structureValue === "object"
        ? structureValue as { components?: Array<Record<string, unknown>>; storage?: Record<string, unknown> }
        : null;
      const componentNodes = componentNodesByHost.get(objectId) ?? [];
      const isWasherHost = ["washer", "washing_machine"].includes(semantic(node));
      const storage = composition?.storage;
      const componentNodeForRole = (role: string, index?: number) => componentNodes.find((componentNode) => {
        const componentRole = text(componentNode.component_role);
        const componentType = semantic(componentNode);
        if (componentRole === role || componentType === role) {
          return index == null || Number(componentNode.component_index ?? 0) === index;
        }
        return false;
      });
      const hasFrontCavity = Boolean(composition?.storage || composition?.components?.some((part) => text(part.role || part.semantic_type) === "door"));
      const hasFrontDoor = Boolean(composition?.components?.some((part) => text(part.role || part.semantic_type) === "door"));
      const isDrawer = semantic(node) === "drawer" || componentRole === "drawer";
      const isClothes = semantic(node) === "clothes";
      const isLaundryDetergent = ["laundry_detergent", "detergent"].includes(semantic(node));
      const isComponentDoor = semantic(node) === "door" || componentRole === "door";
      const folded = Boolean(states?.folded);
      const objectMaterial = new THREE.MeshStandardMaterial({
        color: isLaundryDetergent ? 0xfacc15 : isDrawer ? 0x64748b : isClothes ? 0x94a3b8 : CATEGORY_COLORS[objectCategory(node)],
        transparent: !isLaundryDetergent,
        opacity: isLaundryDetergent ? 1 : 0.86,
        roughness: 0.72,
      });
      if (isLaundryDetergent) {
        objectMaterial.emissive = new THREE.Color(0x8a5a00);
        objectMaterial.emissiveIntensity = 0.12;
      }
      const isOpenFrame = ["rack", "shoe_rack", "drying_rack", "shelf", "resource_station"].includes(semantic(node));
      if (isOpenFrame) {
        objectMaterial.opacity = 0;
        objectMaterial.depthWrite = false;
      }
      if (hasFrontCavity || semantic(node) === "sink") {
        objectMaterial.opacity = 0;
        objectMaterial.depthWrite = false;
      }
      if (Boolean(states?.is_broken)) {
        objectMaterial.color = new THREE.Color(0x991b1b);
        objectMaterial.opacity = 0.72;
        objectMaterial.roughness = 0.95;
      }
      if (Boolean(states?.is_on) && ["light", "room_light"].includes(semantic(node))) {
        objectMaterial.emissive = new THREE.Color(0xffd166);
        objectMaterial.emissiveIntensity = 0.85;
      }
      if (isClothes) {
        // Clothing keeps one stable physical footprint. State is conveyed by
        // material cues so placement/collision boxes never jump when it is
        // folded, wet, or cleaned.
        if (states?.is_dirty) objectMaterial.color.setHex(0x8b6b52);
        if (states?.is_wet) {
          objectMaterial.color.setHex(0x38a3c7);
          objectMaterial.roughness = 0.3;
          objectMaterial.metalness = 0.05;
        }
        if (states?.folded) objectMaterial.emissive = new THREE.Color(0x334155);
      }
      const drawerFaceDepth = Math.min(0.035, depth * 0.08);
      const mesh = new THREE.Mesh(
        isComponentDoor
          ? new THREE.BoxGeometry(width * 0.92, height * 0.92, Math.min(0.04, depth * 0.1))
          : isDrawer
          ? new THREE.BoxGeometry(width * 0.94, height * 0.92, drawerFaceDepth)
          : isLaundryDetergent
            ? new THREE.SphereGeometry(Math.max(0.025, Math.min(width, depth, height) * 0.45), 16, 10)
          : isClothes
            ? new THREE.BoxGeometry(width, height, depth)
            : new THREE.BoxGeometry(width, height, depth),
        objectMaterial,
      );
      if (semantic(node) === "elevator" || objectId.startsWith("elevator_car_")) {
        markElevatorMesh(mesh, "elevator.catalog_anchor", objectId);
      }
      mesh.geometry.computeBoundingBox();
      mesh.position.set(
        x,
        baseHeight + (item.z_cm ?? 0) / 100 + height / 2 - elevatorFloorThickness,
        isComponentDoor || isDrawer ? z - depth / 2 + drawerFaceDepth / 2 : z,
      );
      if (semantic(node) === "elevator") {
        // Runtime current_height is the car floor height in metres. Store the
        // authored centre position once; the render loop adds the runtime
        // height to that centre so the car floor never drops below a level.
        mesh.userData.elevatorBaseY = mesh.position.y;
        mesh.userData.elevatorHeight = height;
        mesh.userData.elevatorRenderHeight = Number(states?.current_height ?? 0);
      }
      mesh.rotation.set(
        Number(item.rotation_x ?? 0) * Math.PI / 2,
        Number(item.rotation_y ?? item.rotation ?? 0) * Math.PI / 2,
        Number(item.rotation_z ?? 0) * Math.PI / 2,
      );
      // Runtime snapshots publish protocol-space transforms. Apply them only
      // when the node explicitly carries the protocol marker; editor-only
      // legacy layouts continue using their authored grid coordinates.
      const protocolTransform = node?.world_transform;
      if (node?.transform_space === "graphworld_z_up"
        && protocolTransform && typeof protocolTransform === "object"
        && placementMode !== "contained"
        // The elevator anchor is authored at its fixed shaft position. Its
        // vertical runtime state is applied exactly once to articulationRoot
        // below; applying the snapshot transform here would bake that height
        // into the anchor and then add current_height a second time.
        && semantic(node) !== "elevator") {
        applyProtocolToThree(mesh, protocolTransform as { position?: number[]; rotation?: number[]; scale?: number[] });
      }
      const parentSemantic = semantic(nodeById.get(text(item.parent_object_id)));
      const containedInAppliance = placementMode === "contained"
        && ["washer", "washing_machine", "dishwasher", "dryer", "clothesdryer"].includes(parentSemantic);
      if (containedInAppliance && parentMesh) {
        const siblings = Object.entries(layout.objects)
          .filter(([, candidate]) => candidate.placement_mode === "contained" && candidate.parent_object_id === item.parent_object_id)
          .map(([id]) => id)
          .sort();
        const contentIndex = Math.max(0, siblings.indexOf(objectId));
        const parentSize = parentMesh.geometry.boundingBox?.getSize(new THREE.Vector3()) ?? new THREE.Vector3(0.6, 0.85, 0.65);
        const localOffset = new THREE.Vector3(
          contentIndex % 2 === 0 ? -0.1 : 0.1,
          -parentSize.y * 0.08 + Math.floor(contentIndex / 2) * 0.08,
          -parentSize.z * 0.08,
        ).applyAxisAngle(new THREE.Vector3(0, 1, 0), parentMesh.rotation.y);
        mesh.position.copy(parentMesh.position).add(localOffset);
        if (semantic(node) === "clothes") mesh.scale.setScalar(0.35);
      }
      mesh.userData = { id: objectId };
      const declaredCapabilities = Array.isArray(node?.capabilities) ? node?.capabilities.map(String) : [];
      const declaredActions = Array.isArray(node?.interactive_actions) ? node?.interactive_actions.map(String) : [];
      const componentRoleValue = text(node?.component_role).toLowerCase();
      const structuralNode = ["room", "floor", "wall", "structure"].includes(text(node?.node_type).toLowerCase());
      const nonPickableComponent = ["storage_slot", "drawer", "door", "button", "hinge"].includes(componentRoleValue)
        || Boolean(node?.can_contain)
        || declaredCapabilities.map((value) => value.toLowerCase()).includes("receptacle");
      mesh.userData.pickable = declaredCapabilities.includes("pickable")
        && !structuralNode
        && !nonPickableComponent
        && !new Set(["chair", "seat", "rack", "shoe_rack", "open_shelf", "shelf"]).has(semantic(node));
      mesh.userData.canReceive = Boolean(node?.can_support || node?.can_contain)
        || declaredCapabilities.includes("support_surface")
        || declaredCapabilities.includes("receptacle");
      const surfaceSpec = node?.surface_spec as Record<string, unknown> | undefined;
      mesh.userData.surfaceSizeCm = surfaceSpec
        ? [Number(surfaceSpec.width_cm) || 0, Number(surfaceSpec.depth_cm) || 0]
        : undefined;
      mesh.userData.surfaceGridCm = surfaceSpec ? Number(surfaceSpec.grid_size_cm) || 1 : 1;
      mesh.userData.layer = "objects";
      mesh.castShadow = true;
      const initiallyContained = placementMode === "contained" || text(node?.storage_mode).toLowerCase() === "hidden";
      if (initiallyContained) {
        mesh.visible = false;
        mesh.userData.collisionEnabled = false;
      }
      const isElevatorObject = semantic(node) === "elevator"
        || objectCategory(node) === "elevator"
        || objectId.startsWith("elevator_car_")
        || (Array.isArray(node?.capabilities)
          && node.capabilities.some((value) => String(value).toLowerCase() === "transport_device"));
      // The elevator's catalog dimensions are only an identity/layout
      // fallback. Its visible and collidable geometry is the articulated
      // cabin created below; never register the solid catalog box itself.
      if (!isElevatorObject && !initiallyContained) {
        scene.add(mesh);
        interactive.push(mesh);
        collisionMeshes.push(mesh);
      } else if (!isElevatorObject) {
        // Keep contained roots in the object registry for state-driven
        // reappearance, but do not expose a hidden load to picking or physics.
        scene.add(mesh);
      }
      // Open frames, cavities, sinks and other transparent proxies are only
      // semantic/visual anchors. Their solid catalog box must not become an
      // invisible wall in Rapier; their real shell/parts are registered below.
      if (isOpenFrame || hasFrontCavity || semantic(node) === "sink") {
        mesh.userData.collisionEnabled = false;
      }
      objectMeshes.set(objectId, mesh);
      const composite = createComposite(objectId, mesh);
      composites.push(composite);
      if (isElevatorObject) {
        // The catalog box is only the object anchor.  The visible elevator
        // car is the hollow articulated shell built below; do not render the
        // generic solid proxy on top of it.
        // Keep the graph/layout anchor for transforms and interaction identity,
        // but never use it as the visual parent. Children of an invisible
        // Three.js Object are invisible too, so the cabin gets its own Group.
        const articulationRoot = new THREE.Group();
        articulationRoot.name = `${objectId}.articulation_root`;
        // The articulation root is the cabin floor top-center, not the
        // catalog box center. current_height therefore directly equals the
        // world height of the cabin floor top.
        articulationRoot.position.copy(mesh.position);
        articulationRoot.position.y -= height / 2 - elevatorFloorThickness;
        articulationRoot.quaternion.copy(mesh.quaternion);
        articulationRoot.scale.copy(mesh.scale);
        articulationRoot.userData = { id: objectId, componentRole: "articulation_root", layer: "objects" };
        // The articulation root is a transform-only Group. It has no geometry
        // and must never be reported as the source of a collider. Individual
        // cabin meshes carry their own debugSource below.
        scene.add(articulationRoot);
        composite.host = articulationRoot;
        mesh.userData.elevatorVisualRoot = articulationRoot;
        // The catalog mesh is only an authoring/layout anchor. It must not
        // remain in the scene graph: leaving this solid proxy attached would
        // render an extra outer shell around the articulated cabin.
        mesh.removeFromParent();
        mesh.visible = false;
        mesh.userData.collisionEnabled = false;
        const carMaterial = new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.55, metalness: 0.3 });
        const cabinWidth = width * 0.9;
        const cabinDepth = depth * 0.9;
        const cabinHeight = height * 0.96;
        const wallThickness = Math.min(0.06, Math.min(cabinWidth, cabinDepth) * 0.08);
      const carFloor = new THREE.Mesh(new THREE.BoxGeometry(cabinWidth, wallThickness, cabinDepth), carMaterial);
      carFloor.position.set(0, -wallThickness / 2, 0);
      carFloor.userData = { id: objectId, componentRole: "elevator_cabin", layer: "objects" };
      markElevatorMesh(carFloor, "elevator.car_floor", objectId);
        const carRoof = new THREE.Mesh(new THREE.BoxGeometry(cabinWidth, wallThickness, cabinDepth), carMaterial);
      carRoof.position.set(0, cabinHeight - wallThickness / 2, 0);
      carRoof.userData = { id: objectId, componentRole: "elevator_cabin", layer: "objects" };
      markElevatorMesh(carRoof, "elevator.car_roof", objectId);
        const carLeftWall = new THREE.Mesh(new THREE.BoxGeometry(wallThickness, cabinHeight, cabinDepth), carMaterial);
        const carRightWall = new THREE.Mesh(new THREE.BoxGeometry(wallThickness, cabinHeight, cabinDepth), carMaterial);
        const carBackWall = new THREE.Mesh(new THREE.BoxGeometry(cabinWidth, cabinHeight, wallThickness), carMaterial);
      carLeftWall.position.set(-cabinWidth / 2 + wallThickness / 2, cabinHeight / 2, 0);
      carRightWall.position.set(cabinWidth / 2 - wallThickness / 2, cabinHeight / 2, 0);
      carBackWall.position.set(0, cabinHeight / 2, cabinDepth / 2 - wallThickness / 2);
        [carLeftWall, carRightWall, carBackWall].forEach((wall) => {
          wall.userData = { id: objectId, componentRole: "elevator_cabin", layer: "objects" };
        });
        markElevatorMesh(carLeftWall, "elevator.left_wall", objectId);
        markElevatorMesh(carRightWall, "elevator.right_wall", objectId);
        markElevatorMesh(carBackWall, "elevator.back_wall", objectId);
        const doorMaterial = new THREE.MeshStandardMaterial({ color: 0x0f766e, roughness: 0.45, metalness: 0.35 });
        // The doors cover the complete clear opening between the cabin side
        // walls and from the floor top to the roof bottom.  Using a fraction
        // of cabinHeight here leaves visible gaps and, more importantly,
        // leaves the matching collider blocking the entrance.
        const carDoorWidth = Math.max(0.01, cabinWidth / 2 - wallThickness);
        const carDoorHeight = Math.max(0.01, cabinHeight - wallThickness);
        const carDoorLeft = new THREE.Mesh(new THREE.BoxGeometry(carDoorWidth, carDoorHeight, wallThickness), doorMaterial);
        const carDoorRight = new THREE.Mesh(new THREE.BoxGeometry(carDoorWidth, carDoorHeight, wallThickness), doorMaterial);
      carDoorLeft.position.set(-cabinWidth / 4, carDoorHeight / 2, -cabinDepth / 2 + wallThickness / 2);
      carDoorRight.position.set(cabinWidth / 4, carDoorHeight / 2, -cabinDepth / 2 + wallThickness / 2);
      carDoorLeft.userData = { id: objectId, componentId: `${objectId}.car_door_left`, componentRole: "door", jointType: "prismatic", layer: "objects" };
      carDoorRight.userData = { id: objectId, componentId: `${objectId}.car_door_right`, componentRole: "door", jointType: "prismatic", layer: "objects" };
      markElevatorMesh(carDoorLeft, "elevator.car_door_left", objectId);
      markElevatorMesh(carDoorRight, "elevator.car_door_right", objectId);
        const buttonPanel = new THREE.Group();
        // The panel is mounted on the cabin's left interior wall, beside the
        // doorway, rather than on the right or in the centre of the car.
        const panelWidth = 0.42;
        // Rotation puts the panel's long axis along local Z.  Keep its whole
        // footprint behind the door plane so the panel cannot intersect the
        // sliding leaves when they are closed.
        const panelFrontClearance = 0.05;
        buttonPanel.position.set(
          -cabinWidth / 2 + wallThickness + 0.04,
          cabinHeight * 0.52,
          -cabinDepth / 2 + wallThickness + panelWidth / 2 + panelFrontClearance,
        );
        buttonPanel.rotation.y = Math.PI / 2;
      buttonPanel.userData = { id: objectId, componentId: `${objectId}.floor_buttons`, componentRole: "floor_button_panel", layer: "objects" };
      markElevatorMesh(buttonPanel, "elevator.control_panel", objectId);
        const panel = new THREE.Mesh(
          new THREE.BoxGeometry(panelWidth, Math.min(0.92, cabinHeight * 0.72), 0.045),
          new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.5, metalness: 0.25 }),
        );
        panel.position.z = -0.025;
      panel.userData = { id: objectId, componentId: `${objectId}.floor_buttons`, componentRole: "floor_button_panel", layer: "objects" };
      markElevatorMesh(panel, "elevator.control_panel_mesh", objectId);
        buttonPanel.add(panel);
        const buttonMaterial = new THREE.MeshStandardMaterial({ color: 0xf59e0b, emissive: 0x5b3a00, emissiveIntensity: 0.7 });
        const buttonIds = ["f1", "f2", "f3", "open", "close"];
        buttonIds.forEach((suffix, index) => {
          const isBottom = index >= 3;
          const button = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 0.024, 16), buttonMaterial.clone());
          button.rotation.x = Math.PI / 2;
          const col = isBottom ? index - 3 : 0;
          // Keep floor order semantic and readable: 1F at the bottom,
          // 2F in the middle, 3F at the top. The door controls share the
          // lower part of the panel, but stay within its visible bounds.
          const floorButtonY = cabinHeight * 0.10 + index * 0.14;
          const doorButtonY = -cabinHeight * 0.12;
          button.position.set(isBottom ? (col - 0.5) * 0.14 : 0, isBottom ? doorButtonY : floorButtonY, 0);
          button.userData = { id: objectId, componentId: `${objectId}_${suffix}_button`, componentRole: isBottom ? `${suffix}_button` : "floor_button", layer: "objects" };
          markElevatorMesh(button, `elevator.button.${suffix}`, objectId);
          elevatorButtonMeshes.set(`${objectId}_${suffix}_button`, button);
          buttonPanel.add(button);
          // Labels are visual children of the button PartTree node. They do
          // not enter the collision index and therefore follow the cabin,
          // door animation, and editor transforms as one unit.
          const buttonLabel = suffix === "open" ? "开" : suffix === "close" ? "关" : suffix.slice(1);
          const label = makeLabel(buttonLabel, "#0f172a");
          label.name = `${objectId}.${suffix}.label`;
          label.position.set(0, 0, -0.035);
          label.scale.set(0.09, 0.065, 1);
          button.add(label);
          interactive.push(button);
        });
        composite.host.add(carFloor, carRoof, carLeftWall, carRightWall, carBackWall, carDoorLeft, carDoorRight, buttonPanel);
        // Register the visible control panel explicitly. It is part of the
        // cabin collision set, not a standalone static scene collider.
        elevatorCollisionMeshes.add(panel);
        buttonPanel.traverse((part) => {
          if (part instanceof THREE.Mesh && part.userData.collisionEnabled !== false) {
            elevatorCollisionMeshes.add(part);
          }
        });
        articulationRoot.traverse((part) => {
          if (part !== articulationRoot && (part instanceof THREE.Mesh || part instanceof THREE.Group)) {
            logElevatorMesh(part, "Elevator mesh created");
          }
        });
        // The cabin doors are on the face toward the hall (negative local Z)
        // and split sideways along the local X axis.
        // Each leaf starts with its inner edge at the cabin centre. To clear
        // the entire opening, its centre must travel one full half-width of
        // the cabin, matching the hall-door travel. A quarter-width travel
        // leaves half of each leaf across the doorway.
        const carDoorTravel = cabinWidth / 2;
        attachPrismatic(composite, `${objectId}.car_door_left`, carDoorLeft, carDoorTravel, new THREE.Vector3(-1, 0, 0));
        attachPrismatic(composite, `${objectId}.car_door_right`, carDoorRight, carDoorTravel, new THREE.Vector3(1, 0, 0));
        // Cabin doors are controlled by the elevator process as well. The
        // floor buttons remain interactive, while the door panels do not.
        collisionMeshes.push(carFloor, carRoof, carLeftWall, carRightWall, carBackWall, carDoorLeft, carDoorRight);
        [carFloor, carRoof, carLeftWall, carRightWall, carBackWall, carDoorLeft, carDoorRight]
          .forEach((part) => elevatorCollisionMeshes.add(part));
      }
      if (isOpenFrame) {
        const frameMaterial = new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.72 });
        const rail = Math.min(0.045, Math.min(width, depth) * 0.08);
        const storage = composition?.storage ?? {};
        const shelfCount = Math.max(1, Number(storage.levels) || (semantic(node) === "drying_rack" ? 3 : 3));
        const columns = Math.max(1, Number(storage.columns) || 1);
          const capacity = Number(node?.max_items) || 8;
          const requiredCapabilities = Array.isArray(node?.accepted_capabilities)
            ? node.accepted_capabilities.map(String)
            : [];
        for (let level = 0; level < shelfCount; level += 1) {
          const levelY = mesh.position.y - height / 2 + (height * (level + 0.5)) / shelfCount;
          const shelfDepth = semantic(node) === "drying_rack" ? depth * 0.82 : depth * 0.72;
          const shelf = new THREE.Mesh(new THREE.BoxGeometry(width * 0.88, rail, shelfDepth), frameMaterial.clone());
          shelf.position.copy(worldPointForHost(x, levelY, z));
          shelf.rotation.y = hostRotation;
          shelf.userData = {
            id: `${objectId}_slot_l${level + 1}_c1`,
            hostId: objectId,
            componentId: `${objectId}_slot_l${level + 1}_c1`,
            componentRole: "storage_slot",
            capabilities: ["place_target"],
            maxCapacity: capacity,
            requiresContainedCapabilities: requiredCapabilities,
          };
          scene.add(shelf);
          interactive.push(shelf);
          attachPart(composite, shelf);
        }
        // An open rack needs a pair of depth-direction uprights for every
        // column boundary. For n columns this is 2(n + 1) posts, so the
        // frame remains stable instead of balancing on two front rods.
        for (let boundary = 0; boundary <= columns; boundary += 1) {
          const postX = x - width * 0.44 + (width * 0.88 * boundary) / columns;
          for (const postZ of [z - depth * 0.36, z + depth * 0.36]) {
            const post = new THREE.Mesh(new THREE.BoxGeometry(rail, height, rail), frameMaterial.clone());
            post.position.copy(worldPointForHost(postX, mesh.position.y, postZ));
            post.rotation.y = hostRotation;
            scene.add(post);
            attachPart(composite, post);
          }
        }
      }
      if (hasFrontCavity || semantic(node) === "sink") {
        const shellMaterial = new THREE.MeshStandardMaterial({ color: CATEGORY_COLORS[objectCategory(node)], roughness: 0.78, metalness: 0.04 });
        const addShellPanel = (panelWidth: number, panelHeight: number, panelDepth: number, px: number, py: number, pz: number) => {
          const panel = new THREE.Mesh(new THREE.BoxGeometry(panelWidth, panelHeight, panelDepth), shellMaterial.clone());
          panel.position.copy(worldPointForHost(px, py, pz));
          panel.rotation.y = hostRotation;
          panel.castShadow = true;
          panel.receiveShadow = true;
          panel.userData.layer = "objects";
          scene.add(panel);
          attachPart(composite, panel);
        };
        const wall = Math.min(0.06, Math.max(0.025, Math.min(width, depth) * 0.08));
        const openFront = hasFrontCavity;
        addShellPanel(width, wall, depth, x, mesh.position.y - height / 2 + wall / 2, z);
        if (semantic(node) !== "sink") {
          addShellPanel(width, wall, depth, x, mesh.position.y + height / 2 - wall / 2, z);
        }
        addShellPanel(wall, height, depth, x - width / 2 + wall / 2, mesh.position.y, z);
        addShellPanel(wall, height, depth, x + width / 2 - wall / 2, mesh.position.y, z);
        addShellPanel(width, height, wall, x, mesh.position.y, z + depth / 2 - wall / 2);
        if (!openFront) addShellPanel(width, height, wall, x, mesh.position.y, z - depth / 2 + wall / 2);
        if (semantic(node) === "sink") {
          const basinWidth = width * 0.72;
          const basinDepth = depth * 0.62;
          const basinWall = Math.min(0.045, wall);
          const rimY = mesh.position.y + height / 2 - basinWall / 2;
          const basinY = mesh.position.y + height * 0.05;
          const basinSideHeight = Math.max(basinWall, rimY - basinY);
          const basinBottom = new THREE.Mesh(
            new THREE.BoxGeometry(basinWidth, basinWall, basinDepth),
            new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.34, metalness: 0.12 }),
          );
          basinBottom.position.set(x, basinY, z);
          basinBottom.userData.layer = "objects";
          scene.add(basinBottom);
          attachPart(composite, basinBottom);
          const basinMaterial = new THREE.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.32, metalness: 0.16 });
          const basinSides = [
            { w: basinWidth, d: basinWall, px: x, pz: z - basinDepth / 2 + basinWall / 2 },
            { w: basinWidth, d: basinWall, px: x, pz: z + basinDepth / 2 - basinWall / 2 },
            { w: basinWall, d: basinDepth, px: x - basinWidth / 2 + basinWall / 2, pz: z },
            { w: basinWall, d: basinDepth, px: x + basinWidth / 2 - basinWall / 2, pz: z },
          ];
          basinSides.forEach((side) => {
            const basinSide = new THREE.Mesh(new THREE.BoxGeometry(side.w, basinSideHeight, side.d), basinMaterial.clone());
            basinSide.position.copy(worldPointForHost(side.px, basinY + basinSideHeight / 2, side.pz));
            basinSide.userData.layer = "objects";
            basinSide.rotation.y = hostRotation;
            scene.add(basinSide);
            attachPart(composite, basinSide);
          });
          addShellPanel(basinWidth, basinWall, basinWall, x, rimY, z - basinDepth / 2);
          addShellPanel(basinWidth, basinWall, basinWall, x, rimY, z + basinDepth / 2);
          addShellPanel(basinWall, basinWall, basinDepth, x - basinWidth / 2, rimY, z);
          addShellPanel(basinWall, basinWall, basinDepth, x + basinWidth / 2, rimY, z);
        }
      }
      if (visualCuesOf(node).has("emissive") || ["light", "room_light"].includes(semantic(node))) {
        const lamp = new THREE.PointLight(0xffe6a3, Boolean(states?.is_on) ? 2.2 : 0, 5.5, 1.8);
        // All assets use the same local origin/height convention.  A
        // wall-mounted placement changes authored layout coordinates, not
        // the object's transform or its light anchor.
        lamp.position.set(0, Math.max(0.15, height / 2), 0);
        mesh.add(lamp);
        lightMeshes.set(objectId, lamp);
      }
      if (semantic(node) === "sink") {
        // `water_level` is the canonical 0..100 quantity. `fill_level` was
        // used by older scene exports as a normalized 0..1 value; convert it
        // only at this compatibility boundary.
        const legacyFill = states?.fill_level == null ? null : Number(states.fill_level);
        const initialFill = Number(states?.water_level ?? (legacyFill == null ? (states?.has_water ? 100 : 0) : legacyFill * 100));
        const drain = new THREE.Mesh(
          new THREE.CylinderGeometry(0.045, 0.045, 0.018, 16),
          new THREE.MeshStandardMaterial({ color: 0x475569, metalness: 0.65, roughness: 0.32 }),
        );
        drain.position.set(width * 0.28, height * 0.18, -depth / 2 - 0.018);
        drain.rotation.x = Math.PI / 2;
        drain.userData = { id: objectId, componentId: `${objectId}_drain`, componentRole: "sink_drain" };
        attachLocalPart(composite, drain);
        interactive.push(drain);
        const water = new THREE.Mesh(
          new THREE.BoxGeometry(width * 0.62, Math.max(0.02, height * 0.45), depth * 0.5),
          new THREE.MeshPhysicalMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.72, roughness: 0.12, metalness: 0.08 }),
        );
        water.position.set(0, height * 0.275, 0);
        water.userData = { layer: "objects" };
        water.visible = initialFill > 0;
        mesh.add(water);
        waterMeshes.set(objectId, water);
        animatedMeshes.set(objectId, { mesh: water, base: water.position.clone(), baseRotation: water.rotation.clone() });
        const faucetNode = faucetsBySink.get(objectId)?.[0];
        if (faucetNode) {
          const faucetGroup = new THREE.Group();
          faucetGroup.position.set(0, height * 0.38, depth * 0.34);
          faucetGroup.userData = { id: text(faucetNode.id), hostId: objectId, componentId: text(faucetNode.id), componentRole: "faucet" };
          const metal = new THREE.MeshStandardMaterial({ color: 0xcbd5e1, metalness: 0.82, roughness: 0.22 });
          const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.022, height * 0.34, 12), metal);
          stem.position.y = height * 0.17;
          const spout = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.018, depth * 0.32, 12), metal);
          spout.rotation.x = Math.PI / 2;
          spout.position.set(0, height * 0.32, -depth * 0.12);
          stem.userData = { id: text(faucetNode.id), hostId: objectId, componentId: text(faucetNode.id), componentRole: "faucet" };
          spout.userData = { id: text(faucetNode.id), hostId: objectId, componentId: text(faucetNode.id), componentRole: "faucet" };
          faucetGroup.add(stem, spout);
          attachLocalPart(composite, faucetGroup);
          interactive.push(stem, spout);
        }
      }
      const nodeCues = visualCuesOf(node);
      if (nodeCues.has("running_pulse") || nodeCues.has("airflow") || Boolean(states?.is_running)
        || ["washer", "washing_machine"].includes(semantic(node))
        || (Boolean(states?.is_on) && ["fan", "ceiling_fan", "ventilator"].includes(semantic(node)))) {
        animatedMeshes.set(objectId, { mesh, base: mesh.position.clone(), baseRotation: mesh.rotation.clone() });
      }
      if (node?.physics_state === "falling") {
        animatedMeshes.set(objectId, { mesh, base: mesh.position.clone(), baseRotation: mesh.rotation.clone() });
      }
      if (Boolean(states?.is_wet) || semantic(node) === "clothes") {
        const dropletMaterial = new THREE.MeshStandardMaterial({ color: 0x38bdf8, emissive: 0x0369a1, emissiveIntensity: 0.25, transparent: true, opacity: 0.82, roughness: 0.25 });
        const dropletRadius = Math.max(0.012, Math.min(width, depth) * 0.035);
        [[-0.28, 0.2], [0.05, -0.16], [0.31, 0.08], [-0.12, -0.3], [0.24, 0.32]].forEach(([ox, oz], index) => {
          const droplet = new THREE.Mesh(new THREE.SphereGeometry(dropletRadius, 8, 6), dropletMaterial.clone());
          droplet.position.set(mesh.position.x + ox * width, mesh.position.y + height * 0.25, mesh.position.z + oz * depth);
          scene.add(droplet);
          effectMeshes.push({ mesh: droplet, host: mesh, nodeId: objectId, kind: "droplet", offset: new THREE.Vector3(ox * width, height * 0.25, oz * depth), phase: index * 1.7 });
        });
        if (semantic(node) === "clothes") {
          const stainMaterial = new THREE.MeshStandardMaterial({ color: 0x79513b, roughness: 0.96, transparent: true, opacity: 0.88 });
          [[-0.22, 0.18], [0.16, 0.04], [0.05, -0.24]].forEach(([ox, oy], index) => {
            const stain = new THREE.Mesh(new THREE.SphereGeometry(Math.max(0.018, width * (0.045 + index * 0.008)), 7, 5), stainMaterial.clone());
            stain.scale.set(1.3, 0.38, 0.12);
            stain.position.set(mesh.position.x + ox * width, mesh.position.y + oy * height, mesh.position.z - depth / 2 - 0.006);
            scene.add(stain);
            effectMeshes.push({ mesh: stain, host: mesh, nodeId: objectId, kind: "stain", offset: new THREE.Vector3(ox * width, oy * height, -depth / 2 - 0.006), phase: index });
          });
        }
        if (states?.cycle_remaining != null) {
          const bubbleMaterial = new THREE.MeshStandardMaterial({ color: 0xfacc15, emissive: 0xca8a04, emissiveIntensity: 0.35, transparent: true, opacity: 0.7 });
          [0.22, 0.5, 0.78].forEach((offset, index) => {
            const bubble = new THREE.Mesh(new THREE.SphereGeometry(Math.max(0.014, width * 0.045), 8, 6), bubbleMaterial.clone());
            const local = new THREE.Vector3((offset - 0.5) * width, height * 0.62, 0);
            bubble.position.copy(mesh.position).add(local);
            scene.add(bubble);
            effectMeshes.push({ mesh: bubble, host: mesh, nodeId: objectId, kind: "drying", offset: local, phase: index * 1.3 });
          });
        }
      }
      if (String(states?.temperature || "").toLowerCase() === "hot") {
        const steamMaterial = new THREE.MeshStandardMaterial({ color: 0xf8fafc, transparent: true, opacity: 0.42, roughness: 0.2 });
        [0.3, 0.6].forEach((offset, index) => {
          const puff = new THREE.Mesh(new THREE.SphereGeometry(Math.max(0.018, width * 0.06), 8, 6), steamMaterial.clone());
          const local = new THREE.Vector3((offset - 0.5) * width, height * 0.68, 0);
          puff.position.copy(mesh.position).add(local);
          scene.add(puff);
          effectMeshes.push({ mesh: puff, host: mesh, nodeId: objectId, kind: "steam", offset: local, phase: index * 1.8 });
        });
      }
      if (Boolean(states?.is_broken)) {
        const brokenOverlay = new THREE.Mesh(
          new THREE.BoxGeometry(width, height, depth),
          new THREE.MeshBasicMaterial({ color: 0xef4444, wireframe: true, transparent: true, opacity: 0.9, depthTest: false }),
        );
        brokenOverlay.position.copy(mesh.position);
        scene.add(brokenOverlay);
        effectMeshes.push({ mesh: brokenOverlay, host: mesh, nodeId: objectId, kind: "broken", offset: new THREE.Vector3(), phase: 0 });
      }
      {
        // The selection frame must describe the rendered root geometry, not
        // the catalog envelope. Composite assets and stateful items (notably
        // folded clothes) intentionally render at a different size.
        mesh.geometry.computeBoundingBox();
        const renderedSize = mesh.geometry.boundingBox?.getSize(new THREE.Vector3())
          ?? new THREE.Vector3(width, height, depth);
        const highlight = new THREE.Mesh(
          new THREE.BoxGeometry(
            Math.max(0.001, renderedSize.x),
            Math.max(0.001, renderedSize.y),
            Math.max(0.001, renderedSize.z),
          ),
          new THREE.MeshBasicMaterial({ color: 0x2563eb, wireframe: true, transparent: true, opacity: 0.95, depthWrite: false }),
        );
        // Keep the editor bounds in the object's transform hierarchy.  A
        // separate world-space mesh becomes stale when the root or its
        // articulation is moved/rotated and leaves a ghost at the old pose.
        highlight.position.set(0, 0, 0);
        highlight.visible = selected;
        mesh.add(highlight);
        selectionVisualsRef.current.set(objectId, highlight);
      }
      const label = makeLabel(nodeName(node) || objectId, "#0f172a");
      label.layers.set(1);
      label.userData.layer = "labels";
      label.position.set(x, baseHeight + (item.z_cm ?? 0) / 100 + height + 0.05, z - depth / 2);
      scene.add(label);
      objectLabels.set(objectId, label);

      const componentMaterial = (role: string) => new THREE.MeshStandardMaterial({
        color: role.includes("button") || role.includes("flush") ? 0xf59e0b : role.includes("drawer") ? 0x0f766e : 0x334155,
        transparent: true,
        opacity: 0.92,
        roughness: 0.62,
      });
      const addComponentMesh = (role: string, face: string, anchor: number[], geometry: THREE.BufferGeometry, position: THREE.Vector3, componentId = `${objectId}_${role}`) => {
        const component = new THREE.Mesh(geometry, componentMaterial(role));
        // Component positions are authored in world coordinates here.  The
        // previous code passed them through worldPointForHost a second time,
        // applying the host translation twice and moving hinges/buttons away
        // from their declared anchors (often into the asset centre).
        component.position.copy(position);
        component.rotation.y = hostRotation;
        component.userData = { id: objectId, componentId, componentRole: role, componentFace: face };
        componentVisuals.set(componentId, component);
        component.castShadow = true;
        scene.add(component);
        interactive.push(component);
        if (role !== "door") {
          attachPart(composite, component);
        }
        return component;
      };
      composition?.components?.forEach((component) => {
        const role = text(component.role || component.semantic_type || "component");
        // Elevator cabins have their own paired sliding-door articulation
        // below.  Ignore legacy generic hinge/door composition entries so an
        // obsolete single green hinged panel cannot be rendered in the cabin.
        if (semantic(node) === "elevator" && (role === "door" || role === "hinge")) return;
        // Old snapshots stored device start buttons on the front. Treat their
        // semantic role as authoritative so existing versions get the fixed
        // top mounting without requiring a data migration.
        const hasDeviceDoor = composition?.components?.some((entry) => text(entry.role || entry.semantic_type) === "door");
        const face = role.includes("button") && hasDeviceDoor ? "top" : text(component.mount_face || "front");
        const anchor = Array.isArray(component.anchor) ? component.anchor.map(Number) : [0.5, 0.5, 0];
        const ax = Math.max(0, Math.min(1, anchor[0] ?? 0.5));
        const ay = Math.max(0, Math.min(1, anchor[1] ?? 0.5));
        const az = Math.max(0, Math.min(1, anchor[2] ?? 0));
        if (role.includes("button") || role.includes("knob")) {
          const buttonSize = Math.max(0.045, Math.min(width, depth) * 0.11);
          const buttonGeometry = new THREE.BoxGeometry(buttonSize, buttonSize, buttonSize * 0.5);
          const isDeviceControl = role.includes("button") && hasDeviceDoor;
          const buttonLocalZ = isDeviceControl ? -depth * 0.34 : (ay - 0.5) * depth;
          const buttonPosition = face === "top"
            ? new THREE.Vector3(x + (ax - 0.5) * width, mesh.position.y + height / 2 + buttonSize / 2, z + buttonLocalZ)
            : new THREE.Vector3(x + (ax - 0.5) * width, mesh.position.y + (ay - 0.5) * height, z - depth / 2 - buttonSize / 3);
          const buttonNode = componentNodeForRole(role) ?? componentNodes.find((entry) => semantic(entry) === "button");
          addComponentMesh(role, face, [ax, ay, az], buttonGeometry, buttonPosition, text(buttonNode?.id) || `${objectId}_${role}`);
        } else if (role === "hinge") {
          const hingeGeometry = new THREE.CylinderGeometry(Math.max(0.018, Math.min(width, height) * 0.035), Math.max(0.018, Math.min(width, height) * 0.035), Math.max(0.12, height * 0.55), 10);
          const hingePosition = new THREE.Vector3(
            x + (ax >= 0.5 ? width / 2 : -width / 2),
            mesh.position.y + (ay - 0.5) * height,
            z - depth / 2 - 0.024,
          );
          const hinge = addComponentMesh(role, face, [ax, ay, az], hingeGeometry, hingePosition);
          // CylinderGeometry is already aligned to Y, so the hinge pin stays
          // vertical (the door's rotation axis) instead of pointing along Z.
        } else if (role === "door") {
          const faceInset = Math.min(0.025, Math.min(width, height) * 0.035);
          const doorWidth = Math.max(0.08, width - faceInset * 2);
          // A host with a front drawer reserves the lower front band for that
          // drawer. The door remains a normal reusable component, simply
          // sized to the free opening rather than covering the drawer.
          const drawerCount = isWasherHost
            ? Math.max(0, Number(storage?.drawer_count) || 1)
            : 0;
          const doorHeight = Math.max(0.12, height * (drawerCount > 0 ? 0.76 : 0.92) - faceInset * 2);
          const doorCenterY = drawerCount > 0
            // Keep the lower edge at the original door sill; only the upper
            // edge moves down to make room for the washer drawer.
            ? mesh.position.y - height * 0.08
            : mesh.position.y;
          const doorGeometry = face === "top"
            ? new THREE.BoxGeometry(doorWidth, 0.025, Math.max(0.08, depth - faceInset * 2))
            : new THREE.BoxGeometry(doorWidth, doorHeight, 0.035);
          if (face === "top") {
            const topDoor = addComponentMesh(role, face, [ax, ay, az], doorGeometry, new THREE.Vector3(x, mesh.position.y + height / 2 + 0.018, z));
            // A top-mounted appliance lid has no articulated pivot in the
            // authored structure yet, but it is still real geometry and must
            // participate in collision and composite transforms.
            attachPart(composite, topDoor);
            collisionMeshes.push(topDoor);
          } else {
            // Device doors rotate around a vertical hinge on their side edge.
            // The old implementation rotated the panel around its own centre,
            // which made the hinge appear horizontal and detached from the box.
          const hingeSpec = composition?.components?.find((item) => text(item.role || item.semantic_type) === "hinge");
          const hingeAnchorX = Array.isArray(hingeSpec?.anchor) ? Number(hingeSpec.anchor[0]) : 0.08;
          const rightHinged = hingeAnchorX >= 0.5;
            const pivot = new THREE.Group();
            pivot.position.copy(worldPointForHost(x + (rightHinged ? width / 2 : -width / 2), doorCenterY, z - depth / 2 - 0.02));
            pivot.rotation.y = hostRotation;
            const doorNode = componentNodeForRole("door");
            const componentId = text(doorNode?.id) || `${objectId}_${role}`;
            const panel = new THREE.Mesh(doorGeometry, componentMaterial(role));
            panel.position.set(rightHinged ? -doorWidth / 2 : doorWidth / 2, 0, 0);
            panel.userData = { id: objectId, componentId, componentRole: role, componentFace: face };
            panel.castShadow = true;
            pivot.add(panel);
            scene.add(pivot);
            interactive.push(panel);
            attachHinge(composite, componentId, panel, pivot, rightHinged ? -Math.PI / 2 : Math.PI / 2);
          }
        } else if (role === "drawer_slot" && isDrawer) {
          const trayMaterial = componentMaterial("drawer");
          const trayDepth = depth * 0.78;
          const trayHeight = Math.max(0.04, height * 0.72);
          const trayWall = Math.min(0.025, Math.max(0.012, height * 0.1));
          const trayCenterZ = z - depth / 2 + drawerFaceDepth + trayDepth / 2;
          const trayParts = [
            { w: width * 0.9, h: trayWall, d: trayDepth, x, y: mesh.position.y - trayHeight / 2, z: trayCenterZ },
            { w: trayWall, h: trayHeight, d: trayDepth, x: x - width * 0.45, y: mesh.position.y, z: trayCenterZ },
            { w: trayWall, h: trayHeight, d: trayDepth, x: x + width * 0.45, y: mesh.position.y, z: trayCenterZ },
            { w: width * 0.9, h: trayHeight, d: trayWall, x, y: mesh.position.y, z: trayCenterZ + trayDepth / 2 },
          ];
          trayParts.forEach((part) => {
            const trayPart = new THREE.Mesh(new THREE.BoxGeometry(part.w, part.h, part.d), trayMaterial.clone());
            trayPart.position.set(part.x, part.y, part.z);
            trayPart.userData = { id: objectId, componentRole: "drawer_tray" };
            scene.add(trayPart);
            attachPart(composite, trayPart);
          });
        }
      });
      // Older scene versions may not yet carry the newly materialized washer
      // drawer. Keep the renderer backward-compatible by deriving the same
      // declarative storage contract from the appliance semantic type.
      if (storage) {
        const mountStoragePart = (part: THREE.Mesh) => {
          attachPart(composite, part);
        };
        const levels = Math.max(1, Number(storage.levels) || 1);
        const columns = Math.max(1, Number(storage.columns) || 1);
        // Washer storage is a single open cavity plus an independent front
        // drawer. Do not generate cabinet shelves/dividers inside the washer.
        if (!isWasherHost) for (let level = 0; level < levels; level += 1) {
          for (let column = 0; column < columns; column += 1) {
            const slot = new THREE.Mesh(
              new THREE.BoxGeometry(width * 0.82 / columns, 0.012, depth * 0.68),
              new THREE.MeshBasicMaterial({ color: 0x93c5fd, transparent: true, opacity: 0.08, depthWrite: false }),
            );
            slot.position.copy(worldPointForHost(
              x + (column + 0.5 - columns / 2) * (width * 0.82 / columns),
              mesh.position.y - height / 2 + (level + 1) * (height * 0.72 / levels) + height * 0.14 + 0.006,
              z - depth * 0.04,
            ));
            slot.rotation.y = hostRotation;
            slot.userData = {
              id: `${objectId}_slot_l${level + 1}_c${column + 1}`,
              hostId: objectId,
              componentId: `${objectId}_slot_l${level + 1}_c${column + 1}`,
              componentRole: "storage_slot",
              capabilities: ["place_target"],
              maxCapacity: Number(node?.max_items) || 8,
              requiresContainedCapabilities: Array.isArray(node?.accepted_capabilities)
                ? node.accepted_capabilities.map(String)
                : [],
            };
            scene.add(slot);
            interactive.push(slot);
            mountStoragePart(slot);
          }
        }
        if (!isWasherHost) for (let level = 1; level < levels; level += 1) {
          const shelf = new THREE.Mesh(new THREE.BoxGeometry(width * 0.82, 0.018, depth * 0.72), new THREE.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.8 }));
          shelf.position.copy(worldPointForHost(x, mesh.position.y - height / 2 + (height * level) / levels, z - depth * 0.04));
          shelf.rotation.y = hostRotation;
          shelf.userData = { id: objectId, componentRole: "storage_shelf" };
          scene.add(shelf);
          mountStoragePart(shelf);
        }
        if (!isWasherHost) for (let column = 1; column < columns; column += 1) {
          const divider = new THREE.Mesh(new THREE.BoxGeometry(0.018, height * 0.76, depth * 0.72), new THREE.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.8 }));
          divider.position.copy(worldPointForHost(x - width / 2 + (width * column) / columns, mesh.position.y, z - depth * 0.04));
          divider.rotation.y = hostRotation;
          divider.userData = { id: objectId, componentRole: "storage_divider" };
          scene.add(divider);
          mountStoragePart(divider);
        }
        const drawerCount = Math.max(0, Number(storage.drawer_count) || 0);
        for (let drawerIndex = 0; drawerIndex < drawerCount; drawerIndex += 1) {
          const drawerColumn = drawerIndex % columns;
          const drawerLevel = Math.floor(drawerIndex / columns) % levels;
          const drawerWidth = width * 0.82 / columns;
          const drawerHeight = isWasherHost
            ? Math.max(0.08, height * 0.18)
            : Math.max(0.08, height * 0.72 / levels - 0.025);
          const wallDepth = Math.max(0.08, depth * 0.62);
          const wallThickness = 0.025;
          const drawer = new THREE.Group();
          drawer.position.copy(worldPointForHost(
            x + (drawerColumn + 0.5 - columns / 2) * drawerWidth,
            isWasherHost
              // The washer door was shortened at its upper edge. The drawer
              // occupies that reserved upper band and remains independent of
              // the door articulation.
              ? mesh.position.y + height / 2 - height * 0.08 - drawerHeight / 2
              : mesh.position.y - height / 2 + height * 0.14 + (drawerLevel + 0.5) * (height * 0.72 / levels),
            // Closed drawers stay inside the cabinet.  The prismatic joint
            // moves them toward -Z only after an explicit open interaction.
            z - depth / 2 + wallDepth / 2 + 0.01,
          ));
          drawer.rotation.y = hostRotation;
          const drawerNode = componentNodeForRole("drawer", drawerIndex);
          const componentId = text(drawerNode?.id) || `${objectId}_drawer_${drawerIndex + 1}`;
          drawer.userData = { id: objectId, componentId, componentRole: `drawer_${drawerIndex + 1}` };
          const bottom = new THREE.Mesh(new THREE.BoxGeometry(drawerWidth, wallThickness, wallDepth), componentMaterial("drawer"));
          bottom.position.y = -drawerHeight / 2;
          const front = new THREE.Mesh(new THREE.BoxGeometry(drawerWidth, drawerHeight, wallThickness), componentMaterial("drawer"));
          front.position.set(0, 0, -wallDepth / 2);
          front.userData = { id: objectId, componentId, componentRole: `drawer_${drawerIndex + 1}` };
          const back = new THREE.Mesh(new THREE.BoxGeometry(drawerWidth, drawerHeight, wallThickness), componentMaterial("drawer"));
          back.position.set(0, 0, wallDepth / 2);
          const left = new THREE.Mesh(new THREE.BoxGeometry(wallThickness, drawerHeight, wallDepth), componentMaterial("drawer"));
          left.position.x = -drawerWidth / 2;
          const right = new THREE.Mesh(new THREE.BoxGeometry(wallThickness, drawerHeight, wallDepth), componentMaterial("drawer"));
          right.position.x = drawerWidth / 2;
          bottom.userData = { id: componentId, hostId: objectId, componentId, componentRole: "drawer", capabilities: ["place_target"] };
          drawer.add(bottom, front, back, left, right);
          // The drawer itself is a mechanism; its bottom is the reusable
          // containment surface for detergent. Keep this as a distinct
          // graph-targeted child so opening the drawer and loading it are
          // independent interactions.
          const drawerSlotId = `${componentId}_slot_l1_c1`;
          const drawerSlot = new THREE.Mesh(
            new THREE.BoxGeometry(Math.max(0.02, drawerWidth - wallThickness * 2), 0.008, Math.max(0.02, wallDepth - wallThickness * 2)),
            new THREE.MeshBasicMaterial({ color: 0x93c5fd, transparent: true, opacity: 0.06, depthWrite: false, side: THREE.DoubleSide }),
          );
          drawerSlot.position.set(0, -drawerHeight / 2 + wallThickness / 2 + 0.006, 0);
          drawerSlot.userData = {
            id: drawerSlotId,
            hostId: componentId,
            componentId: drawerSlotId,
            componentRole: "storage_slot",
            capabilities: ["place_target", "receptacle"],
            maxCapacity: 1,
            requiresContainedCapabilities: ["laundry_detergent"],
          };
          drawer.add(drawerSlot);
          interactive.push(drawerSlot);
          const drawerContents = [
            ...(receptacleContents.get(componentId) ?? []),
            // A washer resource may be placed on the host storage slot in
            // older snapshots rather than on the generated drawer link.
            ...(receptacleContents.get(objectId) ?? []),
          ];
          const detergentId = drawerContents.find((contentId) => {
            const content = nodeById.get(contentId);
            return ["detergent", "laundry_detergent", "dishwasher_detergent"].includes(semantic(content));
          });
          if (detergentId) {
            const detergent = nodeById.get(detergentId);
            const detergentStates = detergent?.states as Record<string, unknown> | undefined;
            const amount = THREE.MathUtils.clamp(Number(detergentStates?.amount ?? 1), 0, 1);
            const bottleWidth = Math.min(drawerWidth * 0.28, 0.11);
            const bottleHeight = Math.min(drawerHeight * 0.72, 0.18);
            const bottle = new THREE.Mesh(
              new THREE.BoxGeometry(bottleWidth, bottleHeight, bottleWidth * 0.72),
              new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.35, transparent: true, opacity: 0.9 }),
            );
            bottle.position.set(-drawerWidth * 0.2, -drawerHeight / 2 + bottleHeight / 2 + wallThickness, 0);
            bottle.userData = { id: detergentId, hostId: objectId, componentRole: "drawer_content" };
            const liquid = new THREE.Mesh(
              new THREE.BoxGeometry(bottleWidth * 0.82, Math.max(0.008, bottleHeight * 0.72 * amount), bottleWidth * 0.58),
              new THREE.MeshStandardMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.78, roughness: 0.2 }),
            );
            liquid.position.set(0, -bottleHeight * 0.14 + (bottleHeight * 0.36 * amount), 0);
            bottle.add(liquid);
            drawer.add(bottle);
            detergentVisuals.set(detergentId, { bottle, liquid });
          }
          scene.add(drawer);
          interactive.push(front);
          const drawerAxisLength = depth;
          const guideOverlap = Math.min(wallDepth * 0.62, drawerAxisLength * 0.38);
          attachPrismatic(composite, componentId, drawer, Math.max(0, drawerAxisLength - guideOverlap));
        }
      }
      // Appliances with a front door expose an interior support surface so
      // movable items can be placed inside during the simulation. This is
      // deliberately a semantic slot, not a visible extra part.
      if (["washer", "washing_machine", "dishwasher", "dryer", "clothesdryer", "microwave", "refrigerator"].includes(semantic(node)) && hasFrontDoor) {
        const interior = new THREE.Mesh(
          // Clothes are represented at their unfolded catalog size. The
          // washer cavity must span nearly the full drum width/depth so the
          // placement fit check does not reject a normal garment.
          new THREE.BoxGeometry(width * 0.88, 0.012, depth * 0.82),
          new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide }),
        );
        interior.position.copy(worldPointForHost(x, mesh.position.y - height / 2 + height * 0.18, z - depth * 0.08));
        interior.rotation.y = hostRotation;
        const interiorSlotId = storageSlotsByHost.get(objectId)?.[0] || `${objectId}_slot_l1_c1`;
        interior.userData = {
          id: interiorSlotId,
          hostId: objectId,
          componentId: interiorSlotId,
          componentRole: "storage_slot",
          capabilities: ["place_target", "receptacle"],
          maxCapacity: 8,
        };
        scene.add(interior);
        interactive.push(interior);
        // This transparent mesh is a hit target for placement only. The
        // appliance shell and its door provide physical collision.
        interior.userData.collisionEnabled = false;
        attachPart(composite, interior);
      }
    });

    // The composite root is the single editor transform authority. Register
    // every mesh in its PartTree as a collision shape so translation and
    // rotation keep visual and collision geometry aligned.
      composites.forEach((composite) => {
      composite.host.traverse((child) => {
        if (!(child instanceof THREE.Mesh) || child === composite.host) return;
        if (composite.id.startsWith("elevator_car_") && !child.userData.debugSource) {
          // A cabin may only render its declared PartTree meshes. Any mesh
          // attached through an obsolete/generated path is an accidental
          // proxy (the source of the extra dark outer shell); keep it out of
          // both rendering and physics instead of treating it as a cabin
          // component.
          child.visible = false;
          child.userData.collisionEnabled = false;
          markElevatorMesh(child, "elevator.removed_unclassified_part", composite.id);
        }
        if (child.userData.collisionEnabled === false || collisionMeshes.includes(child) || elevatorCollisionMeshes.has(child)) return;
        if (composite.id.startsWith("elevator_car_")) {
          // Every collidable cabin part belongs to the same kinematic body;
          // do not let panels/buttons fall back into the static collider set.
          elevatorCollisionMeshes.add(child);
        } else {
          collisionMeshes.push(child);
        }
      });
      });

    const pendingTransform: { id: string; changed: boolean; startPosition: THREE.Vector3 | null } = { id: "", changed: false, startPosition: null };
    let lastRotationObject: THREE.Object3D | null = null;
    const commitRotation = () => {
      const mesh = lastRotationObject ?? rotationControls.object as THREE.Object3D | undefined;
      if (!mesh) return;
      pendingTransform.id = String(mesh.userData.id || selectedId);
      pendingTransform.changed = true;
      mesh.rotation.set(
        normalizeQuarterTurn(mesh.rotation.x) * Math.PI / 2,
        normalizeQuarterTurn(mesh.rotation.y) * Math.PI / 2,
        normalizeQuarterTurn(mesh.rotation.z) * Math.PI / 2,
      );
      syncCompositeFor(pendingTransform.id);
      commitTransform();
    };
    const gizmoLock = { active: false };
    const transformGuard = { active: false };
    const lastValidPositions = new Map<string, THREE.Vector3>();
    objectMeshes.forEach((mesh, id) => lastValidPositions.set(id, mesh.position.clone()));
    const dimensionsFor = (id: string) => {
      const item = layout.objects[id];
      const entry = catalogByType.get(semantic(nodeById.get(id)));
      return {
        width: (entry?.width_cm ?? item?.width_cm ?? (item?.width_cells ?? 1) * cell * 100) / 100,
        depth: (entry?.depth_cm ?? item?.depth_cm ?? (item?.depth_cells ?? 1) * cell * 100) / 100,
        height: (entry?.height_cm ?? item?.height_cm ?? 80) / 100,
      };
    };
    const canOccupy = (id: string, position: THREE.Vector3, currentPosition: THREE.Vector3) => {
      const item = layout.objects[id];
      if (!item || item.placement_mode === "contained" || item.placement_mode === "wall_mounted") return true;
      const room = layout.rooms[item.room_id];
      if (!room) return false;
      const dimensions = dimensionsFor(id);
      const roomX = (room.x_cm ?? room.grid_x * cell * 100) / 100;
      const roomZ = (room.y_cm ?? room.grid_y * cell * 100) / 100;
      const roomWidth = room.width_cells * cell;
      const roomDepth = room.depth_cells * cell;
      if (position.x - dimensions.width / 2 < roomX || position.x + dimensions.width / 2 > roomX + roomWidth || position.z - dimensions.depth / 2 < roomZ || position.z + dimensions.depth / 2 > roomZ + roomDepth || position.y - dimensions.height / 2 < 0) return false;
      const overlapVolume = (first: THREE.Vector3, second: THREE.Vector3, otherSize: { width: number; depth: number; height: number }) =>
        Math.max(0, (dimensions.width + otherSize.width) / 2 - Math.abs(first.x - second.x))
        * Math.max(0, (dimensions.depth + otherSize.depth) / 2 - Math.abs(first.z - second.z))
        * Math.max(0, (dimensions.height + otherSize.height) / 2 - Math.abs(first.y - second.y));
      for (const [otherId, otherMesh] of objectMeshes) {
        if (otherId === id) continue;
        const other = layout.objects[otherId];
        if (!other || other.room_id !== item.room_id || other.placement_mode === "contained" || other.placement_mode === "wall_mounted") continue;
        const otherSize = dimensionsFor(otherId);
        const candidateOverlap = overlapVolume(position, otherMesh.position, otherSize);
        if (candidateOverlap <= 0) continue;
        const currentOverlap = overlapVolume(currentPosition, otherMesh.position, otherSize);
        if (currentOverlap <= 0 || candidateOverlap >= currentOverlap) return false;
      }
      return true;
    };
    const constrainTransform = () => {
      if (transformGuard.active || !transformControls.object) return;
      const id = String(transformControls.object.userData.id || "");
      if (!id || !layout.objects[id]) return;
      const mesh = transformControls.object as THREE.Mesh;
      const size = dimensionsFor(id);
      const item = layout.objects[id];
      const room = layout.rooms[item.room_id];
      if (!room) return;
      const roomX = (room.x_cm ?? room.grid_x * cell * 100) / 100;
      const roomZ = (room.y_cm ?? room.grid_y * cell * 100) / 100;
      const roomWidth = room.width_cells * cell;
      const roomDepth = room.depth_cells * cell;
      const snapped = mesh.position.clone().set(
        Math.round(mesh.position.x / cell) * cell,
        Math.round(mesh.position.y / cell) * cell,
        Math.round(mesh.position.z / cell) * cell,
      );
      const wallMounted = item.placement_mode === "wall_mounted";
      snapped.x = Math.max(roomX + (wallMounted ? 0 : size.width / 2), Math.min(roomX + roomWidth - (wallMounted ? 0 : size.width / 2), snapped.x));
      snapped.z = Math.max(roomZ + (wallMounted ? 0 : size.depth / 2), Math.min(roomZ + roomDepth - (wallMounted ? 0 : size.depth / 2), snapped.z));
      snapped.y = Math.max(size.height / 2, snapped.y);
      const previous = lastValidPositions.get(id) ?? mesh.position.clone();
      transformGuard.active = true;
      mesh.position.copy(canOccupy(id, snapped, previous) ? snapped : previous);
      transformGuard.active = false;
      lastValidPositions.set(id, mesh.position.clone());
    };
    const syncCompositeFor = (id: string) => {
      const composite = composites.find((entry) => entry.id === id);
      if (!composite) return;
      // TransformControls changes the host mesh before the animation loop
      // runs. Update the hierarchy immediately so doors, buttons, shelves,
      // and drawers follow during the drag, not only after mouseup.
      composite.host.updateMatrixWorld(true);
      updateComposites([composite], 1);
      composite.host.updateMatrixWorld(true);
    };
    const commitTransform = () => {
      if (!pendingTransform.id || !pendingTransform.changed) return;
      const item = layout.objects[pendingTransform.id];
      const mesh = objectMeshes.get(pendingTransform.id);
      if (!item || !mesh) return;
      const node = nodeById.get(pendingTransform.id);
      const catalogEntry = catalogByType.get(semantic(node));
      const width = catalogEntry?.width_cm ?? item.width_cm ?? item.width_cells * cell * 100;
      const depth = catalogEntry?.depth_cm ?? item.depth_cm ?? item.depth_cells * cell * 100;
      const height = catalogEntry?.height_cm ?? item.height_cm ?? 80;
      // Mesh Y includes the same placement base used during render. Contained
      // items remain relative to their parent; all other objects, including
      // wall-mounted assets, use the canonical z_cm coordinate directly.
      const parentMesh = item.parent_object_id ? objectMeshes.get(item.parent_object_id) : undefined;
      const parentHeight = parentMesh?.geometry.boundingBox
        ? parentMesh.geometry.boundingBox.max.y - parentMesh.geometry.boundingBox.min.y
        : 0.8;
      const baseHeight = item.placement_mode === "contained" && !(pendingTransform.startPosition && mesh.position.distanceToSquared(pendingTransform.startPosition) > 0.0001)
          ? Math.max(0.02, (parentMesh?.position.y ?? parentHeight) - parentHeight / 2 + 0.03)
          : 0;
      const detachContained = item.placement_mode === "contained"
        && Boolean(pendingTransform.startPosition && mesh.position.distanceToSquared(pendingTransform.startPosition) > 0.0001);
      const next = structuredClone(layout);
      const room = layout.rooms[item.room_id];
      const xCm = Math.round((mesh.position.x - width / 200) * 100);
      const yCm = Math.round((mesh.position.z - depth / 200) * 100);
      const wallMounted = item.placement_mode === "wall_mounted";
      const rotationX = normalizeQuarterTurn(mesh.rotation.x);
      const rotationY = normalizeQuarterTurn(mesh.rotation.y);
      const rotationZ = normalizeQuarterTurn(mesh.rotation.z);
      next.objects[pendingTransform.id] = {
        ...next.objects[pendingTransform.id],
        ...(detachContained ? { placement_mode: "surface" as const, parent_object_id: undefined, layout_anchor: "surface" } : {}),
        // Keep the grid coordinates in sync with the physical snapshot. The
        // 2D editor renders these fields, while 3D preserves centimeter
        // precision and vertical placement in z_cm.
        grid_x: room ? wallMounted
          ? Math.max(0, Math.min(room.width_cells - 1, Math.floor((xCm - (room.x_cm ?? room.grid_x * cell * 100)) / (cell * 100))))
          : Math.round((xCm - (room.x_cm ?? room.grid_x * cell * 100)) / (cell * 100))
          : item.grid_x,
        grid_y: room ? wallMounted
          ? Math.max(0, Math.min(room.depth_cells - 1, Math.floor((yCm - (room.y_cm ?? room.grid_y * cell * 100)) / (cell * 100))))
          : Math.round((yCm - (room.y_cm ?? room.grid_y * cell * 100)) / (cell * 100))
          : item.grid_y,
        x_cm: xCm,
        y_cm: yCm,
        z_cm: Math.round((mesh.position.y - baseHeight - height / 200) * 100),
        rotation: rotationY,
        rotation_x: rotationX,
        rotation_y: rotationY,
        rotation_z: rotationZ,
      };
      changeRef.current(next);
      if (detachContained) placementChangeRef.current?.(pendingTransform.id, item.room_id);
      pendingTransform.id = "";
      pendingTransform.changed = false;
      pendingTransform.startPosition = null;
    };
    transformControls.addEventListener("dragging-changed", (event) => {
      controls.enabled = !(event.value as boolean);
      gizmoLock.active = Boolean(event.value);
      rotationControls.enabled = !Boolean(event.value);
      if (event.value) {
        pendingTransform.id = String(transformControls.object?.userData.id || selectedId);
        pendingTransform.startPosition = transformControls.object?.position.clone() ?? null;
      }
      else commitTransform();
    });
    transformControls.addEventListener("mouseDown", () => { gizmoLock.active = true; rotationControls.enabled = false; });
    transformControls.addEventListener("mouseUp", () => { gizmoLock.active = false; rotationControls.enabled = true; });
    transformControls.addEventListener("objectChange", () => {
      pendingTransform.changed = true;
      syncCompositeFor(String(transformControls.object?.userData.id || selectedId));
    });
    transformControls.addEventListener("objectChange", constrainTransform);
    if (selectedId && objectMeshes.has(selectedId)) {
      transformControls.attach(objectMeshes.get(selectedId)!);
      rotationControls.attach(objectMeshes.get(selectedId)!);
    }
    rotationControls.addEventListener("dragging-changed", (event) => {
      controls.enabled = !(event.value as boolean);
      gizmoLock.active = Boolean(event.value);
      transformControls.enabled = !Boolean(event.value);
      if (event.value) {
        pendingTransform.id = String(rotationControls.object?.userData.id || selectedId);
        pendingTransform.startPosition = rotationControls.object?.position.clone() ?? null;
      } else {
        const mesh = lastRotationObject ?? rotationControls.object as THREE.Object3D | undefined;
        if (mesh) {
          pendingTransform.id = String(mesh.userData.id || selectedId);
          pendingTransform.changed = true;
          mesh.rotation.set(
            normalizeQuarterTurn(mesh.rotation.x) * Math.PI / 2,
            normalizeQuarterTurn(mesh.rotation.y) * Math.PI / 2,
            normalizeQuarterTurn(mesh.rotation.z) * Math.PI / 2,
          );
          syncCompositeFor(pendingTransform.id);
        }
        commitRotation();
      }
    });
    rotationControls.addEventListener("mouseDown", () => { gizmoLock.active = true; transformControls.enabled = false; });
    rotationControls.addEventListener("mouseUp", () => {
      gizmoLock.active = false;
      transformControls.enabled = true;
      const mesh = lastRotationObject ?? rotationControls.object as THREE.Object3D | undefined;
      if (mesh) {
        // Do not rely on a particular TransformControls event ordering. The
        // release gesture itself is the commit boundary for a snapped turn.
        pendingTransform.id = String(mesh.userData.id || selectedId);
        pendingTransform.changed = true;
        mesh.rotation.set(
          normalizeQuarterTurn(mesh.rotation.x) * Math.PI / 2,
          normalizeQuarterTurn(mesh.rotation.y) * Math.PI / 2,
          normalizeQuarterTurn(mesh.rotation.z) * Math.PI / 2,
        );
      }
      commitRotation();
    });
    rotationControls.addEventListener("objectChange", () => {
      pendingTransform.changed = true;
      const mesh = rotationControls.object;
      if (mesh) {
        lastRotationObject = mesh;
        pendingTransform.id = String(mesh.userData.id || selectedId);
        syncCompositeFor(pendingTransform.id);
      }
    });

    const center = new THREE.Vector3(allWidth / 2, 0.8, allDepth / 2);
    const savedCamera = cameraStateRef.current;
    const initialTarget = savedCamera?.target ?? center;
    controls.target.copy(initialTarget);
    camera.position.copy(savedCamera?.position ?? new THREE.Vector3(allWidth * 0.95, Math.max(8, allDepth * 0.95), allDepth * 1.15));
    camera.lookAt(initialTarget);
    controls.update();
    const editorCamera = {
      position: camera.position.clone(),
      target: controls.target.clone(),
    };
    const savedSimulation = simulationStateRef.current;
    const simulation = {
      active: Boolean(savedSimulation),
      yaw: savedSimulation?.yaw ?? 0,
      pitch: savedSimulation?.pitch ?? 0,
      keys: new Set<string>(),
      lastFrame: performance.now(),
      player: savedSimulation?.player.clone() ?? new THREE.Vector3(center.x, 1.6, center.z),
      roomId: savedSimulation?.roomId ?? actorRoomId,
      moving: savedSimulation?.moving ?? false,
    };
    if (simulation.active) {
      camera.position.copy(simulation.player);
      camera.rotation.set(simulation.pitch, simulation.yaw, 0, "YXZ");
      controls.enabled = false;
      simulationActiveRef.current = true;
      transformControls.detach();
      transformControls.getHelper().visible = false;
      rotationControls.detach();
      rotationControls.getHelper().visible = false;
    }
    const cameraDirection = new THREE.Vector3();
    // Keep the first-person hand marker subtle; it is a visual pose cue, not
    // the player's collision or grasp volume.
    const handGeometry = new THREE.SphereGeometry(0.055, 16, 12);
    const handMaterial = new THREE.MeshStandardMaterial({ color: 0xf2b38b, roughness: 0.78 });
    const hands = {
      left: new THREE.Mesh(handGeometry, handMaterial),
      right: new THREE.Mesh(handGeometry, handMaterial),
    };
    const handAnchors = { left: new THREE.Object3D(), right: new THREE.Object3D() };
    const armGeometry = new THREE.CylinderGeometry(0.055, 0.07, 1, 10);
    const armMaterial = new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.82 });
    const arms = { left: new THREE.Mesh(armGeometry, armMaterial.clone()), right: new THREE.Mesh(armGeometry, armMaterial.clone()) };
    const playerBody = new THREE.Mesh(
      new THREE.CapsuleGeometry(0.28, 1.04, 8, 16),
      new THREE.MeshStandardMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.72 }),
    );
    playerBody.userData.layer = "objects";
    playerBody.visible = false;
    scene.add(playerBody);

    // Rapier owns character-vs-scene collision during simulation. Static
    // colliders are generated from the already-built Three.js meshes so the
    // renderer and physics share exactly the same visible geometry.
    void RAPIER.init().then(() => {
      if (rapierInitCancelled) return;
      const world = new RAPIER.World({ x: 0, y: -9.81, z: 0 });
      const staticBody = world.createRigidBody(RAPIER.RigidBodyDesc.fixed());
      const staticColliders = new Map<THREE.Mesh, ReturnType<RAPIER.World["createCollider"]>>();
      const elevatorBody = RAPIER.RigidBodyDesc.kinematicPositionBased()
        .setTranslation(0, 0, 0);
      const elevatorRigidBody = world.createRigidBody(elevatorBody);
      const elevatorColliders = new Map<THREE.Mesh, ReturnType<RAPIER.World["createCollider"]>>();
      collisionMeshes.forEach((mesh) => {
        if (elevatorCollisionMeshes.has(mesh)) return;
        mesh.updateWorldMatrix(true, false);
        const localBounds = mesh.geometry.boundingBox ?? new THREE.Box3().setFromBufferAttribute(mesh.geometry.getAttribute("position") as THREE.BufferAttribute);
        if (localBounds.isEmpty()) return;
        const center = new THREE.Vector3();
        mesh.getWorldPosition(center);
        const scale = new THREE.Vector3();
        mesh.getWorldScale(scale);
        const localSize = localBounds.getSize(new THREE.Vector3());
        const half = localSize.multiply(scale).multiplyScalar(0.5);
        if (half.x <= 1e-4 || half.y <= 1e-4 || half.z <= 1e-4) return;
        const rotation = new THREE.Quaternion();
        mesh.getWorldQuaternion(rotation);
        const collider = world.createCollider(RAPIER.ColliderDesc.cuboid(half.x, half.y, half.z)
          .setTranslation(center.x, center.y, center.z)
          .setRotation({ x: rotation.x, y: rotation.y, z: rotation.z, w: rotation.w }), staticBody);
        collider.setEnabled(mesh.userData.collisionEnabled !== false);
        staticColliders.set(mesh, collider);
      });
      const elevatorRoot = [...objectMeshes.values()]
        .find((mesh) => semantic(nodeById.get(String(mesh.userData.id))) === "elevator")
        ?.userData.elevatorVisualRoot as THREE.Group | undefined;
      if (elevatorRoot) {
        elevatorRoot.updateWorldMatrix(true, true);
        const rootPosition = elevatorRoot.getWorldPosition(new THREE.Vector3());
        const rootRotation = elevatorRoot.getWorldQuaternion(new THREE.Quaternion());
        elevatorRigidBody.setTranslation({ x: rootPosition.x, y: rootPosition.y, z: rootPosition.z }, true);
        elevatorCollisionMeshes.forEach((mesh) => {
          mesh.updateWorldMatrix(true, false);
          const localBounds = mesh.geometry.boundingBox ?? new THREE.Box3().setFromBufferAttribute(mesh.geometry.getAttribute("position") as THREE.BufferAttribute);
          if (localBounds.isEmpty()) return;
          const localSize = localBounds.getSize(new THREE.Vector3());
          const scale = mesh.getWorldScale(new THREE.Vector3());
          const half = localSize.multiply(scale).multiplyScalar(0.5);
          if (half.x <= 1e-4 || half.y <= 1e-4 || half.z <= 1e-4) return;
          const worldPosition = mesh.getWorldPosition(new THREE.Vector3());
          const relativePosition = worldPosition.clone().sub(rootPosition).applyQuaternion(rootRotation.clone().invert());
          const worldQuaternion = mesh.getWorldQuaternion(new THREE.Quaternion());
          const relativeQuaternion = rootRotation.clone().invert().multiply(worldQuaternion);
          const collider = world.createCollider(RAPIER.ColliderDesc.cuboid(half.x, half.y, half.z)
            .setTranslation(relativePosition.x, relativePosition.y, relativePosition.z)
            .setRotation({ x: relativeQuaternion.x, y: relativeQuaternion.y, z: relativeQuaternion.z, w: relativeQuaternion.w }), elevatorRigidBody);
          collider.setEnabled(mesh.userData.collisionEnabled !== false);
          elevatorColliders.set(mesh, collider);
        });
      }
      // Keep the character capsule a small epsilon above authored floor tops.
      // Without this clearance, crossing onto the moving cabin floor starts
      // with a penetrating capsule and Rapier can return zero movement while
      // repeatedly resolving the same floor contact.
      const playerPhysicsY = 0.84;
      const playerBody = world.createRigidBody(
        RAPIER.RigidBodyDesc.kinematicPositionBased().setTranslation(simulation.player.x, playerPhysicsY, simulation.player.z),
      );
      const collider = world.createCollider(RAPIER.ColliderDesc.capsule(0.52, 0.28), playerBody);
      const controller = world.createCharacterController(0.02);
      controller.setUp({ x: 0, y: 1, z: 0 });
      controller.setSlideEnabled(true);
      controller.enableAutostep(0.18, 0.2, false);
      controller.enableSnapToGround(0.12);
      // Build Rapier's broad phase/query pipeline before the first character
      // controller query. Static colliders created after a world step are not
      // visible to computeColliderMovement until the pipeline is synchronized.
      world.step();
      rapierRuntime = { world, controller, collider, playerBody, staticBody, staticColliders, elevatorBody: elevatorRigidBody, elevatorColliders, disposed: false };
      if (import.meta.env.DEV) {
        console.debug("Rapier initialized", {
          staticColliders: staticColliders.size,
          enabledColliders: [...staticColliders.values()].filter((item) => item.isEnabled()).length,
          elevatorColliders: elevatorColliders.size,
          elevatorParts: [...elevatorColliders.keys()].map((mesh) => mesh.userData.debugSource),
          elevatorEnabled: [...elevatorColliders.values()].filter((item) => item.isEnabled()).length,
          elevatorBodyType: elevatorRigidBody.bodyType(),
          player: [simulation.player.x, simulation.player.y, simulation.player.z],
        });
      }
    }).catch((error) => console.error("Rapier initialization failed", error));
    hands.left.userData.layer = "objects";
    hands.right.userData.layer = "objects";
    scene.add(hands.left, hands.right, handAnchors.left, handAnchors.right, arms.left, arms.right);
    const heldVisualIds = new Set<string>();
    const simulationActorId = actorId || "__simulation_player__";
    const heldOverride = new Map<string, "left" | "right">();
    const syncHeldVisuals = () => {
      const nextHeld = new Map<string, "left" | "right">();
      edges.forEach((edge) => {
        if (text(edge.source_id || edge.source) !== simulationActorId) return;
        const relation = text(edge.relation || edge.edge_type);
        const objectId = text(edge.target_id || edge.target);
        if (!objectId) return;
        if (relation === "held_by" || relation === "held_by_right") nextHeld.set(objectId, "right");
        if (relation === "held_by_left") nextHeld.set(objectId, "left");
        if (relation === "held_by_both") nextHeld.set(objectId, "right");
      });
      heldOverride.forEach((hand, objectId) => nextHeld.set(objectId, hand));
      heldVisualIds.forEach((objectId) => {
        if (nextHeld.has(objectId)) return;
        const mesh = objectMeshes.get(objectId);
        if (mesh?.parent === handAnchors.left || mesh?.parent === handAnchors.right) {
          scene.attach(mesh);
          mesh.userData.held = false;
        }
        heldVisualIds.delete(objectId);
      });
      nextHeld.forEach((hand, objectId) => {
        const mesh = objectMeshes.get(objectId);
        if (!mesh) {
          if (import.meta.env.DEV) {
            console.warn("Held visual missing mesh", {
              object_id: objectId,
              hand,
              known_meshes: [...objectMeshes.keys()].filter((id) => id.includes("detergent")),
              known_nodes: [...nodeById.keys()].filter((id) => id.includes("detergent")),
            });
          }
          return;
        }
        if (!heldVisualIds.has(objectId)) {
          if (import.meta.env.DEV) {
            console.debug("Held visual attach", {
              object_id: objectId,
              hand,
              before_visible: mesh.visible,
              before_parent: mesh.parent?.userData?.id ?? mesh.parent?.name ?? "scene",
              node: nodeById.get(objectId),
            });
          }
          handAnchors[hand].add(mesh);
          mesh.position.set(0, 0, -0.16);
          mesh.quaternion.identity();
          mesh.userData.held = true;
          // Retrieval clears the runtime hidden metadata. Apply the visual
          // hand state immediately as well, so the object does not remain
          // invisible until a later animation frame.
          mesh.visible = true;
          mesh.userData.collisionEnabled = false;
          heldVisualIds.add(objectId);
          if (import.meta.env.DEV) {
            console.debug("Held visual attached", {
              object_id: objectId,
              hand,
              visible: mesh.visible,
              parent: mesh.parent?.name,
              position: mesh.position.toArray(),
            });
          }
        }
      });
      heldByHand.left = [...nextHeld.entries()].find(([, hand]) => hand === "left")?.[0] ?? null;
      heldByHand.right = [...nextHeld.entries()].find(([, hand]) => hand === "right")?.[0] ?? null;
      setHeldObjectLabel([heldByHand.left, heldByHand.right]
        .filter((id, index, values): id is string => Boolean(id) && values.indexOf(id) === index)
        .map((id) => nodeName(nodeById.get(id)) || id)
        .join(" / "));
    };
    (["left", "right"] as const).forEach((hand) => {
      const heldId = heldByHand[hand];
      const heldMesh = heldId ? objectMeshes.get(heldId) : undefined;
      if (!heldMesh) return;
      heldMesh.userData.held = true;
      heldMesh.scale.setScalar(1);
      handAnchors[hand].add(heldMesh);
      heldMesh.position.set(0, 0, -0.16);
      heldMesh.quaternion.identity();
    });
    setHeldObjectLabel([heldByHand.left, heldByHand.right]
      .filter((id, index, values): id is string => Boolean(id) && values.indexOf(id) === index)
      .map((id) => nodeName(nodeById.get(id)) || id)
      .join(" / "));
    hands.left.visible = false;
    hands.right.visible = false;
    arms.left.visible = false;
    arms.right.visible = false;
    const startSimulation = async () => {
      if (simulation.active) {
        if (document.pointerLockElement !== renderer.domElement) renderer.domElement.requestPointerLock();
        return;
      }
      const started = await onSimulationStart?.();
      if (effectDisposed) return;
      // The simulation may normalize initial states (doors, devices, held
      // objects) while starting. Merge that authoritative snapshot into the
      // live node objects before the first interaction ray is processed.
      const startedNodes = (started as Record<string, unknown> | undefined)?.snapshot
        && (((started as Record<string, unknown>).snapshot as Record<string, unknown>).nodes);
      if (Array.isArray(startedNodes)) {
        const startedById = new Map(startedNodes.map((item) => [text((item as RawNode).id), item as RawNode]));
        nodes.forEach((item) => {
          const authoritative = startedById.get(text(item.id));
          if (authoritative) Object.assign(item, authoritative);
        });
      }
      editorCamera.position.copy(camera.position);
      editorCamera.target.copy(controls.target);
      const startedState = (started as Record<string, unknown> | undefined)?.snapshot as Record<string, unknown> | undefined;
      const startedWorld = startedState?.world_state as Record<string, unknown> | undefined;
      const startedAgents = startedWorld?.agents as Record<string, Record<string, unknown>> | undefined;
      const startedAgent = startedAgents?.[actorId || "__simulation_player__"];
      const startedPosition = startedAgent?.position as Record<string, unknown> | undefined;
      if (startedPosition && Number.isFinite(Number(startedPosition.x)) && Number.isFinite(Number(startedPosition.z))) {
        simulation.player.set(Number(startedPosition.x), Number(startedPosition.y ?? 1.6), Number(startedPosition.z));
        simulation.roomId = text(startedAgent?.room_id) || actorRoomId;
      } else {
        const spawnRoom = layout.rooms[actorRoomId] ?? roomEntries[0]?.[1];
        if (spawnRoom) {
        simulation.player.set(
          (spawnRoom.grid_x + spawnRoom.width_cells / 2) * cell,
          1.6,
          (spawnRoom.grid_y + spawnRoom.depth_cells / 2) * cell,
        );
        } else {
          simulation.player.set(center.x, 1.6, center.z);
        }
      }
      camera.position.copy(simulation.player);
      // The editor camera is an elevated orbit camera. Reusing its rotation
      // as the first-person spawn heading can point the center ray into a
      // wall, making the first Q/E press become only raise_hand. Aim at the
      // nearest authored affordance in the spawn room instead. This is a
      // generic layout query, not an object-specific interaction rule.
      const spawnCandidates = Object.entries(layout.objects)
        .filter(([, placement]) => placement.room_id === simulation.roomId && placement.placement_mode !== "contained")
        .map(([id, placement]) => {
          const node = nodeById.get(id);
          const capabilities = new Set(Array.isArray(node?.capabilities) ? node.capabilities.map(String) : []);
          const actionable = capabilities.has("switchable") || capabilities.has("openable")
            || capabilities.has("pickable") || capabilities.has("place_target");
          const width = Number(placement.width_cm ?? placement.width_cells * cell * 100) / 100;
          const depth = Number(placement.depth_cm ?? placement.depth_cells * cell * 100) / 100;
          const height = Number(placement.height_cm ?? 80) / 100;
          const point = new THREE.Vector3(
            (Number(placement.x_cm ?? (placement.grid_x * cell * 100)) / 100) + width / 2,
            Number(placement.z_cm ?? 0) / 100 + height / 2 + floorElevation(layout.rooms[simulation.roomId] ?? {}),
            (Number(placement.y_cm ?? (placement.grid_y * cell * 100)) / 100) + depth / 2,
          );
          const distance = point.distanceTo(simulation.player);
          return { id, point, distance, actionable };
        })
        .filter((candidate) => candidate.distance > 0.25)
        .sort((a, b) => Number(b.actionable) - Number(a.actionable) || a.distance - b.distance);
      const target = spawnCandidates[0]?.point;
      if (target) {
        const heading = target.clone().sub(simulation.player);
        const horizontal = Math.hypot(heading.x, heading.z);
        simulation.yaw = Math.atan2(-heading.x, -heading.z);
        simulation.pitch = horizontal > 1e-6 ? Math.atan2(heading.y, horizontal) : 0;
        if (import.meta.env.DEV) console.debug("Simulation spawn heading", {
          room: simulation.roomId,
          target: [target.x, target.y, target.z],
          player: [simulation.player.x, simulation.player.y, simulation.player.z],
          yaw: simulation.yaw,
          pitch: simulation.pitch,
        });
      } else {
        camera.getWorldDirection(cameraDirection);
        simulation.yaw = Math.atan2(-cameraDirection.x, -cameraDirection.z);
        simulation.pitch = 0;
      }
      simulation.lastFrame = performance.now();
      simulation.roomId = simulation.roomId || actorRoomId || roomEntries[0]?.[0] || "";
      lastMoveRequestRef.current = 0;
      moveInFlightRef.current = false;
      pendingMoveRef.current = null;
      simulation.active = true;
      simulationActiveRef.current = true;
      onSimulationActiveChange?.(true);
      controls.enabled = false;
      transformControls.detach();
      transformControls.getHelper().visible = false;
      rotationControls.detach();
      rotationControls.getHelper().visible = false;
      setSimulationActive(true);
      renderer.domElement.focus();
      // An automatic run is entered from a route transition, which is not a
      // browser user gesture. Requesting pointer lock here fails and the
      // resulting pointerlockchange used to tear the session down immediately.
      // The first canvas click below acquires the lock instead.
      if (!autoStartSimulation) renderer.domElement.requestPointerLock();
    };
    const stopSimulation = () => {
      if (placementPreview) placementPreview.visible = false;
      if (placementHighlight) placementHighlight.visible = false;
      clearInteractionHighlight();
      if (!simulation.active) return;
      simulation.active = false;
      simulationStateRef.current = null;
      simulationActiveRef.current = false;
      onSimulationActiveChange?.(false);
      simulation.keys.clear();
      const pendingLayout = pendingSimulationLayoutRef.current;
      if (pendingLayout) {
        changeRef.current(pendingLayout);
        pendingSimulationLayoutRef.current = null;
      }
      if (document.pointerLockElement === renderer.domElement) document.exitPointerLock();
      hands.left.visible = false;
      hands.right.visible = false;
      arms.left.visible = false;
      arms.right.visible = false;
      camera.position.copy(editorCamera.position);
      controls.target.copy(editorCamera.target);
      camera.lookAt(editorCamera.target);
      controls.enabled = true;
      controls.update();
      transformControls.getHelper().visible = true;
      rotationControls.getHelper().visible = true;
      const selectedMesh = objectMeshes.get(selectedIdRef.current);
      if (selectedMesh) {
        transformControls.attach(selectedMesh);
        rotationControls.attach(selectedMesh);
      }
      setSimulationActive(false);
      setPointerLocked(false);
    };
    simulationControllerRef.current = { start: () => { void startSimulation(); }, stop: stopSimulation };
    if (autoStartSimulation) window.setTimeout(() => { if (!simulation.active) void startSimulation(); }, 0);
    const onKeyDown = (event: KeyboardEvent) => {
      if (simulation.active && event.code === "KeyV" && !event.repeat) {
        setViewMode((mode) => mode === "first" ? "third" : "first");
        return;
      }
      const hand = handForKey(event.code);
      if (simulation.active && hand) {
        event.preventDefault();
        if (!event.repeat) {
          handsRef.current[hand] = true;
          activeInteractionHand = hand;
          pointer.set(0, 0);
          // Q/E can arrive between render frames. Ensure the ray uses the
          // current first-person camera pose instead of the previous frame's
          // matrix, otherwise valid targets degrade to raise_hand.
          camera.updateMatrixWorld(true);
          raycaster.setFromCamera(pointer, camera);
          const hit = findSimulationHit();
          if (hit) {
            console.info("Interaction key target", {
              key: event.code,
              target_id: text(hit.object.userData.componentId)
                || objectIdForHit(hit.object, objectMeshes)
                || text(hit.object.userData.id),
            });
            simulationClick(hit);
          }
          else {
            console.info("Interaction key miss", { key: event.code });
            // A miss is still a canonical interaction: the backend records a
            // raise_hand intent while the renderer shows the pose immediately.
            dispatchInteraction({
              targetId: "",
              hand: activeInteractionHand,
              input: "interact_primary",
              hit: { node_id: "", room_id: simulation.roomId },
              event: inputEvent("key", "pressed", ++inputSequenceRef.current, { code: event.code }, "", simulationActorId),
            });
          }
        }
        return;
      }
      if (!simulation.active || !isMovementKey(event.code)) return;
      event.preventDefault();
      simulation.keys.add(event.code);
    };
    const onKeyUp = (event: KeyboardEvent) => {
      const hand = handForKey(event.code);
      if (event.code === "KeyQ") handsRef.current.left = false;
      if (event.code === "KeyE") handsRef.current.right = false;
      if (simulation.active && hand && !event.repeat) {
        dispatchInteraction({
          targetId: "",
          hand,
          input: "lower_hand",
          hit: { node_id: "", room_id: simulation.roomId },
          event: inputEvent("key", "released", ++inputSequenceRef.current, { code: event.code }, "", simulationActorId),
        });
      }
      simulation.keys.delete(event.code);
      if (simulation.active && isMovementKey(event.code)) {
        void Promise.resolve(onSimulationEvent?.(
          inputEvent(
            "movement",
            "released",
            ++inputSequenceRef.current,
            { code: event.code, active_movement_keys: Array.from(simulation.keys) },
            "",
            simulationActorId,
          ),
        )).then((response) => {
          const result = response as Record<string, unknown> | void;
          const delta = result?.delta as Record<string, unknown> | undefined;
          const state = (delta?.agent as Record<string, Record<string, unknown>> | undefined)?.[simulationActorId];
          if (state?.moving != null) simulation.moving = Boolean(state.moving);
        });
      }
    };
    const onMouseLook = (event: MouseEvent) => {
      if (!simulation.active || document.pointerLockElement !== renderer.domElement) return;
      simulation.yaw -= event.movementX * 0.0022;
      simulation.pitch = THREE.MathUtils.clamp(simulation.pitch - event.movementY * 0.0022, -Math.PI / 2 + 0.08, Math.PI / 2 - 0.08);
    };
    const onPointerLockChange = () => {
      const locked = document.pointerLockElement === renderer.domElement;
      setPointerLocked(locked);
      if (!locked) {
        simulation.keys.clear();
        handsRef.current.left = false;
        handsRef.current.right = false;
        // Escape is the explicit simulation exit.  Actions and state updates
        // must never release pointer lock by rebuilding the renderer.
        if (simulation.active) stopSimulation();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    document.addEventListener("mousemove", onMouseLook);
    document.addEventListener("pointerlockchange", onPointerLockChange);
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const dragPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
    const dragPoint = new THREE.Vector3();
    let interactionChain: Promise<unknown> = Promise.resolve();
    const dispatchInteraction = (request: Parameters<Scene3DCanvasProps["onSimulationInteraction"]>[0]) => {
      const next = interactionChain
        .catch(() => undefined)
        .then(() => movementBarrierRef.current)
        .then(() => simulationInteractionRef.current(request));
      interactionChain = next.then(() => undefined, () => undefined);
      return next;
    };
    const simulationClick = (hit: THREE.Intersection<THREE.Object3D>, surfacePlacement = false) => {
      if (!simulation.active) return;
      let hitSource: THREE.Object3D | null = hit.object;
      while (hitSource && !hitSource.userData.debugSource) hitSource = hitSource.parent;
      if (hitSource?.userData.debugSource) {
        logElevatorMesh(hitSource, "Elevator interaction hit");
      }
      const componentRole = text(hit.object.userData.componentRole);
      const componentId = text(hit.object.userData.componentId);
      // Generated component meshes (buttons, slots, faucets) may carry only a
      // component id; resolve their graph root through the PartTree before
      // rejecting the hit. The highlight path already does this lookup.
      const id = String(hit.object.userData.id || objectIdForHit(hit.object, objectMeshes) || "");
      console.info("Interaction dispatch target", {
        target_id: componentId && nodeById.has(componentId) ? componentId : id,
        component_id: componentId,
        root_id: id,
      });
      if (!id) return;
      // A rendered component may use a generated visual id that is not present
      // in the current graph snapshot. Interactions must always target a real
      // graph node; fall back to the host in that case.
      let targetId = componentId && nodeById.has(componentId) ? componentId : id;
      // The floor itself is not a graph node.  Resolve a floor hit to the
      // room whose support surface was hit so a held object can be placed on
      // the floor using the same generic room placement action.
      if (hit.object.userData.simulationSurface && !nodeById.has(targetId)) {
        targetId = roomEntries.find(([, room]) => {
          const minX = room.grid_x * cell;
          const minZ = room.grid_y * cell;
          return hit.point.x >= minX && hit.point.x <= minX + room.width_cells * cell
            && hit.point.z >= minZ && hit.point.z <= minZ + room.depth_cells * cell;
        })?.[0] || simulation.roomId;
      }
      const point = hit.point;
      const interactionHit = interactionHitFromIntersection(hit, targetId, simulation.roomId, raycaster);
      // Submit the same clamped/grid-snapped surface anchor that the preview
      // displayed. Raw ray UV can lie on an edge where the held footprint no
      // longer fits, causing the backend to reject a visibly valid preview.
      if (surfacePlacement && placementPreviewAnchor) {
        interactionHit.surface_uv = placementPreviewAnchor;
        if (import.meta.env.DEV) {
          console.debug("Placement submit anchor", {
            object_id: activeInteractionHand === "left" ? heldByHand.left : heldByHand.right,
            target_id: targetId,
            surface_uv: placementPreviewAnchor,
          });
        }
      }
      const interactionRequest = {
        targetId,
        hand: activeInteractionHand,
        input: "interact_primary" as const,
        hit: interactionHit,
        event: inputEvent("key", "pressed", ++inputSequenceRef.current, { code: activeInteractionHand === "left" ? "KeyQ" : "KeyE" }, "", simulationActorId),
      };
      if (targetId === "door_entrance") {
        console.info("Door interaction state", {
          target_id: targetId,
          visual_is_open: (nodeById.get(targetId)?.states as Record<string, unknown> | undefined)?.is_open,
        });
      }
      void Promise.resolve(dispatchInteraction(interactionRequest)).then((response) => {
        const result = response as Record<string, unknown> | undefined;
        if (!result || result.applied !== true) return;
        const action = result.action as Record<string, unknown> | undefined;
        if (targetId === "door_entrance") {
          console.info("Door interaction result", {
            action,
            delta: result.delta,
            snapshot_is_open: ((result.snapshot as Record<string, unknown> | undefined)?.nodes as RawNode[] | undefined)
              ?.find((node) => text(node.id) === targetId)?.states,
          });
        }
        const actionName = String(action?.action || "");
        const objectId = String(action?.object || "");
        const hand = String(action?.hand || activeInteractionHand).toLowerCase() === "left" ? "left" : "right";
        if (actionName === "pick" && objectId) heldOverride.set(objectId, hand);
        if ((actionName === "place" || actionName === "release") && objectId) heldOverride.delete(objectId);
        if (actionName === "place" && import.meta.env.DEV) {
          const placed = ((result.snapshot as Record<string, unknown> | undefined)?.nodes as RawNode[] | undefined)
            ?.find((node) => text(node.id) === objectId);
          console.debug("Placement result", {
            object_id: objectId,
            target_id: action?.target,
            world_transform: placed?.world_transform,
            placement_transform: placed?.placement_transform,
            transform_space: placed?.transform_space,
          });
        }
        syncHeldVisuals();
        if (import.meta.env.DEV) {
          console.debug("Interaction action visual sync", {
            action: actionName,
            object_id: objectId,
            hand,
            target_id: targetId,
            mesh_exists: objectId ? objectMeshes.has(objectId) : false,
          });
        }
      });
      if (surfacePlacement && placementPreview) {
        placementPreview.visible = false;
      }
    };
    const clearPlacementPreview = () => {
      if (placementPreview) placementPreview.visible = false;
      if (placementHighlight) placementHighlight.visible = false;
      placementPreviewAnchor = null;
      placementPreviewObject = "";
    };
    const clearInteractionHighlight = () => {
      if (interactionHighlight) interactionHighlight.visible = false;
      if (slotHintKeyRef.current) {
        slotHintKeyRef.current = "";
        setSlotHint(null);
      }
    };
    const updateInteractionHighlight = (hit?: THREE.Intersection<THREE.Object3D>) => {
      if (!simulation.active || !hit || hit.object.userData.simulationSurface) {
        clearInteractionHighlight();
        return;
      }
      const id = text(hit.object.userData.componentId) || objectIdForHit(hit.object, objectMeshes) || text(hit.object.userData.id);
      if (!id || heldVisualIds.has(id)) {
        clearInteractionHighlight();
        return;
      }
      const target = hit.object.userData.componentId ? hit.object : objectMeshes.get(id) ?? hit.object;
      const isSlot = text(target.userData.componentRole) === "storage_slot"
        || text(hit.object.userData.componentRole) === "storage_slot";
      if (isSlot) {
        const slotNode = nodeById.get(id);
        const stack = Array.isArray(slotNode?.storage_stack) ? slotNode.storage_stack : [];
        const count = stack.length || (receptacleContents.get(id)?.length ?? 0);
        const capacity = Number(slotNode?.max_items ?? slotNode?.max_capacity ?? target.userData.maxCapacity ?? 0) || 0;
        const hintKey = `${id}:${count}:${capacity}`;
        if (slotHintKeyRef.current !== hintKey) {
          slotHintKeyRef.current = hintKey;
          setSlotHint({ count, capacity });
        }
      } else if (slotHintKeyRef.current) {
        slotHintKeyRef.current = "";
        setSlotHint(null);
      }
      if (!interactionHighlight) {
        interactionHighlight = new THREE.BoxHelper(target, 0xfacc15);
        interactionHighlight.userData.layer = "objects";
        scene.add(interactionHighlight);
      }
      interactionHighlight.setFromObject(target);
      interactionHighlight.visible = true;
    };
    const updatePlacementPreview = (hit?: THREE.Intersection<THREE.Object3D>) => {
      if (!simulation.active || !hit) {
        clearPlacementPreview();
        return;
      }
      // A slot can be hit on its transparent plane or on a nested mesh. Walk
      // the part tree so placement never falls back to the appliance/room
      // root when the actionable slot metadata lives on a parent.
      let targetSource: THREE.Object3D | null = hit.object;
      while (targetSource && !text(targetSource.userData.componentId)
        && text(targetSource.userData.componentRole) !== "storage_slot") {
        targetSource = targetSource.parent;
      }
      const componentId = text(targetSource?.userData.componentId) || text(hit.object.userData.componentId);
      const objectId = objectIdForHit(hit.object, objectMeshes);
      const targetId = componentId || objectId || text(hit.object.userData.id);
      const targetObject = componentId ? (targetSource ?? hit.object) : objectMeshes.get(objectId) ?? hit.object;
      const canReceive = Boolean(targetObject.userData.canReceive)
        || Boolean(hit.object.userData.simulationSurface)
        || text(targetObject.userData.componentRole) === "storage_slot"
        || text(targetObject.userData.componentRole) === "support_surface";
      const preferredHeld = activeInteractionHand === "left" ? heldByHand.left : heldByHand.right;
      const heldId = preferredHeld || (activeInteractionHand === "left" ? heldByHand.right : heldByHand.left);
      const heldMesh = heldId ? objectMeshes.get(heldId) : undefined;
      if (!canReceive || !heldMesh || !targetId || heldId === targetId) {
        clearPlacementPreview();
        return;
      }
      if (!placementPreview) {
        const size = new THREE.Vector3();
        heldMesh.geometry.computeBoundingBox();
        heldMesh.geometry.boundingBox?.getSize(size);
        placementPreview = new THREE.Mesh(
          new THREE.BoxGeometry(Math.max(0.04, size.x), Math.max(0.04, size.y), Math.max(0.04, size.z)),
          new THREE.MeshStandardMaterial({ color: 0x22c55e, transparent: true, opacity: 0.28, depthWrite: false }),
        );
        placementPreview.userData.layer = "objects";
        scene.add(placementPreview);
      }
      const heldSize = new THREE.Vector3();
      heldMesh.geometry.computeBoundingBox();
      heldMesh.geometry.boundingBox?.getSize(heldSize);
      if (placementPreviewObject !== heldId) {
        placementPreview.geometry.dispose();
        placementPreview.geometry = new THREE.BoxGeometry(
          Math.max(0.04, heldSize.x), Math.max(0.04, heldSize.y), Math.max(0.04, heldSize.z),
        );
        placementPreviewObject = heldId ?? "";
      }
      const normal = hit.face?.normal?.clone().transformDirection(hit.object.matrixWorld) ?? new THREE.Vector3(0, 1, 0);
      const up = Math.abs(normal.y) >= 0.7;
      const surfacePoint = hit.point.clone();
      if (up) {
        const bounds = new THREE.Box3().setFromObject(targetObject);
        const grid = Math.max(0.01, Number(targetObject.userData.surfaceGridCm ?? 1) / 100);
        const placement = surfacePlacementPosition(surfacePoint, bounds, heldSize, grid);
        surfacePoint.copy(placement.position);
        // Use authored centimetre dimensions here, matching the backend
        // footprint solver. The rendered Box3 may include visual shells,
        // rotation padding, or generated geometry and must not define the
        // semantic placement limits.
        const targetNode = nodeById.get(targetId);
        const heldNode = heldId ? nodeById.get(heldId) : undefined;
        const targetSize = Array.isArray((targetNode as RawNode | undefined)?.surface_spec)
          ? undefined
          : ((targetNode as RawNode | undefined)?.surface_spec as Record<string, unknown> | undefined);
        const targetDims = (targetNode?.dimensions_cm ?? targetNode?.bounds_cm ?? targetNode?.size_cm) as unknown;
        const heldDims = (heldNode?.footprint_cm ?? heldNode?.dimensions_cm ?? heldNode?.bounds_cm ?? heldNode?.size_cm) as unknown;
        const surfaceWidthCm = Number(targetSize?.width_cm) > 0
          ? Number(targetSize?.width_cm)
          : Array.isArray(targetDims) ? Number(targetDims[0]) : 0;
        const surfaceDepthCm = Number(targetSize?.depth_cm) > 0
          ? Number(targetSize?.depth_cm)
          : Array.isArray(targetDims) ? Number(targetDims[1]) : 0;
        const itemWidthCm = Array.isArray(heldDims) ? Number(heldDims[0]) : heldSize.x * 100;
        const itemDepthCm = Array.isArray(heldDims) ? Number(heldDims[1]) : heldSize.z * 100;
        const rawU = (surfacePoint.x - bounds.min.x) / Math.max(1e-6, bounds.max.x - bounds.min.x);
        const rawV = (surfacePoint.z - bounds.min.z) / Math.max(1e-6, bounds.max.z - bounds.min.z);
        if (surfaceWidthCm > 0 && surfaceDepthCm > 0 && itemWidthCm > 0 && itemDepthCm > 0) {
          const gridCm = Number(targetSize?.grid_size_cm) > 0 ? Number(targetSize?.grid_size_cm) : 1;
          const snap = (value: number, sizeCm: number) => Math.round(value * sizeCm / gridCm) * gridCm / sizeCm;
          const halfU = itemWidthCm / (2 * surfaceWidthCm);
          const halfV = itemDepthCm / (2 * surfaceDepthCm);
          placementPreviewAnchor = [
            THREE.MathUtils.clamp(snap(rawU, surfaceWidthCm), halfU, 1 - halfU),
            THREE.MathUtils.clamp(snap(rawV, surfaceDepthCm), halfV, 1 - halfV),
          ];
        } else {
          placementPreviewAnchor = [
            THREE.MathUtils.clamp((surfacePoint.x - bounds.min.x) / Math.max(1e-6, bounds.max.x - bounds.min.x), 0, 1),
            THREE.MathUtils.clamp((surfacePoint.z - bounds.min.z) / Math.max(1e-6, bounds.max.z - bounds.min.z), 0, 1),
          ];
        }
        const previewMaterial = placementPreview.material as THREE.MeshStandardMaterial;
        previewMaterial.color.setHex(placement.fits ? 0x22c55e : 0xef4444);
      }
      else {
        placementPreviewAnchor = null;
        surfacePoint.add(normal.multiplyScalar(heldSize.z / 2));
      }
      placementPreview.position.copy(surfacePoint);
      placementPreview.quaternion.copy(heldMesh.quaternion);
      placementPreview.visible = true;
      if (import.meta.env.DEV) {
        console.debug("Placement preview", {
          object_id: heldId,
          target_id: targetId,
          position_three: [surfacePoint.x, surfacePoint.y, surfacePoint.z],
          surface_uv: placementPreviewAnchor,
        });
      }
      if (!placementHighlight) {
        placementHighlight = new THREE.BoxHelper(targetObject, 0x22c55e);
        placementHighlight.userData.layer = "objects";
        scene.add(placementHighlight);
      }
      placementHighlight.setFromObject(targetObject);
      placementHighlight.visible = true;
    };
    function findSimulationHit() {
      const targets = [...interactive, ...objectMeshes.values()].filter((item, index, all) => all.indexOf(item) === index);
      return chooseSimulationHit(raycaster.intersectObjects(targets, true)
        .filter((candidate) => {
          let current: THREE.Object3D | null = candidate.object;
          while (current) {
            if (heldVisualIds.has(String(current.userData.id || ""))) return false;
            current = current.parent;
          }
          return true;
        }), { objectMeshes });
    }
    const onPointerDown = (event: PointerEvent) => {
      if (event.button !== 0) return;
      if (simulation.active && document.pointerLockElement !== renderer.domElement) {
        renderer.domElement.requestPointerLock();
        return;
      }
      if (gizmoLock.active) return;
      dragState.pointerId = event.pointerId;
      dragState.startX = event.clientX;
      dragState.startY = event.clientY;
      dragState.moved = false;
      dragState.hit = false;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.copy(simulation.active ? new THREE.Vector2(0, 0) : normalizedPointer(event, renderer.domElement));
      setRayFromPointer(raycaster, camera, pointer);

      // TransformControls registers its native pointer listener before this
      // editor listener. If it accepted a gizmo press, it is already dragging
      // and owns the gesture. Checking `axis` here is too broad: picker meshes
      // can retain an axis hit outside the visible handle and swallow normal
      // object clicks.
      if (!simulation.active && (transformControls.dragging || rotationControls.dragging)) {
        dragState.id = "";
        dragState.hit = true;
        gizmoLock.active = true;
        return;
      }

      if (!simulation.active) renderer.domElement.setPointerCapture(event.pointerId);
      const hits = raycaster.intersectObjects(interactive, true).filter((candidate) => !heldIds.has(String(candidate.object.userData.id || "")));
      // Prefer the nearest actual object mesh. The floor is only a target in
      // simulation mode; it must never become an editor selection.
      const objectHit = hits.find((candidate) => objectIdForHit(candidate.object, objectMeshes));
      // Component affordances (drain, faucet, buttons, rack slots) are the
      // actionable surface even when their transparent host mesh is closer.
      const hit = simulation.active
        ? chooseSimulationHit(hits, { objectMeshes })
        : objectHit;
      // A ray can hit a composite child (shell panel, lamp, shelf, etc.)
      // whose own userData has no id. Resolve through its parent chain before
      // rejecting the hit; objectIdForHit is the canonical editor-root lookup.
      const hitId = hit ? objectIdForHit(hit.object, objectMeshes) : "";
      if (!hit || (!hitId && !hit.object.userData.id)) {
        dragState.id = "";
        if (simulation.active) setStatusCardId("");
        return;
      }
      const id = hitId || String(hit.object.userData.id || "");
      if (simulation.active) {
        // A floor or wall click dismisses the current device/status overlay.
        if (hit.object.userData.simulationSurface || id === "__floor__" || !nodeById.has(id)) {
          const heldForCurrentHand = edges.some((edge) => {
            const relation = text(edge.relation || edge.edge_type);
            return text(edge.source_id || edge.source) === simulationActorId
              && (relation === "held_by" || relation === "held_by_right" || relation === "held_by_left" || relation === "held_by_both");
          });
          if (heldForCurrentHand) simulationClick(hit, true);
          setStatusCardId("");
          dragState.hit = false;
          return;
        }
        // A PartTree child is a graph node in its own right (for example an
        // elevator floor button).  Prefer that node for the status card rather
        // than promoting every hit to the composite/root object.  Generated
        // visual affordances may still use a synthetic component id (such as
        // ``elevator_car.floor_buttons``), so only select it when it resolves
        // to an actual node; otherwise fall back to its explicit host/root.
        const componentId = text(hit.object.userData.componentId);
        const hostId = text(hit.object.userData.hostId) || componentHostById.get(componentId) || "";
        const cardId = (componentId && nodeById.has(componentId) ? componentId : "")
          || controlTargets.get(id)?.[0]
          || hostId
          || id;
        if (nodeById.has(cardId)) {
          setStatusCardId(cardId);
          selectRef.current(cardId);
        }
        dragState.hit = true;
        return;
      }
      // The elevator car is a runtime transport asset. Its position and
      // articulation are controlled by the elevator process, so it is never
      // an editor drag/rotation target.
      if (semantic(nodeById.get(id)) === "elevator") {
        dragState.id = "";
        dragState.hit = false;
        return;
      }
      simulationClick(hit);
      if (onInteractionHit) {
        onInteractionHit(interactionHitFromIntersection(hit, id, undefined, raycaster));
      }
      dragState.hit = true;
      selectRef.current(id);
      const item = layout.objects[id];
      if (item && !simulation.active) {
        const hostMesh = objectMeshes.get(id);
        if (hostMesh) {
          transformControls.attach(hostMesh);
          rotationControls.attach(hostMesh);
          // Every placeable node is an editor root. Composite objects use the
          // host mesh as their root; leaf objects simply use their own mesh.
          // Start a normal object drag as well as attaching the gizmos so a
          // click-drag on the object body remains an editing gesture.
          dragState.id = id;
          dragState.roomId = item.room_id;
          dragState.gridX = item.grid_x;
          dragState.gridY = item.grid_y;
        }
      }
    };
    const onPointerMove = (event: PointerEvent) => {
      if (simulation.active) {
        pointer.set(0, 0);
        setRayFromPointer(raycaster, camera, pointer);
        updatePlacementPreview(findSimulationHit());
        return;
      }
      if (!dragState.id) return;
      if (Math.hypot(event.clientX - dragState.startX, event.clientY - dragState.startY) > 3) dragState.moved = true;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.copy(normalizedPointer(event, renderer.domElement));
      setRayFromPointer(raycaster, camera, pointer);
      if (!raycaster.ray.intersectPlane(dragPlane, dragPoint)) return;
      const room = layout.rooms[dragState.roomId];
      const item = layout.objects[dragState.id];
      const mesh = objectMeshes.get(dragState.id);
      if (!room || !item || !mesh) return;
      const roomXcm = (room.x_cm ?? room.grid_x * cell * 100);
      const roomYcm = (room.y_cm ?? room.grid_y * cell * 100);
      const widthCm = item.width_cm ?? item.width_cells * cell * 100;
      const depthCm = item.depth_cm ?? item.depth_cells * cell * 100;
      const nextXcm = Math.max(0, Math.min(room.width_cells * cell * 100 - widthCm, Math.round((dragPoint.x * 100 - roomXcm - widthCm / 2) / 10) * 10));
      const nextYcm = Math.max(0, Math.min(room.depth_cells * cell * 100 - depthCm, Math.round((dragPoint.z * 100 - roomYcm - depthCm / 2) / 10) * 10));
      mesh.position.x = (roomXcm + nextXcm) / 100 + mesh.geometry.boundingBox?.max.x!;
      mesh.position.z = (roomYcm + nextYcm) / 100 + mesh.geometry.boundingBox?.max.z!;
      // Keep composite children (buttons, lamps, doors, drawers, shelves)
      // aligned with their host while the editor-root mesh is dragged.
      syncCompositeFor(dragState.id);
      dragState.gridX = Math.round(nextXcm / (cell * 100));
      dragState.gridY = Math.round(nextYcm / (cell * 100));
      (dragState as typeof dragState & { xCm?: number; yCm?: number }).xCm = roomXcm + nextXcm;
      (dragState as typeof dragState & { xCm?: number; yCm?: number }).yCm = roomYcm + nextYcm;
    };
    const onPointerUp = () => {
      if (gizmoLock.active && !transformControls.dragging && !rotationControls.dragging) {
        gizmoLock.active = false;
        transformControls.enabled = true;
        rotationControls.enabled = true;
      }
      if (simulation.active) {
        dragState.hit = false;
        return;
      }
      if (lastRotationObject && !rotationControls.dragging) commitRotation();
      if (!dragState.id) {
        if (!dragState.hit) selectRef.current("");
        dragState.hit = false;
        return;
      }
      // A stationary left click is selection-only. Updating the layout here
      // would remount the scene and make the camera visibly jump.
      if (!dragState.moved) {
        dragState.id = "";
        dragState.pointerId = -1;
        dragState.hit = false;
        controls.enabled = true;
        return;
      }
      const next = structuredClone(layout);
      const coordinates = dragState as typeof dragState & { xCm?: number; yCm?: number };
      next.objects[dragState.id] = { ...next.objects[dragState.id], grid_x: dragState.gridX, grid_y: dragState.gridY, x_cm: coordinates.xCm, y_cm: coordinates.yCm };
      changeRef.current(next);
      dragState.id = "";
      dragState.pointerId = -1;
      dragState.hit = false;
      controls.enabled = true;
    };
    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("pointermove", onPointerMove);
    renderer.domElement.addEventListener("pointerup", onPointerUp);
    const resize = () => {
      if (!host.clientWidth || !host.clientHeight) return;
      camera.aspect = host.clientWidth / host.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(host.clientWidth, host.clientHeight);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    const sendMovement = (direction: [number, number], elapsedSeconds: number): void => {
      if (moveInFlightRef.current) {
        const pending = pendingMoveRef.current;
        const previousElapsed = pending?.elapsed ?? 0;
        const totalElapsed = previousElapsed + elapsedSeconds;
        const previousDirection = pending?.direction ?? [0, 0];
        pendingMoveRef.current = {
          direction: [
            (previousDirection[0] * previousElapsed + direction[0] * elapsedSeconds) / Math.max(totalElapsed, 1e-6),
            (previousDirection[1] * previousElapsed + direction[1] * elapsedSeconds) / Math.max(totalElapsed, 1e-6),
          ],
          elapsed: totalElapsed,
        };
        return;
      }
      moveInFlightRef.current = true;
      let releaseMovement: () => void = () => undefined;
      movementBarrierRef.current = new Promise<void>((resolve) => { releaseMovement = resolve; });
      void simulationMoveRef.current(
        { x: simulation.player.x, y: simulation.player.y, z: simulation.player.z },
        direction,
        elapsedSeconds,
        inputEvent("movement", "sampled", ++inputSequenceRef.current, { position: { x: simulation.player.x, y: simulation.player.y, z: simulation.player.z }, direction, elapsed_seconds: elapsedSeconds }, "", simulationActorId),
      ).then((response) => {
        const result = response as Record<string, unknown> | void;
        if (!result) return;
        const responseDelta = (result.delta && typeof result.delta === "object" ? result.delta : {}) as Record<string, unknown>;
        const snapshot = (result.snapshot && typeof result.snapshot === "object" ? result.snapshot : {}) as Record<string, unknown>;
        const worldState = (snapshot.world_state && typeof snapshot.world_state === "object" ? snapshot.world_state : {}) as Record<string, unknown>;
        const agents = (worldState.agents && typeof worldState.agents === "object" ? worldState.agents : {}) as Record<string, Record<string, unknown>>;
        let actor = (responseDelta.agent && typeof responseDelta.agent === "object" ? (responseDelta.agent as Record<string, Record<string, unknown>>)[simulationActorId] : undefined) ?? agents[simulationActorId];
        const changes = Array.isArray(responseDelta.changes) ? responseDelta.changes as Record<string, unknown>[] : [];
        const nodeChange = changes.find((change) => {
          const payload = (change.payload && typeof change.payload === "object" ? change.payload : change) as Record<string, unknown>;
          return text(payload.node_id ?? payload.id) === simulationActorId && (payload.runtime_state || payload.agent_state || payload.world_transform);
        });
        if (nodeChange) {
          const payload = (nodeChange.payload && typeof nodeChange.payload === "object" ? nodeChange.payload : nodeChange) as Record<string, unknown>;
          const runtime = (payload.runtime_state ?? payload.agent_state) as Record<string, unknown> | undefined;
          actor = { ...(actor ?? {}), ...(runtime ?? {}), ...(payload.world_transform ? { world_transform: payload.world_transform } : {}) };
        }
        const runtimePosition = actor?.position as Record<string, unknown> | undefined;
        const authoritative = runtimePosition && Number.isFinite(Number(runtimePosition.x)) && Number.isFinite(Number(runtimePosition.z))
          ? new THREE.Vector3(Number(runtimePosition.x), Number(runtimePosition.y ?? 1.6), Number(runtimePosition.z))
          : (() => {
            const transform = actor?.world_transform as Record<string, unknown> | undefined;
            const position = Array.isArray(transform?.position) ? transform.position : undefined;
            return position?.length === 3 && position.every((value) => Number.isFinite(Number(value)))
              ? new THREE.Vector3(Number(position[0]), Number(position[2]), -Number(position[1])) : null;
          })();
        if (authoritative && result.applied === false) {
          // Rapier owns the immediate local pose. A successful backend sample
          // is asynchronous and may describe an older input frame; applying
          // it here creates visible snaps and can move the player through a
          // doorway after the local controller stopped at its collider. Only
          // an explicit rejection is authoritative enough to correct the
          // local pose.
          simulation.player.copy(authoritative);
        }
        if (actor?.room_id != null) simulation.roomId = text(actor.room_id);
        if (actor?.moving != null) simulation.moving = Boolean(actor.moving);
        if (result.applied === false) console.warn("Simulation movement rejected", result.failures);
      }).catch((error) => console.warn("Simulation movement request failed", error)).finally(() => {
        moveInFlightRef.current = false;
        releaseMovement();
        const pending = pendingMoveRef.current;
        pendingMoveRef.current = null;
        if (pending && simulation.active) sendMovement(pending.direction, pending.elapsed);
      });
    };
    let frame = 0;
    const animate = () => {
      const now = performance.now();
      const delta = Math.min((now - simulation.lastFrame) / 1000, 0.05);
      if (simulation.active) {
        syncHeldVisuals();
        // Advance the cabin visual pose before querying player movement. The
        // resulting delta is the single transport motion used by Three.js,
        // Rapier, and a passenger already standing inside the cabin.
        let elevatorFrameDeltaY = 0;
        if (rapierRuntime && !rapierRuntime.disposed) {
          const elevatorMesh = [...objectMeshes.values()].find((mesh) => semantic(nodeById.get(String(mesh.userData.id))) === "elevator");
          const elevatorRoot = elevatorMesh?.userData.elevatorVisualRoot as THREE.Group | undefined;
          const elevatorNode = elevatorMesh ? nodeById.get(String(elevatorMesh.userData.id)) : undefined;
          const elevatorStates = elevatorNode?.states as Record<string, unknown> | undefined;
          if (elevatorRoot && elevatorStates) {
            elevatorRoot.updateWorldMatrix(true, true);
            const previousPosition = elevatorRoot.getWorldPosition(new THREE.Vector3());
            const targetHeight = Number(elevatorStates.current_height ?? 0);
            if (Number.isFinite(targetHeight)) {
              const baseY = Number(elevatorRoot.userData.elevatorBaseY ?? elevatorRoot.position.y);
              const currentHeight = Number(elevatorRoot.userData.elevatorRenderHeight ?? targetHeight);
              // Runtime snapshots may advance the semantic height by a whole
              // tick.  Move the visual cabin at a fixed physical speed so a
              // snapshot cannot make it jump instantly to another floor.
              const elevatorRenderSpeedMps = 2;
              const heightDelta = targetHeight - currentHeight;
              const maxHeightStep = elevatorRenderSpeedMps * delta;
              const nextHeight = Math.abs(heightDelta) <= maxHeightStep
                ? targetHeight
                : currentHeight + Math.sign(heightDelta) * maxHeightStep;
              elevatorRoot.userData.elevatorBaseY = baseY;
              elevatorRoot.userData.elevatorRenderHeight = nextHeight;
              elevatorRoot.position.y = baseY + nextHeight;
              elevatorRoot.updateWorldMatrix(true, true);
              const nextPosition = elevatorRoot.getWorldPosition(new THREE.Vector3());
              elevatorFrameDeltaY = nextPosition.y - previousPosition.y;

              // Check the old pose before applying its movement. Cabin width
              // and depth come from the authored elevator anchor; the player
              // must be horizontally inside the shell to be transported.
              const localPlayer = simulation.player.clone().sub(previousPosition)
                .applyQuaternion(elevatorRoot.getWorldQuaternion(new THREE.Quaternion()).invert());
              const anchorSize = elevatorMesh?.geometry.boundingBox?.getSize(new THREE.Vector3()) ?? new THREE.Vector3(1.9, 2.4, 1.9);
              const cabinWidth = anchorSize.x * 0.9;
              const cabinDepth = anchorSize.z * 0.9;
              const cabinHeight = anchorSize.y * 0.96;
              const insideCabin = Math.abs(localPlayer.x) < cabinWidth * 0.5 - 0.08
                && Math.abs(localPlayer.z) < cabinDepth * 0.5 - 0.08
                && localPlayer.y > -0.2 && localPlayer.y < cabinHeight + 0.35;
              if (insideCabin && Math.abs(elevatorFrameDeltaY) > 1e-7) {
                simulation.player.y += elevatorFrameDeltaY;
              }
            }
          }
        }
        // Synchronize the kinematic cabin before querying player movement.
        // The previous order updated it after computeColliderMovement(), so
        // the controller could query a stale cabin pose and appear to pass
        // through its walls or jump when the pose caught up one frame later.
        if (rapierRuntime && !rapierRuntime.disposed && rapierRuntime.elevatorBody) {
          const elevatorMesh = [...objectMeshes.values()].find((mesh) => semantic(nodeById.get(String(mesh.userData.id))) === "elevator");
          const elevatorRoot = elevatorMesh?.userData.elevatorVisualRoot as THREE.Group | undefined;
          if (elevatorRoot) {
            elevatorRoot.updateWorldMatrix(true, true);
            const position = elevatorRoot.getWorldPosition(new THREE.Vector3());
            const rotation = elevatorRoot.getWorldQuaternion(new THREE.Quaternion());
            rapierRuntime.elevatorBody.setNextKinematicTranslation({ x: position.x, y: position.y, z: position.z });
            rapierRuntime.elevatorBody.setNextKinematicRotation({ x: rotation.x, y: rotation.y, z: rotation.z, w: rotation.w });
            const inverse = rotation.clone().invert();
            rapierRuntime.elevatorColliders.forEach((collider, mesh) => {
              // Resolve cabin-door passability from the canonical elevator
              // state before the character query. The joint animation runs
              // later in this frame, so relying only on the mesh flag here
              // leaves one stale closed-door collider at the threshold and
              // can trap the character inside an overlap.
              const elevatorNode = [...nodeById.values()].find((candidate) => semantic(candidate) === "elevator");
              const elevatorStates = elevatorNode?.states as Record<string, unknown> | undefined;
              const cabinDoor = String(mesh.userData.debugSource || "").includes("car_door_");
              const cabinPassable = elevatorStates?.is_open === true
                || elevatorStates?.door_phase === "opening"
                || elevatorStates?.door_phase === "dwelling";
              const enabled = cabinDoor ? !cabinPassable : mesh.userData.collisionEnabled !== false;
              mesh.userData.collisionEnabled = enabled;
              collider.setEnabled(enabled);
              mesh.updateWorldMatrix(true, false);
              const meshPosition = mesh.getWorldPosition(new THREE.Vector3());
              const localPosition = meshPosition.sub(position).applyQuaternion(inverse);
              const meshRotation = inverse.clone().multiply(mesh.getWorldQuaternion(new THREE.Quaternion()));
              collider.setTranslationWrtParent({ x: localPosition.x, y: localPosition.y, z: localPosition.z });
              collider.setRotationWrtParent({ x: meshRotation.x, y: meshRotation.y, z: meshRotation.z, w: meshRotation.w });
            });
            rapierRuntime.world.step();
          }
        }
        const [rightAmount, forwardAmount] = movementAxes(simulation.keys);
        const length = Math.hypot(forwardAmount, rightAmount) || 1;
        const speed = 2.2 * delta;
        const dx = ((-Math.sin(simulation.yaw) * forwardAmount) + (Math.cos(simulation.yaw) * rightAmount)) * speed / length;
        const dz = ((-Math.cos(simulation.yaw) * forwardAmount) + (-Math.sin(simulation.yaw) * rightAmount)) * speed / length;
        // The frontend physics layer owns immediate movement collision. Send
        // compact input steps so the backend can record the resulting pose.
        if (forwardAmount || rightAmount) {
            const predictedDelta = new THREE.Vector3(dx, 0, dz);
          let acceptedDelta = new THREE.Vector3();
          if (rapierRuntime && !rapierRuntime.disposed) {
            // Keep enabled state in lockstep with rendered collision meshes.
            rapierRuntime.staticColliders.forEach((collider, mesh) => {
              collider.setEnabled(mesh.userData.collisionEnabled !== false);
              if (!collider.isEnabled()) return;
              mesh.updateWorldMatrix(true, false);
              const center = new THREE.Vector3();
              mesh.getWorldPosition(center);
              const rotation = new THREE.Quaternion();
              mesh.getWorldQuaternion(rotation);
              collider.setTranslation({ x: center.x, y: center.y, z: center.z });
              collider.setRotation({ x: rotation.x, y: rotation.y, z: rotation.z, w: rotation.w });
            });
            rapierRuntime.world.step();
            // CharacterController queries the collider's current pose.  A
            // queued kinematic pose (setNextKinematicTranslation) is only
            // applied by a world step, which we intentionally do not run for
            // this render-driven controller.  Set the pose immediately before
            // querying, otherwise Rapier keeps testing the spawn position and
            // appears to have no collision at all.
            rapierRuntime.playerBody.setTranslation({ x: simulation.player.x, y: simulation.player.y - 0.76, z: simulation.player.z }, true);
            rapierRuntime.world.propagateModifiedBodyPositionsToColliders();
            rapierRuntime.controller.computeColliderMovement(
              rapierRuntime.collider,
              { x: predictedDelta.x, y: 0, z: predictedDelta.z },
            );
            const corrected = rapierRuntime.controller.computedMovement();
            acceptedDelta.set(corrected.x, corrected.y, corrected.z);
            if (import.meta.env.DEV && rapierRuntime.elevatorColliders.size > 0
              && performance.now() - lastCollisionLogAt > 1000) {
              const elevatorState = [...rapierRuntime.elevatorColliders.entries()].map(([mesh, item]) => ({
                source: mesh.userData.debugSource,
                enabled: item.isEnabled(),
                parent: item.parent()?.handle,
              }));
              console.debug("Rapier elevator collision state", {
                bodyType: rapierRuntime.elevatorBody?.bodyType(),
                colliders: elevatorState,
                player: [simulation.player.x, simulation.player.y, simulation.player.z],
              });
            }
            if (import.meta.env.DEV && rapierRuntime.controller.numComputedCollisions() > 0 && performance.now() - lastCollisionLogAt > 500) {
              lastCollisionLogAt = performance.now();
              const runtime = rapierRuntime;
              const collisionDetails = Array.from({ length: runtime.controller.numComputedCollisions() }, (_, index) => {
                const collision = runtime.controller.computedCollision(index);
                const source = collision?.collider
                  ? [...runtime.elevatorColliders.entries()].find(([, collider]) => collider.handle === collision.collider?.handle)?.[0]?.userData.debugSource
                    || [...runtime.staticColliders.entries()].find(([, collider]) => collider.handle === collision.collider?.handle)?.[0]?.userData.debugSource
                    || "unknown"
                  : "unknown";
                return {
                  source,
                  toi: collision?.toi,
                  normal1: collision?.normal1 ? [collision.normal1.x, collision.normal1.y, collision.normal1.z] : undefined,
                  normal2: collision?.normal2 ? [collision.normal2.x, collision.normal2.y, collision.normal2.z] : undefined,
                  applied: collision?.translationDeltaApplied ? [collision.translationDeltaApplied.x, collision.translationDeltaApplied.y, collision.translationDeltaApplied.z] : undefined,
                  remaining: collision?.translationDeltaRemaining ? [collision.translationDeltaRemaining.x, collision.translationDeltaRemaining.y, collision.translationDeltaRemaining.z] : undefined,
                };
              });
              // Keep a small diagnostic breadcrumb while validating the
              // physics world in the browser. It is intentionally gated to
              // development builds and never affects movement.
              console.debug("Rapier collision", {
                collisions: rapierRuntime.controller.numComputedCollisions(),
                desired: [predictedDelta.x, predictedDelta.y, predictedDelta.z],
                corrected: [corrected.x, corrected.y, corrected.z],
                collisionDetails,
                collisionSources: collisionDetails.map((detail) => detail.source),
                enabledElevatorColliders: [...rapierRuntime.elevatorColliders.entries()]
                  .filter(([, item]) => item.isEnabled())
                  .map(([mesh]) => mesh.userData.debugSource),
                player: [simulation.player.x, simulation.player.y, simulation.player.z],
              });
              // Keep a non-collapsed diagnostic for browser consoles that
              // show the object above as an opaque Array(20). This is the
              // authoritative blocking source, unlike the Three.js ray hit.
              console.debug("Rapier collision details", JSON.stringify({
                player: [simulation.player.x, simulation.player.y, simulation.player.z],
                desired: [predictedDelta.x, predictedDelta.y, predictedDelta.z],
                corrected: [corrected.x, corrected.y, corrected.z],
                details: collisionDetails,
              }));
            }
          }
          if (acceptedDelta.lengthSq() > 0) {
            // Prediction is a render concern and must run at the display frame
            // rate. Network sampling below is deliberately slower.
            simulation.player.x += acceptedDelta.x;
            simulation.player.z += acceptedDelta.z;
            const nowMs = performance.now();
            if (nowMs - lastMoveRequestRef.current >= 100) {
              const sampleElapsed = lastMoveRequestRef.current > 0
                ? Math.min((nowMs - lastMoveRequestRef.current) / 1000, 0.1)
                : Math.min(delta, 0.1);
              lastMoveRequestRef.current = nowMs;
              const direction: [number, number] = [acceptedDelta.x / Math.max(delta, 1e-6), acceptedDelta.z / Math.max(delta, 1e-6)];
              sendMovement(direction, sampleElapsed);
            }
          } else if (rapierRuntime) {
            simulation.moving = false;
          }
        }
        if (rapierRuntime) {
          rapierRuntime.playerBody.setNextKinematicTranslation({ x: simulation.player.x, y: simulation.player.y - 0.76, z: simulation.player.z });
          rapierRuntime.world.propagateModifiedBodyPositionsToColliders();
        }
        playerBody.position.set(simulation.player.x, simulation.player.y - 0.8, simulation.player.z);
        playerBody.rotation.y = simulation.yaw;
        playerBody.visible = viewModeRef.current === "third";
        const third = viewModeRef.current === "third";
        const cameraTarget = simulation.player.clone();
        if (third) {
          camera.position.copy(simulation.player).add(new THREE.Vector3(Math.sin(simulation.yaw) * 2.8, 1.1, Math.cos(simulation.yaw) * 2.8));
          cameraTarget.add(new THREE.Vector3(-Math.sin(simulation.yaw) * Math.cos(simulation.pitch), Math.sin(simulation.pitch) + 0.25, -Math.cos(simulation.yaw) * Math.cos(simulation.pitch)));
        } else {
          camera.position.copy(simulation.player);
        }
        if (third) {
          camera.lookAt(cameraTarget);
        } else {
          camera.rotation.set(simulation.pitch, simulation.yaw, 0, "YXZ");
        }
        // First-person orientation is assigned directly each frame. Refresh
        // the world matrix before using the center ray so it never queries
        // the previous editor-camera direction.
        camera.updateMatrixWorld(true);
        pointer.set(0, 0);
        setRayFromPointer(raycaster, camera, pointer);
        const currentHit = findSimulationHit();
        if (import.meta.env.DEV) {
          const debugHitId = currentHit
            ? (text(currentHit.object.userData.componentId) || objectIdForHit(currentHit.object, objectMeshes) || text(currentHit.object.userData.id) || "surface")
            : "";
          if (debugHitId !== lastDebugHitId) {
            lastDebugHitId = debugHitId;
            console.debug("Scene ray target", debugHitId || "none", {
              origin: [raycaster.ray.origin.x, raycaster.ray.origin.y, raycaster.ray.origin.z],
              direction: [raycaster.ray.direction.x, raycaster.ray.direction.y, raycaster.ray.direction.z],
              camera: [camera.position.x, camera.position.y, camera.position.z],
              targetCount: interactive.length + objectMeshes.size,
            });
          }
          // Room/shaft walls intentionally live only in the collision index:
          // they are not interaction targets. Report the collider separately
          // so a ray hitting an outer elevator wall is diagnosable without
          // turning that wall into a backend Action target.
          const colliderHit = raycaster.intersectObjects(collisionMeshes, true)
            .find((candidate) => candidate.object.userData.collisionEnabled !== false);
          let colliderSource = "";
          if (colliderHit) {
            let source: THREE.Object3D | null = colliderHit.object;
            while (source && !source.userData.debugSource) source = source.parent;
            colliderSource = text(source?.userData.debugSource)
              || text(colliderHit.object.userData.id)
              || "collider";
          }
          if (colliderSource !== lastDebugColliderId) {
            lastDebugColliderId = colliderSource;
            console.debug("Scene ray collider", colliderSource || "none", colliderHit ? {
              distance: colliderHit.distance,
              object: colliderHit.object.name,
            } : undefined);
          }
        }
        updateInteractionHighlight(currentHit);
        updatePlacementPreview(currentHit);
        const handPose = (hand: THREE.Mesh, left: boolean, raised: boolean) => {
          const side = left ? -1 : 1;
          camera.updateMatrixWorld();
          // simulation.player is the head/camera height (1.6m). Arms must be
          // driven from the visible body capsule, whose center is at 0.8m.
          const bodyOrigin = playerBody.position.clone();
          const target = third
            ? bodyOrigin.clone().add(new THREE.Vector3(
              side * (raised ? 0.34 : 0.26),
              raised ? 1.05 : 0.72,
              -0.18,
            ).applyAxisAngle(new THREE.Vector3(0, 1, 0), simulation.yaw))
            : camera.position.clone().add(new THREE.Vector3(
              side * (raised ? 0.3 : 0.22), raised ? -0.05 : -0.2, -0.48,
            ).applyQuaternion(camera.quaternion));
          const anchor = handAnchors[left ? "left" : "right"];
          anchor.position.lerp(target, Math.min(1, delta * 12));
          anchor.quaternion.copy(third ? new THREE.Quaternion().setFromEuler(new THREE.Euler(0, simulation.yaw, 0)) : camera.quaternion);
          hand.position.copy(anchor.position);
          hand.quaternion.copy(anchor.quaternion);
          const shoulder = third
            ? bodyOrigin.clone().add(new THREE.Vector3(side * 0.22, 0.45, -0.05).applyAxisAngle(new THREE.Vector3(0, 1, 0), simulation.yaw))
            : camera.position.clone().add(new THREE.Vector3(side * 0.14, -0.16, -0.08).applyQuaternion(camera.quaternion));
          const rod = arms[left ? "left" : "right"];
          const armVector = anchor.position.clone().sub(shoulder);
          const armLength = Math.min(0.75, armVector.length());
          if (armLength > 1e-4) {
            const armEnd = shoulder.clone().add(armVector.normalize().multiplyScalar(armLength));
            anchor.position.copy(armEnd);
            hand.position.copy(armEnd);
            rod.position.copy(shoulder).add(armEnd).multiplyScalar(0.5);
            rod.scale.set(1, armLength, 1);
            rod.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), armEnd.clone().sub(shoulder).normalize());
          }
          const pointerLocked = document.pointerLockElement === renderer.domElement;
          hand.visible = pointerLocked;
          rod.visible = pointerLocked;
        };
        // Only the hand that owns the held object enters the raised pose.
        // The other hand must stay at its resting joint angle.
        handPose(hands.left, true, handsRef.current.left || Boolean(heldByHand.left));
        handPose(hands.right, false, handsRef.current.right || Boolean(heldByHand.right));
      } else {
        controls.update();
      }
      simulation.lastFrame = now;
      const time = performance.now() / 1000;
      animatedMeshes.forEach(({ mesh, base, baseRotation }, id) => {
        const node = nodeById.get(id);
        const nodeStates = node?.states as Record<string, unknown> | undefined;
        const nodeSemantic = semantic(node);
        const cues = visualCuesOf(node);
        if (nodeSemantic === "sink") {
          const legacyFill = nodeStates?.fill_level == null ? null : Number(nodeStates.fill_level);
          const waterLevel = Number(nodeStates?.water_level ?? (legacyFill == null ? (nodeStates?.has_water ? 100 : 0) : legacyFill * 100));
          const level = THREE.MathUtils.clamp(waterLevel / 100, 0, 1);
          const filled = level > 0;
          mesh.visible = filled;
          const wave = filled ? 1 + Math.sin(time * 2.8) * 0.012 : 1;
          mesh.scale.set(wave, Math.max(0.02, level), wave);
          const waterHeight = dimensionsFor(id).height;
          mesh.position.set(base.x, filled ? waterHeight * (0.05 + 0.225 * level) + Math.sin(time * 2) * 0.003 : -0.035, base.z);
          return;
        }
        const running = cues.has("running_pulse") || cues.has("airflow") || Boolean(nodeStates?.is_running);
        const falling = cues.has("falling") || node?.physics_state === "falling";
        if (!running && !falling) {
          mesh.position.copy(base);
          mesh.rotation.copy(baseRotation);
          return;
        }
        if (falling) {
          const drop = Number(node?.drop_height_cm ?? 0) / 100;
          mesh.position.set(base.x, Math.max(mesh.geometry.boundingBox?.max.y ?? 0.02, base.y - drop), base.z);
          return;
        }
        const pulse = Math.sin(time * 24 + id.length) * 0.018;
        mesh.position.set(base.x + pulse, base.y, base.z - pulse * 0.7);
        mesh.rotation.copy(baseRotation);
        mesh.rotation.z += Math.sin(time * 18 + id.length) * (nodeSemantic === "washer" || nodeSemantic === "washing_machine" ? 0.028 : 0.012);
        if (running && (nodeSemantic === "washer" || nodeSemantic === "washing_machine")) {
          // The root mesh is the existing PartTree host. Rotating it moves all
          // authored doors, drawer, panel, and cavity parts together.
          const composite = composites.find((entry) => entry.id === id);
          if (composite?.host && composite.host !== mesh) {
            composite.host.rotation.copy(baseRotation);
            composite.host.rotation.z += Math.sin(time * 18 + id.length) * 0.028;
          }
        }
        mesh.scale.set(1, 1, 1);
      });
      // Runtime state deltas can change clothing after the initial scene
      // build. Keep the material as a pure projection of the canonical state
      // instead of relying on the construction-time color.
      objectMeshes.forEach((mesh, id) => {
        const node = nodeById.get(id);
        if (semantic(node) !== "clothes") return;
        const states = node?.states as Record<string, unknown> | undefined;
        const material = Array.isArray(mesh.material) ? mesh.material[0] : mesh.material;
        if (!(material instanceof THREE.MeshStandardMaterial)) return;
        if (states?.is_wet === true) material.color.setHex(0x38a3c7);
        else if (states?.is_dirty === true) material.color.setHex(0x8b6b52);
        else material.color.setHex(0x94a3b8);
        material.roughness = states?.is_wet === true ? 0.3 : 0.72;
        material.emissive.setHex(states?.folded === true ? 0x334155 : 0x000000);
        material.emissiveIntensity = states?.folded === true ? 0.22 : 0;
        material.needsUpdate = true;
      });
      detergentVisuals.forEach(({ bottle, liquid }, id) => {
        const detergent = nodeById.get(id);
        const states = detergent?.states as Record<string, unknown> | undefined;
        const amount = THREE.MathUtils.clamp(Number(states?.amount ?? 1), 0, 1);
        bottle.visible = Boolean(detergent);
        if (detergent) {
          const size = liquid.geometry.boundingBox?.getSize(new THREE.Vector3()) ?? new THREE.Vector3(0.04, 0.08, 0.03);
          liquid.scale.y = Math.max(0.02, amount);
          liquid.position.y = -size.y * 0.42 + size.y * 0.36 * amount;
        }
      });
      lightMeshes.forEach((light, id) => {
        const node = nodeById.get(id);
        const states = node?.states as Record<string, unknown> | undefined;
        const enabled = visualCuesOf(node).has("emissive") || Boolean(states?.is_on);
        light.intensity = enabled ? 2.2 : 0;
        light.visible = enabled;
        // Keep the lamp mesh in sync with the authoritative runtime state.
        // The material is created once, while button interactions update the
        // node state through simulation deltas after creation.
        const lampMesh = objectMeshes.get(id);
        if (lampMesh) {
          const materials = Array.isArray(lampMesh.material) ? lampMesh.material : [lampMesh.material];
          materials.forEach((material) => {
            if (!(material instanceof THREE.MeshStandardMaterial
              || material instanceof THREE.MeshPhysicalMaterial
              || material instanceof THREE.MeshPhongMaterial
              || material instanceof THREE.MeshLambertMaterial)) return;
            material.emissive.set(0xffd166);
            material.emissiveIntensity = enabled ? 0.85 : 0;
            material.needsUpdate = true;
          });
        }
      });
      // Switch/button illumination is a semantic state, not a light-node
      // special case. This covers hall call buttons and cabin floor buttons.
      const syncButtonMaterial = (mesh: THREE.Mesh, pressed: boolean) => {
        const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        materials.forEach((material) => {
          if (!(material instanceof THREE.MeshStandardMaterial
            || material instanceof THREE.MeshPhysicalMaterial
            || material instanceof THREE.MeshPhongMaterial
            || material instanceof THREE.MeshLambertMaterial)) return;
          material.emissive.set(0xffb000);
          material.emissiveIntensity = pressed ? 1.4 : 0.08;
          material.needsUpdate = true;
        });
      };
      objectMeshes.forEach((mesh, id) => {
        const node = nodeById.get(id);
        const componentRole = text(node?.component_role);
        const isElevatorButton = Boolean(node?.request_floor || node?.request_kind)
          || componentRole === "hall_call_button"
          || componentRole === "floor_button";
        if (semantic(node) === "button" && isElevatorButton) {
          const states = node?.states as Record<string, unknown> | undefined;
          syncButtonMaterial(mesh, states?.is_pressed === true || states?.is_on === true);
        }
      });
      elevatorButtonMeshes.forEach((mesh, id) => {
        const node = nodeById.get(id);
        const states = node?.states as Record<string, unknown> | undefined;
        syncButtonMaterial(mesh, states?.is_pressed === true || states?.is_on === true);
      });
      componentVisuals.forEach((mesh, id) => {
        const componentNode = nodeById.get(id);
        if (semantic(componentNode) !== "button") return;
        const states = componentNode?.states as Record<string, unknown> | undefined;
        if (mesh instanceof THREE.Mesh) syncButtonMaterial(mesh, states?.is_pressed === true);
      });
      composites.forEach((composite) => {
        const hostNode = nodeById.get(composite.id);
        const hostStates = hostNode?.states as Record<string, unknown> | undefined;
        const hostJointStates = hostNode?.joint_states as Record<string, unknown> | undefined;
        composite.joints.forEach((joint) => {
          const componentNode = nodeById.get(joint.id);
          const states = componentNode?.states as Record<string, unknown> | undefined;
          const componentJointStates = componentNode?.joint_states as Record<string, unknown> | undefined;
          const runtimeJointValue = componentJointStates?.[joint.id]
            ?? componentJointStates?.[composite.id]
            ?? hostJointStates?.[joint.id]
            ?? hostJointStates?.[composite.id];
          if (runtimeJointValue !== undefined) {
            applyRuntimeJointState(joint, runtimeJointValue);
          } else {
            joint.progressOverride = undefined;
            // Runtime state is canonical, but snapshots may contain values
            // decoded from generic JSON sources. Do not let the string
            // "false" become truthy and leave a closed door passable.
            const rawOpen = states?.is_open ?? hostStates?.is_open;
            const requestedOpen = rawOpen === true || rawOpen === 1 || rawOpen === "true";
            // Landing doors are driven by the same elevator process. Hold
            // them closed until the rendered cabin has reached its semantic
            // stop; otherwise a snapshot can start the door animation while
            // the cabin is still visually travelling between floors.
            if (hostNode?.door_kind === "elevator_hall") {
              const elevatorMesh = [...objectMeshes.values()].find((mesh) => semantic(nodeById.get(String(mesh.userData.id))) === "elevator");
              const elevatorRoot = elevatorMesh?.userData.elevatorVisualRoot as THREE.Group | undefined;
              const elevatorNode = elevatorMesh ? nodeById.get(String(elevatorMesh.userData.id)) : undefined;
              const elevatorStates = elevatorNode?.states as Record<string, unknown> | undefined;
              const semanticHeight = Number(elevatorStates?.current_height ?? 0);
              const renderedHeight = Number(elevatorRoot?.userData.elevatorRenderHeight ?? semanticHeight);
              joint.open = Math.abs(renderedHeight - semanticHeight) <= 0.02 && requestedOpen;
            } else {
              joint.open = requestedOpen;
            }
          }
          // Structure children are already mounted below the host PartTree.
          // Their runtime snapshot also contains a derived world_transform,
          // but applying that to a joint would compose the host transform and
          // the local hinge/prismatic anchor twice. Keep child placement local
          // and let the semantic joint state above drive the animation.
          joint.runtimeTransform = undefined;
          // Every mesh in a door's articulation (panel, hinge pin, frame,
          // etc.) participates in the same collision state. Toggling only the
          // visible panel leaves an otherwise invisible child at the doorway
          // and makes open/close behavior appear inverted or sticky.
          if (joint.mesh.userData.componentRole === "door" || componentNode?.semantic_type === "door") {
            const collisionEnabled = !joint.open;
            const root = joint.pivot ?? joint.mesh;
            root.traverse((child) => {
              if (child instanceof THREE.Mesh) child.userData.collisionEnabled = collisionEnabled;
            });
          }
        });
      });
      // Cabin-door access follows the elevator semantic state. Disable only
      // the sliding leaves as soon as the process starts opening; the visual
      // joint interpolation can then finish without trapping the player.
      composites.forEach((composite) => {
        if (!composite.id.startsWith("elevator_car_")) return;
        const states = nodeById.get(composite.id)?.states as Record<string, unknown> | undefined;
        const elevatorMesh = objectMeshes.get(composite.id);
        const elevatorRoot = elevatorMesh?.userData.elevatorVisualRoot as THREE.Group | undefined;
        const semanticHeight = Number(states?.current_height ?? 0);
        const renderedHeight = Number(elevatorRoot?.userData.elevatorRenderHeight ?? semanticHeight);
        const carSettled = Math.abs(renderedHeight - semanticHeight) <= 0.02;
        const open = carSettled && (states?.is_open === true || states?.door_phase === "opening" || states?.door_phase === "dwelling");
        composite.joints.forEach((joint) => {
          if (joint.id.includes("car_door_")) joint.mesh.userData.collisionEnabled = !open;
        });
      });
      if (simulation.active) updateComposites(composites);
      // Re-apply door collision after the joint animation has written the
      // final pose. Closing must restore every articulated door mesh before
      // Rapier is synchronized; opening must remove all of them together.
      composites.forEach((composite) => {
        composite.joints.forEach((joint) => {
          if (joint.mesh.userData.componentRole !== "door") return;
          // Collision is disabled only while the panel is travelling. Once
          // an open door reaches its final pose, its collider is restored at
          // the new (out-of-the-way) position; a closed door's restored
          // collider then blocks the doorway naturally.
          const targetProgress = joint.open ? 1 : 0;
          const transitioning = Math.abs(joint.progress - targetProgress) > 0.01;
          const isCabinDoor = composite.id.startsWith("elevator_car_") && joint.id.includes("car_door_");
          // Cabin doors are never obstacles while open, even after their
          // sliding animation reaches its final pose. They become collidable
          // only after a complete closed pose, preventing the open door leaf
          // from trapping the player at the threshold.
          const enabled = isCabinDoor ? !joint.open && !transitioning : !transitioning;
          const root = joint.pivot ?? joint.mesh;
          root.traverse((child) => {
            if (child instanceof THREE.Mesh) child.userData.collisionEnabled = enabled;
          });
          if (import.meta.env.DEV && composite.id === "door_entrance") {
            // Report only semantic collision state transitions. Joint progress
            // changes every render frame while a door animates and must not
            // turn this diagnostic into a console flood.
            const debugState = `${joint.open}:${enabled}`;
            if (debugState !== lastDoorCollisionDebug) {
              lastDoorCollisionDebug = debugState;
              console.debug("Door collision sync", { id: composite.id, open: joint.open, enabled });
            }
          }
        });
      });
      // Joint animation above is the source of the rendered door pose and
      // collisionEnabled flags. Synchronize Rapier after that update so a
      // door that has just closed becomes solid in the same frame (and a door
      // that has just opened is removed from the physics world). The earlier
      // pre-animation sync remains useful for ordinary moving meshes, but it
      // cannot observe this frame's joint state yet.
      if (rapierRuntime && !rapierRuntime.disposed) {
        rapierRuntime.staticColliders.forEach((collider, mesh) => {
          collider.setEnabled(mesh.userData.collisionEnabled !== false);
          mesh.updateWorldMatrix(true, false);
          const center = new THREE.Vector3();
          mesh.getWorldPosition(center);
          const rotation = new THREE.Quaternion();
          mesh.getWorldQuaternion(rotation);
          collider.setTranslation({ x: center.x, y: center.y, z: center.z });
          collider.setRotation({ x: rotation.x, y: rotation.y, z: rotation.z, w: rotation.w });
        });
        const elevatorMesh = [...objectMeshes.values()].find((mesh) => semantic(nodeById.get(String(mesh.userData.id))) === "elevator");
        const elevatorRoot = elevatorMesh?.userData.elevatorVisualRoot as THREE.Group | undefined;
        if (elevatorRoot && rapierRuntime.elevatorBody) {
          elevatorRoot.updateWorldMatrix(true, true);
          const position = elevatorRoot.getWorldPosition(new THREE.Vector3());
          const rotation = elevatorRoot.getWorldQuaternion(new THREE.Quaternion());
          rapierRuntime.elevatorBody.setNextKinematicTranslation({ x: position.x, y: position.y, z: position.z });
          rapierRuntime.elevatorBody.setNextKinematicRotation({ x: rotation.x, y: rotation.y, z: rotation.z, w: rotation.w });
          rapierRuntime.elevatorColliders.forEach((collider, mesh) => {
            collider.setEnabled(mesh.userData.collisionEnabled !== false);
            mesh.updateWorldMatrix(true, false);
            const meshPosition = mesh.getWorldPosition(new THREE.Vector3());
            const relativePosition = meshPosition.clone().sub(position).applyQuaternion(rotation.clone().invert());
            const meshRotation = mesh.getWorldQuaternion(new THREE.Quaternion());
            const relativeRotation = rotation.clone().invert().multiply(meshRotation);
            // Door joints move their Three.js meshes after the kinematic body
            // is created. Keep the attached Rapier shape at that same local
            // pose, otherwise the collider remains at the closed-door pose.
            collider.setTranslationWrtParent({ x: relativePosition.x, y: relativePosition.y, z: relativePosition.z });
            collider.setRotationWrtParent({ x: relativeRotation.x, y: relativeRotation.y, z: relativeRotation.z, w: relativeRotation.w });
          });
        }
        rapierRuntime.world.step();
      }
      // PartTree visuals are authored from the host dimensions and their
      // local anchors above. Runtime snapshots also expose protocol
      // world_transform for every structure child, but applying that world
      // transform here would place an already-attached component a second
      // time. In Run this made appliance doors recede into the body and put
      // microwave hinges/buttons at the wrong location, while editor mode
      // (which has no runtime world_transform) looked correct. The host root
      // transform and joint state are the single visual source for all
      // generated PartTree components.
      // Runtime placement owns the final transform.  Apply it to the root
      // object mesh as well as articulated components so a confirmed surface
      // or floor placement cannot remain at its old editor position.
      objectMeshes.forEach((mesh, id) => {
        // Held objects are mounted under the hand anchor and intentionally
        // follow the agent, not their last semantic world transform.
        if (heldVisualIds.has(id) || mesh.userData.held) return;
        const node = nodeById.get(id);
        // The existing animated-mesh loop owns the transform while a washer
        // is running. Do not immediately overwrite its oscillation with the
        // unchanged runtime world transform.
        if (["washer", "washing_machine"].includes(semantic(node))
          && Boolean((node?.states as Record<string, unknown> | undefined)?.is_running)) return;
        // Elevator height is interpolated from runtime current_height above;
        // applying its snapshot transform here would overwrite that motion.
        if (semantic(node) === "elevator") return;
        const transform = node?.world_transform;
        if (node?.transform_space !== "graphworld_z_up" || !transform || typeof transform !== "object") return;
        applyProtocolWorldToThree(mesh, transform as { position?: number[]; rotation?: number[]; scale?: number[] });
        const storageMode = text(node.storage_mode).toLowerCase();
        const hidden = storageMode === "hidden" || node.visibility === false;
        mesh.visible = !hidden;
        mesh.userData.collisionEnabled = !hidden && node.collision_enabled !== false;
        if (import.meta.env.DEV && id.includes("detergent") && heldVisualIds.has(id)) {
          console.debug("Held visual runtime visibility", {
            object_id: id,
            hidden,
            storage_mode: node.storage_mode,
            visibility: node.visibility,
            parent: mesh.parent?.name,
            visible: mesh.visible,
          });
        }
        // A contained load is mounted at the appliance origin and must stay
        // out of interaction/physics until the runtime exposes it again.
        if (hidden) {
          mesh.userData.pickable = false;
          mesh.userData.collisionEnabled = false;
        }
      });
      updateVisualEffects(effectMeshes, nodeById, time);
      objectLabels.forEach((label, id) => {
        const mesh = objectMeshes.get(id);
        if (mesh) {
          label.position.set(mesh.position.x, mesh.position.y + (mesh.geometry.boundingBox?.max.y ?? 0.4) + 0.05, mesh.position.z - (mesh.geometry.boundingBox?.max.z ?? 0));
          selectionVisualsRef.current.get(id)?.updateMatrixWorld(true);
        }
      });
      if (labelsVisible) {
        camera.updateMatrixWorld();
        objectLabels.forEach((label, id) => {
          const target = objectMeshes.get(id);
          if (!target) return;
          label.visible = !isOccluded(camera.position, label.position, collisionMeshes, target);
        });
      }
      renderer.render(scene, camera);
      frame = requestAnimationFrame(animate);
    };
    animate();
    // Rapier cleanup follows the renderer lifecycle.
    // @ts-ignore Rapier runtime is narrowed by the guard in this compact cleanup.
    return () => { effectDisposed = true; rapierInitCancelled = true; if (rapierRuntime) { rapierRuntime.disposed = true; rapierRuntime.controller.free(); rapierRuntime.world.removeCollider(rapierRuntime.collider, true); rapierRuntime.staticColliders.forEach((collider) => rapierRuntime.world.removeCollider(collider, true)); rapierRuntime.world.free(); rapierRuntime = null; } handsRef.current.left = false; handsRef.current.right = false; if (simulation.active) { simulationStateRef.current = { player: simulation.player.clone(), yaw: simulation.yaw, pitch: simulation.pitch, roomId: simulation.roomId, moving: simulation.moving }; simulationActiveRef.current = false; if (document.pointerLockElement === renderer.domElement) document.exitPointerLock(); cameraStateRef.current = { position: camera.position.clone(), target: controls.target.clone() }; } else { simulationStateRef.current = null; cameraStateRef.current = { position: camera.position.clone(), target: controls.target.clone() }; } simulationControllerRef.current = null; window.removeEventListener("keydown", onKeyDown); window.removeEventListener("keyup", onKeyUp); document.removeEventListener("mousemove", onMouseLook); document.removeEventListener("pointerlockchange", onPointerLockChange); if (pendingTransform.changed) commitTransform(); transformControls.detach(); transformControls.dispose(); transformControlsRef.current = null; rotationControls.detach(); rotationControls.dispose(); rotationControlsRef.current = null; cancelAnimationFrame(frame); observer.disconnect(); renderer.domElement.removeEventListener("pointerdown", onPointerDown); renderer.domElement.removeEventListener("pointermove", onPointerMove); renderer.domElement.removeEventListener("pointerup", onPointerUp); controls.dispose(); renderer.dispose(); sceneRef.current = null; scene.traverse((item) => { if (item instanceof THREE.Mesh) { item.geometry.dispose(); if (Array.isArray(item.material)) item.material.forEach((material) => material.dispose()); else item.material.dispose(); } }); host.replaceChildren(); };
  // `nodes` changes on every runtime interaction (pick/place/press). Rebuilding
  // this effect for those state deltas disposes Rapier, exits pointer lock,
  // and stops the active simulation. The live Three scene owns per-frame
  // runtime state; layout/catalog changes remain the structural rebuild points.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, labelsVisible, catalog, onInteractionHit]);

  return <div className="scene3d-stage" aria-label="3D scene editor">
    <div className="scene3d-renderer" ref={hostRef} />
    {!simulationActive && <div className="scene3d-legend" aria-label="Object category legend">
      <strong>Object categories</strong>
      {CATEGORY_LABELS.map(([category, label]) => <span key={category}><i style={{ backgroundColor: `#${CATEGORY_COLORS[category].toString(16).padStart(6, "0")}` }} />{label}</span>)}
    </div>}
    {!simulationActive && <div className="scene3d-layer-control">
      <button className="scene3d-label-toggle" type="button" title="图层" aria-label="图层" onClick={() => setLayersOpen((open) => !open)}><Layers3 size={15} /></button>
      {layersOpen && <div className="scene3d-layer-panel">
        <strong>图层</strong>
        <label><input type="checkbox" checked={layerVisibility.labels} onChange={(event) => setLayerVisibility((value) => ({ ...value, labels: event.target.checked }))} /> 标签层</label>
        <label><input type="checkbox" checked={layerVisibility.floor} onChange={(event) => setLayerVisibility((value) => ({ ...value, floor: event.target.checked }))} /> 地板层</label>
        <label><input type="checkbox" checked={layerVisibility.objects} onChange={(event) => setLayerVisibility((value) => ({ ...value, objects: event.target.checked }))} /> 物体层</label>
        <small>墙壁始终显示</small>
      </div>}
    </div>}
    {simulationActive && <button className="scene3d-view-toggle" type="button" onClick={() => setViewMode((mode) => mode === "first" ? "third" : "first")}>{viewMode === "first" ? "第三人称" : "第一人称"}</button>}
    {simulationActive && <>
      <div className="scene3d-crosshair" aria-hidden="true" />
      {slotHint && <div className="scene3d-slot-hint" role="status" aria-live="polite">容纳槽 {slotHint.count} / {slotHint.capacity || "-"}</div>}
      <div className="scene3d-simulation-hint">
        <strong>{viewMode === "first" ? "第一人称仿真" : "第三人称仿真"}</strong>
        <span>WASD 移动 · 鼠标观察 · 左键查看状态 · Q/E 交互 · Esc 释放鼠标</span>
        {heldObjectLabel && <span className="scene3d-held-status">手持：{heldObjectLabel} · 对准承载面按 Q/E 放置</span>}
        {!pointerLocked && <button type="button" onClick={() => simulationControllerRef.current?.start()}>点击继续控制视角</button>}
      </div>
      {statusCardId && (() => {
        const node = nodes.find((item) => text(item.id) === statusCardId);
        if (!node) return null;
        const states = (node.states && typeof node.states === "object") ? node.states as Record<string, unknown> : {};
        const property = node.property && typeof node.property === "object" ? node.property as Record<string, unknown> : {};
        const attributes = Object.entries(property).filter(([, value]) => value != null && value !== "" && !(Array.isArray(value) && value.length === 0) && !(typeof value === "object" && !Array.isArray(value) && Object.keys(value as object).length === 0));
        if (semantic(node)) attributes.unshift(["类型", semantic(node)]);
        const format = (value: unknown) => Array.isArray(value) ? value.join(", ") : typeof value === "object" && value !== null ? JSON.stringify(value) : String(value);
        return <section className="scene3d-status-card" aria-label="物体状态">
          <header><strong>{nodeName(node)}</strong><button type="button" aria-label="关闭状态卡片" title="关闭" onClick={() => setStatusCardId("")}><X size={15} /></button></header>
          {Boolean(states.is_running) && <div className="scene3d-device-progress" aria-label="设备运行进度">
            {(() => { const remaining = Number(states.cycle_remaining ?? 0); const configured = Number(node.cycle_duration ?? node.duration_steps ?? (["washer", "washing_machine"].includes(semantic(node)) ? 10 : 3)); const progress = Math.max(0, Math.min(1, 1 - remaining / Math.max(1, configured))); return <><div className="scene3d-device-progress-head"><span>运行中</span><strong>{Math.round(progress * 100)}%</strong></div><div className="scene3d-device-progress-track"><span style={{ width: `${progress * 100}%` }} /></div></>; })()}
          </div>}
          <dl>
            <dt>属性</dt>
            <dd>{attributes.length ? attributes.map(([key, value]) => <span key={key}><b>{key}</b>{format(value)}</span>) : <span>无</span>}</dd>
            <dt>状态</dt>
            <dd>{Object.keys(states).length ? Object.keys(states).join("、") : "无"}</dd>
            <dt>状态值</dt>
            <dd>{Object.entries(states).length ? Object.entries(states).map(([key, value]) => <span key={key}><b>{key}</b>{format(value)}</span>) : "无"}</dd>
          </dl>
        </section>;
      })()}
    </>}
  </div>;
}

function makeLabel(value: string, color = "#334155"): THREE.Sprite {
  const displayText = value.slice(0, 30);
  const canvas = document.createElement("canvas");
  const measureCanvas = document.createElement("canvas");
  const measureContext = measureCanvas.getContext("2d")!;
  measureContext.font = "700 22px sans-serif";
  const horizontalPadding = 8;
  const labelWidth = Math.min(520, Math.ceil(measureContext.measureText(displayText).width + horizontalPadding * 2));
  canvas.width = Math.max(1, labelWidth); canvas.height = 44;
  const context = canvas.getContext("2d")!;
  context.fillStyle = "rgba(255,255,255,0.92)";
  context.beginPath();
  context.roundRect(2, 2, labelWidth - 4, 40, 6);
  context.fill();
  context.font = "700 22px sans-serif";
  context.fillStyle = color;
  context.textBaseline = "middle";
  context.fillText(displayText, horizontalPadding, 22);
  const texture = new THREE.CanvasTexture(canvas);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false }));
  sprite.scale.set(labelWidth / 240, 0.18, 1);
  return sprite;
}
