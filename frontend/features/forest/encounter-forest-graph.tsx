'use client';

import { useMemo, useState } from 'react';
import { ReactFlow, Handle, Position, Controls, Background, MarkerType, type Node, type NodeProps, type Edge } from '@xyflow/react';
import { ResultValue } from '@/features/arena/encounter-presentation';

type Label = { en: string; 'zh-CN': string };
export type EncounterForestNode = {
  id: string;
  label: string;
  count: number;
  event_type?: string;
  case_id?: string;
  is_simulation?: boolean;
  item?: { label: Label };
  reason_id?: string;
  result_status?: string;
  example?: {
    records?: { result: unknown }[];
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
};

type FlowData = { label: string; subtitle: string; kind: string; simulation: boolean; count: number };
type FlowNode = Node<FlowData, 'encounterForest'>;
const nodeTypes = { encounterForest: ForestNodeView };
const reasons: Record<string, [string, string]> = {
  support: ['Support diagnosis', '支持诊断'],
  differentiate: ['Differentiate', '鉴别诊断'],
  urgent: ['Assess urgency', '评估紧急情况'],
  severity: ['Assess severity', '评估严重程度'],
  other: ['Other', '其他'],
};

export function forestNodeLabel(node: EncounterForestNode, chinese: boolean) {
  if (node.item) return node.item.label[chinese ? 'zh-CN' : 'en'];
  if (node.event_type === 'DIAGNOSIS') return chinese ? '记录诊断' : 'Recorded diagnosis';
  if (node.event_type === 'COMPLETE') return chinese ? '完成就诊' : 'Visit completed';
  if (node.event_type === 'PRESCRIPTION') return chinese ? '处方 / 治疗' : 'Prescription / treatment';
  return node.label;
}

export function buildEncounterForestGraph(forest: EncounterForestData, chinese: boolean) {
  const incoming = new Set(forest.edges.map(edge => edge.target));
  const rows = new Map(forest.nodes.map(node => [node.id, node]));
  const children = new Map<string, string[]>();
  for (const edge of forest.edges) {
    children.set(edge.source, [...(children.get(edge.source) ?? []), edge.target]);
  }
  const placed = new Map<string, { x: number; y: number; depth: number }>();
  let leaf = 0;
  function place(id: string, depth: number, path: Set<string>): number {
    if (path.has(id) || !rows.has(id)) return leaf * 310;
    const nextPath = new Set(path).add(id);
    const descendants = (children.get(id) ?? []).filter(child => !nextPath.has(child));
    const xs = descendants.map(child => place(child, depth + 1, nextPath));
    const x = xs.length ? xs.reduce((sum, value) => sum + value, 0) / xs.length : leaf++ * 310;
    placed.set(id, { x, y: depth * 130, depth });
    return x;
  }
  forest.nodes.filter(node => !incoming.has(node.id)).forEach(node => place(node.id, 0, new Set()));
  const nodes: FlowNode[] = forest.nodes.filter(node => placed.has(node.id)).map(node => {
    const point = placed.get(node.id)!;
    const reason = node.reason_id ? reasons[node.reason_id]?.[chinese ? 1 : 0] ?? node.reason_id : '';
    return { id: node.id, type: 'encounterForest', position: { x: point.x, y: point.y }, data: {
      label: forestNodeLabel(node, chinese), count: node.count,
      subtitle: `S${point.depth}${reason ? ' · ' + reason : ''}`,
      kind: node.event_type ?? 'INITIAL', simulation: forest.record_type === 'SIMULATION',
    }};
  });
  const edges: Edge[] = forest.edges.map((edge, index) => ({
    id: `edge-${index}`, source: edge.source, target: edge.target, type: 'straight',
    markerEnd: { type: MarkerType.ArrowClosed }, label: String(edge.count),
    style: { strokeWidth: 2 },
  }));
  return { nodes, edges };
}

export function EncounterForestGraph({ forest, chinese }: { forest: EncounterForestData; chinese: boolean }) {
  const graph = useMemo(() => buildEncounterForestGraph(forest, chinese), [forest, chinese]);
  const [selectedId, setSelectedId] = useState('');
  const selected = forest.nodes.find(node => node.id === selectedId) ?? forest.nodes.find(node => node.event_type === 'DIAGNOSIS') ?? forest.nodes[0];
  if (!graph.nodes.length) return <p>{chinese ? '此筛选下暂无轨迹。' : 'No trajectories for this selection.'}</p>;
  return <div className="enc-forest-visual">
    <p className="enc-muted">{chinese ? '从首诊向下连接实际决策；边上的数字为经过次数。点击节点查看内容。' : 'Recorded decisions run top to bottom. Edge numbers are traversal counts. Select a node to inspect it.'}</p>
    <div className="enc-forest-canvas" aria-label={chinese ? '病例决策森林图' : 'Case decision forest'}>
      <ReactFlow key={`${forest.record_type}-${graph.nodes[0]?.id}`} nodes={graph.nodes} edges={graph.edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.1, maxZoom: 1.1 }} minZoom={0.15} maxZoom={2} nodesDraggable={false} nodesConnectable={false} onNodeClick={(_, node) => setSelectedId(node.id)} proOptions={{ hideAttribution: true }}>
        <Background gap={24} /><Controls showInteractive={false} />
      </ReactFlow>
    </div>
    {selected && <section className="enc-forest-node-detail" aria-live="polite">
      <h3>{forestNodeLabel(selected, chinese)}</h3>
      <p className="enc-muted">{selected.is_simulation ? chinese ? '模拟演示 · 非真实医生轨迹' : 'Simulation · not a real doctor trajectory' : ''} · {selected.count} {chinese ? '次经过' : 'visits'}</p>
      {selected.example?.reason_text && <p>{selected.example.reason_text}</p>}
      {selected.example?.hypothesis && <p>{selected.example.hypothesis}</p>}
      {selected.example?.diagnoses?.map(text => <p key={text}>{text}</p>)}
      {selected.example?.records?.map((row, index) => <ResultValue key={index} value={row.result} chinese={chinese} caseId={selected.case_id ?? ''} />)}
      {selected.example?.text && <p>{selected.example.text}</p>}
      {!selected.example && selected.event_type === 'DIAGNOSIS' && <p>{selected.label.replace(/^DIAGNOSIS: /, '')}</p>}
    </section>}
  </div>;
}

function ForestNodeView({ data, selected }: NodeProps<FlowNode>) {
  return <div className={`enc-forest-flow-node ${selected ? 'is-selected' : ''} kind-${data.kind.toLowerCase()}`}>
    <Handle type="target" position={Position.Top} />
    <small>{data.subtitle} · {data.count}</small><strong title={data.label}>{data.label}</strong>
    <Handle type="source" position={Position.Bottom} />
  </div>;
}
