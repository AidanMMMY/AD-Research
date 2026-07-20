import { useState, useEffect } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { message } from 'antd';
import { AxiosError } from 'axios';
import { UserOutlined, LockOutlined, StockOutlined } from '@ant-design/icons';
import { useAuthStore } from '@/stores/auth';
import AuroraBackground from '@/components/AuroraBackground';

// Shape of the public /health readiness payload (see app/main.py
// ``health_check``: db/redis are "ok" or "error: <detail>" strings and the
// endpoint always answers HTTP 200, even when a component is degraded).
interface HealthReport {
  db: string;
  redis: string;
}

export default function Login() {
  const navigate = useNavigate();
  const { login, isAuthenticated } = useAuthStore();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ username: '', password: '' });
  const [health, setHealth] = useState<HealthReport | null>(null);

  const token = localStorage.getItem('token');

  // Fetch the public /health readiness probe once (no token — the login
  // page is pre-auth). On any failure we fall back to static brand copy
  // rather than pretending every data source is fine.
  useEffect(() => {
    let cancelled = false;
    fetch('/health')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<HealthReport>;
      })
      .then((data) => {
        if (!cancelled) setHealth({ db: data.db, redis: data.redis });
      })
      .catch(() => {
        if (!cancelled) setHealth(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
      // (e.g. 2026-07-01 UserResponse missing 'id' -> 500 -> user thought
      // password was wrong). See runbook 20260701 section 4-B.
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

  // Already signed in — declarative redirect instead of calling navigate()
  // during render (render-phase side effect). Placed after all hooks so the
  // hook order stays stable across renders.
  if (isAuthenticated && token) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <div className="login-page login-page--sci-fi">
      {/* Apple Design overrides scoped to the login page (global.css owns the
          base styles; these are layered on top and win by equal specificity
          + source order). See WWDC "Designing Fluid Interfaces". */}
      <style>{`
        /* #1 Response — feedback on pointer-down, not release. The base rule
           only lifts on hover; :active gives an instant, zero-duration press. */
        .login-page--sci-fi .login-submit:not(:disabled):active {
          transform: translateY(0) scale(0.98);
          opacity: 0.85;
          transition-duration: 0ms;
        }
        /* #4 Springs — critically-damped spring approximation for the hover
           lift instead of a mechanical linear-ish ease. */
        .login-page--sci-fi .login-submit {
          transition:
            opacity 0.2s ease,
            box-shadow 0.2s ease,
            transform 0.32s cubic-bezier(0.32, 0.72, 0, 1);
          will-change: transform;
        }
        /* #15 Typography — size-specific tracking: the 28px brand name gets
           tighter tracking; the 11px hint/disclaimer get positive tracking. */
        .login-page--sci-fi .login-brand-name { letter-spacing: -0.4px; }
        .login-page--sci-fi .login-form-hint,
        .login-page--sci-fi .login-disclaimer,
        .login-page--sci-fi .login-source-status { letter-spacing: 0.1px; }
        /* #11 Frame smoothness — promote the animating glass panels. */
        .login-page--sci-fi .login-glass { will-change: transform, opacity; }
        /* #14 Reduced motion — no press-scale; keep the color feedback only. */
        @media (prefers-reduced-motion: reduce) {
          .login-page--sci-fi .login-submit { transition: opacity 0.01ms; }
          .login-page--sci-fi .login-submit:not(:disabled):active {
            transform: none;
          }
        }
        /* #14 Reduced transparency — fall back to a solid dark material so
           light text remains readable. */
        @media (prefers-reduced-transparency: reduce) {
          .login-page--sci-fi .login-glass {
            backdrop-filter: none;
            -webkit-backdrop-filter: none;
            background: #14181f;
          }
        }
        /* Visual audit fixes (2026-07-16 / 2026-07-17):
           - center brand content vertically so the panel doesn't feel top-heavy
           - tighten the gap between the form title and the inputs
           - keep the login page readable in light theme by forcing dark foreground tokens
             (use the exact dark-theme values so contrast on the dark aurora/card
             background stays >= AA: text-tertiary #9CA3AF, text-muted #7B828E) */
        .login-brand-panel {
          justify-content: center;
        }
        .login-brand-footer {
          margin-top: auto;
        }
        .login-form-header {
          margin-bottom: 16px;
        }
        :root[data-theme="light"] .login-page--sci-fi {
          --text-primary: #E6EDF3;
          --text-secondary: #A0A0A0;
          --text-tertiary: #9CA3AF;
          --text-muted: #7B828E;
          --text-on-accent: #0D1117;
          --accent: #60A5FA;
          --accent-hover: #93BBFD;
          --accent-dim: rgba(96, 165, 250, 0.12);
          --accent-soft: rgba(96, 165, 250, 0.12);
          --accent-border: rgba(96, 165, 250, 0.25);
          --accent-glow: rgba(96, 165, 250, 0.15);
          --color-success-bright: #22c55e;
        }
      `}</style>
      <AuroraBackground />

      {/* ---- Brand Panel ---- */}
      <div className="login-glass login-brand-panel">
        <div className="login-brand-header">
          <div className="login-brand-logo">
            <div className="login-brand-icon-box">
              <StockOutlined />
            </div>
            <span className="login-brand-name">AD-Research</span>
          </div>
          <p className="login-brand-tagline">
            让每一次投资决策，都有数据可依
          </p>

          {/* Live backend health from the public /health endpoint (no token).
              On request failure we show plain brand copy instead — never a
              fake "all good" status line. */}
          <div className="login-source-status" aria-live="polite">
            {health ? (
              <>
                <span className="login-source-dot" />
                <span className="login-source-label">服务状态：</span>
                <span className="login-source-name">
                  数据库 {health.db === 'ok' ? '✅' : '⚠️'}
                  {' · '}
                  缓存 {health.redis === 'ok' ? '✅' : '⚠️'}
                </span>
              </>
            ) : (
              <span className="login-source-name">
                多市场数据 · 指标 · 回测 · AI 研报
              </span>
            )}
          </div>
        </div>

        <div className="login-brand-footer">
          专业投资研究平台 &middot; 2026
        </div>
      </div>

      {/* ---- Form Panel ---- */}
      <div className="login-glass login-form-panel">
        <div className="login-form-header">
          <h2 className="login-form-title">登录</h2>
          <p className="login-form-subtitle">欢迎回来</p>
        </div>

        <div className="login-form">
          <div className="login-input-wrapper">
            <UserOutlined className="login-input-icon" />
            {/* a11y: explicit aria-label since the visual placeholder
                is not a sufficient label for screen readers
                (review-a11y-mobile P0-1). */}
            <label htmlFor="login-username" className="ad-sr-only">
              用户名
            </label>
            <input
              id="login-username"
              type="text"
              placeholder="用户名"
              aria-label="用户名"
              aria-required="true"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
              className="login-input"
              // Disable browser + password-manager autofill highlight.
              // The yellow/blue tint is also suppressed in global.css via
              // `:-webkit-autofill`, but these attributes tell the manager
              // not to surface saved credentials here at all. The username
              // and password fields share the same suppress list because
              // saved credentials almost always come as a pair.
              autoComplete="off"
              spellCheck={false}
              autoCorrect="off"
              autoCapitalize="off"
              inputMode="text"
              data-form-type="other"
              data-1p-ignore
              data-bwignore
              data-kp-ignore
              data-lpignore="true"
              data-dashlane-ignore
              name="login-username-no-autofill"
              aria-autocomplete="none"
            />
          </div>

          <div className="login-input-wrapper">
            <LockOutlined className="login-input-icon" />
            {/* a11y: explicit aria-label since visual placeholder is not a
                sufficient label for screen readers
                (review-a11y-mobile P0-1). */}
            <label htmlFor="login-password" className="ad-sr-only">
              密码
            </label>
            <input
              id="login-password"
              type="password"
              placeholder="密码"
              aria-label="密码"
              aria-required="true"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
              className="login-input"
              // `new-password` is the strongest standard signal Chrome 80+
              // honours — it tells the browser this is a brand-new credential
              // (not an existing one it should pre-fill). Combined with
              // `data-form-type="other"` (Dashlane), `data-1p-ignore`,
              // `data-bwignore`, `data-kp-ignore`, `data-lpignore` we cover
              // every major password manager. The autofill background tint
              // is suppressed in global.css regardless.
              autoComplete="new-password"
              spellCheck={false}
              autoCorrect="off"
              autoCapitalize="off"
              data-form-type="other"
              data-1p-ignore
              data-bwignore
              data-kp-ignore
              data-lpignore="true"
              data-dashlane-ignore
              name="login-password-no-autofill"
              aria-autocomplete="none"
            />
          </div>

          <button
            onClick={handleSubmit}
            disabled={loading}
            className={`login-submit${loading ? ' login-submit--loading' : ''}`}
          >
            {loading ? '登录中...' : '登 录'}
          </button>
        </div>

        <div className="login-form-hint">
          按 Enter 登录 &middot; 忘记密码请联系管理员
        </div>
      </div>

      <footer className="login-disclaimer">
        本平台所有数据、信号、AI 输出仅供参考，不构成投资建议。使用即表示同意。
      </footer>
    </div>
  );
}
