'use client';

import { ArrowDown, ArrowUp, Minus } from 'lucide-react';
import { useLanguage } from '@/features/i18n/language-context';
import { metricLabel, type MetricColumn, type MetricRow } from './metrics';

export function MetricTable({
  metrics,
  runs,
  selectedId,
  onSelect,
}: {
  metrics: MetricColumn[];
  runs: MetricRow[];
  selectedId?: string;
  onSelect: (id: string) => void;
}) {
  const { isChinese: zh } = useLanguage();
  const scales = new Map(
    metrics.map((metric) => {
      const numbers = runs
        .map((run) => run.values[metric.id]?.value)
        .filter(
          (value): value is number =>
            typeof value === 'number' && Number.isFinite(value),
        );
      return [
        metric.id,
        {
          max: Math.max(0, ...numbers),
          best:
            metric.direction === 'LOWER'
              ? Math.min(...numbers)
              : Math.max(...numbers),
        },
      ];
    }),
  );
  return (
    <div className="ws-table-scroll">
      <table
        className="ws-table metric-table"
        aria-label={zh ? '模型指标对比' : 'Model metric comparison'}
      >
        <thead>
          <tr>
            <th>{zh ? '模型 / 运行' : 'Model / run'}</th>
            <th>{zh ? '状态' : 'Status'}</th>
            {metrics.map((metric) => (
              <th
                key={metric.id}
                title={`${metricLabel(metric, zh)} · ${metric.direction}`}
              >
                <span>
                  {metricLabel(metric, zh)}
                  {metric.direction === 'HIGHER' ? (
                    <ArrowUp size={12} />
                  ) : metric.direction === 'LOWER' ? (
                    <ArrowDown size={12} />
                  ) : (
                    <Minus size={12} />
                  )}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr
              key={run.id}
              tabIndex={0}
              aria-selected={selectedId === run.id}
              onClick={() => onSelect(run.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') onSelect(run.id);
              }}
            >
              <td>
                <strong>{run.label}</strong>
                {run.caption && <small>{run.caption}</small>}
              </td>
              <td>
                <span
                  className={`ws-pill ${run.status === 'COMPLETED' ? 'recorded' : ''}`}
                >
                  {run.status ?? '—'}
                </span>
              </td>
              {metrics.map((metric) => {
                const entry = run.values[metric.id];
                const value = entry?.value;
                const scale = scales.get(metric.id)!;
                const number = typeof value === 'number' ? value : null;
                const ranked = ['HIGHER', 'LOWER'].includes(metric.direction);
                return (
                  <td key={metric.id}>
                    <div
                      className={`ws-metric-value ${ranked && number != null && number === scale.best ? 'is-best' : ''}`}
                      title={
                        entry
                          ? `${entry.samples} ${zh ? '个有效指标值' : 'available metric values'}`
                          : zh
                            ? '无指标值'
                            : 'No metric value'
                      }
                    >
                      {number != null && (
                        <i
                          style={{
                            width: `${scale.max > 0 ? Math.max(0, (number / scale.max) * 100) : 0}%`,
                          }}
                        />
                      )}
                      <span>
                        {number != null
                          ? new Intl.NumberFormat(localeFor(zh), {
                              maximumFractionDigits: 3,
                            }).format(number)
                          : (value ?? '—')}
                        {value != null && metric.unit ? ` ${metric.unit}` : ''}
                      </span>
                      {entry?.samples > 1 && <small>n={entry.samples}</small>}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {!runs.length && (
        <div className="ws-empty">
          {zh ? '没有匹配的模型运行。' : 'No matching model runs.'}
        </div>
      )}
    </div>
  );
}

function localeFor(zh: boolean) {
  return zh ? 'zh-CN' : 'en';
}
