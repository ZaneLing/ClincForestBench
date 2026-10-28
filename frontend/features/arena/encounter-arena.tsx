'use client';

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import {
  Activity,
  ClipboardList,
  Download,
  MessageCircle,
  Search,
  Stethoscope,
  X,
} from 'lucide-react';
import { useAuth } from '@/features/auth/auth-context';
import { AuthGate } from '@/features/auth/auth-gate';
import { useLanguage } from '@/features/i18n/language-context';
import { api, eventId } from '@/lib/api';
import { categories, statuses, ResultValue } from './encounter-presentation';
import { PageControls, PagedReader } from './paged-reader';
import { EncounterTrajectoryTree } from './encounter-trajectory-tree';
import './encounter.css';

type Label = { en: string; 'zh-CN': string };
type Item = {
  id: string;
  kind: 'operation' | 'inquiry';
  category: string;
  label: Label;
};
type Reason = { id: string; label: Label };
type Entry = {
  id: string;
  sequence: number;
  type: string;
  timestamp: string;
  item?: Item;
  reason_options?: Reason[];
  reason_id?: string;
  reason_text?: string;
  hypothesis?: string;
  result_status?: string;
  records?: {
    source_id: string;
    result: unknown;
    source_label?: string;
    partial_panel?: boolean;
  }[];
  diagnoses?: string[];
  text?: string;
};
type Visit = {
  id: string;
  created_at: string;
  case_id: string;
  status: string;
  diagnoses: string[];
  prescription: string | null;
  prescription_available: boolean;
  events: Entry[];
  visit: {
    dataset: string;
    demographics: Record<string, unknown>;
    presentation: unknown;
    track_type: string;
  };
};
type Catalog = {
  items: Item[];
  cases: { case_id: string; dataset: string; track_type: string }[];
  conditions: { id: string; label: Label }[];
};
type History = {
  id: string;
  case_id: string;
  status: string;
  created_at: string;
  diagnoses: string[];
};

function EncounterDialog({
  children,
  title,
  onClose,
  busy,
}: {
  children: ReactNode;
  title: string;
  onClose: () => void;
  busy: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="enc-dialog"
      aria-busy={busy}
      aria-labelledby={title}
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
    >
      {children}
    </dialog>
  );
}

export function EncounterArena({
  historyOnly = false,
}: {
  historyOnly?: boolean;
}) {
  const { account, loading } = useAuth();
  const { isChinese } = useLanguage();
  if (loading)
    return (
      <main className="enc-page">{isChinese ? '加载中…' : 'Loading…'}</main>
    );
  if (!account) return <AuthGate />;
  return (
    <EncounterWorkspace key={account.username} historyOnly={historyOnly} />
  );
}

function EncounterWorkspace({
  historyOnly = false,
}: {
  historyOnly?: boolean;
}) {
  const { account, loading } = useAuth();
  const { locale, isChinese: zh } = useLanguage();
  const params = useSearchParams();
  const t = (en: string, cn: string) => (zh ? cn : en);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [visit, setVisit] = useState<Visit | null>(null);
  const [history, setHistory] = useState<History[]>([]);
  const [caseId, setCaseId] = useState('');
  const [dataset, setDataset] = useState('');
  const [kind, setKind] = useState<'operation' | 'inquiry'>('inquiry');
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('');
  const [selected, setSelected] = useState<Item | null>(null);
  const [reasons, setReasons] = useState<Reason[]>([]);
  const [reasonId, setReasonId] = useState('');
  const [reasonText, setReasonText] = useState('');
  const [reasonDetails, setReasonDetails] = useState(false);
  const [hypothesis, setHypothesis] = useState('');
  const [diagnosisOpen, setDiagnosisOpen] = useState(false);
  const [diagnosis, setDiagnosis] = useState('');
  const [prescription, setPrescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [libraryPage, setLibraryPage] = useState(0);
  const [pageSize, setPageSize] = useState(4);
  const libraryBody = useRef<HTMLDivElement>(null);
  const librarySearch = useRef<HTMLInputElement>(null);
  const [stepIndex, setStepIndex] = useState<number | null>(null);
  const [pane, setPane] = useState<'patient' | 'library' | 'result'>('library');
  const [prescriptionOpen, setPrescriptionOpen] = useState(false);
  const [trajectoryOpen, setTrajectoryOpen] = useState(false);
  const [historyPage, setHistoryPage] = useState(0);
  const storageKey = `clincforestbench.encounter.${account?.username ?? ''}`;

  useEffect(() => {
    if (!account) return;
    let live = true;
    Promise.all([
      api<Catalog>('/encounters/catalog'),
      api<History[]>('/encounters/history'),
    ])
      .then(([c, h]) => {
        if (!live) return;
        setCatalog(c);
        setHistory(h);
        setCaseId(c.cases[0]?.case_id ?? '');
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    const id =
      params.get('session') ||
      (!historyOnly && localStorage.getItem(storageKey));
    if (id)
      api<Visit>(`/encounters/${encodeURIComponent(id)}`)
        .then((v) => {
          if (live) {
            setVisit(v);
            setPane(v.events.length ? 'result' : 'library');
            setPrescription(v.prescription ?? '');
          }
        })
        .catch((e) => {
          if (live) setError(e.message);
        });
    return () => {
      live = false;
    };
  }, [account, historyOnly, params, storageKey]);

  const items = useMemo(
    () =>
      (catalog?.items ?? []).filter(
        (i) =>
          i.kind === kind &&
          (!category || i.category === category) &&
          `${i.label.en} ${i.label['zh-CN']} ${i.id}`
            .toLowerCase()
            .includes(query.toLowerCase()),
      ),
    [catalog, kind, category, query],
  );
  const availableCategories = [
    ...new Set(
      catalog?.items.filter((i) => i.kind === kind).map((i) => i.category),
    ),
  ];
  const used = new Set(visit?.events.map((e) => e.item?.id));
  const active = visit?.status === 'ACTIVE';
  const currentStep = Math.min(
    stepIndex ?? (visit?.events.length ?? 1) - 1,
    (visit?.events.length ?? 1) - 1,
  );
  const libraryPages = Math.max(1, Math.ceil(items.length / pageSize));
  const safeLibraryPage = Math.min(libraryPage, libraryPages - 1);

  useEffect(() => {
    const element = libraryBody.current;
    if (!element) return;
    const observer = new ResizeObserver(() => {
      if (element.clientHeight)
        setPageSize(Math.max(1, Math.floor((element.clientHeight + 8) / 78)));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [visit?.id]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError('');
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  async function update(path: string, body: object) {
    const next = await api<Visit>(`/encounters/${visit!.id}/${path}`, {
      method: 'POST',
      body: JSON.stringify({ ...body, client_event_id: eventId(path) }),
    });
    setVisit(next);
    setStepIndex(null);
    setPane('result');
    if (path === 'diagnoses' || path === 'finish') setTrajectoryOpen(true);
    // The mutation already returned the saved visit. Never hold the result dialog
    // open waiting for a second, unrelated history request.
    const saved = {
      id: next.id,
      case_id: next.case_id,
      status: next.status,
      created_at: next.created_at,
      diagnoses: next.diagnoses,
    };
    setHistory((rows) =>
      rows.some((row) => row.id === next.id)
        ? rows.map((row) => (row.id === next.id ? saved : row))
        : [saved, ...rows],
    );
  }
  async function choose(item: Item) {
    setSelected(item);
    setReasons([]);
    setReasonId('');
    setReasonText('');
    setReasonDetails(false);
    setHypothesis('');
    setReasons(
      await api<Reason[]>(`/encounters/reasons/${encodeURIComponent(item.id)}`),
    );
  }
  function continueVisit() {
    setPane('library');
    setQuery('');
    setCategory('');
    setLibraryPage(0);
    requestAnimationFrame(() => librarySearch.current?.focus());
  }
  async function download() {
    const data = await api<object>(`/encounters/${visit!.id}/export`);
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
    );
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${visit!.id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (loading)
    return <main className="enc-page">{t('Loading…', '加载中…')}</main>;
  if (!account) return <AuthGate />;

  return (
    <main className={`enc-page ${visit ? 'enc-workspace' : 'enc-lobby'}`}>
      <header className="enc-heading">
        <div>
          <p className="enc-eyebrow">CLINCFORESTBENCH / VISIT</p>
          <h1>
            {historyOnly
              ? t('Your clinical trajectories', '我的诊疗轨迹')
              : t('Clinical decision workspace', '医生诊疗工作台')}
          </h1>
          <p>
            {t(
              'Ask. Investigate. Explain your choice. Diagnose.',
              '问询、检查、记录选择原因，形成诊断。',
            )}
          </p>
        </div>
        <div className="enc-row">
          <Link href={historyOnly ? '/arena' : '/history'}>
            {historyOnly
              ? t('New visit', '开始就诊')
              : t('History', '历史轨迹')}
          </Link>
          <Link href="/history?mode=classic">
            {t('Model sessions', '模型会话')}
          </Link>
        </div>
      </header>
      {error && (
        <div className="enc-error" role="alert">
          {error}
        </div>
      )}
      {!visit && (
        <section className="enc-card">
          {!historyOnly && (
            <>
              <h2>{t('Choose a visit', '选择就诊病例')}</h2>
              <div className="enc-row">
                <label>
                  {t('Dataset', '数据集')}
                  <select
                    value={dataset}
                    onChange={(e) => {
                      setDataset(e.target.value);
                      setCaseId(
                        catalog?.cases.find(
                          (c) =>
                            !e.target.value || c.dataset === e.target.value,
                        )?.case_id ?? '',
                      );
                    }}
                  >
                    <option value="">{t('All datasets', '全部数据集')}</option>
                    {[...new Set(catalog?.cases.map((c) => c.dataset))].map(
                      (d) => (
                        <option key={d}>{d}</option>
                      ),
                    )}
                  </select>
                </label>
                <label className="enc-grow">
                  {t('Case', '病例')}
                  <select
                    value={caseId}
                    onChange={(e) => setCaseId(e.target.value)}
                  >
                    {catalog?.cases
                      .filter((c) => !dataset || c.dataset === dataset)
                      .map((c) => (
                        <option key={c.case_id} value={c.case_id}>
                          {c.dataset} · {c.case_id}
                        </option>
                      ))}
                  </select>
                </label>
                <button
                  className="enc-primary"
                  disabled={busy || !caseId}
                  onClick={() =>
                    run(async () => {
                      const v = await api<Visit>('/encounters', {
                        method: 'POST',
                        body: JSON.stringify({
                          case_id: caseId,
                          client_event_id: eventId('visit'),
                        }),
                      });
                      setVisit(v);
                      setStepIndex(null);
                      setPane('patient');
                      setKind('inquiry');
                      setQuery('');
                      setCategory('');
                      setLibraryPage(0);
                      setPrescription('');
                      localStorage.setItem(storageKey, v.id);
                    })
                  }
                >
                  {t('Start visit', '进入 Visit')}
                </button>
              </div>
            </>
          )}
          <h2>{t('Saved trajectories', '已保存轨迹')}</h2>
          <div className="enc-history">
            {history.slice(historyPage * 8, historyPage * 8 + 8).map((h) => (
              <button
                key={h.id}
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    const v = await api<Visit>(`/encounters/${h.id}`);
                    setVisit(v);
                    setStepIndex(null);
                    setPane('result');
                    setPrescription(v.prescription ?? '');
                    localStorage.setItem(storageKey, v.id);
                  })
                }
              >
                <strong>{h.case_id}</strong>
                <span>
                  {statuses[h.status]?.[zh ? 1 : 0]} ·{' '}
                  {new Date(h.created_at).toLocaleString(locale)}
                </span>
                <span>{h.diagnoses.join(' · ')}</span>
              </button>
            ))}
            {!history.length && (
              <p>{t('No saved visits yet.', '暂无已保存就诊。')}</p>
            )}
          </div>
          <PageControls
            page={historyPage}
            pages={Math.max(1, Math.ceil(history.length / 8))}
            onChange={setHistoryPage}
            chinese={zh}
            label={t('Saved trajectories', '已保存轨迹')}
          />
        </section>
      )}
      {visit && (
        <>
          <section
            className="enc-card enc-visit-bar"
            aria-label={t('Visit controls', '就诊操作')}
          >
            <div className="enc-row enc-between">
              <div>
                <span className="enc-eyebrow">
                  VISIT · {visit.visit.dataset}
                </span>
                <h2>{visit.case_id}</h2>
              </div>
              <span className={active ? 'enc-status' : 'enc-status enc-closed'}>
                {statuses[visit.status]?.[zh ? 1 : 0]}
              </span>
            </div>
            <div className="enc-row">
              <button
                disabled={busy || !active}
                className="enc-primary"
                onClick={() => {
                  setDiagnosis(visit.diagnoses.join('\n'));
                  setDiagnosisOpen(true);
                }}
              >
                <Stethoscope size={17} />
                {t('Diagnosis', '诊断')}
              </button>
              <button disabled={busy} onClick={() => run(download)}>
                <Download size={17} />
                {t('Export trajectory', '导出轨迹')}
              </button>
              {(!!visit.diagnoses.length || !active) && (
                <button disabled={busy} onClick={() => setTrajectoryOpen(true)}>
                  {t('View trajectory tree', '查看轨迹树')}
                </button>
              )}
              {!!visit.diagnoses.length && active && (
                <>
                  {visit.prescription_available && (
                    <button
                      disabled={busy}
                      onClick={() => setPrescriptionOpen(true)}
                    >
                      {t('Prescription', '处方')}
                    </button>
                  )}
                  <button
                    disabled={busy}
                    onClick={() => run(() => update('finish', {}))}
                  >
                    {t('Complete visit', '完成本次就诊')}
                  </button>
                </>
              )}
              <button
                disabled={busy}
                onClick={() => {
                  setVisit(null);
                  setHistoryPage(0);
                  localStorage.removeItem(storageKey);
                  setHistory([]);
                  void run(async () =>
                    setHistory(await api<History[]>('/encounters/history')),
                  );
                }}
              >
                {t('Choose another visit', '选择其他病例')}
              </button>
            </div>
          </section>
          {visit.status === 'TERMINATED_MISSING_RESULT' && (
            <output className="enc-ended">
              {t(
                'This case has no answer or result for the selected item. The case has ended and the complete trajectory is saved. Choose another visit to continue.',
                '所选问题或检查在此病例中没有答案或结果。病例已结束，完整轨迹已保存。请点击“选择其他病例”继续。',
              )}
            </output>
          )}
          <nav
            className="enc-pane-tabs"
            aria-label={t('Workspace panels', '工作区分栏')}
          >
            {(['patient', 'library', 'result'] as const).map((value) => (
              <button
                key={value}
                aria-pressed={pane === value}
                onClick={() => setPane(value)}
              >
                {
                  {
                    patient: t('Visit information', '首诊信息'),
                    library: t('Choose a step', '问询 / 检查'),
                    result: t('Results & trajectory', '结果 / 轨迹'),
                  }[value]
                }
              </button>
            ))}
          </nav>
          <div className="enc-columns" data-pane={pane}>
            <section className="enc-card enc-patient">
              <h2>{t('Visit information', '首诊信息')}</h2>
              <PagedReader
                key={visit.id}
                chinese={zh}
                label={t('Visit information', '首诊信息')}
              >
                <ResultValue
                  value={visit.visit.demographics}
                  chinese={zh}
                  caseId={visit.case_id}
                />
                <h3 className="enc-section-label">
                  {t('Initial presentation', '首诊描述')}
                </h3>
                <ResultValue
                  value={visit.visit.presentation}
                  chinese={zh}
                  caseId={visit.case_id}
                />
                {visit.visit.track_type === 'WORKFLOW_FOREST' && (
                  <p className="enc-missing">
                    {t(
                      'This source contains offline workflow instructions, not patient examination results.',
                      '该来源为离线工作流指令，内容不代表患者检查结果。',
                    )}
                  </p>
                )}
                {!!visit.diagnoses.length && (
                  <>
                    <h3 className="enc-section-label">
                      {t('Current diagnosis', '当前诊断')}
                    </h3>
                    <p>{visit.diagnoses.join(' · ')}</p>
                  </>
                )}
              </PagedReader>
            </section>
            <section className="enc-card enc-library">
              <h2>
                <ClipboardList size={20} />
                {t('Clinical libraries', '临床目录')}
              </h2>
              <div className="enc-tabs">
                <button
                  aria-pressed={kind === 'inquiry'}
                  onClick={() => {
                    setKind('inquiry');
                    setLibraryPage(0);
                    setCategory('');
                  }}
                >
                  <MessageCircle size={17} />
                  {t('Inquiries', '问询库')} (
                  {catalog?.items.filter((i) => i.kind === 'inquiry').length ??
                    0}
                  )
                </button>
                <button
                  aria-pressed={kind === 'operation'}
                  onClick={() => {
                    setKind('operation');
                    setLibraryPage(0);
                    setCategory('');
                  }}
                >
                  <Activity size={17} />
                  {t('Examinations & procedures', '检查 / 操作库')} (
                  {catalog?.items.filter((i) => i.kind === 'operation')
                    .length ?? 0}
                  )
                </button>
              </div>
              <label className="enc-search">
                <Search size={18} />
                <input
                  ref={librarySearch}
                  aria-label={t('Search clinical library', '搜索临床目录')}
                  placeholder={t(
                    'Search in English or Chinese',
                    '支持中英文搜索',
                  )}
                  value={query}
                  onChange={(e) => {
                    setQuery(e.target.value);
                    setLibraryPage(0);
                  }}
                />
              </label>
              <select
                aria-label={t('Category', '分类')}
                value={category}
                onChange={(e) => {
                  setCategory(e.target.value);
                  setLibraryPage(0);
                }}
              >
                <option value="">{t('All categories', '全部分类')}</option>
                {availableCategories.map((c) => (
                  <option key={c} value={c}>
                    {zh ? (categories[c] ?? c) : c}
                  </option>
                ))}
              </select>
              <p className="enc-muted">
                {t(
                  'Click an item and choose a reason. A missing answer or result ends the case.',
                  '点击项目并选择原因后返回结果；没有答案或结果则结束病例。',
                )}
              </p>
              <div className="enc-items" ref={libraryBody}>
                {items
                  .slice(
                    safeLibraryPage * pageSize,
                    (safeLibraryPage + 1) * pageSize,
                  )
                  .map((item) => (
                    <button
                      key={item.id}
                      title={item.label[locale]}
                      disabled={busy || !active || used.has(item.id)}
                      onClick={() => run(() => choose(item))}
                    >
                      <strong>{item.label[locale]}</strong>
                      <small>
                        {zh
                          ? (categories[item.category] ?? item.category)
                          : item.category}
                        {used.has(item.id)
                          ? t(' · Already selected', ' · 已选择')
                          : ''}
                      </small>
                    </button>
                  ))}
                {!items.length && (
                  <p>{t('No matching items.', '没有匹配项目。')}</p>
                )}
              </div>
              <div className="enc-library-footer">
                <small className="enc-muted">
                  {items.length} {t('items', '项')}
                </small>
                <PageControls
                  page={safeLibraryPage}
                  pages={libraryPages}
                  onChange={setLibraryPage}
                  chinese={zh}
                  label={t('Clinical library', '临床目录')}
                />
              </div>
            </section>
            <section className="enc-card enc-timeline">
              <h2>
                {t('Answers & decision trajectory', '问答结果与决策轨迹')}
              </h2>
              {busy && (
                <output className="enc-step-status">
                  {t('Processing your selection…', '正在处理你的选择…')}
                </output>
              )}
              {!busy && visit.events[currentStep]?.type === 'ACTION' && (
                <output className="enc-step-status">
                  {visit.events[currentStep].result_status === 'RECORDED'
                    ? t(
                        `Step ${visit.events[currentStep].sequence}: answer / result returned below.`,
                        `第 ${visit.events[currentStep].sequence} 步：答案 / 结果已返回，见下方。`,
                      )
                    : visit.status === 'TERMINATED_MISSING_RESULT'
                      ? t(
                          'No answer / result. This case has ended.',
                          '没有答案 / 结果，病例已结束。',
                        )
                      : t(
                          'No recorded answer / result in this step.',
                          '该历史步骤没有记录答案 / 结果。',
                        )}
                </output>
              )}
              {!!visit.events.length && (
                <div className="enc-step-controls">
                  <select
                    aria-label={t('Choose a recorded step', '查看已记录步骤')}
                    value={currentStep}
                    onChange={(event) =>
                      setStepIndex(Number(event.target.value))
                    }
                  >
                    {visit.events.map((event, index) => (
                      <option key={event.id} value={index}>
                        {event.sequence}.{' '}
                        {event.item?.label[locale] ??
                          {
                            DIAGNOSIS: t('Diagnosis', '诊断'),
                            PRESCRIPTION: t('Prescription', '处方'),
                            COMPLETE: t('Visit completed', '就诊完成'),
                          }[event.type] ??
                          event.type}
                      </option>
                    ))}
                  </select>
                  <PageControls
                    page={currentStep}
                    pages={visit.events.length}
                    onChange={setStepIndex}
                    chinese={zh}
                    label={t('Recorded steps', '已记录步骤')}
                  />
                </div>
              )}
              {!visit.events.length && (
                <p className="enc-muted">
                  {t(
                    'The visit begins here. Select an inquiry, an examination, or record your diagnosis.',
                    '从首诊开始，可以选择问询、检查，或直接记录诊断。',
                  )}
                </p>
              )}
              {visit.events.slice(currentStep, currentStep + 1).map((event) => (
                <article key={event.id} className="enc-step">
                  <PagedReader
                    chinese={zh}
                    label={t('Step details', '步骤详情')}
                  >
                    <h3>
                      {event.item?.label[locale] ??
                        {
                          DIAGNOSIS: t('Diagnosis', '诊断'),
                          PRESCRIPTION: t('Prescription', '处方'),
                          COMPLETE: t('Visit completed', '就诊完成'),
                        }[event.type] ??
                        event.type}
                    </h3>
                    {event.reason_id && (
                      <p className="enc-reason">
                        {
                          event.reason_options?.find(
                            (r) => r.id === event.reason_id,
                          )?.label[locale]
                        }
                        {event.reason_text && ` — ${event.reason_text}`}
                      </p>
                    )}
                    {event.hypothesis && (
                      <p>
                        {t('Hypothesis: ', '诊断假设：')}
                        {event.hypothesis}
                      </p>
                    )}
                    {event.result_status === 'NOT_RECORDED' && (
                      <p className="enc-missing">
                        {t(
                          'No recorded answer or result. The choice and reason are saved in the trajectory.',
                          '该病例没有此项答案或结果；所选项目及原因已保存到轨迹。',
                        )}
                      </p>
                    )}
                    {event.records?.map((r, i) => (
                      <div key={`${r.source_id}-${i}`} className="enc-answer">
                        {r.source_label && <strong>{r.source_label}</strong>}
                        {r.partial_panel && (
                          <p className="enc-muted">
                            {t(
                              'Partial panel: only recorded components are shown.',
                              '部分检查组合：仅展示已记录分项。',
                            )}
                          </p>
                        )}
                        <ResultValue
                          value={r.result}
                          chinese={zh}
                          caseId={visit.case_id}
                        />
                      </div>
                    ))}
                    {event.diagnoses && <p>{event.diagnoses.join(' · ')}</p>}
                    {event.text && <p className="enc-prewrap">{event.text}</p>}
                    <small className="enc-muted">
                      {new Date(event.timestamp).toLocaleTimeString(locale)}
                    </small>
                  </PagedReader>
                </article>
              ))}
              {active && !!visit.events.length && (
                <div className="enc-next-actions">
                  <button
                    className="enc-primary"
                    disabled={busy}
                    onClick={continueVisit}
                  >
                    {t(
                      'Choose the next inquiry / examination',
                      '继续选择问询 / 检查',
                    )}
                  </button>
                  <small>
                    {t(
                      'Or use Diagnosis above to record your diagnosis.',
                      '也可点击顶部“诊断”记录当前诊断。',
                    )}
                  </small>
                </div>
              )}
            </section>
          </div>
          {trajectoryOpen && (
            <EncounterDialog title="enc-trajectory-title" busy={busy} onClose={() => setTrajectoryOpen(false)}>
              <button className="enc-close" aria-label={t('Close', '关闭')} disabled={busy} onClick={() => setTrajectoryOpen(false)}><X /></button>
              <h2 id="enc-trajectory-title">{t('Your decision trajectory tree', '本次诊疗轨迹树')}</h2>
              <EncounterTrajectoryTree caseId={visit.case_id} dataset={visit.visit.dataset} demographics={visit.visit.demographics} presentation={visit.visit.presentation} events={visit.events} chinese={zh} onSelect={(index) => { setStepIndex(index); setPane('result'); setTrajectoryOpen(false); }} />
              <p className="enc-muted"><Link href="/forest">{t('View the community forest', '直接查看决策森林')}</Link></p>
            </EncounterDialog>
          )}
          {prescriptionOpen && active && (
            <EncounterDialog
              title="enc-prescription-title"
              busy={busy}
              onClose={() => setPrescriptionOpen(false)}
            >
              <button
                className="enc-close"
                aria-label={t('Close', '关闭')}
                disabled={busy}
                onClick={() => setPrescriptionOpen(false)}
              >
                <X />
              </button>
              {error && (
                <p role="alert" className="enc-error">
                  {error}
                </p>
              )}
              <h2 id="enc-prescription-title">
                {t('After diagnosis', '诊断之后')}
              </h2>
              {visit.prescription_available && (
                <>
                  <label>
                    {t(
                      'Optional prescription / treatment plan',
                      '可选：处方 / 治疗计划',
                    )}
                    <textarea
                      rows={4}
                      value={prescription}
                      onChange={(e) => setPrescription(e.target.value)}
                      placeholder={t(
                        'Drug, dose, route, frequency, duration; or a non-drug treatment plan',
                        '药物、剂量、途径、频次、疗程；或非药物治疗计划',
                      )}
                    />
                  </label>
                  <button
                    disabled={busy || !prescription.trim()}
                    onClick={() =>
                      run(async () => {
                        await update('prescription', { text: prescription });
                        setPrescriptionOpen(false);
                      })
                    }
                  >
                    {t('Save prescription', '保存处方')}
                  </button>
                </>
              )}
              <p className="enc-muted">
                {t(
                  'You may continue investigating or revise the diagnosis before completing the visit.',
                  '完成前仍可继续问询、检查或修改诊断。',
                )}
              </p>
            </EncounterDialog>
          )}
        </>
      )}
      {selected && (
        <EncounterDialog
          title="enc-reason-title"
          onClose={() => setSelected(null)}
          busy={busy}
        >
          {error && (
            <p className="enc-error" role="alert">
              {error}
            </p>
          )}
          <button
            className="enc-close"
            aria-label={t('Close', '关闭')}
            disabled={busy}
            onClick={() => setSelected(null)}
          >
            <X />
          </button>
          <p className="enc-eyebrow">{t('BEFORE THIS STEP', '执行前记录')}</p>
          <h2 id="enc-reason-title">{selected.label[locale]}</h2>
          <p>
            {t('Why do you want to choose this step?', '为什么选择这一步？')}
          </p>
          {!reasons.length && (
            <output className="enc-muted">
              {busy
                ? t('Loading reasons…', '正在加载原因选项…')
                : t(
                    'Reasons could not be loaded. Please retry.',
                    '原因选项加载失败，请重试。',
                  )}
            </output>
          )}
          {!busy && !reasons.length && (
            <button onClick={() => run(() => choose(selected))}>
              {t('Retry', '重试')}
            </button>
          )}
          {!!reasons.length && !reasonDetails && (
            <fieldset disabled={busy}>
              <legend className="enc-muted">
                {t('Select one reason', '请选择一个原因')}
              </legend>
              {reasons.map((r) => (
                <label className="enc-reason-option" key={r.id}>
                  <input
                    type="radio"
                    name="reason"
                    checked={reasonId === r.id}
                    onChange={() => {
                      setReasonId(r.id);
                      if (r.id === 'other') setReasonDetails(true);
                    }}
                  />
                  {r.label[locale]}
                </label>
              ))}
            </fieldset>
          )}
          <button
            className="enc-detail-toggle"
            disabled={busy}
            onClick={() => setReasonDetails(!reasonDetails)}
          >
            {reasonDetails
              ? t('Back to reasons', '返回原因选项')
              : t(
                  'Add explanation or hypothesis (optional)',
                  '补充说明或诊断假设（可选）',
                )}
          </button>
          {reasonDetails && (
            <>
              <p className="enc-reason">
                {reasons.find((r) => r.id === reasonId)?.label[locale] ??
                  t(
                    'Choose a reason before submitting.',
                    '提交前请先选择原因。',
                  )}
              </p>
              <label>
                {t('Additional explanation', '补充说明')}
                {reasonId === 'other' && ' *'}
                <textarea
                  value={reasonText}
                  onChange={(e) => setReasonText(e.target.value)}
                />
              </label>
              <label>
                {t('Suspected diagnosis (optional)', '当前怀疑诊断（可选）')}
                <input
                  value={hypothesis}
                  onChange={(e) => setHypothesis(e.target.value)}
                />
              </label>
            </>
          )}
          <button
            className="enc-primary"
            disabled={
              busy || !reasonId || (reasonId === 'other' && !reasonText.trim())
            }
            onClick={() =>
              run(async () => {
                await update('actions', {
                  item_id: selected.id,
                  reason_id: reasonId,
                  reason_text: reasonText,
                  hypothesis,
                });
                setSelected(null);
              })
            }
          >
            {busy
              ? reasons.length
                ? t('Retrieving answer / result…', '正在获取答案 / 结果…')
                : t('Loading reasons…', '正在加载原因选项…')
              : t(
                  'Record reason and get answer / result',
                  '记录原因并获取答案 / 结果',
                )}
          </button>
        </EncounterDialog>
      )}
      {diagnosisOpen && (
        <EncounterDialog
          title="enc-diagnosis-title"
          onClose={() => setDiagnosisOpen(false)}
          busy={busy}
        >
          {error && (
            <p className="enc-error" role="alert">
              {error}
            </p>
          )}
          <button
            className="enc-close"
            aria-label={t('Close', '关闭')}
            disabled={busy}
            onClick={() => setDiagnosisOpen(false)}
          >
            <X />
          </button>
          <h2 id="enc-diagnosis-title">{t('Diagnosis', '诊断')}</h2>
          <label>
            {t('Select a disease to add', '选择疾病添加')}
            <select
              value=""
              onChange={(e) => {
                if (e.target.value)
                  setDiagnosis((v) => `${v}${v ? '\n' : ''}${e.target.value}`);
              }}
            >
              <option value="">{t('Choose a disease…', '请选择疾病…')}</option>
              {catalog?.conditions.map((c) => (
                <option key={c.id} value={c.label[locale]}>
                  {c.label[locale]}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t(
              'Or enter diagnoses manually, one per line',
              '也可手动输入，每行一个诊断',
            )}
            <textarea
              rows={5}
              value={diagnosis}
              onChange={(e) => setDiagnosis(e.target.value)}
            />
          </label>
          <button
            className="enc-primary"
            disabled={busy || !diagnosis.trim()}
            onClick={() =>
              run(async () => {
                await update('diagnoses', {
                  diagnoses: diagnosis
                    .split('\n')
                    .map((v) => v.trim())
                    .filter(Boolean),
                });
                setDiagnosisOpen(false);
              })
            }
          >
            {t('Save diagnosis', '保存诊断')}
          </button>
        </EncounterDialog>
      )}
    </main>
  );
}
