export type LegacySearch = Record<string, string | string[] | undefined>;

export function legacyDestination(
  base: '/cases' | '/compare',
  search: LegacySearch,
) {
  const query = new URLSearchParams();
  Object.entries(search).forEach(([key, values]) => {
    if (values === undefined) return;
    for (const value of Array.isArray(values) ? values : [values])
      query.append(key, value);
  });
  const caseId = query.get('case') || query.get('case_id');
  const path =
    base === '/cases' && caseId ? `/cases/${encodeURIComponent(caseId)}` : base;
  return `${path}${query.size ? `?${query}` : ''}`;
}
