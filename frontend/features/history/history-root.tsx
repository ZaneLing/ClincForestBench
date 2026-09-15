'use client';

import { useSearchParams } from 'next/navigation';
import { DecisionHistory } from './decision-history';
import { TemporalDecisionHistory } from './temporal-decision-history';

export function HistoryRoot() {
  return useSearchParams().get('mode') === 'temporal'
    ? <TemporalDecisionHistory />
    : <DecisionHistory />;
}
