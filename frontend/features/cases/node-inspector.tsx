'use client';

import { useState } from 'react';
import { Search } from 'lucide-react';
import { useLanguage } from '@/features/i18n/language-context';
import {
  ResultValue,
  categories,
  statuses,
} from '@/features/arena/encounter-presentation';
import {
  reasons,
  forestNodeLabel,
  type EncounterForestNode,
} from '@/features/forest/encounter-forest-graph';
import { JsonView } from './json-cell';
import type { CaseDetail } from './types';

export function NodeInspector({
  node,
  detail,
  tab,
  caseId,
}: {
  node?: EncounterForestNode;
  detail: CaseDetail | null;
  tab: string;
  caseId: string;
}) {
  const { isChinese: zh } = useLanguage();
  const [query, setQuery] = useState('');
  const action = detail?.actions?.find((row) => row.id === node?.item?.id);
  const records = node?.example?.records?.length
    ? node.example.records
    : (action?.records ?? []);
  const showValue = (value: unknown) => (
    <ResultValue value={value} chinese={zh} caseId={caseId} />
  );
  if (tab === 'raw') return <JsonView value={node ?? detail} />;
  if (!node || node.event_type === 'INITIAL') {
    if (!detail)
      return (
        <p className="ws-muted">
          {zh ? '正在读取病例原始证据…' : 'Loading source evidence…'}
        </p>
      );
    return (
      <div className="ws-inspection-content">
        <h2>{zh ? '病例原始证据' : 'Case source evidence'}</h2>
        {tab !== 'evidence' ? (
          <>
            <section>
              <h3>{zh ? '初始信息' : 'Initial information'}</h3>
              {showValue(detail.initial_information)}
            </section>
            <section>
              <h3>{zh ? '诊断参考' : 'Diagnostic reference'}</h3>
              {showValue(
                detail.reference?.oracle ??
                  (zh ? '无参考诊断' : 'No reference available'),
              )}
            </section>
            <section>
              <h3>{zh ? '来源' : 'Source'}</h3>
              {showValue(detail.source ?? '—')}
            </section>
          </>
        ) : (
          <>
            <label className="ws-search">
              <Search size={14} />
              <input
                aria-label={zh ? '搜索证据' : 'Search evidence'}
                placeholder={zh ? '搜索 ID / 结果…' : 'Search ID / result…'}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            {(detail.actions ?? [])
              .filter((row) =>
                `${row.id} ${row.label[zh ? 'zh-CN' : 'en']} ${JSON.stringify(row.records)}`
                  .toLowerCase()
                  .includes(query.toLowerCase()),
              )
              .map((row) => (
                <details className="ws-source-action" key={row.id}>
                  <summary>
                    <b>{row.label[zh ? 'zh-CN' : 'en']}</b>
                    <code>{row.id}</code>
                    <span className="ws-pill">
                      {row.availability ?? 'RECORDED'} · {row.records.length}
                    </span>
                  </summary>
                  {row.records.map((record, i) => (
                    <article className="ws-source-record" key={i}>
                      <code>{record.source_id}</code>
                      {showValue(record.result)}
                    </article>
                  ))}
                </details>
              ))}
            {!detail.actions?.length && (
              <p className="ws-muted">
                {zh ? '暂无动作记录。' : 'No action records.'}
              </p>
            )}
            <details className="ws-source-action">
              <summary>
                {zh ? '模型证据池' : 'Model evidence pool'} ·{' '}
                {detail.model_evidence?.length ?? 0}
              </summary>
              {detail.model_evidence?.length ? (
                detail.model_evidence.map((row) => (
                  <article className="ws-source-record" key={row.evidence_id}>
                    <code>{row.evidence_id}</code>
                    <h3>{row.question}</h3>
                    {showValue(row.answer)}
                  </article>
                ))
              ) : (
                <p>{zh ? '暂无模型证据。' : 'No model evidence.'}</p>
              )}
            </details>
            <details className="ws-source-action">
              <summary>{zh ? '治疗记录 / 媒体' : 'Treatments / media'}</summary>
              {showValue({
                treatments: detail.treatments ?? [],
                media: detail.media ?? [],
              })}
            </details>
          </>
        )}
      </div>
    );
  }
  return (
    <div className="ws-inspection-content">
      <h2>{forestNodeLabel(node, zh)}</h2>
      {tab === 'details' ? (
        <>
          <dl className="ws-inspector-fields">
            {[
              [
                zh ? '动作类型' : 'Action type',
                node.item?.kind ?? node.event_type,
              ],
              [
                zh ? '分类' : 'Category',
                zh
                  ? (categories[node.item?.category ?? ''] ??
                    node.item?.category)
                  : node.item?.category,
              ],
              [
                zh ? '决策原因' : 'Reason',
                reasons[node.reason_id ?? '']?.[zh ? 1 : 0] ?? node.reason_id,
              ],
              [
                zh ? '结果状态' : 'Result status',
                statuses[node.result_status ?? '']?.[zh ? 1 : 0] ??
                  node.result_status,
              ],
              [zh ? '经过次数' : 'Traversals', node.count],
            ].map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value ?? (zh ? '未记录' : 'Not recorded')}</dd>
              </div>
            ))}
          </dl>
          <section>
            <h3>{zh ? '原因说明' : 'Rationale'}</h3>
            <p>
              {node.example?.reason_text ||
                (zh
                  ? '此节点未提供原因说明。'
                  : 'No rationale is available for this node.')}
            </p>
          </section>
          <section>
            <h3>{zh ? '诊断假设' : 'Working hypothesis'}</h3>
            <p>
              {node.example?.hypothesis ||
                (zh ? '未记录诊断假设。' : 'No hypothesis recorded.')}
            </p>
          </section>
        </>
      ) : (
        <>
          <h3>
            {zh ? '源记录' : 'Source records'} · {records.length}
          </h3>
          {records.length ? (
            records.map((record, index) => (
              <article className="ws-source-record" key={index}>
                <header>
                  <code>
                    {record.source_id ??
                      (zh ? '来源 ID 未记录' : 'Source ID not recorded')}
                  </code>
                  <span className="ws-pill recorded">
                    {node.result_status ?? action?.availability ?? 'RECORDED'}
                  </span>
                </header>
                {showValue(record.result)}
                <details>
                  <summary>{zh ? '原始记录' : 'Original record'}</summary>
                  <JsonView value={record} />
                </details>
              </article>
            ))
          ) : (
            <p className="ws-muted">
              {zh
                ? '此节点没有 example.records，也没有匹配的病例动作记录。'
                : 'No example records or matching case action records are available.'}
            </p>
          )}
          <section>
            <h3>{zh ? '诊断' : 'Diagnoses'}</h3>
            {showValue(
              node.example?.diagnoses?.length
                ? node.example.diagnoses
                : node.event_type === 'DIAGNOSIS'
                  ? node.label.replace(/^DIAGNOSIS: /, '')
                  : zh
                    ? '未记录'
                    : 'Not recorded',
            )}
          </section>
          <section>
            <h3>{zh ? '诊断假设' : 'Hypothesis'}</h3>
            {showValue(
              node.example?.hypothesis ?? (zh ? '未记录' : 'Not recorded'),
            )}
          </section>
          {node.example?.text && (
            <section>{showValue(node.example.text)}</section>
          )}
        </>
      )}
    </div>
  );
}
