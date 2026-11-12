'use client';

import Link from 'next/link';
import { useLanguage } from '@/features/i18n/language-context';
import { JsonView } from '@/features/cases/json-cell';
import { ResultValue } from '@/features/arena/encounter-presentation';
import { metricLabel, metricId, type EvaluatedRun } from './metrics';

export function RunInspector({
  runs,
  tab,
}: {
  runs: EvaluatedRun[];
  tab: string;
}) {
  const { isChinese: zh } = useLanguage();
  if (tab === 'raw')
    return <JsonView value={runs.length === 1 ? runs[0] : runs} />;
  return (
    <div className="ws-inspection-content">
      {runs.map((detail) => (
        <section className="ws-run-review" key={detail.run.run_id}>
          <header>
            <strong className="ws-mono">{detail.run.case_id}</strong>
            <Link
              className="ws-button"
              href={`/cases/${encodeURIComponent(detail.run.case_id)}`}
            >
              {zh ? '查看病例 ↗' : 'Open case ↗'}
            </Link>
          </header>
          <p className="ws-muted ws-run-id">{detail.run.run_id}</p>
          <div className="ws-run-meta">
            <span
              className={`ws-pill ${detail.run.status === 'COMPLETED' ? 'recorded' : ''}`}
            >
              {detail.run.status}
            </span>
            <span>
              {detail.trajectory?.length ?? 0}{' '}
              {zh ? '个证据步骤' : 'evidence steps'}
            </span>
            <span>
              {detail.interactions?.length ?? 0}{' '}
              {zh ? '次交互' : 'interactions'}
            </span>
          </div>
          {tab === 'scores' ? (
            <>
              {detail.evaluation?.metrics?.length ? (
                <dl className="ws-inspector-fields">
                  {detail.evaluation.metrics.map((metric) => (
                    <div key={metricId(metric)}>
                      <dt>
                        {metricLabel({ ...metric, id: metricId(metric) }, zh)}
                      </dt>
                      <dd>
                        {metric.value ?? '—'} <small>{metric.direction}</small>
                      </dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="ws-metric-empty">
                  {zh
                    ? '此运行未提供 evaluation.metrics。'
                    : 'This run does not provide evaluation.metrics.'}
                </p>
              )}
              {detail.review && (
                <details className="ws-source-action" open>
                  <summary>
                    {zh ? '已有诊断审核' : 'Existing diagnostic review'}
                  </summary>
                  <ResultValue
                    value={detail.review.comparison}
                    chinese={zh}
                    caseId={detail.run.case_id}
                  />
                </details>
              )}
            </>
          ) : (
            <>
              {detail.run.last_error && (
                <div className="ws-error">
                  <p>{detail.run.last_error}</p>
                </div>
              )}
              {detail.review && (
                <details className="ws-source-action" open>
                  <summary>{zh ? '诊断审核' : 'Diagnostic review'}</summary>
                  <ResultValue
                    value={detail.review.comparison}
                    chinese={zh}
                    caseId={detail.run.case_id}
                  />
                </details>
              )}
              <details className="ws-source-action">
                <summary>
                  {zh ? '证据轨迹' : 'Evidence trajectory'} ·{' '}
                  {detail.trajectory?.length ?? 0}
                </summary>
                {detail.trajectory?.map((step) => (
                  <article
                    className="ws-source-record"
                    key={`${step.step}:${step.evidence_id}`}
                  >
                    <header>
                      <code>
                        {step.step} · {step.evidence_id}
                      </code>
                      <span className="ws-pill">{step.status}</span>
                    </header>
                    <h3>{step.question}</h3>
                    <ResultValue
                      value={step.answer}
                      chinese={zh}
                      caseId={detail.run.case_id}
                    />
                  </article>
                ))}
              </details>
              <details className="ws-source-action">
                <summary>
                  {zh ? '诊断更新' : 'Belief updates'} ·{' '}
                  {detail.belief_history?.length ?? 0}
                </summary>
                <JsonView value={detail.belief_history ?? []} />
              </details>
              <details className="ws-source-action">
                <summary>
                  {zh ? '模型交互' : 'Model interactions'} ·{' '}
                  {detail.interactions?.length ?? 0}
                </summary>
                {detail.interactions?.map((item) => (
                  <article
                    className="ws-source-record"
                    key={item.interaction_id}
                  >
                    <header>
                      <b>#{item.step}</b>
                      <span>
                        {item.latency_ms == null
                          ? '—'
                          : `${item.latency_ms} ms`}
                      </span>
                    </header>
                    <time>{item.created_at}</time>
                    <p>
                      {item.error ??
                        item.parsed_decision?.rationale ??
                        (zh ? '未记录解释' : 'No rationale recorded')}
                    </p>
                    <details>
                      <summary>
                        {zh ? '请求 / 响应 JSON' : 'Request / response JSON'}
                      </summary>
                      <JsonView
                        value={{
                          request: item.request_payload,
                          response: item.response_payload,
                        }}
                      />
                    </details>
                  </article>
                ))}
              </details>
            </>
          )}
        </section>
      ))}
      {!runs.length && (
        <div className="ws-empty">
          {zh ? '运行详情尚未加载。' : 'Run details are not available yet.'}
        </div>
      )}
    </div>
  );
}
