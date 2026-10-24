import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from '@/App';
import { useAuthStore } from '@/stores/auth';
import type { UserProfile } from '@/api/auth';

const authApi = vi.hoisted(() => ({
  login: vi.fn(),
  logout: vi.fn(),
  me: vi.fn(),
}));
const aiDrawerRender = vi.hoisted(() => vi.fn());

vi.mock('@/api', () => ({ authApi }));
vi.mock('@/routes', () => ({
  routes: [
    { path: '/login', element: <div>login page</div>, auth: false },
    { path: '/change-password', element: <div>change password page</div>, auth: true },
    { path: '/dashboard', element: <div>protected page</div>, auth: true },
  ],
}));
vi.mock('@/components/AppLayout', async () => {
  const { Outlet } = await import('react-router-dom');
  return { default: () => <Outlet /> };
});
vi.mock('@/components/AIHelpProvider', () => ({
  AIHelpProvider: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock('@/components/AIHelpDrawer', () => ({
  default: () => {
    aiDrawerRender();
    return <div>AI drawer</div>;
  },
}));

const userA: UserProfile = {
  id: 1,
  username: 'account-a',
  role: 'user',
  must_change_password: false,
};
const userB: UserProfile = {
  id: 2,
  username: 'account-b',
  role: 'user',
  must_change_password: true,
};
const usersByToken: Record<string, UserProfile> = {
  'token-a': userA,
  'token-b': userB,
};

let queryClient: QueryClient;
let meRequestTokens: Array<string | null>;

function setSession(token: string) {
  localStorage.setItem('token', token);
  localStorage.setItem('refresh_token', `refresh-${token}`);
  useAuthStore.setState({
    token,
    refreshToken: `refresh-${token}`,
    isAuthenticated: true,
    user: usersByToken[token],
  });
}

function renderApp() {
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );
}

describe('真实 QueryClient 下的认证身份隔离', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    window.history.replaceState({}, '', '/dashboard');
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    meRequestTokens = [];
    authApi.me.mockImplementation(() => {
      const token = localStorage.getItem('token');
      meRequestTokens.push(token);
      const user = token ? usersByToken[token] : undefined;
      return user
        ? Promise.resolve({ data: user })
        : Promise.reject(new Error('unknown session'));
    });
    authApi.logout.mockResolvedValue({ data: {} });
    authApi.login.mockImplementation(({ username }: { username: string }) => {
      const user = username === 'account-b' ? userB : userA;
      const token = username === 'account-b' ? 'token-b' : 'token-a';
      return Promise.resolve({
        data: {
          access_token: token,
          refresh_token: `refresh-${token}`,
          token_type: 'bearer',
          user,
        },
      });
    });
  });

  afterEach(() => {
    cleanup();
    queryClient.clear();
    localStorage.clear();
  });

  it('A 退出后 B 登录必须重新获取 B 身份并执行 B 的强制改密', async () => {
    setSession('token-a');
    renderApp();

    expect(await screen.findByText('protected page')).toBeInTheDocument();
    await waitFor(() => {
      expect(useAuthStore.getState().user?.username).toBe('account-a');
    });
    // 正常用户仍挂载全局 AI drawer。
    expect(aiDrawerRender).toHaveBeenCalled();

    await act(async () => {
      await useAuthStore.getState().logout();
    });
    expect(await screen.findByText('login page')).toBeInTheDocument();

    await act(async () => {
      await useAuthStore.getState().login('account-b', 'password');
    });
    act(() => {
      window.history.replaceState({}, '', '/dashboard');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    expect(await screen.findByText('change password page')).toBeInTheDocument();
    await waitFor(() => {
      expect(useAuthStore.getState().user?.username).toBe('account-b');
    });
    expect(useAuthStore.getState().user?.must_change_password).toBe(true);
    expect(meRequestTokens).toContain('token-b');
    expect(screen.queryByText('protected page')).not.toBeInTheDocument();
  });

  it('待改密用户不挂载全局 AI drawer', async () => {
    setSession('token-b');
    renderApp();

    expect(await screen.findByText('change password page')).toBeInTheDocument();
    await waitFor(() => {
      expect(useAuthStore.getState().user?.username).toBe('account-b');
    });
    expect(aiDrawerRender).not.toHaveBeenCalled();
    expect(screen.queryByText('AI drawer')).not.toBeInTheDocument();
  });
});
