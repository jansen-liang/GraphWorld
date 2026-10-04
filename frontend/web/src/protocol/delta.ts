type RecordNode = Record<string, unknown>;

export interface SceneState {
  nodes?: RecordNode[];
  edges?: RecordNode[];
  world_state?: RecordNode;
  coordinate_system?: RecordNode;
  revision?: number;
  time_seconds?: number;
}

export interface SceneDelta {
  base_revision?: number;
  revision?: number;
  time_seconds?: number;
  changes?: Array<RecordNode>;
  nodes_added?: Array<RecordNode>;
  state_changes?: Array<RecordNode>;
  edges_added?: Array<RecordNode>;
  edges_removed?: Array<RecordNode>;
  nodes_removed?: string[];
  agent?: Record<string, RecordNode>;
  coordinate_system?: RecordNode;
}

function id(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function edgeKey(edge: RecordNode): string {
  return [
    id(edge.source_id ?? edge.source), id(edge.source_link_id),
    id(edge.target_id ?? edge.target), id(edge.target_link_id),
    id(edge.relation ?? edge.edge_type),
  ].join("\u0000");
}

function nodeId(payload: RecordNode): string {
  return id(payload.node_id ?? payload.id);
}

/** Apply a semantic runtime delta without replacing the live Three.js draft. */
export function applySimulationDelta(scene: SceneState, delta: SceneDelta, expectedRevision: number | null): boolean {
  const base = Number(delta.base_revision);
  if (expectedRevision != null && (!Number.isFinite(base) || base !== expectedRevision)) return false;
  const nodes = scene.nodes ?? (scene.nodes = []);
  const edges = scene.edges ?? (scene.edges = []);
  const byId = new Map(nodes.map((node) => [id(node.id), node]));
  const changes = Array.isArray(delta.changes) ? delta.changes : [];
  const addedNodes = Array.isArray(delta.nodes_added) ? delta.nodes_added : [];
  const stateChanges = Array.isArray(delta.state_changes) ? delta.state_changes : [];
  const addedEdges = Array.isArray(delta.edges_added) ? delta.edges_added : [];
  const removedEdges = Array.isArray(delta.edges_removed) ? delta.edges_removed : [];

  for (const change of changes) {
    const type = id(change.change_type);
    const payload = (change.payload && typeof change.payload === "object" ? change.payload : change) as RecordNode;
    if (type === "state_changed") stateChanges.push(payload);
    if (type === "joint_state_changed") {
      const target = byId.get(nodeId(payload));
      if (target) {
        const jointId = id(payload.joint_id ?? payload.id);
        const value = payload.after ?? payload.value ?? payload.position;
        const jointStates = (target.joint_states && typeof target.joint_states === "object"
          ? target.joint_states : {}) as RecordNode;
        if (jointId) target.joint_states = { ...jointStates, [jointId]: value };
      }
    }
    if (type === "edge_added") addedEdges.push(payload);
    if (type === "edge_removed") removedEdges.push(payload);
    if (type === "node_removed") delta.nodes_removed = [...(delta.nodes_removed ?? []), nodeId(payload)];
    if (type === "node_added") addedNodes.push((payload.node && typeof payload.node === "object" ? payload.node : payload) as RecordNode);
    if (type === "node_updated") {
      const target = byId.get(nodeId(payload));
      if (!target) continue;

      // A node update is the renderer-facing projection of runtime state. Keep
      // this merge generic: components, agents, resources and future node
      // types must all be able to publish the same transform/state fields.
      const nextNode = payload.node;
      if (nextNode && typeof nextNode === "object") Object.assign(target, nextNode);
      for (const key of ["world_transform", "transform_space", "transform_origin", "runtime_state", "joint_states", "visibility", "collision_enabled", "storage_mode", "visual_cues", "request_queue", "requested_room"]) {
        if (key in payload) target[key] = payload[key];
      }

      // Older movement deltas carried only agent_state. Preserve that wire
      // compatibility while normalizing it to the same transform contract.
      const agentState = payload.agent_state;
      if (agentState && typeof agentState === "object") {
        target.runtime_state = agentState;
        const position = (agentState as RecordNode).position;
        if (position && typeof position === "object") {
          const p = position as RecordNode;
          const x = Number(p.x ?? 0);
          const y = Number(p.y ?? 0);
          const z = Number(p.z ?? 0);
          target.world_transform = {
            // Runtime movement retains the historical Web basis internally:
            // x/z are floor axes and y is height.  Publish the protocol's
            // right-handed Z-up basis consistently with full snapshots.
            position: [x, -z, y],
            rotation: [0, 0, 0, 1],
            scale: [1, 1, 1],
          };
        }
      }
    }
  }
  for (const added of addedNodes) {
    const addedId = id(added.id ?? added.node_id);
    if (addedId && !byId.has(addedId)) {
      nodes.push({ ...added, id: addedId });
      byId.set(addedId, nodes[nodes.length - 1]);
    }
  }
  for (const change of stateChanges) {
    const target = byId.get(nodeId(change));
    if (target) target.states = { ...(target.states as RecordNode | undefined), [id(change.state)]: change.after };
  }
  const removedKeys = new Set(removedEdges.map(edgeKey));
  if (removedKeys.size) edges.splice(0, edges.length, ...edges.filter((edge) => !removedKeys.has(edgeKey(edge))));
  for (const edge of addedEdges) {
    if (!edges.some((existing) => edgeKey(existing) === edgeKey(edge))) edges.push({ ...edge });
  }
  const removedNodes = new Set((delta.nodes_removed ?? []).map(String));
  if (removedNodes.size) {
    nodes.splice(0, nodes.length, ...nodes.filter((node) => !removedNodes.has(id(node.id))));
    edges.splice(0, edges.length, ...edges.filter((edge) => !removedNodes.has(id(edge.source_id ?? edge.source)) && !removedNodes.has(id(edge.target_id ?? edge.target))));
  }
  if (delta.agent) {
    const worldState = (scene.world_state && typeof scene.world_state === "object" ? scene.world_state : {}) as RecordNode;
    const agents = (worldState.agents && typeof worldState.agents === "object" ? worldState.agents : {}) as RecordNode;
    scene.world_state = { ...worldState, agents: { ...agents, ...delta.agent } };
    // Agents are nodes too. Keep their renderer-facing projection in sync
    // with the runtime agent map so consumers never need a second local
    // player state. Runtime coordinates are Web X/Y/Z; protocol transforms
    // are GraphWorld right-handed Z-up [x, -z, y].
    for (const [agentId, stateValue] of Object.entries(delta.agent)) {
      const target = byId.get(agentId);
      const state = stateValue as RecordNode;
      const position = state?.position as RecordNode | undefined;
      if (!target || !position) continue;
      const x = Number(position.x ?? 0);
      const y = Number(position.y ?? 0);
      const z = Number(position.z ?? 0);
      target.runtime_state = { ...state };
      target.world_transform = {
        position: [x, -z, y],
        rotation: [0, 0, 0, 1],
        scale: [1, 1, 1],
      };
      target.transform_space = "graphworld_z_up";
      target.transform_origin = "runtime";
    }
  }
  if (Number.isFinite(Number(delta.revision))) scene.revision = delta.revision;
  if (Number.isFinite(Number(delta.time_seconds))) scene.time_seconds = delta.time_seconds;
  if (delta.coordinate_system && typeof delta.coordinate_system === "object") {
    scene.coordinate_system = { ...delta.coordinate_system };
  }
  return true;
}
