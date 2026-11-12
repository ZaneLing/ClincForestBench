'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightOpen,
  Maximize2,
  Minimize2,
  GitBranch,
  RotateCw,
  ArrowRightLeft,
  Database,
} from 'lucide-react';
import { ResizablePanelGroup, ResizablePanel } from '@/components/ui/resizable';
import { InspectorPanel } from '@/components/shell/inspector-panel';
import { useMediaQuery } from '@/components/shell/use-media-query';
import { useWorkspaceQuery } from '@/components/shell/use-workspace-query';
import { useWorkspaceStatus } from '@/components/shell/status-bar';
import { useLanguage } from '@/features/i18n/language-context';
import { api } from '@/lib/api';
import { useForest } from '@/features/forest/use-forest';
import { EncounterForestGraph } from '@/features/forest/encounter-forest-graph';
import { TraceTree } from '@/features/trace/trace-tree';
import { NodeInspector } from './node-inspector';
import { RESEARCH_HEADERS, type CaseDetail } from './types';
import '@/features/arena/encounter.css';
import '@/features/forest/encounter-case-inspector.css';
import './cases.css';
import './detail.css';

export function CaseDetailPage({ caseId }: { caseId: string }) {
  const { isChinese: zh, locale } = useLanguage();
  const { params, update } = useWorkspaceQuery();
  const desktop = useMediaQuery('(min-width: 1440px)');
  const inspectorDesktop = useMediaQuery('(min-width: 1201px)');
  const simulation = params.get('simulation') !== 'false';
  const { forest, traces, stats, busy, error, retry } = useForest(
    caseId,
    simulation,
  );
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [detailError, setDetailError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [treePreference, setTreePreference] = useState<boolean | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [zoom, setZoom] = useState(1);
  const treeOpen = treePreference ?? desktop;
  const selectedId = params.get('node') ?? '';
  const selected = forest?.nodes.find((node) => node.id === selectedId);
  const tabValue = params.get('tab') ?? 'details';
  const tab = ['details', 'evidence', 'raw'].includes(tabValue)
    ? tabValue
    : 'details';
  const inspectorOpen =
    params.get('inspector') !== 'closed' &&
    (Boolean(selectedId) || params.has('tab') || inspectorDesktop);
  const trace = traces.find((row) => row.id === params.get('trace'));
  const horizontal = params.get('layout') === 'horizontal';
  const selectNode = (id: string) => update({ node: id, inspector: null });
  const close = () => update({ inspector: 'closed' });
  useEffect(() => {
    const controller = new AbortController();
    api<CaseDetail>(`/research/case-library/${encodeURIComponent(caseId)}`, {
      headers: RESEARCH_HEADERS,
      signal: controller.signal,
    })
      .then((data) => {
        setDetail(data);
        setDetailError('');
      })
      .catch((e) => {
        if (!controller.signal.aborted) setDetailError(e.message);
      });
    return () => controller.abort();
  }, [caseId, locale, attempt]);
  useEffect(() => {
    function escape(event: KeyboardEvent) {
      if (event.key !== 'Escape' || document.querySelector('[role=dialog]'))
        return;
      const url = new URL(window.location.href);
      url.searchParams.set('inspector', 'closed');
      window.history.replaceState({}, '', url);
      window.dispatchEvent(new Event('workspace-query'));
    }
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, []);
  useWorkspaceStatus([
    `${stats.nodes} ${zh ? '节点' : 'nodes'} / ${stats.edges} ${zh ? '边' : 'edges'}`,
    `${stats.sessions} ${zh ? '条轨迹' : 'traces'}`,
    `${stats.endpoints} ${zh ? '个终点' : 'endpoints'}`,
    `${trace?.label ?? (zh ? '全部路径' : 'All paths')}`,
    `${zh ? '缩放' : 'Zoom'} ${Math.round(zoom * 100)}%`,
  ]);
  return (
    <main className="ws-page case-detail-page">
      <header className="ws-case-header">
        <Link
          className="ws-icon-button"
          href="/cases"
          aria-label={zh ? '返回病例库' : 'Back to cases'}
        >
          <ArrowLeft size={16} />
        </Link>
        <Link href="/cases" className="ws-muted">
          {zh ? '病例库' : 'Cases'}
        </Link>
        <span className="ws-muted">/</span>
        <h1 className="ws-mono">{caseId}</h1>
        <span className="ws-pill">{detail?.dataset ?? '…'}</span>
        <select
          className="ws-button"
          aria-label={zh ? '轨迹来源' : 'Trace source'}
          value={simulation ? 'simulation' : 'doctor'}
          onChange={(e) =>
            update({
              simulation: String(e.target.value === 'simulation'),
              node: null,
              trace: null,
            })
          }
        >
          <option value="simulation">{zh ? '模拟数据' : 'Simulation'}</option>
          <option value="doctor">{zh ? '真实医生' : 'Doctor visits'}</option>
        </select>
        <Link
          className="ws-button ws-classic-link"
          href={`/forest?mode=classic&case=${encodeURIComponent(caseId)}&simulation=${simulation}`}
        >
          {zh ? '经典森林' : 'Classic forest'}
        </Link>
        <button
          className="ws-icon-button"
          aria-label={zh ? '打开检查器' : 'Open inspector'}
          onClick={() => update({ inspector: null, tab })}
        >
          <PanelRightOpen size={16} />
        </button>
      </header>
      {(error || detailError) && (
        <div className="ws-error" role="alert">
          {error || detailError}
          <button
            className="ws-button"
            onClick={() => {
              retry();
              setAttempt((value) => value + 1);
            }}
          >
            {zh ? '重试' : 'Retry'}
          </button>
        </div>
      )}
      {selectedId && forest && !selected && (
        <div className="ws-error">
          {zh
            ? '链接中的节点不在当前森林中。'
            : 'The linked node is not in this forest.'}
          <button onClick={() => update({ node: null })}>
            {zh ? '清除选择' : 'Clear selection'}
          </button>
        </div>
      )}
      <div className="ws-case-body">
        {treeOpen && (
          <aside className="ws-trace-panel">
            <header>
              <GitBranch size={15} />
              <b>{zh ? '轨迹' : 'Traces'}</b>
              <span className="ws-pill">{stats.sessions}</span>
              <button
                className="ws-icon-button"
                aria-label={zh ? '收起轨迹树' : 'Hide trace tree'}
                onClick={() => setTreePreference(false)}
              >
                <PanelLeftClose size={15} />
              </button>
            </header>
            <p className="ws-trace-note">
              {zh
                ? '事件时间未记录 · ↑↓ 移动'
                : 'Timing not recorded · ↑↓ to navigate'}
            </p>
            <TraceTree
              key={`${collapsed}-${simulation}`}
              runs={traces}
              selectedId={selectedId}
              onSelect={selectNode}
              collapseKey={collapsed ? 'collapsed' : 'expanded'}
            />
          </aside>
        )}
        <ResizablePanelGroup
          orientation="horizontal"
          className="ws-case-panels"
        >
          <ResizablePanel id="canvas" minSize="240px">
            <section className="ws-case-canvas">
              <div className="ws-canvas-toolbar">
                <button
                  className="ws-icon-button"
                  aria-label={zh ? '切换轨迹树' : 'Toggle trace tree'}
                  onClick={() => setTreePreference(!treeOpen)}
                >
                  <PanelLeftOpen size={15} />
                </button>
                <button
                  className="ws-icon-button"
                  aria-label={zh ? '展开全部' : 'Expand all'}
                  title={zh ? '展开全部' : 'Expand all'}
                  onClick={() => setCollapsed(false)}
                >
                  <Maximize2 size={14} />
                </button>
                <button
                  className="ws-icon-button"
                  aria-label={zh ? '收起节点' : 'Collapse nodes'}
                  title={zh ? '收起节点' : 'Collapse nodes'}
                  onClick={() => setCollapsed(true)}
                >
                  <Minimize2 size={14} />
                </button>
                <select
                  aria-label={zh ? '筛选轨迹' : 'Filter trace'}
                  value={trace?.id ?? ''}
                  onChange={(e) => update({ trace: e.target.value })}
                >
                  <option value="">{zh ? '全部轨迹' : 'All traces'}</option>
                  {traces.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.label}
                    </option>
                  ))}
                </select>
                <button
                  className="ws-icon-button"
                  aria-label={zh ? '切换布局' : 'Switch layout'}
                  title={zh ? '切换布局' : 'Switch layout'}
                  onClick={() =>
                    update({ layout: horizontal ? null : 'horizontal' })
                  }
                >
                  <ArrowRightLeft size={15} />
                </button>
                <button
                  className="ws-icon-button"
                  aria-label={zh ? '刷新森林' : 'Refresh forest'}
                  onClick={retry}
                >
                  <RotateCw size={14} />
                </button>
              </div>
              {busy ? (
                <output className="ws-layout-loading">
                  <GitBranch size={24} />
                  <span>{zh ? '正在布局…' : 'Preparing forest…'}</span>
                </output>
              ) : forest?.nodes.length ? (
                <EncounterForestGraph
                  canvasOnly
                  forest={forest}
                  chinese={zh}
                  selectedId={selectedId}
                  onSelect={selectNode}
                  collapsed={collapsed}
                  horizontal={horizontal}
                  traceNodeIds={trace?.nodes.map((node) => node.id)}
                  onZoom={setZoom}
                />
              ) : (
                <div className="ws-forest-empty">
                  <Database size={26} />
                  <h2>
                    {simulation
                      ? zh
                        ? '该病例暂无模拟轨迹'
                        : 'No simulation traces for this case'
                      : zh
                        ? '该病例暂无医生轨迹'
                        : 'No doctor traces for this case'}
                  </h2>
                  <p>
                    {zh
                      ? '可继续检查初始信息和固定证据。'
                      : 'Initial information and source evidence are available.'}
                  </p>
                  <button
                    className="ws-button"
                    onClick={() =>
                      update({ node: null, tab: 'evidence', inspector: null })
                    }
                  >
                    {zh
                      ? '查看 Case 原始证据 →'
                      : 'View case source evidence →'}
                  </button>
                </div>
              )}
            </section>
          </ResizablePanel>
          <InspectorPanel
            title={
              selected
                ? `${selected.id} · ${selected.count} ${zh ? '条轨迹' : 'traces'}`
                : caseId
            }
            badge={
              <span
                className={`ws-pill ${simulation ? 'simulation' : 'recorded'}`}
              >
                {simulation
                  ? zh
                    ? '模拟'
                    : 'Simulation'
                  : zh
                    ? '医生'
                    : 'Doctor'}
              </span>
            }
            tabs={[
              { id: 'details', label: zh ? '详情' : 'Details' },
              { id: 'evidence', label: zh ? '证据' : 'Evidence' },
              { id: 'raw', label: zh ? '原始' : 'JSON' },
            ]}
            tab={tab}
            onTabChange={(value) => update({ tab: value })}
            open={inspectorOpen}
            onClose={close}
          >
            <NodeInspector
              key={selected?.id ?? caseId}
              node={selected}
              detail={detail}
              caseId={caseId}
              tab={tab}
            />
          </InspectorPanel>
        </ResizablePanelGroup>
      </div>
    </main>
  );
}
