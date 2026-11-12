'use client';

import { useSyncExternalStore } from 'react';

function subscribe(callback: () => void) {
  window.addEventListener('popstate', callback);
  window.addEventListener('workspace-query', callback);
  return () => {
    window.removeEventListener('popstate', callback);
    window.removeEventListener('workspace-query', callback);
  };
}

export function useWorkspaceQuery() {
  const search = useSyncExternalStore(
    subscribe,
    () => window.location.search,
    () => '',
  );
  function update(values: Record<string, string | null>, replace = false) {
    const url = new URL(window.location.href);
    Object.entries(values).forEach(([key, value]) => {
      if (value == null || value === '') url.searchParams.delete(key);
      else url.searchParams.set(key, value);
    });
    window.history[replace ? 'replaceState' : 'pushState']({}, '', url);
    window.dispatchEvent(new Event('workspace-query'));
  }
  return { params: new URLSearchParams(search), update };
}
