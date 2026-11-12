'use client';

import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
  ReactFlow,
  Handle,
  Position,
  Controls,
  Background,
  MarkerType,
  type Node,
  type NodeProps,
  type Edge,
} from '@xyflow/react';
import { ResultValue } from '@/features/arena/encounter-presentation';
import {
  GitBranch,
  MessageCircle,
  Stethoscope,
  CheckCheck,
} from 'lucide-react';

type Label = { en: string; 'zh-CN': string };
export type EncounterForestNode = {
  id: string;
  label: string;
  count: number;
  event_type?: string;
  case_id?: string;
  is_simulation?: boolean;
  item?: { id?: string; kind?: string; category?: string; label: Label };
  reason_id?: string;
  result_status?: string;
  example?: {
    records?: {
      source_id?: string;
      source_label?: string;
      result: unknown;
      text?: string;
    }[];
    diagnoses?: string[];
    reason_options?: { id: string; label: Label }[];
    reason_text?: string;
    hypothesis?: string;
    text?: string;
  };
};
export type EncounterForestData = {
  session_count: number;
  record_type: 'DOCTOR' | 'SIMULATION';
  cases: { case_id: string; dataset: string }[];
  nodes: EncounterForestNode[];
  edges: { source: string; target: string; count: number }[];
  reason_counts: Record<string, number>;
  demo_visits?: { encounter_id: string; case_id: string; status: string }[];
};

type FlowData = {
  label: string;
  subtitle: string;
  kind: string;
  simulation: boolean;
  count: number;
  status: string;
  itemKind?: string;
  horizontal?: boolean;
};
type FlowNode = Node<FlowData, 'encounterForest'>;
const nodeTypes = { encounterForest: ForestNodeView };
export const reasons: Record<string, [string, string]> = {
  support: ['Support diagnosis', '支持诊断'],
  differentiate: ['Differentiate', '鉴别诊断'],
  urgent: ['Assess urgency', '评估紧急情况'],
  severity: ['Assess severity', '评估严重程度'],
  other: ['Other', '其他'],
};

export function forestNodeLabel(node: EncounterForestNode, chinese: boolean) {
  if (node.item) return node.item.label[chinese ? 'zh-CN' : 'en'];
  if (node.event_type === 'DIAGNOSIS')
    return chinese ? '记录诊断' : 'Recorded diagnosis';
  if (node.event_type === 'COMPLETE')
    return chinese ? '完成就诊' : 'Visit completed';
  if (node.event_type === 'PRESCRIPTION')
    return chinese ? '处方 / 治疗' : 'Prescription / treatment';
  return node.label;
}

export function buildEncounterForestGraph(
  forest: EncounterForestData,
  chinese: boolean,
) {
  const incoming = new Set(forest.edges.map((edge) => edge.target));
  const rows = new Map(forest.nodes.map((node) => [node.id, node]));
  const children = new Map<string, string[]>();
  for (const edge of forest.edges) {
    children.set(edge.source, [
      ...(children.get(edge.source) ?? []),
      edge.target,
    ]);
  }
  const placed = new Map<string, { x: number; y: number; depth: number }>();
  let leaf = 0;
  function place(id: string, depth: number, path: Set<string>): number {
    if (path.has(id) || !rows.has(id)) return leaf * 310;
    const nextPath = new Set(path).add(id);
    const descendants = (children.get(id) ?? []).filter(
      (child) => !nextPath.has(child),
    );
    const xs = descendants.map((child) => place(child, depth + 1, nextPath));
    const x = xs.length
      ? xs.reduce((sum, value) => sum + value, 0) / xs.length
      : leaf++ * 310;
    placed.set(id, { x, y: depth * 130, depth });
    return x;
  }
  forest.nodes
    .filter((node) => !incoming.has(node.id))
    .forEach((node) => place(node.id, 0, new Set()));
  const nodes: FlowNode[] = forest.nodes
    .filter((node) => placed.has(node.id))
    .map((node) => {
      const point = placed.get(node.id)!;
      const reason = node.reason_id
        ? (reasons[node.reason_id]?.[chinese ? 1 : 0] ?? node.reason_id)
        : '';
      return {
        id: node.id,
        type: 'encounterForest',
        position: { x: point.x, y: point.y },
        data: {
          label: forestNodeLabel(node, chinese),
          count: node.count,
          subtitle: `S${point.depth}${reason ? ' · ' + reason : ''}`,
          kind: node.event_type ?? 'INITIAL',
          simulation: forest.record_type === 'SIMULATION',
          status: node.result_status ?? node.event_type ?? 'INITIAL',
          itemKind: node.item?.kind,
        },
      };
    });
  const edges: Edge[] = forest.edges.map((edge, index) => ({
    id: `edge-${index}`,
    source: edge.source,
    target: edge.target,
    type: 'straight',
    markerEnd: { type: MarkerType.ArrowClosed },
    label: String(edge.count),
    style: {
      strokeWidth: 1 + Math.max(0, Math.min(edge.count, 4) - 1) * 0.5,
      stroke: '#94a3b8',
    },
  }));
  return { nodes, edges };
}

export function EncounterForestGraph({
  forest,
  chinese,
  selectedId: controlledId,
  onSelect,
  canvasOnly = false,
  collapsed = false,
  traceNodeIds,
  horizontal = false,
  onZoom,
}: {
  forest: EncounterForestData;
  chinese: boolean;
  selectedId?: string;
  onSelect?: (id: string) => void;
  canvasOnly?: boolean;
  collapsed?: boolean;
  traceNodeIds?: string[];
  horizontal?: boolean;
  onZoom?: (zoom: number) => void;
}) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const [canvasSize, setCanvasSize] = useState<{
    width: number;
    height: number;
  } | null>(null);
  useLayoutEffect(() => {
    const canvas = canvasRef.current;
    if (!canvasOnly || !canvas) return;
    let timer = 0;
    let resizing = false;
    const measure = () => {
      const { width, height } = canvas.getBoundingClientRect();
      setCanvasSize((previous) =>
        previous?.width === width && previous?.height === height
          ? previous
          : { width, height },
      );
    };
    measure();
    const schedule = () => {
      window.clearTimeout(timer);
      if (!resizing) timer = window.setTimeout(measure, 60);
    };
    // Keep the graph viewport stable for the whole splitter gesture. Its
    // synchronous size observer can otherwise flush ancestor layout mid-drag.
    const beginResize = (event: Event) => {
      const target = event.target;
      if (
        target instanceof Element &&
        target.closest('[data-slot="resizable-handle"]') &&
        canvas.closest('[data-slot="resizable-panel-group"]')?.contains(target)
      ) {
        resizing = true;
        window.clearTimeout(timer);
      }
    };
    const endResize = () => {
      if (resizing) {
        resizing = false;
        schedule();
      }
    };
    const observer = new ResizeObserver(() => {
      schedule();
    });
    observer.observe(canvas);
    document.addEventListener('pointerdown', beginResize, true);
    document.addEventListener('pointerup', endResize);
    document.addEventListener('pointercancel', endResize);
    document.addEventListener('keydown', beginResize, true);
    document.addEventListener('keyup', endResize);
    return () => {
      observer.disconnect();
      window.clearTimeout(timer);
      document.removeEventListener('pointerdown', beginResize, true);
      document.removeEventListener('pointerup', endResize);
      document.removeEventListener('pointercancel', endResize);
      document.removeEventListener('keydown', beginResize, true);
      document.removeEventListener('keyup', endResize);
    };
  }, [canvasOnly]);
  const graph = useMemo(
    () => buildEncounterForestGraph(forest, chinese),
    [forest, chinese],
  );
  const [localId, setSelectedId] = useState('');
  const selectedId = controlledId ?? localId;
  const visible = useMemo(() => {
    const scope = traceNodeIds ? new Set(traceNodeIds) : null;
    const rows = graph.nodes.filter(
      (node) =>
        (!scope || scope.has(node.id)) &&
        (!collapsed || node.position.y <= 130),
    );
    const ids = new Set(rows.map((node) => node.id));
    return {
      nodes: rows.map((node) => ({
        ...node,
        selected: node.id === selectedId,
        position: horizontal
          ? { x: node.position.y * 2.5, y: node.position.x * 0.5 }
          : node.position,
        data: { ...node.data, horizontal },
      })),
      edges: graph.edges.filter(
        (edge) => ids.has(edge.source) && ids.has(edge.target),
      ),
    };
  }, [graph, traceNodeIds, collapsed, selectedId, horizontal]);
  const selected =
    forest.nodes.find((node) => node.id === selectedId) ??
    forest.nodes.find((node) => node.event_type === 'DIAGNOSIS') ??
    forest.nodes[0];
  if (!graph.nodes.length)
    return (
      <p>
        {chinese ? '此筛选下暂无轨迹。' : 'No trajectories for this selection.'}
      </p>
    );
  return (
    <div
      className={`enc-forest-visual ${canvasOnly ? 'ws-forest-visual' : ''}`}
    >
      {!canvasOnly && (
        <p className="enc-muted">
          {chinese
            ? '从首诊向下连接实际决策；边上的数字为经过次数。点击节点查看内容。'
            : 'Recorded decisions run top to bottom. Edge numbers are traversal counts. Select a node to inspect it.'}
        </p>
      )}
      <div
        ref={canvasRef}
        className="enc-forest-canvas"
        aria-label={chinese ? '病例决策森林图' : 'Case decision forest'}
      >
        <div
          style={
            canvasOnly && canvasSize
              ? canvasSize
              : { width: '100%', height: '100%' }
          }
        >
          <ReactFlow
            key={`${forest.record_type}-${graph.nodes[0]?.id}-${horizontal}-${collapsed}-${traceNodeIds?.join(',') ?? ''}`}
            nodes={visible.nodes}
            edges={visible.edges}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.18, maxZoom: 1.1 }}
            minZoom={0.15}
            maxZoom={2}
            nodesDraggable={false}
            nodesConnectable={false}
            onNodeClick={(_, node) => {
              setSelectedId(node.id);
              onSelect?.(node.id);
            }}
            onMoveEnd={(_, viewport) => onZoom?.(viewport.zoom)}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={16} size={1} color="var(--ws-dot, #0000000f)" />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
      </div>
      {!canvasOnly && selected && (
        <section className="enc-forest-node-detail" aria-live="polite">
          <h3>{forestNodeLabel(selected, chinese)}</h3>
          <p className="enc-muted">
            {selected.is_simulation
              ? chinese
                ? '模拟演示 · 非真实医生轨迹'
                : 'Simulation · not a real doctor trajectory'
              : ''}{' '}
            · {selected.count} {chinese ? '次经过' : 'visits'}
          </p>
          {selected.example?.reason_text && (
            <p>{selected.example.reason_text}</p>
          )}
          {selected.example?.hypothesis && <p>{selected.example.hypothesis}</p>}
          {selected.example?.diagnoses?.map((text) => (
            <p key={text}>{text}</p>
          ))}
          {selected.example?.records?.map((row, index) => (
            <ResultValue
              key={index}
              value={row.result}
              chinese={chinese}
              caseId={selected.case_id ?? ''}
            />
          ))}
          {selected.example?.text && <p>{selected.example.text}</p>}
          {!selected.example && selected.event_type === 'DIAGNOSIS' && (
            <p>{selected.label.replace(/^DIAGNOSIS: /, '')}</p>
          )}
        </section>
      )}
    </div>
  );
}

function ForestNodeView({ data, selected }: NodeProps<FlowNode>) {
  const Icon =
    data.kind === 'COMPLETE'
      ? CheckCheck
      : data.itemKind === 'operation'
        ? Stethoscope
        : data.kind === 'ACTION'
          ? MessageCircle
          : GitBranch;
  return (
    <div
      className={`enc-forest-flow-node ws-forest-node ${selected ? 'is-selected' : ''} kind-${data.kind.toLowerCase()}`}
    >
      <Handle
        type="target"
        position={data.horizontal ? Position.Left : Position.Top}
      />
      <header>
        <Icon size={15} />
        <strong title={data.label}>{data.label}</strong>
        <span>{data.count}</span>
      </header>
      <div className="ws-node-body">
        <span>{data.kind}</span>
        <small>{data.subtitle}</small>
      </div>
      <footer>
        <span>{data.status}</span>
        <i />
      </footer>
      <Handle
        type="source"
        position={data.horizontal ? Position.Right : Position.Bottom}
      />
    </div>
  );
}
