import { permanentRedirect } from 'next/navigation';
import { legacyDestination, type LegacySearch } from '@/lib/legacy-route';

export default async function ResearchPage({
  searchParams,
}: {
  searchParams: Promise<LegacySearch>;
}) {
  permanentRedirect(legacyDestination('/cases', await searchParams));
}
