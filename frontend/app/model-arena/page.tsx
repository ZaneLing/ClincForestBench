import { Suspense } from 'react';
import { ModelArenaRoot } from '@/features/model-arena/model-arena-root';

export default function ModelArenaPage() {
  return <Suspense fallback={null}><ModelArenaRoot /></Suspense>;
}
