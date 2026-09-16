'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import NextImage from 'next/image';
import { AnimatePresence, motion } from 'motion/react';
import {
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Beaker,
  CheckCircle2,
  Clock3,
  FileText,
  HeartPulse,
  History,
  Image as ImageIcon,
  ListOrdered,
  Play,
  Search,
  Stethoscope,
  Trash2,
} from 'lucide-react';
import { AuthGate } from '@/features/auth/auth-gate';
import { useAuth } from '@/features/auth/auth-context';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { API_BASE, api } from '@/lib/api';
import { useLanguage } from '@/features/i18n/language-context';
import type {
  ClinicalPresentation,
  TemporalArenaCase,
  TemporalArenaIndex,
  TemporalArenaReview,
  TemporalArenaState,
  TemporalEvent,
} from './types';

type ArenaResponse = TemporalArenaState & {
  last_action_outcome?: {
    status: string;
    message?: string;
    clinical_message?: string;
    expected_available_game_time?: number | null;
  };
};

export function TemporalArena() {
  const { isChinese } = useLanguage();
  const { account, loading } = useAuth();
  const [index, setIndex] = useState<TemporalArenaIndex | null>(null);
  const [dataset, setDataset] = useState('');
  const [caseId, setCaseId] = useState('');
  const [state, setState] = useState<TemporalArenaState | null>(null);
  const [review, setReview] = useState<TemporalArenaReview | null>(null);
  const [diagnoses, setDiagnoses] = useState<string[]>([]);
  const [diagnosisQuery, setDiagnosisQuery] = useState('');
  const [actionQuery, setActionQuery] = useState('');
  const [selectedAction, setSelectedAction] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [draggedDiagnosis, setDraggedDiagnosis] = useState<number | null>(null);

  useEffect(() => {
    void api<TemporalArenaIndex>('/temporal/cases')
      .then((result) => {
        setIndex(result);
        const requested = new URLSearchParams(window.location.search).get('case');
        const first = result.cases.find((item) => item.case_id === requested) ?? result.cases[0];
        if (first) {
          setDataset(first.dataset_name);
          setCaseId(first.case_id);
        }
      })
      .catch((error: Error) => setNotice(error.message));
  }, []);

  const datasetCases = useMemo(
    () => (index?.cases ?? []).filter((item) => item.dataset_name === dataset),
    [dataset, index],
  );

  async function mutate(path: string, body?: unknown) {
    if (!state) return;
    const previousTime = state.current_time_min;
    setBusy(true);
    try {
      const next = await api<ArenaResponse>(path, {
        method: 'POST',
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      setState(next);
      if (next.last_action_outcome?.status === 'UNOBSERVED') {
        setNotice(next.last_action_outcome.clinical_message ?? (isChinese ? '本次真实就诊没有该项记录，不能当作阴性结果。' : 'This encounter has no record of that action; absence is not a negative result.'));
      } else if (next.last_action_outcome?.status === 'AVAILABLE') {
        const nextTime = next.last_action_outcome.expected_available_game_time ?? next.current_time_min;
        setNotice(isChinese ? `结果已立即返回；模拟时钟 ${formatArenaTime(previousTime)} → ${formatArenaTime(nextTime)}，无需现实等待。` : `Result returned; simulation clock ${formatArenaTime(previousTime)} → ${formatArenaTime(nextTime)}.`);
      } else {
        setNotice('');
      }
      setSelectedAction('');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : (isChinese ? '操作失败' : 'Action failed'));
    } finally {
      setBusy(false);
    }
  }

  async function start() {
    if (!caseId) return;
    setBusy(true);
    try {
      const next = await api<TemporalArenaState>('/temporal/sessions', {
        method: 'POST',
        body: JSON.stringify({ case_id: caseId }),
      });
      setState(next);
      setReview(null);
      setDiagnoses([]);
      setNotice(isChinese ? '先根据自然语言病情提交 S0；选择问询、查体或检查后，模拟时钟会自动推进并立即显示结果。' : 'Submit S0 from the initial presentation, then choose a question, exam, or test. The simulation clock advances automatically.');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : (isChinese ? '无法开始 Case' : 'Unable to start case'));
    } finally {
      setBusy(false);
    }
  }

  async function finalize() {
    if (!state) return;
    setBusy(true);
    try {
      const result = await api<TemporalArenaReview>(
        `/temporal/sessions/${state.session_id}/finalize`,
        { method: 'POST', body: JSON.stringify({ diagnoses }) },
      );
      setReview(result);
      setNotice(isChinese ? 'Case 已结束：reference 与群体统计现已解锁。' : 'Case complete: reference and cohort statistics are unlocked.');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : (isChinese ? '无法结束 Case' : 'Unable to finalize case'));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <main className="auth-loading">{isChinese ? '正在读取医生账户…' : 'Loading clinician account…'}</main>;
  if (!account) return <AuthGate />;
  if (review) {
    return (
      <TemporalResultReview
        onNewCase={() => {
          setState(null);
          setReview(null);
          setDiagnoses([]);
        }}
        review={review}
      />
    );
  }
  if (!state) {
    return (
      <TemporalArenaLauncher
        busy={busy}
        caseId={caseId}
        cases={datasetCases}
        dataset={dataset}
        index={index}
        notice={notice}
        onCase={setCaseId}
        onDataset={(value) => {
          setDataset(value);
          setCaseId(index?.cases.find((item) => item.dataset_name === value)?.case_id ?? '');
        }}
        onStart={() => void start()}
      />
    );
  }

  const filteredActions = state.available_actions.filter((item) => {
    const needle = actionQuery.trim().toLowerCase();
    return !needle || `${item.display} ${item.action_id} ${item.modality}`.toLowerCase().includes(needle);
  });
  const filteredDiagnoses = state.diagnosis_catalog
    .filter((item) => !diagnoses.includes(item))
    .filter((item) => item.toLowerCase().includes(diagnosisQuery.trim().toLowerCase()))
    .slice(0, 30);

  function addDiagnosis(value: string) {
    const label = value.trim();
    if (!label || diagnoses.some((item) => item.toLowerCase() === label.toLowerCase())) return;
    setDiagnoses((current) => [...current, label]);
    setDiagnosisQuery('');
  }

  function moveDiagnosis(from: number, to: number) {
    if (to < 0 || to >= diagnoses.length || from === to) return;
    setDiagnoses((current) => {
      const next = [...current];
      const [item] = next.splice(from, 1);
      next.splice(to, 0, item);
      return next;
    });
  }

  return (
    <main className="temporal-arena-page">
      <header className="temporal-arena-header">
        <Link href="/"><ArrowLeft />{isChinese ? '主页' : 'Home'}</Link>
        <div><small>Temporal doctor Arena</small><b>{state.dataset_name} · {state.case_id}</b></div>
        <span><Clock3 />{formatArenaTime(state.current_time_min)} · S{state.checkpoint}</span>
        <Button onClick={() => setState(null)} size="sm" variant="outline">{isChinese ? '换一个 Case' : 'Change case'}</Button>
      </header>

      <section className="temporal-arena-grid">
        <article className="temporal-arena-panel path-panel">
          <PanelHeader icon={<History />} kicker="YOUR PATH" title={isChinese ? '医生决策生长树' : 'Clinician decision tree'} />
          <DoctorPath state={state} />
        </article>

        <article className="temporal-arena-panel action-panel">
          <PanelHeader icon={<HeartPulse />} kicker={`STATE S${state.checkpoint}`} title={isChinese ? '病人信息与下一步动作' : 'Patient information and next action'} />
          <div className="temporal-state-scroll">
            <ResultCard presentation={state.initial_presentation} title={isChinese ? 'T0 初始病情' : 'T0 initial presentation'} />
            <AnimatePresence initial={false}>
              {state.revealed_events.map((event) => (
                <motion.div animate={{ opacity: 1, y: 0 }} initial={{ opacity: 0, y: 10 }} key={event.event_id}>
                  <ClinicalEventCard event={event} />
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
          <div className="temporal-action-dock">
            <div className="temporal-action-search">
              <Search /><Input onChange={(event) => setActionQuery(event.target.value)} placeholder={isChinese ? '搜索问询、查体、检验或影像…' : 'Search questions, exams, labs, or imaging…'} value={actionQuery} />
            </div>
            <div className="temporal-action-pool">
              {filteredActions.map((item) => (
                <button className={`modality-${item.modality.toLowerCase()} ${selectedAction === item.action_id ? 'is-selected' : ''}`} key={item.action_id} onClick={() => setSelectedAction(item.action_id)} type="button">
                  {modalityIcon(item.modality)}<span><b>{item.display}</b><small>{item.interaction_label} · {item.modality_label}</small></span>
                </button>
              ))}
            </div>
            <div className="temporal-action-buttons">
              <Button disabled={!selectedAction || busy || state.belief_required} onClick={() => void mutate(`/temporal/sessions/${state.session_id}/order`, { action_id: selectedAction })}>
                {isChinese ? '执行所选临床动作' : 'Perform selected action'} <ArrowRight />
              </Button>
              <span><Clock3 />{isChinese ? '自动推进模拟时间，结果当场显示' : 'Simulation time advances and results appear immediately'}</span>
            </div>
          </div>
        </article>

        <aside className="temporal-arena-panel belief-panel">
          <PanelHeader icon={<Stethoscope />} kicker={`BELIEF S${state.checkpoint}`} title={isChinese ? '阶段性鉴别诊断' : 'Current differential diagnosis'} />
          <div className="temporal-belief-history">
            <details>
              <summary>{isChinese ? '历史提交' : 'Prior submissions'} · {state.belief_history.length}</summary>
              {state.belief_history.map((item) => (
                <div key={`${item.checkpoint}-${item.submitted_at}`}><b>S{item.checkpoint}</b><span>{item.diagnoses.join(' › ')}</span></div>
              ))}
            </details>
          </div>
          <div className="temporal-diagnosis-current">
            {diagnoses.map((item, index) => (
              <div draggable key={item} onDragOver={(event) => event.preventDefault()} onDragStart={() => setDraggedDiagnosis(index)} onDrop={() => { if (draggedDiagnosis !== null) moveDiagnosis(draggedDiagnosis, index); setDraggedDiagnosis(null); }}>
                <span>{index + 1}</span><b>{item}</b>
                <button aria-label={`${isChinese ? '上移' : 'Move up'} ${item}`} onClick={() => moveDiagnosis(index, index - 1)} type="button"><ArrowUp /></button>
                <button aria-label={`${isChinese ? '删除' : 'Remove'} ${item}`} onClick={() => setDiagnoses((current) => current.filter((_, itemIndex) => itemIndex !== index))} type="button"><Trash2 /></button>
              </div>
            ))}
            {!diagnoses.length && <p>{isChinese ? '添加并排序当前鉴别诊断。' : 'Add and rank the current differential.'}</p>}
          </div>
          <div className="temporal-diagnosis-add">
            <Input onChange={(event) => setDiagnosisQuery(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') addDiagnosis(diagnosisQuery); }} placeholder={isChinese ? '搜索或输入疾病名称' : 'Search or enter a diagnosis'} value={diagnosisQuery} />
            {diagnosisQuery && <button onClick={() => addDiagnosis(diagnosisQuery)} type="button">{isChinese ? `添加“${diagnosisQuery}”` : `Add "${diagnosisQuery}"`}</button>}
            <div>{filteredDiagnoses.map((item) => <button key={item} onClick={() => addDiagnosis(item)} type="button">{item}</button>)}</div>
          </div>
          <div className={`temporal-belief-gate ${state.belief_required ? 'is-required' : ''}`}>
            <span>{state.belief_required ? (isChinese ? `看到新信息：请提交 S${state.checkpoint}` : `New information: submit S${state.checkpoint}`) : (isChinese ? `S${state.checkpoint} 已提交，可继续行动` : `S${state.checkpoint} submitted; actions unlocked`)}</span>
            <Button disabled={!diagnoses.length || busy || !state.belief_required} onClick={() => void mutate(`/temporal/sessions/${state.session_id}/beliefs`, { diagnoses })}>
              {isChinese ? '提交' : 'Submit'} S{state.checkpoint}
            </Button>
            <Button disabled={!diagnoses.length || busy || state.belief_required} onClick={() => void finalize()} variant="outline">
              <CheckCircle2 />{isChinese ? '锁定最终诊断' : 'Lock final diagnosis'}
            </Button>
          </div>
        </aside>
      </section>
      {notice && <div className="arena-toast" aria-live="polite"><span />{notice}</div>}
    </main>
  );
}

function TemporalArenaLauncher({ index, cases, dataset, caseId, busy, notice, onDataset, onCase, onStart }: {
  index: TemporalArenaIndex | null;
  cases: TemporalArenaCase[];
  dataset: string;
  caseId: string;
  busy: boolean;
  notice: string;
  onDataset: (value: string) => void;
  onCase: (value: string) => void;
  onStart: () => void;
}) {
  const { isChinese } = useLanguage();
  return (
    <main className="temporal-launcher">
      <header><Link href="/arena"><ArrowLeft />{isChinese ? '返回 Arena' : 'Back to Arena'}</Link><div><small>ClincForestBench · Temporal v2</small><h1>{isChinese ? '选择一条真实时间病例线' : 'Choose an observed clinical timeline'}</h1><p>{isChinese ? '医生只看到自然语言病情；每次问询或检查立即返回，时序延迟由模拟时钟自动记录。' : 'Clinicians see natural-language presentations. Questions and tests return immediately while the simulation clock records source timing.'}</p></div><Badge>{index?.case_count ?? 0} CASES</Badge></header>
      <section className="temporal-dataset-cards">
        {Object.entries(index?.dataset_case_counts ?? {}).map(([name, count], position) => (
          <motion.button animate={{ opacity: 1, y: 0 }} className={dataset === name ? 'is-selected' : ''} initial={{ opacity: 0, y: 10 }} key={name} onClick={() => onDataset(name)} transition={{ delay: position * 0.04 }} type="button">
            <span>{datasetIcon(name)}</span><small>DATASET</small><b>{name}</b><em>{count} cases</em>
          </motion.button>
        ))}
      </section>
      <footer><label><span>{isChinese ? '具体 Case' : 'Case'}</span><select onChange={(event) => onCase(event.target.value)} value={caseId}>{cases.map((item) => <option key={item.case_id} value={item.case_id}>{item.case_id} · {item.eligible_event_count} {isChinese ? '个临床动作' : 'clinical actions'}</option>)}</select></label><div><b>{isChinese ? '玩法顺序' : 'Sequence'}</b><span>{isChinese ? 'S0 判断 → 问询 / 查体 / 检查 → 结果立即返回 → 更新判断 → 最终诊断' : 'S0 belief → history / exam / tests → result → update belief → final diagnosis'}</span></div><Button disabled={!caseId || busy} onClick={onStart}><Play />{isChinese ? '开始模拟' : 'Start simulation'}</Button></footer>
      {notice && <div className="arena-toast"><span />{notice}</div>}
    </main>
  );
}

function DoctorPath({ state }: { state: TemporalArenaState }) {
  const { isChinese } = useLanguage();
  const steps: Array<{ key: string; tone: string; label: string; meta: string }> = [
    { key: 's0', tone: 'context', label: isChinese ? 'T0 初始信息' : 'T0 initial information', meta: 'S0' },
  ];
  state.belief_history.forEach((belief) => steps.push({ key: `belief-${belief.submitted_at}`, tone: 'belief', label: belief.diagnoses[0], meta: `${isChinese ? '提交' : 'Submitted'} S${belief.checkpoint}` }));
  state.pending_actions.forEach((item, index) => {
    steps.push({ key: `order-${index}`, tone: item.status === 'PENDING' ? 'pending' : 'action', label: item.display ?? item.action_id, meta: `${isChinese ? '执行于' : 'Performed at'} ${formatArenaTime(item.ordered_game_time)}` });
    if (item.status === 'AVAILABLE') steps.push({ key: `result-${index}`, tone: item.modality?.toLowerCase() ?? 'result', label: isChinese ? '结果已返回' : 'Result available', meta: formatArenaTime(item.expected_available_game_time ?? 0) });
  });
  return <div className="doctor-path-tree">{steps.map((step, index) => <motion.div animate={{ opacity: 1, scale: 1 }} className={`tone-${step.tone}`} initial={{ opacity: 0, scale: 0.7 }} key={step.key}><i>{index + 1}</i><span><b>{step.label}</b><small>{step.meta}</small></span></motion.div>)}</div>;
}

function ClinicalEventCard({ event }: { event: TemporalEvent }) {
  const { isChinese } = useLanguage();
  const imaging = event.clinical_concept.modality === 'IMAGING';
  return <section className={`temporal-result-card ${imaging ? 'is-imaging' : ''}`}><header>{imaging ? <ImageIcon /> : modalityIcon(event.clinical_concept.modality)}<span><small>{event.presentation?.modality_label ?? event.clinical_concept.modality}</small><b>{event.presentation?.title ?? event.clinical_concept.display}</b></span><em>{formatArenaTime(event.arena_reveal_time_min ?? event.time.relative_available_min ?? event.time.relative_documented_min ?? 0)}</em></header>{imaging && <div className="imaging-result-banner"><ImageIcon /><span><b>{isChinese ? '影像结果 / 报告' : 'Imaging result / report'}</b><small>{isChinese ? '以下内容来自该源 Case 的实际发布记录。' : 'The content below comes from the source case record.'}</small></span></div>}<PresentationBody caseId={event.case_id} presentation={event.presentation} /></section>;
}

function ResultCard({ title, presentation }: { title: string; presentation: ClinicalPresentation }) {
  const { isChinese } = useLanguage();
  return <section className="temporal-result-card is-initial"><header><HeartPulse /><span><small>{isChinese ? '医生首屏可见信息' : 'Initially visible information'}</small><b>{title}</b></span></header><PresentationBody presentation={presentation} /></section>;
}

function PresentationBody({ presentation, caseId }: { presentation?: ClinicalPresentation; caseId?: string }) {
  const { isChinese } = useLanguage();
  if (!presentation) return <div className="clinical-presentation-empty">{isChinese ? '本节点没有可展示的临床结果。' : 'No clinical result is available for this node.'}</div>;
  const blocks = presentation.sections ?? presentation.blocks ?? [];
  return <div className="clinical-presentation">{presentation.headline && <p className="clinical-presentation-headline">{presentation.headline}</p>}{presentation.summary && <p className="clinical-presentation-summary">{presentation.summary}</p>}{caseId && presentation.media?.map((item) => <figure className="clinical-source-media" key={item.asset}><NextImage alt={item.caption} height={900} src={`${API_BASE}/temporal/media/${encodeURIComponent(caseId)}/${encodeURIComponent(item.asset)}`} unoptimized width={1200} /><figcaption>{item.caption}</figcaption></figure>)}{blocks.map((block, blockIndex) => <section key={`${block.title}-${blockIndex}`}><h4>{block.title}</h4>{block.kind === 'NARRATIVE' ? <p>{block.text}</p> : <div className="clinical-result-rows">{(block.rows ?? []).map((row, rowIndex) => <div className={['异常', '偏高', '偏低', 'Abnormal', 'High', 'Low'].includes(row.flag ?? '') ? 'is-abnormal' : ''} key={`${row.label}-${rowIndex}`}><span>{row.label}</span><b>{row.value}{row.unit ? ` ${row.unit}` : ''}</b>{row.flag && <em>{row.flag}</em>}</div>)}</div>}</section>)}</div>;
}

function TemporalResultReview({ review, onNewCase }: { review: TemporalArenaReview; onNewCase: () => void }) {
  const { isChinese } = useLanguage();
  const graph = review.ground_truth_tree;
  return <main className="temporal-review-page"><header><div><small>Temporal Arena completed</small><h1>{review.session.case_id}</h1></div><div><b>{review.comparison.predicted_diagnosis}</b><ArrowRight /><b className="truth">{review.comparison.ground_truth_diagnosis}</b></div><Button onClick={onNewCase}>{isChinese ? '新 Case' : 'New case'}</Button></header><section><article><PanelHeader icon={<ListOrdered />} kicker="DOCTOR" title={isChinese ? '我的判断树' : 'My decision tree'} /><DoctorReviewPath review={review} /></article><article><PanelHeader icon={<Stethoscope />} kicker="REFERENCE" title={isChinese ? 'Case ground-truth 时间树' : 'Case ground-truth timeline'} /><CompactGroundTruth graph={graph} /></article><article><PanelHeader icon={<History />} kicker="FOREST" title={isChinese ? '所有玩家在本 Case 的统计' : 'All-player case statistics'} /><div className="temporal-community"><b>{review.community.completed_session_count} {isChinese ? '次完成' : 'completed'}</b><span>{isChinese ? '平均' : 'Mean'} {review.community.mean_actions} {isChinese ? '个动作' : 'actions'}</span>{review.community.top1_diagnoses.map((item) => <div key={item.diagnosis}><span>{item.diagnosis}</span><i style={{ width: `${Math.max(3, item.rate * 100)}%` }} /><b>{Math.round(item.rate * 100)}%</b></div>)}{!review.community.top1_diagnoses.length && <p>{isChinese ? '完成更多游玩后，这里会长出群体分支。' : 'Cohort branches appear after more completed runs.'}</p>}<details><summary>{isChinese ? '查看完整交互 JSON' : 'View complete interaction JSON'}</summary><pre>{JSON.stringify(review.session, null, 2)}</pre></details></div></article></section></main>;
}

function DoctorReviewPath({ review }: { review: TemporalArenaReview }) {
  const { isChinese } = useLanguage();
  return <div className="doctor-review-path"><div><i>0</i><span><b>T0</b><small>{isChinese ? '初始信息' : 'Initial information'}</small></span></div>{review.session.event_log.map((event, index) => <div key={index}><i>{index + 1}</i><span><b>{String(event.event_type).replaceAll('_', ' ')}</b><small>{event.game_time_min !== undefined ? formatArenaTime(Number(event.game_time_min)) : event.game_time_after_min !== undefined ? formatArenaTime(Number(event.game_time_after_min)) : ''}</small></span></div>)}</div>;
}

function CompactGroundTruth({ graph }: { graph: TemporalArenaReview['ground_truth_tree'] }) {
  const nodes = [...graph.nodes].sort((a, b) => a.reveal_time_min - b.reveal_time_min);
  return <div className="compact-ground-truth">{nodes.map((node) => <div className={`tone-${node.node_type.toLowerCase()} modality-${node.lane.toLowerCase()}`} key={node.node_id} title={`${node.label}\n${node.subtitle}`}><i /> <span><b>{node.label}</b><small>{formatArenaTime(node.reveal_time_min)}</small></span></div>)}</div>;
}

function PanelHeader({ icon, kicker, title }: { icon: React.ReactNode; kicker: string; title: string }) {
  return <header className="temporal-panel-title"><span>{icon}</span><div><small>{kicker}</small><b>{title}</b></div></header>;
}

function modalityIcon(modality: string) {
  if (modality === 'IMAGING') return <ImageIcon />;
  if (modality === 'LAB') return <Beaker />;
  return <FileText />;
}

function datasetIcon(name: string) {
  if (name.includes('MIMIC')) return <HeartPulse />;
  if (name.includes('PMC') || name.includes('NEJM')) return <FileText />;
  return <Stethoscope />;
}

function formatArenaTime(value: number) {
  const rounded = Math.round(value);
  if (Math.abs(rounded) < 60) return `T${rounded < 0 ? '−' : '+'}${Math.abs(rounded)}m`;
  const hours = Math.floor(Math.abs(rounded) / 60);
  const minutes = Math.abs(rounded) % 60;
  return `T${rounded < 0 ? '−' : '+'}${hours}h${minutes ? `${minutes}m` : ''}`;
}
