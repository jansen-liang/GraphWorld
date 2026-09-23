import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { TransformControls } from "three/examples/jsm/controls/TransformControls.js";
import { Eye, EyeOff, Play, Square, Layers3 } from "lucide-react";
import type { FloorplanLayout } from "./FloorplanCanvas";
import type { ObjectCatalogEntry } from "../../api/scenes";
import type { InteractionHit } from "../../types/api";
import { attachHinge, attachPart, attachPrismatic, createComposite, updateComposites, type CompositeObject } from "./compositeRuntime";

type RawNode = Record<string, unknown>;

interface Scene3DCanvasProps {
  nodes: RawNode[];
  layout: FloorplanLayout;
  selectedId: string;
  onSelect: (id: string) => void;
  onChange: (layout: FloorplanLayout) => void;
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

type WallSide = "north" | "east" | "south" | "west";
const OPPOSITE_WALL: Record<WallSide, WallSide> = { north: "south", east: "west", south: "north", west: "east" };

export function Scene3DCanvas({ nodes, layout, selectedId, onSelect, onChange, catalog, onInteractionHit }: Scene3DCanvasProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const selectRef = useRef(onSelect);
  const changeRef = useRef(onChange);
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
  const [viewMode, setViewMode] = useState<"first" | "third">("first");
  const [layersOpen, setLayersOpen] = useState(false);
  const [layerVisibility, setLayerVisibility] = useState({ labels: true, ceiling: true, floor: true, objects: true });
  const viewModeRef = useRef(viewMode);
  const handsRef = useRef({ left: false, right: false });
  selectRef.current = onSelect;
  changeRef.current = onChange;
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
    controls.enableDamping = true;
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
      kind: "droplet" | "drying" | "steam" | "broken";
      offset: THREE.Vector3;
      phase: number;
    }>();
    const composites: CompositeObject[] = [];
    const runtimeOpen = new Map<string, boolean>();
    let heldObjectId: string | null = null;
    const heldOriginalPositions = new Map<string, THREE.Vector3>();
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
    rotationControlsRef.current = rotationControls;
    objectMeshesRef.current = objectMeshes;
    scene.add(transformControls.getHelper());
    scene.add(rotationControls.getHelper());
    transformControls.setRotationSnap(Math.PI / 2);
    camera.layers.enable(1);
    if (!labelsVisible) camera.layers.disable(1);
    const dragState = { id: "", roomId: "", gridX: 0, gridY: 0, pointerId: -1, moved: false, hit: false, startX: 0, startY: 0 };
    const nodeById = new Map(nodes.map((node) => [text(node.id), node]));
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
      new THREE.MeshStandardMaterial({ color: 0xe2e8f0, roughness: 0.95 }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.set((allWidth - 1) / 2, -0.01, (allDepth - 1) / 2);
    floor.receiveShadow = true;
    floor.userData = { id: "__floor__", simulationSurface: true, layer: "floor" };
    scene.add(floor);
    // The floor is a valid placement surface in first-person mode. It is
    // filtered out of editor selection below so it cannot steal room clicks.
    interactive.push(floor);
    const grid = new THREE.GridHelper(Math.max(allWidth, allDepth) + 2, Math.ceil(Math.max(allWidth, allDepth) / cell), 0x94a3b8, 0xcbd5e1);
    grid.position.set((allWidth - 1) / 2, 0, (allDepth - 1) / 2);
    scene.add(grid);
    grid.userData.layer = "floor";

    const wallKeys = new Set<string>();
    const wallMaterial = () => new THREE.MeshStandardMaterial({ color: 0x64748b, roughness: 0.82, metalness: 0.02 });
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
      const catalogEntry = catalogByType.get(semantic(node));
      const [widthCm, depthCm, heightCm] = catalogEntry
        ? [catalogEntry.width_cm, catalogEntry.depth_cm, catalogEntry.height_cm]
        : [item.width_cm ?? Math.max(1, item.width_cells * cell * 100), item.depth_cm ?? Math.max(1, item.depth_cells * cell * 100), item.height_cm ?? 80];
      const width = widthCm / 100;
      const depth = depthCm / 100;
      const height = heightCm / 100;
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
      const selected = selectedId === objectId;
      const states = node?.states as Record<string, unknown> | undefined;
      const objectMaterial = new THREE.MeshStandardMaterial({ color: CATEGORY_COLORS[objectCategory(node)], transparent: true, opacity: 0.86, roughness: 0.72 });
      if (Boolean(states?.is_broken)) {
        objectMaterial.color = new THREE.Color(0x991b1b);
        objectMaterial.opacity = 0.72;
        objectMaterial.roughness = 0.95;
      }
      if (Boolean(states?.is_on) && ["light", "room_light"].includes(semantic(node))) {
        objectMaterial.emissive = new THREE.Color(0xffd166);
        objectMaterial.emissiveIntensity = 0.85;
      }
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(width, height, depth), objectMaterial);
      mesh.geometry.computeBoundingBox();
      mesh.position.set(x, baseHeight + (item.z_cm ?? 0) / 100 + height / 2, z);
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
      if (Boolean(states?.is_running) || (Boolean(states?.is_on) && ["fan", "ceiling_fan", "ventilator"].includes(semantic(node)))) {
        animatedMeshes.set(objectId, { mesh, base: mesh.position.clone() });
      }
      if (node?.physics_state === "falling") {
        animatedMeshes.set(objectId, { mesh, base: mesh.position.clone() });
      }
      if (Boolean(states?.is_wet)) {
        const dropletMaterial = new THREE.MeshStandardMaterial({ color: 0x38bdf8, emissive: 0x0369a1, emissiveIntensity: 0.25, transparent: true, opacity: 0.82, roughness: 0.25 });
        const dropletRadius = Math.max(0.012, Math.min(width, depth) * 0.035);
        [[-0.28, 0.2], [0.05, -0.16], [0.31, 0.08]].forEach(([ox, oz], index) => {
          const droplet = new THREE.Mesh(new THREE.SphereGeometry(dropletRadius, 8, 6), dropletMaterial.clone());
          droplet.position.set(mesh.position.x + ox * width, mesh.position.y + height * 0.25, mesh.position.z + oz * depth);
          scene.add(droplet);
          effectMeshes.push({ mesh: droplet, host: mesh, nodeId: objectId, kind: "droplet", offset: new THREE.Vector3(ox * width, height * 0.25, oz * depth), phase: index * 1.7 });
        });
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

      const composition = node?.composition && typeof node.composition === "object"
        ? node.composition as { components?: Array<Record<string, unknown>>; storage?: Record<string, unknown> }
        : null;
      const componentMaterial = (role: string) => new THREE.MeshStandardMaterial({
        color: role.includes("button") || role.includes("flush") ? 0xf59e0b : role.includes("drawer") ? 0x0f766e : 0x334155,
        transparent: true,
        opacity: 0.92,
        roughness: 0.62,
      });
      const addComponentMesh = (role: string, face: string, anchor: number[], geometry: THREE.BufferGeometry, position: THREE.Vector3, componentId = `${objectId}_${role}`) => {
        const component = new THREE.Mesh(geometry, componentMaterial(role));
        component.position.copy(position);
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
        const face = text(component.mount_face || "front");
        const anchor = Array.isArray(component.anchor) ? component.anchor.map(Number) : [0.5, 0.5, 0];
        const ax = Math.max(0, Math.min(1, anchor[0] ?? 0.5));
        const ay = Math.max(0, Math.min(1, anchor[1] ?? 0.5));
        const az = Math.max(0, Math.min(1, anchor[2] ?? 0));
        if (role.includes("button") || role.includes("knob")) {
          const buttonSize = Math.max(0.045, Math.min(width, depth) * 0.11);
          const buttonGeometry = new THREE.BoxGeometry(buttonSize, buttonSize, buttonSize * 0.5);
          const buttonPosition = face === "top"
            ? new THREE.Vector3(x + (ax - 0.5) * width, mesh.position.y + height / 2 + buttonSize / 2, z + (ay - 0.5) * depth)
            : new THREE.Vector3(x + (ax - 0.5) * width, mesh.position.y + (ay - 0.5) * height, z - depth / 2 - buttonSize / 3);
          addComponentMesh(role, face, [ax, ay, az], buttonGeometry, buttonPosition);
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
          const doorWidth = Math.max(0.08, width * 0.78);
          const doorHeight = Math.max(0.12, height * 0.76);
          const doorGeometry = face === "top"
            ? new THREE.BoxGeometry(doorWidth, 0.025, Math.max(0.08, depth * 0.72))
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
            pivot.position.set(x + (rightHinged ? width / 2 : -width / 2), mesh.position.y, z - depth / 2 - 0.02);
            const panel = new THREE.Mesh(doorGeometry, componentMaterial(role));
            panel.position.set(rightHinged ? -doorWidth / 2 : doorWidth / 2, 0, 0);
            panel.userData = { id: objectId, componentId: `${objectId}_${role}`, componentRole: role, componentFace: face };
            panel.castShadow = true;
            pivot.add(panel);
            scene.add(pivot);
            interactive.push(panel);
            attachHinge(composite, `${objectId}_${role}`, panel, pivot, rightHinged ? -Math.PI / 2 : Math.PI / 2);
          }
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
            slot.position.set(
              x + (column + 0.5 - columns / 2) * (width * 0.82 / columns),
              mesh.position.y - height / 2 + (level + 0.5) * (height * 0.72 / levels) + height * 0.14,
              z - depth * 0.04,
            );
            slot.userData = {
              id: objectId,
              componentId: `${objectId}_slot_l${level + 1}_c${column + 1}`,
              componentRole: "storage_slot",
            };
            scene.add(slot);
            interactive.push(slot);
            mountStoragePart(slot);
          }
        }
        for (let level = 1; level < levels; level += 1) {
          const shelf = new THREE.Mesh(new THREE.BoxGeometry(width * 0.82, 0.018, depth * 0.72), new THREE.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.8 }));
          shelf.position.set(x, mesh.position.y - height / 2 + (height * level) / levels, z - depth * 0.04);
          shelf.userData = { id: objectId, componentRole: "storage_shelf" };
          scene.add(shelf);
          mountStoragePart(shelf);
        }
        for (let column = 1; column < columns; column += 1) {
          const divider = new THREE.Mesh(new THREE.BoxGeometry(0.018, height * 0.76, depth * 0.72), new THREE.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.8 }));
          divider.position.set(x - width / 2 + (width * column) / columns, mesh.position.y, z - depth * 0.04);
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
          const drawer = new THREE.Group();
          drawer.position.set(
            x + (drawerColumn + 0.5 - columns / 2) * drawerWidth,
            mesh.position.y - height / 2 + height * 0.14 + (drawerLevel + 0.5) * (height * 0.72 / levels),
            z - depth / 2 - 0.035,
          );
          const componentId = `${objectId}_drawer_${drawerIndex + 1}`;
          drawer.userData = { id: objectId, componentId, componentRole: `drawer_${drawerIndex + 1}` };
          const wallDepth = Math.max(0.08, depth * 0.62);
          const wallThickness = 0.025;
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
          bottom.userData = { id: componentId, componentId, componentRole: "storage_slot", capabilities: ["place_target"] };
          drawer.add(bottom, front, back, left, right);
          scene.add(drawer);
          interactive.push(front);
          interactive.push(bottom);
          attachPrismatic(composite, componentId, drawer, Math.max(0.08, depth - 0.06));
        }
      }
    });

    const pendingTransform = { id: "", changed: false };
    const gizmoLock = { active: false };
    const transformGuard = { active: false };
    const lastValidPositions = new Map<string, THREE.Vector3>();
    const dimensionsFor = (id: string) => {
      const item = layout.objects[id];
      const entry = catalogByType.get(semantic(nodeById.get(id)));
      return {
        width: (entry?.width_cm ?? item?.width_cm ?? (item?.width_cells ?? 1) * cell * 100) / 100,
        depth: (entry?.depth_cm ?? item?.depth_cm ?? (item?.depth_cells ?? 1) * cell * 100) / 100,
        height: (entry?.height_cm ?? item?.height_cm ?? 80) / 100,
      };
    };
    const canOccupy = (id: string, position: THREE.Vector3) => {
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
      for (const [otherId, otherMesh] of objectMeshes) {
        if (otherId === id) continue;
        const other = layout.objects[otherId];
        if (!other || other.room_id !== item.room_id || other.placement_mode === "contained" || other.placement_mode === "wall_mounted") continue;
        const otherSize = dimensionsFor(otherId);
        if (Math.abs(position.x - otherMesh.position.x) < (dimensions.width + otherSize.width) / 2 && Math.abs(position.z - otherMesh.position.z) < (dimensions.depth + otherSize.depth) / 2 && Math.abs(position.y - otherMesh.position.y) < (dimensions.height + otherSize.height) / 2) return false;
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
      snapped.x = Math.max(roomX + size.width / 2, Math.min(roomX + roomWidth - size.width / 2, snapped.x));
      snapped.z = Math.max(roomZ + size.depth / 2, Math.min(roomZ + roomDepth - size.depth / 2, snapped.z));
      snapped.y = Math.max(size.height / 2, snapped.y);
      const previous = lastValidPositions.get(id) ?? mesh.position.clone();
      transformGuard.active = true;
      mesh.position.copy(canOccupy(id, snapped) ? snapped : previous);
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
        : item.placement_mode === "contained"
          ? Math.max(0.02, (parentMesh?.position.y ?? parentHeight) - parentHeight / 2 + 0.03)
          : 0;
      const next = structuredClone(layout);
      const room = layout.rooms[item.room_id];
      const xCm = Math.round((mesh.position.x - width / 200) * 100);
      const yCm = Math.round((mesh.position.z - depth / 200) * 100);
      next.objects[pendingTransform.id] = {
        ...next.objects[pendingTransform.id],
        // Keep the grid coordinates in sync with the physical snapshot. The
        // 2D editor renders these fields, while 3D preserves centimeter
        // precision and vertical placement in z_cm.
        grid_x: room ? Math.round((xCm - (room.x_cm ?? room.grid_x * cell * 100)) / (cell * 100)) : item.grid_x,
        grid_y: room ? Math.round((yCm - (room.y_cm ?? room.grid_y * cell * 100)) / (cell * 100)) : item.grid_y,
        x_cm: xCm,
        y_cm: yCm,
        z_cm: Math.round((mesh.position.y - baseHeight - height / 200) * 100),
        rotation: Math.round(mesh.rotation.y / (Math.PI / 2)) % 4,
        rotation_x: Math.round(mesh.rotation.x / (Math.PI / 2)) % 4,
        rotation_y: Math.round(mesh.rotation.y / (Math.PI / 2)) % 4,
        rotation_z: Math.round(mesh.rotation.z / (Math.PI / 2)) % 4,
      };
      changeRef.current(next);
      pendingTransform.id = "";
      pendingTransform.changed = false;
    };
    transformControls.addEventListener("dragging-changed", (event) => {
      controls.enabled = !(event.value as boolean);
      gizmoLock.active = Boolean(event.value);
      rotationControls.enabled = !Boolean(event.value);
      if (event.value) pendingTransform.id = String(transformControls.object?.userData.id || selectedId);
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
      if (event.value) pendingTransform.id = String(rotationControls.object?.userData.id || selectedId);
      else commitTransform();
    });
    rotationControls.addEventListener("mouseDown", () => { gizmoLock.active = true; transformControls.enabled = false; });
    rotationControls.addEventListener("mouseUp", () => { gizmoLock.active = false; transformControls.enabled = true; });
    rotationControls.addEventListener("objectChange", () => { pendingTransform.changed = true; });

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
    const hands = {
      left: new THREE.Mesh(new THREE.CapsuleGeometry(0.07, 0.28, 4, 8), new THREE.MeshStandardMaterial({ color: 0xf2b38b })),
      right: new THREE.Mesh(new THREE.CapsuleGeometry(0.07, 0.28, 4, 8), new THREE.MeshStandardMaterial({ color: 0xf2b38b })),
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
      if (heldObjectId) {
        const heldMesh = objectMeshes.get(heldObjectId);
        const original = heldOriginalPositions.get(heldObjectId);
        if (heldMesh && original) heldMesh.position.copy(original);
        if (heldMesh) heldMesh.userData.held = false;
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
      if (simulation.active && event.code === "KeyQ") { handsRef.current.left = true; return; }
      if (simulation.active && event.code === "KeyE") { handsRef.current.right = true; return; }
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
      const semanticType = semantic(node);
      if (["chair", "seat", "sofa", "bed", "table", "coffee_table", "desk", "counter", "cabinet", "wardrobe", "shelf", "rack", "toilet", "sink"].includes(semanticType)) return false;
      const capabilities = nodeCapabilities(node);
      if (capabilities.some((item) => ["pickable", "pickupable", "graspable"].includes(item))) return true;
      if (text(node?.node_type) !== "movable_object") return false;
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
      const type = semantic(node);
      if (id === "__floor__") return Boolean(normal?.y && normal.y > 0.5);
      return capabilities.some((item) => ["place_target", "receptacle", "support_surface"].includes(item))
        || ["table", "counter", "desk", "shelf", "cabinet", "drawer", "refrigerator", "washer", "washing_machine", "microwave"].includes(type)
        || Boolean(normal?.y && normal.y > 0.5);
    };
    const toggleComponent = (hitObject: THREE.Object3D) => {
      const role = text(hitObject.userData.componentRole);
      const componentId = text(hitObject.userData.componentId);
      if (!componentId || !["door", "drawer"].some((kind) => role === kind || role.startsWith(`${kind}_`))) return false;
      runtimeOpen.set(componentId, !(runtimeOpen.get(componentId) ?? false));
      return true;
    };
    const simulationClick = (hit: THREE.Intersection<THREE.Object3D>) => {
      if (!simulation.active) return;
      if (toggleComponent(hit.object)) return;
      const id = String(hit.object.userData.id || "");
      if (!id) return;
      if (heldObjectId) {
        if (id === heldObjectId) return;
        const heldMesh = objectMeshes.get(heldObjectId);
        const normal = hit.face?.normal?.clone().transformDirection(hit.object.matrixWorld) ?? new THREE.Vector3(0, 1, 0);
        if (heldMesh && isPlaceTarget(id, normal) && normal.y > 0.5) {
          const heldBounds = heldMesh.geometry.boundingBox;
          const halfHeight = heldBounds ? (heldBounds.max.y - heldBounds.min.y) / 2 : 0.05;
          const targetNode = nodeById.get(id);
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
            placeX = THREE.MathUtils.clamp(placeX, 0.05, allWidth - 0.05);
            placeZ = THREE.MathUtils.clamp(placeZ, 0.05, allDepth - 0.05);
          }
          heldMesh.position.set(placeX, surfaceY + Math.max(0.01, halfHeight), placeZ);
          heldMesh.rotation.set(0, 0, 0);
          heldMesh.quaternion.identity();
          heldMesh.userData.held = false;
          heldObjectId = null;
          setHeldObjectLabel("");
        }
        return;
      }
      if (isPickable(id)) {
        const mesh = objectMeshes.get(id);
        if (!mesh) return;
        heldOriginalPositions.set(id, mesh.position.clone());
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
      const hit = hits.find((candidate) => objectMeshes.has(String(candidate.object.userData.id)))
        ?? (simulation.active ? hits.find((candidate) => candidate.object.userData.simulationSurface) : undefined);
      if (!hit?.object.userData.id) {
        dragState.id = "";
        return;
      }
      const id = String(hit.object.userData.id);
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
      if (simulation.active) {
        const delta = Math.min((now - simulation.lastFrame) / 1000, 0.05);
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
          cameraTarget.y += 0.25;
        } else {
          camera.position.copy(simulation.player);
        }
        camera.rotation.set(simulation.pitch, simulation.yaw, 0, "YXZ");
        if (third) camera.lookAt(cameraTarget);
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
          const target = simulation.player.clone()
            .add(new THREE.Vector3(side * (raised ? 0.3 : 0.22), raised ? 1.35 : 0.95, -0.48));
          hand.position.lerp(target, Math.min(1, delta * 12));
          hand.quaternion.copy(camera.quaternion);
          hand.visible = viewModeRef.current === "first";
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
        const running = Boolean(nodeStates?.is_running) || (Boolean(nodeStates?.is_on) && ["fan", "ceiling_fan", "ventilator"].includes(nodeSemantic));
        const falling = node?.physics_state === "falling";
        if (!running && !falling) {
          mesh.position.copy(base);
          return;
        }
        if (falling) {
          const drop = Number(node?.drop_height_cm ?? 0) / 100;
          mesh.position.set(base.x, Math.max(mesh.geometry.boundingBox?.max.y ?? 0.02, base.y - drop), base.z);
          return;
        }
        const pulse = Math.sin(time * 18 + id.length) * 0.003;
        mesh.position.set(base.x + pulse, base.y, base.z - pulse * 0.7);
      });
      composites.forEach((composite) => {
        composite.joints.forEach((joint) => {
          const componentNode = nodeById.get(joint.id);
          const states = componentNode?.states as Record<string, unknown> | undefined;
          joint.open = runtimeOpen.get(joint.id)
            ?? Boolean(states?.is_open);
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
              : Boolean(effectStates?.is_broken);
        if (!mesh.visible) return;
        mesh.position.copy(host.position).add(offset);
        if (kind === "droplet") {
          const bob = (Math.sin(time * 5 + phase) + 1) * 0.018;
          mesh.position.y -= bob;
          mesh.scale.setScalar(0.78 + 0.22 * Math.sin(time * 4 + phase) ** 2);
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
        <span>WASD 移动 · 鼠标观察 · 左键点击物体 · Esc 释放鼠标</span>
        {heldObjectLabel && <span className="scene3d-held-status">手持：{heldObjectLabel} · 点击承载面放置</span>}
        {!pointerLocked && <button type="button" onClick={() => simulationControllerRef.current?.start()}>点击继续控制视角</button>}
      </div>
    </>}
  </div>;
}

function makeLabel(value: string, color = "#334155"): THREE.Sprite {
  const canvas = document.createElement("canvas");
  const measureCanvas = document.createElement("canvas");
  const measureContext = measureCanvas.getContext("2d")!;
  measureContext.font = "700 26px sans-serif";
  const labelWidth = Math.max(100, Math.min(520, Math.ceil(measureContext.measureText(value).width + 20)));
  canvas.width = labelWidth; canvas.height = 58;
  const context = canvas.getContext("2d")!;
  context.fillStyle = "rgba(255,255,255,0.92)";
  context.beginPath();
  context.roundRect(2, 2, labelWidth - 4, 54, 8);
  context.fill();
  context.font = "700 26px sans-serif";
  context.fillStyle = color;
  context.fillText(value.slice(0, 30), 6, 40);
  const texture = new THREE.CanvasTexture(canvas);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false }));
  sprite.scale.set(labelWidth / 220, 0.26, 1);
  return sprite;
}
