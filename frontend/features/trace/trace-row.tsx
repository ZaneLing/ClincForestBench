'use client';

import { memo } from 'react';
import {
  CheckCheck,
  MessageCircle,
  Stethoscope,
  GitBranch,
} from 'lucide-react';
import type { EncounterForestNode } from '@/features/forest/encounter-forest-graph';
import { useLanguage } from '@/features/i18n/language-context';

export const TraceRow = memo(function TraceRow({
  node,
  depth,
  selected,
  duration,
  onSelect,
}: {
  node: EncounterForestNode;
  depth: number;
  selected: boolean;
  duration?: string;
  onSelect: (id: string) => void;
}) {
  const { isChinese: zh } = useLanguage();
  const Icon =
    node.event_type === 'COMPLETE'
      ? CheckCheck
      : node.item?.kind === 'operation'
        ? Stethoscope
        : node.event_type === 'ACTION'
          ? MessageCircle
          : GitBranch;
  const label = node.item?.id ?? node.event_type ?? node.id;
  return (
    <button
      role="treeitem"
      aria-selected={selected}
      aria-level={depth + 1}
      tabIndex={selected ? 0 : -1}
      className="ws-trace-row"
      style={{ paddingLeft: depth * 16 + 12 }}
      data-node-id={node.id}
      onClick={() => onSelect(node.id)}
      title={`${label} · ${node.id}`}
    >
      <Icon size={12} />
      <span>{label}</span>
      {node.result_status && (
        <small className="ws-trace-status">{node.result_status}</small>
      )}
      <time title={zh ? '接口未记录事件时间' : 'Event time is not recorded'}>
        {duration ?? '—'}
      </time>
    </button>
  );
});
