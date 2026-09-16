'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { AnimatePresence, motion } from 'motion/react';
import {
  ArrowLeft,
  Bot,
  BrainCircuit,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Code2,
  Database,
  FileJson2,
  FlaskConical,
  KeyRound,
  ListTree,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  Send,
  Sparkles,
  StepForward,
  Workflow,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  PatientPathTree,
  type PatientPathStep,
} from '@/features/arena/patient-path-tree';
import type { CaseSummary } from '@/features/arena/types';
import { DiagnosisReview } from '@/features/forest/diagnosis-review';
import { api } from '@/lib/api';
import type {
  ModelInteraction,
  ModelRunArtifact,
  ModelRunDetail,
  ModelRunSummary,
  OpenRouterModel,
  OpenRouterProvider,
  OpenRouterStatus,
} from './types';

const RESEARCH_KEY = 'local-research-only';

export function ModelArenaDashboard() {
  const [status, setStatus] = useState<OpenRouterStatus | null>(null);
  const [providers, setProviders] = useState<OpenRouterProvider[]>([]);
  const [models, setModels] = useState<OpenRouterModel[]>([]);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [providerId, setProviderId] = useState('');
  const [modelId, setModelId] = useState('');
  const [dataset, setDataset] = useState('DDXPlus');
  const [caseId, setCaseId] = useState('');
  const [modelQuery, setModelQuery] = useState('');
  const [detail, setDetail] = useState<ModelRunDetail | null>(null);
  const [activeRuns, setActiveRuns] = useState<ModelRunSummary[]>([]);
  const [selectedInteractionId, setSelectedInteractionId] = useState('');
  const [autoRun, setAutoRun] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('正在连接 OpenRouter 模型目录…');
  const requestLock = useRef(false);

  const headers = useMemo(
    () => ({ 'X-Research-Key': RESEARCH_KEY }),
    [],
  );

  useEffect(() => {
    let active = true;
    void Promise.all([
      api<OpenRouterStatus>('/model-arena/status', { headers }),
      api<{ providers: OpenRouterProvider[]; models: OpenRouterModel[] }>(
        '/model-arena/models',
        { headers },
      ),
      api<{ cases: CaseSummary[] }>('/cases'),
      api<{ runs: ModelRunSummary[] }>('/model-arena/runs', { headers }),
    ])
      .then(([nextStatus, catalog, caseCatalog, runIndex]) => {
        if (!active) return;
        setStatus(nextStatus);
        setProviders(catalog.providers);
        setModels(catalog.models);
        setCases(caseCatalog.cases);
        setActiveRuns(runIndex.runs.filter((item) => item.status === 'ACTIVE'));
        const preferred =
          catalog.providers.find((item) => item.id === 'openai') ??
          catalog.providers[0];
        setProviderId(preferred?.id ?? '');
        const firstModel = catalog.models.find(
          (item) => item.provider === preferred?.id,
        );
        setModelId(firstModel?.id ?? '');
        const firstCase =
          caseCatalog.cases.find((item) => item.dataset_name === 'DDXPlus') ??
          caseCatalog.cases[0];
        setDataset(firstCase?.dataset_name ?? 'DDXPlus');
        setCaseId(firstCase?.case_id ?? '');
        setNotice(
          nextStatus.configured
            ? ''
            : '后端未读取到 OPENROUTER_API_KEY，请检查项目 .env 或 tools/api_smoke/.env。',
        );
      })
      .catch((error: Error) => {
        if (active) setNotice(error.message);
      });
    return () => {
      active = false;
    };
  }, [headers]);

  const providerModels = useMemo(() => {
    const needle = modelQuery.trim().toLowerCase();
    return models.filter(
      (model) =>
        model.provider === providerId &&
        (!needle ||
          model.name.toLowerCase().includes(needle) ||
          model.id.toLowerCase().includes(needle)),
    );
  }, [modelQuery, models, providerId]);

  const datasetCases = useMemo(
    () => cases.filter((item) => item.dataset_name === dataset),
    [cases, dataset],
  );

  function chooseProvider(nextProvider: string) {
    setProviderId(nextProvider);
    setModelQuery('');
    setModelId(models.find((item) => item.provider === nextProvider)?.id ?? '');
  }

  function chooseDataset(nextDataset: string) {
    setDataset(nextDataset);
    setCaseId(
      cases.find((item) => item.dataset_name === nextDataset)?.case_id ?? '',
    );
  }

  async function startRun() {
    if (!modelId || !caseId || !status?.configured) return;
    setBusy(true);
    setNotice('');
    try {
      const result = await api<ModelRunDetail>('/model-arena/runs', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          model_id: modelId,
          case_id: caseId,
          max_questions: 30,
        }),
      });
      setDetail(result);
      setSelectedInteractionId('');
      setAutoRun(true);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '无法创建模型测试');
    } finally {
      setBusy(false);
    }
  }

  async function resumeRun(runId: string) {
    setBusy(true);
    setNotice('');
    try {
      const result = await api<ModelRunDetail>(`/model-arena/runs/${runId}`, {
        headers,
      });
      setDetail(result);
      setSelectedInteractionId(
        result.interactions.at(-1)?.interaction_id ?? '',
      );
      setAutoRun(false);
      setNotice(result.run.last_error ?? '');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '无法恢复未完成测试');
    } finally {
      setBusy(false);
    }
  }

  const stepRun = useCallback(async () => {
    if (!detail || detail.run.status !== 'ACTIVE' || requestLock.current)
      return;
    requestLock.current = true;
    setBusy(true);
    try {
      const result = await api<ModelRunDetail>(
        `/model-arena/runs/${detail.run.run_id}/step`,
        { method: 'POST', headers },
      );
      setDetail(result);
      const latest = result.interactions.at(-1);
      if (latest) setSelectedInteractionId(latest.interaction_id);
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
      } else {
        setNotice('');
      }
    } catch (error) {
      setAutoRun(false);
      setNotice(error instanceof Error ? error.message : '模型回合执行失败');
    } finally {
      requestLock.current = false;
      setBusy(false);
    }
  }, [detail, headers]);

  useEffect(() => {
    if (!autoRun || busy || !detail || detail.run.status !== 'ACTIVE') return;
    const timer = window.setTimeout(() => void stepRun(), 500);
    return () => window.clearTimeout(timer);
  }, [autoRun, busy, detail, stepRun]);

  function reset() {
    setAutoRun(false);
    setDetail(null);
    setSelectedInteractionId('');
    setNotice('');
  }

  if (!detail) {
    return (
      <ModelRunSetup
        activeRuns={activeRuns}
        busy={busy}
        caseId={caseId}
        dataset={dataset}
        datasetCases={datasetCases}
        modelId={modelId}
        modelQuery={modelQuery}
        notice={notice}
        onCaseChange={setCaseId}
        onDatasetChange={chooseDataset}
        onModelChange={setModelId}
        onModelQueryChange={setModelQuery}
        onProviderChange={chooseProvider}
        onResume={(runId) => void resumeRun(runId)}
        onStart={() => void startRun()}
        providerId={providerId}
        providerModels={providerModels}
        providers={providers}
        status={status}
      />
    );
  }

  if (detail.run.status === 'COMPLETED' && detail.review) {
    return (
      <main className="h-dvh overflow-hidden bg-[#020b12] text-slate-50">
        <DiagnosisReview
          extraAction={<InteractionArchive detail={detail} />}
          onDownloadArtifact={
            detail.artifact
              ? () => downloadModelArtifact(detail.artifact)
              : undefined
          }
          onNewCase={reset}
          review={detail.review}
        />
      </main>
    );
  }

  const selectedInteraction =
    detail.interactions.find(
      (item) => item.interaction_id === selectedInteractionId,
    ) ?? detail.interactions.at(-1);
  const path: PatientPathStep[] = detail.trajectory.slice(1).map((item) => ({
    evidence_id: item.evidence_id,
    evidence: item.question,
    answer: item.answer,
    status: item.status,
    domain: 'OBSERVATION',
    state_hash: item.state_hash,
  }));

  return (
    <main className="model-run-page">
      <header className="model-run-header">
        <Link href="/">
          <ArrowLeft /> 返回主页
        </Link>
        <span className="model-run-mark">
          <BrainCircuit />
        </span>
        <div className="min-w-0 flex-1">
          <p>OPENROUTER · AUTONOMOUS CLINICAL ARENA</p>
          <h1>{detail.run.model_id}</h1>
        </div>
        <div className="model-run-meter">
          <span>
            <b>{detail.state.question_count}</b> / {detail.run.max_questions}
          </span>
          <small>已询问 / 硬上限</small>
        </div>
        <Badge className={autoRun ? 'model-live-badge' : 'model-pause-badge'}>
          {busy ? '模型思考中' : autoRun ? '自动进行中' : '已暂停'}
        </Badge>
        <Button
          disabled={busy}
          onClick={() => setAutoRun((current) => !current)}
          size="sm"
          variant="outline"
        >
          {autoRun ? <Pause /> : <Play />}
          {autoRun ? '暂停' : '继续'}
        </Button>
        <Button disabled={busy || autoRun} onClick={() => void stepRun()} size="sm">
          <StepForward /> 单步
        </Button>
        <Button disabled={busy} onClick={reset} size="sm" variant="ghost">
          <RotateCcw /> New case
        </Button>
      </header>

      <section className="model-run-context-bar">
        <span>
          <Database /> {detail.run.dataset_name}
        </span>
        <span>
          <FlaskConical /> {detail.run.case_id}
        </span>
        <span>
          <Workflow /> 状态 S{detail.state.question_count}
        </span>
        <span>
          <ListTree /> {detail.conditions.length} 个候选结果
        </span>
        <i>问题、疾病 ID 及依赖规则由服务端逐轮验证</i>
      </section>

      <section className="model-run-grid">
        <article className="model-cockpit-panel model-path-panel">
          <PanelHeader
            icon={<ListTree />}
            kicker="LIVE PATIENT PATH"
            title="模型已获得的患者轨迹"
          />
          <PatientPathTree
            beliefSubmitted={!busy}
            key={path.length}
            path={path}
            state={detail.state}
          />
        </article>

        <article className="model-cockpit-panel model-round-panel">
          <PanelHeader
            icon={<BrainCircuit />}
            kicker="DECISION TIMELINE"
            title="每一轮的诊断排序与下一动作"
          />
          <div className="model-round-scroll">
            {!detail.interactions.length && (
              <div className="model-waiting-state">
                <span><Sparkles /></span>
                <h2>初始情况已封装为 JSON</h2>
                <p>模型将先提交 S0 候选诊断，再选择第一个可用问题。</p>
              </div>
            )}
            <AnimatePresence initial={false}>
              {detail.interactions.map((interaction) => (
                <RoundCard
                  conditions={detail.conditions}
                  interaction={interaction}
                  key={interaction.interaction_id}
                  onSelect={() =>
                    setSelectedInteractionId(interaction.interaction_id)
                  }
                  selected={
                    interaction.interaction_id === selectedInteraction?.interaction_id
                  }
                />
              ))}
            </AnimatePresence>
            {busy && <ThinkingCard modelId={detail.run.model_id} />}
          </div>
        </article>

        <article className="model-cockpit-panel model-inspector-panel">
          <PanelHeader
            icon={<Code2 />}
            kicker="ROUND INSPECTOR"
            title="Prompt · 原始响应 · 解析 · 执行"
          />
          <InteractionInspector interaction={selectedInteraction} />
        </article>
      </section>

      {notice && (
        <div className="model-run-toast" role="alert">
          <CircleAlert />
          <span>{notice}</span>
          {detail.run.last_error && (
            <Button disabled={busy} onClick={() => void stepRun()} size="sm">
              <RefreshCw /> 重试当前回合
            </Button>
          )}
        </div>
      )}
    </main>
  );
}

function trailingErrorCount(items: Array<{ error?: string | null }>) {
  let count = 0;
  for (let index = items.length - 1; index >= 0 && items[index]?.error; index -= 1) count += 1;
  return count;
}

function ModelRunSetup({
  activeRuns,
  busy,
  caseId,
  dataset,
  datasetCases,
  modelId,
  modelQuery,
  notice,
  onCaseChange,
  onDatasetChange,
  onModelChange,
  onModelQueryChange,
  onProviderChange,
  onResume,
  onStart,
  providerId,
  providerModels,
  providers,
  status,
}: {
  activeRuns: ModelRunSummary[];
  busy: boolean;
  caseId: string;
  dataset: string;
  datasetCases: CaseSummary[];
  modelId: string;
  modelQuery: string;
  notice: string;
  onCaseChange: (value: string) => void;
  onDatasetChange: (value: string) => void;
  onModelChange: (value: string) => void;
  onModelQueryChange: (value: string) => void;
  onProviderChange: (value: string) => void;
  onResume: (runId: string) => void;
  onStart: () => void;
  providerId: string;
  providerModels: OpenRouterModel[];
  providers: OpenRouterProvider[];
  status: OpenRouterStatus | null;
}) {
  return (
    <main className="model-setup-page">
      <header className="model-setup-header">
        <Link href="/">
          <ArrowLeft /> 返回主页
        </Link>
        <div>
          <p>CLINCFORESTBENCH · MODEL LAB</p>
          <h1>模型测试</h1>
        </div>
        <Link href="/model-arena?mode=temporal">
          <Clock3 /> Temporal 轨迹与评测
        </Link>
        <Badge className={status?.configured ? 'is-connected' : 'is-offline'}>
          <span /> OpenRouter {status?.configured ? '已连接' : '未配置'}
        </Badge>
      </header>

      <section className="model-setup-intro">
        <motion.div
          animate={{ rotate: 360 }}
          className="model-orbit-ring"
          transition={{ duration: 18, ease: 'linear', repeat: Infinity }}
        />
        <span className="model-setup-hero-icon"><BrainCircuit /></span>
        <div>
          <p>AUTONOMOUS DIAGNOSTIC SIMULATION</p>
          <h2>让模型在同一套临床规则下，自己走完一棵决策树。</h2>
          <small>
            每轮只接受一个结构化 JSON；不重复问题、不重复疾病，最多 30 次，可随时锁定唯一结果。
          </small>
        </div>
      </section>

      {activeRuns.length > 0 && (
        <section className="model-resume-strip">
          <span><RefreshCw /></span>
          <div>
            <b>发现 {activeRuns.length} 个未完成的模型测试</b>
            <small>
              {activeRuns[0].model_id} · {activeRuns[0].case_id} · S{activeRuns[0].question_count}
              {activeRuns[0].last_error ? ' · 上一回合需要重试' : ''}
            </small>
          </div>
          <Button disabled={busy} onClick={() => onResume(activeRuns[0].run_id)} size="sm">
            <Play /> 恢复测试
          </Button>
        </section>
      )}

      <section className="model-setup-grid">
        <article className="model-setup-card provider-card">
          <header><span>01</span><div><p>COMPANY</p><h3>选择模型公司</h3></div></header>
          <div className="provider-picker">
            {providers.map((provider) => (
              <button
                className={provider.id === providerId ? 'is-selected' : ''}
                key={provider.id}
                onClick={() => onProviderChange(provider.id)}
                type="button"
              >
                <span><Bot /></span>
                <b>{provider.name}</b>
                <small>{provider.model_count} models</small>
              </button>
            ))}
          </div>
        </article>

        <article className="model-setup-card model-picker-card">
          <header><span>02</span><div><p>MODEL</p><h3>选择 OpenRouter 模型</h3></div></header>
          <div className="model-search-box">
            <Search />
            <Input
              aria-label="搜索 OpenRouter 模型"
              onChange={(event) => onModelQueryChange(event.target.value)}
              placeholder="搜索模型名或 ID"
              value={modelQuery}
            />
          </div>
          <div className="openrouter-model-list">
            {providerModels.map((model) => (
              <button
                className={model.id === modelId ? 'is-selected' : ''}
                key={model.id}
                onClick={() => onModelChange(model.id)}
                type="button"
              >
                <span>{model.id === modelId ? <CheckCircle2 /> : <Bot />}</span>
                <div><b>{model.name}</b><small>{model.id}</small></div>
                {model.context_length && <em>{compactTokens(model.context_length)}</em>}
              </button>
            ))}
            {!providerModels.length && <p className="model-list-empty">没有匹配模型</p>}
          </div>
        </article>

        <article className="model-setup-card case-picker-card">
          <header><span>03</span><div><p>CLINICAL CASE</p><h3>选择数据集与病例</h3></div></header>
          <div className="model-dataset-picker">
            {['DDXPlus', 'Synthea', 'MedAgentBench'].map((name) => (
              <button
                className={dataset === name ? 'is-selected' : ''}
                key={name}
                onClick={() => onDatasetChange(name)}
                type="button"
              >
                <Database />
                <b>{name}</b>
                <small>{datasetCountLabel(name)}</small>
              </button>
            ))}
          </div>
          <label className="model-case-select">
            <span><FlaskConical /> Case</span>
            <select onChange={(event) => onCaseChange(event.target.value)} value={caseId}>
              {datasetCases.map((item) => (
                <option key={item.case_id} value={item.case_id}>
                  {item.case_id} · {item.action_count} actions
                </option>
              ))}
            </select>
          </label>
          <div className="model-rule-strip">
            <span><b>30</b><small>问题硬上限</small></span>
            <span><b>1 JSON</b><small>每轮唯一输出</small></span>
            <span><b>0</b><small>允许重复项</small></span>
          </div>
          <Button
            className="model-launch-button"
            disabled={busy || !modelId || !caseId || !status?.configured}
            onClick={onStart}
          >
            {busy ? <RefreshCw className="animate-spin" /> : <Send />}
            {busy ? '正在创建模型会话…' : '开始自动模拟'}
          </Button>
        </article>
      </section>

      {notice && <div className="model-setup-notice"><CircleAlert /> {notice}</div>}
      <footer className="model-setup-footer">
        <KeyRound /> API Key 只由后端从本地 .env 读取，不会发送给浏览器或写入回合记录。
      </footer>
    </main>
  );
}

function PanelHeader({ icon, kicker, title }: { icon: React.ReactNode; kicker: string; title: string }) {
  return <header className="model-panel-header"><span>{icon}</span><div><p>{kicker}</p><h2>{title}</h2></div></header>;
}

function RoundCard({
  conditions,
  interaction,
  onSelect,
  selected,
}: {
  conditions: Array<{ condition_id: string; name: string }>;
  interaction: ModelInteraction;
  onSelect: () => void;
  selected: boolean;
}) {
  const names = new Map(conditions.map((item) => [item.condition_id, item.name]));
  const decision = interaction.parsed_decision;
  const diagnosisIds = Array.isArray(decision?.diagnoses)
    ? decision.diagnoses
    : [];
  const applied = interaction.application_result ?? {};
  const stateStep = Number(applied.state_step ?? interaction.step - 1);
  return (
    <motion.button
      animate={{ opacity: 1, y: 0 }}
      className={`model-round-card ${selected ? 'is-selected' : ''} ${interaction.error ? 'has-error' : ''}`}
      initial={{ opacity: 0, y: 10 }}
      onClick={onSelect}
      type="button"
    >
      <span className="model-round-index">S{stateStep}</span>
      <div className="model-round-content">
        <header>
          <b>{interaction.error ? '回合校验失败' : decision?.final ? '模型锁定诊断' : '阶段性诊断已提交'}</b>
          <small><Clock3 /> {interaction.latency_ms ?? 0} ms</small>
        </header>
        {diagnosisIds.length > 0 && (
          <ol className="model-ranked-diagnoses">
            {diagnosisIds.map((id, index) => (
              <li key={id}><i>{index + 1}</i><span>{names.get(id) ?? id}<small>{id}</small></span></li>
            ))}
          </ol>
        )}
        {interaction.error ? (
          <p className="model-round-error"><CircleAlert /> {interaction.error}</p>
        ) : decision?.final ? (
          <p className="model-final-action"><CheckCircle2 /> Final · {names.get(decision.final_condition_id ?? '') ?? decision.final_condition_id}</p>
        ) : (
          <div className="model-question-action">
            <span><Send /></span>
            <div><small>NEXT QUESTION</small><b>{displayUnknown(applied.question ?? decision?.next_action_id ?? '—')}</b><em>{displayUnknown(applied.answer ?? '等待患者回答')}</em></div>
          </div>
        )}
      </div>
    </motion.button>
  );
}

function ThinkingCard({ modelId }: { modelId: string }) {
  return (
    <div className="model-thinking-card">
      <span><BrainCircuit /></span>
      <div><b>{modelId}</b><small>正在读取全量问题库与疾病库，生成下一轮 JSON…</small></div>
      <i /><i /><i />
    </div>
  );
}

function InteractionInspector({ interaction }: { interaction?: ModelInteraction }) {
  if (!interaction) {
    return <div className="model-inspector-empty"><FileJson2 /><b>等待第一轮</b><p>每轮的完整请求与响应会在这里可视化。</p></div>;
  }
  const situation = extractSituation(interaction.request_payload);
  return (
    <Tabs className="model-inspector-tabs" defaultValue="prompt" key={interaction.interaction_id}>
      <TabsList>
        <TabsTrigger value="prompt">Prompt JSON</TabsTrigger>
        <TabsTrigger value="response">原始响应</TabsTrigger>
        <TabsTrigger value="parsed">解析 JSON</TabsTrigger>
        <TabsTrigger value="applied">状态更新</TabsTrigger>
      </TabsList>
      <TabsContent value="prompt"><JsonPane value={situation} /></TabsContent>
      <TabsContent value="response"><JsonPane value={interaction.response_payload ?? interaction.assistant_content} /></TabsContent>
      <TabsContent value="parsed"><JsonPane value={interaction.parsed_decision} /></TabsContent>
      <TabsContent value="applied"><JsonPane value={interaction.application_result ?? { error: interaction.error }} /></TabsContent>
    </Tabs>
  );
}

function InteractionArchive({ detail }: { detail: ModelRunDetail }) {
  return (
    <Sheet>
      <SheetTrigger render={<Button variant="outline" />}>
        <FileJson2 /> 查看全部交互
      </SheetTrigger>
      <SheetContent className="model-archive-sheet sm:max-w-4xl">
        <SheetHeader>
          <SheetTitle>{detail.run.model_id} · 完整交互档案</SheetTitle>
          <SheetDescription>
            {detail.interactions.length} 轮 Prompt、OpenRouter 原始响应、解析 JSON 和状态更新。
          </SheetDescription>
        </SheetHeader>
        <div className="model-archive-scroll">
          {detail.interactions.map((interaction) => (
            <details key={interaction.interaction_id} open={interaction.step === 1}>
              <summary>
                <span>S{Number(interaction.application_result?.state_step ?? interaction.step - 1)}</span>
                <b>{interaction.parsed_decision?.final ? '最终提交' : interaction.parsed_decision?.next_action_id ?? '校验失败'}</b>
                <small>{interaction.latency_ms} ms</small>
              </summary>
              <InteractionInspector interaction={interaction} />
            </details>
          ))}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function JsonPane({ value }: { value: unknown }) {
  return <pre className="model-json-pane">{JSON.stringify(value ?? null, null, 2)}</pre>;
}

function extractSituation(payload: Record<string, unknown>) {
  const messages = payload.messages;
  if (!Array.isArray(messages)) return payload;
  const system = messages.find(
    (item) => typeof item === 'object' && item !== null && (item as { role?: string }).role === 'system',
  ) as { content?: unknown } | undefined;
  const user = messages.find(
    (item) => typeof item === 'object' && item !== null && (item as { role?: string }).role === 'user',
  ) as { content?: unknown } | undefined;
  let situation: unknown = user?.content;
  if (typeof situation === 'string') {
    try { situation = JSON.parse(situation); } catch { /* preserve provider text */ }
  }
  return {
    model: payload.model,
    temperature: payload.temperature,
    max_tokens: payload.max_tokens,
    system_instruction: system?.content,
    situation,
  };
}

function compactTokens(value: number) {
  if (value >= 1_000_000) return `${Math.round(value / 100_000) / 10}M`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}K`;
  return `${value}`;
}

function datasetCountLabel(name: string) {
  if (name === 'DDXPlus') return 'Diagnostic questioning';
  if (name === 'Synthea') return 'Clinical evidence';
  return 'FHIR workflow';
}

function displayUnknown(value: unknown) {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return `${value}`;
  return JSON.stringify(value);
}

function downloadModelArtifact(artifact: ModelRunArtifact | undefined) {
  if (!artifact) return;
  const blob = new Blob([JSON.stringify(artifact, null, 2)], {
    type: 'application/json',
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `model-arena-${artifact.model_run.case_id}-${artifact.model_run.run_id}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}
