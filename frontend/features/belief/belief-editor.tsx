'use client';

import { type ReactNode, useMemo, useState } from 'react';
import { CheckCheck, GripVertical, Plus, Search, Trash2 } from 'lucide-react';
import { Reorder } from 'motion/react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type { Condition } from '@/features/arena/types';

export function BeliefEditor({
  conditions,
  selectedIds,
  disabled,
  submitLabel,
  onSelectedIds,
  onSubmit,
  history,
  noun = '疾病',
}: {
  conditions: Condition[];
  selectedIds: string[];
  disabled?: boolean;
  submitLabel: string;
  onSelectedIds: (value: string[]) => void;
  onSubmit: () => void;
  history?: ReactNode;
  noun?: string;
}) {
  const [query, setQuery] = useState('');
  const conditionById = useMemo(
    () => new Map(conditions.map((item) => [item.condition_id, item])),
    [conditions],
  );
  const available = useMemo(() => {
    const selected = new Set(selectedIds);
    const needle = query.trim().toLocaleLowerCase();
    return conditions.filter(
      (condition) =>
        !selected.has(condition.condition_id) &&
        (!needle ||
          condition.name.toLocaleLowerCase().includes(needle) ||
          condition.condition_id.toLocaleLowerCase().includes(needle)),
    );
  }, [conditions, query, selectedIds]);

  return (
    <div className="belief-editor">
      <div className="belief-editor-columns">
        <div className="belief-editor-left">
          {history}
          <section className="belief-candidate-section">
            <div className="belief-section-heading">
              <div>
                <span>候选{noun}</span>
                <b>{selectedIds.length}</b>
              </div>
              <small>拖动调整优先级</small>
            </div>

            {selectedIds.length ? (
              <Reorder.Group
                axis="y"
                className="belief-ranking-list"
                onReorder={onSelectedIds}
                values={selectedIds}
              >
                {selectedIds.map((conditionId, index) => (
                  <Reorder.Item
                    className="belief-ranking-item"
                    dragListener={!disabled}
                    key={conditionId}
                    value={conditionId}
                    whileDrag={{ scale: 1.02, zIndex: 20 }}
                  >
                    <span className="belief-rank">{index + 1}</span>
                    <GripVertical className="belief-grip" />
                    <b>
                      {conditionById.get(conditionId)?.name ?? conditionId}
                    </b>
                    <Button
                      aria-label={`删除 ${conditionById.get(conditionId)?.name ?? conditionId}`}
                      disabled={disabled}
                      onClick={() =>
                        onSelectedIds(
                          selectedIds.filter((item) => item !== conditionId),
                        )
                      }
                      size="icon"
                      type="button"
                      variant="ghost"
                    >
                      <Trash2 />
                    </Button>
                  </Reorder.Item>
                ))}
              </Reorder.Group>
            ) : (
              <div className="belief-ranking-empty">
                从右侧选择{noun}，建立你的有序判断列表。
              </div>
            )}
          </section>
        </div>

        <section className="belief-pool-section">
          <div className="belief-section-heading">
            <div>
              <span>待选{noun}</span>
              <b>{available.length}</b>
            </div>
            <Button
              className="belief-select-all"
              disabled={disabled || available.length === 0}
              onClick={() =>
                onSelectedIds([
                  ...selectedIds,
                  ...available.map((condition) => condition.condition_id),
                ])
              }
              size="xs"
              type="button"
              variant="outline"
            >
              <CheckCheck /> {query.trim() ? '全选结果' : '全部加入'}
            </Button>
          </div>
          <div className="belief-search">
            <Search />
            <Input
              aria-label={`筛选待选${noun}`}
              disabled={disabled}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={`输入${noun}关键词筛选…`}
              value={query}
            />
          </div>
          <div className="belief-condition-pool">
            {available.map((condition) => (
              <button
                disabled={disabled}
                key={condition.condition_id}
                onClick={() =>
                  onSelectedIds([...selectedIds, condition.condition_id])
                }
                type="button"
              >
                <Plus />
                <span>{condition.name}</span>
              </button>
            ))}
            {!available.length && (
              <p>
                {query.trim()
                  ? `没有匹配的${noun}`
                  : `所有${noun}都已加入候选列表`}
              </p>
            )}
          </div>
        </section>
      </div>

      <Button
        className="belief-stage-submit"
        disabled={disabled || selectedIds.length === 0}
        onClick={onSubmit}
        type="button"
      >
        {submitLabel}
      </Button>
    </div>
  );
}
