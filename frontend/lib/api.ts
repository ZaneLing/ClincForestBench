export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
export const AUTH_TOKEN_KEY = 'clincforestbench.auth-token';
export const LANGUAGE_KEY = 'clincforestbench.language';

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set('Content-Type', 'application/json');
  if (typeof window !== 'undefined' && !headers.has('Authorization')) {
    const token = window.localStorage.getItem(AUTH_TOKEN_KEY);
    if (token) headers.set('Authorization', `Bearer ${token}`);
  }
  let localizedPath = path;
  if (typeof window !== 'undefined') {
    const url = new URL(path, API_BASE);
    url.searchParams.set(
      'lang',
      window.localStorage.getItem(LANGUAGE_KEY) === 'zh-CN' ? 'zh-CN' : 'en',
    );
    localizedPath = `${url.pathname}${url.search}`;
  }
  const response = await fetch(`${API_BASE}${localizedPath}`, {
    ...init,
    headers,
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as {
      detail?: string;
    };
    throw new Error(body.detail ?? `${response.status} ${response.statusText}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function eventId(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}
