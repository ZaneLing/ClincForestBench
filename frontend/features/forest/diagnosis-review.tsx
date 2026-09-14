'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  useNodesState,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  Download,
  GitBranch,
  RotateCcw,
  Stethoscope,
  Target,
  UserRound,
  UsersRound,
} from 'lucide-react';
import { motion } from 'motion/react';
import { Button } from '@/components/ui/button';
import type { Graph, SessionReview } from '@/features/arena/types';
import { GroundTruthTree } from '@/features/forest/ground-truth-tree';

type MatchKind =
  | 'shared'
  | 'personal-only'
  | 'community-only'
  | 'prediction'
  | 'truth';

type ResultTreeNodeData = {
  tree: 'personal' | 'community';
  kind: 'state' | 'prediction' | 'truth' | 'community-diagnosis';
  match: MatchKind;
  title: string;
  label: string;
  step?: number;
  depth?: number;
  answer?: string;
  status?: string;
  diagnosis?: string;
  stateHash?: string;
  evidenceIds?: string[];
  support?: number;
  selectionRate?: number;
  top1Rate?: number;
  correct?: boolean;
};

type ResultFlowNode = Node<ResultTreeNodeData, 'resultTree'>;
type ResultFlow = { nodes: ResultFlowNode[]; edges: Edge[] };
const nodeTypes = { resultTree: ResultTreeNode };

export function DiagnosisReview({
  review,
  onNewCase,
  onDownloadArtifact,
  extraAction,
}: {
  review: SessionReview;
  onNewCase: () => void;
  onDownloadArtifact?: () => void;
  extraAction?: React.ReactNode;
}) {
  const result = review.comparison;
  const isModel = review.player_type === 'MODEL';
  const personalHashes = useMemo(
    () => new Set(review.trajectory.map((item) => item.state_hash)),
    [review.trajectory],
  );
  const communityHashes = useMemo(
    () => new Set(review.case_graph.nodes.map((item) => item.state_hash)),
    [review.case_graph.nodes],
  );
  const personalTree = useMemo(
    () => buildPersonalTree(review, communityHashes),
    [communityHashes, review],
  );
  const communityTree = useMemo(
    () => buildCommunityTree(review, personalHashes),
    [personalHashes, review],
  );
  return (
    <motion.section
      animate={{ opacity: 1, scale: 1 }}
      className="result-workspace"
      initial={{ opacity: 0, scale: 0.99 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
    >
      <header className="result-command-bar">
        <Link className="result-home-link" href="/">
          <ArrowLeft /> 返回主页
        </Link>
        <div
          className={`result-verdict-icon ${result.is_correct ? 'is-correct' : 'is-wrong'}`}
        >
          {result.is_correct ? <Check /> : <AlertTriangle />}
        </div>
        <div className="min-w-0 flex-1">
          <p>SESSION COMPLETE · THREE-TREE REVIEW</p>
          <h2>
            {result.is_correct
              ? `${review.terminology} 与 Ground Truth 一致`
              : `${review.terminology} 与 Ground Truth 不同`}
          </h2>
          {review.generation_mode === 'OFFLINE_TASK_REPLAY' && (
            <small>Offline FHIR task replay · no live resource response</small>
          )}
        </div>
        <div className="result-diagnosis-pair">
          <span>
            {isModel ? 'Model result' : 'Your result'}{' '}
            <b>{result.predicted_label}</b>
          </span>
          <i>vs</i>
          <span>
            Ground truth <b>{result.ground_truth_label}</b>
          </span>
        </div>
        <div className="result-command-actions">
          {extraAction}
          {onDownloadArtifact && (
            <Button onClick={onDownloadArtifact} variant="outline">
              <Download /> 下载本轮 JSON
            </Button>
          )}
          <Button onClick={onNewCase}>
            <RotateCcw /> New case
          </Button>
        </div>
      </header>

      <div className="result-tree-comparison">
        <ResultTreePanel
          eyebrow={isModel ? 'LEFT · MODEL PATH' : 'LEFT · MY PATH'}
          graph={personalTree}
          icon={<UserRound />}
          meta={`${review.trajectory.length} states · ${result.questions_asked} actions`}
          title={isModel ? '模型的判断' : '我的判断'}
        />
        <ResultGroundTruthPanel review={review} />
        <ResultTreePanel
          eyebrow={
            isModel ? 'RIGHT · MODEL CASE FOREST' : 'RIGHT · CASE FOREST'
          }
          graph={communityTree}
          icon={<UsersRound />}
          meta={
            isModel
              ? `${review.case_graph.participant_count} models · ${review.case_graph.completed_session_count} completed`
              : `${review.case_graph.physician_count} doctors · ${review.case_graph.completed_session_count} completed`
          }
          title={isModel ? '模型历史决策树' : '群体决策树'}
        />
      </div>
    </motion.section>
  );
}

function ResultGroundTruthPanel({ review }: { review: SessionReview }) {
  return (
    <section className="result-tree-panel result-ground-truth-panel">
      <header>
        <span>
          <Stethoscope />
        </span>
        <div>
          <p>MIDDLE · CASE REFERENCE</p>
          <h3>Ground Truth</h3>
        </div>
        <small>{review.comparison.ground_truth_label}</small>
      </header>
      <GroundTruthTree
        key={review.session_id}
        tree={review.ground_truth_tree}
      />
    </section>
  );
}

function ResultTreePanel({
  graph,
  eyebrow,
  title,
  meta,
  icon,
}: {
  graph: ResultFlow;
  eyebrow: string;
  title: string;
  meta: string;
  icon: React.ReactNode;
}) {
  const [selectedId, setSelectedId] = useState(graph.nodes[0]?.id ?? '');
  const [nodes, , onNodesChange] = useNodesState<ResultFlowNode>(graph.nodes);
  const selected = nodes.find((node) => node.id === selectedId)?.data;
  return (
    <section className="result-tree-panel">
      <header>
        <span>{icon}</span>
        <div>
          <p>{eyebrow}</p>
          <h3>{title}</h3>
        </div>
        <small>{meta}</small>
      </header>
      {selected && <ResultTreeDetail data={selected} />}
      <div className="result-tree-canvas">
        <ReactFlow
          colorMode="dark"
          edges={graph.edges}
          fitView
          fitViewOptions={{ padding: 0.2, minZoom: 0.12, maxZoom: 1.05 }}
          maxZoom={2.5}
          minZoom={0.08}
          nodes={nodes}
          nodesConnectable={false}
          nodesDraggable
          nodeTypes={nodeTypes}
          onNodeClick={(_, node) => setSelectedId(node.id)}
          onNodesChange={onNodesChange}
          panOnScroll
          proOptions={{ hideAttribution: true }}
        >
          <Background
            color="#164e63"
            gap={28}
            size={1}
            variant={BackgroundVariant.Dots}
          />
          <MiniMap
            maskColor="rgb(2 15 23 / 74%)"
            nodeColor={(node) => resultNodeColor(node as ResultFlowNode)}
            pannable
            zoomable
          />
          <Controls showInteractive={false} />
        </ReactFlow>
        <p className="result-tree-help">
          点击节点查看详情 · 滚轮缩放 · 拖动画布
        </p>
      </div>
    </section>
  );
}

function buildPersonalTree(
  review: SessionReview,
  communityHashes: Set<string>,
): ResultFlow {
  const nodes: ResultFlowNode[] = review.trajectory.map((item, index) => ({
    id: `personal-state-${item.step}`,
    type: 'resultTree',
    position: { x: 320 + (index % 2 === 0 ? -18 : 18), y: index * 105 },
    data: {
      tree: 'personal',
      kind: 'state',
      match: communityHashes.has(item.state_hash) ? 'shared' : 'personal-only',
      title: `状态 S${item.step} · ${item.status}`,
      label: item.question,
      step: item.step,
      answer: item.answer,
      status: item.status,
      diagnosis:
        item.belief?.diagnoses[0]?.condition_id ?? 'Belief not captured',
      stateHash: item.state_hash,
    },
  }));
  const leafY = review.trajectory.length * 105 + 24;
  nodes.push({
    id: 'personal-prediction',
    type: 'resultTree',
    position: { x: 320, y: leafY },
    data: {
      tree: 'personal',
      kind: 'prediction',
      match: 'prediction',
      title: '我的最终诊断',
      label: review.comparison.predicted_label,
      diagnosis: review.comparison.predicted_label,
      correct: review.comparison.is_correct,
    },
  });
  const edges: Edge[] = review.trajectory.slice(1).map((item, index) => ({
    id: `personal-edge-${item.step}`,
    source: `personal-state-${review.trajectory[index].step}`,
    target: `personal-state-${item.step}`,
    type: 'smoothstep',
    animated: true,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#22d3ee', width: 12 },
    style: { stroke: '#22d3ee', strokeWidth: 2.5 },
  }));
  const last = `personal-state-${review.trajectory.at(-1)?.step ?? 0}`;
  edges.push({
    id: 'personal-edge-prediction',
    source: last,
    target: 'personal-prediction',
    type: 'smoothstep',
    animated: true,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#a78bfa', width: 12 },
    style: { stroke: '#a78bfa', strokeWidth: 2.5 },
  });
  return { nodes, edges };
}

function buildCommunityTree(
  review: SessionReview,
  personalHashes: Set<string>,
): ResultFlow {
  const graph = review.case_graph;
  if (!graph.nodes.length) return { nodes: [], edges: [] };
  const minEvidence = Math.min(
    ...graph.nodes.map((node) => node.revealed_evidence_ids.length),
  );
  const personalOrder = new Map(
    review.trajectory.map((item, index) => [item.state_hash, index]),
  );
  const incoming = incomingEdges(graph);
  const layers = new Map<number, Graph['nodes']>();
  for (const node of graph.nodes) {
    const depth = node.revealed_evidence_ids.length - minEvidence;
    layers.set(depth, [...(layers.get(depth) ?? []), node]);
  }
  const nodes: ResultFlowNode[] = [];
  const maxDepth = Math.max(...layers.keys());
  for (const [depth, layer] of [...layers.entries()].sort(
    ([left], [right]) => left - right,
  )) {
    layer.sort((left, right) => {
      const leftOrder = personalOrder.get(left.state_hash);
      const rightOrder = personalOrder.get(right.state_hash);
      if (leftOrder !== undefined && rightOrder !== undefined)
        return leftOrder - rightOrder;
      if (leftOrder !== undefined) return -1;
      if (rightOrder !== undefined) return 1;
      return (
        right.support - left.support ||
        left.state_hash.localeCompare(right.state_hash)
      );
    });
    const width = Math.max(0, layer.length - 1) * 108;
    layer.forEach((node, index) => {
      const incomingEdge = incoming.get(node.state_hash)?.[0];
      const matchedStep = personalOrder.get(node.state_hash);
      nodes.push({
        id: node.state_hash,
        type: 'resultTree',
        position: { x: 360 - width / 2 + index * 108, y: depth * 105 },
        data: {
          tree: 'community',
          kind: 'state',
          match: personalHashes.has(node.state_hash)
            ? 'shared'
            : 'community-only',
          title:
            matchedStep !== undefined
              ? `对应我的状态 S${matchedStep}`
              : depth === 0
                ? '共同初始状态'
                : `群体状态 · Level ${depth}`,
          label: incomingEdge?.question ?? 'Initial patient state',
          step: matchedStep,
          depth,
          stateHash: node.state_hash,
          evidenceIds: node.revealed_evidence_ids,
          support: node.support,
        },
      });
    });
  }
  const edges: Edge[] = graph.edges.map((edge) => {
    const isShared =
      personalHashes.has(edge.source_hash) &&
      personalHashes.has(edge.target_hash);
    const color = isShared ? '#22d3ee' : '#64748b';
    return {
      id: `community-${edge.source_hash}-${edge.target_hash}-${edge.action_evidence_id}`,
      source: edge.source_hash,
      target: edge.target_hash,
      type: 'smoothstep',
      animated: isShared,
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 11 },
      style: {
        stroke: color,
        strokeWidth: Math.min(4, 1.2 + edge.support * 0.45),
      },
    };
  });
  const sources = new Set(graph.edges.map((edge) => edge.source_hash));
  const terminalNodes = graph.nodes.filter(
    (node) => !sources.has(node.state_hash),
  );
  const diagnoses = review.community_final_diagnoses.slice(0, 10);
  if (diagnoses.length) {
    const hubId = 'community-final-submissions';
    const hubY = (maxDepth + 1) * 105 + 8;
    nodes.push({
      id: hubId,
      type: 'resultTree',
      position: { x: 360, y: hubY },
      data: {
        tree: 'community',
        kind: 'state',
        match: 'community-only',
        title: '群体最终提交',
        label: `${graph.completed_session_count} 条完成路径汇总`,
        support: graph.completed_session_count,
      },
    });
    for (const node of terminalNodes) {
      edges.push({
        id: `community-final-${node.state_hash}`,
        source: node.state_hash,
        target: hubId,
        type: 'smoothstep',
        markerEnd: { type: MarkerType.ArrowClosed, color: '#64748b', width: 11 },
        style: { stroke: '#64748b', strokeWidth: 1.6 },
      });
    }
    const width = Math.max(0, diagnoses.length - 1) * 108;
    diagnoses.forEach((diagnosis, index) => {
      const diagnosisId = `community-diagnosis-${index}`;
      nodes.push({
        id: diagnosisId,
        type: 'resultTree',
        position: {
          x: 360 - width / 2 + index * 108,
          y: hubY + 120,
        },
        data: {
          tree: 'community',
          kind: 'community-diagnosis',
          match: 'community-only',
          title: `群体诊断 #${index + 1}`,
          label: diagnosis.label ?? diagnosis.condition,
          diagnosis: diagnosis.label ?? diagnosis.condition,
          support: diagnosis.selection_count,
          selectionRate: diagnosis.selection_rate,
          top1Rate: diagnosis.top1_rate,
        },
      });
      edges.push({
        id: `community-diagnosis-edge-${index}`,
        source: hubId,
        target: diagnosisId,
        type: 'smoothstep',
        markerEnd: { type: MarkerType.ArrowClosed, color: '#a78bfa', width: 11 },
        style: {
          stroke: '#a78bfa',
          strokeWidth: Math.max(1.4, 1.2 + diagnosis.selection_rate * 3),
        },
      });
    });
  }
  return { nodes, edges };
}

function incomingEdges(graph: Graph) {
  const result = new Map<string, Graph['edges']>();
  for (const edge of graph.edges) {
    result.set(edge.target_hash, [
      ...(result.get(edge.target_hash) ?? []),
      edge,
    ]);
  }
  for (const edges of result.values()) {
    edges.sort((left, right) => right.support - left.support);
  }
  return result;
}

function ResultTreeNode({ data, selected }: NodeProps<ResultFlowNode>) {
  return (
    <div
      className={`result-tree-node match-${data.match} kind-${data.kind} ${selected ? 'is-selected' : ''}`}
      title={`${data.title}\n${data.label}`}
    >
      <Handle position={Position.Top} type="target" />
      <span className="result-tree-node-symbol">
        {data.kind === 'truth' ? (
          <Stethoscope />
        ) : data.kind === 'prediction' ||
          data.kind === 'community-diagnosis' ? (
          <Target />
        ) : data.tree === 'community' ? (
          data.step !== undefined ? (
            `S${data.step}`
          ) : (
            <GitBranch />
          )
        ) : (
          `S${data.step}`
        )}
      </span>
      {data.support !== undefined && (
        <small className="result-tree-support">{data.support}×</small>
      )}
      <Handle position={Position.Bottom} type="source" />
      <span className="result-tree-tooltip">
        <small>{data.title}</small>
        <b>{data.label}</b>
      </span>
    </div>
  );
}

function ResultTreeDetail({ data }: { data: ResultTreeNodeData }) {
  return (
    <div className={`result-tree-detail match-${data.match}`}>
      <span className="result-tree-detail-mark">
        {data.kind === 'truth' ? (
          <Stethoscope />
        ) : data.kind === 'prediction' ||
          data.kind === 'community-diagnosis' ? (
          <Target />
        ) : data.tree === 'community' ? (
          data.step !== undefined ? (
            `S${data.step}`
          ) : (
            <GitBranch />
          )
        ) : (
          `S${data.step}`
        )}
      </span>
      <div>
        <small>{data.title}</small>
        <b>{data.label}</b>
      </div>
      <span className="result-tree-detail-facts">
        {data.answer && <em>患者回答：{data.answer}</em>}
        {data.diagnosis && data.kind === 'state' && (
          <em>节点诊断：{data.diagnosis}</em>
        )}
        {data.support !== undefined && <em>{data.support} 条路径经过</em>}
        {data.selectionRate !== undefined && (
          <em>入选率 {Math.round(data.selectionRate * 100)}%</em>
        )}
        {data.top1Rate !== undefined && (
          <em>首选率 {Math.round(data.top1Rate * 100)}%</em>
        )}
        {data.evidenceIds && <em>{data.evidenceIds.length} 项已知证据</em>}
        <em>{matchLabel(data.match)}</em>
      </span>
    </div>
  );
}

function matchLabel(match: MatchKind) {
  if (match === 'shared') return '两棵树共有节点';
  if (match === 'community-only') return '仅群体树出现';
  if (match === 'personal-only') return '仅个人路径出现';
  if (match === 'prediction') return '个人最终提交';
  return 'Ground truth';
}

function resultNodeColor(node: ResultFlowNode) {
  if (node.data.match === 'shared') return '#22d3ee';
  if (node.data.match === 'truth') return '#34d399';
  if (node.data.match === 'prediction') return '#a78bfa';
  if (node.data.match === 'personal-only') return '#f59e0b';
  return '#64748b';
}
