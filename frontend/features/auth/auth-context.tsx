'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import { api, AUTH_TOKEN_KEY } from '@/lib/api';

type Account = { username: string };
type AuthResult = { account: Account; token: string };
type AuthContextValue = {
  account: Account | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [account, setAccount] = useState<Account | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = window.localStorage.getItem(AUTH_TOKEN_KEY);
    if (!token) {
      const timer = window.setTimeout(() => setLoading(false), 0);
      return () => window.clearTimeout(timer);
    }
    let active = true;
    void api<Account>('/auth/me')
      .then((value) => {
        if (active) setAccount(value);
      })
      .catch(() => window.localStorage.removeItem(AUTH_TOKEN_KEY))
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function authenticate(
    endpoint: '/auth/login' | '/auth/register',
    username: string,
    password: string,
  ) {
    const result = await api<AuthResult>(endpoint, {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    window.localStorage.setItem(AUTH_TOKEN_KEY, result.token);
    setAccount(result.account);
  }

  async function logout() {
    try {
      await api('/auth/logout', { method: 'POST' });
    } finally {
      window.localStorage.removeItem(AUTH_TOKEN_KEY);
      setAccount(null);
    }
  }

  const value: AuthContextValue = {
    account,
    loading,
    login: (username, password) =>
      authenticate('/auth/login', username, password),
    register: (username, password) =>
      authenticate('/auth/register', username, password),
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
