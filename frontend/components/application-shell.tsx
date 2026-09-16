'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  BookOpenText,
  Bot,
  FileClock,
  GitBranch,
  HeartPulse,
  History,
  LogOut,
  ShieldCheck,
  Trees,
  UserRound,
} from 'lucide-react';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarSeparator,
  SidebarTrigger,
} from '@/components/ui/sidebar';
import { useAuth } from '@/features/auth/auth-context';
import {
  LanguageSwitcher,
  useLanguage,
} from '@/features/i18n/language-context';

const navigation = [
  {
    href: '/arena',
    label: { en: 'Arena', zh: '竞技场' },
    detail: { en: '14 datasets in one arena', zh: '14 个数据集进入竞技场' },
    icon: HeartPulse,
  },
  {
    href: '/model-arena',
    label: { en: 'Model testing', zh: '模型测试' },
    detail: { en: 'Classic + Temporal autoplay', zh: '经典 + Temporal 自动游玩' },
    icon: Bot,
  },
  {
    href: '/temporal',
    label: { en: 'Temporal Arena', zh: '时序竞技场' },
    detail: { en: 'History, tests, time, diagnosis', zh: '问询、检查、时钟推进与诊断' },
    icon: FileClock,
  },
  {
    href: '/history',
    label: { en: 'Decision history', zh: '决策历史' },
    detail: { en: 'Classic / Temporal decisions', zh: '经典 / Temporal 每轮判断' },
    icon: History,
  },
  {
    href: '/research',
    label: { en: 'Case inspector', zh: 'Case 查看' },
    detail: { en: '188 source cases and trees', zh: '188 Case 原始数据和树' },
    icon: GitBranch,
  },
  {
    href: '/forest',
    label: { en: 'Forest explorer', zh: '森林查看' },
    detail: { en: 'Classic / Temporal cohorts', zh: '经典 / Temporal 群体统计' },
    icon: Trees,
  },
  {
    href: '/evidence',
    label: { en: 'Datasets and rules', zh: '数据集与规则' },
    detail: { en: '14 schemas and protocols', zh: '14 套字段、转换与玩法' },
    icon: BookOpenText,
  },
  {
    href: '/admin',
    label: { en: 'Account admin', zh: '账户后台' },
    detail: { en: 'Prototype account management', zh: '原型账户管理' },
    icon: ShieldCheck,
  },
];

export function ApplicationShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { account, logout } = useAuth();
  const { isChinese } = useLanguage();

  if (pathname === '/') return <><LanguageSwitcher />{children}</>;

  return (
    <SidebarProvider className="bench-app-shell" defaultOpen>
      <Sidebar className="border-cyan-300/10" collapsible="icon">
        <SidebarHeader className="p-3">
          <div className="flex items-center gap-2">
            <SidebarTrigger className="sidebar-brand-trigger" />
            <div className="min-w-0 group-data-[collapsible=icon]:hidden">
              <b className="block truncate text-sm text-white">
                ClincForestBench
              </b>
              <small className="block truncate text-xs text-cyan-200/60">
                Clinical decision forest
              </small>
            </div>
          </div>
        </SidebarHeader>
        <SidebarSeparator className="bg-cyan-100/10" />
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel>{isChinese ? '系统导航' : 'Navigation'}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {navigation.map((item) => {
                  const Icon = item.icon;
                  const active = pathname.startsWith(item.href);
                  return (
                    <SidebarMenuItem key={item.href}>
                      <SidebarMenuButton
                        className="bench-sidebar-link h-11"
                        isActive={active}
                        render={<Link href={item.href} />}
                        tooltip={isChinese ? item.label.zh : item.label.en}
                      >
                        <Icon />
                        <span className="min-w-0">
                          <b className="block truncate font-medium">
                            {isChinese ? item.label.zh : item.label.en}
                          </b>
                          <small className="block truncate text-xs opacity-55">
                            {isChinese ? item.detail.zh : item.detail.en}
                          </small>
                        </span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter>
          <div className="sidebar-account group-data-[collapsible=icon]:hidden">
            <span>
              <UserRound />
            </span>
            <div>
              <small>{account ? (isChinese ? '当前医生' : 'Current clinician') : (isChinese ? '医生账户' : 'Clinician account')}</small>
              <b>{account?.username ?? (isChinese ? '未登录' : 'Signed out')}</b>
            </div>
            {account && (
              <button
                aria-label={isChinese ? '退出登录' : 'Sign out'}
                onClick={() => void logout()}
                title={isChinese ? '退出登录' : 'Sign out'}
                type="button"
              >
                <LogOut />
              </button>
            )}
          </div>
          <LanguageSwitcher />
          <div className="rounded-lg border border-cyan-200/10 bg-cyan-200/[0.04] px-3 py-2 group-data-[collapsible=icon]:hidden">
            <small className="block text-xs text-cyan-100/50">Dataset</small>
            <b className="mt-0.5 block text-xs font-medium text-cyan-50">
              DDXPlus · Synthea · MedAgentBench · MIMIC · MC-MED · eICU · PMC · NEJM · consultation · persona · memory · rubric
            </b>
          </div>
        </SidebarFooter>
        <SidebarRail />
      </Sidebar>
      <div className="app-shell-content">
        <SidebarTrigger className="mobile-sidebar-trigger md:hidden" />
        {children}
      </div>
    </SidebarProvider>
  );
}
