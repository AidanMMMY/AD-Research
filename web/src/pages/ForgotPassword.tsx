import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { message } from 'antd';
import { AxiosError } from 'axios';
import { MailOutlined } from '@ant-design/icons';
import AuthPageChrome from '@/components/auth/AuthPageChrome';
import InlineField from '@/components/auth/InlineField';
import ResendButton from '@/components/auth/ResendButton';
import { authApi } from '@/api';
import { validateEmail } from '@/utils/registrationValidation';

/**
 * Password reset, step 1 of 2 (2026-10-25): submit the account email, then
 * wait for the reset message. The backend answers 202 for every well-formed
 * address (anti-enumeration), so the copy stays neutral: "if this address
 * has an account, the mail is on its way". Resend uses the same 60s ring
 * countdown as the registration verify page.
 */
export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [emailError, setEmailError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  const request = useCallback(async (address: string) => {
    try {
      await authApi.forgotPassword(address);
      return true;
    } catch (err) {
      const status = (err as AxiosError)?.response?.status;
      if (status === 429) {
        message.info('发送太频繁啦，稍等一分钟再试');
      } else if (status !== undefined && status >= 500) {
        message.error('服务器开小差了，请稍后再试');
      } else {
        message.error('发送失败了，请稍后再试');
      }
      return false;
    }
  }, []);

  const handleSubmit = async () => {
    if (loading) return;
    const error = validateEmail(email);
    setEmailError(error);
    if (error) return;
    setLoading(true);
    try {
      // 防枚举：未注册邮箱同样回 202，这里统一按"邮件已发出"继续。
      if (await request(email.trim())) {
        setSent(true);
        message.success('重置邮件已发送，请查收（也翻翻垃圾箱）');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleResend = useCallback(async () => {
    await request(email.trim());
  }, [email, request]);

  return (
    <AuthPageChrome
      title={sent ? '去邮箱查收' : '忘记密码'}
      subtitle={sent ? '重置链接和验证码都在那封邮件里' : '输入注册邮箱，我们给你发一封重置邮件'}
      hint={
        <>
          想起来了？
          <Link to="/login" className="register-link register-link--accent">
            返回登录
          </Link>
        </>
      }
    >
      {sent ? (
        <div className="register-success" aria-live="polite">
          <div className="register-success-badge" aria-hidden="true">
            ✉
          </div>
          <h3 className="register-success-title">重置邮件已发送</h3>
          <p className="register-success-text">
            如果 <span className="register-otp-email">{email}</span>{' '}
            注册过账号，几分钟内就会收到「重置密码」邮件（也翻翻垃圾箱）。链接 15
            分钟、验证码 10 分钟内有效。
          </p>
          <div className="register-resend-row">
            <ResendButton onResend={handleResend} />
          </div>
          <button type="button" className="login-submit" onClick={() => setSent(false)}>
            换个邮箱再试
          </button>
        </div>
      ) : (
        <>
          <InlineField
            id="forgot-email"
            label="注册邮箱"
            icon={<MailOutlined />}
            value={email}
            onChange={(v) => {
              setEmail(v);
              setEmailError(null);
            }}
            validate={validateEmail}
            error={emailError ?? undefined}
            placeholder="name@example.com"
            type="email"
            inputMode="email"
            autoComplete="email"
            maxLength={254}
            showValidMark
            onEnter={handleSubmit}
          />
          <button
            type="button"
            onClick={handleSubmit}
            disabled={loading}
            className={`login-submit${loading ? ' login-submit--loading' : ''}`}
          >
            {loading ? '发送中...' : '发送重置邮件'}
          </button>
        </>
      )}
    </AuthPageChrome>
  );
}
