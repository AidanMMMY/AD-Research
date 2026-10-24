import { useCallback, useRef, useState } from 'react';
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { message } from 'antd';
import { AxiosError } from 'axios';
import { LockOutlined, MailOutlined, UserOutlined } from '@ant-design/icons';
import AuthPageChrome from '@/components/auth/AuthPageChrome';
import InlineField from '@/components/auth/InlineField';
import PasswordPolicyHints from '@/components/auth/PasswordPolicyHints';
import { authApi } from '@/api';
import { useAuthStore } from '@/stores/auth';
import { validatePassword } from '@/utils/passwordPolicy';
import {
  USERNAME_RULE_HINT,
  validateEmail,
  validateUsername,
} from '@/utils/registrationValidation';

interface SubmitErrors {
  email: string | null;
  username: string | null;
  password: string | null;
}

interface UsernameCheck {
  available: boolean | null;
  suggestions: string[] | null;
}

const NO_ERRORS: SubmitErrors = { email: null, username: null, password: null };
const NO_CHECK: UsernameCheck = { available: null, suggestions: null };

/**
 * Self-service registration, step 1 of 3 (docs/dev-notes/
 * 20261025-self-registration-design.md §1/§4): one screen, three fields, all
 * validated live (400ms debounce). On 201 the user moves to /register/verify
 * carrying their email + username via router state so the verify page can
 * offer "换个邮箱重新注册" without a retyping round-trip.
 */
export default function Register() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { isAuthenticated } = useAuthStore();

  // ?username= carries the name back from the verify page's "换个邮箱重新注册".
  const initialUsername =
    (location.state as { username?: string } | null)?.username ??
    searchParams.get('username') ??
    '';
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState(initialUsername);
  const [password, setPassword] = useState('');
  const [usernameCheck, setUsernameCheck] = useState<UsernameCheck>(NO_CHECK);
  const [submitErrors, setSubmitErrors] = useState<SubmitErrors>(NO_ERRORS);
  const [loading, setLoading] = useState(false);

  const usernameRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  // Async username validator for InlineField: format gate first, then the
  // check-username probe. Stores availability + suggestions for the submit
  // gate and the suggestion chips; fails open on probe errors (the server
  // re-checks on submit, a flaky probe must not block anyone).
  const checkUsernameAvailability = useCallback(
    async (value: string): Promise<string | null> => {
      const syncError = validateUsername(value);
      if (syncError) {
        setUsernameCheck(NO_CHECK);
        return syncError;
      }
      try {
        const { data } = await authApi.checkUsername(value);
        setUsernameCheck({ available: data.available, suggestions: data.suggestions ?? null });
        if (data.available) return null;
        return data.suggestions?.length
          ? `这个名字已经被占用了，试试 ${data.suggestions[0]}？`
          : '这个名字已经被占用了';
      } catch {
        return null;
      }
    },
    [],
  );

  const handleUsernameChange = (value: string) => {
    setUsername(value);
    // Availability of the previous name no longer applies.
    setUsernameCheck(NO_CHECK);
    if (submitErrors.username) setSubmitErrors((prev) => ({ ...prev, username: null }));
  };

  const applySuggestion = (suggestion: string) => {
    setUsername(suggestion);
    setUsernameCheck(NO_CHECK);
    setSubmitErrors((prev) => ({ ...prev, username: null }));
    // InlineField re-runs the debounced probe on the new value automatically.
  };

  const handleSubmit = async () => {
    const emailError = validateEmail(email);
    const usernameError = validateUsername(username);
    const passwordError = validatePassword(password);
    const taken = usernameError == null && usernameCheck.available === false;
    setSubmitErrors({
      email: emailError,
      username: usernameError ?? (taken ? '这个名字已经被占用了' : null),
      password: passwordError,
    });
    if (emailError || usernameError || passwordError || taken) {
      message.error('还有几处要改一下，看看红字提示');
      return;
    }
    setLoading(true);
    try {
      await authApi.register({ email, username, password });
      // 防枚举：邮箱已注册也回 201，所以这里统一按"验证邮件已发出"继续。
      navigate('/register/verify', { state: { email, username } });
    } catch (err) {
      const status = (err as AxiosError)?.response?.status;
      const detail = (err as AxiosError<{ detail?: string }>)?.response?.data?.detail;
      if (status === 400 && detail === 'username already taken') {
        // Live probe missed it (fail-open or a race) — the server is the
        // source of truth; surface it inline under the username field.
        setSubmitErrors((prev) => ({ ...prev, username: '这个名字已经被占用了' }));
        message.error('这个名字已经被占用了，换一个试试');
      } else if (status !== undefined && status >= 500) {
        message.error('服务器开小差了，请稍后再试');
      } else {
        message.error('注册没有成功，请稍后再试');
      }
    } finally {
      setLoading(false);
    }
  };

  const token = localStorage.getItem('token');
  // Already signed in — same declarative redirect as the login page.
  if (isAuthenticated && token) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <AuthPageChrome
      title="创建账号"
      subtitle="注册 → 验证邮箱 → 直接开始使用"
      hint={
        <>
          已经有账号了？
          <Link to="/login" className="register-link register-link--accent">
            直接登录
          </Link>
        </>
      }
    >
      <InlineField
        id="register-email"
        label="邮箱"
        icon={<MailOutlined />}
        value={email}
        onChange={(v) => {
          setEmail(v);
          if (submitErrors.email) setSubmitErrors((prev) => ({ ...prev, email: null }));
        }}
        validate={validateEmail}
        error={submitErrors.email ?? undefined}
        placeholder="name@example.com"
        type="email"
        inputMode="email"
        autoComplete="email"
        maxLength={254}
        showValidMark
        onEnter={() => usernameRef.current?.focus()}
      />

      <InlineField
        id="register-username"
        label="用户名"
        icon={<UserOutlined />}
        value={username}
        onChange={handleUsernameChange}
        validate={checkUsernameAvailability}
        error={submitErrors.username ?? undefined}
        placeholder={`用户名（${USERNAME_RULE_HINT}）`}
        autoComplete="username"
        showValidMark
        onEnter={() => passwordRef.current?.focus()}
        ref={usernameRef}
        extra={
          usernameCheck.available === false && usernameCheck.suggestions?.length ? (
            <div className="register-suggestions">
              <span className="register-suggestions-label">试试这些：</span>
              {usernameCheck.suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  className="register-suggestion-chip"
                  onClick={() => applySuggestion(suggestion)}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          ) : undefined
        }
      />

      <InlineField
        id="register-password"
        label="密码"
        icon={<LockOutlined />}
        value={password}
        onChange={(v) => {
          setPassword(v);
          if (submitErrors.password) setSubmitErrors((prev) => ({ ...prev, password: null }));
        }}
        error={submitErrors.password ?? undefined}
        placeholder="密码（至少 12 位，含字母和数字）"
        type="password"
        autoComplete="new-password"
        maxLength={64}
        ref={passwordRef}
        onEnter={handleSubmit}
        extra={<PasswordPolicyHints password={password} />}
      />

      <button
        type="button"
        onClick={handleSubmit}
        disabled={loading}
        className={`login-submit${loading ? ' login-submit--loading' : ''}`}
      >
        {loading ? '创建中...' : '创建账号'}
      </button>
    </AuthPageChrome>
  );
}
