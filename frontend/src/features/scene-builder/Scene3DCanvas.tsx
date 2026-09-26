import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { TransformControls } from "three/examples/jsm/controls/TransformControls.js";
import { Eye, EyeOff, Play, Square, Layers3, X } from "lucide-react";
import type { FloorplanLayout } from "./FloorplanCanvas";
import type { ObjectCatalogEntry } from "../../api/scenes";
import type { InteractionHit } from "../../types/api";
import { attachHinge, attachLocalPart, attachPart, attachPrismatic, createComposite, updateComposites, type CompositeObject } from "./compositeRuntime";
import { resolveLocalInteraction } from "./interactionResolver";

type RawNode = Record<string, unknown>;

interface Scene3DCanvasProps {
  nodes: RawNode[];
  edges: RawNode[];
  layout: FloorplanLayout;
  selectedId: string;
  onSelect: (id: string) => void;
  onChange: (layout: FloorplanLayout) => void;
  onSimulationPlace?: (objectId: string, parentId: string) => void;
  catalog: ObjectCatalogEntry[];
  onInteractionHit?: (hit: InteractionHit) => void;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function semantic(node: RawNode | undefined): string {
  return text(node?.semantic_type || node?.object_type).toLowerCase();
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

export function Scene3DCanvas({ nodes, edges, layout, selectedId, onSelect, onChange, onSimulationPlace, catalog, onInteractionHit }: Scene3DCanvasProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const selectRef = useRef(onSelect);
  const changeRef = useRef(onChange);
  const simulationPlaceRef = useRef(onSimulationPlace);
  const pendingSimulationLayoutRef = useRef<FloorplanLayout | null>(null);
  const pendingSimulationParentsRef = useRef<Array<{ objectId: string; parentId: string }>>([]);
  const cameraStateRef = useRef<{ position: THREE.Vector3; target: THREE.Vector3 } | null>(null);
  const selectionVisualsRef = useRef(new Map<string, THREE.Object3D>());
  const transformControlsRef = useRef<TransformControls | null>(null);
  const rotationControlsRef = useRef<TransformControls | null>(null);
  const objectMeshesRef = useRef(new Map<string, THREE.Mesh>());
  const sceneRef = useRef<THREE.Scene | null>(null);
  const simulationActiveRef = useRef(false);
  const simulationControllerRef = useRef<{ start: () => void; stop: () => void } | null>(null);
  const selectedIdRef = useRef(selectedId);
  const [labelsVisible, setLabelsVisible] = useState(true);
  const [simulationActive, setSimulationActive] = useState(false);
  const [pointerLocked, setPointerLocked] = useState(false);
  const [heldObjectLabel, setHeldObjectLabel] = useState("");
  const [statusCardId, setStatusCardId] = useState("");
  const [runtimeStatusOverrides, setRuntimeStatusOverrides] = useState<Record<string, Record<string, unknown>>>({});
  const [viewMode, setViewMode] = useState<"first" | "third">("first");
  const [layersOpen, setLayersOpen] = useState(false);
  const [layerVisibility, setLayerVisibility] = useState({ labels: true, ceiling: true, floor: true, objects: true });
  const viewModeRef = useRef(viewMode);
  const handsRef = useRef({ left: false, right: false });
  selectRef.current = onSelect;
  changeRef.current = onChange;
  simulationPlaceRef.current = onSimulationPlace;
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
      else if (layer === "ceiling") item.visible = layerVisibility.ceiling;
      else if (layer === "floor") item.visible = layerVisibility.floor;
      else if (layer === "objects") item.visible = layerVisibility.objects;
    });
  }, [layerVisibility]);

  useEffect(() => {
    selectionVisualsRef.current.forEach((visual, id) => { visual.visible = id === selectedId; });
    const transform = transformControlsRef.current;
    const rotation = rotationControlsRef.current;
    if (!transform || simulationActiveRef.current) return;
    const selectedMesh = objectMeshesRef.current.get(selectedId);
    if (selectedMesh) {
      transform.attach(selectedMesh);
      rotation?.attach(selectedMesh);
    } else {
      transform.detach();
      rotation?.detach();
    }
  }, [selectedId]);

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

    const camera = new THREE.PerspectiveCamera(45, 1, 0.05, 500);
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
    const objectMeshes = new Map<string, THREE.Mesh>();
    const objectLabels = new Map<string, THREE.Sprite>();
    const animatedMeshes = new Map<string, { mesh: THREE.Mesh; base: THREE.Vector3 }>();
    const effectMeshes = new Array<{
      mesh: THREE.Mesh;
      host: THREE.Mesh;
      nodeId: string;
      kind: "droplet" | "drying" | "steam" | "broken" | "stain";
      offset: THREE.Vector3;
      phase: number;
    }>();
    const composites: CompositeObject[] = [];
    const runtimeOpen = new Map<string, boolean>();
    const runtimeLightState = new Map<string, boolean>();
    const runtimeSinkFill = new Map<string, number>();
    const runtimeFaucetOpen = new Set<string>();
    const waterMeshes = new Map<string, THREE.Mesh>();
    const runtimeDeviceRunning = new Map<string, boolean>();
    const placedContents = new Map<string, number>();
    const controlTargets = new Map<string, string[]>();
    const faucetsBySink = new Map<string, RawNode[]>();
    edges.forEach((edge) => {
      if (text(edge.relation || edge.edge_type) !== "controls") return;
      const source = text(edge.source_id || edge.source);
      const target = text(edge.target_id || edge.target);
      controlTargets.set(source, [...(controlTargets.get(source) ?? []), target]);
      if (semantic(nodes.find((node) => text(node.id) === source)) === "faucet") {
        faucetsBySink.set(target, [...(faucetsBySink.get(target) ?? []), nodes.find((node) => text(node.id) === source)!]);
      }
    });
    // Older scene snapshots contain a standalone switch and target but omit
    // the logical controls edge. Infer only an unambiguous same-container
    // binding; explicit edges always remain authoritative.
    nodes.forEach((sourceNode) => {
      const sourceId = text(sourceNode.id);
      const sourceCaps = Array.isArray(sourceNode.capabilities) ? sourceNode.capabilities.map(String) : [];
      if (!sourceId || controlTargets.has(sourceId) || !sourceCaps.includes("switchable")) return;
      if (text(sourceNode.node_type) !== "control_object" && semantic(sourceNode) !== "button") return;
      const parentId = text(sourceNode.parent || sourceNode.parent_id);
      const candidates = nodes.filter((candidate) => {
        const candidateId = text(candidate.id);
        const candidateCaps = Array.isArray(candidate.capabilities) ? candidate.capabilities.map(String) : [];
        if (!candidateId || candidateId === sourceId || !candidateCaps.includes("switchable")) return false;
        if (text(candidate.node_type) === "control_object" || semantic(candidate) === "button") return false;
        return text(candidate.parent || candidate.parent_id) === parentId;
      });
      if (candidates.length === 1) controlTargets.set(sourceId, [text(candidates[0].id)]);
    });
    let heldObjectId: string | null = null;
    const heldOriginalPositions = new Map<string, THREE.Vector3>();
    const heldOriginalRotations = new Map<string, THREE.Quaternion>();
    const heldOriginalParents = new Map<string, string>();
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
    const componentNodeIds = new Set<string>();
    const componentEdgeRelations = new Set(["component_of", "controls", "part_of"]);
    nodes.forEach((node) => {
      const hostId = text(node.component_of || node.parent);
      if (!hostId) return;
      const nodeSemantic = semantic(node);
      const isMechanicalComponent = Boolean(text(node.component_role)) || ["button", "door", "hinge", "drawer"].includes(nodeSemantic);
      if (isMechanicalComponent && (text(node.component_of) || edges.some((edge) => {
        const relation = text(edge.relation || edge.edge_type);
        const source = text(edge.source_id || edge.source);
        const target = text(edge.target_id || edge.target);
        return componentEdgeRelations.has(relation)
          && ((source === text(node.id) && target === hostId) || (source === hostId && target === text(node.id)));
      }))) componentNodeIds.add(text(node.id));
      componentNodesByHost.set(hostId, [...(componentNodesByHost.get(hostId) ?? []), node]);
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
    const roomHeight = 2.6;
    const allWidth = Math.max(...roomEntries.map(([, room]) => (room.grid_x + room.width_cells) * cell), 8);
    const allDepth = Math.max(...roomEntries.map(([, room]) => (room.grid_y + room.depth_cells) * cell), 6);

    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(allWidth + 2, allDepth + 2),
      new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.95 }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.set((allWidth - 1) / 2, -0.01, (allDepth - 1) / 2);
    floor.receiveShadow = true;
    floor.userData = { id: "__floor__", simulationSurface: true, layer: "floor" };
    scene.add(floor);
    roomEntries.forEach(([, room]) => {
      const ceiling = new THREE.Mesh(
        new THREE.PlaneGeometry(room.width_cells * cell, room.depth_cells * cell),
        new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.96, side: THREE.DoubleSide }),
      );
      ceiling.rotation.x = Math.PI / 2;
      ceiling.position.set(
        (room.grid_x + room.width_cells / 2) * cell,
        roomHeight,
        (room.grid_y + room.depth_cells / 2) * cell,
      );
      ceiling.userData.layer = "ceiling";
      ceiling.visible = layerVisibility.ceiling;
      scene.add(ceiling);
    });
    // The floor is a valid placement surface in first-person mode. It is
    // filtered out of editor selection below so it cannot steal room clicks.
    interactive.push(floor);
    const grid = new THREE.GridHelper(Math.max(allWidth, allDepth) + 2, Math.ceil(Math.max(allWidth, allDepth) / cell), 0x94a3b8, 0xcbd5e1);
    grid.position.set((allWidth - 1) / 2, 0, (allDepth - 1) / 2);
    scene.add(grid);
    grid.userData.layer = "floor";

    const wallKeys = new Set<string>();
    const wallMaterial = () => new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.9, metalness: 0.01 });
    const wallOpenings = (roomId: string, wall: WallSide): Array<[number, number]> => {
      const openings: Array<[number, number]> = [];
      Object.values(layout.doors).forEach((door) => {
        const roomA = layout.rooms[door.room_a_id];
        const roomB = layout.rooms[door.room_b_id];
        if (!roomA || !roomB) return;
        const side = door.room_a_id === roomId ? door.wall : door.room_b_id === roomId ? OPPOSITE_WALL[door.wall] : null;
        if (side !== wall) return;
        const horizontal = wall === "north" || wall === "south";
        const currentRoom = door.room_a_id === roomId ? roomA : roomB;
        const origin = horizontal ? currentRoom.grid_x : currentRoom.grid_y;
        const start = (origin + door.offset_cells) * cell;
        openings.push([start, start + door.width_cells * cell]);
      });
      return openings.sort((first, second) => first[0] - second[0]);
    };
    const addWallSegments = (roomId: string, side: WallSide, selected: boolean) => {
      const room = layout.rooms[roomId];
      const horizontal = side === "north" || side === "south";
      const axisStart = (horizontal ? room.grid_x : room.grid_y) * cell;
      const axisEnd = axisStart + (horizontal ? room.width_cells : room.depth_cells) * cell;
      const boundary = (horizontal ? room.grid_y : room.grid_x) * cell + (side === "south" || side === "east" ? (horizontal ? room.depth_cells : room.width_cells) * cell : 0);
      const openings = wallOpenings(roomId, side);
      const cuts = [axisStart, ...openings.flatMap(([start, end]) => [Math.max(axisStart, start), Math.min(axisEnd, end)]), axisEnd];
      for (let index = 0; index < cuts.length - 1; index += 2) {
        const start = cuts[index];
        const end = cuts[index + 1];
        if (end - start <= 0.01) continue;
        const key = `${horizontal ? "h" : "v"}:${boundary.toFixed(3)}:${start.toFixed(3)}:${end.toFixed(3)}`;
        if (wallKeys.has(key)) continue;
        wallKeys.add(key);
        const length = end - start;
        const wall = new THREE.Mesh(
          horizontal ? new THREE.BoxGeometry(length, roomHeight, 0.1) : new THREE.BoxGeometry(0.1, roomHeight, length),
          wallMaterial(),
        );
        wall.position.set(horizontal ? (start + end) / 2 : boundary, roomHeight / 2, horizontal ? boundary : (start + end) / 2);
        wall.userData.layer = "objects";
        scene.add(wall);
        collisionMeshes.push(wall);
      }
    };

    roomEntries.forEach(([roomId, room], index) => {
      const width = room.width_cells * cell;
      const depth = room.depth_cells * cell;
      const x = (room.grid_x + room.width_cells / 2) * cell;
      const z = (room.grid_y + room.depth_cells / 2) * cell;
      const roomMesh = new THREE.Mesh(new THREE.BoxGeometry(width, 0.02, depth), new THREE.MeshStandardMaterial({ color: colorFor(index), transparent: true, opacity: selectedId === roomId ? 0.22 : 0.08, depthWrite: false }));
      roomMesh.position.set(x, 0.02, z);
      roomMesh.userData = { id: roomId };
      scene.add(roomMesh);
      interactive.push(roomMesh);
      {
        const highlight = new THREE.Mesh(
          new THREE.BoxGeometry(width, 0.04, depth),
          new THREE.MeshBasicMaterial({ color: 0x2563eb, transparent: true, opacity: 0.2, depthWrite: false, side: THREE.DoubleSide }),
        );
        highlight.position.set(x, 0.05, z);
        highlight.visible = selectedId === roomId;
        scene.add(highlight);
        selectionVisualsRef.current.set(roomId, highlight);
      }
      addWallSegments(roomId, "north", selectedId === roomId);
      addWallSegments(roomId, "east", selectedId === roomId);
      addWallSegments(roomId, "south", selectedId === roomId);
      addWallSegments(roomId, "west", selectedId === roomId);
      const label = makeLabel(nodeName(nodeById.get(roomId)) || roomId);
      label.layers.set(1);
      label.userData.layer = "labels";
      label.position.set(room.grid_x * cell + 0.12, 0.04, room.grid_y * cell + 0.12);
      scene.add(label);
    });

    Object.entries(layout.doors).forEach(([doorId, door]) => {
      const room = layout.rooms[door.room_a_id];
      if (!room) return;
      const horizontal = door.wall === "north" || door.wall === "south";
      const width = door.width_cells * cell;
      const axisStart = (horizontal ? room.grid_x : room.grid_y) * cell + door.offset_cells * cell;
      const boundary = (horizontal ? room.grid_y : room.grid_x) * cell + (door.wall === "south" || door.wall === "east" ? (horizontal ? room.depth_cells : room.width_cells) * cell : 0);
      const doorRoot = new THREE.Group();
      doorRoot.position.set(horizontal ? axisStart : boundary, 0, horizontal ? boundary : axisStart);
      const hinge = new THREE.Group();
      hinge.position.set(0, 0, 0);
      hinge.rotation.y = door.wall === "east" || door.wall === "north" ? Math.PI / 2 : -Math.PI / 2;
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
      collisionMeshes.push(panel);
      const composite = createComposite(doorId, doorRoot);
      attachHinge(composite, doorId, panel, hinge, door.wall === "east" || door.wall === "north" ? -Math.PI / 2 : Math.PI / 2);
      composites.push(composite);
    });

    Object.entries(layout.objects).forEach(([objectId, item]) => {
      const room = layout.rooms[item.room_id];
      if (!room) return;
      const node = nodeById.get(objectId);
      if (componentNodeIds.has(objectId)) return;
      const catalogEntry = catalogByType.get(semantic(node));
      const [widthCm, depthCm, heightCm] = catalogEntry
        ? [catalogEntry.width_cm, catalogEntry.depth_cm, catalogEntry.height_cm]
        : [item.width_cm ?? Math.max(1, item.width_cells * cell * 100), item.depth_cm ?? Math.max(1, item.depth_cells * cell * 100), item.height_cm ?? 80];
      const componentHost = text(node?.component_of || node?.parent);
      const componentRole = text(node?.component_role);
      const isGraphComponent = Boolean(text(node?.component_of) || edges.some((edge) => text(edge.relation || edge.edge_type) === "component_of" && text(edge.source_id || edge.source) === objectId));
      const width = (isGraphComponent ? item.width_cm ?? widthCm : widthCm) / 100;
      const depth = (isGraphComponent ? item.depth_cm ?? depthCm : depthCm) / 100;
      const height = (isGraphComponent ? item.height_cm ?? heightCm : heightCm) / 100;
      const placementMode = item.placement_mode;
      const parentMesh = item.parent_object_id ? objectMeshes.get(item.parent_object_id) : undefined;
      const parentHeight = parentMesh?.geometry.boundingBox ? parentMesh.geometry.boundingBox.max.y - parentMesh.geometry.boundingBox.min.y : 0.8;
      const baseHeight = placementMode === "wall_mounted"
        ? 2.1
        : placementMode === "contained"
          ? Math.max(0.02, (parentMesh?.position.y ?? parentHeight) - parentHeight / 2 + 0.03)
          : 0;
      const x = ((item.x_cm ?? ((room.grid_x + item.grid_x) * cell * 100)) / 100) + width / 2;
      const z = ((item.y_cm ?? ((room.grid_y + item.grid_y) * cell * 100)) / 100) + depth / 2;
      const hostRotation = Number(item.rotation_y ?? item.rotation ?? 0) * Math.PI / 2;
      const worldPointForHost = (px: number, py: number, pz: number) =>
        new THREE.Vector3(px - x, py - (baseHeight + (item.z_cm ?? 0) / 100 + height / 2), pz - z)
          .applyAxisAngle(new THREE.Vector3(0, 1, 0), hostRotation)
          .add(new THREE.Vector3(x, baseHeight + (item.z_cm ?? 0) / 100 + height / 2, z));
      const selected = selectedId === objectId;
      const states = node?.states as Record<string, unknown> | undefined;
      const composition = node?.composition && typeof node.composition === "object"
        ? node.composition as { components?: Array<Record<string, unknown>>; storage?: Record<string, unknown> }
        : null;
      const componentNodes = componentNodesByHost.get(objectId) ?? [];
      const componentNodeForRole = (role: string, index?: number) => componentNodes.find((componentNode) => {
        const componentRole = text(componentNode.component_role);
        const componentType = semantic(componentNode);
        if (componentRole === role || componentType === role) {
          return index == null || Number(componentNode.component_index ?? 0) === index;
        }
        return false;
      });
      const hasFrontCavity = Boolean(composition?.storage || composition?.components?.some((part) => text(part.role || part.semantic_type) === "door"));
      const isDrawer = semantic(node) === "drawer" || componentRole === "drawer";
      const isClothes = semantic(node) === "clothes";
      const isComponentDoor = semantic(node) === "door" || componentRole === "door";
      const folded = Boolean(states?.folded);
      const objectMaterial = new THREE.MeshStandardMaterial({
        color: isDrawer ? 0x64748b : isClothes ? 0x94a3b8 : CATEGORY_COLORS[objectCategory(node)],
        transparent: true,
        opacity: 0.86,
        roughness: 0.72,
      });
      const isOpenFrame = ["rack", "shoe_rack", "drying_rack", "shelf"].includes(semantic(node));
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
      const drawerFaceDepth = Math.min(0.035, depth * 0.08);
      const mesh = new THREE.Mesh(
        isComponentDoor
          ? new THREE.BoxGeometry(width * 0.92, height * 0.92, Math.min(0.04, depth * 0.1))
          : isDrawer
          ? new THREE.BoxGeometry(width * 0.94, height * 0.92, drawerFaceDepth)
          : isClothes
            ? new THREE.BoxGeometry(width * (folded ? 0.72 : 1), height * (folded ? 0.42 : 1), depth * (folded ? 1.2 : 0.72))
            : new THREE.BoxGeometry(width, height, depth),
        objectMaterial,
      );
      mesh.geometry.computeBoundingBox();
      mesh.position.set(
        x,
        baseHeight + (item.z_cm ?? 0) / 100 + height / 2,
        isComponentDoor || isDrawer ? z - depth / 2 + drawerFaceDepth / 2 : z,
      );
      mesh.rotation.set(
        Number(item.rotation_x ?? 0) * Math.PI / 2,
        Number(item.rotation_y ?? item.rotation ?? 0) * Math.PI / 2,
        Number(item.rotation_z ?? 0) * Math.PI / 2,
      );
      mesh.userData = { id: objectId };
      mesh.userData.layer = "objects";
      mesh.castShadow = true;
      scene.add(mesh);
      interactive.push(mesh);
      collisionMeshes.push(mesh);
      objectMeshes.set(objectId, mesh);
      const composite = createComposite(objectId, mesh);
      composites.push(composite);
      if (isOpenFrame) {
        const frameMaterial = new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.72 });
        const rail = Math.min(0.045, Math.min(width, depth) * 0.08);
        const storage = composition?.storage ?? {};
        const shelfCount = Math.max(1, Number(storage.levels) || (semantic(node) === "drying_rack" ? 3 : 3));
        const columns = Math.max(1, Number(storage.columns) || 1);
        const capacity = Number(storage.capacity_per_slot) || Number(node?.max_capacity) || 8;
        const requiredCapabilities = Array.isArray(storage.accepted_capabilities)
          ? storage.accepted_capabilities.map(String)
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
      if (["light", "room_light"].includes(semantic(node))) {
        const lamp = new THREE.PointLight(0xffe6a3, Boolean(states?.is_on) ? 2.2 : 0, 5.5, 1.8);
        lamp.position.set(0, placementMode === "wall_mounted" ? -0.35 : Math.max(0.15, height / 2), 0);
        mesh.add(lamp);
        runtimeLightState.set(objectId, Boolean(states?.is_on));
      }
      if (semantic(node) === "sink") {
        const initialFill = Number(states?.fill_level ?? (states?.is_full ? 1 : 0));
        runtimeSinkFill.set(objectId, THREE.MathUtils.clamp(initialFill > 1 ? initialFill / 100 : initialFill, 0, 1));
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
        water.visible = runtimeSinkFill.get(objectId)! > 0;
        mesh.add(water);
        waterMeshes.set(objectId, water);
        animatedMeshes.set(objectId, { mesh: water, base: water.position.clone() });
        const faucetNode = faucetsBySink.get(objectId)?.[0];
        if (faucetNode) {
          const faucetGroup = new THREE.Group();
          faucetGroup.position.set(0, height * 0.38, depth * 0.34);
          faucetGroup.userData = { id: text(faucetNode.id), componentId: text(faucetNode.id), componentRole: "faucet" };
          const metal = new THREE.MeshStandardMaterial({ color: 0xcbd5e1, metalness: 0.82, roughness: 0.22 });
          const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.022, height * 0.34, 12), metal);
          stem.position.y = height * 0.17;
          const spout = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.018, depth * 0.32, 12), metal);
          spout.rotation.x = Math.PI / 2;
          spout.position.set(0, height * 0.32, -depth * 0.12);
          stem.userData = { id: text(faucetNode.id), componentId: text(faucetNode.id), componentRole: "faucet" };
          spout.userData = { id: text(faucetNode.id), componentId: text(faucetNode.id), componentRole: "faucet" };
          faucetGroup.add(stem, spout);
          attachLocalPart(composite, faucetGroup);
          interactive.push(stem, spout);
        }
      }
      if (["washer", "washing_machine", "microwave", "dishwasher", "dryer", "clothesdryer"].includes(semantic(node))) {
        runtimeDeviceRunning.set(objectId, Boolean(states?.is_running));
        animatedMeshes.set(objectId, { mesh, base: mesh.position.clone() });
      }
      if (Boolean(states?.is_running) || (Boolean(states?.is_on) && ["fan", "ceiling_fan", "ventilator"].includes(semantic(node)))) {
        animatedMeshes.set(objectId, { mesh, base: mesh.position.clone() });
      }
      if (node?.physics_state === "falling") {
        animatedMeshes.set(objectId, { mesh, base: mesh.position.clone() });
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
          new THREE.BoxGeometry(width + 0.025, height + 0.025, depth + 0.025),
          new THREE.MeshBasicMaterial({ color: 0xef4444, wireframe: true, transparent: true, opacity: 0.9, depthTest: false }),
        );
        brokenOverlay.position.copy(mesh.position);
        scene.add(brokenOverlay);
        effectMeshes.push({ mesh: brokenOverlay, host: mesh, nodeId: objectId, kind: "broken", offset: new THREE.Vector3(), phase: 0 });
      }
      {
        const highlight = new THREE.Mesh(
          new THREE.BoxGeometry(width + 0.04, height + 0.04, depth + 0.04),
          new THREE.MeshBasicMaterial({ color: 0x2563eb, wireframe: true, transparent: true, opacity: 0.95, depthWrite: false }),
        );
        highlight.position.copy(mesh.position);
        highlight.visible = selected;
        scene.add(highlight);
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
        component.position.copy(worldPointForHost(position.x, position.y, position.z));
        component.rotation.y = hostRotation;
        component.userData = { id: objectId, componentId, componentRole: role, componentFace: face };
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
          const doorHeight = Math.max(0.12, height - faceInset * 2);
          const doorGeometry = face === "top"
            ? new THREE.BoxGeometry(doorWidth, 0.025, Math.max(0.08, depth - faceInset * 2))
            : new THREE.BoxGeometry(doorWidth, doorHeight, 0.035);
          if (face === "top") {
            addComponentMesh(role, face, [ax, ay, az], doorGeometry, new THREE.Vector3(x, mesh.position.y + height / 2 + 0.018, z));
          } else {
            // Device doors rotate around a vertical hinge on their side edge.
            // The old implementation rotated the panel around its own centre,
            // which made the hinge appear horizontal and detached from the box.
          const hingeSpec = composition?.components?.find((item) => text(item.role || item.semantic_type) === "hinge");
          const hingeAnchorX = Array.isArray(hingeSpec?.anchor) ? Number(hingeSpec.anchor[0]) : 0.08;
          const rightHinged = hingeAnchorX >= 0.5;
            const pivot = new THREE.Group();
            pivot.position.copy(worldPointForHost(x + (rightHinged ? width / 2 : -width / 2), mesh.position.y, z - depth / 2 - 0.02));
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
      const storage = composition?.storage;
      if (storage) {
        const mountStoragePart = (part: THREE.Mesh) => {
          attachPart(composite, part);
        };
        const levels = Math.max(1, Number(storage.levels) || 1);
        const columns = Math.max(1, Number(storage.columns) || 1);
        for (let level = 0; level < levels; level += 1) {
          for (let column = 0; column < columns; column += 1) {
            const slot = new THREE.Mesh(
              new THREE.BoxGeometry(width * 0.82 / columns, Math.max(0.08, height * 0.72 / levels), depth * 0.68),
              new THREE.MeshBasicMaterial({ color: 0x93c5fd, transparent: true, opacity: 0.08, depthWrite: false }),
            );
            slot.position.copy(worldPointForHost(
              x + (column + 0.5 - columns / 2) * (width * 0.82 / columns),
              mesh.position.y - height / 2 + (level + 0.5) * (height * 0.72 / levels) + height * 0.14,
              z - depth * 0.04,
            ));
            slot.rotation.y = hostRotation;
            slot.userData = {
              id: `${objectId}_slot_l${level + 1}_c${column + 1}`,
              hostId: objectId,
              componentId: `${objectId}_slot_l${level + 1}_c${column + 1}`,
              componentRole: "storage_slot",
              capabilities: ["place_target"],
              maxCapacity: Number(storage.capacity_per_slot) || 8,
              requiresContainedCapabilities: Array.isArray(storage.accepted_capabilities)
                ? storage.accepted_capabilities.map(String)
                : [],
            };
            scene.add(slot);
            interactive.push(slot);
            mountStoragePart(slot);
          }
        }
        for (let level = 1; level < levels; level += 1) {
          const shelf = new THREE.Mesh(new THREE.BoxGeometry(width * 0.82, 0.018, depth * 0.72), new THREE.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.8 }));
          shelf.position.copy(worldPointForHost(x, mesh.position.y - height / 2 + (height * level) / levels, z - depth * 0.04));
          shelf.rotation.y = hostRotation;
          shelf.userData = { id: objectId, componentRole: "storage_shelf" };
          scene.add(shelf);
          mountStoragePart(shelf);
        }
        for (let column = 1; column < columns; column += 1) {
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
          const drawerHeight = Math.max(0.08, height * 0.72 / levels - 0.025);
          const wallDepth = Math.max(0.08, depth * 0.62);
          const wallThickness = 0.025;
          const drawer = new THREE.Group();
          drawer.position.copy(worldPointForHost(
            x + (drawerColumn + 0.5 - columns / 2) * drawerWidth,
            mesh.position.y - height / 2 + height * 0.14 + (drawerLevel + 0.5) * (height * 0.72 / levels),
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
          bottom.userData = { id: componentId, hostId: objectId, componentId, componentRole: "storage_slot", capabilities: ["place_target"] };
          drawer.add(bottom, front, back, left, right);
          scene.add(drawer);
          interactive.push(front);
          interactive.push(bottom);
          const drawerAxisLength = mesh.geometry.boundingBox?.getSize(new THREE.Vector3()).z ?? depth;
          const guideOverlap = Math.min(wallDepth * 0.62, drawerAxisLength * 0.38);
          attachPrismatic(composite, componentId, drawer, Math.max(0, drawerAxisLength - guideOverlap));
        }
      }
    });

    const pendingTransform: { id: string; changed: boolean; startPosition: THREE.Vector3 | null } = { id: "", changed: false, startPosition: null };
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
      // Mesh Y includes the placement-mode base height used during render.
      // Store z_cm relative to that base, otherwise wall-mounted objects get
      // the base height added a second time when the scene remounts.
      const parentMesh = item.parent_object_id ? objectMeshes.get(item.parent_object_id) : undefined;
      const parentHeight = parentMesh?.geometry.boundingBox
        ? parentMesh.geometry.boundingBox.max.y - parentMesh.geometry.boundingBox.min.y
        : 0.8;
      const baseHeight = item.placement_mode === "wall_mounted"
        ? 2.1
        : item.placement_mode === "contained" && !(pendingTransform.startPosition && mesh.position.distanceToSquared(pendingTransform.startPosition) > 0.0001)
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
      if (detachContained) simulationPlaceRef.current?.(pendingTransform.id, item.room_id);
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
    transformControls.addEventListener("objectChange", () => { pendingTransform.changed = true; });
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
      }
    });
    rotationControls.addEventListener("mouseDown", () => { gizmoLock.active = true; transformControls.enabled = false; });
    rotationControls.addEventListener("mouseUp", () => {
      gizmoLock.active = false;
      transformControls.enabled = true;
      const mesh = rotationControls.object as THREE.Object3D | undefined;
      if (mesh) {
        mesh.rotation.set(
          normalizeQuarterTurn(mesh.rotation.x) * Math.PI / 2,
          normalizeQuarterTurn(mesh.rotation.y) * Math.PI / 2,
          normalizeQuarterTurn(mesh.rotation.z) * Math.PI / 2,
        );
      }
      commitTransform();
    });
    rotationControls.addEventListener("objectChange", () => {
      pendingTransform.changed = true;
      const mesh = rotationControls.object;
      if (mesh) pendingTransform.id = String(mesh.userData.id || selectedId);
    });

    const center = new THREE.Vector3(allWidth / 2, 0.8, allDepth / 2);
    const savedCamera = cameraStateRef.current;
    controls.target.copy(savedCamera?.target ?? center);
    camera.position.copy(savedCamera?.position ?? new THREE.Vector3(allWidth * 0.95, Math.max(8, allDepth * 0.95), allDepth * 1.15));
    camera.lookAt(center);
    controls.update();
    const editorCamera = {
      position: camera.position.clone(),
      target: controls.target.clone(),
    };
    const simulation = {
      active: false,
      yaw: 0,
      pitch: 0,
      keys: new Set<string>(),
      lastFrame: performance.now(),
      player: new THREE.Vector3(center.x, 1.6, center.z),
    };
    const cameraDirection = new THREE.Vector3();
    // Keep the first-person hand marker subtle; it is a visual pose cue, not
    // the player's collision or grasp volume.
    const handGeometry = new THREE.SphereGeometry(0.055, 16, 12);
    const handMaterial = new THREE.MeshStandardMaterial({ color: 0xf2b38b, roughness: 0.78 });
    const hands = {
      left: new THREE.Mesh(handGeometry, handMaterial),
      right: new THREE.Mesh(handGeometry, handMaterial),
    };
    const playerBody = new THREE.Mesh(
      new THREE.CapsuleGeometry(0.28, 1.04, 8, 16),
      new THREE.MeshStandardMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.72 }),
    );
    playerBody.userData.layer = "objects";
    playerBody.visible = false;
    scene.add(playerBody);
    hands.left.userData.layer = "objects";
    hands.right.userData.layer = "objects";
    scene.add(hands.left, hands.right);
    const startSimulation = () => {
      if (simulation.active) {
        renderer.domElement.requestPointerLock();
        return;
      }
      editorCamera.position.copy(camera.position);
      editorCamera.target.copy(controls.target);
      const spawnRoom = roomEntries[0]?.[1];
      if (spawnRoom) {
        simulation.player.set(
          (spawnRoom.grid_x + spawnRoom.width_cells / 2) * cell,
          1.6,
          (spawnRoom.grid_y + spawnRoom.depth_cells / 2) * cell,
        );
      } else {
        simulation.player.set(center.x, 1.6, center.z);
      }
      camera.position.copy(simulation.player);
      camera.getWorldDirection(cameraDirection);
      simulation.yaw = Math.atan2(-cameraDirection.x, -cameraDirection.z);
      simulation.pitch = 0;
      simulation.lastFrame = performance.now();
      simulation.active = true;
      simulationActiveRef.current = true;
      controls.enabled = false;
      transformControls.detach();
      transformControls.getHelper().visible = false;
      rotationControls.detach();
      rotationControls.getHelper().visible = false;
      setSimulationActive(true);
      renderer.domElement.focus();
      renderer.domElement.requestPointerLock();
    };
    const stopSimulation = () => {
      if (!simulation.active) return;
      simulation.active = false;
      simulationActiveRef.current = false;
      simulation.keys.clear();
      const pendingLayout = pendingSimulationLayoutRef.current;
      if (pendingLayout) {
        changeRef.current(pendingLayout);
        pendingSimulationLayoutRef.current = null;
      }
      pendingSimulationParentsRef.current.splice(0).forEach(({ objectId, parentId }) => {
        simulationPlaceRef.current?.(objectId, parentId);
      });
      if (heldObjectId) {
        const heldMesh = objectMeshes.get(heldObjectId);
        const original = heldOriginalPositions.get(heldObjectId);
        if (heldMesh && original) heldMesh.position.copy(original);
        const originalRotation = heldOriginalRotations.get(heldObjectId);
        if (heldMesh && originalRotation) heldMesh.quaternion.copy(originalRotation);
        if (heldMesh) heldMesh.userData.held = false;
        const originalParent = heldOriginalParents.get(heldObjectId);
        if (originalParent) placedContents.set(originalParent, (placedContents.get(originalParent) ?? 0) + 1);
        heldObjectId = null;
        setHeldObjectLabel("");
      }
      if (document.pointerLockElement === renderer.domElement) document.exitPointerLock();
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
    simulationControllerRef.current = { start: startSimulation, stop: stopSimulation };
    const onKeyDown = (event: KeyboardEvent) => {
      if (simulation.active && event.code === "KeyV" && !event.repeat) {
        setViewMode((mode) => mode === "first" ? "third" : "first");
        return;
      }
      if (simulation.active && (event.code === "KeyQ" || event.code === "KeyE")) {
        event.preventDefault();
        if (!event.repeat) {
          handsRef.current[event.code === "KeyQ" ? "left" : "right"] = true;
          pointer.set(0, 0);
          raycaster.setFromCamera(pointer, camera);
          const hit = raycaster.intersectObjects(interactive, false).find((candidate) => String(candidate.object.userData.id || "") !== heldObjectId);
          if (hit) simulationClick(hit);
        }
        return;
      }
      if (!simulation.active || !["KeyW", "KeyA", "KeyS", "KeyD"].includes(event.code)) return;
      event.preventDefault();
      simulation.keys.add(event.code);
    };
    const onKeyUp = (event: KeyboardEvent) => {
      if (event.code === "KeyQ") handsRef.current.left = false;
      if (event.code === "KeyE") handsRef.current.right = false;
      simulation.keys.delete(event.code);
    };
    const onMouseLook = (event: MouseEvent) => {
      if (!simulation.active || document.pointerLockElement !== renderer.domElement) return;
      simulation.yaw -= event.movementX * 0.0022;
      simulation.pitch = THREE.MathUtils.clamp(simulation.pitch - event.movementY * 0.0022, -Math.PI / 2 + 0.08, Math.PI / 2 - 0.08);
    };
    const onPointerLockChange = () => {
      const locked = document.pointerLockElement === renderer.domElement;
      setPointerLocked(locked);
      if (!locked) simulation.keys.clear();
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    document.addEventListener("mousemove", onMouseLook);
    document.addEventListener("pointerlockchange", onPointerLockChange);
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const dragPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
    const dragPoint = new THREE.Vector3();
    const nodeCapabilities = (node: RawNode | undefined): string[] => Array.isArray(node?.capabilities) ? node.capabilities.map(String) : [];
    const isPickable = (id: string) => {
      const node = nodeById.get(id);
      const capabilities = nodeCapabilities(node);
      if (capabilities.some((item) => ["pickable", "pickupable", "graspable"].includes(item))) return true;
      if (text(node?.mobility) !== "movable" && text(node?.node_type) !== "movable_object") return false;
      const mesh = objectMeshes.get(id);
      if (!mesh) return false;
      if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox();
      const bounds = mesh.geometry.boundingBox;
      if (!bounds) return false;
      const size = new THREE.Vector3().subVectors(bounds.max, bounds.min);
      // A generic movable node is only implicitly graspable when it is a
      // hand-sized item. Large furniture must explicitly declare pickable.
      const volume = size.x * size.y * size.z;
      return Math.max(size.x, size.y, size.z) <= 0.5 && volume <= 0.08;
    };
    const isPlaceTarget = (id: string, normal?: THREE.Vector3) => {
      const node = nodeById.get(id);
      const capabilities = nodeCapabilities(node);
      if (id === "__floor__") return Boolean(normal?.y && normal.y > 0.5);
      return capabilities.some((item) => ["place_target", "receptacle", "support_surface"].includes(item))
        || Boolean(normal?.y && normal.y > 0.5);
    };
    const toggleComponent = (hitObject: THREE.Object3D) => {
      const role = text(hitObject.userData.componentRole);
      const componentId = text(hitObject.userData.componentId);
      if (!componentId || !["door", "drawer"].some((kind) => role === kind || role.startsWith(`${kind}_`))) return false;
      const parentStates = nodeById.get(String(hitObject.userData.id || ""))?.states as Record<string, unknown> | undefined;
      runtimeOpen.set(componentId, !(runtimeOpen.get(componentId) ?? Boolean(parentStates?.is_open)));
      return true;
    };
    const simulationClick = (hit: THREE.Intersection<THREE.Object3D>) => {
      if (!simulation.active) return;
      const componentRole = text(hit.object.userData.componentRole);
      const componentId = text(hit.object.userData.componentId);
      const id = String(hit.object.userData.id || "");
      if (!id) return;
      const targetNode = nodeById.get(id);
      const componentNode = componentId ? nodeById.get(componentId) : undefined;
      const targetCapabilities = [...new Set([...nodeCapabilities(targetNode), ...nodeCapabilities(componentNode)])];
      const normal = hit.face?.normal?.clone().transformDirection(hit.object.matrixWorld) ?? new THREE.Vector3(0, 1, 0);
      const controlledIds = controlTargets.get(componentId) ?? controlTargets.get(id) ?? [];
      const accessOpen = [...runtimeOpen.entries()].some(([accessId, open]) => {
        if (!open) return false;
        const accessNode = nodeById.get(accessId);
        return text(accessNode?.parent) === id || text(accessNode?.parent_id) === id;
      });
      const resolution = resolveLocalInteraction({
        id: componentId || id,
        capabilities: targetCapabilities,
        componentRole,
        isOpen: runtimeOpen.get(componentId || id) ?? Boolean((componentNode?.states as Record<string, unknown> | undefined)?.is_open),
        hostRunning: runtimeDeviceRunning.get(id) ?? false,
        startRequiresClosed: Boolean(targetNode?.requires_closed_to_start) || targetCapabilities.includes("start_requires_closed"),
        accessOpen,
        pickable: isPickable(id),
        placeTarget: isPlaceTarget(id, normal) && normal.y > 0.5,
      }, heldObjectId);
      if (!resolution.action) return;
      if (resolution.action === "drain") {
        runtimeSinkFill.set(id, 0);
        setRuntimeStatusOverrides((current) => ({ ...current, [id]: { fill_level: 0, is_full: false, has_water: false, water_level: 0 } }));
        const water = waterMeshes.get(id);
        if (water) water.visible = false;
        return;
      }
      if (resolution.action === "open" || resolution.action === "close") {
        if (!toggleComponent(hit.object)) runtimeOpen.set(componentId || id, resolution.action === "open");
        return;
      }
      if (resolution.action === "press") {
        const targets = controlledIds.length ? controlledIds : [id];
        targets.forEach((targetId) => {
          const controlledNode = nodeById.get(targetId);
          const capabilities = nodeCapabilities(controlledNode);
          if (capabilities.includes("water_source_control")) {
            if (runtimeFaucetOpen.has(targetId)) runtimeFaucetOpen.delete(targetId);
            else runtimeFaucetOpen.add(targetId);
            return;
          }
          if (capabilities.includes("timed_device") || runtimeDeviceRunning.has(targetId)) {
            const nextRunning = !runtimeDeviceRunning.get(targetId);
            runtimeDeviceRunning.set(targetId, nextRunning);
            const device = objectMeshes.get(targetId);
            if (device?.material instanceof THREE.MeshStandardMaterial) {
              device.material.emissive.set(nextRunning ? 0x0ea5e9 : 0x000000);
              device.material.emissiveIntensity = nextRunning ? 0.45 : 0;
            }
            return;
          }
          const nextOn = !(runtimeLightState.get(targetId) ?? Boolean((controlledNode?.states as Record<string, unknown> | undefined)?.is_on));
          runtimeLightState.set(targetId, nextOn);
          const lamp = objectMeshes.get(targetId);
          lamp?.traverse((part) => {
            if (part instanceof THREE.PointLight) part.intensity = nextOn ? 2.8 : 0;
            if (part === lamp && part instanceof THREE.Mesh && part.material instanceof THREE.MeshStandardMaterial) {
              part.material.emissive.set(nextOn ? 0xffd166 : 0x000000);
              part.material.emissiveIntensity = nextOn ? 0.85 : 0;
            }
          });
        });
        return;
      }
      if (heldObjectId && resolution.action === "place") {
        if (id === heldObjectId) return;
        const heldMesh = objectMeshes.get(heldObjectId);
        if (heldMesh && isPlaceTarget(id, normal) && normal.y > 0.5) {
          if (hit.distance > 3.5 || hit.point.y > 2.2) return;
          const heldBounds = heldMesh.geometry.boundingBox;
          const halfHeight = heldBounds ? (heldBounds.max.y - heldBounds.min.y) / 2 : 0.05;
          const targetNode = nodeById.get(id);
          const targetMeta = targetNode ?? (hit.object.userData as Record<string, unknown>);
          const declaredCapacity = Number(targetMeta?.capacity ?? targetMeta?.slot_count ?? targetMeta?.maxCapacity);
          const capacity = id === "__floor__" || !Number.isFinite(declaredCapacity)
            ? Number.POSITIVE_INFINITY
            : declaredCapacity;
          const alreadyPlaced = placedContents.get(id) ?? edges.filter((edge) =>
            text(edge.source_id || edge.source) === id && ["on", "contains", "inside"].includes(text(edge.relation || edge.edge_type)),
          ).length;
          if (alreadyPlaced >= capacity) return;
          const requiredCapabilities = Array.isArray(targetMeta?.requiresContainedCapabilities)
            ? targetMeta.requiresContainedCapabilities.map(String).map((value) => value.toLowerCase())
            : [];
          if (requiredCapabilities.length) {
            const heldNode = nodeById.get(heldObjectId);
            const heldCapabilities = Array.isArray(heldNode?.capabilities)
              ? heldNode.capabilities.map(String).map((value) => value.toLowerCase())
              : [];
            const missing = requiredCapabilities.filter((value) => !heldCapabilities.includes(value));
            if (missing.length) return;
          }
          const heldSize = heldBounds?.getSize(new THREE.Vector3()) ?? new THREE.Vector3(0.1, 0.1, 0.1);
          const targetSize = id === "__floor__"
            ? { width: allWidth, depth: allDepth, height: roomHeight }
            : dimensionsFor(id);
          if (heldSize.x > targetSize.width || heldSize.y > targetSize.height || heldSize.z > targetSize.depth) return;
          const configuredGridCm = Number(targetNode?.surface_grid_cm ?? targetNode?.support_grid_cm ?? 10);
          const gridMeters = Math.max(0.01, Number.isFinite(configuredGridCm) ? configuredGridCm / 100 : 0.1);
          // Place the object's footprint centre on the hit surface, snapped
          // to the scene grid. This prevents half-sunk or tilted placements.
          const surfaceY = id === "__floor__" ? 0 : hit.point.y;
          let placeX = Math.round(hit.point.x / gridMeters) * gridMeters;
          let placeZ = Math.round(hit.point.z / gridMeters) * gridMeters;
          if (id !== "__floor__") {
            const targetBounds = new THREE.Box3().setFromObject(hit.object);
            const halfWidth = heldBounds ? (heldBounds.max.x - heldBounds.min.x) / 2 : 0.05;
            const halfDepth = heldBounds ? (heldBounds.max.z - heldBounds.min.z) / 2 : 0.05;
            placeX = THREE.MathUtils.clamp(placeX, targetBounds.min.x + halfWidth, targetBounds.max.x - halfWidth);
            placeZ = THREE.MathUtils.clamp(placeZ, targetBounds.min.z + halfDepth, targetBounds.max.z - halfDepth);
          } else {
            placeX = THREE.MathUtils.clamp(placeX, heldSize.x / 2, allWidth - heldSize.x / 2);
            placeZ = THREE.MathUtils.clamp(placeZ, heldSize.z / 2, allDepth - heldSize.z / 2);
          }
          const supportTop = id === "__floor__" ? 0 : new THREE.Box3().setFromObject(hit.object).max.y;
          const supportY = Math.max(surfaceY, supportTop);
          if (supportY > 1.8 || Math.abs(hit.point.y - supportY) > 0.18) return;
          heldMesh.position.set(placeX, supportY + Math.max(0.01, halfHeight), placeZ);
          const originalRotation = heldOriginalRotations.get(heldObjectId) ?? new THREE.Quaternion();
          heldMesh.quaternion.copy(originalRotation);
          heldMesh.userData.held = false;
          heldMesh.userData.parentObjectId = id;
          placedContents.set(id, alreadyPlaced + 1);
          heldOriginalParents.delete(heldObjectId);
          heldOriginalPositions.delete(heldObjectId);
          heldOriginalRotations.delete(heldObjectId);
          const baseLayout = pendingSimulationLayoutRef.current ?? layout;
          const currentPlacement = baseLayout.objects[heldObjectId];
          const objectNode = nodeById.get(heldObjectId);
          const roomId = currentPlacement?.room_id ?? String(objectNode?.room_id || "");
          const room = layout.rooms[roomId];
          if (currentPlacement && room) {
            const widthCm = currentPlacement.width_cm ?? currentPlacement.width_cells * cell * 100;
            const depthCm = currentPlacement.depth_cm ?? currentPlacement.depth_cells * cell * 100;
            const roomXcm = room.x_cm ?? room.grid_x * cell * 100;
            const roomYcm = room.y_cm ?? room.grid_y * cell * 100;
            const xCm = Math.round((placeX - widthCm / 200) * 100);
            const yCm = Math.round((placeZ - depthCm / 200) * 100);
            const targetParentId = id === "__floor__" ? roomId : id;
            const nextLayout = structuredClone(baseLayout);
            nextLayout.objects[heldObjectId] = {
              ...currentPlacement,
              placement_mode: "surface",
              parent_object_id: targetParentId === roomId ? undefined : targetParentId,
              layout_anchor: "surface",
              x_cm: xCm,
              y_cm: yCm,
              z_cm: Math.round((heldMesh.position.y - halfHeight) * 100),
              grid_x: Math.max(0, Math.floor((xCm - roomXcm) / (cell * 100))),
              grid_y: Math.max(0, Math.floor((yCm - roomYcm) / (cell * 100))),
              rotation: normalizeQuarterTurn(heldMesh.rotation.y),
              rotation_x: normalizeQuarterTurn(heldMesh.rotation.x),
              rotation_y: normalizeQuarterTurn(heldMesh.rotation.y),
              rotation_z: normalizeQuarterTurn(heldMesh.rotation.z),
            };
            pendingSimulationLayoutRef.current = nextLayout;
            pendingSimulationParentsRef.current.push({ objectId: heldObjectId, parentId: targetParentId });
          }
          heldObjectId = null;
          setHeldObjectLabel("");
        }
        return;
      }
      if (resolution.action === "pick") {
        const mesh = objectMeshes.get(id);
        if (!mesh) return;
        const parentId = text(edges.find((edge) =>
          text(edge.target_id || edge.target) === id
          && ["on", "contains", "inside"].includes(text(edge.relation || edge.edge_type)),
        )?.source_id || "");
        if (parentId) {
          const count = placedContents.get(parentId) ?? edges.filter((edge) =>
            text(edge.source_id || edge.source) === parentId
            && ["on", "contains", "inside"].includes(text(edge.relation || edge.edge_type)),
          ).length;
          placedContents.set(parentId, Math.max(0, count - 1));
          heldOriginalParents.set(id, parentId);
        }
        heldOriginalPositions.set(id, mesh.position.clone());
        heldOriginalRotations.set(id, mesh.quaternion.clone());
        heldObjectId = id;
        mesh.userData.held = true;
        setHeldObjectLabel(nodeName(nodeById.get(id)) || id);
      }
    };
    const onPointerDown = (event: PointerEvent) => {
      if (event.button !== 0) return;
      if (gizmoLock.active) return;
      dragState.pointerId = event.pointerId;
      dragState.startX = event.clientX;
      dragState.startY = event.clientY;
      dragState.moved = false;
      dragState.hit = false;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = simulation.active ? 0 : ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = simulation.active ? 0 : -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);

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
      const hits = raycaster.intersectObjects(interactive, false).filter((candidate) => String(candidate.object.userData.id || "") !== heldObjectId);
      // Prefer the nearest actual object mesh. The floor is only a target in
      // simulation mode; it must never become an editor selection.
      const componentHit = simulation.active
        ? hits.find((candidate) => {
            const role = text(candidate.object.userData.componentRole);
            return role === "sink_drain" || role === "faucet" || role === "storage_slot" || role === "door" || role.startsWith("drawer") || role.includes("button");
          })
        : undefined;
      const objectHit = hits.find((candidate) => objectMeshes.has(String(candidate.object.userData.id)));
      const hit = componentHit && (!objectHit || componentHit.distance <= objectHit.distance + 0.08)
        ? componentHit
        : objectHit ?? (simulation.active ? hits.find((candidate) => candidate.object.userData.simulationSurface) : undefined);
      if (!hit?.object.userData.id) {
        dragState.id = "";
        return;
      }
      const id = String(hit.object.userData.id);
      if (simulation.active) {
        const cardId = String(hit.object.userData.id || "");
        if (nodeById.has(cardId)) {
          setStatusCardId(cardId);
          selectRef.current(cardId);
        }
        dragState.hit = true;
        return;
      }
      simulationClick(hit);
      if (onInteractionHit) {
        const point = hit.point;
        const normal = hit.face?.normal?.clone().transformDirection(hit.object.matrixWorld);
        const uv = hit.uv;
        const hitMesh = hit.object as THREE.Mesh;
        const localPoint = hitMesh.worldToLocal(point.clone());
        const geometry = hitMesh.geometry;
        if (!geometry.boundingBox) geometry.computeBoundingBox();
        const bounds = geometry.boundingBox;
        const volumeUv = bounds
          ? [
              THREE.MathUtils.clamp((localPoint.x - bounds.min.x) / Math.max(1e-6, bounds.max.x - bounds.min.x), 0, 1),
              THREE.MathUtils.clamp((localPoint.y - bounds.min.y) / Math.max(1e-6, bounds.max.y - bounds.min.y), 0, 1),
              THREE.MathUtils.clamp((localPoint.z - bounds.min.z) / Math.max(1e-6, bounds.max.z - bounds.min.z), 0, 1),
            ] as [number, number, number]
          : undefined;
        onInteractionHit({
          node_id: id,
          ...(uv ? { surface_uv: [uv.x, uv.y] } : {}),
          ...(volumeUv ? { volume_uv: volumeUv } : {}),
          point_cm: [point.x * 100, point.y * 100, point.z * 100],
          ...(normal ? { normal: [normal.x, normal.y, normal.z] } : {}),
          ray_origin: [raycaster.ray.origin.x, raycaster.ray.origin.y, raycaster.ray.origin.z],
          ray_direction: [raycaster.ray.direction.x, raycaster.ray.direction.y, raycaster.ray.direction.z],
          distance_m: hit.distance,
        });
      }
      dragState.hit = true;
      selectRef.current(id);
      const item = layout.objects[id];
      if (item && !simulation.active) {
        transformControls.attach(objectMeshes.get(id)!);
        rotationControls.attach(objectMeshes.get(id)!);
        dragState.id = "";
      }
    };
    const onPointerMove = (event: PointerEvent) => {
      if (simulation.active) return;
      if (!dragState.id) return;
      if (Math.hypot(event.clientX - dragState.startX, event.clientY - dragState.startY) > 3) dragState.moved = true;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
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
    let frame = 0;
    const animate = () => {
      const now = performance.now();
      const delta = Math.min((now - simulation.lastFrame) / 1000, 0.05);
      if (simulation.active) {
        const forwardAmount = Number(simulation.keys.has("KeyW")) - Number(simulation.keys.has("KeyS"));
        const rightAmount = Number(simulation.keys.has("KeyD")) - Number(simulation.keys.has("KeyA"));
        const length = Math.hypot(forwardAmount, rightAmount) || 1;
        const speed = 2.2 * delta;
        const dx = ((-Math.sin(simulation.yaw) * forwardAmount) + (Math.cos(simulation.yaw) * rightAmount)) * speed / length;
        const dz = ((-Math.cos(simulation.yaw) * forwardAmount) + (-Math.sin(simulation.yaw) * rightAmount)) * speed / length;
        const radius = 0.28;
        const blocked = (x: number, z: number) => collisionMeshes.some((mesh) => {
          if (!mesh.visible || mesh.userData.held) return false;
          const node = nodeById.get(String(mesh.userData.id));
          if (node && ["floor", "room"].includes(semantic(node))) return false;
          const box = new THREE.Box3().setFromObject(mesh);
          return x + radius > box.min.x && x - radius < box.max.x
            && z + radius > box.min.z && z - radius < box.max.z
            && box.min.y < 1.6 && box.max.y > 0;
        });
        if (!blocked(simulation.player.x + dx, simulation.player.z)) simulation.player.x += dx;
        if (!blocked(simulation.player.x, simulation.player.z + dz)) simulation.player.z += dz;
        simulation.player.x = THREE.MathUtils.clamp(simulation.player.x, 0.15, Math.max(0.15, allWidth - 0.15));
        simulation.player.z = THREE.MathUtils.clamp(simulation.player.z, 0.15, Math.max(0.15, allDepth - 0.15));
        simulation.player.y = 1.6;
        playerBody.position.set(simulation.player.x, 0.8, simulation.player.z);
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
        if (heldObjectId) {
          const heldMesh = objectMeshes.get(heldObjectId);
          if (heldMesh) {
            camera.getWorldDirection(cameraDirection);
            heldMesh.position.copy(camera.position)
              .addScaledVector(cameraDirection, 0.85)
              .add(new THREE.Vector3(0.28, -0.22, 0));
            heldMesh.quaternion.copy(camera.quaternion);
          }
        }
        const handPose = (hand: THREE.Mesh, left: boolean, raised: boolean) => {
          const side = left ? -1 : 1;
          camera.updateMatrixWorld();
          const target = third
            ? simulation.player.clone().add(new THREE.Vector3(
              side * (raised ? 0.34 : 0.26),
              raised ? 1.35 : 1.05,
              -0.18,
            ).applyAxisAngle(new THREE.Vector3(0, 1, 0), simulation.yaw))
            : camera.position.clone().add(new THREE.Vector3(
              side * (raised ? 0.3 : 0.22), raised ? -0.05 : -0.2, -0.48,
            ).applyQuaternion(camera.quaternion));
          hand.position.lerp(target, Math.min(1, delta * 12));
          hand.quaternion.copy(third ? new THREE.Quaternion().setFromEuler(new THREE.Euler(0, simulation.yaw, 0)) : camera.quaternion);
          hand.visible = true;
        };
        handPose(hands.left, true, handsRef.current.left || Boolean(heldObjectId));
        handPose(hands.right, false, handsRef.current.right);
      } else {
        controls.update();
      }
      simulation.lastFrame = now;
      const time = performance.now() / 1000;
      animatedMeshes.forEach(({ mesh, base }, id) => {
        const node = nodeById.get(id);
        const nodeStates = node?.states as Record<string, unknown> | undefined;
        const nodeSemantic = semantic(node);
        if (nodeSemantic === "sink") {
          const connectedFaucets = faucetsBySink.get(id) ?? [];
          const flowing = connectedFaucets.some((faucet) => runtimeFaucetOpen.has(text(faucet.id)));
          let level = runtimeSinkFill.get(id) ?? 0;
          if (flowing && level < 1) {
            level = Math.min(1, level + delta * 0.16);
            runtimeSinkFill.set(id, level);
            const levelBand = Math.min(6, Math.max(0, Math.ceil(level * 6)));
            setRuntimeStatusOverrides((current) => ({
              ...current,
              [id]: {
                fill_level: level,
                is_full: level >= 1,
                has_water: level > 0,
                water_level: Math.round(level * 100),
                water_level_band: levelBand,
              },
            }));
          }
          const filled = level > 0;
          mesh.visible = filled;
          const wave = filled ? 1 + Math.sin(time * 2.8) * 0.012 : 1;
          mesh.scale.set(wave, Math.max(0.02, level), wave);
          const waterHeight = dimensionsFor(id).height;
          mesh.position.set(base.x, filled ? waterHeight * (0.05 + 0.225 * level) + Math.sin(time * 2) * 0.003 : -0.035, base.z);
          return;
        }
        const running = Boolean(nodeStates?.is_running) || (Boolean(nodeStates?.is_on) && ["fan", "ceiling_fan", "ventilator"].includes(nodeSemantic));
        const interactiveRunning = runtimeDeviceRunning.get(id) ?? false;
        const falling = node?.physics_state === "falling";
        if (!running && !interactiveRunning && !falling) {
          mesh.position.copy(base);
          return;
        }
        if (falling) {
          const drop = Number(node?.drop_height_cm ?? 0) / 100;
          mesh.position.set(base.x, Math.max(mesh.geometry.boundingBox?.max.y ?? 0.02, base.y - drop), base.z);
          return;
        }
        const pulse = Math.sin(time * (interactiveRunning ? 24 : 18) + id.length) * (interactiveRunning ? 0.008 : 0.003);
        mesh.position.set(base.x + pulse, base.y, base.z - pulse * 0.7);
      });
      composites.forEach((composite) => {
        const hostStates = nodeById.get(composite.id)?.states as Record<string, unknown> | undefined;
        composite.joints.forEach((joint) => {
          const componentNode = nodeById.get(joint.id);
          const states = componentNode?.states as Record<string, unknown> | undefined;
          joint.open = runtimeOpen.get(joint.id)
            ?? Boolean(states?.is_open ?? hostStates?.is_open);
        });
      });
      updateComposites(composites);
      effectMeshes.forEach(({ mesh, host, nodeId, kind, offset, phase }) => {
        const effectNode = nodeById.get(nodeId);
        const effectStates = effectNode?.states as Record<string, unknown> | undefined;
        mesh.visible = kind === "droplet"
          ? Boolean(effectStates?.is_wet)
          : kind === "drying"
            ? Boolean(effectStates?.is_wet) && effectStates?.cycle_remaining != null
              : kind === "steam"
              ? String(effectStates?.temperature || "").toLowerCase() === "hot"
              : kind === "stain"
                ? Boolean(effectStates?.is_dirty)
                : Boolean(effectStates?.is_broken);
        if (!mesh.visible) return;
        mesh.position.copy(host.position).add(offset);
        if (kind === "droplet") {
          const slide = (time * 0.22 + phase * 0.17) % 1;
          mesh.position.y = host.position.y + offset.y + host.geometry.boundingBox!.min.y + slide * (host.geometry.boundingBox!.max.y - host.geometry.boundingBox!.min.y);
          mesh.position.x += Math.sin(time * 4 + phase) * 0.008;
          mesh.scale.setScalar(0.78 + 0.22 * Math.sin(time * 4 + phase) ** 2);
        } else if (kind === "stain") {
          mesh.position.copy(host.position).add(offset);
        } else if (kind === "drying" || kind === "steam") {
          const bob = (Math.sin(time * 3.5 + phase) + 1) * 0.025;
          mesh.position.y += bob;
          mesh.scale.setScalar(0.72 + 0.28 * Math.sin(time * 2.5 + phase) ** 2);
        } else {
          mesh.rotation.y = time * 0.12;
        }
      });
      objectLabels.forEach((label, id) => {
        const mesh = objectMeshes.get(id);
        if (mesh) {
          label.position.set(mesh.position.x, mesh.position.y + (mesh.geometry.boundingBox?.max.y ?? 0.4) + 0.05, mesh.position.z - (mesh.geometry.boundingBox?.max.z ?? 0));
          selectionVisualsRef.current.get(id)?.position.copy(mesh.position);
        }
      });
      if (labelsVisible) {
        camera.updateMatrixWorld();
        const direction = new THREE.Vector3();
        const ray = new THREE.Raycaster();
        objectLabels.forEach((label, id) => {
          const target = objectMeshes.get(id);
          if (!target) return;
          direction.subVectors(label.position, camera.position);
          const distance = direction.length();
          ray.set(camera.position, direction.normalize());
          const blockers = ray.intersectObjects(collisionMeshes, false);
          label.visible = !blockers.some((hit) => hit.object !== target && hit.distance < distance - 0.04);
        });
      }
      renderer.render(scene, camera);
      frame = requestAnimationFrame(animate);
    };
    animate();
    return () => { if (simulation.active) { simulation.active = false; simulationActiveRef.current = false; if (document.pointerLockElement === renderer.domElement) document.exitPointerLock(); camera.position.copy(editorCamera.position); controls.target.copy(editorCamera.target); } cameraStateRef.current = { position: camera.position.clone(), target: controls.target.clone() }; simulationControllerRef.current = null; window.removeEventListener("keydown", onKeyDown); window.removeEventListener("keyup", onKeyUp); document.removeEventListener("mousemove", onMouseLook); document.removeEventListener("pointerlockchange", onPointerLockChange); commitTransform(); transformControls.detach(); transformControls.dispose(); transformControlsRef.current = null; rotationControls.detach(); rotationControls.dispose(); rotationControlsRef.current = null; cancelAnimationFrame(frame); observer.disconnect(); renderer.domElement.removeEventListener("pointerdown", onPointerDown); renderer.domElement.removeEventListener("pointermove", onPointerMove); renderer.domElement.removeEventListener("pointerup", onPointerUp); controls.dispose(); renderer.dispose(); sceneRef.current = null; scene.traverse((item) => { if (item instanceof THREE.Mesh) { item.geometry.dispose(); if (Array.isArray(item.material)) item.material.forEach((material) => material.dispose()); else item.material.dispose(); } }); host.replaceChildren(); };
  }, [layout, nodes, labelsVisible, catalog, onInteractionHit, layerVisibility]);

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
        <label><input type="checkbox" checked={layerVisibility.ceiling} onChange={(event) => setLayerVisibility((value) => ({ ...value, ceiling: event.target.checked }))} /> 天花板层</label>
        <label><input type="checkbox" checked={layerVisibility.floor} onChange={(event) => setLayerVisibility((value) => ({ ...value, floor: event.target.checked }))} /> 地板层</label>
        <label><input type="checkbox" checked={layerVisibility.objects} onChange={(event) => setLayerVisibility((value) => ({ ...value, objects: event.target.checked }))} /> 物体层</label>
        <small>墙壁始终显示</small>
      </div>}
    </div>}
    <button className={`scene3d-simulation-toggle${simulationActive ? " is-running" : ""}`} type="button" onClick={() => simulationActive ? simulationControllerRef.current?.stop() : simulationControllerRef.current?.start()}>
      {simulationActive ? <Square size={15} /> : <Play size={15} />}
      {simulationActive ? "退出仿真" : "开始仿真"}
    </button>
    {simulationActive && <button className="scene3d-view-toggle" type="button" onClick={() => setViewMode((mode) => mode === "first" ? "third" : "first")}>{viewMode === "first" ? "第三人称" : "第一人称"}</button>}
    {simulationActive && <>
      <div className="scene3d-crosshair" aria-hidden="true" />
      <div className="scene3d-simulation-hint">
        <strong>{viewMode === "first" ? "第一人称仿真" : "第三人称仿真"}</strong>
        <span>WASD 移动 · 鼠标观察 · 左键查看状态 · Q/E 交互 · Esc 释放鼠标</span>
        {heldObjectLabel && <span className="scene3d-held-status">手持：{heldObjectLabel} · 对准承载面按 Q/E 放置</span>}
        {!pointerLocked && <button type="button" onClick={() => simulationControllerRef.current?.start()}>点击继续控制视角</button>}
      </div>
      {statusCardId && (() => {
        const node = nodes.find((item) => text(item.id) === statusCardId);
        if (!node) return null;
        const states = { ...((node.states && typeof node.states === "object") ? node.states as Record<string, unknown> : {}), ...(runtimeStatusOverrides[statusCardId] ?? {}) };
        const property = node.property && typeof node.property === "object" ? node.property as Record<string, unknown> : {};
        const attributes = Object.entries(property).filter(([, value]) => value != null && value !== "" && !(Array.isArray(value) && value.length === 0) && !(typeof value === "object" && !Array.isArray(value) && Object.keys(value as object).length === 0));
        if (semantic(node)) attributes.unshift(["类型", semantic(node)]);
        const format = (value: unknown) => Array.isArray(value) ? value.join(", ") : typeof value === "object" && value !== null ? JSON.stringify(value) : String(value);
        return <section className="scene3d-status-card" aria-label="物体状态">
          <header><strong>{nodeName(node)}</strong><button type="button" aria-label="关闭状态卡片" title="关闭" onClick={() => setStatusCardId("")}><X size={15} /></button></header>
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
