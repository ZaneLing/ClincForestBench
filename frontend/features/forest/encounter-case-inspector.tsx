'use client';

import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { useLanguage } from '@/features/i18n/language-context';
import { PageControls, PagedReader } from '@/features/arena/paged-reader';
import {
  categories,
  ResultValue,
} from '@/features/arena/encounter-presentation';

type Item = {
  id: string;
  kind: 'inquiry' | 'operation';
  category: string;
  label: { en: string; 'zh-CN': string };
};
export type InspectionCatalog = {
  items: Item[];
  cases: { case_id: string; dataset: string; source: 'classic' | 'temporal' }[];
};
type SourceRecord = {
  source_id: string;
  source_label?: string;
  result: unknown;
  partial_panel?: boolean;
  mapping_method?: string;
  source_time?: unknown;
};
type Inspection = {
  catalog_version: string;
  visit: { demographics: unknown; presentation: unknown };
  bindings: Record<string, SourceRecord[]>;
  counts: Record<'inquiry' | 'operation', { total: number; recorded: number }>;
  treatments: { source_id: string; label: string; result: unknown }[];
};

export function EncounterCaseInspector({
  caseId,
  catalog,
}: {
  caseId: string;
  catalog: InspectionCatalog;
}) {
  const { isChinese: zh, locale } = useLanguage();
  const t = (en: string, cn: string) => (zh ? cn : en);
  const [data, setData] = useState<Inspection | null>(null);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [kind, setKind] = useState<'inquiry' | 'operation'>('inquiry');
  const [availability, setAvailability] = useState('recorded');
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('');
  const [selectedId, setSelectedId] = useState('');
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(3);
  const [pane, setPane] = useState<'patient' | 'library' | 'result'>('library');
  const [resultTab, setResultTab] = useState<'answer' | 'treatment'>('answer');
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let live = true;
    api<Inspection>(`/research/encounter-cases/${encodeURIComponent(caseId)}`, {
      headers: { 'X-Research-Key': 'local-research-only' },
    })
      .then((value) => {
        if (live) {
          setData(value);
          setError('');
        }
      })
      .catch((e: Error) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [caseId, locale, attempt]);

  useEffect(() => {
    if (!list.current) return;
    const observer = new ResizeObserver(() => {
      if (list.current?.clientHeight)
        setPageSize(
          Math.max(1, Math.floor((list.current.clientHeight + 8) / 78)),
        );
    });
    observer.observe(list.current);
    return () => observer.disconnect();
  }, [data]);

  if (error)
    return (
      <div className="enc-error" role="alert">
        {error}{' '}
        <button onClick={() => setAttempt(attempt + 1)}>
          {t('Retry', '重试')}
        </button>
      </div>
    );
  if (!data)
    return <output>{t('Loading case mappings…', '正在加载病例映射…')}</output>;

  const items = catalog.items.filter((item) => {
    const recorded = !!data.bindings[item.id]?.length;
    return (
      item.kind === kind &&
      (!category || item.category === category) &&
      (availability === 'all' ||
        (availability === 'recorded' ? recorded : !recorded)) &&
      `${item.id} ${item.label.en} ${item.label['zh-CN']}`
        .toLowerCase()
        .includes(query.toLowerCase())
    );
  });
  const pages = Math.max(1, Math.ceil(items.length / pageSize));
  const safePage = Math.min(page, pages - 1);
  const selected = items.find((i) => i.id === selectedId) ?? items[0];
  const records = selected ? (data.bindings[selected.id] ?? []) : [];
  const label = (item: Item) =>
    zh ? (categories[item.category] ?? item.category) : item.category;

  return (
    <>
      <nav
        className="enc-pane-tabs"
        aria-label={t('Inspector panels', '病例面板')}
      >
        {(['patient', 'library', 'result'] as const).map((p, i) => (
          <button key={p} aria-pressed={pane === p} onClick={() => setPane(p)}>
            {
              [
                t('Visit', '首诊'),
                t('Libraries', '问询 / 操作'),
                t('Results', '结果 / 治疗'),
              ][i]
            }
          </button>
        ))}
      </nav>
      <div className="enc-columns" data-pane={pane}>
        <section className="enc-card enc-patient">
          <h2>{t('Visit information', '首诊信息')}</h2>
          <PagedReader
            key={`${caseId}-${locale}`}
            chinese={zh}
            label={t('Visit information', '首诊信息')}
          >
            <ResultValue
              value={data.visit.demographics}
              chinese={zh}
              caseId={caseId}
            />
            <h3 className="enc-section-label">
              {t('Initial presentation', '首诊描述')}
            </h3>
            <ResultValue
              value={data.visit.presentation}
              chinese={zh}
              caseId={caseId}
            />
            <h3 className="enc-section-label">
              {t('Case coverage', '病例映射概况')}
            </h3>
            {(['inquiry', 'operation'] as const).map((k) => (
              <p key={k}>
                {k === 'inquiry'
                  ? t('Inquiries', '问询')
                  : t('Operations', '检查 / 操作')}
                ：{data.counts[k].recorded} / {data.counts[k].total}{' '}
                {t('recorded', '项有记录')}
              </p>
            ))}
            <p>
              {t('Source treatments', '源治疗记录')}：{data.treatments.length}
            </p>
            <p className="enc-muted">
              {t(
                'Missing answers or results end an Arena visit. Recorded negative answers remain valid results.',
                '工作台中选择没有答案或结果的项目会结束病例；有记录的阴性回答仍属于有效结果。',
              )}
            </p>
            <small>{data.catalog_version}</small>
          </PagedReader>
        </section>
        <section className="enc-card enc-library">
          <h2>{t('Shared clinical libraries', '共享问询与操作库')}</h2>
          <div className="enc-tabs">
            {(['inquiry', 'operation'] as const).map((k) => (
              <button
                key={k}
                aria-pressed={kind === k}
                onClick={() => {
                  setKind(k);
                  setCategory('');
                  setPage(0);
                  setSelectedId('');
                  setResultTab('answer');
                }}
              >
                {k === 'inquiry'
                  ? t('Inquiries', '问询库')
                  : t('Examinations / procedures', '检查 / 操作库')}{' '}
                ({data.counts[k].recorded}/{data.counts[k].total})
              </button>
            ))}
          </div>
          <input
            aria-label={t('Search clinical library', '搜索临床目录')}
            placeholder={t(
              'Search by name or catalog ID',
              '搜索中英文名称或目录 ID',
            )}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
          />
          <div className="case-library-filters">
            <select
              aria-label={t('Category', '分类')}
              value={category}
              onChange={(e) => {
                setCategory(e.target.value);
                setPage(0);
              }}
            >
              <option value="">{t('All categories', '全部分类')}</option>
              {[
                ...new Set(
                  catalog.items
                    .filter((i) => i.kind === kind)
                    .map((i) => i.category),
                ),
              ].map((c) => (
                <option value={c} key={c}>
                  {zh ? (categories[c] ?? c) : c}
                </option>
              ))}
            </select>
            <select
              aria-label={t('Record availability', '记录状态')}
              value={availability}
              onChange={(e) => {
                setAvailability(e.target.value);
                setPage(0);
              }}
            >
              <option value="recorded">{t('Recorded', '有记录')}</option>
              <option value="all">{t('All items', '全部项目')}</option>
              <option value="missing">{t('Not recorded', '未记录')}</option>
            </select>
          </div>
          <p className="enc-muted">
            {t(
              'Same catalog IDs and answers as the Arena. Click to inspect; no action is executed.',
              '与工作台使用相同目录 ID 和答案。点击仅查看，不执行操作。',
            )}
          </p>
          <div className="enc-items" ref={list}>
            {items
              .slice(safePage * pageSize, (safePage + 1) * pageSize)
              .map((item) => (
                <button
                  key={item.id}
                  aria-pressed={selected?.id === item.id}
                  title={item.label[locale]}
                  onClick={() => {
                    setSelectedId(item.id);
                    setResultTab('answer');
                    setPane('result');
                  }}
                >
                  <strong>{item.label[locale]}</strong>
                  <small>
                    {label(item)} ·{' '}
                    {data.bindings[item.id]?.length
                      ? t('Recorded', '有记录')
                      : t('Not recorded · ends visit', '未记录 · 就诊将结束')}
                  </small>
                </button>
              ))}
            {!items.length && (
              <p>
                {t(
                  'No matching items. Change the filters to view the full library.',
                  '没有匹配项目，可调整筛选条件查看完整目录。',
                )}
              </p>
            )}
          </div>
          <div className="enc-library-footer">
            <small>
              {items.length} {t('items', '项')}
            </small>
            <PageControls
              page={safePage}
              pages={pages}
              onChange={(p) => {
                setPage(p);
                setSelectedId(items[p * pageSize]?.id ?? '');
              }}
              chinese={zh}
              label={t('Clinical library', '临床目录')}
            />
          </div>
        </section>
        <section className="enc-card enc-timeline">
          <div className="enc-tabs">
            <button
              aria-pressed={resultTab === 'answer'}
              onClick={() => setResultTab('answer')}
            >
              {t('Answer / result', '答案 / 结果')}
            </button>
            <button
              aria-pressed={resultTab === 'treatment'}
              onClick={() => setResultTab('treatment')}
            >
              {t('Source treatments', '源治疗记录')} ({data.treatments.length})
            </button>
          </div>
          <PagedReader
            key={`${caseId}-${selected?.id}-${resultTab}-${locale}`}
            chinese={zh}
            label={t('Mapped case content', '病例映射内容')}
          >
            {resultTab === 'treatment' ? (
              <>
                <h2>{t('Source treatment records', '源治疗记录')}</h2>
                <p className="enc-muted">
                  {t(
                    'Source reference only, not a physician prescription or an executed order. Available after diagnosis in the Arena.',
                    '仅为病例源记录，不是医生提交的处方，也不执行医嘱。工作台在诊断后提供可选处方阶段。',
                  )}
                </p>
                {!data.treatments.length && (
                  <p>
                    {t(
                      'No source treatment stage in this case.',
                      '该病例没有源治疗记录，不提供处方阶段。',
                    )}
                  </p>
                )}
                {data.treatments.map((row, i) => (
                  <article key={`${row.source_id}-${i}`} className="enc-answer">
                    <h3>{row.label}</h3>
                    <ResultValue
                      value={row.result}
                      chinese={zh}
                      caseId={caseId}
                    />
                    <small>
                      {t('Source ID', '来源 ID')}：{row.source_id}
                    </small>
                  </article>
                ))}
              </>
            ) : selected ? (
              <>
                <h2>{selected.label[locale]}</h2>
                <p className="enc-muted">
                  {selected.id} · {label(selected)}
                </p>
                <p
                  className={records.length ? 'enc-step-status' : 'enc-missing'}
                >
                  {records.length
                    ? t(
                        'Recorded — the Arena returns the following content.',
                        '有记录 — 工作台返回以下内容。',
                      )
                    : t(
                        'Not recorded — selecting this item in the Arena ends the case and preserves the trajectory. This read-only preview does not end any visit.',
                        '未记录 — 在工作台选择此项会结束病例并保留轨迹。此处为只读预览，不会结束任何就诊。',
                      )}
                </p>
                {records.map((row, i) => (
                  <article key={`${row.source_id}-${i}`} className="enc-answer">
                    {row.source_label && <h3>{row.source_label}</h3>}
                    {row.partial_panel && (
                      <p className="enc-muted">
                        {t(
                          'Partial panel: only recorded components are shown.',
                          '部分检查组合：仅展示已记录分项。',
                        )}
                      </p>
                    )}
                    <ResultValue
                      value={row.result}
                      chinese={zh}
                      caseId={caseId}
                    />
                    <p className="case-source-id">
                      {t('Source ID', '来源 ID')}：{row.source_id}
                    </p>
                    {!!row.source_time && (
                      <details>
                        <summary>{t('Source timing', '源记录时间')}</summary>
                        <ResultValue
                          value={row.source_time}
                          chinese={zh}
                          caseId={caseId}
                        />
                      </details>
                    )}
                  </article>
                ))}
              </>
            ) : (
              <p>
                {t(
                  'Select an item from the library.',
                  '请从目录选择一个项目。',
                )}
              </p>
            )}
          </PagedReader>
        </section>
      </div>
    </>
  );
}
