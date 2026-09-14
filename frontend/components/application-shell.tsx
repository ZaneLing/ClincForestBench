'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  BookOpenText,
  Bot,
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

const navigation = [
  {
    href: '/arena',
    label: 'Arena',
    detail: '选择数据集并进入竞技场',
    icon: HeartPulse,
  },
  {
    href: '/model-arena',
    label: '模型测试',
    detail: 'OpenRouter 自动游玩',
    icon: Bot,
  },
  {
    href: '/history',
    label: '决策历史',
    detail: '我的病例与每轮判断',
    icon: History,
  },
  {
    href: '/research',
    label: 'Case 查看',
    detail: '原始数据、结构和树',
    icon: GitBranch,
  },
  {
    href: '/forest',
    label: '森林查看',
    detail: '医生群体决策统计',
    icon: Trees,
  },
  {
    href: '/evidence',
    label: '数据集与规则',
    detail: '原始字段、转换与玩法',
    icon: BookOpenText,
  },
  {
    href: '/admin',
    label: '账户后台',
    detail: '原型账户管理',
    icon: ShieldCheck,
  },
];

export function ApplicationShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { account, logout } = useAuth();

  if (pathname === '/') return <>{children}</>;

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
            <SidebarGroupLabel>系统导航</SidebarGroupLabel>
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
                        tooltip={item.label}
                      >
                        <Icon />
                        <span className="min-w-0">
                          <b className="block truncate font-medium">
                            {item.label}
                          </b>
                          <small className="block truncate text-xs opacity-55">
                            {item.detail}
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
              <small>{account ? '当前医生' : '医生账户'}</small>
              <b>{account?.username ?? '未登录'}</b>
            </div>
            {account && (
              <button
                aria-label="退出登录"
                onClick={() => void logout()}
                title="退出登录"
                type="button"
              >
                <LogOut />
              </button>
            )}
          </div>
          <div className="rounded-lg border border-cyan-200/10 bg-cyan-200/[0.04] px-3 py-2 group-data-[collapsible=icon]:hidden">
            <small className="block text-xs text-cyan-100/50">Dataset</small>
            <b className="mt-0.5 block text-xs font-medium text-cyan-50">
              DDXPlus · Synthea · MedAgentBench · 130 cases
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
