'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useSyncExternalStore,
} from 'react';
import { Languages } from 'lucide-react';
import { LANGUAGE_KEY } from '@/lib/api';

export type AppLocale = 'en' | 'zh-CN';

function subscribeLanguage(onChange: () => void) {
  window.addEventListener('storage', onChange);
  return () => window.removeEventListener('storage', onChange);
}

function browserLocale(): AppLocale {
  return window.localStorage.getItem(LANGUAGE_KEY) === 'zh-CN' ? 'zh-CN' : 'en';
}

function serverLocale(): AppLocale {
  return 'en';
}

const LanguageContext = createContext<{
  locale: AppLocale;
  setLocale: (locale: AppLocale) => void;
  isChinese: boolean;
}>({
  locale: 'en',
  setLocale: () => undefined,
  isChinese: false,
});

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const locale = useSyncExternalStore(
    subscribeLanguage,
    browserLocale,
    serverLocale,
  );

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: AppLocale) => {
    window.localStorage.setItem(LANGUAGE_KEY, next);
    document.documentElement.lang = next;
    window.location.reload();
  }, []);

  const value = useMemo(
    () => ({ locale, setLocale, isChinese: locale === 'zh-CN' }),
    [locale, setLocale],
  );
  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  return useContext(LanguageContext);
}

export function LanguageSwitcher() {
  const { locale, setLocale } = useLanguage();
  return (
    <fieldset className="language-switcher" aria-label="Language">
      <Languages aria-hidden="true" />
      <button
        aria-pressed={locale === 'en'}
        onClick={() => setLocale('en')}
        type="button"
      >
        EN
      </button>
      <button
        aria-pressed={locale === 'zh-CN'}
        onClick={() => setLocale('zh-CN')}
        type="button"
      >
        中文
      </button>
    </fieldset>
  );
}
