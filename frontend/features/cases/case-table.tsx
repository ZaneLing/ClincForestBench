'use client';

import { memo } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown, ArrowUpRight } from 'lucide-react';
import Link from 'next/link';
import { useLanguage } from '@/features/i18n/language-context';
import type { CaseRow } from './types';
import { JsonCell } from './json-cell';

export const CASE_COLUMNS = [
  ['case_id', 'Case ID', '病例 ID'],
  ['status', 'Status', '状态'],
  ['dataset', 'Dataset', '数据集'],
  ['input', 'Input', '初始信息'],
  ['expected', 'Expected', '参考诊断'],
  ['counts', 'Counts', '问询记录'],
  ['actions', 'Actions', '操作'],
] as const;

export const CaseTable = memo(function CaseTable({
  rows,
  columns,
  selection,
  onSelect,
  onOpen,
  sort,
  direction,
  onSort,
  loading,
}: {
  rows: CaseRow[];
  columns: string[];
  selection: string[];
  onSelect: (ids: string[]) => void;
  onOpen: (id: string) => void;
  sort: string;
  direction: string;
  onSort: (key: string) => void;
  loading: boolean;
}) {
  const { isChinese: zh } = useLanguage();
  const toggle = (id: string) =>
    onSelect(
      selection.includes(id)
        ? selection.filter((value) => value !== id)
        : [...selection, id],
    );
  const visible = CASE_COLUMNS.filter(([id]) => columns.includes(id));
  const all =
    rows.length > 0 && rows.every((row) => selection.includes(row.case_id));
  return (
    <div className="ws-table-scroll">
      <table
        className="ws-table case-table"
        aria-label={zh ? '病例库' : 'Case library'}
      >
        <thead>
          <tr>
            <th className="ws-check-cell">
              <input
                type="checkbox"
                aria-label={zh ? '选择本页' : 'Select this page'}
                checked={all}
                disabled={!rows.length}
                onChange={() =>
                  onSelect(
                    all
                      ? selection.filter(
                          (id) => !rows.some((r) => r.case_id === id),
                        )
                      : [
                          ...new Set([
                            ...selection,
                            ...rows.map((r) => r.case_id),
                          ]),
                        ],
                  )
                }
              />
            </th>
            {visible.map(([id, en, cn]) => (
              <th key={id} className={`case-col-${id}`}>
                {['case_id', 'dataset', 'counts', 'status'].includes(id) ? (
                  <button onClick={() => onSort(id)}>
                    {zh ? cn : en}
                    {sort === id ? (
                      direction === 'desc' ? (
                        <ArrowDown size={12} />
                      ) : (
                        <ArrowUp size={12} />
                      )
                    ) : (
                      <ArrowUpDown size={12} />
                    )}
                  </button>
                ) : zh ? (
                  cn
                ) : (
                  en
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading
            ? Array.from({ length: 12 }, (_, i) => (
                <tr key={i} aria-hidden="true">
                  <td aria-label="Loading" colSpan={visible.length + 1}>
                    <div className="ws-skeleton" />
                  </td>
                </tr>
              ))
            : rows.map((row) => (
                <tr
                  key={row.case_id}
                  aria-selected={selection.includes(row.case_id)}
                  tabIndex={0}
                  onClick={(e) =>
                    e.metaKey || e.ctrlKey
                      ? toggle(row.case_id)
                      : onOpen(row.case_id)
                  }
                  onKeyDown={(e) => {
                    if (e.target !== e.currentTarget) return;
                    if (e.key === 'Enter') onOpen(row.case_id);
                    if (e.key === ' ') {
                      e.preventDefault();
                      toggle(row.case_id);
                    }
                  }}
                >
                  <td
                    className="ws-check-cell"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <input
                      type="checkbox"
                      aria-label={`${zh ? '选择' : 'Select'} ${row.case_id}`}
                      checked={selection.includes(row.case_id)}
                      onChange={() => toggle(row.case_id)}
                    />
                  </td>
                  {visible.map(([id]) => (
                    <td key={id} className={`case-col-${id}`}>
                      {id === 'case_id' && (
                        <span
                          className="ws-case-id ws-mono"
                          title={row.case_id}
                        >
                          {row.case_id}
                        </span>
                      )}
                      {id === 'status' && (
                        <span
                          className={`ws-pill ${row.inquiry_count + row.operation_count > 0 ? 'recorded' : ''}`}
                        >
                          {row.inquiry_count + row.operation_count > 0
                            ? 'RECORDED'
                            : 'NO_RECORDS'}
                        </span>
                      )}
                      {id === 'dataset' && <span>{row.dataset}</span>}
                      {id === 'input' &&
                        (row.initial_information ? (
                          <JsonCell
                            value={{
                              ...row.initial_information.demographics,
                              presentation:
                                row.initial_information.presentation,
                            }}
                          />
                        ) : (
                          <span className="ws-muted">
                            {JSON.stringify(row.demographics?.age ?? '—')} /{' '}
                            {row.demographics?.sex ?? '—'}{' '}
                            <span className="ws-mini-loading">…</span>
                          </span>
                        ))}
                      {id === 'expected' && (
                        <div className="ws-expected">
                          <span>
                            {row.reference?.oracle?.display_name ||
                              row.reference?.oracle?.pathology ||
                              '—'}
                          </span>
                          {row.reference?.oracle?.severity != null && (
                            <span className="ws-pill">
                              {zh ? '严重度' : 'Severity'}{' '}
                              {JSON.stringify(row.reference.oracle.severity)}
                            </span>
                          )}
                        </div>
                      )}
                      {id === 'counts' && (
                        <span className="ws-mono">
                          {row.counts?.inquiry?.recorded ?? row.inquiry_count}
                          <span className="ws-muted">
                            {' '}
                            / {row.counts?.inquiry?.total ?? '—'}
                          </span>
                        </span>
                      )}
                      {id === 'actions' && (
                        <Link
                          className="ws-icon-button"
                          href={`/cases/${encodeURIComponent(row.case_id)}`}
                          aria-label={`${zh ? '打开' : 'Open'} ${row.case_id}`}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <ArrowUpRight size={15} />
                        </Link>
                      )}
                    </td>
                  ))}
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  );
});
