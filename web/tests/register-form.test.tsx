import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import Register from '@/pages/Register';
import { useAuthStore } from '@/stores/auth';

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

/** Captures the router location so assertions can cover navigation + state. */
function LocationProbe() {
  const location = useLocation();
  return (
    <div>
      <span data-testid="probe-pathname">{location.pathname}</span>
      <span data-testid="probe-state">{JSON.stringify(location.state ?? null)}</span>
    </div>
  );
}

function renderRegister(initialEntry = '/register') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/register" element={<Register />} />
        <Route path="/register/verify" element={<LocationProbe />} />
        <Route path="/login" element={<div>login page</div>} />
        <Route path="/dashboard" element={<div>dashboard</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

const VALID_EMAIL = 'aidan@example.com';
const VALID_USERNAME = 'aidan';
const VALID_PASSWORD = 'abcd1234efgh'; // gitleaks:allow — 测试夹具假密码，须满足 12+ 字符策略故触发熵阈值

function fillForm(
  email = VALID_EMAIL,
  username = VALID_USERNAME,
  password = VALID_PASSWORD,
) {
  fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: email } });
  fireEvent.change(screen.getByLabelText('用户名'), { target: { value: username } });
  fireEvent.change(screen.getByLabelText('密码'), { target: { value: password } });
}

describe('注册表单校验与提交流程', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    useAuthStore.setState({
      token: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
    });
    authApi.checkUsername.mockResolvedValue({ data: { available: true, suggestions: null } });
    authApi.register.mockResolvedValue({ data: { detail: 'verification email sent' } });
  });

  afterEach(() => {
    cleanup();
  });

  it('邮箱格式错误时给人话提示（400ms 防抖后）', async () => {
    renderRegister();
    fireEvent.change(screen.getByLabelText('邮箱'), {
      target: { value: 'not-an-email' },
    });
    expect(await screen.findByText(/邮箱格式看起来不太对/)).toBeInTheDocument();
  });

  it('用户名被占用时展示人话文案 + 可点选的建议', async () => {
    authApi.checkUsername.mockResolvedValueOnce({
      data: {
        available: false,
        suggestions: ['aidan_2026', 'aidan_dev', 'aidan'],
      },
    });
    authApi.checkUsername.mockResolvedValueOnce({
      data: { available: true, suggestions: null },
    });
    renderRegister();

    fireEvent.change(screen.getByLabelText('用户名'), { target: { value: 'aidan' } });
    expect(await screen.findByText(/这个名字已经被占用了，试试 aidan_2026？/)).toBeInTheDocument();
    // 建议以可点选 chip 呈现
    const chip = screen.getByRole('button', { name: 'aidan_dev' });
    expect(chip).toBeInTheDocument();

    // 点选建议自动填充并重新走查重
    fireEvent.click(screen.getByRole('button', { name: 'aidan_2026' }));
    expect(screen.getByLabelText('用户名')).toHaveValue('aidan_2026');
    await waitFor(() =>
      expect(authApi.checkUsername).toHaveBeenLastCalledWith('aidan_2026'),
    );
    expect(await screen.findByText('✓ 可用')).toBeInTheDocument();
  });

  it('密码策略提示实时联动，达标后提示符合要求', async () => {
    renderRegister();
    const passwordField = screen.getByLabelText('密码');
    expect(screen.getByText('长度 12–64 位')).toBeInTheDocument();

    fireEvent.change(passwordField, { target: { value: 'short1' } });
    expect(screen.getByText('6/64')).toBeInTheDocument();

    fireEvent.change(passwordField, { target: { value: VALID_PASSWORD } });
    expect(await screen.findByText('密码符合要求')).toBeInTheDocument();
    expect(screen.getByText('12/64')).toBeInTheDocument();
  });

  it('提交成功后携带 email/username 进入验证页', async () => {
    renderRegister();
    fillForm();
    fireEvent.click(screen.getByRole('button', { name: '创建账号' }));

    await waitFor(() =>
      expect(authApi.register).toHaveBeenCalledWith({
        email: VALID_EMAIL,
        username: VALID_USERNAME,
        password: VALID_PASSWORD,
      }),
    );
    await waitFor(() =>
      expect(screen.getByTestId('probe-pathname')).toHaveTextContent('/register/verify'),
    );
    const state = JSON.parse(screen.getByTestId('probe-state').textContent ?? 'null');
    expect(state).toEqual({ email: VALID_EMAIL, username: VALID_USERNAME });
  });

  it('表单未通过校验时不发注册请求', () => {
    renderRegister();
    fireEvent.click(screen.getByRole('button', { name: '创建账号' }));
    expect(authApi.register).not.toHaveBeenCalled();
    // 同步展示字段级错误（submit 路径不走防抖）
    expect(screen.getByText('先填一个邮箱，验证邮件要发到这里')).toBeInTheDocument();
    expect(screen.getByText(/给自己起个名字吧/)).toBeInTheDocument();
  });

  it('服务端 400 用户名占用时，把错误落回用户名字段（防抖查重漏网的兜底）', async () => {
    // 查重探针失败 → 前端 fail-open 放行，让服务端当事实源
    authApi.checkUsername.mockRejectedValue(new Error('probe down'));
    authApi.register.mockRejectedValue({
      response: { status: 400, data: { detail: 'username already taken' } },
    });
    renderRegister();
    fillForm();
    fireEvent.click(screen.getByRole('button', { name: '创建账号' }));

    await waitFor(() => expect(authApi.register).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('这个名字已经被占用了')).toBeInTheDocument();
  });

  it('已登录用户访问注册页被重定向到 dashboard', () => {
    useAuthStore.setState({
      token: 'tok',
      isAuthenticated: true,
      user: { id: 1, username: 'aidan', role: 'user' },
    });
    localStorage.setItem('token', 'tok');
    renderRegister();
    expect(screen.getByText('dashboard')).toBeInTheDocument();
  });
});
