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
  candidate_actions: CandidateAction[];
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
