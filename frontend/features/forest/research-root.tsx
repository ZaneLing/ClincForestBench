'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { useLanguage } from '@/features/i18n/language-context';
import {
  EncounterCaseInspector,
  type InspectionCatalog,
} from './encounter-case-inspector';
import '@/features/arena/encounter.css';
import './encounter-case-inspector.css';

export function ResearchRoot() {
  const { isChinese: zh } = useLanguage();
  const t = (en: string, cn: string) => (zh ? cn : en);
  const [catalog, setCatalog] = useState<InspectionCatalog | null>(null);
  const [dataset, setDataset] = useState('');
  const [caseId, setCaseId] = useState('');
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    api<InspectionCatalog>('/research/encounter-cases', {
      headers: { 'X-Research-Key': 'local-research-only' },
    })
      .then((data) => {
        if (!live) return;
        setCatalog(data);
        setError('');
        const requested = new URLSearchParams(window.location.search).get(
          'case',
        );
        const first =
          data.cases.find((c) => c.case_id === requested) ?? data.cases[0];
        if (first) {
          setCaseId(first.case_id);
          setDataset(first.dataset);
        }
      })
      .catch((e: Error) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [attempt]);

  function selectCase(id: string) {
    setCaseId(id);
    const url = new URL(window.location.href);
    url.searchParams.set('case', id);
    url.searchParams.delete('view');
    window.history.replaceState({}, '', url);
  }

  return (
    <main className="case-sheet">
      <header className="case-sheet-header">
        <div className="case-sheet-title">
          <span className="case-sheet-mark" aria-hidden="true">
            C.
          </span>
          <div>
            <p>{t('CASE LIBRARY', 'CASE LIBRARY / 病例库')}</p>
            <h1>{t('Questions & answers', '病例问答')}</h1>
          </div>
        </div>
        <div className="case-sheet-selectors">
          <label>
            <span>{t('Dataset', '数据集')}</span>
            <select
              value={dataset}
              disabled={!catalog}
              onChange={(e) => {
                setDataset(e.target.value);
                selectCase(
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
            <span>{t('Case', '病例')}</span>
            <select
              value={caseId}
              disabled={!catalog}
              onChange={(e) => selectCase(e.target.value)}
            >
              {catalog?.cases
                .filter((c) => c.dataset === dataset)
                .map((c) => (
                  <option key={c.case_id}>{c.case_id}</option>
                ))}
            </select>
          </label>
        </div>
      </header>
      {error ? (
        <div className="case-sheet-message" role="alert">
          {error}{' '}
          <button onClick={() => setAttempt(attempt + 1)}>
            {t('Retry', '重试')}
          </button>
        </div>
      ) : caseId && catalog ? (
        <EncounterCaseInspector
          key={caseId}
          caseId={caseId}
          catalog={catalog}
        />
      ) : (
        <output className="case-sheet-message">
          {t('Loading cases…', '正在加载病例…')}
        </output>
      )}
    </main>
  );
}
