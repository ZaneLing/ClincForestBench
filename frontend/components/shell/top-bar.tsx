'use client';

import Link from 'next/link';
import {
  HeartPulse,
  LogOut,
  Search,
  ShieldCheck,
  UserRound,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useAuth } from '@/features/auth/auth-context';
import {
  LanguageSwitcher,
  useLanguage,
} from '@/features/i18n/language-context';

export type NavigationItem = { href: string; label: string; icon: LucideIcon };

export function TopBar({
  tabs,
  active,
  actions,
  onSearch,
}: {
  tabs: NavigationItem[];
  active: string;
  actions?: React.ReactNode;
  onSearch: () => void;
}) {
  const { isChinese: zh } = useLanguage();
  const { account, logout } = useAuth();
  return (
    <header className="workspace-topbar">
      <Link href="/cases" className="workspace-brand">
        <span>
          <HeartPulse size={20} />
        </span>
        <b>MedTreeBench</b>
      </Link>
      <span className="workspace-divider" />
      <nav
        className="workspace-tabs"
        aria-label={zh ? '主导航' : 'Main navigation'}
      >
        {tabs.map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            aria-current={active === href ? 'page' : undefined}
          >
            {label}
          </Link>
        ))}
      </nav>
      <div className="workspace-top-actions">
        <LanguageSwitcher />
        <button
          className="ws-button ws-search-trigger"
          onClick={onSearch}
          aria-label={zh ? '搜索病例' : 'Search cases'}
        >
          <Search size={15} />
          <kbd>⌘ K</kbd>
        </button>
        {actions}
        <details className="workspace-account">
          <summary
            aria-label={zh ? '账户菜单' : 'Account menu'}
            title={account?.username}
          >
            <UserRound size={17} />
          </summary>
          <div className="ws-menu">
            <small>{account?.username ?? (zh ? '访客' : 'Guest')}</small>
            <Link href="/admin">
              <ShieldCheck size={15} />
              {zh ? '账户后台' : 'Account admin'}
            </Link>
            {account && (
              <button onClick={() => void logout()}>
                <LogOut size={15} />
                {zh ? '退出登录' : 'Sign out'}
              </button>
            )}
          </div>
        </details>
      </div>
    </header>
  );
}
