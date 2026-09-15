'use client';

import { useSearchParams } from 'next/navigation';
import { ForestDashboard } from './forest-dashboard';
import { TemporalForestDashboard } from './temporal-forest-dashboard';

export function ForestRoot() {
  return useSearchParams().get('mode') === 'temporal'
    ? <TemporalForestDashboard />
    : <ForestDashboard />;
}
