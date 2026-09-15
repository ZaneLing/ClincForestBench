'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Braces,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Database,
  GitBranch,
  LoaderCircle,
  LockKeyhole,
  Route,
} from 'lucide-react';
import { api } from '@/lib/api';
import type { TemporalCaseDetail } from '@/features/temporal/types';

type ExampleKind = 'CLASSIC' | 'TEMPORAL';

type ClassicTreeAudit = {
  manifest_entry: Record<string, unknown>;
  raw_case: Record<string, unknown>;
  processed_tree: {
    schema_version?: string;
    case_id?: string;
    classification?: unknown;
    semantics?: unknown;
    source?: Record<string, unknown>;
    audit?: Record<string, unknown>;
    tree?: {
      root_id?: string;
      nodes?: Array<Record<string, unknown>>;
      edges?: Array<Record<string, unknown>>;
    };
  };
};

type ExampleData =
  | { kind: 'CLASSIC'; bundle: Record<string, unknown>; audit: ClassicTreeAudit }
  | { kind: 'TEMPORAL'; detail: TemporalCaseDetail };

type WalkthroughStep = {
  title: string;
  description: string;
  input: string;
  output: string;
  artifactLabel: string;
  artifact: unknown;
};

const RESEARCH_HEADERS = { 'X-Research-Key': 'local-research-only' };

export function DatasetCaseWalkthrough({
  caseId,
  datasetName,
  enabled,
  kind,
}: {
  caseId: string;
  datasetName: string;
  enabled: boolean;
  kind: ExampleKind;
}) {
  const [data, setData] = useState<ExampleData | null>(null);
  const [error, setError] = useState('');
  const loading = enabled && !data && !error;

  useEffect(() => {
    if (!enabled || data) return;
    let active = true;
    const request = kind === 'CLASSIC'
      ? Promise.all([
        api<Record<string, unknown>>(`/research/cases/${caseId}`, { headers: RESEARCH_HEADERS }),
        api<ClassicTreeAudit>(`/research/cases/${caseId}/tree-audit`, { headers: RESEARCH_HEADERS }),
      ]).then(([bundle, audit]) => ({ kind: 'CLASSIC' as const, bundle, audit }))
      : api<TemporalCaseDetail>(`/research/temporal/cases/${caseId}`, {
        headers: RESEARCH_HEADERS,
      }).then((detail) => ({ kind: 'TEMPORAL' as const, detail }));

    void request
      .then((result) => {
        if (active) setData(result);
      })
      .catch((requestError: unknown) => {
        if (active) setError(requestError instanceof Error ? requestError.message : '真实 Case 读取失败');
      });
    return () => {
      active = false;
    };
  }, [caseId, data, enabled, kind]);

  const walkthrough = useMemo(() => data ? buildWalkthrough(data) : null, [data]);

  return (
    <section className="dataset-real-walkthrough">
      <header className="dataset-real-walkthrough-head">
        <div className="dataset-real-icon"><Route /></div>
        <div>
          <p>REAL CASE · END-TO-END CONVERSION AUDIT</p>
          <h3>真实病例 {caseId}：从源记录到可玩病例树</h3>
          <span>下面每一步都展示本项目实际落盘的输入与输出；不是示意 JSON。</span>
        </div>
        <div className="dataset-real-case-badge"><b>{datasetName}</b><code>{caseId}</code></div>
      </header>

      {loading && (
        <div className="dataset-real-state"><LoaderCircle className="animate-spin" />正在读取 raw、case 与 tree 审计文件…</div>
      )}
      {error && (
        <div className="dataset-real-state is-error"><AlertTriangle />{error}<small>请确认后端运行在 localhost:8000，并已生成该数据集的 MVP artifacts。</small></div>
      )}
      {walkthrough && (
        <>
          <div className="dataset-real-summary">
            <div><Database /><span><small>真实来源</small><b>{walkthrough.sourceLabel}</b></span></div>
            <div><Braces /><span><small>规范记录</small><b>{walkthrough.eventLabel}</b></span></div>
            <div><GitBranch /><span><small>最终结构</small><b>{walkthrough.graphLabel}</b></span></div>
            <div><CheckCircle2 /><span><small>转换状态</small><b>来源可追溯</b></span></div>
          </div>
          <div className="dataset-real-steps">
            {walkthrough.steps.map((step, index) => (
              <details className="dataset-real-step" key={step.title} open={index === 0}>
                <summary>
                  <span className="dataset-real-step-index">{String(index + 1).padStart(2, '0')}</span>
                  <span className="dataset-real-step-copy"><b>{step.title}</b><small>{step.description}</small></span>
                  <span className="dataset-real-io"><code>{step.input}</code><span>→</span><code>{step.output}</code></span>
                  <ChevronDown />
                </summary>
                <div className="dataset-real-artifact">
                  <div><span>ACTUAL ARTIFACT</span><b>{step.artifactLabel}</b></div>
                  <JsonArtifact value={step.artifact} />
                </div>
              </details>
            ))}
          </div>
          <footer className="dataset-real-boundary">
            <LockKeyhole />
            <div><b>泄漏隔离</b><span>reference / oracle 在转换审计中可见，但进入 Arena 后会一直隐藏到玩家锁定诊断。</span></div>
            <Clock3 />
            <div><b>动作边界</b><span>{kind === 'TEMPORAL' ? '模型只能提交库内 action_id；病例没有记录的库内动作返回 UNOBSERVED，不伪造检查结果。' : '模型只能提交当前 AVAILABLE 的库内 action_id；库外、重复或依赖未满足的条目会被拒绝。'}</span></div>
          </footer>
        </>
      )}
    </section>
  );
}

function buildWalkthrough(data: ExampleData) {
  if (data.kind === 'TEMPORAL') return buildTemporalWalkthrough(data.detail);
  return buildClassicWalkthrough(data.bundle, data.audit);
}

function buildClassicWalkthrough(bundle: Record<string, unknown>, audit: ClassicTreeAudit) {
  const rawCase = audit.raw_case;
  const treeDocument = audit.processed_tree;
  const nodes = treeDocument.tree?.nodes ?? [];
  const edges = treeDocument.tree?.edges ?? [];
  const provenance = asRecord(rawCase.provenance);
  const rawRow = rawCase.raw_row ?? rawCase;
  const source = asRecord(treeDocument.source);
  const actionSpace = Array.isArray(bundle.action_space)
    ? bundle.action_space
    : { semantics: treeDocument.semantics, normalized_truth: bundle.truth };
  const typeCounts = countValues(nodes, 'node_type');
  const sourceName = textValue(provenance.source_file) || textValue(provenance.projection) || 'source record';

  const steps: WalkthroughStep[] = [
    {
      title: '定位源数据中的唯一病例',
      description: '先用原始行号、Encounter ID 或官方 task ID 锁定病例边界，并保存来源哈希或生成模式。',
      input: 'source dataset',
      output: 'provenance',
      artifactLabel: 'raw_case.provenance',
      artifact: provenance,
    },
    {
      title: '无损提取原始记录',
      description: '把源行及其关联表原样保存；此层不翻译、不补齐、不推断临床事实。',
      input: 'source rows',
      output: 'raw_row',
      artifactLabel: 'raw_case.raw_row',
      artifact: rawRow,
    },
    {
      title: '解析为规范 Case',
      description: '将人口学、初始信息、动作空间、完整事实与受保护参考拆成稳定字段，供不同前端与 Arena 共用。',
      input: 'raw_row',
      output: 'canonical case',
      artifactLabel: 'case bundle',
      artifact: bundle,
    },
    {
      title: '记录逐字段 Lineage',
      description: '每个原字段明确指向它生成的 context、stage、action、observation 或 diagnosis 节点。',
      input: 'canonical fields',
      output: 'field lineage',
      artifactLabel: 'processed_tree.source.field_lineage',
      artifact: {
        raw_case_path: source.raw_case_path,
        raw_sha256: source.raw_sha256,
        field_lineage: source.field_lineage,
      },
    },
    {
      title: '生成同构树节点',
      description: `本病例实际生成 ${nodes.length} 个节点；节点类型分布为 ${formatCounts(typeCounts)}。`,
      input: 'case + lineage',
      output: 'typed nodes',
      artifactLabel: 'processed_tree.tree.nodes',
      artifact: nodes,
    },
    {
      title: '连接路径并运行完整性审计',
      description: `用 ${edges.length} 条有类型的边连接阶段、动作和结果，并验证一动作一结果、来源一致性与参考完整性。`,
      input: 'typed nodes',
      output: 'tree + checks',
      artifactLabel: 'processed_tree.tree.edges + audit',
      artifact: { root_id: treeDocument.tree?.root_id, edges, audit: treeDocument.audit },
    },
    {
      title: '裁剪成 Arena 可见状态',
      description: '开局只暴露初始状态；玩家每选一个合法条目才揭示对应结果，oracle/reference 留在保护层。',
      input: 'audited tree',
      output: 'playable state machine',
      artifactLabel: 'action semantics + protected reference',
      artifact: {
        action_space: actionSpace,
        initial_evidence: bundle.initial_evidence,
        initial_context: bundle.initial_context,
        protected_oracle: bundle.oracle,
        semantics: treeDocument.semantics,
      },
    },
  ];

  return {
    sourceLabel: sourceName,
    eventLabel: `${nodes.length} typed nodes`,
    graphLabel: `${nodes.length} nodes · ${edges.length} edges`,
    steps,
  };
}

function buildTemporalWalkthrough(detail: TemporalCaseDetail) {
  const caseData = detail.case;
  const nodes = caseData.temporal_graph.nodes;
  const edges = caseData.temporal_graph.edges;
  const eligibleCount = caseData.timeline_events.filter((event) => event.arena.arena_eligible).length;
  const typeCounts = countValues(nodes as unknown as Array<Record<string, unknown>>, 'node_type');
  const sourceName = textValue(caseData.source.dataset)
    || textValue(caseData.source.source_file)
    || detail.manifest_entry.dataset_name;

  const steps: WalkthroughStep[] = [
    {
      title: '提取真实 Episode 原始资料',
      description: '保留候选行、关联事件摘录、文章原文或源文件定位；文字报告和影像印象也停留在这一来源层。',
      input: 'restricted source',
      output: 'raw_source',
      artifactLabel: 'case.raw_source',
      artifact: caseData.raw_source,
    },
    {
      title: '确定病例边界与时间零点',
      description: '用住院、急诊到诊、ICU 入科或叙事起点定义 T0；精确时间和叙事代理时间明确区分。',
      input: 'candidate episode',
      output: 'anchor + initial state',
      artifactLabel: 'case.source + case.anchor + case.initial_state',
      artifact: { source: caseData.source, anchor: caseData.anchor, initial_state: caseData.initial_state },
    },
    {
      title: '执行字段映射与安全转换',
      description: '转换审计逐条声明输入、规则和输出，同时保留“禁止合成结果、隐藏参考答案”等安全不变量。',
      input: 'raw_source',
      output: 'conversion audit',
      artifactLabel: 'case.transformation',
      artifact: caseData.transformation,
    },
    {
      title: '规范化为时序临床事件',
      description: `本病例抽取 ${caseData.timeline_events.length} 个真实事件，其中 ${eligibleCount} 个可在 Arena 中主动获取；每个事件保留结果、模态、六类时间与 provenance。`,
      input: 'source extracts',
      output: 'timeline_events',
      artifactLabel: 'case.timeline_events',
      artifact: caseData.timeline_events,
    },
    {
      title: '拆开医嘱、执行与结果可见时间',
      description: '把 action 与 result reveal 分开保存在树中；Arena 点击动作后同步推进模拟时钟到 available_time，不发生现实等待。',
      input: 'timeline_events',
      output: 'realized trajectory',
      artifactLabel: 'case.realized_trajectory',
      artifact: caseData.realized_trajectory,
    },
    {
      title: '生成动态时间树 / DAG',
      description: `生成 ${nodes.length} 个节点和 ${edges.length} 条边；类型分布为 ${formatCounts(typeCounts)}。节点详情携带真实文字结果、影像印象和时间置信度。`,
      input: 'initial + events',
      output: 'temporal graph',
      artifactLabel: 'case.temporal_graph',
      artifact: caseData.temporal_graph,
    },
    {
      title: '形成可玩的状态机并隔离 Ground Truth',
      description: '只把 eligible 动作放入候选库；未记录的库内动作返回 UNOBSERVED。模型自主决定何时 final，最多 30 个动作。',
      input: 'audited graph',
      output: 'Arena contract',
      artifactLabel: 'arena_config + quality + protected reference',
      artifact: {
        arena_config: caseData.arena_config,
        hidden_evidence_pool: caseData.hidden_evidence_pool,
        case_quality: caseData.case_quality,
        temporal_quality: caseData.temporal_quality,
        protected_reference: caseData.reference,
      },
    },
  ];

  return {
    sourceLabel: sourceName,
    eventLabel: `${caseData.timeline_events.length} timed events`,
    graphLabel: `${nodes.length} nodes · ${edges.length} edges`,
    steps,
  };
}

function JsonArtifact({ value }: { value: unknown }) {
  let serialized = '';
  try {
    serialized = JSON.stringify(value, null, 2);
  } catch {
    serialized = '该 artifact 无法序列化。';
  }
  return <pre>{serialized}</pre>;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function textValue(value: unknown) {
  return typeof value === 'string' ? value : '';
}

function countValues(items: Array<Record<string, unknown>>, key: string) {
  return items.reduce<Record<string, number>>((counts, item) => {
    const value = textValue(item[key]) || 'UNKNOWN';
    counts[value] = (counts[value] ?? 0) + 1;
    return counts;
  }, {});
}

function formatCounts(counts: Record<string, number>) {
  return Object.entries(counts).map(([name, count]) => `${name} ${count}`).join(' / ');
}
