'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useLanguage } from '@/features/i18n/language-context';
import { api } from '@/lib/api';
import '@/features/arena/encounter.css';

type Forest = {
  session_count: number;
  nodes: {
    id: string;
    label: string;
    count: number;
    item?: { label: { en: string; 'zh-CN': string } };
    reason_id?: string;
    result_status?: string;
  }[];
  edges: { source: string; target: string; count: number }[];
  reason_counts: Record<string, number>;
};

export function EncounterForest() {
  const { locale, isChinese: zh } = useLanguage();
  const [key, setKey] = useState('');
  const [forest, setForest] = useState<Forest | null>(null);
  const [error, setError] = useState('');
  const reasons: Record<string, string> = zh
    ? {
        support: '支持诊断',
        differentiate: '鉴别诊断',
        urgent: '评估紧急情况',
        severity: '严重程度与治疗适用性',
        other: '其他',
      }
    : {
        support: 'Support diagnosis',
        differentiate: 'Differentiate',
        urgent: 'Assess urgency',
        severity: 'Severity and treatment suitability',
        other: 'Other',
      };
  function branch(id: string, depth = 0): React.ReactNode {
    const node = forest?.nodes.find((n) => n.id === id);
    if (!node) return null;
    const children = forest?.edges.filter((e) => e.source === id) ?? [];
    return (
      <details
        key={id}
        open={depth < 2}
        style={{ marginLeft: depth > 0 && depth < 5 ? 16 : 0, padding: '8px 0' }}
      >
        <summary>
          {node.item?.label[locale] ??
            (node.label === 'DIAGNOSIS'
              ? zh
                ? '诊断'
                : 'Diagnosis'
              : node.label === 'PRESCRIPTION'
                ? zh
                  ? '处方'
                  : 'Prescription'
                : node.label === 'COMPLETE'
                  ? zh
                    ? '完成'
                    : 'Complete'
                  : node.label)}{' '}
          {node.reason_id && ` · ${reasons[node.reason_id]}`} · {node.count}
          {node.result_status === 'NOT_RECORDED' &&
            (zh ? ' · 未记载' : ' · Not recorded')}
        </summary>
        {children.map((edge) => branch(edge.target, depth + 1))}
      </details>
    );
  }
  return (
    <main className="enc-page">
      <header className="enc-heading">
        <div>
          <p className="enc-eyebrow">CLINCFORESTBENCH / FOREST</p>
          <h1>
            {zh ? '医生操作与原因森林' : 'Clinical action and rationale forest'}
          </h1>
          <p>
            {zh
              ? '按病例、动作、原因和结果聚合决策路径。'
              : 'Paths grouped by case, action, reason and result.'}
          </p>
        </div>
        <div className="enc-row">
          <Link href="/forest?mode=classic">
            {zh ? '旧版经典森林' : 'Earlier classic forest'}
          </Link>
          <Link href="/forest?mode=temporal">
            {zh ? '旧版时序森林' : 'Earlier temporal forest'}
          </Link>
        </div>
      </header>
      <section className="enc-card">
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setError('');
            try {
              setForest(
                await api<Forest>('/research/encounter-forest', {
                  headers: { 'X-Research-Key': key },
                }),
              );
            } catch (err) {
              setError(err instanceof Error ? err.message : String(err));
            }
          }}
        >
          <label>
            {zh ? '研究密钥' : 'Research key'}
            <input
              type="password"
              value={key}
              onChange={(e) => setKey(e.target.value)}
            />
          </label>
          <button className="enc-primary" type="submit">
            {zh ? '加载森林' : 'Load forest'}
          </button>
        </form>
        {error && <p role="alert">{error}</p>}
      </section>
      {forest && (
        <>
          <section className="enc-card">
            <h2>
              {forest.session_count} {zh ? '条就诊轨迹' : 'visits'}
            </h2>
            <div className="enc-row">
              {Object.entries(forest.reason_counts).map(([id, count]) => (
                <span key={id}>
                  {reasons[id]}: {count}
                </span>
              ))}
            </div>
          </section>
          <section className="enc-card">
            {forest.nodes
              .filter((n) => !forest.edges.some((e) => e.target === n.id))
              .map((n) => branch(n.id))}
            {!forest.nodes.length && (
              <p>{zh ? '暂无轨迹。' : 'No trajectories yet.'}</p>
            )}
          </section>
        </>
      )}
    </main>
  );
}
