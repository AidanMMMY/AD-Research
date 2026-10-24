import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { message } from 'antd';
import { AxiosError } from 'axios';
import { MailOutlined } from '@ant-design/icons';
import AuthPageChrome from '@/components/auth/AuthPageChrome';
import InlineField from '@/components/auth/InlineField';
import OtpInput from '@/components/auth/OtpInput';
import ResendButton from '@/components/auth/ResendButton';
import { authApi } from '@/api';
import { useAuthStore } from '@/stores/auth';
import { meQueryKey } from '@/hooks/useAuth';
import { validateEmail } from '@/utils/registrationValidation';

const OTP_LENGTH = 6;
/** How long the green "verified" moment lingers before auto-navigating. */
const SUCCESS_DWELL_MS = 1200;

type OtpStatus = 'idle' | 'error' | 'success';

const LINK_FAIL_REASONS: Record<string, string> = {
  expired: '链接已过期（15 分钟内有效），可以在下面输入验证码或重发一封新的。',
  invalid: '链接无效，请确认是从邮件里完整复制的地址。',
  used: '这个链接已经被使用过了，输入验证码或重发一封新的都行。',
};

/**
 * Registration step 2: verify the email with a 6-digit code (or land here via
 * the email's magic link as /register/verify?verified=…). A successful code
 * answers with a fresh token pair — we persist it exactly the way the
 * change-password flow does (setTokens → localStorage + zustand), sync the
 * `me` query cache and glide into the dashboard after a short verified beat.
 */
export default function RegisterVerify() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const setTokens = useAuthStore((s) => s.setTokens);
  const [searchParams] = useSearchParams();
  const location = useLocation();

  const routerState = location.state as { email?: string; username?: string } | null;
  const [email, setEmail] = useState(
    routerState?.email ?? searchParams.get('email') ?? '',
  );
  const [emailDraft, setEmailDraft] = useState('');
  const [emailError, setEmailError] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [status, setStatus] = useState<OtpStatus>('idle');
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [emphasizeResend, setEmphasizeResend] = useState(false);

  const navTimerRef = useRef<number | null>(null);
  useEffect(
    () => () => {
      if (navTimerRef.current !== null) window.clearTimeout(navTimerRef.current);
    },
    [],
  );

  // Magic-link return trip: the backend 302s to ?verified=1&email=… or
  // ?verified=0&reason=…; render the outcome directly instead of the OTP form.
  const verifiedParam = searchParams.get('verified');
  const isLinkSuccess = verifiedParam === '1';
  const isLinkFailed = verifiedParam === '0';
  const linkFailText = LINK_FAIL_REASONS[searchParams.get('reason') ?? ''] ??
    '链接没有验证成功，输入验证码或重发一封新的都行。';

  const handleCodeChange = (value: string) => {
    setCode(value);
    setStatus('idle');
    setNotice(null);
  };

  const handleVerify = useCallback(async () => {
    if (code.length !== OTP_LENGTH || submitting || status === 'success') return;
    setSubmitting(true);
    setStatus('idle');
    setNotice(null);
    try {
      const { data } = await authApi.verifyRegistration({ email, code });
      // 注册即登录：与改密页同一套令牌落库方式（localStorage + zustand）；
      // setTokens 内部会顺带拉取 /auth/me 刷新 user。
      await setTokens(data.access_token, data.refresh_token);
      const user = useAuthStore.getState().user ?? data.user;
      queryClient.setQueryData(meQueryKey(useAuthStore.getState().token), { data: user });
      setStatus('success');
      message.success('邮箱验证成功，欢迎加入 AlloyResearch');
      navTimerRef.current = window.setTimeout(() => {
        navigate('/dashboard', { replace: true });
      }, SUCCESS_DWELL_MS);
    } catch (err) {
      const resp = (err as AxiosError<{ detail?: string; remaining_attempts?: number }>)?.response;
      setStatus('error');
      if (resp?.status === 410) {
        setNotice('验证码已过期（10 分钟内有效）。给你发一封新的？点下方按钮即可。');
        setEmphasizeResend(true);
      } else if (resp?.status === 400) {
        const remaining = resp.data?.remaining_attempts;
        if (remaining === 0) {
          setNotice('连续输错太多次，这个验证码已作废。给你发一封新的？点下方按钮即可。');
          setEmphasizeResend(true);
        } else if (typeof remaining === 'number' && remaining <= 1) {
          setNotice('验证码不对，只剩最后一次机会了，仔细核对一下邮件里的数字。');
          setEmphasizeResend(true);
        } else if (typeof remaining === 'number') {
          setNotice(`验证码不对，还差一位？再检查一下，还剩 ${remaining} 次机会。`);
        } else {
          setNotice('验证码不对，再检查一下邮件里的数字。');
        }
      } else if (resp?.status !== undefined && resp.status >= 500) {
        setNotice('服务器暂时开小差了，稍等几秒再按一次 Enter 试试。');
      } else {
        setNotice('网络好像不太稳定，请稍后再试。');
      }
    } finally {
      setSubmitting(false);
    }
  }, [code, submitting, status, email, setTokens, queryClient, navigate]);

  const handleResend = useCallback(async () => {
    if (!email) return;
    try {
      await authApi.resendVerification(email);
      setEmphasizeResend(false);
      setNotice(null);
      message.success('新的验证邮件已发送，请查收（也翻翻垃圾箱）');
    } catch (err) {
      const status = (err as AxiosError)?.response?.status;
      if (status === 429) {
        message.info('发送太频繁啦，稍等一分钟再试');
      } else {
        message.error('发送失败了，请稍后再试');
      }
    }
  }, [email]);

  const handleEmailCatchup = () => {
    const error = validateEmail(emailDraft);
    setEmailError(error);
    if (error) return;
    setEmail(emailDraft.trim());
  };

  const backToRegisterTarget =
    routerState?.username ?? searchParams.get('username') ?? '';
  const backToRegister = backToRegisterTarget
    ? `/register?username=${encodeURIComponent(backToRegisterTarget)}`
    : '/register';

  // ---- Magic-link success: verified, but no tokens in the redirect; the
  // user signs in with the credentials they just chose. ----
  if (isLinkSuccess) {
    return (
      <AuthPageChrome
        title="验证完成"
        subtitle="最后一步：用刚注册的账号登录"
        hint={
          <>
            想重新走一遍注册？
            <Link to={backToRegister} className="register-link">
              返回注册
            </Link>
          </>
        }
      >
        <div className="register-success" aria-live="polite">
          <div className="register-success-badge" aria-hidden="true">
            ✓
          </div>
          <h3 className="register-success-title">邮箱已验证</h3>
          <p className="register-success-text">
            {email ? `${email} 已完成验证。` : ''}
            用刚才设置的账号密码登录，就可以开始使用了。
          </p>
          <Link to="/login" className="register-primary-link">
            去登录 →
          </Link>
        </div>
      </AuthPageChrome>
    );
  }

  return (
    <AuthPageChrome
      title={isLinkFailed ? '链接没有生效' : '验证邮箱'}
      subtitle="输入邮件里的 6 位验证码，验证完成会自动登录"
      hint={
        <>
          填错邮箱了？
          <Link to={backToRegister} className="register-link">
            换个邮箱重新注册
          </Link>
        </>
      }
    >
      {isLinkFailed && (
        <p className="register-banner" role="status">
          {linkFailText}
        </p>
      )}

      {!email ? (
        <div className="register-email-catchup">
          <p className="register-otp-lead">
            直接打开了这个页面？输入你注册时用的邮箱，继续完成验证。
          </p>
          <InlineField
            id="verify-email"
            label="注册邮箱"
            icon={<MailOutlined />}
            value={emailDraft}
            onChange={(v) => {
              setEmailDraft(v);
              setEmailError(null);
            }}
            error={emailError ?? undefined}
            placeholder="name@example.com"
            type="email"
            inputMode="email"
            autoComplete="email"
            maxLength={254}
            onEnter={handleEmailCatchup}
          />
          <button type="button" className="login-submit" onClick={handleEmailCatchup}>
            继续
          </button>
        </div>
      ) : status === 'success' ? (
        <div className="register-success" aria-live="polite">
          <div className="register-success-badge" aria-hidden="true">
            ✓
          </div>
          <h3 className="register-success-title">邮箱已验证</h3>
          <p className="register-success-text">正在自动登录，带你进入平台…</p>
        </div>
      ) : (
        <>
          <p className="register-otp-lead">
            验证码已发送到 <span className="register-otp-email">{email}</span>
            （10 分钟内有效）
          </p>
          <OtpInput
            value={code}
            onChange={handleCodeChange}
            onSubmit={handleVerify}
            status={status}
            disabled={submitting}
            focusOnMount
          />
          {notice && (
            <p className="register-notice" role="status">
              {notice}
            </p>
          )}
          <button
            type="button"
            className={`login-submit${submitting ? ' login-submit--loading' : ''}`}
            onClick={handleVerify}
            disabled={code.length !== OTP_LENGTH || submitting}
          >
            {submitting ? '验证中...' : '验证并进入平台'}
          </button>
          <div className="register-resend-row">
            <ResendButton onResend={handleResend} emphasize={emphasizeResend} />
          </div>
        </>
      )}
    </AuthPageChrome>
  );
}
