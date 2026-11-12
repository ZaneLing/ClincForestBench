import { permanentRedirect } from 'next/navigation';
import { legacyDestination, type LegacySearch } from '@/lib/legacy-route';

export default async function ModelArenaPage({
  searchParams,
}: {
  searchParams: Promise<LegacySearch>;
}) {
  permanentRedirect(legacyDestination('/compare', await searchParams));
}
