'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import {
  BookOpenText,
  ChartNoAxesCombined,
  Database,
  HeartPulse,
  History,
  Plus,
} from 'lucide-react';
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import {
  LanguageSwitcher,
  useLanguage,
} from '@/features/i18n/language-context';
import { api } from '@/lib/api';
import { TopBar } from './shell/top-bar';
import { IconRail } from './shell/icon-rail';
import { StatusProvider } from './shell/status-bar';

export function ApplicationShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { isChinese: zh } = useLanguage();
  const [searchOpen, setSearchOpen] = useState(false);
  const [cases, setCases] = useState<{ case_id: string; dataset: string }[]>(
    [],
  );
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [query, setQuery] = useState('');
  const tabs = [
    { href: '/cases', label: zh ? '病例库' : 'Cases', icon: Database },
    {
      href: '/compare',
      label: zh ? '模型对比' : 'Compare',
      icon: ChartNoAxesCombined,
    },
    { href: '/arena', label: zh ? '交互就诊' : 'Arena', icon: HeartPulse },
    { href: '/history', label: zh ? '决策历史' : 'History', icon: History },
    {
      href: '/evidence',
      label: zh ? '数据集' : 'Datasets',
      icon: BookOpenText,
    },
  ];
  const active =
    tabs.find((item) => pathname.startsWith(item.href))?.href ??
    (pathname === '/model-arena'
      ? '/compare'
      : ['/research', '/forest'].includes(pathname)
        ? '/cases'
        : '');
  useEffect(() => {
    function handleKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setSearchOpen((value) => !value);
      }
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, []);
  useEffect(() => {
    if (!searchOpen || cases.length) return;
    const controller = new AbortController();
    api<{ cases: typeof cases }>('/research/case-library', {
      signal: controller.signal,
      headers: { 'X-Research-Key': 'local-research-only' },
    })
      .then((data) => {
        setCases(data.cases);
        setError('');
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(String(e.message));
      });
    return () => controller.abort();
  }, [searchOpen, cases.length, attempt]);
  if (pathname === '/')
    return (
      <>
        <LanguageSwitcher />
        {children}
      </>
    );
  return (
    <div className="workspace-shell">
      <StatusProvider>
        <TopBar
          tabs={tabs}
          active={active}
          onSearch={() => setSearchOpen(true)}
          actions={
            <Link href="/arena" className="ws-button ws-primary">
              <Plus size={15} />
              <span>{zh ? '开始就诊' : 'New visit'}</span>
            </Link>
          }
        />
        <div className="workspace-main">
          <IconRail items={tabs} active={active} />
          <div className="app-shell-page workspace-page">{children}</div>
        </div>
      </StatusProvider>
      <CommandDialog
        open={searchOpen}
        onOpenChange={setSearchOpen}
        title={zh ? '搜索病例' : 'Search cases'}
        description={zh ? '输入病例 ID 或数据集' : 'Type a case ID or dataset'}
      >
        <Command shouldFilter={false}>
          <CommandInput
            value={query}
            onValueChange={setQuery}
            placeholder={
              zh ? '搜索病例 ID、数据集…' : 'Search case ID, dataset…'
            }
          />
          <CommandList>
            {error ? (
              <div role="alert" className="ws-empty">
                {error}
                <button
                  className="ws-button"
                  onClick={() => setAttempt((value) => value + 1)}
                >
                  {zh ? '重试' : 'Retry'}
                </button>
              </div>
            ) : !cases.length ? (
              <div className="ws-empty">{zh ? '加载中…' : 'Loading…'}</div>
            ) : (
              <CommandEmpty>
                {zh ? '没有匹配病例' : 'No matching cases'}
              </CommandEmpty>
            )}
            {cases
              .filter((row) =>
                `${row.case_id} ${row.dataset}`
                  .toLowerCase()
                  .includes(query.toLowerCase()),
              )
              .slice(0, 60)
              .map((row) => (
                <CommandItem
                  key={row.case_id}
                  value={row.case_id}
                  onSelect={() => {
                    setSearchOpen(false);
                    router.push(`/cases/${encodeURIComponent(row.case_id)}`);
                  }}
                >
                  <Database size={15} />
                  <span>{row.case_id}</span>
                  <small className="ml-auto">{row.dataset}</small>
                </CommandItem>
              ))}
          </CommandList>
        </Command>
      </CommandDialog>
    </div>
  );
}
