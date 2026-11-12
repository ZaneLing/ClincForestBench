import type { ModelRunDetail } from '@/features/model-arena/types';

export type Metric = {
  id?: string;
  key?: string;
  label: string | { en: string; 'zh-CN': string };
  direction: string;
  value?: number | string | null;
  unit?: string;
};
export type EvaluatedRun = ModelRunDetail & {
  evaluation?: { metrics?: Metric[] };
};
export type MetricColumn = {
  id: string;
  label: Metric['label'];
  direction: string;
  unit?: string;
};
export type MetricRow = {
  id: string;
  label: string;
  caption?: string;
  status?: string;
  values: Record<string, { value: number | string | null; samples: number }>;
};

export function metricId(metric: Metric) {
  return (
    metric.id ||
    metric.key ||
    (typeof metric.label === 'string' ? metric.label : metric.label.en)
  );
}
export function metricLabel(metric: MetricColumn, chinese: boolean) {
  return typeof metric.label === 'string'
    ? metric.label
    : metric.label[chinese ? 'zh-CN' : 'en'];
}
export function metricColumns(runs: EvaluatedRun[]): MetricColumn[] {
  const columns = new Map<string, MetricColumn>();
  runs.forEach((run) =>
    run.evaluation?.metrics?.forEach((metric) => {
      if (!metric.label) return;
      const id = metricId(metric);
      const previous = columns.get(id);
      // Conflicting metadata cannot establish a ranking direction.
      columns.set(id, {
        id,
        label: metric.label,
        direction:
          previous && previous.direction !== metric.direction
            ? 'DESCRIPTIVE'
            : metric.direction,
        unit: metric.unit,
      });
    }),
  );
  return [...columns.values()];
}
export function metricValues(runs: EvaluatedRun[]): MetricRow['values'] {
  const values: Record<string, (number | string)[]> = {};
  runs.forEach((run) =>
    run.evaluation?.metrics?.forEach((metric) => {
      if (
        !metric.label ||
        metric.value == null ||
        (typeof metric.value === 'number' && !Number.isFinite(metric.value))
      )
        return;
      const id = metricId(metric);
      (values[id] ??= []).push(metric.value);
    }),
  );
  return Object.fromEntries(
    Object.entries(values).map(([id, items]) => [
      id,
      {
        value: items.every((item) => typeof item === 'number')
          ? items.reduce((sum, value) => sum + value, 0) / items.length
          : [...new Set(items)].join(', '),
        samples: items.length,
      },
    ]),
  );
}
