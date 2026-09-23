export type ControlMode = "agent" | "human" | "npc_only" | "hybrid";
export type VisibilityMode = "full" | "room" | "fog_of_war";
export type RunStatus = "pending" | "running" | "waiting_for_human" | "completed" | "failed" | "canceled";

export interface UserRead {
  id: string;
  username: string;
  display_name: string;
  role: "admin" | "user" | string;
  is_active: boolean;
  created_at?: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserRead;
}

export interface SceneRead {
  id: string;
  name: string;
  domain: string;
  description: string;
  created_at?: string;
}

export interface SceneVersionRead {
  id: string;
  scene_id: string;
  version: number;
  graph_summary: Record<string, unknown>;
  created_at?: string;
}

export interface GraphNode {
  id: string;
  node_type: string;
  semantic_type: string;
  properties: Record<string, unknown>;
}

export interface GraphEdge {
  source_id: string;
  target_id: string;
  relation: string;
  properties: Record<string, unknown>;
}

export interface SceneGraphResponse {
  scene_version_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  source_json: Record<string, unknown>;
}

export interface SceneLayoutValidation {
  valid: boolean;
  issues: string[];
}

export interface CandidateAction {
  action_id: string;
  action_type: string;
  actor_id: string;
  target_id: string;
  object_id: string;
  reason: string;
  legal: boolean;
  preview: string;
  payload: Record<string, unknown>;
  action_contract: {
    category?: string;
    parameters?: string[];
    description?: string;
    mutates_edges?: boolean;
    mutates_states?: boolean;
    effect_summary?: string[];
  };
}

export interface InteractionHit {
  node_id: string;
  surface_uv?: [number, number];
  volume_uv?: [number, number, number];
  point_cm?: [number, number, number];
  normal?: [number, number, number];
  ray_origin?: [number, number, number];
  ray_direction?: [number, number, number];
  distance_m?: number;
}

export interface FirstPersonCamera {
  contract_version: number;
  agent_id: string;
  room_id: string;
  eye_height_m: number;
  fov_deg: number;
  near_m: number;
  far_m: number;
  forward: [number, number, number];
  up: [number, number, number];
  viewport_uv: [number, number];
  origin: [number, number, number];
  interaction_ray: {
    screen_uv: [number, number];
    origin: [number, number, number];
    direction: [number, number, number];
    space: string;
  };
}

export interface Observation {
  actor_id: string;
  step_index: number;
  visibility_mode: VisibilityMode | string;
  visible_rooms: string[];
  visible_nodes: Record<string, unknown>[];
  visible_edges: Record<string, unknown>[];
  memory_nodes: Record<string, unknown>[];
  unknown_rooms: string[];
  confidence_by_room: Record<string, number>;
  observation_status_by_node: Record<string, string>;
  last_seen_step_by_node: Record<string, number>;
  observation_status_by_room: Record<string, string>;
  candidate_actions: CandidateAction[];
  camera: FirstPersonCamera;
}

export interface ActionResult {
  ok: boolean;
  message: string;
  failures: string[];
  payload: Record<string, unknown>;
}

export interface RunRead {
  id: string;
  owner_user_id?: string | null;
  owner_username?: string | null;
  scene_version_id: string;
  control_mode: ControlMode;
  visibility_mode: VisibilityMode;
  status: RunStatus;
  current_step: number;
  config: Record<string, unknown>;
  summary: Record<string, unknown>;
  artifact_uri: string;
  error_message: string;
  started_at?: string;
  finished_at?: string;
  created_at?: string;
}

export interface RunCreate {
  scene_version_id: string;
  control_mode: ControlMode;
  visibility_mode: VisibilityMode;
  task_id: string;
  agent_model?: string | null;
  max_steps: number;
  seed?: number | null;
  config?: Record<string, unknown>;
}

export interface RunCurrentResponse {
  run: RunRead;
  observation: Observation | null;
  candidate_actions: CandidateAction[];
  latest_action_result: ActionResult | null;
  metrics: Record<string, unknown>;
}

export interface ReplayStepRead {
  run_id: string;
  step_index: number;
  actor_type: string;
  actor_id: string;
  observation: Observation | Record<string, unknown>;
  candidate_actions: CandidateAction[];
  selected_action: Record<string, unknown>;
  action_result: ActionResult | Record<string, unknown>;
  world_state_before: Record<string, unknown>;
  world_state_after: Record<string, unknown>;
  events: Record<string, unknown>[];
  metrics: Record<string, unknown>;
  created_at?: string;
}

export interface ReplayResponse {
  run_id: string;
  steps: ReplayStepRead[];
  summary: Record<string, unknown>;
}

export interface MetricPoint {
  step_index: number | null;
  metric_name: string;
  metric_value: number | null;
  payload: Record<string, unknown>;
}

export interface RunMetricsResponse {
  run_id: string;
  metrics: MetricPoint[];
  summary: Record<string, unknown>;
}
