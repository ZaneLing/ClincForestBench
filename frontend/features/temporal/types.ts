export type TemporalConfidence = 'EXACT' | 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN';

export type ClinicalPresentationRow = {
  label: string;
  value: string;
  unit?: string | null;
  flag?: string | null;
};

export type ClinicalPresentationBlock = {
  title: string;
  kind: 'ROWS' | 'NARRATIVE';
  text?: string;
  rows?: ClinicalPresentationRow[];
};

export type ClinicalPresentation = {
  title: string;
  headline?: string;
  summary?: string;
  dataset?: string;
  modality_label?: string;
  sections?: ClinicalPresentationBlock[];
  blocks?: ClinicalPresentationBlock[];
  media?: Array<{
    asset: string;
    media_type: string;
    caption: string;
  }>;
};

export type TemporalEvent = {
  case_id: string;
  event_id: string;
  event_type: string;
  clinical_concept: {
    canonical_id: string;
    display: string;
    source_code?: string | null;
    source_system: string;
    modality: string;
  };
  action_id?: string | null;
  time: {
    order_time?: string | null;
    acquired_time?: string | null;
    available_time?: string | null;
    documented_time?: string | null;
    start_time?: string | null;
    end_time?: string | null;
    relative_order_min?: number | null;
    relative_acquired_min?: number | null;
    relative_available_min?: number | null;
    relative_documented_min?: number | null;
    relative_start_min?: number | null;
    relative_end_min?: number | null;
    temporal_confidence: TemporalConfidence;
    availability_semantics: string;
  };
  result: Record<string, unknown>;
  presentation?: ClinicalPresentation;
  arena_reveal_time_min?: number | null;
  provenance: {
    dataset: string;
    source_table: string;
    source_row_id: string;
    is_observed_real_result: boolean;
  };
  arena: {
    arena_eligible: boolean;
    state_changing_intervention: boolean;
    state_changing_intervention_before_result: boolean;
    leakage_risk: string;
    exclusion_reason?: string | null;
    temporal_replay_mode: string;
  };
};

export type TemporalGraphNode = {
  node_id: string;
  node_type:
    | 'ROOT'
    | 'CONTEXT'
    | 'ACTION'
    | 'RESULT'
    | 'INTERVENTION'
    | 'REFERENCE';
  label: string;
  subtitle: string;
  game_time_min: number;
  reveal_time_min: number;
  lane: string;
  event_id?: string | null;
  temporal_confidence: TemporalConfidence;
  data: Record<string, unknown>;
};

export type TemporalGraphEdge = {
  edge_id: string;
  source_node: string;
  target_node: string;
  edge_type: string;
  action_id?: string | null;
  action_time_min?: number | null;
  result_available_time_min?: number | null;
  latency_min?: number | null;
  result_status: string;
  source_event_id?: string | null;
};

export type TemporalCase = {
  case_id: string;
  case_version: string;
  task_type: string;
  source: Record<string, unknown>;
  raw_source: Record<string, unknown>;
  transformation: Record<string, unknown>;
  anchor: Record<string, unknown>;
  initial_state: Record<string, unknown>;
  timeline_events: TemporalEvent[];
  queryable_context: Array<Record<string, unknown>>;
  hidden_evidence_pool: string[];
  realized_trajectory: Array<Record<string, unknown>>;
  reference: Record<string, unknown>;
  case_quality: Record<string, unknown>;
  temporal_quality: {
    anchor_confidence?: string;
    core_event_minimum_confidence?: string;
    warnings?: string[];
    intervention_boundary_min?: number | null;
    [key: string]: unknown;
  };
  arena_config: Record<string, unknown>;
  temporal_graph: {
    schema_version: string;
    root_id: string;
    nodes: TemporalGraphNode[];
    edges: TemporalGraphEdge[];
  };
  mvp_simulations: Array<Record<string, unknown>>;
};

export type TemporalManifestEntry = {
  case_id: string;
  dataset_name: string;
  task_type: string;
  reference_label: string | string[];
  event_count: number;
  eligible_event_count: number;
  max_time_min: number;
  temporal_confidence_counts: Record<string, number>;
  path: string;
  review_path: string;
  checks: Record<string, boolean>;
};

export type TemporalManifest = {
  schema_version: string;
  case_version: string;
  case_count: number;
  dataset_case_counts: Record<string, number>;
  all_checks_pass: boolean;
  status: 'READY' | 'NOT_BUILT';
  build_command?: string;
  privacy: string;
  cases: TemporalManifestEntry[];
};

export type TemporalCaseDetail = {
  manifest_entry: TemporalManifestEntry;
  case: TemporalCase;
  trajectory_evaluation?: {
    status: 'READY' | 'NO_COMPLETED_TRAJECTORIES';
    completed_trajectory_count: number;
    aggregate: Record<string, number | null>;
    metric_definitions: Array<{
      key: string;
      label: string;
      direction: string;
      description: string;
    }>;
    interpretation_limits: string[];
  };
};

export type TemporalArenaCase = {
  case_id: string;
  dataset_name: string;
  task_type: string;
  event_count: number;
  eligible_event_count: number;
  max_time_min: number;
};

export type TemporalArenaIndex = {
  case_count: number;
  dataset_case_counts: Record<string, number>;
  cases: TemporalArenaCase[];
};

export type TemporalArenaAction = {
  action_id: string;
  display: string;
  modality: string;
  modality_label: string;
  interaction_type: 'QUESTION' | 'EXAM' | 'ORDER' | 'REVIEW';
  interaction_label: string;
};

export type TemporalPendingAction = {
  action_id: string;
  display?: string;
  modality?: string;
  status: 'PENDING' | 'AVAILABLE' | 'UNOBSERVED';
  ordered_game_time: number;
  expected_available_game_time: number | null;
  source_event_id: string | null;
  temporal_replay_mode?: string;
  temporal_confidence?: TemporalConfidence;
};

export type TemporalBelief = {
  checkpoint: number;
  game_time_min: number;
  diagnoses: string[];
  revealed_event_ids: string[];
  pending_action_ids: string[];
  submitted_at: string;
  is_final: boolean;
};

export type TemporalArenaState = {
  session_id: string;
  case_id: string;
  dataset_name: string;
  task_type: string;
  status: 'ACTIVE' | 'COMPLETED';
  initial_state: Record<string, unknown>;
  initial_presentation: ClinicalPresentation;
  current_time_min: number;
  checkpoint: number;
  belief_required: boolean;
  belief_history: TemporalBelief[];
  pending_actions: TemporalPendingAction[];
  revealed_events: TemporalEvent[];
  newly_revealed_event_ids: string[];
  action_count: number;
  max_actions: number;
  available_actions: TemporalArenaAction[];
  diagnosis_catalog: string[];
};

export type TemporalArenaReview = {
  session: Record<string, unknown> & {
    case_id: string;
    initial_state: Record<string, unknown>;
    belief_history: TemporalBelief[];
    event_log: Array<Record<string, unknown>>;
    revealed_event_ids: string[];
  };
  comparison: {
    predicted_diagnosis: string;
    ground_truth_diagnosis: string;
    is_exact_match: boolean;
    actions_used: number;
    elapsed_game_time_min: number;
  };
  ground_truth_tree: TemporalCase['temporal_graph'];
  mvp_strategy_paths: Array<Record<string, unknown>>;
  community: {
    completed_session_count: number;
    top1_diagnoses: Array<{
      diagnosis: string;
      count: number;
      rate: number;
    }>;
    mean_actions: number;
  };
};
