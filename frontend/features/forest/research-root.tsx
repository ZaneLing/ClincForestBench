'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { ChevronRight, Database, Microscope, Stethoscope } from 'lucide-react';
import { api } from '@/lib/api';
import type { TemporalManifest } from '@/features/temporal/types';
import { TemporalCaseInspector } from '@/features/temporal/temporal-case-inspector';
import { useLanguage } from '@/features/i18n/language-context';
import type { CaseTreeManifest } from './case-tree-types';
import { ResearchDashboard } from './research-dashboard';

type UnifiedCaseEntry = {
  key: string;
  caseId: string;
  datasetName: string;
  label: string;
  source: 'classic' | 'temporal';
};

export function ResearchRoot() {
  const { isChinese } = useLanguage();
  const [entries, setEntries] = useState<UnifiedCaseEntry[]>([]);
  const [dataset, setDataset] = useState('');
  const [entryKey, setEntryKey] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    const headers = { 'X-Research-Key': 'local-research-only' };
    void Promise.all([
      api<CaseTreeManifest>('/research/case-trees', { headers }),
      api<TemporalManifest>('/research/temporal/cases', { headers }),
    ])
      .then(([classicManifest, temporalManifest]) => {
        if (!active) return;
        const merged: UnifiedCaseEntry[] = [
          ...classicManifest.cases.map((item) => ({
            key: `classic:${item.case_id}`,
            caseId: item.case_id,
            datasetName: item.dataset_name,
            label: `${item.case_id} · ${item.pathology}`,
            source: 'classic' as const,
          })),
          ...temporalManifest.cases.map((item) => ({
            key: `temporal:${item.case_id}`,
            caseId: item.case_id,
            datasetName: item.dataset_name,
            label: `${item.case_id} · ${item.event_count} events`,
            source: 'temporal' as const,
          })),
        ];
        setEntries(merged);
        const requestedCase = new URLSearchParams(window.location.search).get('case');
        const first = merged.find((item) => item.caseId === requestedCase) ?? merged[0];
        if (first) {
          setDataset(first.datasetName);
          setEntryKey(first.key);
          syncUrl(first.caseId);
        }
      })
      .catch((reason: Error) => {
        if (active) setError(reason.message);
      });
    return () => {
      active = false;
    };
  }, []);

  const datasets = useMemo(
    () => Array.from(new Set(entries.map((item) => item.datasetName))).sort(),
    [entries],
  );
  const visibleEntries = useMemo(
    () => entries.filter((item) => item.datasetName === dataset),
    [dataset, entries],
  );
  const selected = entries.find((item) => item.key === entryKey);

  function selectDataset(nextDataset: string) {
    setDataset(nextDataset);
    const first = entries.find((item) => item.datasetName === nextDataset);
    if (first) {
      setEntryKey(first.key);
      syncUrl(first.caseId);
    }
  }

  function selectCase(nextKey: string) {
    setEntryKey(nextKey);
    const next = entries.find((item) => item.key === nextKey);
    if (next) syncUrl(next.caseId);
  }

  return (
    <main className="unified-research-page">
      <header className="unified-research-header">
        <div className="unified-research-brand">
          <span><Microscope /></span>
          <div>
            <small>ClincForestBench · Case Inspector</small>
            <h1>{isChinese ? '病例转换与 Ground-truth 树' : 'Case conversion and ground-truth trees'}</h1>
          </div>
        </div>
        <div className="unified-case-selectors">
          <label htmlFor="unified-dataset-picker">
            <span><Database />{isChinese ? '数据集' : 'Dataset'}</span>
            <select
              disabled={!entries.length}
              id="unified-dataset-picker"
              onChange={(event) => selectDataset(event.target.value)}
              value={dataset}
            >
              {datasets.map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </label>
          <label htmlFor="unified-case-picker">
            <span><Stethoscope />Case</span>
            <select
              disabled={!visibleEntries.length}
              id="unified-case-picker"
              onChange={(event) => selectCase(event.target.value)}
              value={entryKey}
            >
              {visibleEntries.map((item) => (
                <option key={item.key} value={item.key}>{item.label}</option>
              ))}
            </select>
          </label>
          <Link className="audit-nav-link" href="/arena">
            {isChinese ? '进入 Arena' : 'Open Arena'} <ChevronRight />
          </Link>
        </div>
      </header>

      <section className="unified-research-content">
        {error ? (
          <div className="unified-research-error" role="alert">{error}</div>
        ) : selected?.source === 'temporal' ? (
          <TemporalCaseInspector embedded key={selected.key} selectedCaseId={selected.caseId} />
        ) : selected ? (
          <ResearchDashboard key={selected.key} selectedCaseId={selected.caseId} />
        ) : (
          <section className="audit-empty"><Database /><b>{isChinese ? '正在读取病例索引' : 'Loading case index'}</b></section>
        )}
      </section>
    </main>
  );
}

function syncUrl(caseId: string) {
  const url = new URL(window.location.href);
  url.searchParams.set('case', caseId);
  url.searchParams.delete('mode');
  window.history.replaceState({}, '', url);
}
