'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { AnimatePresence, motion } from 'motion/react';
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  CircleAlert,
  Clock3,
  CornerDownRight,
  Database,
  FlaskConical,
  GitBranch,
  History,
  ListChecks,
  LockKeyhole,
  RotateCcw,
  Search,
  Stethoscope,
  UserRound,
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
import { BeliefEditor } from '@/features/belief/belief-editor';
import { AuthGate } from '@/features/auth/auth-gate';
import { useAuth } from '@/features/auth/auth-context';
import {
  PatientPathTree,
  type PatientPathStep,
} from '@/features/arena/patient-path-tree';
import { DiagnosisReview } from '@/features/forest/diagnosis-review';
import { api, eventId } from '@/lib/api';
import type {
  AvailableEvidence,
  BeliefSnapshotPayload,
  CaseSummary,
  Condition,
  Diagnosis,
  ObservationState,
  SessionArtifact,
  SessionReview,
} from './types';

const initialDiagnosisIds: string[] = [];

function displayValue(
  evidence: ObservationState['revealed_evidences'][number],
) {
  if (evidence.status === 'PRESENT') return 'Yes';
  if (evidence.status === 'ABSENT') return 'No';
  if (evidence.status === 'NOT_APPLICABLE') return 'Not applicable';
  if (evidence.status === 'DEFAULT') return 'No recorded value';
  if (evidence.values?.length) return evidence.values.join(', ');
  if (evidence.value == null) return evidence.status;
  if (typeof evidence.value === 'string') return evidence.value;
  if (typeof evidence.value === 'number' || typeof evidence.value === 'boolean')
    return `${evidence.value}`;
  return JSON.stringify(evidence.value);
}

export function ArenaShell() {
  const [sessionId, setSessionId] = useState('');
  const [state, setState] = useState<ObservationState | null>(null);
  const [conditions, setConditions] = useState<Condition[]>([]);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState('');
  const [available, setAvailable] = useState<AvailableEvidence[]>([]);
  const [diagnosisIds, setDiagnosisIds] =
    useState<string[]>(initialDiagnosisIds);
  const [beliefSubmitted, setBeliefSubmitted] = useState(false);
  const [beliefHistory, setBeliefHistory] = useState<BeliefSnapshotPayload[]>(
    [],
  );
  const [query, setQuery] = useState('');
  const [domain, setDomain] = useState('ALL');
  const [selected, setSelected] = useState<AvailableEvidence | null>(null);
  const [path, setPath] = useState<PatientPathStep[]>([]);
  const [latestAnswer, setLatestAnswer] = useState<PatientPathStep | null>(
    null,
  );
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [review, setReview] = useState<SessionReview | null>(null);
  const [artifact, setArtifact] = useState<SessionArtifact | null>(null);
  const { account, loading: authLoading } = useAuth();

  useEffect(() => {
    api<{ case_ids: string[]; cases: CaseSummary[] }>('/cases')
      .then((result) => {
        setCases(result.cases);
        setSelectedCaseId(
          (current) => current || result.case_ids[0] || '',
        );
      })
      .catch((error: Error) => setNotice(`API unavailable: ${error.message}`));
  }, []);

  useEffect(() => {
    if (!selectedCaseId) return;
    void api<{ conditions: Condition[] }>(
      `/cases/${selectedCaseId}/catalog`,
    )
      .then((catalog) => {
        setConditions(catalog.conditions);
        setDiagnosisIds([]);
      })
      .catch((error: Error) => setNotice(error.message));
  }, [selectedCaseId]);

  const caseSummary =
    cases.find((item) => item.case_id === (state?.case_id || selectedCaseId)) ??
    cases[0];
  const isWorkflow =
    (state?.case_type ?? caseSummary?.case_type) === 'WORKFLOW_FOREST';
  const beliefNoun = isWorkflow ? '工作流结果' : '诊断';
  const actionNoun =
    state?.dataset_name === 'DDXPlus' ? '问题' : '临床动作';

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return available.filter(
      (item) =>
        item.dependency_met &&
        (domain === 'ALL' || questionCategory(item) === domain) &&
        (!needle ||
          item.question_en.toLowerCase().includes(needle) ||
          item.evidence_id.toLowerCase().includes(needle) ||
          item.suggested_by.some((name) =>
            name.toLowerCase().includes(needle),
          )),
    );
  }, [available, domain, query]);

  const domains = useMemo(
    () => ['ALL', ...Array.from(new Set(available.map(questionCategory)))],
    [available],
  );

  async function refreshActions(id: string) {
    const result = await api<{ actions: AvailableEvidence[] }>(
      `/sessions/${id}/available-evidences`,
    );
    setAvailable(result.actions);
  }

  const start = useCallback(async () => {
    if (!account) return { status: 'failed', message: '请先登录医生账户' };
    setBusy(true);
    try {
      const caseCatalog = await api<{ conditions: Condition[] }>(
        `/cases/${selectedCaseId}/catalog`,
      );
      setConditions(caseCatalog.conditions);
      const result = await api<{
        session: { session_id: string };
        state: ObservationState;
      }>('/sessions', {
        method: 'POST',
        body: JSON.stringify({
          case_id: selectedCaseId || undefined,
          arena_mode: 'FREE_EXPLORATION',
          belief_capture_mode: 'EVERY_STEP',
        }),
      });
      setSessionId(result.session.session_id);
      setState(result.state);
      setPath([]);
      setAvailable([]);
      setLatestAnswer(null);
      setDiagnosisIds(initialDiagnosisIds);
      setBeliefSubmitted(false);
      setBeliefHistory([]);
      setCompleted(false);
      setReview(null);
      setArtifact(null);
      setSelected(null);
      setQuery('');
      setDomain('ALL');
      setNotice('');
      return { status: 'created', session_id: result.session.session_id };
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Unable to create session';
      setNotice(message);
      return { status: 'failed', message };
    } finally {
      setBusy(false);
    }
  }, [account, selectedCaseId]);

  useEffect(() => {
    const context = document.modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    void Promise.resolve(
      context.registerTool(
        {
          name: 'start_clinical_session',
          title: 'Start clinical session',
          description:
            'Create a deterministic multi-dataset clinical Arena session and show its initial path.',
          inputSchema: {
            type: 'object',
            properties: {},
            additionalProperties: false,
          },
          annotations: { readOnlyHint: false, untrustedContentHint: false },
          execute: async () => start(),
        },
        { signal: lifecycle.signal },
      ),
    ).catch(() => undefined);
    return () => lifecycle.abort();
  }, [start]);

  const belief = () => ({
    diagnoses: rankedDiagnoses(diagnosisIds),
    overall_confidence: 0,
  });

  async function submitBelief() {
    if (!sessionId) return;
    setBusy(true);
    try {
      const snapshot = await api<BeliefSnapshotPayload>(
        `/sessions/${sessionId}/beliefs`,
        {
          method: 'POST',
          body: JSON.stringify({
            belief: belief(),
            client_event_id: eventId(`belief-s${state?.question_count ?? 0}`),
          }),
        },
      );
      await refreshActions(sessionId);
      setBeliefHistory((current) => [...current, snapshot]);
      setBeliefSubmitted(true);
      setNotice('');
    } catch (error) {
      setNotice(
        error instanceof Error ? error.message : 'Belief was not saved',
      );
    } finally {
      setBusy(false);
    }
  }

  async function ask() {
    if (!sessionId || !selected) return;
    setBusy(true);
    try {
      const result = await api<{
        result_type: string;
        observation: ObservationState['revealed_evidences'][number] | null;
        answer_text: string | null;
        state: ObservationState;
        message: string;
      }>(`/sessions/${sessionId}/actions/evidence`, {
        method: 'POST',
        body: JSON.stringify({
          evidence_id: selected.evidence_id,
          client_event_id: eventId('ask'),
        }),
      });
      setState(result.state);
      if (result.observation && result.result_type === 'OBSERVATION') {
        const step = {
          evidence_id: selected.evidence_id,
          evidence: selected.question_en,
          answer: result.answer_text ?? displayValue(result.observation),
          status: result.observation.status,
          domain: selected.clinical_domain,
          state_hash: result.state.state_hash,
        };
        setPath((current) => [...current, step]);
        setLatestAnswer(step);
        setBeliefSubmitted(false);
        setAvailable([]);
      }
      setNotice(result.result_type === 'OBSERVATION' ? '' : result.message);
      setSelected(null);
      setQuery('');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Question failed');
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    if (!sessionId) return;
    setBusy(true);
    try {
      await api(`/sessions/${sessionId}/finalize`, {
        method: 'POST',
        body: JSON.stringify({
          belief: belief(),
          client_event_id: eventId('final'),
        }),
      });
      const [result, completedArtifact] = await Promise.all([
        api<SessionReview>(`/sessions/${sessionId}/review`),
        api<SessionArtifact>(`/sessions/${sessionId}/artifact`),
      ]);
      setReview(result);
      setArtifact(completedArtifact);
      setCompleted(true);
      downloadSessionArtifact(completedArtifact);
      setNotice('');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Finalize failed');
    } finally {
      setBusy(false);
    }
  }

  const stage = state?.question_count ?? 0;

  function resetToDatasetSelection() {
    setSessionId('');
    setState(null);
    setAvailable([]);
    setDiagnosisIds([]);
    setBeliefSubmitted(false);
    setBeliefHistory([]);
    setPath([]);
    setLatestAnswer(null);
    setSelected(null);
    setQuery('');
    setDomain('ALL');
    setCompleted(false);
    setReview(null);
    setArtifact(null);
    setNotice('');
  }

  function remindBeforeQuestion() {
    const message = `请先提交 S${stage} 阶段${beliefNoun}，再选择下一个${actionNoun}。`;
    setNotice(message);
    window.setTimeout(
      () => setNotice((current) => (current === message ? '' : current)),
      2_600,
    );
  }

  if (authLoading) {
    return <main className="auth-loading">正在读取医生账户…</main>;
  }

  if (!account) return <AuthGate />;

  if (!state && !completed) {
    return (
      <main className="arena-select-page h-dvh overflow-hidden bg-[#020b12]">
        <DatasetSelection
          busy={busy}
          cases={cases}
          onCaseChange={setSelectedCaseId}
          onStart={() => void start()}
          selectedCaseId={selectedCaseId}
        />
        {notice && (
          <div aria-live="polite" className="arena-toast">
            <span /> {notice}
          </div>
        )}
      </main>
    );
  }

  if (completed && review) {
    return (
      <main className="h-dvh overflow-hidden bg-[#020b12] text-slate-50">
        <DiagnosisReview
          onDownloadArtifact={
            artifact ? () => downloadSessionArtifact(artifact) : undefined
          }
          onNewCase={resetToDatasetSelection}
          review={review}
        />
      </main>
    );
  }

  return (
    <main className="arena-shell h-dvh overflow-hidden bg-[#eaf1f3] text-slate-950">
      <header className="arena-main-header border-b border-cyan-900/50 bg-[#061d2a] text-white shadow-lg shadow-slate-950/10">
        <div className="mx-auto flex max-w-[1720px] items-center justify-between px-4 py-2.5 lg:px-5">
          <div className="flex items-center gap-3">
            <Link
              className="arena-home-link"
              href="/"
            >
              <ArrowLeft /> 返回主页
            </Link>
            <span className="brand-mark">
              <Activity />
            </span>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">
                ClincForestBench
              </p>
              <h1 className="text-lg font-semibold tracking-tight">
                {state?.dataset_name} · Clinical Decision Arena
              </h1>
            </div>
          </div>
          <Button
            className="arena-new-case-button"
            disabled={busy}
            onClick={resetToDatasetSelection}
            size="sm"
            type="button"
          >
            <RotateCcw /> New case
          </Button>
        </div>
      </header>

      <div className="arena-layout">
        <aside className="clinical-panel arena-column">
          <PanelTitle
            icon={<History />}
            eyebrow="Patient path tree"
            title={
              isWorkflow
                ? 'Live workflow trajectory'
                : 'Live diagnostic trajectory'
            }
          />
          {state ? (
            <PatientPathTree
              beliefSubmitted={beliefSubmitted}
              key={path.length}
              path={path}
              state={state}
            />
          ) : (
            <EmptyCopy text="Start a case. Every question, answer and diagnosis checkpoint will appear here in order." />
          )}
        </aside>

        <section className="clinical-panel arena-column">
          <PanelTitle
            icon={<Stethoscope />}
            eyebrow={`Clinical interaction · S${stage}`}
            title={`Choose the next ${actionNoun}`}
          />
          <div className="arena-center-body p-3">
            <AnimatePresence mode="popLayout">
              {latestAnswer && (
                <motion.div
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  className="answer-reveal"
                  exit={{ opacity: 0, y: -8, scale: 0.98 }}
                  initial={{ opacity: 0, y: -12, scale: 0.98 }}
                  key={`${stage}-${latestAnswer.evidence}`}
                >
                  <span className="answer-pulse" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-cyan-900">Latest observation</p>
                    <p className="mt-0.5 font-semibold text-slate-950">
                      {latestAnswer.evidence}
                    </p>
                  </div>
                  <Badge className={answerClass(latestAnswer.status)}>
                    {latestAnswer.answer}
                  </Badge>
                </motion.div>
              )}
            </AnimatePresence>

            {!beliefSubmitted && (
              <div className="arena-stage-guide is-locked">
                <LockKeyhole />
                <div>
                  <p className="font-semibold">
                    S{stage} {beliefNoun} is required
                  </p>
                  <p>
                    每次获得新信息后，先提交当前判断，才能继续下一步。
                  </p>
                </div>
              </div>
            )}

            <div className="arena-evidence-filters flex flex-col gap-2 sm:flex-row">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-3 size-4 text-slate-400" />
                <Input
                  aria-label="Search clinical actions"
                  className="h-8 pl-9 text-xs"
                  disabled={!beliefSubmitted || completed}
                  onChange={(event) => {
                    setQuery(event.target.value);
                    setSelected(null);
                  }}
                  placeholder={`搜索${actionNoun}、编号或关键词…`}
                  value={query}
                />
              </div>
              <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5">
                {domains.map((value) => (
                  <button
                    className={`rounded-md px-2 py-1 text-xs font-medium transition ${domain === value ? 'bg-white text-cyan-800 shadow-sm' : 'text-slate-500 hover:text-slate-900'}`}
                    key={value}
                    onClick={() => setDomain(value)}
                    type="button"
                  >
                    {categoryLabel(value)}
                  </button>
                ))}
              </div>
            </div>

            <div className="evidence-picker-grid mt-2 min-h-0 flex-1">
              {!beliefSubmitted && (
                <button
                  className="question-gate-trigger"
                  onClick={remindBeforeQuestion}
                  type="button"
                >
                  <LockKeyhole /> 选择下一个{actionNoun}
                </button>
              )}
              {filtered.map((item, index) => (
                <motion.button
                  animate={{ opacity: 1, y: 0 }}
                  className={`evidence-choice evidence-${questionCategory(item).toLowerCase().replace('_', '-')} ${selected?.evidence_id === item.evidence_id ? 'is-selected' : ''}`}
                  disabled={!item.dependency_met}
                  initial={{ opacity: 0, y: 6 }}
                  key={item.evidence_id}
                  layout
                  onClick={() => {
                    if (!beliefSubmitted) {
                      remindBeforeQuestion();
                      return;
                    }
                    setNotice('');
                    setSelected(item);
                  }}
                  transition={{ delay: Math.min(index * 0.025, 0.2) }}
                  type="button"
                  whileTap={{ scale: 0.99 }}
                >
                  <span className="evidence-choice-head">
                    <span className="evidence-choice-icon">
                      {questionCategory(item) === 'ANTECEDENT' ? (
                        <History />
                      ) : (
                        <CircleDot />
                      )}
                    </span>
                    <em>{questionCategoryLabel(item)}</em>
                    <code>{item.evidence_id}</code>
                  </span>
                  <b>{item.question_en}</b>
                  {item.parent_question_en && (
                    <span
                      className="evidence-parent-question"
                      title={item.parent_question_en}
                    >
                      <CornerDownRight />
                      <span>前置动作：{item.parent_question_en}</span>
                    </span>
                  )}
                  <span className="evidence-choice-foot">
                    <ChevronRight />
                  </span>
                </motion.button>
              ))}
              {beliefSubmitted && filtered.length === 0 && (
                <div className="grid min-h-48 place-items-center rounded-xl border border-dashed border-slate-300 text-center text-sm text-slate-500">
                  No available actions match this filter.
                  <br />
                  尝试其他关键词或动作分类。
                </div>
              )}
              {!state && (
                <div className="grid min-h-48 place-items-center rounded-xl border border-dashed border-slate-300 text-sm text-slate-400">
                  Clinical actions will appear after the case starts.
                </div>
              )}
            </div>
            <div className="sticky bottom-0 mt-2 border-t border-slate-200 bg-white/95 pt-2 backdrop-blur">
              <Button
                className="h-9 w-full bg-cyan-800 text-sm text-white shadow-lg shadow-cyan-900/10 hover:bg-cyan-700"
                disabled={!selected || busy || completed || !beliefSubmitted}
                onClick={ask}
              >
                执行所选{actionNoun} <ArrowRight />
              </Button>
            </div>
          </div>
        </section>

        <aside className="clinical-panel arena-column">
          <PanelTitle
            action={
              <ArenaGuide
                datasetName={state?.dataset_name ?? caseSummary?.dataset_name}
                isWorkflow={isWorkflow}
              />
            }
            icon={<FlaskConical />}
            eyebrow={`Belief checkpoint · S${stage}`}
            title={`What is your ${beliefNoun} now?`}
          />
          <div className="arena-diagnosis-body">
            <BeliefEditor
              conditions={conditions}
              disabled={!state || busy || completed || beliefSubmitted}
              history={
                <BeliefHistory
                  conditions={conditions}
                  snapshots={beliefHistory}
                />
              }
              key={sessionId}
              noun={isWorkflow ? '结果' : '疾病'}
              onSelectedIds={setDiagnosisIds}
              onSubmit={submitBelief}
              selectedIds={diagnosisIds}
              submitLabel={
                beliefSubmitted
                  ? `S${stage} ${beliefNoun}已提交`
                  : `提交 S${stage} 阶段${beliefNoun}`
              }
            />
            <div className="arena-final-diagnosis">
              <Button
                disabled={!beliefSubmitted || busy || completed}
                onClick={finish}
                variant="outline"
              >
                <CheckCircle2 /> 锁定最终{beliefNoun}
              </Button>
            </div>
          </div>
        </aside>
      </div>

      {notice && (
        <div aria-live="polite" className="arena-toast">
          <span /> {notice}
        </div>
      )}
    </main>
  );
}

function PanelTitle({
  icon,
  eyebrow,
  title,
  action,
}: {
  icon: React.ReactNode;
  eyebrow: string;
  title: string;
  action?: React.ReactNode;
}) {
  return (
    <header className="flex items-center gap-2 border-b border-slate-200 bg-white px-3 py-2.5">
      <span className="grid size-8 place-items-center rounded-lg bg-cyan-950 text-cyan-200 [&_svg]:size-4">
        {icon}
      </span>
      <div>
        <p className="text-[11px] font-bold uppercase tracking-[0.11em] text-cyan-700">
          {eyebrow}
        </p>
        <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
      </div>
      {action && <div className="ml-auto">{action}</div>}
    </header>
  );
}

function DatasetSelection({
  busy,
  cases,
  selectedCaseId,
  onCaseChange,
  onStart,
}: {
  busy: boolean;
  cases: CaseSummary[];
  selectedCaseId: string;
  onCaseChange: (caseId: string) => void;
  onStart: () => void;
}) {
  const selectedCase = cases.find((item) => item.case_id === selectedCaseId);
  const selectedDataset = selectedCase?.dataset_name ?? 'DDXPlus';
  const visibleCases = cases.filter(
    (item) => item.dataset_name === selectedDataset,
  );
  const tracks = [
    {
      name: 'DDXPlus' as const,
      eyebrow: 'DIAGNOSTIC QUESTIONING',
      title: '症状问询森林',
      description:
        '从 223 个 Evidence 中选择问题；命中证据返回 Yes，其余返回 No，逐轮维护鉴别诊断。',
      action: '问症状、病史与细节',
      outcome: '疾病鉴别诊断排序',
      icon: <Stethoscope />,
    },
    {
      name: 'Synthea' as const,
      eyebrow: 'EVIDENCE ACQUISITION',
      title: '纵向 EHR 证据森林',
      description:
        '从一次 index encounter 出发，按依赖查看真实导出的指标、检验、操作与用药记录。',
      action: '查看结构化临床记录',
      outcome: '参考疾病排序',
      icon: <Database />,
    },
    {
      name: 'MedAgentBench' as const,
      eyebrow: 'FHIR WORKFLOW',
      title: '临床行动森林',
      description:
        '完成患者解析、FHIR 查询、结果校验或医嘱创建流程；当前 MVP 忠实离线回放任务规则。',
      action: 'FHIR 查询与工作流动作',
      outcome: '工作流结果排序',
      icon: <GitBranch />,
    },
  ];

  function selectDataset(name: CaseSummary['dataset_name']) {
    const first = cases.find((item) => item.dataset_name === name);
    if (first) onCaseChange(first.case_id);
  }

  return (
    <section className="arena-dataset-select">
      <header>
        <Link href="/">
          <ArrowLeft /> 返回主页
        </Link>
        <div>
          <p>ClincForestBench · Arena tracks</p>
          <h1>选择一种病例森林</h1>
          <span>三类数据，共用逐步暴露、阶段提交和路径对比规则。</span>
        </div>
        <Badge>{cases.length || 130} VERSIONED CASES</Badge>
      </header>

      <div className="arena-track-grid">
        {tracks.map((track, index) => {
          const active = selectedDataset === track.name;
          const count = cases.filter(
            (item) => item.dataset_name === track.name,
          ).length;
          return (
            <motion.button
              animate={{ opacity: 1, y: 0 }}
              aria-pressed={active}
              className={`arena-track-card track-${track.name.toLowerCase()} ${active ? 'is-selected' : ''}`}
              initial={{ opacity: 0, y: 16 }}
              key={track.name}
              onClick={() => selectDataset(track.name)}
              transition={{ delay: index * 0.08 }}
              type="button"
              whileHover={{ y: -5 }}
            >
              <span className="arena-track-icon">{track.icon}</span>
              <span className="arena-track-count">{count || '—'} CASES</span>
              <small>{track.eyebrow}</small>
              <h2>{track.name}</h2>
              <h3>{track.title}</h3>
              <p>{track.description}</p>
              <dl>
                <div>
                  <dt>你的动作</dt>
                  <dd>{track.action}</dd>
                </div>
                <div>
                  <dt>阶段判断</dt>
                  <dd>{track.outcome}</dd>
                </div>
              </dl>
              <span className="arena-track-select">
                {active ? <CheckCircle2 /> : <CircleDot />}
                {active ? '已选择' : '选择此数据集'}
              </span>
            </motion.button>
          );
        })}
        <motion.div
          animate={{ opacity: 1, y: 0 }}
          className="arena-track-card track-temporal"
          initial={{ opacity: 0, y: 16 }}
          transition={{ delay: 0.24 }}
          whileHover={{ y: -5 }}
        >
          <span className="arena-track-icon"><Activity /></span>
          <span className="arena-track-count">40 CASES</span>
          <small>TIME-AWARE DECISION MAKING</small>
          <h2>Temporal v2</h2>
          <h3>真实时间动态诊断森林</h3>
          <p>选择检查、形成 pending、等待真实记录结果，再逐轮更新诊断；包含 MIMIC、MC-MED、eICU、PMC 与 NEJM CPC。</p>
          <dl>
            <div><dt>你的动作</dt><dd>下单、并行检查与等待</dd></div>
            <div><dt>阶段判断</dt><dd>每次结果后的诊断排序</dd></div>
          </dl>
          <Link className="arena-track-select" href="/temporal?mode=arena">
            <Clock3 />进入时间 Arena
          </Link>
        </motion.div>
      </div>

      <footer className="arena-case-launcher">
        <div>
          <span>当前数据集</span>
          <b>{selectedDataset}</b>
        </div>
        <label>
          <span>选择具体病例</span>
          <select
            aria-label="选择具体病例"
            disabled={busy || !visibleCases.length}
            onChange={(event) => onCaseChange(event.target.value)}
            value={selectedCaseId}
          >
            {visibleCases.map((item) => (
              <option key={item.case_id} value={item.case_id}>
                {item.case_id} · {item.action_count} actions
              </option>
            ))}
          </select>
        </label>
        <Button disabled={busy || !selectedCaseId} onClick={onStart}>
          {busy ? '正在准备病例…' : '进入这个 Arena'} <ArrowRight />
        </Button>
      </footer>
    </section>
  );
}

function ArenaGuide({
  isWorkflow,
  datasetName,
}: {
  isWorkflow: boolean;
  datasetName?: CaseSummary['dataset_name'];
}) {
  const datasetRule =
    datasetName === 'DDXPlus'
      ? 'DDXPlus：候选池来自完整 223 项 Evidence；病例命中的证据为 Yes，未命中为 No，子问题仅在父问题询问后开放。'
      : datasetName === 'Synthea'
        ? 'Synthea：动作只会展示本次 index encounter 中存在的结构化原始记录；查看结果不代表重新开立检查或重建临床时间线。'
        : 'MedAgentBench：当前是 OFFLINE_TASK_REPLAY，只复现官方任务与函数调用路径；无 FHIR 服务时不会伪造化验值、响应或新建资源。';
  const guideDescription =
    datasetName === 'DDXPlus'
      ? '逐轮选择问诊问题，并在每个患者回答后更新鉴别诊断。'
      : datasetName === 'Synthea'
        ? '逐轮查看 index encounter 的结构化临床记录，并更新当前疾病判断。'
        : isWorkflow
          ? '逐轮执行 FHIR 工作流动作，并在每个状态提交当前结果判断。'
          : '逐轮获取信息并提交当前判断。';
  return (
    <Sheet>
      <SheetTrigger
        render={
          <Button className="arena-guide-trigger" size="xs" variant="outline" />
        }
      >
        <BookOpen /> 玩法与规则
      </SheetTrigger>
      <SheetContent className="arena-guide-sheet" side="right">
        <SheetHeader>
          <SheetTitle>Clinical Decision Arena</SheetTitle>
          <SheetDescription>{guideDescription}</SheetDescription>
        </SheetHeader>
        <div className="arena-guide-body">
          <GuideSection icon={<ListChecks />} title="游玩流程">
            <ol>
              <li>阅读左侧患者初始信息。</li>
              <li>从候选池选择并排序当前判断，提交 S0。</li>
              <li>选择一个当前可用的临床动作，查看返回信息。</li>
              <li>每次得到新信息后提交下一轮判断；不变也可直接提交。</li>
              <li>锁定最终结果后，对比个人路径、群体树和 Ground Truth。</li>
            </ol>
          </GuideSection>
          <GuideSection icon={<Stethoscope />} title="Arena 规则">
            <ul>
              <li>候选列表的上下顺序代表当前优先级。</li>
              <li>无需输入概率；系统只记录选择、排序和删除。</li>
              <li>每个动作返回之后，必须先提交阶段判断才能继续。</li>
              <li>依赖动作只有在前置动作执行后才会出现在动作池。</li>
              <li>病例进行中不会显示 Ground Truth。</li>
              <li>{datasetRule}</li>
            </ul>
          </GuideSection>
          <GuideSection icon={<CircleAlert />} title="注意事项">
            <ul>
              <li>“全部加入”会加入当前搜索结果，可继续拖动排序或删除。</li>
              <li>New case 会回到数据集选择，并开始一条新的决策路径。</li>
              <li>只有完成并锁定最终结果的病例才会进入个人决策历史。</li>
            </ul>
          </GuideSection>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function GuideSection({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="arena-guide-section">
      <header>
        <span>{icon}</span>
        <h3>{title}</h3>
      </header>
      {children}
    </section>
  );
}

function BeliefHistory({
  snapshots,
  conditions,
}: {
  snapshots: BeliefSnapshotPayload[];
  conditions: Condition[];
}) {
  const conditionNames = new Map(
    conditions.map((item) => [item.condition_id, item.name]),
  );
  return (
    <details className="belief-history">
      <summary>
        <span>历史提交</span>
        <b>{snapshots.length}</b>
        <small>{snapshots.length ? '展开查看各阶段判断' : '尚未提交'}</small>
      </summary>
      <div>
        {snapshots.map((snapshot) => (
          <article key={snapshot.belief_id}>
            <span>S{snapshot.step}</span>
            <ol>
              {[...snapshot.belief.diagnoses]
                .sort((left, right) => left.rank - right.rank)
                .map((diagnosis) => (
                  <li key={diagnosis.condition_id}>
                    <i>{diagnosis.rank}</i>
                    {conditionNames.get(diagnosis.condition_id) ??
                      diagnosis.condition_id}
                  </li>
                ))}
            </ol>
          </article>
        ))}
        {!snapshots.length && <p>提交阶段诊断后会记录在这里。</p>}
      </div>
    </details>
  );
}

function rankedDiagnoses(conditionIds: string[]): Diagnosis[] {
  const totalWeight = (conditionIds.length * (conditionIds.length + 1)) / 2;
  return conditionIds.map((conditionId, index) => ({
    condition_id: conditionId,
    rank: index + 1,
    probability: Number(
      ((conditionIds.length - index) / totalWeight).toFixed(6),
    ),
  }));
}

function downloadSessionArtifact(artifact: SessionArtifact) {
  const payload = JSON.stringify(artifact, null, 2);
  const url = URL.createObjectURL(
    new Blob([payload], { type: 'application/json;charset=utf-8' }),
  );
  const anchor = document.createElement('a');
  const safeCaseId = artifact.session.case_id.replace(/[^a-zA-Z0-9_-]/g, '-');
  anchor.href = url;
  anchor.download = `ClincForestBench_${safeCaseId}_${artifact.session.session_id.slice(0, 8)}.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

function questionCategory(
  evidence: AvailableEvidence,
): string {
  if (evidence.clinical_domain !== 'SYMPTOM') {
    return evidence.clinical_domain;
  }
  if (evidence.semantic_role === 'SYMPTOM_ATTRIBUTE')
    return 'SYMPTOM_ATTRIBUTE';
  return 'PRESENTING_SYMPTOM';
}

function questionCategoryLabel(evidence: AvailableEvidence) {
  return categoryLabel(questionCategory(evidence));
}

function categoryLabel(category: string) {
  const labels: Record<string, string> = {
    ALL: '全部',
    PRESENTING_SYMPTOM: '症状',
    SYMPTOM_ATTRIBUTE: '症状细节',
    SYMPTOM: '症状',
    ANTECEDENT: '病史',
    OBSERVATION: '检查/指标',
    PROCEDURE: '操作',
    MEDICATION: '用药',
    PATIENT: '患者检索',
    WORKFLOW: '判断',
    SERVICEREQUEST: '转诊医嘱',
    MEDICATIONREQUEST: '用药医嘱',
  };
  return labels[category] ?? category.replaceAll('_', ' ').toLowerCase();
}

function answerClass(status: string) {
  if (status === 'PRESENT' || status === 'VALUE')
    return 'bg-cyan-50 text-cyan-800';
  if (status === 'ABSENT') return 'bg-slate-100 text-slate-600';
  return 'bg-amber-50 text-amber-800';
}

function EmptyCopy({ text }: { text: string }) {
  return (
    <div className="grid min-h-80 place-items-center p-8 text-center">
      <div>
        <UserRound className="mx-auto mb-3 size-7 text-slate-300" />
        <p className="max-w-64 text-sm leading-6 text-slate-500">{text}</p>
      </div>
    </div>
  );
}
