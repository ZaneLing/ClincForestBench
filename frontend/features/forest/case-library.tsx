'use client';

import { useEffect, useMemo, useState } from 'react';
import { Braces, CheckCircle2, ChevronLeft, ChevronRight, Clipboard, Database, Download, FileSpreadsheet, ListFilter, LoaderCircle, MessageCircle, Search, Stethoscope } from 'lucide-react';
import { api, API_BASE } from '@/lib/api';
import { useLanguage } from '@/features/i18n/language-context';
import { categories, ResultValue, statuses } from '@/features/arena/encounter-presentation';
import '@/features/arena/encounter.css';
import './case-library.css';

type Item = { id: string; kind: 'inquiry' | 'operation'; category: string; label: { en: string; 'zh-CN': string } };
type Entry = { case_id: string; dataset: string; demographics: { age: number | string | null; sex: string }; inquiry_count: number; operation_count: number; model_evidence_count: number };
type Index = { case_count: number; cases: Entry[]; items: Item[]; datasets: Record<string, number> };
type RecordResult = { source_id: string; source_label?: string; mapping_method?: string; result: unknown };
type Action = Item & { display_name: string; records: RecordResult[]; record_count: number; partial_panel: boolean };
type Evidence = { evidence_id: string; question: string; action_kind: string; clinical_domain: string; parent_evidence_id: string | null; access: string; status: string; answer: unknown; display_answer: string };
type Detail = {
  case_id: string; dataset: string; case_hash: string; identity: { case_type: string; generation_mode: string };
  initial_information: { demographics: { age: unknown; sex: string }; presentation: unknown };
  actions: Action[]; model_evidence: Evidence[]; treatments: { label: string; result: unknown }[];
  media: { asset: string; url: string }[]; source: Record<string, unknown>;
  reference: { oracle: { pathology: string; display_name: string; outcome_kind: string; differential: { condition: string; probability: number }[] }; quality: Record<string, unknown>; fidelity_note: string };
};
const HEADERS = { 'X-Research-Key': 'local-research-only' };
const PAGE_SIZE = 20;

export function CaseLibrary() {
  const { isChinese: zh, locale } = useLanguage();
  const t = (en: string, cn: string) => zh ? cn : en;
  const [index, setIndex] = useState<Index | null>(null);
  const [caseId, setCaseId] = useState('');
  const [dataset, setDataset] = useState('');
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api<Index>('/research/case-library', { headers: HEADERS, signal: controller.signal })
      .then(data => {
        setIndex(data);
        setError('');
        const requested = new URLSearchParams(window.location.search).get('case');
        const first = data.cases.find(c => c.case_id === requested) ?? data.cases[0];
        if (first) { setCaseId(first.case_id); setDataset(first.dataset); }
      }).catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [attempt, locale]);
  const filtered = useMemo(() => index?.cases.filter(c =>
    (!dataset || c.dataset === dataset) && `${c.case_id} ${c.dataset}`.toLowerCase().includes(query.toLowerCase())) ?? [], [index, dataset, query]);
  function selectCase(id: string) {
    setCaseId(id);
    const url = new URL(window.location.href);
    url.searchParams.set('case', id);
    window.history.replaceState({}, '', url);
  }
  return (
    <main className="library">
      <header className="library-heading">
        <div className="library-heading-icon"><Database size={25} /></div>
        <div><p>CASE LIBRARY</p><h1>{t('Explore cases & evidence', '病例与证据浏览器')}</h1><span>{t('Initial information, selectable actions and fixed answers in one place.', '一次看清：开局信息、可选问询 / 检查，以及固定证据结果。')}</span></div>
        <div className="library-total"><b>{index?.case_count ?? '—'}</b><span>{t('cases · 14 datasets', '病例 · 14 个数据集')}</span></div>
      </header>
      {error ? <div className="library-error" role="alert">{error} <button onClick={() => setAttempt(a => a + 1)}>{t('Retry', '重试')}</button></div> : null}
      <div className="library-layout">
        <aside className="library-sidebar">
          <label className="library-search"><Search size={16} /><input aria-label={t('Search cases', '搜索病例')} placeholder={t('Search Case ID…', '搜索 Case ID / 数据集…')} value={query} onChange={e => setQuery(e.target.value)} /></label>
          <label className="library-dataset"><span>{t('Dataset', '数据集')}</span><select value={dataset} onChange={e => { setDataset(e.target.value); setQuery(''); }}>
            <option value="">{t('All datasets', '全部数据集')}</option>
            {Object.entries(index?.datasets ?? {}).map(([name, count]) => <option value={name} key={name}>{name} · {count}</option>)}
          </select></label>
          <div className="library-list-count">{filtered.length} {t('matching cases', '个匹配病例')}</div>
          <div className="library-case-list">
            {filtered.map(c => <button className="library-case-button" key={c.case_id} aria-current={caseId === c.case_id ? 'true' : undefined} onClick={() => selectCase(c.case_id)}>
              <span>{c.dataset}</span><b>{c.case_id}</b><small>{c.inquiry_count} {t('inquiries', '问询')} · {c.operation_count} {t('examinations', '检查')}</small>
            </button>)}
            {index && !filtered.length ? <p className="library-empty">{t('No cases match. Try another ID or dataset.', '没有匹配的病例，请更换 ID 或数据集。')}</p> : null}
          </div>
        </aside>
        <section className="library-workspace">
          {index && caseId ? <CaseDetail key={caseId + locale} caseId={caseId} index={index} /> : <p className="library-loading"><LoaderCircle className="animate-spin" />{t('Loading case library…', '正在加载病例库…')}</p>}
        </section>
      </div>
    </main>
  );
}

function CaseDetail({ caseId, index }: { caseId: string; index: Index }) {
  const { isChinese: zh, locale } = useLanguage();
  const t = (en: string, cn: string) => zh ? cn : en;
  const [data, setData] = useState<Detail | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [tab, setTab] = useState('overview');
  const [search, setSearch] = useState('');
  const [kind, setKind] = useState('');
  const [recordedOnly, setRecordedOnly] = useState(true);
  const [page, setPage] = useState(0);
  const [scope, setScope] = useState('case');
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    api<Detail>(`/research/case-library/${encodeURIComponent(caseId)}`, { headers: HEADERS, signal: controller.signal })
      .then(result => { setData(result); setError(''); })
      .catch((e: Error) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [caseId, locale, attempt]);
  const actions = useMemo(() => {
    if (!data) return [];
    const recorded = new Map(data.actions.map(a => [a.id, a]));
    return index.items.filter(item =>
      (!kind || kind === item.kind) && (!recordedOnly || recorded.has(item.id)))
      .map(item => ({ ...item, recorded: recorded.get(item.id) }))
      .filter(item => `${item.id} ${item.label[locale]} ${item.category} ${item.recorded ? JSON.stringify(item.recorded.records) : ''}`.toLowerCase().includes(search.toLowerCase()));
  }, [data, index.items, kind, recordedOnly, search, locale]);
  const evidence = useMemo(() => data?.model_evidence.filter(e =>
    `${e.evidence_id} ${e.question} ${e.status} ${e.display_answer}`.toLowerCase().includes(search.toLowerCase())) ?? [], [data, search]);
  const count = tab === 'model' ? evidence.length : actions.length;
  const pages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const currentPage = Math.min(page, pages - 1);
  async function download(format: 'json' | 'xlsx') {
    if (!data) return;
    setBusy(format); setNotice('');
    try {
      const url = new URL('/research/case-library/export', API_BASE);
      url.searchParams.set('format', format); url.searchParams.set('lang', locale);
      if (scope === 'case') url.searchParams.set('case_id', caseId);
      if (scope === 'dataset') url.searchParams.set('dataset', data.dataset);
      const response = await fetch(url, { headers: HEADERS });
      if (!response.ok) {
        const failure = await response.json().catch(() => ({})) as { detail?: string };
        throw new Error(failure.detail ?? `Export failed (${response.status})`);
      }
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = `${scope === 'case' ? caseId : scope === 'dataset' ? data.dataset : 'all_cases'}_${locale}.${format}`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      setNotice(t('Download ready.', '导出已完成，文件已下载。'));
    } catch (e) { setNotice(e instanceof Error ? e.message : t('Export failed', '导出失败')); }
    finally { setBusy(''); }
  }
  if (error) return <div className="library-error" role="alert">{error} <button onClick={() => setAttempt(a => a + 1)}>{t('Retry', '重试')}</button></div>;
  if (!data) return <p className="library-loading"><LoaderCircle className="animate-spin" />{t('Reading case evidence…', '正在读取病例证据…')}</p>;
  const stats = [{ icon: <MessageCircle />, value: data.actions.filter(a => a.kind === 'inquiry').length, text: t('Inquiries with answers', '有答案的问询') },
    { icon: <Stethoscope />, value: data.actions.filter(a => a.kind === 'operation').length, text: t('Recorded examinations', '有结果的检查') },
    { icon: <Braces />, value: data.model_evidence.length, text: t('Model evidence fields', '模型证据字段') }];
  return <div className="library-detail">
    <header className="library-detail-heading">
      <div><span className="library-dataset-badge">{data.dataset}</span><h2>{caseId}</h2><p>{t('Research preview · Fixed answers and references are visible here.', '研究预览 · 可查看固定答案和参考诊断。')}</p></div>
      <div className="library-exports">
        <select aria-label={t('Export scope', '导出范围')} value={scope} onChange={e => setScope(e.target.value)}>
          <option value="case">{t('This case', '当前病例')}</option><option value="dataset">{t('This dataset', '当前病例所在数据集')}</option><option value="all">{t('All cases', '全部病例')}</option>
        </select>
        <button disabled={Boolean(busy)} onClick={() => void download('json')}><Download size={15} />{busy === 'json' ? t('Exporting…', '导出中…') : 'JSON'}</button>
        <button className="library-excel" disabled={Boolean(busy)} onClick={() => void download('xlsx')}><FileSpreadsheet size={15} />{busy === 'xlsx' ? t('Exporting…', '导出中…') : 'Excel'}</button>
      </div>
    </header>
    <output className="library-notice">{notice}</output>
    <div className="library-stats">{stats.map(s => <div key={s.text}>{s.icon}<span><b>{s.value}</b><small>{s.text}</small></span></div>)}</div>
    <nav className="library-tabs" aria-label={t('Case sections', '病例查看分区')}>
      {[['overview', t('Initial information', '初始信息')], ['actions', t('Selectable actions', '问询 / 检查')], ['model', t('Model evidence pool', '模型证据池')], ['reference', t('Reference & source', '诊断参考 / 来源')], ['json', 'JSON']].map(([id, label]) =>
        <button key={id} aria-current={tab === id ? 'page' : undefined} onClick={() => { setTab(id); setSearch(''); setPage(0); }}>{label}</button>)}
    </nav>
    {tab === 'overview' ? <>
      <article className="library-panel library-initial"><div className="library-panel-title"><span>01</span><h3>{t('What is known at the start?', '开局已经知道什么？')}</h3><CheckCircle2 size={17} /></div>
        <div className="library-demographics"><span>{t('Age', '年龄')} <b><ResultValue value={data.initial_information.demographics.age} chinese={zh} caseId={caseId} /></b></span><span>{t('Sex', '性别')} <b>{statuses[data.initial_information.demographics.sex]?.[zh ? 1 : 0] ?? data.initial_information.demographics.sex}</b></span><span>{t('Evidence access', '证据获取')} <b>{t('Self-directed, no clock', '自主选择，无模拟时钟')}</b></span></div>
        <div className="library-presentation"><ResultValue value={data.initial_information.presentation} chinese={zh} caseId={caseId} /></div>
      </article>
      <div className="library-overview-links">{[['actions', t('Explore questions and examinations', '查看可以问什么、检查什么'), t('Open each action to inspect its fixed answer and source record.', '按动作展开，查看固定答案及源记录。')], ['model', t('Inspect the model evidence pool', '查看模型拿到的证据池'), t('Evidence IDs, parent rules, status and answers.', '查看证据 ID、父项条件、状态和固定回答。')]].map(([id, title, text]) =>
        <button key={id} onClick={() => setTab(id)}><b>{title}</b><span>{text}</span><ChevronRight /></button>)}</div>
      {data.media.length ? <article className="library-panel"><h3>{t('Original images & reports', '原始图像与报告')}</h3>{data.media.map(m => <a key={m.asset} href={`${API_BASE}${m.url}`} target="_blank" rel="noreferrer">{m.asset}</a>)}</article> : null}
    </> : null}
    {tab === 'actions' || tab === 'model' ? <>
      <div className="library-filter-bar">
        <label className="library-search"><Search size={16} /><input aria-label={t('Search evidence', '搜索证据')} value={search} placeholder={t('Search ID, question, result…', '搜索 ID、问题、结果…')} onChange={e => { setSearch(e.target.value); setPage(0); }} /></label>
        {tab === 'actions' ? <><select aria-label={t('Action type', '动作类型')} value={kind} onChange={e => { setKind(e.target.value); setPage(0); }}><option value="">{t('All types', '全部类型')}</option><option value="inquiry">{t('Inquiries', '问询')}</option><option value="operation">{t('Examinations', '检查 / 操作')}</option></select>
          <label className="library-check"><input type="checkbox" checked={recordedOnly} onChange={e => { setRecordedOnly(e.target.checked); setPage(0); }} />{t('Recorded results only', '仅看有记录结果')}</label></> : null}
      </div>
      <p className="library-explanation"><ListFilter size={15} />{tab === 'model' ? t('This is the canonical model pool. INITIAL is already known; CONDITIONAL is a parent evidence rule, not clinical chronology.', '这是模型协议的证据池：INITIAL 为初始已知，CONDITIONAL 为父证据条件，与临床检查时序无关。') : t('Uncheck the filter to see the shared action library. Unrecorded items have no source result in this case.', '取消“仅看有记录结果”，可查看共享动作全集；未记录项在本病例中没有源结果。')}</p>
      <div className="library-evidence-list">
        {tab === 'actions' ? actions.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE).map(item =>
          <details className="library-evidence" key={item.id} data-kind={item.kind}>
            <summary><span className="library-type-icon">{item.kind === 'inquiry' ? <MessageCircle size={17} /> : <Stethoscope size={17} />}</span><div><b>{item.label[locale]}</b><small><code>{item.id}</code> · {zh ? categories[item.category] ?? item.category : item.category}</small></div><span className={`library-status ${item.recorded ? 'recorded' : 'missing'}`}>{item.id === 'inquiry:CHIEF' ? t('Initially known', '初始已知') : item.recorded ? t('Recorded', '已记录') : t('No recorded result', '无记录结果')}</span><ChevronRight size={16} /></summary>
            <div className="library-evidence-body">{item.recorded ? <>{item.recorded.partial_panel ? <p>{t('Only recorded panel components are returned.', '仅返回源记录中存在的检查分项。')}</p> : null}{item.recorded.records.map((record, i) =>
              <article key={`${record.source_id}:${i}`} className="library-result"><div className="library-result-source">{record.source_label ?? item.label[locale]}<code>{record.source_id}</code></div><ResultValue value={record.result} chinese={zh} caseId={caseId} /></article>)}</> :
              <p>{t('The shared menu contains this action, but this case has no fixed result. The system does not invent one.', '共享菜单中有此动作，但本病例没有固定结果；系统不会补造答案。')}</p>}</div>
          </details>) : evidence.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE).map(item =>
          <details className="library-evidence" key={item.evidence_id}><summary><span className="library-type-icon"><Braces size={17} /></span><div><b>{item.question}</b><small><code>{item.evidence_id}</code> · {item.access}</small></div><span className="library-status recorded">{statuses[item.status]?.[zh ? 1 : 0] ?? item.status}</span><ChevronRight size={16} /></summary><div className="library-evidence-body"><dl className="library-model-meta"><div><dt>{t('Parent evidence', '父证据')}</dt><dd>{item.parent_evidence_id ?? t('None', '无')}</dd></div><div><dt>{t('Action type', '动作类型')}</dt><dd>{item.action_kind}</dd></div></dl><ResultValue value={item.answer ?? item.display_answer} chinese={zh} caseId={caseId} /></div></details>)}
        {!count ? <p className="library-empty">{t('No matching evidence. Clear your filters.', '没有匹配证据，请调整筛选条件。')}</p> : null}
      </div>
      <footer className="library-pagination"><span>{count} {t('items', '项')} · {currentPage + 1} / {pages}</span><button aria-label={t('Previous page', '上一页')} disabled={!currentPage} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={17} /></button><button aria-label={t('Next page', '下一页')} disabled={currentPage >= pages - 1} onClick={() => setPage(currentPage + 1)}><ChevronRight size={17} /></button></footer>
    </> : null}
    {tab === 'reference' ? <><article className="library-panel library-reference"><h3>{t('Protected reference', '受保护的诊断参考')}</h3><p>{t('Visible for research review; it is hidden during an active clinical visit.', '此处用于研究审核，实际就诊过程中不会展示参考答案。')}</p><h4>{data.reference.oracle.display_name || data.reference.oracle.pathology}</h4><ResultValue value={data.reference.quality} chinese={zh} caseId={caseId} />{data.reference.oracle.differential.length ? <details><summary>{t('Differential diagnosis reference', '鉴别诊断参考')}</summary><ResultValue value={data.reference.oracle.differential} chinese={zh} caseId={caseId} /></details> : null}<p>{data.reference.fidelity_note}</p></article>
      <article className="library-panel"><h3>{t('Source & identity', '来源与身份信息')}</h3><ResultValue value={data.source} chinese={zh} caseId={caseId} /><details><summary>{t('Case metadata', '病例元数据')}</summary><ResultValue value={{ ...data.identity, case_hash: data.case_hash }} chinese={zh} caseId={caseId} /></details></article>
      {data.treatments.length ? <article className="library-panel"><h3>{t('Recorded treatment context', '已有治疗记录')}</h3>{data.treatments.map((r, i) => <details key={i}><summary>{r.label}</summary><ResultValue value={r.result} chinese={zh} caseId={caseId} /></details>)}</article> : null}</> : null}
    {tab === 'json' ? <article className="library-panel library-json"><header><h3>{t('Structured case JSON', '结构化病例 JSON')}</h3><button onClick={() => void navigator.clipboard.writeText(JSON.stringify(data, null, 2)).then(() => setNotice(t('JSON copied.', 'JSON 已复制。'))).catch(() => setNotice(t('Copy failed. Use JSON download.', '复制失败，请使用 JSON 下载。')))}><Clipboard size={16} />{t('Copy', '复制')}</button></header><pre>{JSON.stringify(data, null, 2)}</pre></article> : null}
  </div>;
}
