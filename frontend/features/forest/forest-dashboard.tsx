'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
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
import {
  Activity,
  Clock3,
  GitBranch,
  KeyRound,
  Network,
  Stethoscope,
  Trees,
  UsersRound,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { api } from '@/lib/api';

type DiagnosisStatistic = {
  condition: string;
  label?: string;
  is_ground_truth: boolean;
  selection_count: number;
  selection_rate: number;
  top1_rate: number;
  mean_rank_when_selected: number;
  mean_rank_weight: number;
};

type ForestCaseSummary = {
  case_id: string;
  pathology: string;
  pathology_label: string;
  dataset_name: string;
  case_type: string;
  disease_category: string;
  physician_count: number;
  physician_session_count: number;
  completed_session_count: number;
};

type ForestNode = {
  state_hash: string;
  support: number;
  revealed_evidence_ids: string[];
  step: number;
  visit_rate: number;
  belief_submission_count: number;
  diagnoses: DiagnosisStatistic[];
};

type ForestDetail = {
  case_id: string;
  dataset_name: string;
  case_type: string;
  summary: {
    physician_count: number;
    physician_session_count: number;
    completed_session_count: number;
    state_node_count: number;
  };
  reference: {
    pathology: string;
    pathology_label: string;
    differential: Array<{
      condition: string;
      label?: string;
      probability: number;
    }>;
  };
  stages: Array<{
    step: number;
    submission_count: number;
    diagnoses: DiagnosisStatistic[];
  }>;
  final_diagnoses: DiagnosisStatistic[];
  nodes: ForestNode[];
  edges: Array<{
    source_hash: string;
    target_hash: string;
    action_evidence_id: string;
    support: number;
    probability: number;
    question: string;
  }>;
};

type ForestFlowNode = Node<ForestNode, 'forestState'>;
const nodeTypes = { forestState: ForestStateNode };

export function ForestDashboard() {
  const [researchKey, setResearchKey] = useState('local-research-only');
  const [cases, setCases] = useState<ForestCaseSummary[]>([]);
  const [dataset, setDataset] = useState('ALL');
  const [caseId, setCaseId] = useState('');
  const [detail, setDetail] = useState<ForestDetail | null>(null);
  const [selectedHash, setSelectedHash] = useState('');
  const [stage, setStage] = useState(0);
  const [notice, setNotice] = useState('正在汇总医生决策森林…');
  const [busy, setBusy] = useState(false);

  async function loadCase(nextCaseId: string, key = researchKey) {
    if (!nextCaseId) return;
    setBusy(true);
    setCaseId(nextCaseId);
    try {
      const value = await api<ForestDetail>(
        `/research/forest/cases/${nextCaseId}`,
        { headers: { 'X-Research-Key': key } },
      );
      setDetail(value);
      setSelectedHash(value.nodes[0]?.state_hash ?? '');
      setStage(value.stages[0]?.step ?? 0);
      setNotice('');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '森林统计加载失败');
    } finally {
      setBusy(false);
    }
  }

  async function unlock(key = researchKey) {
    setBusy(true);
    try {
      const index = await api<{ cases: ForestCaseSummary[] }>(
        '/research/forest/cases',
        { headers: { 'X-Research-Key': key } },
      );
      setCases(index.cases);
      const first = index.cases[0];
      if (first) await loadCase(first.case_id, key);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '森林权限验证失败');
      setBusy(false);
    }
  }

  useEffect(() => {
    const headers = { 'X-Research-Key': 'local-research-only' };
    let active = true;
    void api<{ cases: ForestCaseSummary[] }>('/research/forest/cases', {
      headers,
    })
      .then(async (index) => {
        if (!active) return;
        setCases(index.cases);
        const first = index.cases[0];
        if (!first) return;
        const value = await api<ForestDetail>(
          `/research/forest/cases/${first.case_id}`,
          { headers },
        );
        if (!active) return;
        setCaseId(first.case_id);
        setDetail(value);
        setSelectedHash(value.nodes[0]?.state_hash ?? '');
        setStage(value.stages[0]?.step ?? 0);
        setNotice('');
      })
      .catch((error: Error) => {
        if (active) setNotice(error.message);
      });
    return () => {
      active = false;
    };
  }, []);

  const graph = useMemo(() => buildForestGraph(detail), [detail]);
  const datasets = useMemo(
    () => ['ALL', ...Array.from(new Set(cases.map((item) => item.dataset_name)))],
    [cases],
  );
  const visibleCases = useMemo(
    () =>
      cases.filter(
        (item) => dataset === 'ALL' || item.dataset_name === dataset,
      ),
    [cases, dataset],
  );
  const selectedNode = detail?.nodes.find(
    (node) => node.state_hash === selectedHash,
  );
  const selectedStage = detail?.stages.find((item) => item.step === stage);
  const outcomeNoun = detail?.case_type === 'WORKFLOW_FOREST' ? '工作流结果' : '诊断';

  function changeDataset(nextDataset: string) {
    setDataset(nextDataset);
    const first = cases.find(
      (item) => nextDataset === 'ALL' || item.dataset_name === nextDataset,
    );
    if (first) void loadCase(first.case_id);
  }

  return (
    <main className="forest-page">
      <header className="forest-header">
        <div>
          <span className="brand-mark">
            <Trees />
          </span>
          <div>
            <p>ClincForestBench · Population analytics</p>
            <h1>病例决策森林</h1>
          </div>
        </div>
        <Badge>
          <Network /> Ground truth 与医生选择分离统计
        </Badge>
        <Link className="audit-nav-link" href="/forest?mode=temporal">
          Temporal Forest <Clock3 />
        </Link>
      </header>

      <section className="forest-toolbar">
        <label htmlFor="forest-dataset-picker">
          <span>Dataset</span>
          <select
            disabled={busy || !cases.length}
            id="forest-dataset-picker"
            onChange={(event) => changeDataset(event.target.value)}
            value={dataset}
          >
            {datasets.map((name) => (
              <option key={name} value={name}>
                {name === 'ALL'
                  ? `全部数据集 · ${cases.length} cases`
                  : `${name} · ${cases.filter((item) => item.dataset_name === name).length} cases`}
              </option>
            ))}
          </select>
        </label>
        <label htmlFor="forest-case-picker">
          <span>Case</span>
          <select
            disabled={busy || !cases.length}
            id="forest-case-picker"
            onChange={(event) => void loadCase(event.target.value)}
            value={caseId}
          >
            {visibleCases.map((item) => (
              <option key={item.case_id} value={item.case_id}>
                {item.dataset_name} · {item.case_id} · {item.pathology_label}
              </option>
            ))}
          </select>
        </label>
        <label htmlFor="forest-research-key">
          <span>
            <KeyRound /> Research key
          </span>
          <Input
            id="forest-research-key"
            onChange={(event) => setResearchKey(event.target.value)}
            type="password"
            value={researchKey}
          />
        </label>
        <Button disabled={busy} onClick={() => void unlock()}>
          {busy ? '汇总中…' : '加载森林'}
        </Button>
        {detail && <ForestSummary detail={detail} />}
      </section>

      {detail ? (
        <section className="forest-workspace">
          <article className="forest-map-panel">
            <header>
              <div>
                <p>CASE FOREST</p>
                <h2>{detail.case_id}</h2>
              </div>
              <small>节点百分比 = 经过该状态的医生游玩次数占比</small>
            </header>
            <div className="forest-canvas">
              <ReactFlow
                edges={graph.edges}
                fitView
                fitViewOptions={{ padding: 0.2, maxZoom: 1.05 }}
                maxZoom={2.5}
                minZoom={0.08}
                nodes={graph.nodes}
                nodesConnectable={false}
                nodesDraggable={false}
                nodeTypes={nodeTypes}
                onNodeClick={(_, node) => setSelectedHash(node.id)}
                panOnDrag
                panOnScroll={false}
                proOptions={{ hideAttribution: true }}
                zoomOnScroll
              >
                <Background
                  color="#164e63"
                  gap={28}
                  size={1}
                  variant={BackgroundVariant.Dots}
                />
                <Controls showInteractive={false} />
              </ReactFlow>
            </div>
          </article>

          <article className="forest-distribution-panel">
            <header>
              <Activity />
              <div>
                <p>SELECTED NODE</p>
                <h2>
                  {selectedNode
                    ? `S${selectedNode.step} 节点选择集中`
                    : '选择一个节点'}
                </h2>
              </div>
            </header>
            {selectedNode ? (
              <>
                <div className="forest-node-meta">
                  <span>
                    <b>{percent(selectedNode.visit_rate)}</b>医生游玩访问率
                  </span>
                  <span>
                    <b>{selectedNode.belief_submission_count}</b>该节点阶段判断
                  </span>
                  <span>
                    <b>{selectedNode.support}</b>路径支持数
                  </span>
                </div>
                <DiagnosisDistribution
                  diagnoses={selectedNode.diagnoses}
                  empty="该节点还没有医生诊断提交"
                />
              </>
            ) : null}
          </article>

          <article className="forest-stage-panel">
            <Tabs className="forest-tabs" defaultValue="stages">
              <TabsList>
                <TabsTrigger value="stages">
                  <GitBranch />
                  逐轮统计
                </TabsTrigger>
                <TabsTrigger value="final">
                  <Stethoscope />
                  最终{outcomeNoun}
                </TabsTrigger>
              </TabsList>
              <TabsContent value="stages">
                <div className="forest-stage-picker">
                  {detail.stages.map((item) => (
                    <button
                      className={item.step === stage ? 'is-active' : undefined}
                      key={item.step}
                      onClick={() => setStage(item.step)}
                      type="button"
                    >
                      S{item.step}
                      <small>{item.submission_count}</small>
                    </button>
                  ))}
                </div>
                <DiagnosisDistribution
                  diagnoses={selectedStage?.diagnoses ?? []}
                  empty="该轮次还没有提交"
                />
              </TabsContent>
              <TabsContent value="final">
                <div className="forest-reference">
                  <span>Ground truth</span>
                  <b>{detail.reference.pathology_label}</b>
                </div>
                <details className="forest-oracle-reference">
                  <summary>Ground-truth 参考概率分布</summary>
                  <div>
                    {detail.reference.differential.map((item) => (
                      <span key={item.condition}>
                        <b>{item.label ?? item.condition}</b>
                        <i>{percent(item.probability)}</i>
                      </span>
                    ))}
                  </div>
                </details>
                <DiagnosisDistribution
                  diagnoses={detail.final_diagnoses}
                  empty={`还没有医生完成这个病例的${outcomeNoun}提交`}
                />
              </TabsContent>
            </Tabs>
          </article>
        </section>
      ) : (
        <section className="forest-empty">
          <Trees />
          <b>{notice}</b>
        </section>
      )}
      {notice && detail && <p className="case-audit-notice">{notice}</p>}
    </main>
  );
}

function ForestSummary({ detail }: { detail: ForestDetail }) {
  return (
    <div className="forest-summary">
      <span>
        <UsersRound />
        <b>{detail.summary.physician_count}</b>医生
      </span>
      <span>
        <Activity />
        <b>{detail.summary.physician_session_count}</b>次游玩
      </span>
      <span>
        <GitBranch />
        <b>{detail.summary.state_node_count}</b>状态节点
      </span>
    </div>
  );
}

function DiagnosisDistribution({
  diagnoses,
  empty,
}: {
  diagnoses: DiagnosisStatistic[];
  empty: string;
}) {
  if (!diagnoses.length)
    return <div className="distribution-empty">{empty}</div>;
  return (
    <div className="diagnosis-distribution">
      {diagnoses.map((item) => (
        <article
          className={item.is_ground_truth ? 'is-truth' : undefined}
          key={item.condition}
        >
          <header>
            <b>{item.label ?? item.condition}</b>
            {item.is_ground_truth && <span>Ground truth</span>}
          </header>
          <div className="distribution-track">
            <i
              style={{ width: `${Math.max(item.selection_rate * 100, 1)}%` }}
            />
          </div>
          <dl>
            <div>
              <dt>选择率</dt>
              <dd>{percent(item.selection_rate)}</dd>
            </div>
            <div>
              <dt>Top 1</dt>
              <dd>{percent(item.top1_rate)}</dd>
            </div>
            <div>
              <dt>排序权重</dt>
              <dd>{percent(item.mean_rank_weight)}</dd>
            </div>
            <div>
              <dt>被选时平均名次</dt>
              <dd>{item.mean_rank_when_selected.toFixed(2)}</dd>
            </div>
          </dl>
        </article>
      ))}
    </div>
  );
}

function buildForestGraph(detail: ForestDetail | null): {
  nodes: ForestFlowNode[];
  edges: Edge[];
} {
  if (!detail?.nodes.length) return { nodes: [], edges: [] };
  const layers = new Map<number, ForestNode[]>();
  detail.nodes.forEach((node) =>
    layers.set(node.step, [...(layers.get(node.step) ?? []), node]),
  );
  const nodes: ForestFlowNode[] = [];
  for (const [depth, layer] of [...layers.entries()].sort(
    ([a], [b]) => a - b,
  )) {
    layer.sort(
      (a, b) =>
        b.support - a.support || a.state_hash.localeCompare(b.state_hash),
    );
    const gap = 126;
    const width = (layer.length - 1) * gap;
    layer.forEach((node, index) =>
      nodes.push({
        id: node.state_hash,
        type: 'forestState',
        position: { x: 420 - width / 2 + index * gap, y: depth * 120 },
        data: node,
      }),
    );
  }
  const edges: Edge[] = detail.edges.map((edge) => ({
    id: `${edge.source_hash}-${edge.target_hash}-${edge.action_evidence_id}`,
    source: edge.source_hash,
    target: edge.target_hash,
    type: 'smoothstep',
    animated: edge.probability >= 0.5,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#22d3ee', width: 11 },
    style: {
      stroke: '#22d3ee',
      strokeWidth: Math.min(4, 1 + edge.support * 0.4),
    },
    label: percent(edge.probability),
    labelStyle: { fill: '#67e8f9', fontSize: 10 },
    labelBgStyle: { fill: '#062331', fillOpacity: 0.9 },
  }));
  return { nodes, edges };
}

function ForestStateNode({ data, selected }: NodeProps<ForestFlowNode>) {
  return (
    <div
      className={`forest-state-node ${selected ? 'is-selected' : ''}`}
      title={`S${data.step} · ${data.support} paths`}
    >
      <Handle position={Position.Top} type="target" />
      <b>S{data.step}</b>
      <span>{percent(data.visit_rate)}</span>
      <small>{data.support}×</small>
      <Handle position={Position.Bottom} type="source" />
    </div>
  );
}

function percent(value: number) {
  return `${Math.round(value * 100)}%`;
}
