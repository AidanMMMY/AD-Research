import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AdminUsers from '@/pages/AdminUsers';
import { useAuthStore } from '@/stores/auth';

const api = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  delete: vi.fn(),
  resetPassword: vi.fn(),
}));

vi.mock('@/api', () => ({
  adminUsersApi: api,
  authApi: {
    login: vi.fn(),
    logout: vi.fn(),
    me: vi.fn(),
  },
}));

if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

if (!window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function renderAdminUsers() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const result = render(
    <QueryClientProvider client={queryClient}>
      <AdminUsers />
    </QueryClientProvider>,
  );
  return { queryClient, ...result };
}

async function openCreateModal(username = 'newuser') {
  fireEvent.click(screen.getByRole('button', { name: /新\s*增\s*用\s*户/ }));
  const dialog = await screen.findByRole('dialog');
  fireEvent.change(within(dialog).getByPlaceholderText('用户名'), {
    target: { value: username },
  });
  return dialog;
}

function modalOkButton(dialog: HTMLElement) {
  return within(dialog).getByRole('button', { name: /确\s*定|OK/ });
}

function expectPlaintextAbsentFromMutationCache(
  queryClient: QueryClient,
  plaintext: string,
) {
  for (const mutation of queryClient.getMutationCache().getAll()) {
    expect(JSON.stringify(mutation.state.data ?? '')).not.toContain(plaintext);
  }
}

describe('AdminUsers 自动密码流程', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    useAuthStore.setState({
      isAuthenticated: true,
      user: { id: 1, username: 'admin', role: 'admin' },
    });
    api.list.mockResolvedValue({
      data: [
        {
          id: 2,
          username: 'target',
          role: 'user',
          is_active: true,
          created_at: '2026-10-24T00:00:00Z',
        },
      ],
    });
  });

  afterEach(cleanup);

  it('创建请求 pending 时重复点击确认只产生一个请求，且不能关闭弹窗', async () => {
    const pending = deferred<unknown>();
    api.create.mockReturnValue(pending.promise);
    renderAdminUsers();
    const dialog = await openCreateModal();

    fireEvent.click(modalOkButton(dialog));
    await waitFor(() => expect(api.create).toHaveBeenCalledTimes(1));
    fireEvent.click(modalOkButton(dialog));
    expect(api.create).toHaveBeenCalledTimes(1);

    const cancel = within(dialog).getByRole('button', { name: /^(取\s*消|Cancel)$/ });
    fireEvent.click(cancel);
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    // Let the pending mutation finish so its zero-GC cleanup does not outlive
    // this test's QueryClient.
    pending.resolve({ data: {} });
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('创建响应复制到本地后立即清 mutation cache，关闭后清本地明文', async () => {
    const plaintext = 'CreateOneTime123';
    api.create.mockResolvedValue({
      data: {
        id: 3,
        username: 'newuser',
        role: 'user',
        is_active: true,
        initial_password: plaintext,
      },
    });
    const { queryClient } = renderAdminUsers();
    const dialog = await openCreateModal();

    fireEvent.click(modalOkButton(dialog));
    expect(await screen.findByText(plaintext)).toBeInTheDocument();
    await waitFor(() => {
      expectPlaintextAbsentFromMutationCache(queryClient, plaintext);
    });

    fireEvent.click(screen.getByRole('button', { name: /我\s*已\s*保\s*存/ }));
    await waitFor(() => {
      expect(screen.queryByText(plaintext)).not.toBeInTheDocument();
    });
    expectPlaintextAbsentFromMutationCache(queryClient, plaintext);
  });

  it('重置密码同样防止重复请求并清除响应中的明文', async () => {
    const pending = deferred<unknown>();
    api.resetPassword.mockReturnValue(pending.promise);
    const { queryClient } = renderAdminUsers();

    fireEvent.click(await screen.findByRole('button', { name: '重置密码' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(modalOkButton(dialog));
    await waitFor(() => expect(api.resetPassword).toHaveBeenCalledTimes(1));
    fireEvent.click(modalOkButton(dialog));
    expect(api.resetPassword).toHaveBeenCalledTimes(1);

    pending.resolve({
      data: { message: 'ok', initial_password: 'ResetOneTime123' },
    });
    expect(await screen.findByText('ResetOneTime123')).toBeInTheDocument();
    await waitFor(() => {
      expectPlaintextAbsentFromMutationCache(queryClient, 'ResetOneTime123');
    });
  });
});
