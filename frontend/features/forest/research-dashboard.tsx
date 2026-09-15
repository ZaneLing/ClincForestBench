'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Braces,
  ChevronDown,
  ChevronRight,
  Clipboard,
  Code2,
  Database,
  FileJson2,
  GitBranch,
  Rows3,
} from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { api } from '@/lib/api';
import type { CaseTreeAudit } from './case-tree-types';
import { GroundTruthTree } from './ground-truth-tree';

export function ResearchDashboard({ selectedCaseId }: { selectedCaseId: string }) {
  const [audit, setAudit] = useState<CaseTreeAudit | null>(null);
  const [highlightedNodeId, setHighlightedNodeId] = useState('');
  const [error, setError] = useState('');
  const [liveMessage, setLiveMessage] = useState('');

  useEffect(() => {
    const headers = { 'X-Research-Key': 'local-research-only' };
    let active = true;
    void api<CaseTreeAudit>(
      `/research/cases/${selectedCaseId}/tree-audit`,
      { headers },
    )
      .then((treeAudit) => {
        if (!active) return;
        setAudit(treeAudit);
        setError('');
        setHighlightedNodeId(treeAudit.processed_tree.tree.root_id);
      })
      .catch((error: Error) => {
        if (active) setError(error.message);
      });
    return () => {
      active = false;
    };
  }, [selectedCaseId]);

  return (
    <div className="case-audit-dashboard">
      {audit ? (
        <section className="case-audit-grid">
          <AuditPanel
            eyebrow="1 · Source"
            icon={<Database />}
            title="原始病例数据"
          >
            <div className="audit-file-meta">
              <span>Unparsed source row</span>
              <code>
                {audit.raw_case.provenance.source_task_id ??
                  audit.raw_case.provenance.source_encounter_id ??
                  (audit.raw_case.provenance.source_row_number_one_based
                    ? `row ${audit.raw_case.provenance.source_row_number_one_based}`
                    : audit.manifest_entry.dataset_name)}
              </code>
            </div>
            <JsonDocument
              evidenceLabels={evidenceLabelsFromTree(audit.processed_tree)}
              filename={`${audit.manifest_entry.case_id}.raw.json`}
              onNotice={setLiveMessage}
              value={audit.raw_case.raw_row}
            />
          </AuditPanel>

          <AuditPanel
            eyebrow="2 · Transform"
            icon={<Braces />}
            title={
              audit.manifest_entry.case_type === 'WORKFLOW_FOREST'
                ? '规范化 Workflow Tree'
                : '规范化 Case Tree'
            }
          >
            <JsonDocument
              defaultView="table"
              filename={`${audit.manifest_entry.case_id}.tree.json`}
              onNodeSelect={setHighlightedNodeId}
              onNotice={setLiveMessage}
              selectedNodeId={highlightedNodeId}
              value={audit.processed_tree}
            />
          </AuditPanel>

          <AuditPanel
            eyebrow="3 · Visual QA"
            icon={<GitBranch />}
            title={
              audit.manifest_entry.case_type === 'WORKFLOW_FOREST'
                ? 'Ground-truth 工作流树'
                : 'Ground-truth 诊断树'
            }
          >
            <GroundTruthTree
              key={selectedCaseId}
              onSelectedNodeIdChange={setHighlightedNodeId}
              selectedNodeId={highlightedNodeId}
              tree={audit.processed_tree}
            />
          </AuditPanel>
        </section>
      ) : (
        <section className="audit-empty">
          <FileJson2 />
          <b>{error || '正在读取病例'}</b>
        </section>
      )}
      <span aria-live="polite" className="sr-only">{liveMessage}</span>
    </div>
  );
}

function AuditPanel({
  eyebrow,
  title,
  icon,
  children,
}: {
  eyebrow: string;
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <article className="case-audit-panel">
      <header>
        <span className="audit-panel-icon">{icon}</span>
        <div>
          <p>{eyebrow}</p>
          <h2>{title}</h2>
        </div>
      </header>
      <div className="case-audit-panel-body">{children}</div>
    </article>
  );
}

export function JsonDocument({
  value,
  filename,
  onNotice,
  evidenceLabels = {},
  defaultView = 'json',
  onNodeSelect,
  selectedNodeId,
}: {
  value: unknown;
  filename: string;
  onNotice: (notice: string) => void;
  evidenceLabels?: Record<string, string>;
  defaultView?: 'json' | 'table';
  onNodeSelect?: (nodeId: string) => void;
  selectedNodeId?: string;
}) {
  const content = JSON.stringify(value, null, 2);
  const [collapsedPaths, setCollapsedPaths] = useState<Set<string>>(
    () => new Set(),
  );
  async function copy() {
    await navigator.clipboard.writeText(content);
    onNotice(`${filename} copied to clipboard.`);
  }
  const rows = useMemo(
    () => flattenJson(value, evidenceLabels),
    [evidenceLabels, value],
  );
  const visibleRows = useMemo(
    () =>
      rows.filter(
        (row) =>
          !row.ancestors.some((ancestor) => collapsedPaths.has(ancestor)),
      ),
    [collapsedPaths, rows],
  );

  function togglePath(path: string) {
    setCollapsedPaths((current) => {
      const next = new Set(current);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  return (
    <Tabs className="json-document" defaultValue={defaultView}>
      <div className="json-document-bar">
        <span>
          <FileJson2 /> {filename}
        </span>
        <div className="json-document-actions">
          <TabsList>
            <TabsTrigger value="json">
              <Code2 /> JSON
            </TabsTrigger>
            <TabsTrigger value="table">
              <Rows3 /> 结构化表格
            </TabsTrigger>
          </TabsList>
          <button onClick={() => void copy()} type="button">
            <Clipboard /> Copy
          </button>
        </div>
      </div>
      <TabsContent className="json-code-view" value="json">
        <pre>{content}</pre>
      </TabsContent>
      <TabsContent className="json-table-view" value="table">
        <table>
          <thead>
            <tr>
              <th>字段 / 序号</th>
              <th>内容</th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, index) => (
              <tr
                className={`${row.container ? 'is-container' : ''} ${row.linkedNodeId ? 'is-node-link' : ''} ${row.linkedNodeId === selectedNodeId ? 'is-node-selected' : ''}`}
                key={`${row.path}-${index}`}
              >
                <th aria-label={row.path} scope="row">
                  <span
                    className="json-tree-field"
                    style={{ paddingLeft: `${Math.min(row.depth, 10) * 13}px` }}
                    title={row.path}
                  >
                    {row.container ? (
                      <button
                        aria-expanded={!collapsedPaths.has(row.path)}
                        aria-label={`${collapsedPaths.has(row.path) ? '展开' : '收起'} ${row.key}`}
                        className="json-disclosure"
                        onClick={() => togglePath(row.path)}
                        type="button"
                      >
                        {collapsedPaths.has(row.path) ? (
                          <ChevronRight />
                        ) : (
                          <ChevronDown />
                        )}
                      </button>
                    ) : (
                      <i aria-hidden="true">·</i>
                    )}
                    {row.linkedNodeId && onNodeSelect ? (
                      <button
                        className="json-node-link"
                        onClick={() => onNodeSelect(row.linkedNodeId!)}
                        title={`在右侧树中定位 ${row.linkedNodeId}`}
                        type="button"
                      >
                        <code>{row.key}</code>
                      </button>
                    ) : (
                      <code>{row.key}</code>
                    )}
                  </span>
                </th>
                <td>
                  {row.diagnosis ? (
                    <span className="diagnosis-probability-row">
                      <b>{row.diagnosis}</b>
                      <span>
                        <small>Probability</small>
                        <code>{row.probability}</code>
                      </span>
                    </span>
                  ) : (
                    row.value
                  )}
                  {row.annotation && (
                    <small className="evidence-row-meaning">
                      {row.annotation}
                    </small>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TabsContent>
    </Tabs>
  );
}

type StructuredRow = {
  key: string;
  path: string;
  depth: number;
  value: string;
  container: boolean;
  diagnosis?: string;
  probability?: string;
  annotation?: string;
  ancestors: string[];
  linkedNodeId?: string;
};

function flattenJson(
  value: unknown,
  evidenceLabels: Record<string, string> = {},
): StructuredRow[] {
  const rows: StructuredRow[] = [];

  function visit(
    current: unknown,
    key: string,
    path: string,
    depth: number,
    isRoot = false,
    ancestors: string[] = [],
    inheritedNodeId?: string,
  ) {
    const embedded =
      typeof current === 'string' ? parseEmbeddedCollection(current) : null;
    const normalized = embedded?.value ?? current;

    if (Array.isArray(normalized)) {
      if (!isRoot) {
        rows.push({
          key,
          path,
          depth,
          value: normalized.length
            ? `${embedded ? '由字符串解析 · ' : ''}${normalized.length} 项`
            : '[]',
          container: true,
          ancestors,
          linkedNodeId: inheritedNodeId,
        });
      }
      const childDepth = isRoot ? depth : depth + 1;
      const childAncestors = isRoot ? ancestors : [...ancestors, path];
      if (
        key === 'DIFFERENTIAL_DIAGNOSIS' &&
        isDiagnosisProbabilityList(normalized)
      ) {
        normalized.forEach(([diagnosis, probability], index) => {
          rows.push({
            key: `[${index}]`,
            path: `${path}[${index}]`,
            depth: childDepth,
            value: `${diagnosis} · ${probability}`,
            diagnosis,
            probability: formatScalar(probability),
            container: false,
            ancestors: childAncestors,
            linkedNodeId: inheritedNodeId,
          });
        });
        return;
      }
      normalized.forEach((item, index) =>
        visit(
          item,
          `[${index}]`,
          `${path}[${index}]`,
          childDepth,
          false,
          childAncestors,
          inheritedNodeId,
        ),
      );
      return;
    }

    if (normalized !== null && typeof normalized === 'object') {
      const entries = Object.entries(normalized);
      const localNodeId =
        'node_id' in normalized && typeof normalized.node_id === 'string'
          ? normalized.node_id
          : inheritedNodeId;
      if (!isRoot) {
        rows.push({
          key,
          path,
          depth,
          value: entries.length
            ? `${embedded ? '由字符串解析 · ' : ''}${entries.length} 个字段`
            : '{}',
          container: true,
          ancestors,
          linkedNodeId: localNodeId,
        });
      }
      const childDepth = isRoot ? depth : depth + 1;
      const childAncestors = isRoot ? ancestors : [...ancestors, path];
      entries.forEach(([childKey, item]) =>
        visit(
          item,
          childKey,
          path === '$' ? childKey : `${path}.${childKey}`,
          childDepth,
          false,
          childAncestors,
          localNodeId,
        ),
      );
      return;
    }

    const evidenceId =
      typeof normalized === 'string'
        ? normalized.split('_@_', 1)[0]
        : undefined;
    rows.push({
      key,
      path,
      depth,
      value: formatScalar(normalized),
      container: false,
      annotation: evidenceId ? evidenceLabels[evidenceId] : undefined,
      ancestors,
      linkedNodeId: inheritedNodeId,
    });
  }

  visit(value, '$', '$', 0, true);
  return rows;
}

function isDiagnosisProbabilityList(
  value: unknown[],
): value is Array<[string, number]> {
  return value.every(
    (item) =>
      Array.isArray(item) &&
      item.length === 2 &&
      typeof item[0] === 'string' &&
      typeof item[1] === 'number',
  );
}

function evidenceLabelsFromTree(tree: CaseTreeAudit['processed_tree']) {
  return Object.fromEntries(
    tree.tree.nodes.flatMap((node) => {
      if (node.node_type !== 'ACTION') return [];
      const evidenceId = node.data.evidence_id;
      return typeof evidenceId === 'string'
        ? [[evidenceId, node.label] as const]
        : [];
    }),
  );
}

function parseEmbeddedCollection(source: string) {
  const input = source.trim();
  if (
    !(
      (input.startsWith('[') && input.endsWith(']')) ||
      (input.startsWith('{') && input.endsWith('}'))
    )
  ) {
    return null;
  }

  try {
    return { value: JSON.parse(input) as unknown };
  } catch {
    // DDXPlus serializes some columns as Python literals with single quotes.
  }

  try {
    let cursor = 0;
    const skipWhitespace = () => {
      while (/\s/.test(input[cursor] ?? '')) cursor += 1;
    };
    const parseQuoted = () => {
      const quote = input[cursor];
      cursor += 1;
      let result = '';
      while (cursor < input.length) {
        const character = input[cursor];
        cursor += 1;
        if (character === quote) return result;
        if (character === '\\') {
          const escaped = input[cursor];
          cursor += 1;
          const escapes: Record<string, string> = {
            n: '\n',
            r: '\r',
            t: '\t',
            '\\': '\\',
            "'": "'",
            '"': '"',
          };
          result += escapes[escaped] ?? escaped;
        } else {
          result += character;
        }
      }
      throw new Error('Unterminated string');
    };
    const parseValue = (): unknown => {
      skipWhitespace();
      const character = input[cursor];
      if (character === "'" || character === '"') return parseQuoted();
      if (character === '[') {
        cursor += 1;
        const values: unknown[] = [];
        skipWhitespace();
        if (input[cursor] === ']') {
          cursor += 1;
          return values;
        }
        while (cursor < input.length) {
          values.push(parseValue());
          skipWhitespace();
          if (input[cursor] === ']') {
            cursor += 1;
            return values;
          }
          if (input[cursor] !== ',') throw new Error('Expected comma');
          cursor += 1;
        }
        throw new Error('Unterminated array');
      }
      if (character === '{') {
        cursor += 1;
        const record: Record<string, unknown> = {};
        skipWhitespace();
        if (input[cursor] === '}') {
          cursor += 1;
          return record;
        }
        while (cursor < input.length) {
          const parsedKey = parseValue();
          skipWhitespace();
          if (input[cursor] !== ':') throw new Error('Expected colon');
          cursor += 1;
          record[String(parsedKey)] = parseValue();
          skipWhitespace();
          if (input[cursor] === '}') {
            cursor += 1;
            return record;
          }
          if (input[cursor] !== ',') throw new Error('Expected comma');
          cursor += 1;
        }
        throw new Error('Unterminated object');
      }
      const numberMatch = input
        .slice(cursor)
        .match(/^-?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?/i);
      if (numberMatch) {
        cursor += numberMatch[0].length;
        return Number(numberMatch[0]);
      }
      const tokenMatch = input.slice(cursor).match(/^[A-Za-z]+/);
      if (!tokenMatch) throw new Error('Unsupported token');
      cursor += tokenMatch[0].length;
      if (tokenMatch[0] === 'True' || tokenMatch[0] === 'true') return true;
      if (tokenMatch[0] === 'False' || tokenMatch[0] === 'false') return false;
      if (tokenMatch[0] === 'None' || tokenMatch[0] === 'null') return null;
      throw new Error('Unsupported literal');
    };
    const value = parseValue();
    skipWhitespace();
    if (cursor !== input.length) throw new Error('Trailing content');
    return { value };
  } catch {
    return null;
  }
}

function formatScalar(value: unknown) {
  if (value === null) return 'null';
  if (value === undefined) return 'undefined';
  if (typeof value === 'string') return value;
  return JSON.stringify(value);
}
