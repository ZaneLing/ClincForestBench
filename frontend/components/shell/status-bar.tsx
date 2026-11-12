'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import { Activity } from 'lucide-react';
import { useLanguage } from '@/features/i18n/language-context';

const StatusContext = createContext<(items: string[]) => void>(() => {});

export function StatusProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<string[]>([]);
  const { isChinese: zh } = useLanguage();
  return (
    <StatusContext.Provider value={setItems}>
      {children}
      <StatusBar
        items={
          items.length
            ? items
            : [
                zh ? '临床决策工作台' : 'Clinical decision workspace',
                'UNORDERED_EVIDENCE',
              ]
        }
      />
    </StatusContext.Provider>
  );
}

export function useWorkspaceStatus(items: string[]) {
  const setItems = useContext(StatusContext);
  const serialized = JSON.stringify(items);
  useEffect(() => {
    setItems(JSON.parse(serialized));
    return () => setItems([]);
  }, [setItems, serialized]);
}

export function StatusBar({ items }: { items: string[] }) {
  const { isChinese: zh } = useLanguage();
  return (
    <footer className="workspace-status">
      <Activity size={13} />
      <div>
        {items.map((item, i) => (
          <span key={i}>{item}</span>
        ))}
      </div>
      <span className="workspace-status-caption">
        {zh ? '自主证据获取' : 'Self-directed evidence acquisition'}
      </span>
    </footer>
  );
}
