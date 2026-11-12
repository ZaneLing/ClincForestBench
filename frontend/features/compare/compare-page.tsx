'use client';

import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { ChartNoAxesCombined, RotateCw, Search } from 'lucide-react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useLanguage } from '@/features/i18n/language-context';
import { useWorkspaceQuery } from '@/components/shell/use-workspace-query';
import { useWorkspaceStatus } from '@/components/shell/status-bar';
import { InspectorPanel } from '@/components/shell/inspector-panel';
import { ResizablePanelGroup, ResizablePanel } from '@/components/ui/resizable';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { RESEARCH_HEADERS } from '@/features/cases/types';
import type { ModelRunSummary } from '@/features/model-arena/types';
import { MetricTable } from './metric-table';
import { metricColumns, metricValues, type EvaluatedRun } from './metrics';
import { RunInspector } from './run-inspector';
import '@/features/cases/cases.css';
import '@/features/cases/detail.css';
import './compare.css';

const ModelArena = lazy(() =>
  import('@/features/model-arena/model-arena-root').then((module) => ({
    default: module.ModelArenaRoot,
  })),
);

export function ComparePage() {
  const { isChinese: zh, locale } = useLanguage();
  const { params, update } = useWorkspaceQuery();
  const [runs, setRuns] = useState<ModelRunSummary[] | null>(null);
  const [details, setDetails] = useState<Record<string, EvaluatedRun>>({});
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const mode = ['case', 'run'].includes(params.get('tab') ?? '')
    ? params.get('tab')!
    : 'overview';
  const query = params.get('q') ?? '';
  const casesQuery = params.get('cases') ?? params.get('case') ?? '';
  const selectedCases = useMemo(
    () => casesQuery.split(',').filter(Boolean),
    [casesQuery],
  );
  const selectedId = params.get('model') ?? '';
  const runId = params.get('run') ?? '';
  const inspectTab = ['scores', 'raw'].includes(params.get('view') ?? '')
    ? params.get('view')!
    : 'preview';
  useEffect(() => {
    const controller = new AbortController();
    api<{ runs: ModelRunSummary[] }>('/model-arena/runs', {
      headers: RESEARCH_HEADERS,
      signal: controller.signal,
    })
      .then(async (result) => {
        setRuns(result.runs);
        setError('');
        let cursor = 0;
        async function worker() {
          while (cursor < result.runs.length && !controller.signal.aborted) {
            const run = result.runs[cursor++];
            try {
              const detail = await api<EvaluatedRun>(
                `/model-arena/runs/${encodeURIComponent(run.run_id)}`,
                { headers: RESEARCH_HEADERS, signal: controller.signal },
              );
              if (!controller.signal.aborted)
                setDetails((rows) => ({ ...rows, [run.run_id]: detail }));
            } catch (e) {
              if (!controller.signal.aborted)
                setError(e instanceof Error ? e.message : 'Unable to load run');
            }
          }
        }
        await Promise.all([worker(), worker(), worker()]);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [attempt, locale]);
  const filtered = (runs ?? []).filter(
    (run) =>
      `${run.model_id} ${run.case_id}`
        .toLowerCase()
        .includes(query.toLowerCase()) &&
      (mode !== 'case' ||
        !selectedCases.length ||
        selectedCases.includes(run.case_id)),
  );
  const grouped = new Map<string, ModelRunSummary[]>();
  filtered.forEach((run) =>
    grouped.set(run.model_id, [...(grouped.get(run.model_id) ?? []), run]),
  );
  const metrics = metricColumns(
    filtered.flatMap((run) =>
      details[run.run_id] ? [details[run.run_id]] : [],
    ),
  );
  const rows =
    mode === 'case'
      ? filtered.map((run) => ({
          id: run.run_id,
          label: run.model_id,
          caption: `${run.case_id} · ${run.run_id.slice(0, 8)}`,
          status: run.status,
          values: metricValues(
            details[run.run_id] ? [details[run.run_id]] : [],
          ),
        }))
      : [...grouped].map(([model, group]) => ({
          id: model,
          label: model,
          caption: `${group.length} ${zh ? '次运行' : 'runs'} · ${new Set(group.map((run) => run.case_id)).size} ${zh ? '个病例' : 'cases'}`,
          status: group.every((run) => run.status === 'COMPLETED')
            ? 'COMPLETED'
            : group.every((run) => run.status === 'ACTIVE')
              ? 'ACTIVE'
              : 'MIXED',
          values: metricValues(
            group.flatMap((run) =>
              details[run.run_id] ? [details[run.run_id]] : [],
            ),
          ),
        }));
  const inspected = (
    runId
      ? filtered.filter((run) => run.run_id === runId)
      : filtered.filter((run) => run.model_id === selectedId)
  ).flatMap((run) => (details[run.run_id] ? [details[run.run_id]] : []));
  const loaded = (runs ?? []).filter((run) => details[run.run_id]).length;
  useWorkspaceStatus([
    `${runs?.length ?? '—'} ${zh ? '次模型运行' : 'model runs'}`,
    `${grouped.size} ${zh ? '个模型' : 'models'}`,
    `${metrics.length} ${zh ? '项接口指标' : 'API metrics'}`,
  ]);
  return (
    <main className="ws-page compare-page">
      <header className="ws-page-heading">
        <div className="ws-heading-icon">
          <ChartNoAxesCombined size={20} />
        </div>
        <div>
          <h1>{zh ? '模型评测对比' : 'Compare'}</h1>
          <p>
            {zh
              ? '查看模型运行、逐例证据与评测结果'
              : 'Inspect model runs, case evidence and evaluation results'}
          </p>
        </div>
        <button
          className="ws-button"
          onClick={() => setAttempt((value) => value + 1)}
        >
          <RotateCw size={14} />
          {zh ? '刷新' : 'Refresh'}
        </button>
      </header>
      <Tabs
        className="ws-compare-tabs"
        value={mode}
        onValueChange={(value) =>
          update({ tab: String(value), model: null, run: null })
        }
      >
        <TabsList variant="line">
          <TabsTrigger value="overview">{zh ? '总览' : 'Overview'}</TabsTrigger>
          <TabsTrigger value="case">
            {zh ? '单例对标' : 'Case comparison'}
          </TabsTrigger>
          <TabsTrigger value="run">
            {zh ? '运行模型' : 'Run models'}
          </TabsTrigger>
        </TabsList>
      </Tabs>
      {error && (
        <div className="ws-error" role="alert">
          {error}
          <button
            className="ws-button"
            onClick={() => setAttempt((value) => value + 1)}
          >
            {zh ? '重试' : 'Retry'}
          </button>
        </div>
      )}
      {mode === 'run' ? (
        <div className="ws-legacy-model">
          <Suspense
            fallback={
              <div className="ws-empty">
                {zh ? '加载运行工作台…' : 'Loading run workspace…'}
              </div>
            }
          >
            <ModelArena />
          </Suspense>
        </div>
      ) : (
        <>
          <div className="ws-toolbar">
            <label className="ws-search">
              <Search size={15} />
              <input
                aria-label={zh ? '搜索模型' : 'Search models'}
                placeholder={zh ? '搜索模型、病例…' : 'Search model, case…'}
                value={query}
                onChange={(e) => update({ q: e.target.value }, true)}
              />
            </label>
            {mode === 'case' && (
              <select
                className="ws-button"
                aria-label={zh ? '选择对比病例' : 'Choose comparison case'}
                value={selectedCases.length === 1 ? selectedCases[0] : ''}
                onChange={(e) =>
                  update({ cases: e.target.value, case: null, run: null })
                }
              >
                <option value="">
                  {zh ? '所有已选病例' : 'All selected cases'}
                </option>
                {[
                  ...new Set([
                    ...(runs ?? []).map((run) => run.case_id),
                    ...selectedCases,
                  ]),
                ].map((id) => (
                  <option key={id}>{id}</option>
                ))}
              </select>
            )}
            <span className="ws-muted">
              {loaded}/{runs?.length ?? '—'}{' '}
              {zh ? '运行详情已加载' : 'run details loaded'}
            </span>
          </div>
          {mode === 'case' && selectedCases.length > 0 && (
            <div className="ws-case-chips">
              {selectedCases.map((id) => (
                <Link
                  key={id}
                  href={`/cases/${encodeURIComponent(id)}`}
                  className="ws-pill"
                >
                  {id}
                  {!runs?.some((run) => run.case_id === id) &&
                    ` · ${zh ? '暂无运行' : 'No runs'}`}
                </Link>
              ))}
            </div>
          )}
          {!metrics.length && runs && loaded === runs.length && (
            <div className="ws-metric-empty">
              {zh
                ? '现有运行尚未返回 evaluation.metrics。可查看运行记录和已有诊断审核；指标与方向由接口提供后自动显示。'
                : 'Existing runs do not return evaluation.metrics. Run records and diagnostic reviews are available; metric columns and directions will appear when provided by the API.'}
            </div>
          )}
          {metrics.length > 0 && (
            <p className="ws-metric-caption">
              {zh
                ? '总览取有效运行指标的均值（n 为有效值数）；↑ 越高越好，↓ 越低越好，— 仅描述、不排名。'
                : 'Overview uses the mean of available run metrics (n = values). ↑ Higher is better; ↓ lower is better; — descriptive, unranked.'}
            </p>
          )}
          <ResizablePanelGroup
            orientation="horizontal"
            className="ws-comparison-body"
          >
            <ResizablePanel id="comparison" minSize="300px">
              {runs ? (
                <MetricTable
                  metrics={metrics}
                  runs={rows}
                  selectedId={mode === 'case' ? runId : selectedId}
                  onSelect={(id) =>
                    update(
                      mode === 'case'
                        ? { run: id, model: null }
                        : { model: id, run: null },
                    )
                  }
                />
              ) : (
                <div className="ws-compare-loading">
                  {Array.from({ length: 6 }, (_, i) => (
                    <div key={i} className="ws-skeleton" />
                  ))}
                </div>
              )}
            </ResizablePanel>
            <InspectorPanel
              title={
                inspected[0]?.run.model_id ?? (zh ? '运行详情' : 'Run details')
              }
              open={Boolean(selectedId || runId)}
              onClose={() => update({ model: null, run: null })}
              tabs={[
                { id: 'preview', label: zh ? '预览' : 'Preview' },
                { id: 'scores', label: zh ? '评分' : 'Scores' },
                { id: 'raw', label: 'JSON' },
              ]}
              tab={inspectTab}
              onTabChange={(value) => update({ view: value })}
            >
              <RunInspector runs={inspected} tab={inspectTab} />
            </InspectorPanel>
          </ResizablePanelGroup>
        </>
      )}
    </main>
  );
}
