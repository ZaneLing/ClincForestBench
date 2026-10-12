'use client';

import { useSearchParams } from 'next/navigation';
import { ForestDashboard } from './forest-dashboard';
import { TemporalForestDashboard } from './temporal-forest-dashboard';
import { EncounterForest } from './encounter-forest';

export function ForestRoot() {
  const mode = useSearchParams().get('mode');
  return mode === 'temporal' ? (
    <TemporalForestDashboard />
  ) : mode === 'classic' ? (
    <ForestDashboard />
  ) : (
    <EncounterForest />
  );
}
