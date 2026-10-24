import type { ReactNode } from 'react';
import LoginBackdrop from '@/components/LoginBackdrop';

/**
 * Page chrome shared by the public registration pages (/register,
 * /register/verify): the same login backdrop, glass panels and disclaimer as
 * Login.tsx so the "创建账号" hop feels like the same place (design doc §4.1).
 *
 * The <style> block re-declares the dark-canvas token set for the light
 * theme — identical values to Login.tsx — because the register pages can be
 * loaded directly (deep link / email link) without Login ever mounting. It
 * also relaxes Login's fixed 480px panel height: the registration form is
 * taller than the login form.
 */
const REGISTER_PAGE_STYLE = `
  :root[data-theme="light"] .register-page {
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
    --login-glow: var(--accent-glow);
    --color-success-bright: #22c55e;
  }
  .register-page .login-submit:not(:disabled):active {
    transform: translateY(0) scale(0.98);
    opacity: 0.85;
    transition-duration: 0ms;
  }
  @media (prefers-reduced-motion: reduce) {
    .register-page .login-submit { transition-duration: 0.01ms; }
    .register-page .login-submit:not(:disabled):active { transform: none; }
  }
`;

interface AuthPageChromeProps {
  title: string;
  subtitle: ReactNode;
  /** Form-panel body: fields, actions, success panels. */
  children: ReactNode;
  /** Rendered in the muted hint slot under the form (e.g. back-to-login link). */
  hint?: ReactNode;
}

export default function AuthPageChrome({ title, subtitle, children, hint }: AuthPageChromeProps) {
  return (
    <div className="login-page login-page--sci-fi register-page">
      <style>{REGISTER_PAGE_STYLE}</style>
      <LoginBackdrop />

      {/* ---- Brand Panel (same identity as the login card) ---- */}
      <div className="login-glass login-brand-panel">
        <div className="login-brand-header">
          <div className="login-brand-logo">
            <div
              className="login-brand-icon-box login-brand-icon-box--logomark"
              aria-hidden="true"
            >
              E
            </div>
            <span className="login-brand-name">AlloyResearch</span>
          </div>
          <p className="login-brand-tagline">让每一次投资决策，都有数据可依</p>
        </div>
        <div className="login-brand-footer">
          <div className="login-source-status">
            <span className="login-source-name">多市场数据 · 指标 · 回测 · AI 研报</span>
          </div>
          <div>专业投资研究平台 &middot; 2026</div>
        </div>
      </div>

      {/* ---- Form Panel ---- */}
      <div className="login-glass login-form-panel">
        <div className="login-form-header">
          <h2 className="login-form-title">{title}</h2>
          <p className="login-form-subtitle">{subtitle}</p>
        </div>
        <div className="login-form register-form">{children}</div>
        {hint ? <div className="login-form-hint">{hint}</div> : null}
      </div>

      <footer className="login-disclaimer">
        本平台所有数据、信号、AI 输出仅供参考，不构成投资建议。使用即表示同意。
      </footer>
    </div>
  );
}
