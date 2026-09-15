'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  Activity,
  Check,
  ChevronRight,
  CircleX,
  Clock3,
  FileClock,
  GitBranch,
  History,
  Stethoscope,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { AuthGate } from '@/features/auth/auth-gate';
import { useAuth } from '@/features/auth/auth-context';
import type {
  BeliefSnapshotPayload,
  SessionArtifact,
} from '@/features/arena/types';
import type { ProcessedCaseTree } from '@/features/forest/case-tree-types';
import { GroundTruthTree } from '@/features/forest/ground-truth-tree';
import { JsonDocument } from '@/features/forest/research-dashboard';
import { api } from '@/lib/api';

type HistoryEntry = {
  session_id: string;
  case_id: string;
  dataset_name: string;
  case_type: string;
  terminology: string;
  started_at: string;
  completed_at: string;
  questions_asked: number;
  predicted_diagnosis: string;
  ground_truth_diagnosis: string;
  predicted_label: string;
  ground_truth_label: string;
  is_correct: boolean;
};

type HistoryDetail = {
  session_id: string;
  case_id: string;
  ground_truth_tree: ProcessedCaseTree;
  decision_json: SessionArtifact;
  belief_rounds: BeliefSnapshotPayload[];
};

export function DecisionHistory() {
  const { account, loading: authLoading } = useAuth();
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [dataset, setDataset] = useState('ALL');
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState<HistoryDetail | null>(null);
  const [notice, setNotice] = useState('正在读取个人决策历史…');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!account) return;
    let active = true;
    void api<{ sessions: HistoryEntry[] }>('/me/history')
      .then(async (value) => {
        if (!active) return;
        setEntries(value.sessions);
        const first = value.sessions[0];
        if (!first) {
          setNotice('还没有已完成的病例。');
          return;
        }
        setSelectedId(first.session_id);
        const nextDetail = await api<HistoryDetail>(
          `/me/history/${first.session_id}`,
        );
        if (!active) return;
        setDetail(nextDetail);
        setNotice('');
      })
      .catch((error: Error) => {
        if (active) setNotice(error.message);
      });
    return () => {
      active = false;
    };
  }, [account]);

  async function selectSession(sessionId: string) {
    setSelectedId(sessionId);
    setBusy(true);
    try {
      setDetail(await api<HistoryDetail>(`/me/history/${sessionId}`));
      setNotice('');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '历史病例加载失败');
    } finally {
      setBusy(false);
    }
  }

  const datasets = useMemo(
    () => ['ALL', ...Array.from(new Set(entries.map((item) => item.dataset_name)))],
    [entries],
  );
  const visibleEntries = useMemo(
    () => entries.filter((item) => dataset === 'ALL' || item.dataset_name === dataset),
    [dataset, entries],
  );
  const selected = entries.find((item) => item.session_id === selectedId);
  const isWorkflow = selected?.case_type === 'WORKFLOW_FOREST';

  function changeDataset(nextDataset: string) {
    setDataset(nextDataset);
    const first = entries.find(
      (item) => nextDataset === 'ALL' || item.dataset_name === nextDataset,
    );
    if (first) void selectSession(first.session_id);
  }

  if (authLoading)
    return <main className="auth-loading">正在读取医生账户…</main>;
  if (!account) return <AuthGate />;

  return (
    <main className="history-page">
      <header className="history-header">
        <div>
          <span className="brand-mark">
            <History />
          </span>
          <div>
            <p>ClincForestBench · {account.username}</p>
            <h1>我的决策历史</h1>
          </div>
        </div>
        <Badge className="history-count">
          <FileClock /> {entries.length} 个已完成病例
        </Badge>
        <Link className="audit-nav-link" href="/history?mode=temporal">
          Temporal history <Clock3 />
        </Link>
      </header>

      <section className="history-toolbar">
        <label>
          <span>数据集</span>
          <select
            disabled={busy || !entries.length}
            onChange={(event) => changeDataset(event.target.value)}
            value={dataset}
          >
            {datasets.map((name) => (
              <option key={name} value={name}>
                {name === 'ALL' ? '全部数据集' : name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>选择一次游玩记录</span>
          <select
            disabled={busy || !entries.length}
            onChange={(event) => void selectSession(event.target.value)}
            value={selectedId}
          >
            {visibleEntries.map((item) => (
              <option key={item.session_id} value={item.session_id}>
                {item.dataset_name} · {item.case_id} ·{' '}
                {new Date(item.completed_at).toLocaleString('zh-CN')} ·{' '}
                {item.is_correct ? '诊断一致' : '诊断不同'}
              </option>
            ))}
          </select>
        </label>
        {selected && (
          <div className="history-outcome">
            <span className={selected.is_correct ? 'is-correct' : 'is-wrong'}>
              {selected.is_correct ? <Check /> : <CircleX />}
            </span>
            <p>
              我的最终{isWorkflow ? '工作流结果' : '判断'} <b>{selected.predicted_label}</b>
            </p>
            <ChevronRight />
            <p>
              Ground truth <b>{selected.ground_truth_label}</b>
            </p>
          </div>
        )}
      </section>

      {detail ? (
        <section className="history-grid">
          <HistoryPanel
            eyebrow="1 · Reference"
            icon={<Stethoscope />}
            title="Ground-truth 树"
          >
            <GroundTruthTree
              key={detail.session_id}
              tree={detail.ground_truth_tree}
            />
          </HistoryPanel>
          <HistoryPanel
            eyebrow="2 · My JSON"
            icon={<GitBranch />}
            title="我的决策树 JSON"
          >
            <JsonDocument
              filename={`${detail.case_id}.${detail.session_id.slice(0, 8)}.decision.json`}
              onNotice={setNotice}
              value={detail.decision_json}
            />
          </HistoryPanel>
          <HistoryPanel
            eyebrow="3 · My checkpoints"
            icon={<Activity />}
            title={isWorkflow ? '每轮工作流结果排序' : '每轮诊断排序'}
          >
            <DecisionRounds
              labels={detail.decision_json.reference.outcome_labels}
              rounds={detail.belief_rounds}
            />
          </HistoryPanel>
        </section>
      ) : (
        <section className="history-empty">
          <History />
          <b>{notice}</b>
          <Link href="/arena">
            进入 Arena 完成第一个病例 <ChevronRight />
          </Link>
        </section>
      )}
      {notice && detail && <p className="case-audit-notice">{notice}</p>}
    </main>
  );
}

function HistoryPanel({
  eyebrow,
  icon,
  title,
  children,
}: {
  eyebrow: string;
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <article className="history-panel">
      <header>
        <span>{icon}</span>
        <div>
          <p>{eyebrow}</p>
          <h2>{title}</h2>
        </div>
      </header>
      <div className="history-panel-body">{children}</div>
    </article>
  );
}

function DecisionRounds({
  rounds,
  labels,
}: {
  rounds: BeliefSnapshotPayload[];
  labels: Record<string, string>;
}) {
  return (
    <div className="decision-rounds">
      {rounds.map((round) => (
        <article
          className={round.is_final ? 'is-final' : undefined}
          key={round.belief_id}
        >
          <header>
            <span>{round.is_final ? 'FINAL' : `S${round.step}`}</span>
            <small>{round.is_final ? '锁定诊断' : '阶段性提交'}</small>
          </header>
          <ol>
            {[...round.belief.diagnoses]
              .sort((left, right) => left.rank - right.rank)
              .map((diagnosis) => (
                <li key={diagnosis.condition_id}>
                  <i>{diagnosis.rank}</i>
                  <b>{labels[diagnosis.condition_id] ?? diagnosis.condition_id}</b>
                </li>
              ))}
          </ol>
        </article>
      ))}
    </div>
  );
}
