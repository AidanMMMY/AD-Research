import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { message } from 'antd';
import { AxiosError } from 'axios';
import { UserOutlined, LockOutlined, StockOutlined } from '@ant-design/icons';
import { useAuthStore } from '@/stores/auth';
import AuroraBackground from '@/components/AuroraBackground';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';

const DATA_SOURCES = [
  { name: 'tushare', label: 'Tushare' },
  { name: 'fred', label: 'FRED' },
  { name: 'xueqiu', label: '雪球' },
];

const ROTATION_MS = 3000;
const CROSSFADE_MS = 220;

export default function Login() {
  const navigate = useNavigate();
  const { login, isAuthenticated } = useAuthStore();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ username: '', password: '' });
  const [sourceIndex, setSourceIndex] = useState(0);
  // Apple Design #2 Interruptibility — animate from live value, never snap.
  // The label is rendered twice (current + incoming) so we can cross-fade
  // between them instead of doing a hard swap every 3s.
  const [incomingIndex, setIncomingIndex] = useState(
    (1) % DATA_SOURCES.length,
  );
  const [isTransitioning, setIsTransitioning] = useState(false);
  const reducedMotion = usePrefersReducedMotion();

  const token = localStorage.getItem('token');
  if (isAuthenticated && token) {
    navigate('/dashboard', { replace: true });
    return null;
  }

  // Cycle through data source status indicators every 3 seconds.
  // Apple Design #14: under prefers-reduced-motion the swap is a clean cut
  // instead of a cross-fade — we keep the status dynamic (people rely on it as
  // a live signal) but skip the motion entirely.
  useEffect(() => {
    const interval = setInterval(() => {
      if (reducedMotion) {
        setSourceIndex((prev) => (prev + 1) % DATA_SOURCES.length);
        return;
      }
      // 1) start the cross-fade (fade current out + incoming in)
      setIsTransitioning(true);
      // 2) after the transition completes, swap and reset so we're ready for
      //    the next tick without a flash.
      window.setTimeout(() => {
        setSourceIndex((prev) => {
          const next = (prev + 1) % DATA_SOURCES.length;
          setIncomingIndex(next);
          return next;
        });
        setIsTransitioning(false);
      }, CROSSFADE_MS);
    }, ROTATION_MS);
    return () => clearInterval(interval);
  }, [reducedMotion]);

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
        /* #2 Interruptibility — cross-fade between data-source labels instead
           of an abrupt swap. Two stacked spans share the slot; opacity is the
           only property animated (cheap to composite, transform-free). */
        .login-page--sci-fi .login-source-name--stage {
          display: inline-block;
          transition: opacity ${CROSSFADE_MS}ms cubic-bezier(0.32, 0.72, 0, 1);
          will-change: opacity;
        }
        .login-page--sci-fi .login-source-name--incoming {
          position: absolute;
          inset-inline-start: 0;
          top: 0;
        }
        .login-page--sci-fi .login-source-name--in { opacity: 1; }
        .login-page--sci-fi .login-source-name--out { opacity: 0; }
        .login-page--sci-fi .login-source-name--stage {
          position: relative;
        }
        @media (prefers-reduced-motion: reduce) {
          .login-page--sci-fi .login-source-name--stage { transition: none; }
          .login-page--sci-fi .login-source-name--incoming { display: none; }
        }
        /* #14 Reduced transparency — fall back to a solid material. */
        @media (prefers-reduced-transparency: reduce) {
          .login-page--sci-fi .login-glass {
            backdrop-filter: none;
            -webkit-backdrop-filter: none;
            background: var(--bg-surface, #14181f);
          }
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

          {/* Cycling data source status (Apple Design #2 — cross-fade, not snap) */}
          <div className="login-source-status">
            <span className="login-source-dot" />
            <span className="login-source-label">数据源状态：</span>
            <span
              className={`login-source-name login-source-name--stage ${
                isTransitioning ? 'login-source-name--out' : 'login-source-name--in'
              }`}
              aria-live="polite"
            >
              {DATA_SOURCES[sourceIndex].label}
            </span>
            <span
              className={`login-source-name login-source-name--stage login-source-name--incoming ${
                isTransitioning ? 'login-source-name--in' : 'login-source-name--out'
              }`}
              aria-hidden="true"
            >
              {DATA_SOURCES[incomingIndex].label}
            </span>
            <span className="login-source-check">{'✅'}</span>
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
            <input
              type="text"
              placeholder="用户名"
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
              id="login-username"
              aria-autocomplete="none"
            />
          </div>

          <div className="login-input-wrapper">
            <LockOutlined className="login-input-icon" />
            <input
              type="password"
              placeholder="密码"
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
              id="login-password"
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
