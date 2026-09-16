'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import {
  Activity,
  ArrowLeft,
  Bot,
  BrainCircuit,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Code2,
  Database,
  FileJson2,
  GitBranch,
  KeyRound,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  Send,
  StepForward,
  Stethoscope,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import type {
  TemporalArenaCase,
  TemporalArenaIndex,
  TemporalArenaReview,
  TemporalArenaState,
  TemporalCase,
  TemporalEvent,
  TemporalGraphNode,
} from '@/features/temporal/types';
import { api } from '@/lib/api';
import type { OpenRouterModel, OpenRouterProvider, OpenRouterStatus } from './types';

const HEADERS = { 'X-Research-Key': 'local-research-only' };

type TemporalModelDecision = {
  diagnoses: string[];
  next_action_id: string | null;
  final: boolean;
  final_diagnosis: string | null;
  rationale: string;
};

type TemporalModelInteraction = {
  interaction_id: string;
  step: number;
  request_payload: Record<string, unknown>;
  response_payload: Record<string, unknown> | null;
  assistant_content: string | null;
  parsed_decision: TemporalModelDecision | null;
  application_result: {
    checkpoint?: number;
    result_type?: string;
    action_id?: string;
    final_diagnosis?: string;
    forced_final?: boolean;
    [key: string]: unknown;
  } | null;
  error: string | null;
  latency_ms: number;
  created_at: string;
};

type TemporalModelRun = {
  run_id: string;
  session_id: string;
  model_id: string;
  provider: string;
  case_id: string;
  dataset_name: string;
  status: 'ACTIVE' | 'COMPLETED';
  max_actions: number;
  forced_final: boolean;
  last_error: string | null;
  created_at: string;
  completed_at: string | null;
};

type TemporalModelEvaluation = {
  outcome: {
    exact_top1: boolean;
    reference_ever_considered: boolean;
    last_differential_reference_rank: number | null;
    last_differential_reciprocal_rank: number;
    first_reference_checkpoint: number | null;
    first_correct_top1_checkpoint: number | null;
  };
  evidence_acquisition: {
    actions_used: number;
    action_budget: number;
    eligible_recorded_evidence_count: number;
    revealed_evidence_count: number;
    source_evidence_reveal_coverage: number;
    recorded_action_overlap_rate: number;
    source_order_alignment: number;
    recorded_action_count: number;
    unobserved_action_count: number;
    unresolved_pending_count_at_final: number;
    elapsed_game_time_min: number;
    wait_count: number;
    simulation_time_advance_count?: number;
    max_orders_before_wait: number;
  };
  belief_dynamics: {
    checkpoint_count: number;
    unique_top1_count: number;
    top1_revision_count: number;
    differential_revision_count: number;
    mean_consecutive_differential_jaccard: number;
  };
  execution: {
    interaction_count: number;
    invalid_interaction_count: number;
    mean_model_latency_ms: number;
    reasoning_tokens: number;
    total_tokens: number;
    reported_cost_usd: number;
    forced_final: boolean;
  };
  flags: {
    ended_with_pending_results: boolean;
    premature_finalization_proxy: boolean;
    correct_early_stop: boolean;
  };
  interpretation_limits: string[];
};

type CaseTrajectoryRow = {
  session_id: string;
  run_id: string | null;
  participant_type: 'MODEL' | 'DOCTOR';
  participant_label: string;
  final_prediction: string;
  exact_top1: boolean;
  actions_used: number;
  action_budget: number;
  recorded_action_overlap_rate: number;
  premature_finalization_proxy: boolean;
};

type CaseTrajectoryEvaluation = {
  completed_trajectory_count: number;
  aggregate: Record<string, number | null>;
  trajectories: CaseTrajectoryRow[];
  metric_definitions: Array<{ key: string; label: string; direction: string; description: string }>;
  interpretation_limits: string[];
};

type TemporalModelDetail = {
  run: TemporalModelRun;
  state: TemporalArenaState;
  interactions: TemporalModelInteraction[];
  review?: TemporalArenaReview;
  evaluation?: TemporalModelEvaluation;
  case_evaluation?: CaseTrajectoryEvaluation;
  case_record?: TemporalCase;
  artifact?: Record<string, unknown>;
};

type RunSummary = TemporalModelRun & { interaction_count: number };

export function TemporalModelArenaDashboard() {
  const [status, setStatus] = useState<OpenRouterStatus | null>(null);
  const [providers, setProviders] = useState<OpenRouterProvider[]>([]);
  const [models, setModels] = useState<OpenRouterModel[]>([]);
  const [cases, setCases] = useState<TemporalArenaCase[]>([]);
  const [activeRuns, setActiveRuns] = useState<RunSummary[]>([]);
  const [completedRuns, setCompletedRuns] = useState<RunSummary[]>([]);
  const [providerId, setProviderId] = useState('');
  const [modelId, setModelId] = useState('');
  const [dataset, setDataset] = useState('');
  const [caseId, setCaseId] = useState('');
  const [query, setQuery] = useState('');
  const [detail, setDetail] = useState<TemporalModelDetail | null>(null);
  const [selectedInteraction, setSelectedInteraction] = useState('');
  const [autoRun, setAutoRun] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('正在读取 Temporal Case…');
  const requestLock = useRef(false);

  useEffect(() => {
    let active = true;
    void Promise.all([
      api<OpenRouterStatus>('/model-arena/status', { headers: HEADERS }),
      api<{ providers: OpenRouterProvider[]; models: OpenRouterModel[] }>('/model-arena/models', { headers: HEADERS }),
      api<TemporalArenaIndex>('/temporal/cases'),
      api<{ runs: RunSummary[] }>('/temporal-model-arena/runs', { headers: HEADERS }),
    ]).then(([nextStatus, catalog, caseIndex, runIndex]) => {
      if (!active) return;
      setStatus(nextStatus);
      setProviders(catalog.providers);
      setModels(catalog.models);
      setCases(caseIndex.cases);
      setActiveRuns(runIndex.runs.filter((item) => item.status === 'ACTIVE'));
      setCompletedRuns(runIndex.runs.filter((item) => item.status === 'COMPLETED'));
      const provider = catalog.providers.find((item) => item.id === 'openai') ?? catalog.providers[0];
      setProviderId(provider?.id ?? '');
      setModelId(catalog.models.find((item) => item.provider === provider?.id)?.id ?? '');
      const first = caseIndex.cases[0];
      setDataset(first?.dataset_name ?? '');
      setCaseId(first?.case_id ?? '');
      setNotice(nextStatus.configured ? '' : '后端未读取到 OPENROUTER_API_KEY，请检查项目 .env 或 tools/api_smoke/.env。');
      const requestedRun = new URLSearchParams(window.location.search).get('run');
      if (requestedRun && runIndex.runs.some((item) => item.run_id === requestedRun)) {
        setBusy(true);
        void api<TemporalModelDetail>(`/temporal-model-arena/runs/${requestedRun}`, { headers: HEADERS }).then((result) => {
          if (!active) return;
          setDetail(result);
          setSelectedInteraction(result.interactions.at(-1)?.interaction_id ?? '');
          setNotice(result.run.last_error ?? '');
        }).catch((error: Error) => {
          if (active) setNotice(error.message);
        }).finally(() => {
          if (active) setBusy(false);
        });
      }
    }).catch((error: Error) => active && setNotice(error.message));
    return () => { active = false; };
  }, []);

  const providerModels = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return models.filter((item) => item.provider === providerId && (!needle || item.id.toLowerCase().includes(needle) || item.name.toLowerCase().includes(needle)));
  }, [models, providerId, query]);
  const datasets = useMemo(() => [...new Set(cases.map((item) => item.dataset_name))], [cases]);
  const datasetCounts = useMemo(
    () => cases.reduce<Record<string, number>>((counts, item) => {
      counts[item.dataset_name] = (counts[item.dataset_name] ?? 0) + 1;
      return counts;
    }, {}),
    [cases],
  );
  const datasetCases = cases.filter((item) => item.dataset_name === dataset);

  function chooseProvider(value: string) {
    setProviderId(value);
    setModelId(models.find((item) => item.provider === value)?.id ?? '');
    setQuery('');
  }

  function chooseDataset(value: string) {
    setDataset(value);
    setCaseId(cases.find((item) => item.dataset_name === value)?.case_id ?? '');
  }

  async function start() {
    if (!modelId || !caseId || !status?.configured) return;
    setBusy(true);
    setNotice('');
    try {
      const result = await api<TemporalModelDetail>('/temporal-model-arena/runs', {
        method: 'POST',
        headers: HEADERS,
        body: JSON.stringify({ model_id: modelId, case_id: caseId, max_questions: 30 }),
      });
      setDetail(result);
      window.history.replaceState(null, '', `/model-arena?mode=temporal&run=${encodeURIComponent(result.run.run_id)}`);
      setSelectedInteraction('');
      setAutoRun(true);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '无法创建 Temporal 模型会话');
    } finally {
      setBusy(false);
    }
  }

  async function resume(runId: string) {
    setBusy(true);
    try {
      const result = await api<TemporalModelDetail>(`/temporal-model-arena/runs/${runId}`, { headers: HEADERS });
      setDetail(result);
      window.history.replaceState(null, '', `/model-arena?mode=temporal&run=${encodeURIComponent(runId)}`);
      setSelectedInteraction(result.interactions.at(-1)?.interaction_id ?? '');
      setNotice(result.run.last_error ?? '');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '无法恢复模型会话');
    } finally {
      setBusy(false);
    }
  }

  const step = useCallback(async () => {
    if (!detail || detail.run.status !== 'ACTIVE' || requestLock.current) return;
    requestLock.current = true;
    setBusy(true);
    try {
      const result = await api<TemporalModelDetail>(`/temporal-model-arena/runs/${detail.run.run_id}/step`, { method: 'POST', headers: HEADERS });
      setDetail(result);
      const latest = result.interactions.at(-1);
      setSelectedInteraction(latest?.interaction_id ?? '');
      if (latest?.error) {
        const rejectedCount = trailingErrorCount(result.interactions);
        if (rejectedCount >= 3) setAutoRun(false);
        setNotice(
          rejectedCount >= 3
            ? `连续 ${rejectedCount} 次返回无效动作，已暂停：${latest.error}`
            : `动作未执行，错误已回传给模型重新选择（${rejectedCount}/3）：${latest.error}`,
        );
      } else if (result.run.status === 'COMPLETED') {
        setAutoRun(false);
        setNotice('');
      }
    } catch (error) {
      setAutoRun(false);
      setNotice(error instanceof Error ? error.message : 'Temporal 模型回合失败');
    } finally {
      requestLock.current = false;
      setBusy(false);
    }
  }, [detail]);

  useEffect(() => {
    if (!autoRun || busy || !detail || detail.run.status !== 'ACTIVE') return;
    const timer = window.setTimeout(() => void step(), 500);
    return () => window.clearTimeout(timer);
  }, [autoRun, busy, detail, step]);

  function reset() {
    setAutoRun(false);
    setDetail(null);
    window.history.replaceState(null, '', '/model-arena?mode=temporal');
    setSelectedInteraction('');
    setNotice('');
  }

  if (!detail) return <TemporalModelSetup activeRuns={activeRuns} busy={busy} caseId={caseId} cases={datasetCases} completedRuns={completedRuns} dataset={dataset} datasetCounts={datasetCounts} datasets={datasets} modelId={modelId} models={providerModels} notice={notice} onCase={setCaseId} onDataset={chooseDataset} onModel={setModelId} onProvider={chooseProvider} onQuery={setQuery} onResume={(value) => void resume(value)} onStart={() => void start()} providerId={providerId} providers={providers} query={query} status={status} />;
  if (detail.run.status === 'COMPLETED' && detail.review) return <TemporalModelReview detail={detail} onReset={reset} review={detail.review} />;

  const selected = detail.interactions.find((item) => item.interaction_id === selectedInteraction) ?? detail.interactions.at(-1);
  return <main className="model-run-page temporal-model-run-page">
    <header className="model-run-header"><Link href="/model-arena?mode=temporal"><ArrowLeft />模型选择</Link><span className="model-run-mark"><Clock3 /></span><div className="min-w-0 flex-1"><p>OPENROUTER · TEMPORAL FOREST</p><h1>{detail.run.model_id}</h1></div><div className="model-run-meter"><span><b>{detail.state.action_count}</b> / {detail.run.max_actions}</span><small>动作 / 硬上限</small></div><Badge className={autoRun ? 'model-live-badge' : 'model-pause-badge'}>{busy ? '模型思考中' : autoRun ? '自动进行中' : '已暂停'}</Badge><Button disabled={busy} onClick={() => setAutoRun((value) => !value)} size="sm" variant="outline">{autoRun ? <Pause /> : <Play />}{autoRun ? '暂停' : '继续'}</Button><Button disabled={busy || autoRun} onClick={() => void step()} size="sm"><StepForward />单步</Button><Button disabled={busy} onClick={reset} size="sm" variant="ghost"><RotateCcw />New case</Button></header>
    <section className="model-run-context-bar"><span><Database />{detail.run.dataset_name}</span><span><GitBranch />{detail.run.case_id}</span><span><Clock3 />T+{Math.round(detail.state.current_time_min)}m</span><span><Activity />S{detail.state.checkpoint}</span><i>临床动作、模拟时钟推进与结果揭示均走医生 Arena 的同一状态机</i></section>
    <section className="model-run-grid">
      <article className="model-cockpit-panel"><PanelTitle icon={<GitBranch />} kicker="LIVE TIME PATH" title="模型当前可见的患者轨迹" /><TemporalPath state={detail.state} /></article>
      <article className="model-cockpit-panel"><PanelTitle icon={<BrainCircuit />} kicker="DECISION TIMELINE" title="每轮诊断、动作与时间推进" /><div className="model-round-scroll">{!detail.interactions.length && <div className="model-waiting-state"><span><Clock3 /></span><h2>S0 已封装成 JSON</h2><p>模型先提交诊断排序，再选择临床动作或直接结束；动作结果同步返回。</p></div>}{detail.interactions.map((item) => <button className={`temporal-model-round ${item.interaction_id === selected?.interaction_id ? 'is-selected' : ''} ${item.error ? 'has-error' : ''}`} key={item.interaction_id} onClick={() => setSelectedInteraction(item.interaction_id)} type="button"><span>S{item.application_result?.checkpoint ?? item.step - 1}</span><div><header><b>{item.error ? 'JSON / 状态校验失败' : item.parsed_decision?.final ? '锁定诊断' : item.application_result?.result_type === 'WAIT' ? '旧版时间推进' : '执行问询 / 检查 / 调阅'}</b><small>{item.latency_ms} ms</small></header><ol>{item.parsed_decision?.diagnoses.map((value, index) => <li key={value}><i>{index + 1}</i>{value}</li>)}</ol>{item.error ? <p>{item.error}</p> : <footer><span>{String(item.application_result?.action_id ?? item.parsed_decision?.next_action_id ?? item.application_result?.final_diagnosis ?? '—')}</span><small>{item.parsed_decision?.rationale}</small></footer>}</div></button>)}</div></article>
      <article className="model-cockpit-panel"><PanelTitle icon={<Code2 />} kicker="ROUND INSPECTOR" title="Prompt · 原始响应 · 解析 · 执行" /><TemporalInspector interaction={selected} /></article>
    </section>
    {notice && <div className="model-run-toast"><CircleAlert /><span>{notice}</span>{detail.run.last_error && <Button disabled={busy} onClick={() => void step()} size="sm"><RefreshCw />重试</Button>}</div>}
  </main>;
}

function trailingErrorCount(items: Array<{ error?: string | null }>) {
  let count = 0;
  for (let index = items.length - 1; index >= 0 && items[index]?.error; index -= 1) count += 1;
  return count;
}

function TemporalModelSetup({ activeRuns, busy, caseId, cases, completedRuns, dataset, datasetCounts, datasets, modelId, models, notice, onCase, onDataset, onModel, onProvider, onQuery, onResume, onStart, providerId, providers, query, status }: { activeRuns: RunSummary[]; busy: boolean; caseId: string; cases: TemporalArenaCase[]; completedRuns: RunSummary[]; dataset: string; datasetCounts: Record<string, number>; datasets: string[]; modelId: string; models: OpenRouterModel[]; notice: string; onCase: (value: string) => void; onDataset: (value: string) => void; onModel: (value: string) => void; onProvider: (value: string) => void; onQuery: (value: string) => void; onResume: (value: string) => void; onStart: () => void; providerId: string; providers: OpenRouterProvider[]; query: string; status: OpenRouterStatus | null }) {
  return <main className="model-setup-page">
    <header className="model-setup-header"><Link href="/model-arena"><ArrowLeft />普通数据集模型测试</Link><div><p>CLINCFORESTBENCH · TEMPORAL MODEL LAB</p><h1>时间病例模型测试</h1></div><Badge className={status?.configured ? 'is-connected' : 'is-offline'}><span />OpenRouter {status?.configured ? '已连接' : '未配置'}</Badge></header>
    <section className="model-setup-intro"><span className="model-setup-hero-icon"><Clock3 /></span><div><p>DYNAMIC TEMPORAL DIAGNOSTIC SIMULATION</p><h2>让模型面对会随临床动作推进、逐步揭示真实结果的时间树。</h2><small>{Object.values(datasetCounts).reduce((sum, count) => sum + count, 0)} 个 Case 已同步；每轮只返回一个 JSON，疾病和动作不可重复，最多 30 个动作，可随时锁定诊断。</small></div></section>
    {activeRuns.length > 0 && <section className="model-resume-strip"><span><RefreshCw /></span><div><b>发现 {activeRuns.length} 个未完成的时间模型测试</b><small>{activeRuns[0].model_id} · {activeRuns[0].case_id} · {activeRuns[0].interaction_count} turns</small></div><Button disabled={busy} onClick={() => onResume(activeRuns[0].run_id)} size="sm"><Play />恢复测试</Button></section>}
    {completedRuns.length > 0 && <section className="temporal-completed-runs"><header><span><CheckCircle2 /></span><div><b>最近完成的真实模型轨迹</b><small>点击查看逐轮路径、参考树高亮和轨迹指标</small></div></header><div>{completedRuns.slice(0, 6).map((run) => <button disabled={busy} key={run.run_id} onClick={() => onResume(run.run_id)} type="button"><span>{run.provider}</span><b>{run.model_id}</b><small>{run.case_id} · {run.interaction_count} turns</small></button>)}</div></section>}
    <section className="model-setup-grid">
      <article className="model-setup-card provider-card"><header><span>01</span><div><p>COMPANY</p><h3>选择模型公司</h3></div></header><div className="provider-picker">{providers.map((item) => <button className={item.id === providerId ? 'is-selected' : ''} key={item.id} onClick={() => onProvider(item.id)} type="button"><span><Bot /></span><b>{item.name}</b><small>{item.model_count}</small></button>)}</div></article>
      <article className="model-setup-card model-picker-card"><header><span>02</span><div><p>MODEL</p><h3>选择 OpenRouter 模型</h3></div></header><div className="model-search-box"><Search /><Input onChange={(event) => onQuery(event.target.value)} placeholder="搜索模型名或 ID" value={query} /></div><div className="openrouter-model-list">{models.map((item) => <button className={item.id === modelId ? 'is-selected' : ''} key={item.id} onClick={() => onModel(item.id)} type="button"><span>{item.id === modelId ? <CheckCircle2 /> : <Bot />}</span><div><b>{item.name}</b><small>{item.id}</small></div></button>)}</div></article>
      <article className="model-setup-card case-picker-card"><header><span>03</span><div><p>TEMPORAL CASE</p><h3>选择新数据集与病例</h3></div></header><div className="model-dataset-picker temporal-model-datasets">{datasets.map((name) => <button className={dataset === name ? 'is-selected' : ''} key={name} onClick={() => onDataset(name)} type="button"><Database /><b>{name}</b><small>{datasetCounts[name] ?? 0} cases · dynamic tree</small></button>)}</div><label className="model-case-select"><span><Stethoscope />Case</span><select onChange={(event) => onCase(event.target.value)} value={caseId}>{cases.map((item) => <option key={item.case_id} value={item.case_id}>{item.case_id} · {item.eligible_event_count} actions · T+{Math.round(item.max_time_min)}m</option>)}</select></label><div className="model-rule-strip"><span><b>30</b><small>动作硬上限</small></span><span><b>SYNC</b><small>模拟时间推进</small></span><span><b>1 JSON</b><small>每轮输出</small></span></div><Button className="model-launch-button" disabled={busy || !modelId || !caseId || !status?.configured} onClick={onStart}>{busy ? <RefreshCw className="animate-spin" /> : <Send />}{busy ? '正在创建…' : '开始自动模拟'}</Button></article>
    </section>
    {notice && <div className="model-setup-notice"><CircleAlert />{notice}</div>}<footer className="model-setup-footer"><KeyRound />API Key 只从后端本地 .env 读取；受限病例与交互日志保持本地。</footer>
  </main>;
}

function TemporalPath({ state }: { state: TemporalArenaState }) {
  return <div className="temporal-model-path"><div className="is-initial"><i /><span><b>Initial state</b><small>{summarize(state.initial_state)}</small></span></div>{state.revealed_events.map((event) => <div className={`modality-${event.clinical_concept.modality.toLowerCase()}`} key={event.event_id}><i /><span><b>{event.clinical_concept.display}</b><small>T+{Math.round(event.time.relative_available_min ?? event.time.relative_documented_min ?? 0)}m · {summarizeEvent(event)}</small></span></div>)}{state.pending_actions.filter((item) => item.status === 'PENDING').map((item) => <div className="is-pending" key={`${item.action_id}-${item.source_event_id}`}><i /><span><b>{item.display ?? item.action_id}</b><small>Pending · expected T+{Math.round(item.expected_available_game_time ?? 0)}m</small></span></div>)}</div>;
}

function TemporalInspector({ interaction }: { interaction?: TemporalModelInteraction }) {
  if (!interaction) return <div className="model-inspector-empty"><FileJson2 /><b>等待第一轮</b><p>完整 Prompt、响应、解析和状态更新会在这里保留。</p></div>;
  return <Tabs className="model-inspector-tabs" defaultValue="prompt" key={interaction.interaction_id}><TabsList><TabsTrigger value="prompt">Prompt JSON</TabsTrigger><TabsTrigger value="response">原始响应</TabsTrigger><TabsTrigger value="parsed">解析 JSON</TabsTrigger><TabsTrigger value="applied">状态更新</TabsTrigger></TabsList><TabsContent value="prompt"><Json value={extractPrompt(interaction.request_payload)} /></TabsContent><TabsContent value="response"><Json value={interaction.response_payload ?? interaction.assistant_content} /></TabsContent><TabsContent value="parsed"><Json value={interaction.parsed_decision} /></TabsContent><TabsContent value="applied"><Json value={interaction.application_result ?? { error: interaction.error }} /></TabsContent></Tabs>;
}

function TemporalModelReview({ detail, onReset, review }: { detail: TemporalModelDetail; onReset: () => void; review: TemporalArenaReview }) {
  return <main className="temporal-model-review">
    <header>
      <Link href="/model-arena?mode=temporal"><ArrowLeft />模型选择</Link>
      <div><small>{detail.run.model_id} · {detail.run.dataset_name}</small><h1>{detail.run.case_id} · 模型诊断轨迹</h1></div>
      <Badge className={review.comparison.is_exact_match ? 'is-correct' : 'is-wrong'}>{review.comparison.is_exact_match ? <CheckCircle2 /> : <CircleAlert />}{review.comparison.is_exact_match ? 'Top-1 命中' : 'Top-1 未命中'}</Badge>
      <Button onClick={() => download(detail.artifact, `${detail.run.run_id}.json`)} variant="outline"><FileJson2 />导出本 Case</Button>
      <Button onClick={onReset}><RotateCcw />New case</Button>
    </header>
    <section>
      <article className="temporal-review-timeline-panel"><PanelTitle icon={<BrainCircuit />} kicker="MODEL TRACE" title="决策时间线" /><TemporalDecisionTimeline interactions={detail.interactions} /></article>
      <article className="temporal-review-tree-panel"><PanelTitle icon={<Stethoscope />} kicker="PATH OVERLAY" title="GT 与模型轨迹" /><TemporalTrajectoryComparison graph={review.ground_truth_tree} prediction={review.comparison.predicted_diagnosis} reference={review.comparison.ground_truth_diagnosis} session={review.session} /><div className="temporal-model-comparison"><span>模型最终诊断<b>{review.comparison.predicted_diagnosis}</b></span><span>参考诊断<b>{review.comparison.ground_truth_diagnosis}</b></span></div></article>
      <article className="temporal-review-result-panel"><PanelTitle icon={<Activity />} kicker="CASE RESULT" title="结果与完整评估" /><TemporalResultSidebar detail={detail} review={review} /></article>
    </section>
  </main>;
}

function TemporalDecisionTimeline({ interactions }: { interactions: TemporalModelInteraction[] }) {
  return <div className="temporal-review-timeline">
    <div className="temporal-review-timeline-summary"><b>{interactions.length}</b><span>轮模型交互</span><small>点击任一轮展开完整鉴别诊断与理由</small></div>
    {interactions.map((item) => {
      const decision = item.parsed_decision;
      const resultType = item.error ? 'ERROR' : String(item.application_result?.result_type ?? 'DECISION');
      const action = String(item.application_result?.action_id ?? decision?.next_action_id ?? item.application_result?.final_diagnosis ?? '—');
      return <details className={`temporal-review-turn ${item.error ? 'has-error' : ''}`} key={item.interaction_id}>
        <summary><i>R{item.step}</i><span><b>{decision?.diagnoses[0] ?? '解析失败'}</b><small>S{item.application_result?.checkpoint ?? item.step - 1} · {resultType} · {action}</small></span><em>{item.latency_ms} ms</em></summary>
        <div>{item.error ? <p>{item.error}</p> : <><ol>{decision?.diagnoses.map((value, index) => <li key={value}><i>{index + 1}</i><span>{value}</span></li>)}</ol>{decision?.rationale && <p>{decision.rationale}</p>}</>}</div>
      </details>;
    })}
  </div>;
}

function TemporalResultSidebar({ detail, review }: { detail: TemporalModelDetail; review: TemporalArenaReview }) {
  const evaluation = detail.evaluation;
  if (!evaluation) return <div className="temporal-result-sidebar"><p>评估数据正在生成。</p></div>;
  const outcome = evaluation.outcome;
  const evidence = evaluation.evidence_acquisition;
  const belief = evaluation.belief_dynamics;
  const execution = evaluation.execution;
  const caseEvaluation = detail.case_evaluation;
  return <div className="temporal-result-sidebar">
    <section className={`temporal-result-outcome ${outcome.exact_top1 ? 'is-correct' : 'is-wrong'}`}>
      <header><span>{outcome.exact_top1 ? <CheckCircle2 /> : <CircleAlert />}</span><div><small>MODEL TOP-1</small><b>{outcome.exact_top1 ? '诊断命中' : '诊断未命中'}</b></div></header>
      <p><small>模型</small><b>{review.comparison.predicted_diagnosis}</b></p>
      <p><small>参考</small><b>{review.comparison.ground_truth_diagnosis}</b></p>
    </section>

    {evaluation.flags.premature_finalization_proxy && <div className="temporal-result-warning"><CircleAlert /><span><b>疑似错误早停</b><small>结束时仍有 {evidence.unresolved_pending_count_at_final} 个 pending，证据揭示 {Math.round(evidence.source_evidence_reveal_coverage * 100)}%。</small></span></div>}

    <ResultMetricGroup title="诊断结果" metrics={[
      ['参考诊断是否进入列表', outcome.reference_ever_considered ? '是' : '否'],
      ['最终参考诊断排名', outcome.last_differential_reference_rank ? `#${outcome.last_differential_reference_rank}` : '未进入'],
      ['最终参考 MRR', outcome.last_differential_reciprocal_rank.toFixed(3)],
      ['首次进入阶段', outcome.first_reference_checkpoint === null ? '从未' : `S${outcome.first_reference_checkpoint}`],
    ]} />
    <ResultMetricGroup title="轨迹与证据" metrics={[
      ['GT 动作节点重合', percent(evidence.recorded_action_overlap_rate)],
      ['源路径顺序一致', percent(evidence.source_order_alignment)],
      ['证据揭示覆盖', `${evidence.revealed_evidence_count}/${evidence.eligible_recorded_evidence_count} · ${percent(evidence.source_evidence_reveal_coverage)}`],
      ['动作 / 上限', `${evidence.actions_used}/${evidence.action_budget}`],
      ['模拟时间推进', String(evidence.simulation_time_advance_count ?? evidence.wait_count)],
      ['结束时 Pending', String(evidence.unresolved_pending_count_at_final)],
      ['未记录动作', String(evidence.unobserved_action_count)],
      ['病例时间', `T+${Math.round(evidence.elapsed_game_time_min)}m`],
    ]} />
    <ResultMetricGroup title="信念与模型执行" metrics={[
      ['诊断状态数', String(belief.checkpoint_count)],
      ['Top-1 改变', String(belief.top1_revision_count)],
      ['鉴别列表改变', String(belief.differential_revision_count)],
      ['相邻列表 Jaccard', belief.mean_consecutive_differential_jaccard.toFixed(3)],
      ['交互 / 错误', `${execution.interaction_count}/${execution.invalid_interaction_count}`],
      ['平均延迟', `${execution.mean_model_latency_ms} ms`],
      ['Tokens', execution.total_tokens.toLocaleString()],
      ['OpenRouter 成本', `$${execution.reported_cost_usd.toFixed(4)}`],
    ]} />

    {caseEvaluation && <section className="temporal-case-run-section"><header><div><small>SAME CASE</small><b>同一病例的全部完成结果</b></div><span>{caseEvaluation.completed_trajectory_count}</span></header><div>{caseEvaluation.trajectories.map((row) => {
      const content = <><i className={row.exact_top1 ? 'is-correct' : 'is-wrong'}>{row.participant_type === 'MODEL' ? 'AI' : 'DR'}</i><span><b>{row.participant_label}</b><small>{row.final_prediction || '未记录最终诊断'} · {row.actions_used}/{row.action_budget} actions</small></span><em>{row.exact_top1 ? '命中' : '未命中'}</em></>;
      return row.run_id ? <Link className={row.run_id === detail.run.run_id ? 'is-current' : ''} href={`/model-arena?mode=temporal&run=${encodeURIComponent(row.run_id)}`} key={row.session_id}>{content}</Link> : <div key={row.session_id}>{content}</div>;
    })}</div></section>}

    <details className="temporal-result-details"><summary>指标含义与解释限制</summary><div>{caseEvaluation?.metric_definitions.map((item) => <p key={item.key}><b>{item.label}</b><span>{item.description}</span></p>)}{[...(caseEvaluation?.interpretation_limits ?? []), ...evaluation.interpretation_limits].filter((value, index, values) => values.indexOf(value) === index).map((item) => <em key={item}>{item}</em>)}</div></details>
    <details className="temporal-result-details temporal-result-json"><summary>病例原始数据、规范事件与 GT JSON</summary><Json value={detail.case_record} /></details>
    <details className="temporal-result-details temporal-result-json"><summary>完整 Prompt、响应与状态 JSON · {detail.interactions.length} turns</summary><Json value={detail.artifact} /></details>
  </div>;
}

function ResultMetricGroup({ metrics, title }: { metrics: Array<[string, string]>; title: string }) {
  return <section className="temporal-result-metric-group"><h3>{title}</h3><div>{metrics.map(([label, value]) => <span key={label}><small>{label}</small><b>{value}</b></span>)}</div></section>;
}

function percent(value: number) { return `${Math.round(value * 100)}%`; }

type TrajectoryNodeStatus = 'gt-only' | 'shared' | 'model-only' | 'pending' | 'reference' | 'correct-final';
type TrajectoryNodeData = {
  kind: string;
  label: string;
  shortLabel: string;
  status: TrajectoryNodeStatus;
  subtitle: string;
  timeMin: number;
  source?: TemporalGraphNode;
};
type TrajectoryFlowNode = Node<TrajectoryNodeData, 'trajectoryNode'>;
const trajectoryNodeTypes = { trajectoryNode: TrajectoryNode };

function TemporalTrajectoryComparison({ graph, prediction, reference, session }: {
  graph: TemporalArenaReview['ground_truth_tree'];
  prediction: string;
  reference: string;
  session: TemporalArenaReview['session'];
}) {
  const [selectedId, setSelectedId] = useState(graph.root_id);
  const flow = useMemo(
    () => buildTrajectoryComparison(graph, session, prediction, reference, selectedId),
    [graph, prediction, reference, selectedId, session],
  );
  const selected = flow.nodes.find((node) => node.id === selectedId)?.data ?? flow.nodes[0]?.data;
  return <div className="trajectory-comparison-canvas">
    <div className="trajectory-compare-legend">
      <span><i className="is-shared" />模型与 GT 重合</span>
      <span><i className="is-gt-only" />仅 GT</span>
      <span><i className="is-model-only" />仅模型 / belief</span>
      <span><i className="is-pending" />已下单未返回</span>
      <span><i className="is-reference" />参考诊断</span>
    </div>
    <div className="trajectory-lane-labels"><span>完整 GT 时间树</span><span>MODEL TRACE</span></div>
    <ReactFlow
      edges={flow.edges}
      fitView
      fitViewOptions={{ padding: 0.12, minZoom: 0.08, maxZoom: 0.9 }}
      maxZoom={2.5}
      minZoom={0.05}
      nodes={flow.nodes}
      nodesConnectable={false}
      nodesDraggable={false}
      nodeTypes={trajectoryNodeTypes}
      onNodeClick={(_, node) => setSelectedId(node.id)}
      panOnDrag
      proOptions={{ hideAttribution: true }}
      zoomOnScroll
    >
      <Background color="#31505d" gap={22} size={1} variant={BackgroundVariant.Dots} />
      <Controls showInteractive={false} />
    </ReactFlow>
    {selected && <div className={`trajectory-node-inspector status-${selected.status}`}><span>{statusLabel(selected.status)}</span><b>{selected.label}</b><small>{selected.subtitle || selected.kind} · T+{Math.round(selected.timeMin)}m</small></div>}
  </div>;
}

function buildTrajectoryComparison(
  graph: TemporalArenaReview['ground_truth_tree'],
  session: TemporalArenaReview['session'],
  prediction: string,
  reference: string,
  selectedId: string,
): { nodes: TrajectoryFlowNode[]; edges: Edge[] } {
  const graphNodes = graph.nodes;
  const ranks = new Map(
    Array.from(new Set(graphNodes.map((node) => node.reveal_time_min)))
      .sort((left, right) => left - right)
      .map((value, index) => [value, index]),
  );
  const collisions = new Map<string, number>();
  const positions = new Map<string, { x: number; y: number }>();
  for (const node of graphNodes) {
    const rank = ranks.get(node.reveal_time_min) ?? 0;
    const lane = comparisonLaneX(node.lane);
    const key = `${rank}:${lane}`;
    const collision = collisions.get(key) ?? 0;
    collisions.set(key, collision + 1);
    positions.set(node.node_id, {
      x: lane + collision * 52 + (node.node_type === 'RESULT' ? 46 : 0),
      y: rank * 50,
    });
  }

  const ordered = new Set<string>();
  const revealed = new Set(session.revealed_event_ids);
  for (const item of session.event_log) {
    if (item.event_type !== 'ORDER_ACTION' || !item.outcome || typeof item.outcome !== 'object') continue;
    const sourceEventId = (item.outcome as Record<string, unknown>).source_event_id;
    if (typeof sourceEventId === 'string') ordered.add(sourceEventId);
  }
  const gtShared = new Set<string>();
  const context = graphNodes.find((node) => node.node_type === 'CONTEXT') ?? graphNodes.find((node) => node.node_id === graph.root_id);
  const root = graphNodes.find((node) => node.node_id === graph.root_id);
  if (root) gtShared.add(root.node_id);
  if (context) gtShared.add(context.node_id);
  for (const node of graphNodes) {
    if (!node.event_id) continue;
    if (node.node_type === 'ACTION' && ordered.has(node.event_id)) gtShared.add(node.node_id);
    if (node.node_type === 'RESULT' && revealed.has(node.event_id)) gtShared.add(node.node_id);
  }

  const nodes: TrajectoryFlowNode[] = graphNodes.map((source) => {
    let status: TrajectoryNodeStatus = gtShared.has(source.node_id) ? 'shared' : 'gt-only';
    if (source.node_type === 'RESULT' && source.event_id && ordered.has(source.event_id) && !revealed.has(source.event_id)) status = 'pending';
    if (source.node_type === 'REFERENCE') status = 'reference';
    return {
      id: source.node_id,
      type: 'trajectoryNode',
      position: positions.get(source.node_id) ?? { x: 360, y: 0 },
      selected: source.node_id === selectedId,
      data: {
        kind: source.node_type,
        label: source.label,
        shortLabel: shortNodeLabel(source.node_type, source.lane),
        status,
        subtitle: source.subtitle,
        timeMin: source.game_time_min,
        source,
      },
    };
  });

  const edges: Edge[] = graph.edges.map((edge) => {
    const support = edge.edge_type === 'SUPPORTS_REFERENCE';
    const result = edge.edge_type === 'RESULT_AVAILABLE';
    const color = support ? '#ef4444' : result ? '#527685' : '#385866';
    return {
      id: `GT::${edge.edge_id}`,
      source: edge.source_node,
      target: edge.target_node,
      type: 'smoothstep',
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 11, height: 11 },
      style: { stroke: color, strokeWidth: support ? 2.2 : 1.2, opacity: support ? 0.9 : 0.62 },
    };
  });

  const eventNode = (eventId: string, type: 'ACTION' | 'RESULT') =>
    graphNodes.find((node) => node.event_id === eventId && node.node_type === type);
  const modelSteps: Array<{ id: string; label: string; shortLabel: string; kind: string; subtitle: string; timeMin: number; matchId?: string; status: TrajectoryNodeStatus }> = [];
  if (context) modelSteps.push({ id: 'MODEL::S0', label: '模型读取初始病情', shortLabel: 'S0', kind: 'MODEL_CONTEXT', subtitle: '与 GT 初始状态重合', timeMin: 0, matchId: context.node_id, status: 'shared' });
  let beliefIndex = 0;
  let actionIndex = 0;
  for (const item of session.event_log) {
    const eventType = typeof item.event_type === 'string' ? item.event_type : '';
    const timeMin = firstFinite(item.game_time_min, item.game_time_after_min, 0);
    if (eventType === 'BELIEF_SUBMITTED') {
      const diagnoses = Array.isArray(item.diagnoses) ? item.diagnoses.map(String) : [];
      const top1 = diagnoses[0] ?? '未提交诊断';
      const checkpoint = typeof item.checkpoint === 'number' || typeof item.checkpoint === 'string' ? item.checkpoint : beliefIndex;
      modelSteps.push({ id: `MODEL::BELIEF::${beliefIndex}`, label: `S${checkpoint} · ${top1}`, shortLabel: `S${checkpoint}`, kind: 'BELIEF', subtitle: diagnoses.map((value, index) => `${index + 1}. ${value}`).join(' · '), timeMin, status: 'model-only' });
      beliefIndex += 1;
    } else if (eventType === 'ORDER_ACTION') {
      const outcome = item.outcome && typeof item.outcome === 'object' ? item.outcome as Record<string, unknown> : {};
      const eventId = typeof outcome.source_event_id === 'string' ? outcome.source_event_id : '';
      const match = eventId ? eventNode(eventId, 'ACTION') : undefined;
      const label = typeof outcome.display === 'string' ? outcome.display : typeof outcome.action_id === 'string' ? outcome.action_id : '未记录动作';
      modelSteps.push({ id: `MODEL::ACTION::${actionIndex}`, label, shortLabel: 'ACT', kind: 'MODEL_ACTION', subtitle: match ? '模型动作与 GT 记录动作重合' : '模型选择，但源病例没有该动作结果', timeMin, matchId: match?.node_id, status: match ? 'shared' : 'model-only' });
      actionIndex += 1;
    } else if (eventType === 'WAIT_FOR_NEXT_RESULT' || eventType === 'RESULT_REVEALED') {
      const resolved = Array.isArray(item.resolved_event_ids) ? item.resolved_event_ids.map(String) : [];
      for (const eventId of resolved) {
        const match = eventNode(eventId, 'RESULT');
        modelSteps.push({ id: `MODEL::RESULT::${eventId}`, label: match?.label ?? eventId, shortLabel: 'RES', kind: 'MODEL_RESULT', subtitle: '模拟时钟推进后向模型揭示的真实记录结果', timeMin, matchId: match?.node_id, status: match ? 'shared' : 'model-only' });
      }
    } else if (eventType === 'FINAL_DIAGNOSIS') {
      const diagnoses = Array.isArray(item.diagnoses) ? item.diagnoses.map(String) : [prediction];
      const exact = diagnoses[0]?.toLocaleLowerCase() === reference.toLocaleLowerCase();
      modelSteps.push({ id: 'MODEL::FINAL', label: diagnoses[0] || prediction || 'Final', shortLabel: 'DX', kind: 'MODEL_FINAL', subtitle: exact ? '模型最终诊断与参考诊断一致' : `参考诊断：${reference}`, timeMin, status: exact ? 'correct-final' : 'model-only' });
    }
  }

  modelSteps.forEach((step, index) => {
    nodes.push({
      id: step.id,
      type: 'trajectoryNode',
      position: { x: 720, y: index * 72 },
      selected: step.id === selectedId,
      data: { kind: step.kind, label: step.label, shortLabel: step.shortLabel, status: step.status, subtitle: step.subtitle, timeMin: step.timeMin },
    });
    if (index > 0) {
      edges.push({
        id: `MODEL::PATH::${index}`,
        source: modelSteps[index - 1].id,
        target: step.id,
        type: 'smoothstep',
        animated: true,
        markerEnd: { type: MarkerType.ArrowClosed, color: '#a78bfa', width: 13, height: 13 },
        style: { stroke: '#a78bfa', strokeWidth: 2.8 },
      });
    }
    if (step.matchId) {
      edges.push({
        id: `MODEL::MATCH::${index}`,
        source: step.matchId,
        target: step.id,
        type: 'straight',
        style: { stroke: '#22d3ee', strokeDasharray: '5 5', strokeWidth: 1.4, opacity: 0.75 },
      });
    }
  });
  return { nodes, edges };
}

function TrajectoryNode({ data, selected }: NodeProps<TrajectoryFlowNode>) {
  return <button className={`trajectory-compare-node status-${data.status} ${selected ? 'is-selected' : ''}`} title={`${data.label}\n${data.subtitle}`} type="button">
    <Handle position={Position.Top} type="target" />
    <span>{data.shortLabel}</span>
    <Handle position={Position.Bottom} type="source" />
  </button>;
}

function comparisonLaneX(lane: string) {
  return ({ ANCHOR: 280, CONTEXT: 280, HISTORY: 20, EXAM: 20, VITALS: 20, LAB: 145, IMAGING: 280, ECG: 415, CARDIOLOGY: 415, INTERVENTION: 550, DIAGNOSIS: 550, REFERENCE: 280 } as Record<string, number>)[lane] ?? 280;
}

function shortNodeLabel(nodeType: TemporalGraphNode['node_type'], lane: string) {
  if (nodeType === 'ROOT') return 'T0';
  if (nodeType === 'CONTEXT') return 'S0';
  if (nodeType === 'REFERENCE') return 'GT';
  if (nodeType === 'ACTION') return 'ACT';
  if (nodeType === 'INTERVENTION') return 'TX';
  return ({ LAB: 'LAB', IMAGING: 'IMG', ECG: 'ECG', CARDIOLOGY: 'ECG', HISTORY: 'H', EXAM: 'EX' } as Record<string, string>)[lane] ?? 'RES';
}

function statusLabel(status: TrajectoryNodeStatus) {
  return ({ 'gt-only': '仅 GT', shared: '模型与 GT 重合', 'model-only': '仅模型轨迹', pending: '下单后未返回', reference: '回顾参考诊断', 'correct-final': '最终诊断命中' } as Record<TrajectoryNodeStatus, string>)[status];
}

function firstFinite(...values: unknown[]) {
  return values.find((value): value is number => typeof value === 'number' && Number.isFinite(value)) ?? 0;
}

function PanelTitle({ icon, kicker, title }: { icon: React.ReactNode; kicker: string; title: string }) { return <header className="model-panel-header"><span>{icon}</span><div><p>{kicker}</p><h2>{title}</h2></div></header>; }
function Json({ value }: { value: unknown }) { return <pre className="model-json-pane">{JSON.stringify(value ?? null, null, 2)}</pre>; }
function summarize(value: unknown) { const text = JSON.stringify(value); return text.length > 180 ? `${text.slice(0, 180)}…` : text; }
function summarizeEvent(event: TemporalEvent) { const result = event.result; const value = result.text ?? result.report_text ?? result.value ?? result.result; if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value); return summarize(value ?? result); }
function extractPrompt(payload: Record<string, unknown>) { const messages = payload.messages; if (!Array.isArray(messages)) return payload; const system = messages.find((item) => typeof item === 'object' && item !== null && (item as { role?: string }).role === 'system') as { content?: unknown } | undefined; const user = messages.find((item) => typeof item === 'object' && item !== null && (item as { role?: string }).role === 'user') as { content?: unknown } | undefined; let situation = user?.content; if (typeof situation === 'string') { try { situation = JSON.parse(situation); } catch { /* retain provider text */ } } return { model: payload.model, system_instruction: system?.content, situation }; }
function download(value: unknown, filename: string) { const blob = new Blob([JSON.stringify(value ?? null, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click(); URL.revokeObjectURL(url); }
