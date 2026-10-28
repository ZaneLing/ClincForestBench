'use client';

import { useEffect, useState } from 'react';
import { MessageCircle, Stethoscope } from 'lucide-react';
import { api } from '@/lib/api';
import { useLanguage } from '@/features/i18n/language-context';
import { PagedReader } from '@/features/arena/paged-reader';
import { ResultValue } from '@/features/arena/encounter-presentation';

type Item = {
  id: string;
  kind: 'inquiry' | 'operation';
  label: { en: string; 'zh-CN': string };
};
export type InspectionCatalog = {
  items: Item[];
  cases: { case_id: string; dataset: string; source: 'evidence' }[];
};
type SourceRecord = {
  source_id: string;
  source_label?: string;
  result: unknown;
  partial_panel?: boolean;
};
type Inspection = { bindings: Record<string, SourceRecord[]> };

function CaseAnswer({
  value,
  chinese,
  caseId,
}: {
  value: unknown;
  chinese: boolean;
  caseId: string;
}) {
  if (
    value &&
    typeof value === 'object' &&
    !Array.isArray(value) &&
    'answer' in value &&
    Object.keys(value).every((key) =>
      ['answer', 'question', 'status'].includes(key),
    )
  ) {
    const answer = value as { question?: unknown; answer: unknown };
    return (
      <>
        {answer.question != null && (
          <div className="case-answer-context">
            <ResultValue
              value={answer.question}
              chinese={chinese}
              caseId={caseId}
            />
          </div>
        )}
        <ResultValue value={answer.answer} chinese={chinese} caseId={caseId} />
      </>
    );
  }
  return <ResultValue value={value} chinese={chinese} caseId={caseId} />;
}

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
  const [mobileKind, setMobileKind] = useState<'inquiry' | 'operation'>(
    'inquiry',
  );

  useEffect(() => {
    let live = true;
    api<Inspection>('/research/encounter-cases/' + encodeURIComponent(caseId), {
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

  if (error)
    return (
      <div className="case-sheet-message" role="alert">
        {error}{' '}
        <button onClick={() => setAttempt(attempt + 1)}>
          {t('Retry', '重试')}
        </button>
      </div>
    );
  if (!data)
    return (
      <output className="case-sheet-message">
        {t('Loading answers…', '正在加载问答…')}
      </output>
    );

  return (
    <>
      <nav
        className="case-sheet-mobile-tabs"
        aria-label={t('Question type', '问答类型')}
      >
        <button
          data-kind="inquiry"
          aria-pressed={mobileKind === 'inquiry'}
          onClick={() => setMobileKind('inquiry')}
        >
          <MessageCircle size={16} />
          {t('Inquiries', '问询')}
        </button>
        <button
          data-kind="operation"
          aria-pressed={mobileKind === 'operation'}
          onClick={() => setMobileKind('operation')}
        >
          <Stethoscope size={16} />
          {t('Examinations & procedures', '检查 / 操作')}
        </button>
      </nav>
      <div className="case-sheet-columns" data-mobile-kind={mobileKind}>
        {(['inquiry', 'operation'] as const).map((kind) => {
          const items = catalog.items.filter(
            (item) => item.kind === kind && data.bindings[item.id]?.length,
          );
          const heading =
            kind === 'inquiry'
              ? t('Inquiries', '问询')
              : t('Examinations & procedures', '检查 / 操作');
          return (
            <section
              className="case-sheet-column"
              data-kind={kind}
              key={kind}
              aria-label={heading}
            >
              <header className="case-column-header">
                <span className="case-column-icon">
                  {kind === 'inquiry' ? (
                    <MessageCircle size={19} />
                  ) : (
                    <Stethoscope size={19} />
                  )}
                </span>
                <h2>{heading}</h2>
                <span className="case-column-caption">
                  {kind === 'inquiry'
                    ? t('QUESTION / ANSWER', '问题 / 回答')
                    : t('ACTION / RESULT', '动作 / 结果')}
                </span>
              </header>
              {items.length ? (
                <PagedReader
                  key={caseId + locale + kind}
                  chinese={zh}
                  label={heading + t(' pages', '分页')}
                >
                  {items.map((item, index) => (
                    <article className="case-qa" key={item.id}>
                      <div className="case-qa-question">
                        <span className="case-qa-number">
                          {String(index + 1).padStart(2, '0')}
                        </span>
                        <h3>{item.label[locale]}</h3>
                      </div>
                      <div className="case-qa-answer">
                        {data.bindings[item.id].some(
                          (row) => row.partial_panel,
                        ) && (
                          <p className="case-partial">
                            {t('Recorded components only', '仅包含已记录分项')}
                          </p>
                        )}
                        {data.bindings[item.id].map((row, rowIndex) => (
                          <div
                            className="case-answer-record"
                            key={row.source_id + rowIndex}
                          >
                            {data.bindings[item.id].length > 1 &&
                              row.source_label &&
                              row.source_label !== item.label[locale] && (
                                <p className="case-answer-context">
                                  {row.source_label}
                                </p>
                              )}
                            <CaseAnswer
                              value={row.result}
                              chinese={zh}
                              caseId={caseId}
                            />
                          </div>
                        ))}
                      </div>
                    </article>
                  ))}
                </PagedReader>
              ) : (
                <p className="case-column-empty">
                  {kind === 'inquiry'
                    ? t(
                        'No recorded inquiry answers in this case.',
                        '该病例暂无问询记录。',
                      )
                    : t(
                        'No recorded examination or procedure results in this case.',
                        '该病例暂无检查或操作记录。',
                      )}
                </p>
              )}
            </section>
          );
        })}
      </div>
    </>
  );
}
