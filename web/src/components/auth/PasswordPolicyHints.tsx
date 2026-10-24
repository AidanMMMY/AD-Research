import { validatePassword } from '@/utils/passwordPolicy';

export interface PasswordPolicyRule {
  key: string;
  label: string;
  passed: boolean;
}

export interface PasswordPolicyState {
  rules: PasswordPolicyRule[];
  /** True when validatePassword() is fully satisfied (incl. 64/UTF-8 caps). */
  allPassed: boolean;
  /** 0 = empty, 1–3 = weak → strong. 达标即绿，不做恐吓式红色。 */
  strength: 0 | 1 | 2 | 3;
  /** Code-point length (mirrors Python len(str) like passwordPolicy.ts). */
  length: number;
}

/**
 * Derive the live policy state for a password. Kept in a pure exported helper
 * so tests can assert rule math without rendering.
 */
export function getPasswordPolicyState(password: string): PasswordPolicyState {
  // Array.from counts Unicode code points, matching the backend policy and
  // utils/passwordPolicy.ts (emoji etc. count as one character).
  const length = Array.from(password).length;
  const hasLetter = /[A-Za-z]/.test(password);
  const hasDigit = /\d/.test(password);
  const hasSymbol = /[^A-Za-z0-9]/.test(password);
  const rules: PasswordPolicyRule[] = [
    { key: 'length', label: '长度 12–64 位', passed: length >= 12 && length <= 64 },
    { key: 'letter', label: '至少 1 个英文字母', passed: hasLetter },
    { key: 'digit', label: '至少 1 个数字', passed: hasDigit },
  ];
  const lengthScore = length >= 16 ? 2 : length >= 12 ? 1 : 0;
  const variety = [hasLetter, hasDigit, hasSymbol].filter(Boolean).length;
  const strength = (password
    ? Math.max(1, Math.min(3, lengthScore + (variety >= 2 ? 1 : 0)))
    : 0) as PasswordPolicyState['strength'];
  return { rules, allPassed: validatePassword(password) === null, strength, length };
}

const STRENGTH_LABELS = ['', '弱', '中', '强'];

/**
 * Live password policy hints for the registration form — same semantics as
 * the /change-password rules (utils/passwordPolicy.ts): 12–64 code points,
 * at least one ASCII letter and one digit. Adds the two-tone strength bar
 * from the design doc: fills turn from accent to success green once the
 * policy is met (达标变绿不再恐吓).
 */
export default function PasswordPolicyHints({ password }: { password: string }) {
  const { rules, allPassed, strength, length } = getPasswordPolicyState(password);
  const nearCap = length > 58 && length <= 64;
  const overCap = length > 64;

  return (
    <div className="register-policy" aria-label="密码要求">
      {/* Concise live summary for screen readers — the per-rule list below is
          static text, announcing each keystroke against it would be noise. */}
      <p className="ad-sr-only" aria-live="polite">
        {password ? (allPassed ? '密码符合要求' : '密码还不满足要求') : ''}
      </p>
      <div className="register-policy-bar">
        <div className="register-policy-strength" aria-hidden="true">
          {[1, 2, 3].map((slot) => (
            <span
              key={slot}
              className={`register-policy-seg${
                strength >= slot ? (allPassed ? ' register-policy-seg--ok' : ' register-policy-seg--on') : ''
              }`}
            />
          ))}
        </div>
        <span className="register-policy-strength-label" aria-hidden="true">
          {password ? `强度：${STRENGTH_LABELS[strength]}` : '密码强度'}
        </span>
        <span
          className={`register-policy-count${
            overCap ? ' register-policy-count--over' : nearCap ? ' register-policy-count--warn' : ''
          }`}
        >
          {length}/64
        </span>
      </div>
      <ul className="register-policy-rules">
        {rules.map((rule) => (
          <li
            key={rule.key}
            className={`register-policy-rule${rule.passed ? ' register-policy-rule--ok' : ''}`}
          >
            {rule.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
