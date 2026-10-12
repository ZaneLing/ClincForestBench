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
import { api, eventId, API_BASE } from '@/lib/api';
import { PageControls, PagedReader } from './paged-reader';
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

const categories: Record<string, string> = {
  Laboratory: '检验科',
  Endocrinology: '内分泌',
  Obstetrics: '产科',
  Microbiology: '微生物',
  Immunology: '免疫',
  Hematology: '血液',
  Toxicology: '毒理',
  Oncology: '肿瘤',
  Genetics: '遗传',
  Imaging: '影像',
  'Nuclear medicine': '核医学',
  Cardiology: '心血管',
  Respiratory: '呼吸',
  Endoscopy: '内镜',
  Neurology: '神经',
  Sampling: '穿刺取样',
  Pathology: '病理',
  Gynecology: '妇科',
  'Reproductive medicine': '生殖医学',
  Urology: '泌尿',
  Ophthalmology: '眼科',
  ENT: '耳鼻喉',
  Dermatology: '皮肤',
  'Physical examination': '体格检查',
  Records: '既往记录',
  Presentation: '就诊信息',
  Symptoms: '症状',
  'Systems review': '系统回顾',
  'Mental health': '心理健康',
  Lifestyle: '生活方式',
  History: '病史',
  'Medication and allergy': '用药与过敏',
  'Family history': '家族史',
  Exposure: '暴露史',
  'Reproductive history': '生殖史',
  Pediatrics: '儿科',
  Prevention: '预防',
  'Social context': '社会情况',
  Preferences: '意愿',
  Workflow: '工作流',
  'Source catalog': '源数据扩展目录',
};
const fieldNames: Record<string, [string, string]> = {
  age: ['Age', '年龄'],
  age_range: ['Age range', '年龄范围'],
  sex: ['Sex', '性别'],
  gender: ['Gender', '性别'],
  occupation: ['Occupation', '职业'],
  question: ['Presentation', '首诊描述'],
  answer: ['Answer', '回答'],
  components: ['Components', '检查分项'],
  name: ['Name', '名称'],
  label: ['Item', '项目'],
  value: ['Value', '结果'],
  number_value: ['Value', '数值'],
  unit: ['Unit', '单位'],
  units: ['Unit', '单位'],
  text: ['Result', '结果'],
  flag: ['Flag', '标记'],
  finding: ['Finding', '所见'],
  impression: ['Impression', '报告结论'],
  narrative_text: ['Record', '记录'],
  patient_answer: ['Answer', '回答'],
  caption: ['Description', '说明'],
  status: ['Evidence status', '证据状态'],
  note: ['Note', '备注'],
  report: ['Report', '报告'],
  heart_rate: ['Heart rate', '心率'],
  respiratory_rate: ['Respiratory rate', '呼吸频率'],
  sbp: ['Systolic pressure', '收缩压'],
  dbp: ['Diastolic pressure', '舒张压'],
  spo2: ['SpO₂', '血氧饱和度'],
  temperature_c: ['Temperature (°C)', '体温（℃）'],
  temperature_f: ['Temperature (°F)', '体温（℉）'],
};
const statuses: Record<string, [string, string]> = {
  ACTIVE: ['In progress', '进行中'],
  COMPLETED: ['Completed', '已完成'],
  TERMINATED_MISSING_RESULT: [
    'Ended: result not recorded',
    '已终止：病例未记录该检查',
  ],
  PRESENT: ['Present', '存在'],
  ABSENT: ['Absent', '不存在'],
  DEFAULT: ['Dataset default', '数据集默认值'],
  NOT_APPLICABLE: ['Not applicable', '不适用'],
  VALUE: ['Recorded value', '已记录结果'],
  M: ['Male', '男'],
  F: ['Female', '女'],
  unknown: ['Not recorded', '未记载'],
};

function ResultValue({
  value,
  chinese,
  caseId,
}: {
  value: unknown;
  chinese: boolean;
  caseId: string;
}) {
  if (value == null || value === '')
    return (
      <span className="enc-muted">{chinese ? '未记载' : 'Not recorded'}</span>
    );
  if (Array.isArray(value))
    return (
      <div className="enc-values">
        {value.map((v, i) => (
          <ResultValue key={i} value={v} chinese={chinese} caseId={caseId} />
        ))}
      </div>
    );
  if (typeof value === 'object') {
    const data = value as Record<string, unknown>;
    return (
      <dl className="enc-result">
        {Object.entries(data)
          .filter(
            ([key]) =>
              ![
                'source_path',
                'source_sentence_index',
                'source_patient_turn',
                'time_is_sequence_proxy',
                'specimen_id',
                'media_type',
                'panel_abnormal',
              ].includes(key),
          )
          .map(([key, val]) =>
            key === 'media_asset' ? (
              <div key={key}>
                <a
                  target="_blank"
                  rel="noreferrer"
                  href={`${API_BASE}/temporal/media/${encodeURIComponent(caseId)}/${encodeURIComponent(typeof val === 'string' ? val : '')}`}
                >
                  {chinese ? '打开原始报告图像' : 'Open original report image'}
                </a>
              </div>
            ) : (
              <div key={key}>
                <dt>
                  {fieldNames[key]?.[chinese ? 1 : 0] ??
                    key.replaceAll('_', ' ')}
                </dt>
                <dd>
                  <ResultValue value={val} chinese={chinese} caseId={caseId} />
                </dd>
              </div>
            ),
          )}
      </dl>
    );
  }
  const text =
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'boolean'
      ? `${value}`
      : '';
  return <span>{statuses[text]?.[chinese ? 1 : 0] ?? text}</span>;
}

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
  const [stepIndex, setStepIndex] = useState<number | null>(null);
  const [pane, setPane] = useState<'patient' | 'library' | 'result'>('library');
  const [prescriptionOpen, setPrescriptionOpen] = useState(false);
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
    setHistory(await api<History[]>('/encounters/history'));
  }
  async function choose(item: Item) {
    setReasons(
      await api<Reason[]>(`/encounters/reasons/${encodeURIComponent(item.id)}`),
    );
    setSelected(item);
    setReasonId('');
    setReasonText('');
    setReasonDetails(false);
    setHypothesis('');
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
            {t('Earlier sessions', '旧版会话')}
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
                'The selected examination has no recorded result in this case. This visit has ended; your choice, reason and full trajectory have been saved.',
                '该病例没有所选检查的记录结果，本次就诊已终止。所选检查、原因及完整轨迹已保存。',
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
                  'Choose an item, then record why you chose it.',
                  '选择项目后，请记录本次选择的原因。',
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
              <h2>{t('Decision trajectory', '诊疗决策轨迹')}</h2>
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
                        {t('Not recorded in this case.', '该病例未记载。')}
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
            </section>
          </div>
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
          {!reasonDetails && (
            <fieldset>
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
            {t('Record reason and perform step', '记录原因并执行')}
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
