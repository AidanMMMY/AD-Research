import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { message } from 'antd';
import { AxiosError } from 'axios';
import { UserOutlined, LockOutlined, StockOutlined } from '@ant-design/icons';
import { useAuthStore } from '@/stores/auth';
import AuroraBackground from '@/components/AuroraBackground';

export default function Login() {
  const navigate = useNavigate();
  const { login, isAuthenticated } = useAuthStore();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ username: '', password: '' });

  const token = localStorage.getItem('token');
  if (isAuthenticated && token) {
    navigate('/dashboard', { replace: true });
    return null;
  }

  const handleSubmit = async () => {
    if (!form.username || !form.password) {
      message.error('请输入用户名和密码');
      return;
    }
    setLoading(true);
    try {
      await login(form.username, form.password);
      message.success('登录成功');
      navigate('/dashboard', { replace: true });
    } catch (err) {
      // Distinguish 401 (bad credentials) from 5xx (server fault).
      // Collapsing both into "用户名密码不正确" hid real bugs in the past
      // (e.g. 2026-07-01 UserResponse missing 'id' → 500 → user thought
      // password was wrong). See runbook 20260701 § 4-B.
      const status = (err as AxiosError)?.response?.status;
      if (status === 401) {
        message.error('用户名或密码错误');
      } else if (status && status >= 500) {
        message.error('服务器错误，请稍后再试');
      } else if (!status) {
        message.error('无法连接到服务器，请检查网络');
      } else {
        message.error(`登录失败（HTTP ${status}）`);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page login-page--sci-fi">
      <AuroraBackground />

      <div className="login-card">
        <div className="login-card__corners" aria-hidden="true">
          <span className="login-card__corner login-card__corner--tl" />
          <span className="login-card__corner login-card__corner--tr" />
          <span className="login-card__corner login-card__corner--bl" />
          <span className="login-card__corner login-card__corner--br" />
        </div>

        <div className="login-logo-wrap">
          <div className="login-logo">
            <StockOutlined className="login-logo-icon" />
          </div>
          <h1 className="login-brand">
            AD-Research
          </h1>
          <p className="login-subtitle">
            全市场数据分析与投研工具
          </p>
        </div>

        <div className="login-form">
          <div className="login-input-wrapper"
          >
            <UserOutlined className="login-input-icon" />
            <input
              type="text"
              placeholder="用户名"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
              className="login-input"
            />
          </div>

          <div className="login-input-wrapper"
          >
            <LockOutlined className="login-input-icon" />
            <input
              type="password"
              placeholder="密码"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
              className="login-input"
            />
          </div>

          <button
            onClick={handleSubmit}
            disabled={loading}
            className="login-submit"
          >
            {loading ? '登录中...' : '登 录'}
          </button>
        </div>
      </div>
    </div>
  );
}
