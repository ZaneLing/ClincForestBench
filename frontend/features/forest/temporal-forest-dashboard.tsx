'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Activity, ArrowLeft, Clock3, GitBranch, Stethoscope, Trees, UsersRound } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';
import type { TemporalCase } from '@/features/temporal/types';

type CaseRow = { case_id: string; dataset_name: string; task_type: string; event_count: number; eligible_event_count: number; completed_session_count: number; participant_count: number };
type Distribution = { diagnosis: string; selection_count: number; selection_rate: number; top1_rate: number; mean_rank: number };
type TrajectoryRow = { session_id: string; run_id: string | null; participant_type: 'MODEL' | 'DOCTOR'; participant_label: string; final_prediction: string; exact_top1: boolean; reference_ever_considered: boolean; last_reference_rank: number | null; actions_used: number; action_budget: number; recorded_action_overlap_rate: number; source_order_alignment: number; source_evidence_reveal_coverage: number; pending_at_final: number; premature_finalization_proxy: boolean };
type TrajectoryEvaluation = {
  status: 'READY' | 'NO_COMPLETED_TRAJECTORIES';
  completed_trajectory_count: number;
  aggregate: Record<string, number | null>;
  trajectories: TrajectoryRow[];
  metric_definitions: Array<{ key: string; label: string; direction: string; description: string }>;
  interpretation_limits: string[];
};
type TemporalForestDetail = {
  case_id: string;
  dataset_name: string;
  task_type: string;
  summary: { completed_session_count: number; participant_count: number; mean_actions: number; mean_elapsed_time_min: number };
  reference: { diagnosis: string; strength?: string; is_absolute_ground_truth: boolean };
  stages: Array<{ checkpoint: number; submission_count: number; diagnoses: Distribution[] }>;
  final_diagnoses: Distribution[];
  actions: Array<{ action_id: string; selection_count: number; selection_rate: number }>;
  ground_truth_tree: TemporalCase['temporal_graph'];
  temporal_quality: Record<string, unknown>;
  trajectory_evaluation: TrajectoryEvaluation;
};

export function TemporalForestDashboard() {
  const [cases, setCases] = useState<CaseRow[]>([]);
  const [dataset, setDataset] = useState('ALL');
  const [caseId, setCaseId] = useState('');
  const [detail, setDetail] = useState<TemporalForestDetail | null>(null);
  const [stage, setStage] = useState<number | 'FINAL'>('FINAL');
  const [notice, setNotice] = useState('正在读取 Temporal Forest…');

  async function loadCase(value: string) {
    if (!value) return;
    try {
      const next = await api<TemporalForestDetail>(`/research/temporal/forest/cases/${value}`, { headers: { 'X-Research-Key': 'local-research-only' } });
      setCaseId(value);
      setDetail(next);
      setStage(next.stages.at(-1)?.checkpoint ?? 'FINAL');
      setNotice('');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Temporal Forest 加载失败');
    }
  }

  useEffect(() => {
    void api<{ cases: CaseRow[] }>('/research/temporal/forest/cases', { headers: { 'X-Research-Key': 'local-research-only' } })
      .then((result) => {
        setCases(result.cases);
        const requested = new URLSearchParams(window.location.search).get('case');
        const first = result.cases.find((item) => item.case_id === requested) ?? result.cases[0];
        if (first) void loadCase(first.case_id);
      })
      .catch((error: Error) => setNotice(error.message));
  }, []);

  const datasets = useMemo(() => ['ALL', ...new Set(cases.map((item) => item.dataset_name))], [cases]);
  const visible = cases.filter((item) => dataset === 'ALL' || item.dataset_name === dataset);
  const distribution = stage === 'FINAL' ? detail?.final_diagnoses ?? [] : detail?.stages.find((item) => item.checkpoint === stage)?.diagnoses ?? [];

  return <main className="temporal-forest-page">
    <header><div><span><Trees /></span><div><small>ClincForestBench · Temporal population analytics</small><h1>时间决策森林</h1></div></div><Badge><Clock3 />40 TEMPORAL CASES</Badge><Link href="/forest"><ArrowLeft />普通病例森林</Link></header>
    <section className="temporal-forest-toolbar">
      <label><span>Dataset</span><select onChange={(event) => { const value = event.target.value; setDataset(value); const first = cases.find((item) => value === 'ALL' || item.dataset_name === value); if (first) void loadCase(first.case_id); }} value={dataset}>{datasets.map((name) => <option key={name} value={name}>{name === 'ALL' ? `全部 · ${cases.length}` : `${name} · ${cases.filter((item) => item.dataset_name === name).length}`}</option>)}</select></label>
      <label><span>Case</span><select onChange={(event) => void loadCase(event.target.value)} value={caseId}>{visible.map((item) => <option key={item.case_id} value={item.case_id}>{item.case_id} · {item.completed_session_count} plays</option>)}</select></label>
      {detail && <div className="temporal-forest-summary"><span><UsersRound /><b>{detail.summary.participant_count}</b>玩家</span><span><Activity /><b>{detail.summary.completed_session_count}</b>次完成</span><span><GitBranch /><b>{detail.summary.mean_actions}</b>平均动作</span><span><Clock3 /><b>{Math.round(detail.summary.mean_elapsed_time_min)}m</b>平均时间</span></div>}
    </section>
    {detail ? <section className="temporal-forest-grid">
      <article><PanelTitle icon={<GitBranch />} kicker="REFERENCE TRAJECTORY" title="病例真实时间树" /><div className="temporal-forest-tree">{[...detail.ground_truth_tree.nodes].sort((a, b) => a.reveal_time_min - b.reveal_time_min).map((node) => <div className={`tone-${node.node_type.toLowerCase()} modality-${node.lane.toLowerCase()}`} key={node.node_id} title={node.subtitle}><i /><span><b>{node.label}</b><small>T+{Math.round(node.reveal_time_min)}m · {node.temporal_confidence}</small></span></div>)}</div></article>
      <article><PanelTitle icon={<Stethoscope />} kicker="BELIEF DISTRIBUTION" title={stage === 'FINAL' ? '最终诊断分布' : `S${stage} 诊断排序分布`} /><div className="temporal-stage-tabs">{detail.stages.map((item) => <button className={stage === item.checkpoint ? 'is-active' : ''} key={item.checkpoint} onClick={() => setStage(item.checkpoint)} type="button">S{item.checkpoint}<small>{item.submission_count}</small></button>)}<button className={stage === 'FINAL' ? 'is-active' : ''} onClick={() => setStage('FINAL')} type="button">FINAL</button></div><DistributionList items={distribution} empty="这个阶段还没有玩家提交。" /><div className="temporal-forest-reference"><span>Reference（与玩家分布分开）</span><b>{detail.reference.diagnosis}</b><small>{detail.reference.strength ?? 'reference'}</small></div></article>
      <article><PanelTitle icon={<Activity />} kicker="TRAJECTORY EVALUATION" title="每个 Case 的轨迹评估" /><TrajectoryEvaluationPanel evaluation={detail.trajectory_evaluation} /><details className="temporal-action-details"><summary>检查 / 调阅动作选择率 · {detail.actions.length}</summary><div className="temporal-action-stats">{detail.actions.map((item) => <div key={item.action_id}><span><b>{item.action_id}</b><small>{item.selection_count} 次选择</small></span><i><em style={{ width: `${Math.max(2, item.selection_rate * 100)}%` }} /></i><strong>{Math.round(item.selection_rate * 100)}%</strong></div>)}{!detail.actions.length && <p>还没有已完成的游玩。完成一次 Temporal Arena 后，这里会出现动作分支。</p>}</div></details><details className="temporal-quality-json"><summary>时间质量与限制</summary><pre>{JSON.stringify(detail.temporal_quality, null, 2)}</pre></details></article>
    </section> : <section className="forest-empty"><Trees /><b>{notice}</b></section>}
    {notice && detail && <p className="case-audit-notice">{notice}</p>}
  </main>;
}

const trajectoryMetricCards = [
  ['exact_top1_accuracy', 'Top-1 准确率', 'percent'],
  ['reference_considered_rate', '参考诊断进入率', 'percent'],
  ['mean_last_reference_reciprocal_rank', '最终参考 MRR', 'decimal'],
  ['mean_recorded_action_overlap_rate', 'GT 动作节点重合', 'percent'],
  ['mean_source_order_alignment', '源路径顺序一致度', 'percent'],
  ['mean_source_evidence_reveal_coverage', '证据揭示覆盖', 'percent'],
  ['mean_action_budget_usage', '动作预算使用', 'percent'],
  ['premature_finalization_proxy_rate', '疑似错误早停率', 'percent'],
] as const;

function TrajectoryEvaluationPanel({ evaluation }: { evaluation: TrajectoryEvaluation }) {
  return <div className="case-trajectory-evaluation">
    {evaluation.status === 'NO_COMPLETED_TRAJECTORIES' ? <div className="trajectory-evaluation-empty"><GitBranch /><b>评估协议已绑定</b><span>这个 Case 尚无完成轨迹；医生或模型完成后，这些指标会自动填充。</span></div> : <>
      <div className="case-trajectory-metrics">{trajectoryMetricCards.map(([key, label, format]) => <span key={key}><small>{label}</small><b>{formatTrajectoryMetric(evaluation.aggregate[key], format)}</b></span>)}</div>
      <div className="case-trajectory-runs">{evaluation.trajectories.map((row) => {
        const content = <><i className={row.exact_top1 ? 'is-correct' : 'is-wrong'}>{row.participant_type === 'MODEL' ? 'AI' : 'DR'}</i><span><b>{row.participant_label}</b><small>{row.final_prediction || '未记录最终诊断'} · {row.actions_used}/{row.action_budget} actions · 重合 {Math.round(row.recorded_action_overlap_rate * 100)}%</small></span><strong>{row.exact_top1 ? '命中' : row.premature_finalization_proxy ? '疑似早停' : '未命中'}</strong></>;
        return row.run_id ? <Link href={`/model-arena?mode=temporal&run=${encodeURIComponent(row.run_id)}`} key={row.session_id}>{content}</Link> : <div key={row.session_id}>{content}</div>;
      })}</div>
    </>}
    <details className="trajectory-metric-definitions"><summary>指标口径与解释限制</summary><div>{evaluation.metric_definitions.map((item) => <p key={item.key}><b>{item.label}</b><span>{item.description}</span></p>)}{evaluation.interpretation_limits.map((item) => <em key={item}>{item}</em>)}</div></details>
  </div>;
}

function formatTrajectoryMetric(value: number | null | undefined, format: 'percent' | 'decimal') {
  if (typeof value !== 'number') return '待生成';
  return format === 'percent' ? `${Math.round(value * 100)}%` : value.toFixed(3);
}

function DistributionList({ items, empty }: { items: Distribution[]; empty: string }) {
  if (!items.length) return <div className="distribution-empty">{empty}</div>;
  return <div className="temporal-diagnosis-stats">{items.map((item) => <article key={item.diagnosis}><header><b>{item.diagnosis}</b><span>Top 1 {Math.round(item.top1_rate * 100)}%</span></header><div><i style={{ width: `${Math.max(2, item.selection_rate * 100)}%` }} /></div><footer><span>选择率 {Math.round(item.selection_rate * 100)}%</span><span>平均名次 {item.mean_rank.toFixed(2)}</span></footer></article>)}</div>;
}

function PanelTitle({ icon, kicker, title }: { icon: React.ReactNode; kicker: string; title: string }) {
  return <header className="temporal-panel-title"><span>{icon}</span><div><small>{kicker}</small><b>{title}</b></div></header>;
}
