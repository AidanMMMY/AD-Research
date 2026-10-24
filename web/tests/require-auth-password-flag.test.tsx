import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import App from '@/App';
import { useAuthStore } from '@/stores/auth';

const useMeMock = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/useAuth', () => ({ useMe: useMeMock }));
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
vi.mock('@/components/AIHelpDrawer', () => ({ default: () => null }));

function mockMe(data?: { must_change_password: boolean }, isLoading = false) {
  useMeMock.mockReturnValue({
    data: data ? { data } : undefined,
    isError: false,
    error: null,
    isLoading,
    refetch: vi.fn(),
  });
}

function setPersistedUser(mustChangePassword: boolean) {
  localStorage.setItem('token', 'token');
  useAuthStore.setState({
    token: 'token',
    isAuthenticated: true,
    user: {
      id: 1,
      username: 'tester',
      role: 'user',
      must_change_password: mustChangePassword,
    },
  });
}

describe('RequireAuth 首登强制改密门控', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/dashboard');
    localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('本次 /me 返回 true 时立即跳转，不先挂载持久化 false 对应的 children', async () => {
    setPersistedUser(false);
    mockMe({ must_change_password: true });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('change password page')).toBeInTheDocument();
    });
    expect(screen.queryByText('protected page')).not.toBeInTheDocument();
  });

  it('本次 /me 返回 false 时覆盖持久化的 stale true', async () => {
    setPersistedUser(true);
    mockMe({ must_change_password: false });

    render(<App />);

    expect(await screen.findByText('protected page')).toBeInTheDocument();
    expect(screen.queryByText('change password page')).not.toBeInTheDocument();
  });

  it('已认证但 /me 尚未返回数据时不渲染受保护 children', () => {
    setPersistedUser(false);
    mockMe(undefined, false);

    const { container } = render(<App />);

    expect(screen.queryByText('protected page')).not.toBeInTheDocument();
    expect(container.querySelector('.auth-loading')).not.toBeNull();
  });
});
