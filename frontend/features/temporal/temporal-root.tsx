'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { FileClock, Gamepad2, GitBranch } from 'lucide-react';
import { useLanguage } from '@/features/i18n/language-context';
import { TemporalArena } from './temporal-arena';
import { TemporalCaseInspector } from './temporal-case-inspector';
import { TemporalDashboard } from './temporal-dashboard';

export function TemporalRoot() {
  const { isChinese } = useLanguage();
  const params = useSearchParams();
  const mode = params.get('mode') ?? 'arena';
  return (
    <div className="temporal-root">
      <nav className="temporal-mode-nav" aria-label={isChinese ? 'Temporal v2 模式' : 'Temporal v2 modes'}>
        <Link className={mode === 'arena' ? 'is-active' : ''} href="/temporal?mode=arena"><Gamepad2 />{isChinese ? '医生 Arena' : 'Clinician Arena'}</Link>
        <Link href="/research?mode=temporal"><GitBranch />{isChinese ? 'Case 转换查看' : 'Case inspector'}</Link>
        <Link className={mode === 'timeline' ? 'is-active' : ''} href="/temporal?mode=timeline"><FileClock />{isChinese ? '真实轨迹回放' : 'Observed timeline'}</Link>
      </nav>
      {mode === 'audit' ? <TemporalCaseInspector /> : mode === 'timeline' ? <TemporalDashboard /> : <TemporalArena />}
    </div>
  );
}
