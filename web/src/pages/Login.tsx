import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { message } from 'antd';
import { AxiosError } from 'axios';
import { UserOutlined, LockOutlined, StockOutlined } from '@ant-design/icons';
import { useAuthStore } from '@/stores/auth';
import ParticleBackground from '@/components/ParticleBackground';

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
    <div
      style={{
        height: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--bg-base)',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Animated particle network */}
      <ParticleBackground />

      {/* Subtle tech grid */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: `
            linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)
          `,
          backgroundSize: '60px 60px',
          pointerEvents: 'none',
          zIndex: 0,
        }}
      />

      {/* Radial vignette to keep the form readable */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: 'radial-gradient(circle at center, transparent 0%, var(--bg-base) 75%)',
          pointerEvents: 'none',
          zIndex: 0,
        }}
      />

      <div
        style={{
          width: 420,
          padding: '48px 40px',
          background: 'rgba(17, 17, 17, 0.72)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          border: '1px solid var(--card-border)',
          borderRadius: 'var(--card-radius)',
          boxShadow: 'var(--shadow-card)',
          position: 'relative',
          zIndex: 1,
        }}
      >
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div
            style={{
              width: 64,
              height: 64,
              borderRadius: 20,
              background: 'var(--accent)',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              marginBottom: 20,
            }}
          >
            <StockOutlined style={{ fontSize: 32, color: '#fff' }} />
          </div>
          <h1
            style={{
              fontSize: 24,
              fontWeight: 700,
              color: 'var(--text-primary)',
              margin: '0 0 8px 0',
              letterSpacing: '1px',
            }}
          >
            AD-Research
          </h1>
          <p style={{ fontSize: 14, color: 'var(--text-secondary)', margin: 0 }}>
            全市场数据分析与投研工具
          </p>
        </div>

        <h2 style={{ textAlign: 'center', marginBottom: 24, color: 'var(--text-primary)', fontSize: 16, fontWeight: 500 }}>
          账户密码登录
        </h2>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '12px 16px',
              background: 'var(--bg-input)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-lg)',
              transition: 'border-color 200ms ease, background-color 200ms ease',
            }}
          >
            <UserOutlined style={{ color: 'var(--text-secondary)', fontSize: 16 }} />
            <input
              type="text"
              placeholder="用户名"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
              style={{
                flex: 1,
                background: 'transparent',
                border: 'none',
                outline: 'none',
                color: 'var(--text-primary)',
                fontSize: 14,
                fontFamily: 'inherit',
              }}
            />
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '12px 16px',
              background: 'var(--bg-input)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-lg)',
              transition: 'border-color 200ms ease, background-color 200ms ease',
            }}
          >
            <LockOutlined style={{ color: 'var(--text-secondary)', fontSize: 16 }} />
            <input
              type="password"
              placeholder="密码"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
              style={{
                flex: 1,
                background: 'transparent',
                border: 'none',
                outline: 'none',
                color: 'var(--text-primary)',
                fontSize: 14,
                fontFamily: 'inherit',
              }}
            />
          </div>

          <button
            onClick={handleSubmit}
            disabled={loading}
            style={{
              width: '100%',
              padding: '14px',
              marginTop: 8,
              borderRadius: 'var(--radius-lg)',
              border: 'none',
              background: 'var(--accent)',
              color: '#fff',
              fontSize: 15,
              fontWeight: 600,
              cursor: loading ? 'not-allowed' : 'pointer',
              opacity: loading ? 0.7 : 1,
              transition: 'opacity 200ms ease, transform 200ms ease',
            }}
            onMouseEnter={(e) => {
              if (!loading) {
                e.currentTarget.style.opacity = '0.9';
                e.currentTarget.style.transform = 'translateY(-1px)';
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.opacity = '1';
              e.currentTarget.style.transform = 'translateY(0)';
            }}
          >
            {loading ? '登录中...' : '登 录'}
          </button>
        </div>
      </div>
    </div>
  );
}
