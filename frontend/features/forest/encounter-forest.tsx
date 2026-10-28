'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useLanguage } from '@/features/i18n/language-context';
import { api } from '@/lib/api';
import { EncounterForestGraph, type EncounterForestData } from './encounter-forest-graph';
import '@/features/arena/encounter.css';

export function EncounterForest() {
  const { isChinese: zh } = useLanguage();
  const params = useSearchParams();
  const caseId = params.get('case') ?? '';
  const simulation = params.get('simulation') === 'true';
  const [forest, setForest] = useState<EncounterForestData | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(true);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let live = true;
    const query = new URLSearchParams({ simulation: String(simulation) });
    if (caseId) query.set('case_id', caseId);
    api<EncounterForestData>(`/research/encounter-forest?${query}`).then(value => {
      if (live) { setForest(value); setError(''); }
    }).catch(err => {
      if (live) setError(err instanceof Error ? err.message : String(err));
    }).finally(() => {
      if (live) setBusy(false);
    });
    return () => { live = false; };
  }, [refresh, caseId, simulation, zh]);
  const reasons: Record<string, string> = zh
    ? { support: '支持诊断', differentiate: '鉴别诊断', urgent: '评估紧急情况', severity: '严重程度与治疗适用性', other: '其他' }
    : { support: 'Support diagnosis', differentiate: 'Differentiate', urgent: 'Assess urgency', severity: 'Severity and treatment suitability', other: 'Other' };
  const cases = caseId ? forest?.cases.filter(row => row.case_id === caseId) ?? [] : forest?.cases ?? [];
  const toggleLink = `/forest?${new URLSearchParams({ ...(caseId ? { case: caseId } : {}), simulation: String(!simulation) })}`;
  return <main className="enc-page">
    <header className="enc-heading">
      <div><p className="enc-eyebrow">CLINCFORESTBENCH / FOREST</p><h1>{simulation ? zh ? '模拟案例决策森林' : 'Simulated case decision forest' : zh ? '医生操作与原因森林' : 'Clinical action and rationale forest'}</h1><p>{simulation ? zh ? '仅显示明确标记的模拟演示，不计入真实医生统计。' : 'Labelled demonstrations only; excluded from doctor statistics.' : zh ? '按病例、动作、原因和结果聚合决策路径。无需研究密钥即可查看。' : 'Paths grouped by case, action, reason and result. No research key is needed.'}</p></div>
      <div className="enc-row"><Link href={toggleLink}>{simulation ? zh ? '查看真实医生轨迹' : 'Doctor trajectories' : zh ? '查看模拟演示' : 'Simulations'}</Link><Link href={`/forest?mode=classic&simulation=${simulation}${caseId ? `&case=${encodeURIComponent(caseId)}` : ''}`}>{zh ? '模型决策森林' : 'Model decision forest'}</Link></div>
    </header>
    <section className="enc-card"><div className="enc-row"><label>{zh ? '病例' : 'Case'}<select aria-label={zh ? '选择森林病例' : 'Select forest case'} value={caseId} onChange={event => { const query = new URLSearchParams({ simulation: String(simulation) }); if (event.target.value) query.set('case', event.target.value); window.location.assign(`/forest?${query}`); }}><option value="">{zh ? '所有病例' : 'All cases'}</option>{forest?.cases.map(row => <option key={row.case_id} value={row.case_id}>{row.dataset} · {row.case_id}</option>)}</select></label><button disabled={busy} className="enc-primary" onClick={() => { setBusy(true); setError(''); setRefresh(value => value + 1); }}>{busy ? zh ? '加载中…' : 'Loading…' : zh ? '刷新森林' : 'Refresh forest'}</button></div>{error && <p role="alert">{error}</p>}</section>
    {forest && <><section className="enc-card"><h2>{forest.session_count} {simulation ? zh ? '条模拟轨迹' : 'simulated visits' : zh ? '条就诊轨迹' : 'visits'}</h2><div className="enc-row">{Object.entries(forest.reason_counts).map(([id, count]) => <span key={id}>{reasons[id] ?? id}: {count}</span>)}</div></section><section className="enc-card"><EncounterForestGraph key={`${simulation}-${caseId}`} forest={forest} chinese={zh} /></section>{caseId && <p className="enc-muted">{cases[0]?.dataset} · {caseId}</p>}</>}
  </main>;
}
