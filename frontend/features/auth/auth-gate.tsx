'use client';

import { useState } from 'react';
import { HeartPulse, KeyRound, LogIn, UserPlus } from 'lucide-react';
import { motion } from 'motion/react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useAuth } from './auth-context';

export function AuthGate() {
  const { loading, login, register } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event: { preventDefault: () => void }) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      if (mode === 'login') await login(username, password);
      else await register(username, password);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '账户操作失败');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-gate">
      <div className="auth-grid" />
      <motion.section
        animate={{ opacity: 1, y: 0 }}
        className="auth-card"
        initial={{ opacity: 0, y: 18 }}
      >
        <header>
          <span>
            <HeartPulse />
          </span>
          <div>
            <p>ClincForestBench</p>
            <h1>医生账户</h1>
          </div>
        </header>
        <Tabs
          onValueChange={(value) => setMode(value as 'login' | 'register')}
          value={mode}
        >
          <TabsList className="auth-tabs">
            <TabsTrigger value="login">
              <LogIn /> 登录
            </TabsTrigger>
            <TabsTrigger value="register">
              <UserPlus /> 注册
            </TabsTrigger>
          </TabsList>
          <TabsContent value="login">
            <p className="auth-mode-copy">
              登录后继续诊断并查看自己的历史病例。
            </p>
          </TabsContent>
          <TabsContent value="register">
            <p className="auth-mode-copy">创建仅包含账户名和密码的医生账号。</p>
          </TabsContent>
        </Tabs>
        <form onSubmit={submit}>
          <label htmlFor="physician-username">
            <span>账户</span>
            <div>
              <UserPlus />
              <Input
                autoComplete="username"
                id="physician-username"
                minLength={3}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="doctor_name"
                required
                value={username}
              />
            </div>
          </label>
          <label htmlFor="physician-password">
            <span>密码</span>
            <div>
              <KeyRound />
              <Input
                autoComplete={
                  mode === 'login' ? 'current-password' : 'new-password'
                }
                id="physician-password"
                minLength={4}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="输入密码"
                required
                type="password"
                value={password}
              />
            </div>
          </label>
          {error && (
            <p className="auth-error" role="alert">
              {error}
            </p>
          )}
          <Button disabled={busy || loading} type="submit">
            {mode === 'login' ? <LogIn /> : <UserPlus />}
            {busy ? '处理中…' : mode === 'login' ? '登录并进入' : '注册并进入'}
          </Button>
        </form>
      </motion.section>
    </main>
  );
}
