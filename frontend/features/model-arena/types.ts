import type {
  BeliefSnapshotPayload,
  Condition,
  ObservationState,
  SessionReview,
} from '@/features/arena/types';

export type OpenRouterStatus = {
  provider: 'OpenRouter';
  configured: boolean;
  base_url: string;
  max_questions: 30;
};

export type OpenRouterProvider = {
  id: string;
  name: string;
  model_count: number;
};

export type OpenRouterModel = {
  id: string;
  name: string;
  provider: string;
  provider_label: string;
  context_length: number | null;
  pricing: Record<string, string>;
};

export type ModelRun = {
  run_id: string;
  session_id: string;
  model_id: string;
  provider: string;
  case_id: string;
  dataset_name: string;
  status: 'ACTIVE' | 'COMPLETED';
  max_questions: number;
  forced_final: boolean;
  last_error: string | null;
  created_at: string;
  completed_at: string | null;
};

export type ModelRunSummary = ModelRun & {
  interaction_count: number;
  question_count: number;
};

export type ModelDecision = {
  diagnoses: string[];
  next_action_id: string | null;
  final: boolean;
  final_condition_id: string | null;
  rationale?: string;
};

export type ModelInteraction = {
  interaction_id: string;
  run_id: string;
  step: number;
  request_payload: Record<string, unknown>;
  response_payload: Record<string, unknown> | null;
  assistant_content: string | null;
  parsed_decision: ModelDecision | null;
  application_result: Record<string, unknown> | null;
  error: string | null;
  latency_ms: number | null;
  created_at: string;
};

export type ModelTrajectoryStep = {
  step: number;
  state_hash: string;
  evidence_id: string;
  question: string;
  answer: string;
  status: string;
};

export type ModelRunArtifact = {
  schema_version: 'clincforestbench.model-arena-run.v1';
  model_run: ModelRun;
  arena: Record<string, unknown>;
  interactions: ModelInteraction[];
};

export type ModelRunDetail = {
  run: ModelRun;
  session: Record<string, unknown>;
  state: ObservationState;
  conditions: Condition[];
  trajectory: ModelTrajectoryStep[];
  belief_history: BeliefSnapshotPayload[];
  interactions: ModelInteraction[];
  review?: SessionReview;
  artifact?: ModelRunArtifact;
};
