import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ForgotPassword from '@/pages/ForgotPassword';
import ResetPassword from '@/pages/ResetPassword';
import { useAuthStore } from '@/stores/auth';
import type { UserProfile } from '@/api/auth';

const authApi = vi.hoisted(() => ({
  forgotPassword: vi.fn(),
  resetPassword: vi.fn(),
  me: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
}));

vi.mock('@/api', () => ({ authApi }));

const VERIFIED_USER: UserProfile = {
  id: 9,
  username: 'aidan',
  role: 'user',
  must_change_password: false,
};

const RESET_SUCCESS = {
  data: {
    access_token: 'acc-reset',
    refresh_token: 'ref-reset',
    token_type: 'bearer',
    user: VERIFIED_USER,
  },
};

function renderAt(initialEntry: string, element: React.ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/forgot-password" element={element} />
          <Route path="/reset-password" element={element} />
          <Route path="/login" element={<div>login page</div>} />
          <Route path="/dashboard" element={<div>dashboard page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function enterCode(code: string) {
  fireEvent.paste(screen.getByLabelText('第 1 位邮箱验证码'), {
    clipboardData: { getData: () => code },
  });
}

describe('忘记密码页', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authApi.forgotPassword.mockResolvedValue({ data: { detail: 'reset email sent' } });
  });

  afterEach(cleanup);

  it('邮箱格式不对：红字提示且不发请求', () => {
    renderAt('/forgot-password', <ForgotPassword />);
    fireEvent.change(screen.getByLabelText('注册邮箱'), { target: { value: 'nope' } });
    fireEvent.click(screen.getByRole('button', { name: '发送重置邮件' }));
    expect(authApi.forgotPassword).not.toHaveBeenCalled();
  });

  it('提交成功：进入查收状态并展示邮箱 + 重发入口', async () => {
    renderAt('/forgot-password', <ForgotPassword />);
    fireEvent.change(screen.getByLabelText('注册邮箱'), { target: { value: 'a@b.com' } });
    fireEvent.click(screen.getByRole('button', { name: '发送重置邮件' }));

    await waitFor(() => expect(authApi.forgotPassword).toHaveBeenCalledWith('a@b.com'));
    expect(await screen.findByText('重置邮件已发送')).toBeInTheDocument();
    expect(screen.getByText('a@b.com')).toBeInTheDocument();
    // 重发按钮进入 60s 冷却（环形倒计时可见）
    expect(screen.getByRole('button', { name: /冷却中/ })).toBeDisabled();
    expect(screen.getByRole('link', { name: /返回登录/ })).toHaveAttribute('href', '/login');
  });

  it('429 冷却：给出轻提示不进入查收状态', async () => {
    authApi.forgotPassword.mockRejectedValue({
      response: { status: 429, data: { detail: 'cooldown' } },
    });
    renderAt('/forgot-password', <ForgotPassword />);
    fireEvent.change(screen.getByLabelText('注册邮箱'), { target: { value: 'a@b.com' } });
    fireEvent.click(screen.getByRole('button', { name: '发送重置邮件' }));
    await waitFor(() => expect(authApi.forgotPassword).toHaveBeenCalled());
    // 仍在表单态，未切到查收面板
    expect(screen.queryByText('重置邮件已发送')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '发送重置邮件' })).toBeEnabled();
  });
});

describe('重置密码页', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    useAuthStore.setState({
      token: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
    });
    authApi.me.mockResolvedValue({ data: VERIFIED_USER });
    authApi.resetPassword.mockResolvedValue(RESET_SUCCESS);
  });

  afterEach(cleanup);

  it('code 模式：邮箱+验证码+新密码 → 写双令牌自动登录进 dashboard', async () => {
    renderAt('/reset-password?email=a@b.com', <ResetPassword />);
    fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'fresh-start-2026x' } });
    fireEvent.change(screen.getByLabelText('确认新密码'), {
      target: { value: 'fresh-start-2026x' },
    });
    enterCode('123456');
    fireEvent.click(screen.getByRole('button', { name: '重置密码并登录' }));

    await waitFor(() =>
      expect(authApi.resetPassword).toHaveBeenCalledWith({
        email: 'a@b.com',
        code: '123456',
        new_password: 'fresh-start-2026x',
      }),
    );
    await waitFor(() => expect(localStorage.getItem('token')).toBe('acc-reset'));
    expect(localStorage.getItem('refresh_token')).toBe('ref-reset');
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(await screen.findByText('dashboard page', {}, { timeout: 4000 })).toBeInTheDocument();
  });

  it('token 模式（邮件链接回跳）：免输验证码直接设新密码', async () => {
    renderAt('/reset-password?token=jwt-abc&email=a@b.com', <ResetPassword />);
    expect(screen.queryByLabelText('第 1 位邮箱验证码')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'fresh-start-2026x' } });
    fireEvent.change(screen.getByLabelText('确认新密码'), {
      target: { value: 'fresh-start-2026x' },
    });
    fireEvent.click(screen.getByRole('button', { name: '重置密码并登录' }));

    await waitFor(() =>
      expect(authApi.resetPassword).toHaveBeenCalledWith({
        token: 'jwt-abc',
        new_password: 'fresh-start-2026x',
      }),
    );
    await waitFor(() => expect(localStorage.getItem('token')).toBe('acc-reset'));
  });

  it('链接失败回跳 ?error=expired：说明原因并提供重新申请入口', () => {
    renderAt('/reset-password?error=expired', <ResetPassword />);
    expect(screen.getByText(/链接已过期/)).toBeInTheDocument();
    const retryLink = screen.getByRole('link', { name: /重新申请一封/ });
    expect(retryLink).toHaveAttribute('href', '/forgot-password');
  });

  it('验证码错误（400）：展示剩余次数并抖动', async () => {
    authApi.resetPassword.mockRejectedValue({
      response: { status: 400, data: { detail: 'invalid code', remaining_attempts: 2 } },
    });
    renderAt('/reset-password?email=a@b.com', <ResetPassword />);
    fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'fresh-start-2026x' } });
    fireEvent.change(screen.getByLabelText('确认新密码'), {
      target: { value: 'fresh-start-2026x' },
    });
    enterCode('000000');
    fireEvent.click(screen.getByRole('button', { name: '重置密码并登录' }));

    expect(await screen.findByText(/还剩 2 次机会/)).toBeInTheDocument();
    const cell = screen.getByLabelText('第 1 位邮箱验证码');
    expect((cell.parentElement as HTMLElement).className).toContain('otp-group--error');
  });

  it('验证码过期（410）：提示重新申请', async () => {
    authApi.resetPassword.mockRejectedValue({
      response: { status: 410, data: { detail: 'code expired' } },
    });
    renderAt('/reset-password?email=a@b.com', <ResetPassword />);
    fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'fresh-start-2026x' } });
    fireEvent.change(screen.getByLabelText('确认新密码'), {
      target: { value: 'fresh-start-2026x' },
    });
    enterCode('111111');
    fireEvent.click(screen.getByRole('button', { name: '重置密码并登录' }));

    expect(await screen.findByText(/已过期/)).toBeInTheDocument();
  });

  it('两次密码不一致：红字提示且不提交', () => {
    renderAt('/reset-password?email=a@b.com', <ResetPassword />);
    fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'fresh-start-2026x' } });
    fireEvent.change(screen.getByLabelText('确认新密码'), {
      target: { value: 'different-pass-1',
      },
    });
    enterCode('123456');
    fireEvent.click(screen.getByRole('button', { name: '重置密码并登录' }));
    expect(screen.getByText('两次输入的密码不一致')).toBeInTheDocument();
    expect(authApi.resetPassword).not.toHaveBeenCalled();
  });

  it('新密码与旧密码相同（422）：密码框下红字', async () => {
    authApi.resetPassword.mockRejectedValue({
      response: { status: 422, data: { detail: '新密码不能与旧密码相同' } },
    });
    renderAt('/reset-password?email=a@b.com', <ResetPassword />);
    fireEvent.change(screen.getByLabelText('新密码'), { target: { value: 'fresh-start-2026x' } });
    fireEvent.change(screen.getByLabelText('确认新密码'), {
      target: { value: 'fresh-start-2026x' },
    });
    enterCode('123456');
    fireEvent.click(screen.getByRole('button', { name: '重置密码并登录' }));

    expect(await screen.findByText('新密码不能与旧密码相同')).toBeInTheDocument();
  });
});
