'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ArrowLeft,
  Columns3,
  Database,
  Download,
  Filter,
  Search,
  ChevronLeft,
  ChevronRight,
  X,
} from 'lucide-react';
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';
import { useWorkspaceQuery } from '@/components/shell/use-workspace-query';
import { useWorkspaceStatus } from '@/components/shell/status-bar';
import { useLanguage } from '@/features/i18n/language-context';
import { api } from '@/lib/api';
import { CaseTable, CASE_COLUMNS } from './case-table';
import {
  RESEARCH_HEADERS,
  referenceStrength,
  type CaseDetail,
  type CaseIndex,
  type CaseRow,
} from './types';
import './cases.css';

// Store compact row summaries only; full patient evidence is fetched on demand.
const summaryCache = new Map<string, Partial<CaseRow>>();
export function CaseLibraryPage() {
  const { isChinese: zh, locale } = useLanguage();
  const { params, update } = useWorkspaceQuery();
  const router = useRouter();
  const [index, setIndex] = useState<CaseIndex | null>(null);
  const [summaries, setSummaries] = useState<Record<string, Partial<CaseRow>>>(
    {},
  );
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const query = params.get('q') ?? '';
  const datasetQuery = params.get('dataset') ?? '';
  const datasets = useMemo(
    () => datasetQuery.split(',').filter(Boolean),
    [datasetQuery],
  );
  const caseType = params.get('case_type') ?? '';
  const operation = params.get('operation') ?? '';
  const strength = params.get('strength') ?? '';
  const sort = params.get('sort') ?? 'case_id';
  const direction = params.get('direction') ?? 'asc';
  const selection = (params.get('selected') ?? '').split(',').filter(Boolean);
  const columns = params.has('columns')
    ? (params.get('columns') ?? '').split(',')
    : CASE_COLUMNS.map(([id]) => id);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      api<CaseIndex>('/research/case-library', {
        headers: RESEARCH_HEADERS,
        signal: controller.signal,
      }).then((data) => {
        setIndex(data);
        setError('');
        return data;
      }),
      api<{ cases: { case_id: string; case_type?: string }[] }>('/cases', {
        signal: controller.signal,
      }),
    ])
      .then(([data, catalog]) => {
        const types = new Map(
          catalog.cases.map((row) => [row.case_id, row.case_type]),
        );
        setIndex({
          ...data,
          cases: data.cases.map((row) => ({
            ...row,
            case_type: types.get(row.case_id),
          })),
        });
        setError('');
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [attempt, locale]);
  const filtered = useMemo(() => {
    const datasetSet = new Set(datasets);
    const rows =
      index?.cases.filter(
        (row) =>
          (!datasetSet.size || datasetSet.has(row.dataset)) &&
          (!caseType || row.case_type === caseType) &&
          (!operation ||
            (operation === 'yes'
              ? row.operation_count > 0
              : row.operation_count === 0)) &&
          (!strength || referenceStrength(row) === strength) &&
          `${row.case_id} ${row.dataset}`
            .toLowerCase()
            .includes(query.toLowerCase()),
      ) ?? [];
    return rows.sort((a, b) => {
      const compare =
        sort === 'counts'
          ? a.inquiry_count - b.inquiry_count
          : sort === 'status'
            ? Number(a.inquiry_count + a.operation_count > 0) -
              Number(b.inquiry_count + b.operation_count > 0)
            : String(
                a[sort === 'dataset' ? 'dataset' : 'case_id'],
              ).localeCompare(
                String(b[sort === 'dataset' ? 'dataset' : 'case_id']),
              );
      return compare * (direction === 'desc' ? -1 : 1);
    });
  }, [index, datasets, caseType, operation, strength, query, sort, direction]);
  const pages = Math.max(1, Math.ceil(filtered.length / 50));
  const page = Math.max(1, Math.min(Number(params.get('page')) || 1, pages));
  const pageRows = filtered.slice((page - 1) * 50, page * 50);
  const pageIds = pageRows.map((row) => row.case_id).join(',');
  useEffect(() => {
    const controller = new AbortController();
    const ids = pageIds.split(',').filter(Boolean);
    let cursor = 0;
    const initial: Record<string, Partial<CaseRow>> = {};
    ids.forEach((id) => {
      const cached = summaryCache.get(`${locale}:${id}`);
      if (cached) initial[id] = cached;
    });
    async function worker() {
      while (cursor < ids.length && !controller.signal.aborted) {
        const id = ids[cursor++];
        if (initial[id]) continue;
        try {
          const data = await api<CaseDetail>(
            `/research/case-library/${encodeURIComponent(id)}`,
            { signal: controller.signal, headers: RESEARCH_HEADERS },
          );
          const summary = {
            initial_information: data.initial_information,
            reference: { oracle: data.reference?.oracle },
            counts: data.counts,
          };
          summaryCache.set(`${locale}:${id}`, summary);
          if (!controller.signal.aborted)
            setSummaries((current) => ({
              ...current,
              [`${locale}:${id}`]: summary,
            }));
        } catch (e) {
          if (!controller.signal.aborted)
            setError(
              zh
                ? `部分病例详情未能加载：${String(e)}`
                : `Some case details could not load: ${String(e)}`,
            );
        }
      }
    }
    for (let i = 0; i < 4; i++) void worker();
    return () => controller.abort();
  }, [pageIds, locale, attempt, zh]);
  useWorkspaceStatus([
    `${filtered.length} / ${index?.case_count ?? '—'} ${zh ? '病例' : 'cases'}`,
    `${Object.keys(index?.datasets ?? {}).length} ${zh ? '数据集' : 'datasets'}`,
    `${selection.length} ${zh ? '已选' : 'selected'}`,
  ]);
  const setFilter = (key: string, value: string) =>
    update({ [key]: value, page: null });
  function exportRows() {
    const rows = (
      selection.length
        ? (index?.cases.filter((row) => selection.includes(row.case_id)) ?? [])
        : filtered
    ).map((row) => ({
      ...row,
      ...summaryCache.get(`${locale}:${row.case_id}`),
    }));
    const url = URL.createObjectURL(
      new Blob(
        [
          JSON.stringify(
            { scope: 'case-library-summary', count: rows.length, cases: rows },
            null,
            2,
          ),
        ],
        { type: 'application/json' },
      ),
    );
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'medtree-cases.json';
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const filterCount =
    datasets.length +
    Number(Boolean(caseType)) +
    Number(Boolean(operation)) +
    Number(Boolean(strength));
  return (
    <main className="ws-page case-library-page">
      <header className="ws-page-heading">
        <div className="ws-heading-icon">
          <Database size={20} />
        </div>
        <div>
          <h1>{zh ? '病例库' : 'Cases'}</h1>
          <p>
            {zh
              ? '浏览初始信息、固定证据与诊断参考'
              : 'Explore initial information, evidence and diagnostic references'}
          </p>
        </div>
        <span className="ws-pill">
          {index?.case_count ?? '…'} {zh ? '病例' : 'cases'}
        </span>
      </header>
      <div className="ws-toolbar">
        <button
          className="ws-icon-button"
          aria-label={zh ? '返回' : 'Go back'}
          onClick={() => router.back()}
        >
          <ArrowLeft size={16} />
        </button>
        <label className="ws-search">
          <Search size={15} />
          <input
            value={query}
            onChange={(e) => update({ q: e.target.value, page: null }, true)}
            placeholder={
              zh ? '搜索病例 ID、数据集…' : 'Search case ID, dataset…'
            }
            aria-label={zh ? '搜索病例' : 'Search cases'}
          />
        </label>
        <button className="ws-button" onClick={() => setFiltersOpen(true)}>
          <Filter size={14} />
          {zh ? '筛选' : 'Filters'}
          {filterCount > 0 && <span className="ws-pill">{filterCount}</span>}
        </button>
        <details className="ws-columns-menu">
          <summary className="ws-button">
            <Columns3 size={14} />
            {zh ? '列' : 'Columns'} {columns.length}/7
          </summary>
          <div className="ws-menu">
            {CASE_COLUMNS.map(([id, en, cn]) => (
              <label key={id}>
                <input
                  type="checkbox"
                  checked={columns.includes(id)}
                  disabled={id === 'case_id'}
                  onChange={() =>
                    update({
                      columns: (columns.includes(id)
                        ? columns.filter((c) => c !== id)
                        : [...columns, id]
                      ).join(','),
                    })
                  }
                />
                {zh ? cn : en}
              </label>
            ))}
          </div>
        </details>
        <button className="ws-button" disabled={!index} onClick={exportRows}>
          <Download size={14} />
          {zh ? '导出' : 'Export'}
        </button>
      </div>
      {selection.length > 0 && (
        <div className="ws-selection">
          <b>
            {selection.length} {zh ? '已选病例' : 'selected cases'}
          </b>
          <button
            className="ws-button"
            onClick={() =>
              router.push(
                `/compare?tab=case&cases=${encodeURIComponent(selection.join(','))}`,
              )
            }
          >
            {zh ? '加入对比' : 'Add to comparison'}
          </button>
          <button
            className="ws-icon-button"
            aria-label={zh ? '清空选择' : 'Clear selection'}
            onClick={() => update({ selected: null })}
          >
            <X size={14} />
          </button>
        </div>
      )}
      {error && (
        <div className="ws-error" role="alert">
          {error}
          <button
            className="ws-button"
            onClick={() => {
              setError('');
              setAttempt((a) => a + 1);
            }}
          >
            {zh ? '重试' : 'Retry'}
          </button>
        </div>
      )}
      <CaseTable
        rows={pageRows.map((row) => ({
          ...row,
          ...summaryCache.get(`${locale}:${row.case_id}`),
          ...summaries[`${locale}:${row.case_id}`],
        }))}
        columns={columns}
        selection={selection}
        onSelect={(ids) => update({ selected: ids.join(',') })}
        onOpen={(id) => router.push(`/cases/${encodeURIComponent(id)}`)}
        sort={sort}
        direction={direction}
        onSort={(key) =>
          update({
            sort: key,
            direction: sort === key && direction === 'asc' ? 'desc' : 'asc',
            page: null,
          })
        }
        loading={!index}
      />
      {index && !filtered.length && (
        <div className="ws-empty">
          {zh
            ? '没有匹配病例，请调整筛选。'
            : 'No matching cases. Adjust your filters.'}
          <button
            className="ws-button"
            onClick={() =>
              update({
                q: null,
                dataset: null,
                case_type: null,
                operation: null,
                strength: null,
              })
            }
          >
            {zh ? '重置筛选' : 'Reset filters'}
          </button>
        </div>
      )}
      <footer className="ws-pagination">
        <span>
          {filtered.length ? (page - 1) * 50 + 1 : 0}–
          {Math.min(page * 50, filtered.length)} / {filtered.length} ·{' '}
          {zh ? '每页 50 例' : '50 per page'}
        </span>
        <button
          className="ws-icon-button"
          aria-label={zh ? '上一页' : 'Previous page'}
          disabled={page <= 1}
          onClick={() => update({ page: String(page - 1) })}
        >
          <ChevronLeft size={16} />
        </button>
        <span>
          {page} / {pages}
        </span>
        <button
          className="ws-icon-button"
          aria-label={zh ? '下一页' : 'Next page'}
          disabled={page >= pages}
          onClick={() => update({ page: String(page + 1) })}
        >
          <ChevronRight size={16} />
        </button>
      </footer>
      <Sheet open={filtersOpen} onOpenChange={setFiltersOpen}>
        <SheetContent className="ws-filter-sheet">
          <SheetTitle>{zh ? '筛选病例' : 'Filter cases'}</SheetTitle>
          <SheetDescription>
            {filtered.length} {zh ? '个匹配病例' : 'matching cases'}
          </SheetDescription>
          <fieldset>
            <legend>
              {zh ? '数据集' : 'Dataset'} ·{' '}
              {Object.keys(index?.datasets ?? {}).length}
            </legend>
            {Object.entries(index?.datasets ?? {}).map(([name, count]) => (
              <label key={name}>
                <input
                  type="checkbox"
                  checked={datasets.includes(name)}
                  onChange={() =>
                    setFilter(
                      'dataset',
                      (datasets.includes(name)
                        ? datasets.filter((d) => d !== name)
                        : [...datasets, name]
                      ).join(','),
                    )
                  }
                />
                <span>{name}</span>
                <small>{count}</small>
              </label>
            ))}
          </fieldset>
          <label>
            {zh ? '病例类型' : 'Case type'}
            <select
              value={caseType}
              onChange={(e) => setFilter('case_type', e.target.value)}
            >
              <option value="">{zh ? '全部' : 'All'}</option>
              {[
                ...new Set(
                  index?.cases
                    .map((r) => r.case_type)
                    .filter((value): value is string => Boolean(value)),
                ),
              ]
                .sort((a, b) => a.localeCompare(b))
                .map((type) => (
                  <option key={type}>{type}</option>
                ))}
            </select>
          </label>
          <label>
            {zh ? '检查记录' : 'Operation records'}
            <select
              value={operation}
              onChange={(e) => setFilter('operation', e.target.value)}
            >
              <option value="">{zh ? '全部' : 'All'}</option>
              <option value="yes">{zh ? '有记录' : 'With records'}</option>
              <option value="no">{zh ? '无记录' : 'No records'}</option>
            </select>
          </label>
          <label>
            {zh ? '参考强度' : 'Reference strength'}
            <select
              value={strength}
              onChange={(e) => setFilter('strength', e.target.value)}
            >
              <option value="">{zh ? '全部' : 'All'}</option>
              {[...new Set(index?.cases.map(referenceStrength))]
                .sort()
                .map((value) => (
                  <option key={value}>{value}</option>
                ))}
            </select>
          </label>
          <button
            className="ws-button"
            onClick={() =>
              update({
                dataset: null,
                case_type: null,
                operation: null,
                strength: null,
                page: null,
              })
            }
          >
            {zh ? '重置筛选' : 'Reset filters'}
          </button>
        </SheetContent>
      </Sheet>
    </main>
  );
}
