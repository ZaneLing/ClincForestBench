'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight, GitBranch } from 'lucide-react';
import type { ForestTrace } from '@/features/forest/use-forest';
import { useLanguage } from '@/features/i18n/language-context';
import { TraceRow } from './trace-row';

export function TraceTree({
  runs,
  selectedId,
  onSelect,
  collapseKey = '',
}: {
  runs: ForestTrace[];
  selectedId: string;
  onSelect: (id: string) => void;
  collapseKey?: string;
}) {
  const { isChinese: zh } = useLanguage();
  const [closed, setClosed] = useState<string[]>([]);
  const collapsedAll = collapseKey === 'collapsed';
  return (
    <div
      className="ws-trace-tree"
      role="tree"
      aria-label={zh ? '就诊轨迹' : 'Visit traces'}
      tabIndex={0}
      onKeyDown={(event) => {
        if (
          !['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight'].includes(
            event.key,
          )
        )
          return;
        event.preventDefault();
        const target = event.target as HTMLElement;
        if (
          (event.key === 'ArrowLeft' || event.key === 'ArrowRight') &&
          target.dataset.traceId
        ) {
          const id = target.dataset.traceId;
          const mark = (event.key === 'ArrowLeft') !== collapsedAll;
          setClosed((rows) =>
            mark
              ? [...new Set([...rows, id])]
              : rows.filter((row) => row !== id),
          );
          return;
        }
        const buttons = Array.from(
          event.currentTarget.querySelectorAll<HTMLButtonElement>(
            '[role=treeitem]',
          ),
        );
        const index = buttons.indexOf(target as HTMLButtonElement);
        const next =
          buttons[
            Math.max(
              0,
              Math.min(
                buttons.length - 1,
                index + (event.key === 'ArrowUp' ? -1 : 1),
              ),
            )
          ];
        next?.focus();
        if (next?.dataset.nodeId) onSelect(next.dataset.nodeId);
      }}
    >
      {runs.map((run) => {
        const open = collapsedAll
          ? closed.includes(run.id)
          : !closed.includes(run.id);
        return (
          <section key={run.id} className="ws-trace-branch">
            <button
              role="treeitem"
              aria-expanded={open}
              aria-level={1}
              className="ws-trace-root"
              data-trace-id={run.id}
              title={run.encounterId ?? run.label}
              onClick={() =>
                setClosed((rows) =>
                  rows.includes(run.id)
                    ? rows.filter((id) => id !== run.id)
                    : [...rows, run.id],
                )
              }
            >
              {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              <GitBranch size={13} />
              <b>{run.label}</b>
              <small>{run.nodes.length}</small>
            </button>
            {open && (
              <fieldset aria-label={run.label} className="ws-trace-children">
                {run.nodes.map((node) => (
                  <TraceRow
                    node={node}
                    key={node.id}
                    depth={1}
                    selected={selectedId === node.id}
                    onSelect={onSelect}
                  />
                ))}
              </fieldset>
            )}
          </section>
        );
      })}
      {!runs.length && (
        <div className="ws-empty">
          {zh ? '暂无轨迹' : 'No traces available'}
        </div>
      )}
    </div>
  );
}
