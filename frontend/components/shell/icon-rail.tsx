'use client';

import Link from 'next/link';
import { Moon, Sun } from 'lucide-react';
import { useEffect, useSyncExternalStore } from 'react';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useLanguage } from '@/features/i18n/language-context';
import type { NavigationItem } from './top-bar';

function subscribeTheme(notify: () => void) {
  window.addEventListener('medtree-theme', notify);
  return () => window.removeEventListener('medtree-theme', notify);
}
export function IconRail({
  items,
  active,
}: {
  items: NavigationItem[];
  active: string;
}) {
  const { isChinese: zh } = useLanguage();
  const dark = useSyncExternalStore(
    subscribeTheme,
    () => localStorage.getItem('medtree.theme') === 'dark',
    () => false,
  );
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
  }, [dark]);
  function toggleTheme() {
    const value = !dark;
    localStorage.setItem('medtree.theme', value ? 'dark' : 'light');
    window.dispatchEvent(new Event('medtree-theme'));
    document.documentElement.classList.toggle('dark', value);
  }
  return (
    <aside className="workspace-rail">
      <nav aria-label={zh ? '工作区导航' : 'Workspace navigation'}>
        {items.map(({ href, label, icon: Icon }) => (
          <Tooltip key={href}>
            <TooltipTrigger
              render={
                <Link
                  href={href}
                  className="workspace-rail-link"
                  aria-label={label}
                  aria-current={active === href ? 'page' : undefined}
                />
              }
            >
              <Icon size={19} />
            </TooltipTrigger>
            <TooltipContent side="right">{label}</TooltipContent>
          </Tooltip>
        ))}
      </nav>
      <button
        className="workspace-rail-link workspace-theme"
        onClick={toggleTheme}
        aria-label={zh ? '切换深色模式' : 'Toggle dark mode'}
        title={zh ? '切换深色模式' : 'Toggle dark mode'}
      >
        {dark ? <Sun size={19} /> : <Moon size={19} />}
      </button>
    </aside>
  );
}
