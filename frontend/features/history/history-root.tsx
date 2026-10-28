'use client';

import { useSearchParams } from 'next/navigation';
import { DecisionHistory } from './decision-history';
import { EncounterArena } from '@/features/arena/encounter-arena';

export function HistoryRoot() {
  const mode = useSearchParams().get('mode');
  return mode === 'classic' ? (
    <DecisionHistory />
  ) : (
    <EncounterArena historyOnly />
  );
}
