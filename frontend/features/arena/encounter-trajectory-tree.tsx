'use client';

import { ArrowDown, Activity, CheckCircle2, MessageCircle, Stethoscope, UserRound } from 'lucide-react';

type Label = { en: string; 'zh-CN': string };
export type TrajectoryEntry = {
  id: string;
  sequence: number;
  type: string;
  timestamp: string;
  item?: { kind: 'operation' | 'inquiry'; label: Label };
  reason_options?: { id: string; label: Label }[];
  reason_id?: string;
  reason_text?: string;
  hypothesis?: string;
  result_status?: string;
  records?: { result: unknown }[];
  diagnoses?: string[];
  text?: string;
};

function compact(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return value.map(compact).filter(Boolean).join(' · ');
  if (typeof value === 'object') {
    const row = value as Record<string, unknown>;
    if (row.answer != null) return [compact(row.question), compact(row.answer)].filter(Boolean).join(' — ');
    return Object.entries(row).map(([key, entry]) => `${key}: ${compact(entry)}`).join(' · ');
  }
  return '';
}

export function EncounterTrajectoryTree({
  caseId, dataset, demographics, presentation, events, chinese, onSelect,
}: {
  caseId: string;
  dataset: string;
  demographics: Record<string, unknown>;
  presentation: unknown;
  events: TrajectoryEntry[];
  chinese: boolean;
  onSelect: (index: number) => void;
}) {
  const locale = chinese ? 'zh-CN' : 'en';
  const t = (en: string, cn: string) => chinese ? cn : en;
  const titles: Record<string, string> = {
    DIAGNOSIS: t('Recorded diagnosis', '记录诊断'),
    PRESCRIPTION: t('Prescription / treatment', '处方 / 治疗计划'),
    COMPLETE: t('Visit completed', '本次就诊完成'),
  };
  return <div className="enc-path-scroll" aria-label={t('Your recorded trajectory tree', '本次已记录诊疗轨迹树')}>
    <p className="enc-path-caption">{t('Top to bottom: your actual steps, not the reference path. Select a step to inspect its full result.', '从上到下按实际操作顺序连接，不是参考路径。点击步骤查看完整答案与结果。')}</p>
    <ol className="enc-path-tree">
      <li className="enc-path-entry">
        <div className="enc-path-node enc-path-initial">
          <span className="enc-path-heading"><UserRound size={18} /><b>{t('Initial presentation', '首诊信息')}</b><small>S0</small></span>
          <p>{dataset} · {caseId}</p>
          <p>{compact(demographics).slice(0, 160)}</p>
          <p>{compact(presentation).slice(0, 220)}</p>
        </div>
        {!!events.length && <ArrowDown className="enc-path-connector" aria-hidden="true" />}
      </li>
      {events.map((event, index) => {
        const missing = event.result_status === 'NOT_RECORDED';
        const Icon = event.type === 'DIAGNOSIS' ? Stethoscope : event.type === 'COMPLETE' ? CheckCircle2 : event.item?.kind === 'inquiry' ? MessageCircle : Activity;
        const reason = event.reason_options?.find(r => r.id === event.reason_id)?.label[locale] ?? event.reason_id;
        const answer = event.diagnoses?.join(' · ') || event.text || event.records?.map(r => compact(r.result)).filter(Boolean).join(' · ');
        return <li className="enc-path-entry" key={event.id}>
          <button type="button" className={`enc-path-node ${event.type === 'DIAGNOSIS' ? 'enc-path-diagnosis' : ''} ${missing ? 'enc-path-missing' : ''}`} onClick={() => onSelect(index)} aria-label={`${t('Inspect step', '查看步骤')} ${event.sequence}: ${event.item?.label[locale] ?? titles[event.type] ?? event.type}`}>
            <span className="enc-path-heading"><Icon size={18} /><b>{event.item?.label[locale] ?? titles[event.type] ?? event.type}</b><small>S{event.sequence}</small></span>
            {reason && <p>{t('Reason: ', '原因：')}{reason}{event.reason_text && ` — ${event.reason_text}`}</p>}
            {event.hypothesis && <p>{t('Hypothesis: ', '诊断假设：')}{event.hypothesis}</p>}
            {missing ? <p>{t('No recorded result; case ended.', '无已记录答案 / 结果，病例在此截断。')}</p> : answer ? <p>{answer.slice(0, 240)}{answer.length > 240 ? '…' : ''}</p> : event.type === 'COMPLETE' ? <p>{t('Trajectory saved.', '完整轨迹已保存。')}</p> : null}
            <time dateTime={event.timestamp}>{new Date(event.timestamp).toLocaleTimeString(locale)}</time>
          </button>
          {index < events.length - 1 && <ArrowDown className="enc-path-connector" aria-hidden="true" />}
        </li>;
      })}
    </ol>
  </div>;
}
