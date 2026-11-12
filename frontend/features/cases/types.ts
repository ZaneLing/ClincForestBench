export type CaseRecord = {
  source_id: string;
  source_label?: string;
  result: unknown;
  text?: string;
};
export type CaseAction = {
  id: string;
  kind: string;
  category: string;
  label: { en: string; 'zh-CN': string };
  availability?: string;
  record_count?: number;
  records: CaseRecord[];
};
export type CaseDetail = {
  case_id: string;
  dataset: string;
  identity?: { case_type?: string; generation_mode?: string };
  initial_information?: {
    demographics?: { age?: unknown; sex?: string };
    presentation?: unknown;
  };
  counts?: {
    inquiry?: { recorded: number; total: number };
    operation?: { recorded: number; total: number };
  };
  actions?: CaseAction[];
  model_evidence?: {
    evidence_id: string;
    question: string;
    answer: unknown;
    status: string;
  }[];
  reference?: {
    oracle?: { pathology?: string; display_name?: string; severity?: unknown };
    quality?: Record<string, unknown>;
  };
  treatments?: unknown[];
  media?: unknown[];
  source?: unknown;
};
export type CaseRow = {
  case_id: string;
  dataset: string;
  demographics?: { age?: unknown; sex?: string };
  inquiry_count: number;
  operation_count: number;
  model_evidence_count: number;
  reference_quality?: { reference_strength?: unknown };
  case_type?: string;
  initial_information?: CaseDetail['initial_information'];
  counts?: CaseDetail['counts'];
  reference?: CaseDetail['reference'];
};
export type CaseIndex = {
  case_count: number;
  cases: CaseRow[];
  datasets: Record<string, number>;
};
export const RESEARCH_HEADERS = { 'X-Research-Key': 'local-research-only' };

export function referenceStrength(row: CaseRow) {
  const value =
    row.reference_quality?.reference_strength ??
    row.reference?.quality?.reference_strength;
  return typeof value === 'string' && value ? value : 'UNSPECIFIED';
}
