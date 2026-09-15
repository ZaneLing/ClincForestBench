'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Activity, ArrowLeft, ChevronRight, Clock3, FileClock, GitBranch, History, Stethoscope } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { AuthGate } from '@/features/auth/auth-gate';
import { useAuth } from '@/features/auth/auth-context';
import { JsonDocument } from '@/features/forest/research-dashboard';
import type { TemporalArenaReview } from '@/features/temporal/types';
import { api } from '@/lib/api';

type Entry = { session_id: string; case_id: string; dataset_name: string; status: string; created_at: string; completed_at: string | null; actions_used: number };

export function TemporalDecisionHistory() {
  const { account, loading } = useAuth();
  const [entries, setEntries] = useState<Entry[]>([]);
  const [dataset, setDataset] = useState('ALL');
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState<TemporalArenaReview | null>(null);
  const [notice, setNotice] = useState('正在读取时间病例历史…');

  async function select(value: string) {
    if (!value) return;
    try {
      const result = await api<TemporalArenaReview>(`/me/temporal-history/${value}`);
      setSelectedId(value);
      setDetail(result);
      setNotice('');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '历史读取失败');
    }
  }

  useEffect(() => {
    if (!account) return;
    void api<{ sessions: Entry[] }>('/me/temporal-history').then((result) => {
      const completed = result.sessions.filter((item) => item.status === 'COMPLETED');
      setEntries(completed);
      if (completed[0]) void select(completed[0].session_id);
      else setNotice('还没有完成过 Temporal Case。');
    }).catch((error: Error) => setNotice(error.message));
  }, [account]);

  const datasets = useMemo(() => ['ALL', ...new Set(entries.map((item) => item.dataset_name))], [entries]);
  const visible = entries.filter((item) => dataset === 'ALL' || item.dataset_name === dataset);
  if (loading) return <main className="auth-loading">正在读取医生账户…</main>;
  if (!account) return <AuthGate />;

  return <main className="history-page temporal-history-page">
    <header className="history-header"><div><span className="brand-mark"><Clock3 /></span><div><p>ClincForestBench · {account.username}</p><h1>Temporal 决策历史</h1></div></div><Badge className="history-count"><FileClock />{entries.length} 个已完成病例</Badge><Link className="audit-nav-link" href="/history"><ArrowLeft />普通病例历史</Link></header>
    <section className="history-toolbar"><label><span>数据集</span><select onChange={(event) => { const value = event.target.value; setDataset(value); const first = entries.find((item) => value === 'ALL' || item.dataset_name === value); if (first) void select(first.session_id); }} value={dataset}>{datasets.map((name) => <option key={name} value={name}>{name === 'ALL' ? '全部时间数据集' : name}</option>)}</select></label><label><span>选择游玩记录</span><select onChange={(event) => void select(event.target.value)} value={selectedId}>{visible.map((item) => <option key={item.session_id} value={item.session_id}>{item.dataset_name} · {item.case_id} · {item.actions_used} actions</option>)}</select></label>{detail && <div className="history-outcome"><span className={detail.comparison.is_exact_match ? 'is-correct' : 'is-wrong'}><Activity /></span><p>我的最终判断 <b>{detail.comparison.predicted_diagnosis}</b></p><ChevronRight /><p>Reference <b>{detail.comparison.ground_truth_diagnosis}</b></p></div>}</section>
    {detail ? <section className="history-grid">
      <HistoryPanel eyebrow="1 · Reference" icon={<Stethoscope />} title="Ground-truth 时间树"><div className="temporal-history-tree">{[...detail.ground_truth_tree.nodes].sort((a, b) => a.reveal_time_min - b.reveal_time_min).map((node) => <div className={`tone-${node.node_type.toLowerCase()}`} key={node.node_id}><i /><span><b>{node.label}</b><small>T+{Math.round(node.reveal_time_min)}m · {node.node_type}</small></span></div>)}</div></HistoryPanel>
      <HistoryPanel eyebrow="2 · My JSON" icon={<GitBranch />} title="完整时间决策 JSON"><JsonDocument filename={`${detail.session.case_id}.${selectedId.slice(0, 12)}.temporal.json`} onNotice={setNotice} value={detail.session} /></HistoryPanel>
      <HistoryPanel eyebrow="3 · Checkpoints" icon={<History />} title="每轮诊断排序"><div className="decision-rounds temporal-rounds">{detail.session.belief_history.map((round) => <article key={round.submitted_at}><header><span>S{round.checkpoint}</span><small>T+{Math.round(round.game_time_min)}m</small></header><ol>{round.diagnoses.map((diagnosis, index) => <li key={diagnosis}><i>{index + 1}</i><b>{diagnosis}</b></li>)}</ol></article>)}</div></HistoryPanel>
    </section> : <section className="history-empty"><Clock3 /><b>{notice}</b><Link href="/temporal?mode=arena">进入 Temporal Arena <ChevronRight /></Link></section>}
    {notice && detail && <p className="case-audit-notice">{notice}</p>}
  </main>;
}

function HistoryPanel({ eyebrow, icon, title, children }: { eyebrow: string; icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return <article className="history-panel"><header><span>{icon}</span><div><p>{eyebrow}</p><h2>{title}</h2></div></header><div className="history-panel-body">{children}</div></article>;
}
