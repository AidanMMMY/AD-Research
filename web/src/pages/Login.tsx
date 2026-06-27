import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { message } from 'antd';
import { UserOutlined, LockOutlined, StockOutlined } from '@ant-design/icons';
import { useAuthStore } from '@/stores/auth';

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
    } catch {
      message.error('登录失败，请检查用户名和密码');
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
        background: 'linear-gradient(180deg, var(--bg-base) 0%, var(--bg-elevated) 100%)',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          width: 420,
          padding: '48px 40px',
          background: 'var(--card-bg)',
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
              transition: 'all 200ms',
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
              transition: 'all 200ms',
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
              transition: 'all 200ms',
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
