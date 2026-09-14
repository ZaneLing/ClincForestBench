export type CaseTreeManifestEntry = {
  case_id: string;
  pathology: string;
  disease_category_key: string;
  disease_category: string;
  dataset_name: string;
  case_type: string;
  generation_mode: string;
  raw_case_path: string;
  tree_path: string;
  raw_sha256: string;
  tree_sha256: string;
  node_count: number;
  source_evidence_count: number;
  all_checks_pass: boolean;
  dataset_case_counts: Record<string, number>;
  source_manifests?: Array<Record<string, unknown>>;
};

export type CaseTreeManifest = {
  manifest_name: string;
  manifest_version: string;
  tree_schema_version: string;
  taxonomy_version: string;
  case_count: number;
  pathology_count: number;
  taxonomy_condition_count: number;
  category_count: number;
  category_case_counts: Record<string, number>;
  dataset_case_counts: Record<string, number>;
  source_manifests: Array<{
    dataset_name: string;
    manifest_version: string;
    case_count: number;
    path: string;
  }>;
  all_checks_pass: boolean;
  cases: CaseTreeManifestEntry[];
};

export type CaseTreeNode = {
  node_id: string;
  node_type:
    | 'CASE'
    | 'STAGE'
    | 'CONTEXT'
    | 'ACTION'
    | 'OBSERVATION'
    | 'DIAGNOSIS';
  action_type?: string;
  label: string;
  order: number;
  data: Record<string, unknown>;
};

export type CaseTreeEdge = {
  source: string;
  target: string;
  edge_type: string;
  order: number;
};

export type ProcessedCaseTree = {
  schema_version: string;
  case_id: string;
  case_hash: string;
  classification: {
    pathology: string;
    disease_category_key: string;
    disease_category: string;
    severity: number;
    taxonomy_version: string;
    taxonomy_source: string;
  };
  semantics: {
    tree_kind: string;
    is_observed_clinician_chronology: boolean;
    source_asserted_evidence_only: boolean;
    description: string;
    supported_action_types: string[];
    unsupported_source_modalities: string[];
  };
  source: {
    raw_case_path: string;
    raw_sha256: string;
    field_lineage: Record<string, string[]>;
  };
  tree: {
    root_id: string;
    nodes: CaseTreeNode[];
    edges: CaseTreeEdge[];
  };
  audit: {
    raw_evidence_token_count: number;
    source_asserted_evidence_count: number;
    action_node_count: number;
    observation_node_count: number;
    differential_node_count: number;
    total_node_count: number;
    orphan_hierarchy_count: number;
    checks: Record<string, boolean>;
  };
};

export type RawCaseProjection = {
  provenance: {
    case_id: string;
    projection: string;
    raw_row_sha256?: string;
    source_file: string;
    source_row_number_one_based?: number;
    source_split?: string;
    source_encounter_id?: string;
    source_task_id?: string;
    generation_mode?: string;
    runtime_status?: string;
  };
  raw_row: Record<string, unknown>;
};

export type CaseTreeAudit = {
  manifest_entry: CaseTreeManifestEntry;
  raw_case: RawCaseProjection;
  processed_tree: ProcessedCaseTree;
};
