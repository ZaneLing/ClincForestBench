'use client';

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { FileClock, Gamepad2, GitBranch } from 'lucide-react';
import { TemporalArena } from './temporal-arena';
import { TemporalCaseInspector } from './temporal-case-inspector';
import { TemporalDashboard } from './temporal-dashboard';

export function TemporalRoot() {
  const params = useSearchParams();
  const mode = params.get('mode') ?? 'arena';
  return (
    <div className="temporal-root">
      <nav className="temporal-mode-nav" aria-label="Temporal v2 模式">
        <Link className={mode === 'arena' ? 'is-active' : ''} href="/temporal?mode=arena"><Gamepad2 />医生 Arena</Link>
        <Link href="/research?mode=temporal"><GitBranch />Case 转换查看</Link>
        <Link className={mode === 'timeline' ? 'is-active' : ''} href="/temporal?mode=timeline"><FileClock />真实轨迹回放</Link>
      </nav>
      {mode === 'audit' ? <TemporalCaseInspector /> : mode === 'timeline' ? <TemporalDashboard /> : <TemporalArena />}
    </div>
  );
}
