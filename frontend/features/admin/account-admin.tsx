'use client';

import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  Eye,
  EyeOff,
  KeyRound,
  RefreshCw,
  ShieldCheck,
  UserRound,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { api } from '@/lib/api';

type AdminAccount = {
  username: string;
  password_plaintext: string;
  created_at: string;
  session_count: number;
  completed_session_count: number;
};

export function AccountAdmin() {
  const [researchKey, setResearchKey] = useState('local-research-only');
  const [accounts, setAccounts] = useState<AdminAccount[]>([]);
  const [visiblePasswords, setVisiblePasswords] = useState(false);
  const [notice, setNotice] = useState('正在读取原型账户…');
  const [busy, setBusy] = useState(false);

  async function load(key = researchKey) {
    setBusy(true);
    try {
      const value = await api<{ accounts: AdminAccount[] }>('/admin/accounts', {
        headers: { 'X-Research-Key': key },
      });
      setAccounts(value.accounts);
      setNotice('');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : '账户后台加载失败');
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    let active = true;
    void api<{ accounts: AdminAccount[] }>('/admin/accounts', {
      headers: { 'X-Research-Key': 'local-research-only' },
    })
      .then((value) => {
        if (!active) return;
        setAccounts(value.accounts);
        setNotice('');
      })
      .catch((error: Error) => {
        if (active) setNotice(error.message);
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="admin-page">
      <header className="admin-header">
        <div>
          <span className="brand-mark">
            <ShieldCheck />
          </span>
          <div>
            <p>ClincForestBench · Local prototype</p>
            <h1>医生账户后台</h1>
          </div>
        </div>
        <div className="admin-warning">
          <AlertTriangle />
          <span>
            <b>明文密码模式</b>仅用于当前本地 MVP，禁止用于生产或真实密码。
          </span>
        </div>
      </header>
      <section className="admin-toolbar">
        <label htmlFor="admin-research-key">
          <span>
            <KeyRound /> Research key
          </span>
          <Input
            id="admin-research-key"
            onChange={(event) => setResearchKey(event.target.value)}
            type="password"
            value={researchKey}
          />
        </label>
        <Button disabled={busy} onClick={() => void load()}>
          <RefreshCw />
          {busy ? '读取中…' : '刷新账户'}
        </Button>
        <Button
          onClick={() => setVisiblePasswords((value) => !value)}
          variant="outline"
        >
          {visiblePasswords ? <EyeOff /> : <Eye />}
          {visiblePasswords ? '隐藏密码' : '显示密码'}
        </Button>
      </section>
      <section className="admin-table-panel">
        <header>
          <UserRound />
          <div>
            <p>REGISTERED PHYSICIANS</p>
            <h2>{accounts.length} 个账户</h2>
          </div>
        </header>
        <div className="admin-table-scroll">
          <table>
            <thead>
              <tr>
                <th>账户</th>
                <th>密码（明文）</th>
                <th>注册时间</th>
                <th>游玩次数</th>
                <th>完成病例</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((account) => (
                <tr key={account.username}>
                  <td>
                    <b>{account.username}</b>
                  </td>
                  <td>
                    <code>
                      {visiblePasswords
                        ? account.password_plaintext
                        : '••••••••'}
                    </code>
                  </td>
                  <td>
                    {new Date(account.created_at).toLocaleString('zh-CN')}
                  </td>
                  <td>{account.session_count}</td>
                  <td>{account.completed_session_count}</td>
                </tr>
              ))}
              {!accounts.length && (
                <tr>
                  <td className="admin-empty" colSpan={5}>
                    {notice || '还没有注册账户'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
      {notice && accounts.length > 0 && (
        <p className="case-audit-notice">{notice}</p>
      )}
    </main>
  );
}
