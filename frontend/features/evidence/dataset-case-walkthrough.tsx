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

type ExampleData = { bundle: Record<string, unknown>; audit: ClassicTreeAudit };

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
}: {
  caseId: string;
  datasetName: string;
  enabled: boolean;
}) {
  const [data, setData] = useState<ExampleData | null>(null);
  const [error, setError] = useState('');
  const loading = enabled && !data && !error;

  useEffect(() => {
    if (!enabled || data) return;
    let active = true;
    const request = Promise.all([
        api<Record<string, unknown>>(`/research/cases/${caseId}`, { headers: RESEARCH_HEADERS }),
        api<ClassicTreeAudit>(`/research/cases/${caseId}/tree-audit`, { headers: RESEARCH_HEADERS }),
      ]).then(([bundle, audit]) => ({ bundle, audit }));

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
  }, [caseId, data, enabled]);

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
            <div><b>动作边界</b><span>自主选择问询和检查；已记录结果立即返回。模型只能提交当前可用的动作 ID，不补造结果。</span></div>
          </footer>
        </>
      )}
    </section>
  );
}

function buildWalkthrough(data: ExampleData) {
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
