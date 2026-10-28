'use client';

import { useSearchParams } from 'next/navigation';
import { ForestDashboard } from './forest-dashboard';
import { EncounterForest } from './encounter-forest';

export function ForestRoot() {
  const mode = useSearchParams().get('mode');
  return mode === 'classic' ? (
    <ForestDashboard />
  ) : (
    <EncounterForest />
  );
}
