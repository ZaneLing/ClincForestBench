'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import { AnimatePresence, motion } from 'motion/react';
import {
  Activity,
  BadgeCheck,
  Beaker,
  BrainCircuit,
  CircleStop,
  Clock3,
  FileClock,
  GitBranch,
  HeartPulse,
  History,
  Pause,
  Play,
  RotateCcw,
  ScanLine,
  SkipForward,
  Stethoscope,
  TriangleAlert,
  Waves,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { api } from '@/lib/api';
import type {
  TemporalCase,
  TemporalCaseDetail,
  TemporalEvent,
  TemporalGraphNode,
  TemporalManifest,
} from './types';

type FlowData = {
  source: TemporalGraphNode;
  pending: boolean;
  onInspect: (id: string) => void;
};
type TemporalFlowNode = Node<FlowData, 'temporalNode'>;
const nodeTypes = { temporalNode: TemporalNode };

export function TemporalDashboard() {
  const [manifest, setManifest] = useState<TemporalManifest | null>(null);
  const [detail, setDetail] = useState<TemporalCaseDetail | null>(null);
  const [dataset, setDataset] = useState('ALL');
  const [caseId, setCaseId] = useState('');
  const [currentTime, setCurrentTime] = useState(0);
  const [selectedNodeId, setSelectedNodeId] = useState('');
  const [playing, setPlaying] = useState(false);
  const [notice, setNotice] = useState('正在读取本地 Temporal v2 MVP…');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function loadCase(nextCaseId: string) {
    setPlaying(false);
    setNotice('正在组装真实时间事件…');
    try {
      const next = await api<TemporalCaseDetail>(
        `/research/temporal/cases/${nextCaseId}`,
        { headers: { 'X-Research-Key': 'local-research-only' } },
      );
      setDetail(next);
      setCaseId(nextCaseId);
      setCurrentTime(0);
      setSelectedNodeId(
        next.case.temporal_graph.nodes.find(
          (node) => node.node_type === 'CONTEXT',
        )?.node_id ?? next.case.temporal_graph.root_id,
      );
      setNotice(
        `${nextCaseId} · ${next.case.timeline_events.length} 个真实事件 · 0 个合成结果`,
      );
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Case 读取失败');
    }
  }

  useEffect(() => {
    void api<TemporalManifest>('/research/temporal/cases', {
      headers: { 'X-Research-Key': 'local-research-only' },
    })
      .then(async (nextManifest) => {
        setManifest(nextManifest);
        if (!nextManifest.cases.length) {
          setNotice('Temporal v2 尚未生成，请先运行 make preprocess-temporal。');
          return;
        }
        await loadCase(nextManifest.cases[0].case_id);
      })
      .catch((error: Error) => setNotice(error.message));
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  const caseData = detail?.case ?? null;
  const thresholds = useMemo(
    () =>
      Array.from(
        new Set(
          (caseData?.temporal_graph.nodes ?? []).map((node) =>
            Math.max(0, Number(node.reveal_time_min.toFixed(2))),
          ),
        ),
      ).sort((left, right) => left - right),
    [caseData],
  );
  const maxTime = thresholds.at(-1) ?? 0;
  const visibleEntries = useMemo(
    () =>
      (manifest?.cases ?? []).filter(
        (item) => dataset === 'ALL' || item.dataset_name === dataset,
      ),
    [dataset, manifest],
  );

  useEffect(() => {
    if (!playing || !caseData) return;
    const next = thresholds.find((value) => value > currentTime + 0.001);
    if (next === undefined) return;
    timer.current = setTimeout(() => {
      setCurrentTime(next);
      if (next === thresholds.at(-1)) setPlaying(false);
    }, 760);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [caseData, currentTime, playing, thresholds]);

  function stepForward() {
    const next = thresholds.find((value) => value > currentTime + 0.001);
    if (next !== undefined) setCurrentTime(next);
  }

  const selectedNode = caseData?.temporal_graph.nodes.find(
    (node) => node.node_id === selectedNodeId,
  );
  const selectedEvent = selectedNode?.event_id
    ? caseData?.timeline_events.find(
        (event) => event.event_id === selectedNode.event_id,
      )
    : undefined;
  const pendingEvents = (caseData?.timeline_events ?? []).filter((event) => {
    const order = eventOrder(event);
    const available = eventAvailable(event);
    return order <= currentTime && available > currentTime;
  });

  if (manifest?.status === 'NOT_BUILT') {
    return (
      <main className="temporal-empty-page">
        <div>
          <FileClock />
          <p>Temporal Forest v2</p>
          <h1>本地受控数据尚未转换</h1>
          <span>
            运行 <code>{manifest.build_command}</code> 后，本页面会读取 15 个本地 MVP Case。
          </span>
        </div>
      </main>
    );
  }

  return (
    <main className="temporal-page">
      <header className="temporal-header">
        <div className="temporal-title">
          <span><BrainCircuit /></span>
          <div>
            <small>ClincForestBench · Temporal Forest v2</small>
            <h1>真实时间驱动的动态诊断树</h1>
          </div>
        </div>
        <div className="temporal-controls">
          <label>
            <span>数据源</span>
            <select
              onChange={(event) => {
                const value = event.target.value;
                setDataset(value);
                const first = manifest?.cases.find(
                  (item) => value === 'ALL' || item.dataset_name === value,
                );
                if (first) void loadCase(first.case_id);
              }}
              value={dataset}
            >
              <option value="ALL">全部 · {manifest?.case_count ?? 0}</option>
              {Object.entries(manifest?.dataset_case_counts ?? {}).map(
                ([name, count]) => (
                  <option key={name} value={name}>{name} · {count}</option>
                ),
              )}
            </select>
          </label>
          <label className="temporal-case-picker">
            <span>Case</span>
            <select
              onChange={(event) => void loadCase(event.target.value)}
              value={caseId}
            >
              {visibleEntries.map((item) => (
                <option key={item.case_id} value={item.case_id}>
                  {item.case_id} · {item.event_count} events
                </option>
              ))}
            </select>
          </label>
          <Badge className="temporal-real-badge">
            <BadgeCheck /> REAL OBSERVATIONS ONLY
          </Badge>
        </div>
      </header>

      <section className="temporal-player-bar">
        <div className="temporal-play-buttons">
          <Button
            aria-label="从头播放"
            onClick={() => { setCurrentTime(0); setPlaying(true); }}
            size="icon"
            variant="outline"
          ><RotateCcw /></Button>
          <Button
            aria-label={playing ? '暂停' : '播放'}
            onClick={() => setPlaying((value) => !value)}
            size="icon"
          >{playing ? <Pause /> : <Play />}</Button>
          <Button
            aria-label="下一时间节点"
            onClick={stepForward}
            size="icon"
            variant="outline"
          ><SkipForward /></Button>
        </div>
        <div className="temporal-clock">
          <Clock3 /><b>{formatTime(currentTime)}</b><span>/ {formatTime(maxTime)}</span>
        </div>
        <Slider
          aria-label="临床时间"
          className="temporal-slider"
          max={Math.max(maxTime, 1)}
          min={0}
          onValueChange={(value) => {
            setPlaying(false);
            setCurrentTime(Number(Array.isArray(value) ? value[0] : value));
          }}
          step={1}
          value={currentTime}
        />
        <div className="temporal-stage-count">
          <span>
            {caseData?.temporal_graph.nodes.filter(
              (node) => node.reveal_time_min <= currentTime,
            ).length ?? 0}
          </span>
          / {caseData?.temporal_graph.nodes.length ?? 0} nodes
        </div>
      </section>

      <section className="temporal-workspace">
        <aside className="temporal-ledger">
          <header>
            <History />
            <span><small>EVENT LEDGER</small><b>真实事件账本</b></span>
          </header>
          <div className="temporal-ledger-body">
            {(caseData?.timeline_events ?? []).map((event) => {
              const order = eventOrder(event);
              const available = eventAvailable(event);
              const status =
                available <= currentTime
                  ? 'available'
                  : order <= currentTime
                    ? 'pending'
                    : 'future';
              return (
                <button
                  aria-label={`查看 ${event.clinical_concept.display}`}
                  className={`temporal-ledger-row is-${status}`}
                  key={event.event_id}
                  onClick={() =>
                    setSelectedNodeId(
                      `${event.event_id}::${status === 'available' ? 'RESULT' : 'ACTION'}`,
                    )
                  }
                  type="button"
                >
                  <span
                    className={`temporal-ledger-dot modality-${event.clinical_concept.modality.toLowerCase()}`}
                  />
                  <span className="temporal-ledger-copy">
                    <b>{event.clinical_concept.display}</b>
                    <small>{event.action_id}</small>
                  </span>
                  <span className="temporal-ledger-time">
                    <b>{formatTime(available)}</b>
                    <small>
                      {status === 'pending' ? 'PENDING' : status.toUpperCase()}
                    </small>
                  </span>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="temporal-canvas-panel">
          <div className="temporal-canvas-meta">
            <span>
              <Waves /> {caseData?.task_type.replaceAll('_', ' ') ?? 'TEMPORAL CASE'}
            </span>
            <span>{pendingEvents.length} pending</span>
            <span>{notice}</span>
          </div>
          {caseData && (
            <TemporalCanvas
              caseData={caseData}
              currentTime={currentTime}
              onInspect={setSelectedNodeId}
              selectedNodeId={selectedNodeId}
            />
          )}
          <div className="temporal-legend">
            <Legend tone="context" label="S0" />
            <Legend tone="lab" label="化验" />
            <Legend tone="imaging" label="影像" />
            <Legend tone="ecg" label="ECG" />
            <Legend tone="pending" label="等待结果" />
            <Legend tone="intervention" label="状态改变干预" />
            <Legend tone="reference" label="回顾性参考" />
          </div>
        </section>

        <aside className="temporal-inspector">
          <header>
            <Stethoscope />
            <span>
              <small>STATE @ {formatTime(currentTime)}</small>
              <b>节点与时间语义</b>
            </span>
          </header>
          <div className="temporal-inspector-body">
            <AnimatePresence mode="wait">
              <motion.section
                animate={{ opacity: 1, y: 0 }}
                className="temporal-detail-card"
                initial={{ opacity: 0, y: 8 }}
                key={selectedNode?.node_id ?? 'initial'}
              >
                <div className="temporal-detail-heading">
                  <span
                    className={`temporal-detail-icon modality-${(selectedNode?.lane ?? 'context').toLowerCase()}`}
                  >
                    {iconFor(selectedNode?.lane ?? 'CONTEXT')}
                  </span>
                  <div>
                    <small>{selectedNode?.node_type ?? 'STATE'}</small>
                    <b>{selectedNode?.label ?? '选择一个节点'}</b>
                    <span>{selectedNode?.subtitle}</span>
                  </div>
                </div>
                {selectedNode && (
                  <TimeFacts node={selectedNode} event={selectedEvent} />
                )}
                <pre>
                  {JSON.stringify(
                    selectedEvent?.result ??
                      (selectedNode?.node_type === 'CONTEXT'
                        ? caseData?.initial_state
                        : selectedNode?.data) ??
                      caseData?.initial_state ??
                      {},
                    null,
                    2,
                  )}
                </pre>
              </motion.section>
            </AnimatePresence>

            <section className="temporal-pending-card">
              <div>
                <Clock3 /><b>Pending actions</b><span>{pendingEvents.length}</span>
              </div>
              {pendingEvents.length ? (
                pendingEvents.map((event) => (
                  <button
                    key={event.event_id}
                    onClick={() =>
                      setSelectedNodeId(`${event.event_id}::ACTION`)
                    }
                    type="button"
                  >
                    <span>
                      <b>{event.clinical_concept.display}</b>
                      <small>{event.action_id}</small>
                    </span>
                    <em>{formatTime(eventAvailable(event))}</em>
                  </button>
                ))
              ) : (
                <p>当前没有等待中的结果。</p>
              )}
            </section>

            <section className="temporal-quality-card">
              <div><TriangleAlert /><b>时间质量与边界</b></div>
              <p>
                <span>Anchor</span>
                <b>{String(caseData?.temporal_quality.anchor_confidence ?? '—')}</b>
              </p>
              <p>
                <span>核心事件</span>
                <b>
                  {String(
                    caseData?.temporal_quality.core_event_minimum_confidence ??
                      '—',
                  )}+
                </b>
              </p>
              {(caseData?.temporal_quality.warnings ?? []).map((warning) => (
                <small key={warning}>{humanize(warning)}</small>
              ))}
            </section>
            {detail?.trajectory_evaluation && <section className="temporal-case-evaluation-card">
              <div><GitBranch /><b>此 Case 的轨迹评估</b><span>{detail.trajectory_evaluation.completed_trajectory_count} runs</span></div>
              {detail.trajectory_evaluation.status === 'READY' ? <div className="temporal-case-evaluation-grid">
                <span><small>Top-1</small><b>{evaluationPercent(detail.trajectory_evaluation.aggregate.exact_top1_accuracy)}</b></span>
                <span><small>GT 节点重合</small><b>{evaluationPercent(detail.trajectory_evaluation.aggregate.mean_recorded_action_overlap_rate)}</b></span>
                <span><small>证据揭示</small><b>{evaluationPercent(detail.trajectory_evaluation.aggregate.mean_source_evidence_reveal_coverage)}</b></span>
                <span><small>错误早停</small><b>{evaluationPercent(detail.trajectory_evaluation.aggregate.premature_finalization_proxy_rate)}</b></span>
              </div> : <p>还没有完成轨迹；评估协议已经绑定，完成后自动计算。</p>}
              <details><summary>指标口径与解释限制</summary><div>{detail.trajectory_evaluation.metric_definitions.map((item) => <p key={item.key}><b>{item.label}</b><span>{item.description}</span></p>)}{detail.trajectory_evaluation.interpretation_limits.map((item) => <em key={item}>{item}</em>)}</div></details>
            </section>}
          </div>
        </aside>
      </section>
    </main>
  );
}

export function TemporalCanvas({
  caseData,
  currentTime,
  selectedNodeId,
  onInspect,
}: {
  caseData: TemporalCase;
  currentTime: number;
  selectedNodeId: string;
  onInspect: (id: string) => void;
}) {
  const flow = useMemo(
    () => buildFlow(caseData, currentTime, selectedNodeId, onInspect),
    [caseData, currentTime, onInspect, selectedNodeId],
  );
  return (
    <div className="temporal-flow-canvas">
      <ReactFlow
        edges={flow.edges}
        fitView
        fitViewOptions={{ padding: 0.12, minZoom: 0.18, maxZoom: 0.9 }}
        maxZoom={2.4}
        minZoom={0.08}
        key={`${caseData.case_id}:${currentTime}`}
        nodes={flow.nodes}
        nodesConnectable={false}
        nodesDraggable={false}
        nodeTypes={nodeTypes}
        onNodeClick={(_, node) => onInspect(node.id)}
        onInit={(instance) => {
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              void instance.fitView({
                duration: 220,
                maxZoom: 0.9,
                minZoom: 0.18,
                padding: 0.12,
              });
            });
          });
        }}
        panOnDrag
        proOptions={{ hideAttribution: true }}
        zoomOnScroll
      >
        <Background
          color="#86b6c2"
          gap={24}
          size={1}
          variant={BackgroundVariant.Dots}
        />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

function buildFlow(
  caseData: TemporalCase,
  currentTime: number,
  selectedNodeId: string,
  onInspect: (id: string) => void,
): { nodes: TemporalFlowNode[]; edges: Edge[] } {
  const all = caseData.temporal_graph.nodes;
  const visible = all.filter(
    (node) => node.reveal_time_min <= currentTime + 0.001,
  );
  const timeRanks = new Map(
    Array.from(new Set(all.map((node) => node.reveal_time_min)))
      .sort((left, right) => left - right)
      .map((value, index) => [value, index]),
  );
  const occupied = new Map<string, number>();
  const positions = new Map<string, { x: number; y: number }>();
  for (const node of all) {
    const rank = timeRanks.get(node.reveal_time_min) ?? 0;
    const lane = laneX(node.lane);
    const key = `${rank}:${lane}`;
    const collision = occupied.get(key) ?? 0;
    occupied.set(key, collision + 1);
    positions.set(node.node_id, {
      x: lane + collision * 72 + (node.node_type === 'RESULT' ? 72 : 0),
      y: rank * 118,
    });
  }
  const visibleIds = new Set(visible.map((node) => node.node_id));
  const pendingEventIds = new Set(
    caseData.timeline_events
      .filter(
        (event) =>
          eventOrder(event) <= currentTime && eventAvailable(event) > currentTime,
      )
      .map((event) => event.event_id),
  );
  const nodes = visible.map<TemporalFlowNode>((node) => ({
    id: node.node_id,
    type: 'temporalNode',
    position: positions.get(node.node_id) ?? { x: 520, y: 0 },
    selected: node.node_id === selectedNodeId,
    data: {
      source: node,
      pending: Boolean(
        node.event_id &&
          pendingEventIds.has(node.event_id) &&
          node.node_type === 'ACTION',
      ),
      onInspect,
    },
  }));
  const edges = caseData.temporal_graph.edges.flatMap<Edge>((edge) => {
    if (
      !visibleIds.has(edge.source_node) ||
      !visibleIds.has(edge.target_node)
    )
      return [];
    const isResult = edge.edge_type === 'RESULT_AVAILABLE';
    const isReference = edge.edge_type === 'SUPPORTS_REFERENCE';
    const color = isReference ? '#dc2626' : isResult ? '#0891b2' : '#6b8e99';
    return [
      {
        id: edge.edge_id,
        source: edge.source_node,
        target: edge.target_node,
        type: 'smoothstep',
        animated: isResult,
        label:
          isResult && edge.latency_min
            ? `+${Math.round(edge.latency_min)}m`
            : undefined,
        labelStyle: { fill: '#4b6570', fontSize: 10, fontWeight: 700 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color,
          width: 12,
          height: 12,
        },
        style: {
          stroke: color,
          strokeWidth: isReference ? 2.2 : 1.5,
        },
      },
    ];
  });
  return { nodes, edges };
}

function TemporalNode({ data, selected }: NodeProps<TemporalFlowNode>) {
  const node = data.source;
  const tone = nodeTone(node);
  return (
    <motion.button
      animate={{ opacity: 1, scale: 1 }}
      aria-label={`${node.node_type}: ${node.label}`}
      className={`temporal-flow-node tone-${tone} ${selected ? 'is-selected' : ''} ${data.pending ? 'is-pending' : ''}`}
      initial={{ opacity: 0, scale: 0.35 }}
      onClick={() => data.onInspect(node.node_id)}
      title={`${node.label}\n${node.subtitle}\n${formatTime(node.game_time_min)}`}
      transition={{ type: 'spring', stiffness: 280, damping: 20 }}
      type="button"
    >
      <Handle id="top" position={Position.Top} type="target" />
      {iconFor(node.lane)}
      <Handle id="bottom" position={Position.Bottom} type="source" />
      <span>
        <b>{node.label}</b>
        <small>{formatTime(node.game_time_min)}</small>
      </span>
    </motion.button>
  );
}

function TimeFacts({
  node,
  event,
}: {
  node: TemporalGraphNode;
  event?: TemporalEvent;
}) {
  return (
    <div className="temporal-time-facts">
      <span><small>节点时间</small><b>{formatTime(node.game_time_min)}</b></span>
      <span><small>置信度</small><b>{node.temporal_confidence}</b></span>
      {event && (
        <>
          <span><small>下单</small><b>{nullableTime(event.time.relative_order_min)}</b></span>
          <span><small>采集</small><b>{nullableTime(event.time.relative_acquired_min)}</b></span>
          <span><small>可见</small><b>{nullableTime(event.time.relative_available_min)}</b></span>
          <span>
            <small>重放</small>
            <b>{event.arena.temporal_replay_mode.replaceAll('_', ' ')}</b>
          </span>
        </>
      )}
    </div>
  );
}

function Legend({ tone, label }: { tone: string; label: string }) {
  return <span><i className={`tone-${tone}`} />{label}</span>;
}

function eventOrder(event: TemporalEvent) {
  return firstNumber(
    event.time.relative_order_min,
    event.time.relative_start_min,
    event.time.relative_acquired_min,
    event.time.relative_available_min,
    event.time.relative_documented_min,
  );
}

function eventAvailable(event: TemporalEvent) {
  return firstNumber(
    event.time.relative_available_min,
    event.time.relative_documented_min,
    event.time.relative_acquired_min,
    event.time.relative_end_min,
    event.time.relative_start_min,
    event.time.relative_order_min,
  );
}

function firstNumber(...values: Array<number | null | undefined>) {
  return values.find((value): value is number => typeof value === 'number') ?? 0;
}

function nullableTime(value?: number | null) {
  return typeof value === 'number' ? formatTime(value) : '未提供';
}

function formatTime(value: number) {
  const sign = value < 0 ? '−' : '+';
  const absolute = Math.abs(Math.round(value));
  if (absolute < 60) return `T${sign}${absolute}m`;
  const hours = Math.floor(absolute / 60);
  const minutes = absolute % 60;
  return `T${sign}${hours}h${minutes ? `${minutes}m` : ''}`;
}

function laneX(lane: string) {
  return (
    {
      ANCHOR: 520,
      CONTEXT: 520,
      HISTORY: 80,
      EXAM: 80,
      VITALS: 80,
      LAB: 280,
      IMAGING: 520,
      ECG: 760,
      CARDIOLOGY: 760,
      INTERVENTION: 980,
      DIAGNOSIS: 980,
      REFERENCE: 520,
    } as Record<string, number>
  )[lane] ?? 520;
}

function nodeTone(node: TemporalGraphNode) {
  if (node.node_type === 'ROOT' || node.node_type === 'CONTEXT') return 'context';
  if (node.node_type === 'REFERENCE') return 'reference';
  if (node.node_type === 'INTERVENTION') return 'intervention';
  if (node.node_type === 'ACTION') return 'action';
  return node.lane.toLowerCase();
}

function iconFor(lane: string) {
  if (lane === 'LAB') return <Beaker />;
  if (lane === 'IMAGING') return <ScanLine />;
  if (lane === 'ECG' || lane === 'CARDIOLOGY') return <Activity />;
  if (lane === 'INTERVENTION') return <CircleStop />;
  if (lane === 'HISTORY' || lane === 'EXAM') return <History />;
  if (lane === 'REFERENCE' || lane === 'DIAGNOSIS') return <Stethoscope />;
  return <HeartPulse />;
}

function humanize(value: string) {
  return value
    .toLowerCase()
    .replaceAll('_', ' ')
    .replace(/^./, (letter) => letter.toUpperCase());
}

function evaluationPercent(value: number | null | undefined) {
  return typeof value === 'number' ? `${Math.round(value * 100)}%` : '待生成';
}
