'use client';

import { useEffect, useMemo, useState } from 'react';
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
  useNodesState,
} from '@xyflow/react';
import {
  Activity,
  Braces,
  ChevronDown,
  CircleDot,
  GitBranch,
  MessageCircleQuestion,
  Stethoscope,
  UserRound,
} from 'lucide-react';
import type { CaseTreeNode, ProcessedCaseTree } from './case-tree-types';

type GroundTreeNodeData = {
  source: CaseTreeNode;
  tone: ReturnType<typeof nodeTone>;
};

type GroundTreeFlowNode = Node<GroundTreeNodeData, 'groundTree'>;
const nodeTypes = { groundTree: GroundTreeNode };

export function GroundTruthTree({
  tree,
  selectedNodeId,
  onSelectedNodeIdChange,
}: {
  tree: ProcessedCaseTree;
  selectedNodeId?: string;
  onSelectedNodeIdChange?: (nodeId: string) => void;
}) {
  const [internalSelectedId, setInternalSelectedId] = useState(
    tree.tree.root_id,
  );
  const selectedId = selectedNodeId ?? internalSelectedId;
  const graph = useMemo(() => buildOverviewTree(tree), [tree]);
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<GroundTreeFlowNode>(
    graph.nodes,
  );
  const selected =
    tree.tree.nodes.find((node) => node.node_id === selectedId) ??
    tree.tree.nodes[0];

  useEffect(() => {
    setFlowNodes(
      graph.nodes.map((node) => ({
        ...node,
        selected: node.id === selectedId,
      })),
    );
  }, [graph.nodes, selectedId, setFlowNodes]);

  function selectNode(nodeId: string) {
    setInternalSelectedId(nodeId);
    onSelectedNodeIdChange?.(nodeId);
  }

  return (
    <div className="ground-truth-tree-shell">
      <details className="tree-legend-disclosure">
        <summary>
          <span>节点颜色图例</span>
          <small>7 种节点</small>
          <ChevronDown />
        </summary>
        <div className="tree-legend" aria-label="Node color legend">
          <Legend tone="case" label="病例" />
          <Legend tone="stage" label="阶段" />
          <Legend tone="context" label="患者信息" />
          <Legend tone="action" label="问询" />
          <Legend tone="observation" label="结果" />
          <Legend tone="diagnosis" label="鉴别诊断" />
          <Legend tone="ground-truth" label="Ground truth" />
        </div>
      </details>

      <div className="compact-tree-canvas">
        <ReactFlow
          edges={graph.edges}
          fitView
          fitViewOptions={{ padding: 0.12, minZoom: 0.16, maxZoom: 1.1 }}
          maxZoom={2.5}
          minZoom={0.08}
          nodes={flowNodes}
          nodesConnectable={false}
          nodesDraggable={false}
          nodeTypes={nodeTypes}
          onNodeClick={(_, node) => selectNode(node.id)}
          onNodesChange={onNodesChange}
          panOnDrag
          panOnScroll={false}
          proOptions={{ hideAttribution: true }}
          zoomOnScroll
        >
          <Background
            color="#b9dce5"
            gap={22}
            size={1}
            variant={BackgroundVariant.Dots}
          />
          <Controls showInteractive={false} />
        </ReactFlow>
        <p className="compact-tree-help">
          点击节点查看详情 · 滚轮缩放 · 拖动画布
        </p>
      </div>

      <details className="tree-node-disclosure" key={selectedId} open>
        <summary>
          <span>节点内容</span>
          <b>{selected.label}</b>
          <ChevronDown />
        </summary>
        <div className="compact-tree-detail" aria-live="polite">
          <span className={`compact-tree-detail-icon node-${nodeTone(selected)}`}>
            {nodeIcon(selected)}
          </span>
          <div>
            <small>{nodeCaption(selected)}</small>
            <b>{selected.label}</b>
          </div>
          <code>{selected.node_id}</code>
          <NodeFacts node={selected} />
        </div>
      </details>
    </div>
  );
}

function buildOverviewTree(tree: ProcessedCaseTree): {
  nodes: GroundTreeFlowNode[];
  edges: Edge[];
} {
  const sourceNodes = new Map(
    tree.tree.nodes.map((node) => [node.node_id, node]),
  );
  const root = sourceNodes.get(tree.tree.root_id);
  if (!root) return { nodes: [], edges: [] };

  // Keep the source chronology visible: stages form one vertical spine, while
  // each stage's evidence fans out to the sides without occupying that spine.
  const stages = tree.tree.nodes
    .filter((node) => node.node_type === 'STAGE')
    .sort(sortNodes);
  const centers = new Map<string, { x: number; y: number }>();
  const spineX = 560;
  const branchGap = 116;
  const childDrop = 104;
  const resultDrop = 104;
  centers.set(root.node_id, { x: spineX, y: 0 });

  let stageY = 132;
  stages.forEach((stage, stageIndex) => {
    centers.set(stage.node_id, { x: spineX, y: stageY });
    const directChildren = tree.tree.edges
      .filter(
        (edge) =>
          edge.source === stage.node_id && edge.edge_type !== 'NEXT_STAGE',
      )
      .sort(
        (left, right) =>
          left.order - right.order || left.target.localeCompare(right.target),
      )
      .map((edge) => edge.target);
    const diagnosisIds = directChildren.filter(
      (nodeId) => sourceNodes.get(nodeId)?.node_type === 'DIAGNOSIS',
    );
    const branchIds = directChildren.filter(
      (nodeId) => sourceNodes.get(nodeId)?.node_type !== 'DIAGNOSIS',
    );
    const offsets = branchOffsets(branchIds.length, branchGap, stageIndex);

    const branchBottoms = branchIds.map((nodeId, index) =>
      positionSubtree(nodeId, spineX + offsets[index], stageY + childDrop),
    );

    const diagnosisOffsets = rowOffsets(diagnosisIds.length, branchGap);
    diagnosisIds.forEach((nodeId, index) => {
      centers.set(nodeId, {
        x: spineX + diagnosisOffsets[index],
        y: stageY + childDrop,
      });
    });

    const branchDepth = branchBottoms.length
      ? Math.max(...branchBottoms) - stageY
      : 0;
    stageY += Math.max(132, branchDepth + 126);
  });

  function positionSubtree(nodeId: string, x: number, y: number): number {
    centers.set(nodeId, { x, y });
    const children = tree.tree.edges
      .filter((edge) => edge.source === nodeId)
      .sort(
        (left, right) =>
          left.order - right.order || left.target.localeCompare(right.target),
      )
      .map((edge) => edge.target)
      .filter((targetId) => sourceNodes.get(targetId)?.node_type !== 'STAGE');
    if (!children.length) return y;
    const offsets =
      children.length === 1
        ? [0]
        : rowOffsets(children.length, branchGap * 0.8);
    return Math.max(
      ...children.map((childId, index) =>
        positionSubtree(childId, x + offsets[index], y + resultDrop),
      ),
    );
  }

  const nodes = tree.tree.nodes.flatMap<GroundTreeFlowNode>((node) => {
    const center = centers.get(node.node_id);
    if (!center) return [];
    return [
      {
        id: node.node_id,
        type: 'groundTree',
        position: { x: center.x - 29, y: center.y },
        data: { source: node, tone: nodeTone(node) },
      },
    ];
  });
  const edges = tree.tree.edges.flatMap<Edge>((edge) => {
    const sourceCenter = centers.get(edge.source);
    const targetCenter = centers.get(edge.target);
    const targetNode = sourceNodes.get(edge.target);
    if (!sourceCenter || !targetCenter || !targetNode) return [];
    const isSpine = edge.edge_type === 'NEXT_STAGE';
    const tone = isSpine ? '#2563eb' : toneColor(nodeTone(targetNode));
    const sourceHandle = isSpine
      ? 'bottom'
      : targetCenter.x < sourceCenter.x
        ? 'left'
        : targetCenter.x > sourceCenter.x
          ? 'right'
          : 'bottom';
    return [
      {
        id: `${edge.edge_type}::${edge.source}::${edge.target}`,
        source: edge.source,
        sourceHandle,
        target: edge.target,
        targetHandle: 'top',
        type: 'straight',
        markerEnd: { type: MarkerType.ArrowClosed, color: tone, width: 12 },
        style: { stroke: tone, strokeWidth: isSpine ? 2.4 : 1.6 },
      },
    ];
  });
  return { nodes, edges };
}

function branchOffsets(count: number, gap: number, stageIndex: number) {
  if (count === 0) return [];
  if (count === 1) return [(stageIndex % 2 === 0 ? -1 : 1) * gap];
  const leftCount = Math.ceil(count / 2);
  const rightCount = count - leftCount;
  return [
    ...Array.from(
      { length: leftCount },
      (_, index) => -((leftCount - index) * gap),
    ),
    ...Array.from({ length: rightCount }, (_, index) => (index + 1) * gap),
  ];
}

function rowOffsets(count: number, gap: number) {
  return Array.from(
    { length: count },
    (_, index) => (index - (count - 1) / 2) * gap,
  );
}

function GroundTreeNode({ data, selected }: NodeProps<GroundTreeFlowNode>) {
  const node = data.source;
  return (
    <div
      aria-label={`${nodeCaption(node)}: ${node.label}`}
      className={`ground-tree-circle node-${data.tone} ${selected ? 'is-selected' : ''}`}
      title={`${nodeCaption(node)}\n${node.label}`}
    >
      <Handle id="top" position={Position.Top} type="target" />
      {nodeIcon(node)}
      <Handle id="left" position={Position.Left} type="source" />
      <Handle id="right" position={Position.Right} type="source" />
      <Handle id="bottom" position={Position.Bottom} type="source" />
      <span className="ground-tree-tooltip">
        <small>{nodeCaption(node)}</small>
        <b>{node.label}</b>
        {typeof node.data.probability === 'number' && (
          <em>Probability {formatProbability(node.data.probability)}</em>
        )}
      </span>
    </div>
  );
}

function NodeFacts({ node }: { node: CaseTreeNode }) {
  const facts = Object.entries(node.data)
    .filter(([, value]) => value !== undefined && value !== null)
    .slice(0, 3);
  if (!facts.length) return null;
  return (
    <span className="compact-tree-facts">
      {facts.map(([label, value]) => (
        <em key={label}>
          {humanize(label)}: {formatValue(value)}
        </em>
      ))}
    </span>
  );
}

function sortNodes(
  left: CaseTreeNode | undefined,
  right: CaseTreeNode | undefined,
) {
  if (!left && !right) return 0;
  if (!left) return 1;
  if (!right) return -1;
  return left.order - right.order || left.node_id.localeCompare(right.node_id);
}

function nodeTone(node: CaseTreeNode) {
  if (node.node_type === 'CASE') return 'case' as const;
  if (node.node_type === 'STAGE') return 'stage' as const;
  if (node.node_type === 'CONTEXT') return 'context' as const;
  if (node.node_type === 'ACTION') return 'action' as const;
  if (node.node_type === 'OBSERVATION') return 'observation' as const;
  if (node.node_type === 'DIAGNOSIS' && node.data.is_ground_truth)
    return 'ground-truth' as const;
  return 'diagnosis' as const;
}

function nodeCaption(node: CaseTreeNode) {
  if (node.node_type === 'ACTION') return '问询动作';
  if (node.node_type === 'OBSERVATION') return '患者回答';
  if (node.node_type === 'DIAGNOSIS') {
    return node.data.is_ground_truth
      ? 'Ground truth diagnosis'
      : 'Differential diagnosis';
  }
  if (node.node_type === 'CONTEXT') return '患者基础信息';
  if (node.node_type === 'STAGE') return '诊断阶段';
  return '病例根节点';
}

function nodeIcon(node: CaseTreeNode) {
  if (node.node_type === 'CASE') return <GitBranch />;
  if (node.node_type === 'STAGE') return <CircleDot />;
  if (node.node_type === 'CONTEXT') return <UserRound />;
  if (node.node_type === 'ACTION') return <MessageCircleQuestion />;
  if (node.node_type === 'OBSERVATION') return <Activity />;
  if (node.node_type === 'DIAGNOSIS') return <Stethoscope />;
  return <Braces />;
}

function toneColor(tone: ReturnType<typeof nodeTone>) {
  if (tone === 'case') return '#0e7490';
  if (tone === 'stage') return '#2563eb';
  if (tone === 'context') return '#64748b';
  if (tone === 'action') return '#7c3aed';
  if (tone === 'observation') return '#059669';
  if (tone === 'ground-truth') return '#dc2626';
  return '#d97706';
}

function formatValue(value: unknown) {
  if (
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'boolean'
  ) {
    return String(value);
  }
  return JSON.stringify(value);
}

function formatProbability(value: number) {
  return `${(value * 100).toFixed(2)}% · ${value}`;
}

function humanize(value: string) {
  return value.replaceAll('_', ' ');
}

function Legend({ tone, label }: { tone: string; label: string }) {
  return (
    <span>
      <i className={`legend-dot node-${tone}`} /> {label}
    </span>
  );
}
