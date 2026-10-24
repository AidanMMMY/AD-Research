import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { message } from 'antd';
import { AxiosError } from 'axios';
import { LockOutlined, MailOutlined } from '@ant-design/icons';
import AuthPageChrome from '@/components/auth/AuthPageChrome';
import InlineField from '@/components/auth/InlineField';
import OtpInput from '@/components/auth/OtpInput';
import PasswordPolicyHints from '@/components/auth/PasswordPolicyHints';
import { authApi } from '@/api';
import { useAuthStore } from '@/stores/auth';
import { meQueryKey } from '@/hooks/useAuth';
import { validatePassword } from '@/utils/passwordPolicy';
import { validateEmail } from '@/utils/registrationValidation';

const OTP_LENGTH = 6;
/** How long the green "reset done" moment lingers before auto-navigating. */
const SUCCESS_DWELL_MS = 1200;
const CONFIRM_MISMATCH = '两次输入的密码不一致';

type OtpStatus = 'idle' | 'error' | 'success';

interface ResetPayloadCode {
  email: string;
  code: string;
  new_password: string;
}
interface ResetPayloadToken {
  token: string;
  new_password: string;
}
type ResetPayload = ResetPayloadCode | ResetPayloadToken;

const LINK_FAIL_REASONS: Record<string, string> = {
  expired: '重置链接已过期（15 分钟内有效），重新申请一封新的即可。',
  invalid: '重置链接无效，请确认是从邮件里完整复制的地址。',
};

interface SubmitErrors {
  email: string | null;
  password: string | null;
  confirm: string | null;
}

const NO_ERRORS: SubmitErrors = { email: null, password: null, confirm: null };

/**
 * Password reset, step 2 of 2 (2026-10-25). Two entry modes:
 *  - token mode — landed from the email's primary button via
 *    /auth/reset-link 302 (?token=…&email=…): just pick a new password, no
 *    code typing; ?error=expired|invalid explains a failed link and points
 *    back to /forgot-password.
 *  - code mode — direct visit or link failure: email + 6-digit code from the
 *    message body + new password.
 * A successful reset answers with a fresh token pair (auto login — same
 * big-tech pattern as the registration verify page); we persist it exactly
 * like RegisterVerify does (setTokens → localStorage + zustand → me cache)
 * and glide into the dashboard.
 */
export default function ResetPassword() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const setTokens = useAuthStore((s) => s.setTokens);
  const [searchParams] = useSearchParams();

  const linkToken = searchParams.get('token');
  const linkError = searchParams.get('error');
  const tokenMode = Boolean(linkToken) && !linkError;

  const [email, setEmail] = useState(searchParams.get('email') ?? '');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [otpStatus, setOtpStatus] = useState<OtpStatus>('idle');
  const [submitErrors, setSubmitErrors] = useState<SubmitErrors>(NO_ERRORS);
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const navTimerRef = useRef<number | null>(null);
  useEffect(
    () => () => {
      if (navTimerRef.current !== null) window.clearTimeout(navTimerRef.current);
    },
    [],
  );

  const handleCodeChange = (value: string) => {
    setCode(value);
    setOtpStatus('idle');
    setNotice(null);
  };

  const handleReset = useCallback(async () => {
    if (submitting || otpStatus === 'success') return;
    const emailError = tokenMode ? null : validateEmail(email);
    const passwordError = validatePassword(password);
    const confirmError = confirm !== password ? CONFIRM_MISMATCH : null;
    setSubmitErrors({ email: emailError, password: passwordError, confirm: confirmError });
    if (emailError || passwordError || confirmError) {
      message.error('还有几处要改一下，看看红字提示');
      return;
    }
    if (!tokenMode && code.length !== OTP_LENGTH) {
      setNotice('先把邮件里的 6 位验证码输完。');
      return;
    }

    const payload: ResetPayload = tokenMode
      ? { token: linkToken as string, new_password: password }
      : { email: email.trim(), code, new_password: password };

    setSubmitting(true);
    setNotice(null);
    try {
      const { data } = await authApi.resetPassword(payload);
      // 重置即登录：与注册验证页同一套令牌落库方式（localStorage +
      // zustand）；setTokens 内部会顺带拉取 /auth/me 刷新 user。
      await setTokens(data.access_token, data.refresh_token);
      const user = useAuthStore.getState().user ?? data.user;
      queryClient.setQueryData(meQueryKey(useAuthStore.getState().token), { data: user });
      setOtpStatus('success');
      message.success('密码已重置，欢迎回来');
      navTimerRef.current = window.setTimeout(() => {
        navigate('/dashboard', { replace: true });
      }, SUCCESS_DWELL_MS);
    } catch (err) {
      const resp = (
        err as AxiosError<{ detail?: string; remaining_attempts?: number }>
      )?.response;
      if (resp?.status === 400 && resp.data?.detail === 'invalid code') {
        setOtpStatus('error');
        const remaining = resp.data?.remaining_attempts;
        if (typeof remaining === 'number' && remaining <= 1) {
          setNotice('验证码不对，只剩最后一次机会了，仔细核对一下邮件里的数字。');
        } else if (typeof remaining === 'number') {
          setNotice(`验证码不对，再检查一下，还剩 ${remaining} 次机会。`);
        } else {
          setNotice('重置链接无效，请从邮件里重新打开，或回到第一步重新申请。');
        }
      } else if (resp?.status === 410) {
        setNotice('验证码或链接已过期（码 10 分钟、链接 15 分钟内有效），重新申请一封新的吧。');
      } else if (resp?.status === 422) {
        setSubmitErrors((prev) => ({ ...prev, password: resp.data?.detail ?? null }));
      } else if (resp?.status === 404) {
        setNotice('找回密码功能暂未开放，请联系管理员。');
      } else if (resp?.status !== undefined && resp.status >= 500) {
        setNotice('服务器暂时开小差了，稍等几秒再按一次试试。');
      } else {
        setNotice('网络好像不太稳定，请稍后再试。');
      }
    } finally {
      setSubmitting(false);
    }
  }, [
    submitting,
    otpStatus,
    tokenMode,
    linkToken,
    email,
    code,
    password,
    confirm,
    setTokens,
    queryClient,
    navigate,
  ]);

  const linkFailText = LINK_FAIL_REASONS[linkError ?? ''] ??
    (linkError ? '链接没有生效，重新申请一封新的即可。' : null);

  // ---- Success beat: green panel, then auto-navigate. ----
  if (otpStatus === 'success') {
    return (
      <AuthPageChrome
        title="密码已重置"
        subtitle="新密码已生效，其他设备需要重新登录"
        hint={
          <>
            想重新登录一次？
            <Link to="/login" className="register-link">
              去登录
            </Link>
          </>
        }
      >
        <div className="register-success" aria-live="polite">
          <div className="register-success-badge" aria-hidden="true">
            ✓
          </div>
          <h3 className="register-success-title">设置完成</h3>
          <p className="register-success-text">正在自动登录，带你进入平台…</p>
        </div>
      </AuthPageChrome>
    );
  }

  return (
    <AuthPageChrome
      title={tokenMode ? '设置新密码' : '重置密码'}
      subtitle={
        tokenMode
          ? '验证已通过，直接设置新密码即可'
          : '输入邮件里的验证码，再设置一个新密码'
      }
      hint={
        <>
          没收到邮件？
          <Link to="/forgot-password" className="register-link register-link--accent">
            重新申请
          </Link>
        </>
      }
    >
      {linkFailText && (
        <p className="register-banner" role="status">
          {linkFailText}{' '}
          <Link to="/forgot-password" className="register-link">
            重新申请一封 →
          </Link>
        </p>
      )}

      {tokenMode ? (
        <p className="register-otp-lead">
          {email ? (
            <>
              正在为 <span className="register-otp-email">{email}</span> 设置新密码。
            </>
          ) : (
            '正在为你的账号设置新密码。'
          )}
        </p>
      ) : (
        <>
          <InlineField
            id="reset-email"
            label="注册邮箱"
            icon={<MailOutlined />}
            value={email}
            onChange={(v) => {
              setEmail(v);
              setSubmitErrors((prev) => ({ ...prev, email: null }));
            }}
            validate={validateEmail}
            error={submitErrors.email ?? undefined}
            placeholder="name@example.com"
            type="email"
            inputMode="email"
            autoComplete="email"
            maxLength={254}
          />
          <p className="register-otp-lead">
            验证码已发送到 <span className="register-otp-email">{email || '你的邮箱'}</span>
            （10 分钟内有效）
          </p>
          <OtpInput
            value={code}
            onChange={handleCodeChange}
            onSubmit={handleReset}
            status={otpStatus}
            disabled={submitting}
            focusOnMount={!email}
          />
        </>
      )}

      <InlineField
        id="reset-password"
        label="新密码"
        icon={<LockOutlined />}
        value={password}
        onChange={(v) => {
          setPassword(v);
          setSubmitErrors((prev) => ({ ...prev, password: null, confirm: null }));
        }}
        error={submitErrors.password ?? undefined}
        placeholder="新密码（至少 12 位，含字母和数字）"
        type="password"
        autoComplete="new-password"
        maxLength={64}
        onEnter={handleReset}
        extra={<PasswordPolicyHints password={password} />}
      />
      <InlineField
        id="reset-confirm"
        label="确认新密码"
        icon={<LockOutlined />}
        value={confirm}
        onChange={(v) => {
          setConfirm(v);
          setSubmitErrors((prev) => ({ ...prev, confirm: null }));
        }}
        error={submitErrors.confirm ?? undefined}
        placeholder="再输入一遍新密码"
        type="password"
        autoComplete="new-password"
        maxLength={64}
        onEnter={handleReset}
      />

      {notice && (
        <p className="register-notice" role="status">
          {notice}
        </p>
      )}
      <button
        type="button"
        className={`login-submit${submitting ? ' login-submit--loading' : ''}`}
        onClick={handleReset}
        disabled={submitting || (!tokenMode && code.length !== OTP_LENGTH)}
      >
        {submitting ? '提交中...' : '重置密码并登录'}
      </button>
    </AuthPageChrome>
  );
}
