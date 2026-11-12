'use client';

import { X } from 'lucide-react';
import { ResizableHandle, ResizablePanel } from '@/components/ui/resizable';
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { useLanguage } from '@/features/i18n/language-context';
import { useMediaQuery } from './use-media-query';

export type InspectorTab = { id: string; label: string };

export function InspectorPanel({
  title,
  badge,
  tabs = [],
  tab,
  onTabChange,
  children,
  open,
  onClose,
}: {
  title: string;
  badge?: React.ReactNode;
  tabs?: InspectorTab[];
  tab?: string;
  onTabChange?: (tab: string) => void;
  children: React.ReactNode;
  open: boolean;
  onClose: () => void;
}) {
  const desktop = useMediaQuery('(min-width: 1201px)');
  const { isChinese: zh } = useLanguage();
  const body = (
    <div className="workspace-inspector">
      <header className="workspace-inspector-header">
        <strong title={title}>{title}</strong>
        {badge}
        <button
          className="ws-icon-button"
          aria-label={zh ? '关闭检查器' : 'Close inspector'}
          onClick={onClose}
        >
          <X size={16} />
        </button>
      </header>
      {tabs.length ? (
        <Tabs
          value={tab}
          onValueChange={(value) => onTabChange?.(String(value))}
          className="workspace-inspector-tabs"
        >
          <TabsList variant="line">
            {tabs.map((item) => (
              <TabsTrigger value={item.id} key={item.id}>
                {item.label}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent
            value={tab ?? tabs[0].id}
            className="workspace-inspector-body"
          >
            {children}
          </TabsContent>
        </Tabs>
      ) : (
        <div className="workspace-inspector-body">{children}</div>
      )}
    </div>
  );
  if (!desktop)
    return (
      <Sheet
        open={open}
        onOpenChange={(value) => {
          if (!value) onClose();
        }}
      >
        <SheetContent
          className="workspace-inspector-sheet"
          showCloseButton={false}
        >
          <SheetTitle className="sr-only">{title}</SheetTitle>
          <SheetDescription className="sr-only">
            {zh
              ? '查看详情、证据和原始数据'
              : 'Inspect details, evidence and raw data'}
          </SheetDescription>
          {body}
        </SheetContent>
      </Sheet>
    );
  if (!open) return null;
  return (
    <>
      <ResizableHandle className="workspace-resize" />
      <ResizablePanel
        id="inspector"
        defaultSize="400px"
        minSize="320px"
        maxSize="560px"
      >
        {body}
      </ResizablePanel>
    </>
  );
}
