import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import RegisterVerify from '@/pages/RegisterVerify';
import ResendButton from '@/components/auth/ResendButton';
import { useAuthStore } from '@/stores/auth';
import type { UserProfile } from '@/api/auth';

const authApi = vi.hoisted(() => ({
  register: vi.fn(),
  checkUsername: vi.fn(),
  resendVerification: vi.fn(),
  verifyRegistration: vi.fn(),
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

const VERIFY_SUCCESS = {
  data: {
    access_token: 'acc-1',
    refresh_token: 'ref-1',
    token_type: 'bearer',
    user: VERIFIED_USER,
  },
};

function renderVerify(initialEntry: string | { pathname: string; state?: unknown }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/register/verify" element={<RegisterVerify />} />
          <Route path="/register" element={<div>register page</div>} />
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

describe('注册验证页（OTP 流程）', () => {
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
    authApi.verifyRegistration.mockResolvedValue(VERIFY_SUCCESS);
  });

  afterEach(cleanup);

  it('验证成功：写双令牌 → 同步 me → 自动跳转 dashboard', async () => {
    renderVerify({ pathname: '/register/verify', state: { email: 'a@b.com', username: 'aidan' } });
    enterCode('123456');
    expect(screen.getByLabelText('第 6 位邮箱验证码')).toHaveValue('6');

    fireEvent.click(screen.getByRole('button', { name: '验证并进入平台' }));

    // 令牌走既有存储方式：localStorage + zustand store（与改密页一致）
    await waitFor(() => expect(localStorage.getItem('token')).toBe('acc-1'));
    expect(localStorage.getItem('refresh_token')).toBe('ref-1');
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().user).toEqual(VERIFIED_USER);
    expect(authApi.verifyRegistration).toHaveBeenCalledWith({ email: 'a@b.com', code: '123456' });

    // 绿色涟漪 + 已验证提示，随后自动进入 dashboard
    expect(await screen.findByText('邮箱已验证')).toBeInTheDocument();
    expect(await screen.findByText('dashboard page', {}, { timeout: 4000 })).toBeInTheDocument();
  });

  it('验证码错误（400）：展示剩余次数并抖动', async () => {
    authApi.verifyRegistration.mockRejectedValue({
      response: { status: 400, data: { detail: 'invalid code', remaining_attempts: 3 } },
    });
    renderVerify({ pathname: '/register/verify', state: { email: 'a@b.com' } });
    enterCode('000000');
    fireEvent.click(screen.getByRole('button', { name: '验证并进入平台' }));

    expect(await screen.findByText(/还剩 3 次机会/)).toBeInTheDocument();
    const cell = screen.getByLabelText('第 1 位邮箱验证码');
    expect((cell.parentElement as HTMLElement).className).toContain('otp-group--error');
  });

  it('验证码过期（410）：一键重发被强调', async () => {
    authApi.verifyRegistration.mockRejectedValue({
      response: { status: 410, data: { detail: 'code expired' } },
    });
    renderVerify({ pathname: '/register/verify', state: { email: 'a@b.com' } });
    enterCode('111111');
    fireEvent.click(screen.getByRole('button', { name: '验证并进入平台' }));

    expect(await screen.findByText(/验证码已过期/)).toBeInTheDocument();
    expect(document.querySelector('.resend--emphasize')).not.toBeNull();
  });

  it('魔法链接成功回跳 ?verified=1：直接呈现结果 + 去登录入口', () => {
    renderVerify('/register/verify?verified=1&email=a@b.com');
    expect(screen.getByText('邮箱已验证')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /去登录/ })).toHaveAttribute('href', '/login');
    // 验证已完成，不应再渲染 OTP 输入
    expect(screen.queryByLabelText('第 1 位邮箱验证码')).not.toBeInTheDocument();
  });

  it('魔法链接失败回跳 ?verified=0&reason=expired：说明原因并保留 OTP 出路', () => {
    renderVerify('/register/verify?verified=0&reason=expired&email=a@b.com');
    expect(screen.getByText(/链接已过期/)).toBeInTheDocument();
    expect(screen.getByLabelText('第 1 位邮箱验证码')).toBeInTheDocument();
    const backLink = screen.getByRole('link', { name: /换个邮箱重新注册/ });
    expect(backLink).toHaveAttribute('href', '/register');
  });

  it('直接打开验证页（无 email）：先补邮箱再进入 OTP', () => {
    renderVerify('/register/verify');
    const emailField = screen.getByLabelText('注册邮箱');
    fireEvent.change(emailField, { target: { value: 'a@b.com' } });
    fireEvent.click(screen.getByRole('button', { name: '继续' }));
    expect(screen.getByLabelText('第 1 位邮箱验证码')).toBeInTheDocument();
    expect(screen.getByText('a@b.com')).toBeInTheDocument();
  });

  it('验证页携带 username 时，「换个邮箱重新注册」把用户名带回去', () => {
    renderVerify({
      pathname: '/register/verify',
      state: { email: 'a@b.com', username: 'aidan' },
    });
    const backLink = screen.getByRole('link', { name: /换个邮箱重新注册/ });
    expect(backLink).toHaveAttribute('href', '/register?username=aidan');
  });
});

describe('ResendButton 冷却', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(cleanup);

  it('冷却结束可点击并触发重发，点击后冷却重启', async () => {
    const onResend = vi.fn().mockResolvedValue(undefined);
    render(<ResendButton onResend={onResend} cooldownSeconds={1} />);

    const button = screen.getByRole('button', { name: /冷却中/ });
    expect(button).toBeDisabled();

    const ready = await screen.findByRole('button', { name: '重新发送验证邮件' });
    expect(ready).toBeEnabled();

    fireEvent.click(ready);
    await waitFor(() => expect(onResend).toHaveBeenCalledTimes(1));
    // 冷却重新计时：按钮再次进入禁用态
    await waitFor(() => expect(screen.getByRole('button', { name: /冷却中/ })).toBeDisabled());
  });
});
