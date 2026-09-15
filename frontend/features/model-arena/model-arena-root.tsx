'use client';

import { useSearchParams } from 'next/navigation';
import { ModelArenaDashboard } from './model-arena-dashboard';
import { TemporalModelArenaDashboard } from './temporal-model-arena-dashboard';

export function ModelArenaRoot() {
  const params = useSearchParams();
  return params.get('mode') === 'temporal'
    ? <TemporalModelArenaDashboard />
    : <ModelArenaDashboard />;
}
