'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  Braces,
  Database,
  FileClock,
  GitBranch,
  Image as ImageIcon,
  ImageOff,
  ShieldCheck,
  Stethoscope,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { JsonDocument } from '@/features/forest/research-dashboard';
import { api } from '@/lib/api';
import { TemporalCanvas } from './temporal-dashboard';
import type {
  TemporalCaseDetail,
  TemporalEvent,
  TemporalManifest,
} from './types';

export function TemporalCaseInspector({
  embedded = false,
  selectedCaseId,
}: {
  embedded?: boolean;
  selectedCaseId?: string;
}) {
  const [manifest, setManifest] = useState<TemporalManifest | null>(null);
  const [detail, setDetail] = useState<TemporalCaseDetail | null>(null);
  const [dataset, setDataset] = useState('ALL');
  const [caseId, setCaseId] = useState('');
  const [selectedNodeId, setSelectedNodeId] = useState('');
  const [treeExpanded, setTreeExpanded] = useState(true);
  const [error, setError] = useState('');
  const [liveMessage, setLiveMessage] = useState('');

  async function loadCase(value: string) {
    if (!value) return;
    try {
      const result = await api<TemporalCaseDetail>(
        `/research/temporal/cases/${value}`,
        { headers: { 'X-Research-Key': 'local-research-only' } },
      );
      setError('');
      setDetail(result);
      setCaseId(value);
      setSelectedNodeId(
        result.case.temporal_graph.nodes.find(
          (node) => node.node_type === 'CONTEXT',
        )?.node_id ?? result.case.temporal_graph.root_id,
      );
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Case 读取失败');
    }
  }

  useEffect(() => {
    if (embedded) return;
    void api<TemporalManifest>('/research/temporal/cases', {
      headers: { 'X-Research-Key': 'local-research-only' },
    }).then((result) => {
      setManifest(result);
      const requested = new URLSearchParams(window.location.search).get('case');
      const first = result.cases.find((item) => item.case_id === requested) ?? result.cases[0];
      if (first) void loadCase(first.case_id);
    }).catch((reason: Error) => setError(reason.message));
  }, [embedded]);

  useEffect(() => {
    if (!selectedCaseId) return;
    let active = true;
    void api<TemporalCaseDetail>(
      `/research/temporal/cases/${selectedCaseId}`,
      { headers: { 'X-Research-Key': 'local-research-only' } },
    )
      .then((result) => {
        if (!active) return;
        setDetail(result);
        setCaseId(selectedCaseId);
        setSelectedNodeId(
          result.case.temporal_graph.nodes.find(
            (node) => node.node_type === 'CONTEXT',
          )?.node_id ?? result.case.temporal_graph.root_id,
        );
        setError('');
      })
      .catch((reason: Error) => {
        if (active) setError(reason.message);
      });
    return () => {
      active = false;
    };
  }, [selectedCaseId]);

  const entries = useMemo(
    () => (manifest?.cases ?? []).filter((item) => dataset === 'ALL' || item.dataset_name === dataset),
    [dataset, manifest],
  );
  const caseData = detail?.case;
  const maxTime = Math.max(...(caseData?.temporal_graph.nodes.map((node) => node.reveal_time_min) ?? [0]));
  const selectedNode = caseData?.temporal_graph.nodes.find((node) => node.node_id === selectedNodeId);
  const selectedEvent = selectedNode?.event_id
    ? caseData?.timeline_events.find((event) => event.event_id === selectedNode.event_id)
    : undefined;
  const referenceNode = caseData?.temporal_graph.nodes.find(
    (node) => node.node_type === 'REFERENCE',
  );
  const imagingNodes = caseData?.temporal_graph.nodes.filter(
    (node) => node.node_type === 'RESULT' && node.lane === 'IMAGING',
  ) ?? [];
  const RootElement = embedded ? 'div' : 'main';

  return (
    <RootElement className={`temporal-audit-page ${embedded ? 'is-embedded' : ''}`}>
      {!embedded && (
        <header className="temporal-audit-header">
          <Link href="/research"><ArrowLeft />统一 Case 查看</Link>
          <div><small>ClincForestBench · Temporal conversion audit</small><h1>原始数据 → 规范事件 → 动态树</h1></div>
          <Badge><ShieldCheck />{manifest?.case_count ?? 0} CASES</Badge>
          <label><span>数据源</span><select onChange={(event) => { const value = event.target.value; setDataset(value); const first = manifest?.cases.find((item) => value === 'ALL' || item.dataset_name === value); if (first) void loadCase(first.case_id); }} value={dataset}><option value="ALL">全部数据源</option>{Object.entries(manifest?.dataset_case_counts ?? {}).map(([name, count]) => <option key={name} value={name}>{name} · {count}</option>)}</select></label>
          <label className="temporal-audit-case"><span>Case</span><select onChange={(event) => void loadCase(event.target.value)} value={caseId}>{entries.map((item) => <option key={item.case_id} value={item.case_id}>{item.case_id} · {item.event_count} events</option>)}</select></label>
        </header>
      )}

      {caseData ? (
        <section className="temporal-audit-grid">
          <article>
            <AuditHeading icon={<Database />} step="1 · RAW" title="原始病例与实际取用字段" />
            <JsonDocument filename={`${caseId}.raw.json`} onNotice={setLiveMessage} value={caseData.raw_source} />
          </article>
          <article>
            <AuditHeading icon={<Braces />} step="2 · NORMALIZE" title="规范 Case 与转换说明" />
            <div className="temporal-conversion-summary">
              <span><FileClock />T0: {formatAuditValue(caseData.anchor.anchor_type)}</span>
              <span><GitBranch />{caseData.timeline_events.length} events</span>
              <span><ShieldCheck />0 synthetic results</span>
            </div>
            <JsonDocument defaultView="table" filename={`${caseId}.conversion.json`} onNotice={setLiveMessage} value={{ transformation: caseData.transformation, anchor: caseData.anchor, initial_state: caseData.initial_state, timeline_events: caseData.timeline_events, hidden_evidence_pool: caseData.hidden_evidence_pool, temporal_quality: caseData.temporal_quality, arena_config: caseData.arena_config }} />
          </article>
          <article className="temporal-audit-tree-panel">
            <AuditHeading icon={<GitBranch />} step="3 · GRAPH" title="完整时间树与节点内容" />
            {detail.trajectory_evaluation && <CaseEvaluationSummary evaluation={detail.trajectory_evaluation} />}
            <div className="temporal-tree-disclosures">
              <section className="temporal-tree-disclosure is-canvas" data-open={treeExpanded}>
                <button
                  aria-expanded={treeExpanded}
                  className="temporal-tree-disclosure-toggle"
                  onClick={() => setTreeExpanded((value) => !value)}
                  type="button"
                >
                  <span>完整时间树</span><small>{caseData.temporal_graph.nodes.length} nodes</small>
                </button>
                {treeExpanded && <div className="temporal-audit-tree">
                  <TemporalCanvas caseData={caseData} currentTime={maxTime} onInspect={setSelectedNodeId} selectedNodeId={selectedNodeId} />
                  {imagingNodes.length > 0 && (
                    <label className="temporal-audit-imaging-jump">
                      <ImageIcon />
                      <select
                        aria-label="选择影像报告节点"
                        onChange={(event) => {
                          if (event.target.value) setSelectedNodeId(event.target.value);
                        }}
                        value={imagingNodes.some((node) => node.node_id === selectedNodeId) ? selectedNodeId : ''}
                      >
                        <option value="">影像报告 · {imagingNodes.length} 项</option>
                        {imagingNodes.map((node) => (
                          <option key={node.node_id} value={node.node_id}>{node.label}</option>
                        ))}
                      </select>
                    </label>
                  )}
                  {referenceNode && (
                    <button
                      className="temporal-audit-reference-jump"
                      onClick={() => setSelectedNodeId(referenceNode.node_id)}
                      type="button"
                    >
                      <span><Stethoscope /></span>
                      <small>最终参考诊断 · 点击查看</small>
                      <b>{referenceNode.label}</b>
                    </button>
                  )}
                </div>}
              </section>
              <details className="temporal-tree-disclosure is-node" key={selectedNodeId} open>
                <summary><span>节点内容</span><small>{selectedNode?.label ?? '点击树节点查看'}</small></summary>
                <NodeInspector
                  event={selectedEvent}
                  initialState={caseData.initial_state}
                  node={selectedNode}
                />
              </details>
            </div>
          </article>
        </section>
      ) : <section className="audit-empty"><FileClock /><b>{error || '正在加载本地病例'}</b></section>}
      <span aria-live="polite" className="sr-only">{liveMessage}</span>
    </RootElement>
  );
}

function CaseEvaluationSummary({ evaluation }: { evaluation: NonNullable<TemporalCaseDetail['trajectory_evaluation']> }) {
  const metric = (key: string) => {
    const value = evaluation.aggregate[key];
    if (typeof value !== 'number') return '待生成';
    if (key.includes('count')) return value.toFixed(2);
    if (key.includes('reciprocal_rank')) return value.toFixed(3);
    return `${Math.round(value * 100)}%`;
  };
  return <div className="temporal-audit-evaluation">
    <div className="temporal-audit-metric-bar">
      <span><small>完成轨迹</small><b>{evaluation.completed_trajectory_count}</b></span>
      <span><small>Top-1</small><b>{metric('exact_top1_accuracy')}</b></span>
      <span><small>GT 重合</small><b>{metric('mean_recorded_action_overlap_rate')}</b></span>
      <span><small>错误早停</small><b>{metric('premature_finalization_proxy_rate')}</b></span>
    </div>
    <details><summary>本 Case 的全部指标与口径</summary><div>{evaluation.metric_definitions.map((item) => <p key={item.key}><span>{item.label}</span><b>{metric(item.key)}</b><small>{item.description}</small></p>)}{evaluation.interpretation_limits.map((item) => <em key={item}>{item}</em>)}</div></details>
  </div>;
}

function AuditHeading({ icon, step, title }: { icon: React.ReactNode; step: string; title: string }) {
  return <header className="temporal-audit-panel-heading"><span>{icon}</span><div><small>{step}</small><b>{title}</b></div></header>;
}

function NodeInspector({ node, event, initialState }: { node?: { node_type: string; label: string; subtitle: string; reveal_time_min: number; temporal_confidence: string; lane: string; data: Record<string, unknown> }; event?: TemporalEvent; initialState: Record<string, unknown> }) {
  const result = event?.result ?? (node?.node_type === 'CONTEXT' ? initialState : node?.data) ?? {};
  const imaging = event?.clinical_concept.modality === 'IMAGING' || node?.lane === 'IMAGING';
  const diagnosis = node?.node_type === 'REFERENCE';
  return (
    <aside className={`temporal-audit-node-inspector ${imaging ? 'is-imaging' : ''} ${diagnosis ? 'is-diagnosis' : ''}`}>
      <header>
        {imaging ? <ImageIcon /> : diagnosis ? <Stethoscope /> : <FileClock />}
        <div>
          <small>{node?.node_type ?? 'NODE'} · {node?.temporal_confidence ?? '—'}</small>
          <b>{node?.label ?? '点击树节点查看'}</b>
          <span>{node?.subtitle}</span>
        </div>
      </header>
      {imaging ? (
        <ImagingNodeContent result={result} />
      ) : diagnosis ? (
        <DiagnosisNodeContent diagnosis={node.label} result={result} />
      ) : (
        <pre>{JSON.stringify(result, null, 2)}</pre>
      )}
    </aside>
  );
}

function ImagingNodeContent({ result }: { result: Record<string, unknown> }) {
  const report = firstText(
    result.impression,
    result.report_text,
    result.narrative_text,
    result.findings,
    result.text,
  );
  return (
    <div className="temporal-imaging-content">
      <section className="temporal-image-unavailable">
        <ImageOff />
        <span>
          <b>当前源数据没有影像像素文件</b>
          <small>本地 Case 仅含报告文本，没有可渲染的 DICOM、JPG 或 PNG；系统不会用示意图冒充患者影像。</small>
        </span>
      </section>
      <section className="temporal-imaging-report">
        <small>RADIOLOGY IMPRESSION / SOURCE NARRATIVE</small>
        <p>{report ?? '该节点没有可用的报告正文。'}</p>
      </section>
      <details>
        <summary>查看原始影像字段</summary>
        <pre>{JSON.stringify(result, null, 2)}</pre>
      </details>
    </div>
  );
}

function DiagnosisNodeContent({ diagnosis, result }: { diagnosis: string; result: Record<string, unknown> }) {
  const codes = asRecord(result.diagnosis_codes);
  const icd10 = firstText(codes.icd10);
  const icd9 = firstText(codes.icd9);
  const strength = firstText(result.reference_strength) ?? 'SOURCE REFERENCE';
  const supporting = Array.isArray(result.discharge_diagnoses)
    ? result.discharge_diagnoses.map(String)
    : Array.isArray(result.recorded_diagnoses)
      ? result.recorded_diagnoses.map(String)
      : Array.isArray(result.mesh_diagnosis_proxy)
        ? result.mesh_diagnosis_proxy.map(String)
        : [];
  return (
    <div className="temporal-diagnosis-content">
      <section>
        <small>RETROSPECTIVE REFERENCE DIAGNOSIS</small>
        <h3>{diagnosis}</h3>
        <p>{strength.replaceAll('_', ' ')}</p>
        {(icd10 || icd9) && (
          <div>
            {icd10 && <span>ICD-10 <b>{icd10}</b></span>}
            {icd9 && <span>ICD-9 <b>{icd9}</b></span>}
          </div>
        )}
      </section>
      {supporting.length > 0 && (
        <details>
          <summary>来源记录中的相关诊断 · {supporting.length}</summary>
          <ol>{supporting.map((value, index) => <li key={`${value}-${index}`}>{value}</li>)}</ol>
        </details>
      )}
      <details>
        <summary>查看完整诊断字段</summary>
        <pre>{JSON.stringify(result, null, 2)}</pre>
      </details>
    </div>
  );
}

function firstText(...values: unknown[]) {
  return values.find((value): value is string => typeof value === 'string' && value.trim().length > 0);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function formatAuditValue(value: unknown) {
  if (value === null || value === undefined) return 'source-defined';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value);
}
