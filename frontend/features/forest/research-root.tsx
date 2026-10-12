'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { TemporalCaseInspector } from '@/features/temporal/temporal-case-inspector';
import { useLanguage } from '@/features/i18n/language-context';
import { ResearchDashboard } from './research-dashboard';
import {
  EncounterCaseInspector,
  type InspectionCatalog,
} from './encounter-case-inspector';
import '@/features/arena/encounter.css';
import './encounter-case-inspector.css';

const headers = { 'X-Research-Key': 'local-research-only' };

export function ResearchRoot() {
  const { isChinese: zh } = useLanguage();
  const t = (en: string, cn: string) => (zh ? cn : en);
  const [catalog, setCatalog] = useState<InspectionCatalog | null>(null);
  const [dataset, setDataset] = useState('');
  const [caseId, setCaseId] = useState('');
  const [mode, setMode] = useState<'library' | 'source'>('library');
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    api<InspectionCatalog>('/research/encounter-cases', { headers })
      .then((data) => {
        if (!live) return;
        setCatalog(data);
        setError('');
        const params = new URLSearchParams(window.location.search);
        const first =
          data.cases.find((c) => c.case_id === params.get('case')) ??
          data.cases[0];
        if (first) {
          setCaseId(first.case_id);
          setDataset(first.dataset);
        }
        setMode(params.get('view') === 'source' ? 'source' : 'library');
      })
      .catch((e: Error) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [attempt]);

  const selected = catalog?.cases.find((c) => c.case_id === caseId);
  function navigate(nextId: string, nextMode = mode) {
    setCaseId(nextId);
    setMode(nextMode);
    const url = new URL(window.location.href);
    url.searchParams.set('case', nextId);
    url.searchParams.set('view', nextMode);
    window.history.replaceState({}, '', url);
  }

  return (
    <main className="enc-page enc-workspace case-library-shell">
      <header className="enc-heading">
        <div>
          <p className="enc-eyebrow">CLINCFORESTBENCH / CASE INSPECTOR</p>
          <h1>{t('Cases by clinical library', '病例问询与操作映射')}</h1>
          <p>
            {t(
              'Read-only research view · contains case answers; does not create a visit.',
              '研究只读视图 · 含病例答案，不创建就诊或写入医生轨迹。',
            )}
          </p>
        </div>
        <Link href="/arena">{t('Open Arena', '进入医生工作台')}</Link>
      </header>
      <section
        className="enc-card case-library-toolbar"
        aria-label={t('Case selection', '病例选择')}
      >
        <label>
          {t('Dataset', '数据集')}
          <select
            value={dataset}
            disabled={!catalog}
            onChange={(e) => {
              setDataset(e.target.value);
              navigate(
                catalog?.cases.find((c) => c.dataset === e.target.value)
                  ?.case_id ?? '',
              );
            }}
          >
            {[...new Set(catalog?.cases.map((c) => c.dataset))].map((d) => (
              <option key={d}>{d}</option>
            ))}
          </select>
        </label>
        <label>
          {t('Case', '病例')}
          <select
            value={caseId}
            disabled={!catalog}
            onChange={(e) => navigate(e.target.value)}
          >
            {catalog?.cases
              .filter((c) => c.dataset === dataset)
              .map((c) => (
                <option key={c.case_id}>{c.case_id}</option>
              ))}
          </select>
        </label>
        <div className="enc-tabs" aria-label={t('Case view', '病例视图')}>
          <button
            aria-pressed={mode === 'library'}
            onClick={() => navigate(caseId, 'library')}
          >
            {t('Inquiry / operation mapping', '问询 / 操作映射')}
          </button>
          <button
            aria-pressed={mode === 'source'}
            onClick={() => navigate(caseId, 'source')}
          >
            {t('Source audit', '原始数据审计')}
          </button>
        </div>
      </section>
      {error ? (
        <div role="alert" className="enc-error">
          {error}{' '}
          <button onClick={() => setAttempt(attempt + 1)}>
            {t('Retry', '重试')}
          </button>
        </div>
      ) : selected && catalog ? (
        mode === 'library' ? (
          <EncounterCaseInspector
            key={caseId}
            caseId={caseId}
            catalog={catalog}
          />
        ) : (
          <div className="case-library-source">
            {selected.source === 'temporal' ? (
              <TemporalCaseInspector
                embedded
                key={caseId}
                selectedCaseId={caseId}
              />
            ) : (
              <ResearchDashboard key={caseId} selectedCaseId={caseId} />
            )}
          </div>
        )
      ) : (
        <output>{t('Loading case index…', '正在加载病例索引…')}</output>
      )}
    </main>
  );
}
