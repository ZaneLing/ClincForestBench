import { ForestRoot } from '@/features/forest/forest-root';
import { permanentRedirect } from 'next/navigation';
import { legacyDestination, type LegacySearch } from '@/lib/legacy-route';

export default async function ForestPage({
  searchParams,
}: {
  searchParams: Promise<LegacySearch>;
}) {
  const search = await searchParams;
  if (search.mode === 'classic') return <ForestRoot />;
  permanentRedirect(legacyDestination('/cases', search));
}
