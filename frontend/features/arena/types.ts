export type EvidenceResponse = {
  evidence_id: string;
  status: 'PRESENT' | 'ABSENT' | 'VALUE' | 'DEFAULT' | 'NOT_APPLICABLE';
  data_type: 'binary' | 'categorical' | 'multi_choice';
  value: unknown;
  values: unknown[];
};

export type ObservationState = {
  case_id: string;
  dataset_name: 'DDXPlus' | 'Synthea' | 'MedAgentBench';
  case_type:
    | 'DIAGNOSTIC_QUESTIONING'
    | 'DIAGNOSTIC_EVIDENCE_ACQUISITION'
    | 'WORKFLOW_FOREST';
  generation_mode: string;
  initial_context: Record<string, unknown>;
  demographics: { age: number; sex: string };
  initial_evidence_id: string;
  initial_evidence_question: string;
  initial_evidence_answer: string;
  revealed_evidences: EvidenceResponse[];
  question_count: number;
  created_resource_ids: string[];
  state_hash: string;
};

export type AvailableEvidence = {
  action_type: 'ASK_EVIDENCE';
  evidence_id: string;
  question_en: string;
  dependency_met: boolean;
  semantic_role: string;
  clinical_domain: string;
  data_type: 'binary' | 'categorical' | 'multi_choice';
  exposure_tier: number;
  suggested_by: string[];
  parent_evidence_id: string | null;
  parent_question_en: string | null;
  action_kind: string;
  resource_type: string | null;
  mutates_state: boolean;
};

export type Condition = {
  condition_id: string;
  name: string;
  kind?: string;
};
export type CaseSummary = {
  case_id: string;
  dataset_name: 'DDXPlus' | 'Synthea' | 'MedAgentBench';
  case_type: string;
  generation_mode: string;
  action_count: number;
  outcome_kind: string;
  terminology: 'diagnosis' | 'workflow outcome';
  runtime_status: string;
};
export type Diagnosis = {
  condition_id: string;
  rank: number;
  probability: number;
};

export type Graph = {
  case_id: string;
  session_count: number;
  completed_session_count: number;
  participant_count: number;
  physician_count: number;
  physician_session_count: number;
  model_count?: number;
  model_session_count?: number;
  nodes: Array<{
    state_hash: string;
    support: number;
    revealed_evidence_ids: string[];
  }>;
  edges: Array<{
    source_hash: string;
    target_hash: string;
    action_evidence_id: string;
    support: number;
    probability: number;
    question?: string;
  }>;
};

export type SessionReview = {
  player_type?: 'PHYSICIAN' | 'MODEL' | 'RESEARCHER';
  session_id: string;
  case_id: string;
  dataset_name: string;
  case_type: string;
  generation_mode: string;
  terminology: 'diagnosis' | 'workflow outcome';
  fidelity_note: string;
  comparison: {
    is_correct: boolean;
    predicted_diagnosis: string;
    ground_truth_diagnosis: string;
    predicted_label: string;
    ground_truth_label: string;
    ground_truth_rank_in_submission: number | null;
    questions_asked: number;
    positive_findings_discovered: number;
    positive_findings_missed: number;
  };
  trajectory: Array<{
    step: number;
    state_hash: string;
    evidence_id: string;
    question: string;
    answer: string;
    status: string;
    belief: { diagnoses: Diagnosis[]; overall_confidence: number } | null;
  }>;
  missed_positive_findings: Array<{
    evidence_id: string;
    question: string;
    answer: string;
  }>;
  oracle_differential: Array<{ condition: string; probability: number }>;
  case_graph: Graph;
  ground_truth_tree: import('@/features/forest/case-tree-types').ProcessedCaseTree;
  community_final_diagnoses: Array<{
    condition: string;
    label?: string;
    is_ground_truth: boolean;
    selection_count: number;
    selection_rate: number;
    top1_rate: number;
    mean_rank_when_selected: number;
    mean_rank_weight: number;
  }>;
};

export type BeliefSnapshotPayload = {
  belief_id: string;
  session_id: string;
  step: number;
  state_hash: string;
  belief: { diagnoses: Diagnosis[]; overall_confidence: number };
  is_final: boolean;
  timestamp: string;
  submission_type?: 'STAGE_DIAGNOSIS' | 'FINAL_DIAGNOSIS';
};

export type SessionArtifact = {
  schema_version: 'clincforestbench.arena-run.v1';
  export_type: 'completed_arena_run';
  generated_at: string | null;
  dataset_name: string;
  case_type: string;
  generation_mode: string;
  fidelity_note: string;
  capture_semantics: {
    diagnosis_input: string;
    probability: string;
    overall_confidence: string;
  };
  session: Record<string, unknown> & { session_id: string; case_id: string };
  patient_path: SessionReview['trajectory'];
  belief_history: BeliefSnapshotPayload[];
  event_log: Array<Record<string, unknown>>;
  observation_states: Array<Record<string, unknown>>;
  outcome: SessionReview['comparison'];
  reference: {
    oracle_differential: SessionReview['oracle_differential'];
    missed_positive_findings: SessionReview['missed_positive_findings'];
    outcome_labels: Record<string, string>;
  };
};
