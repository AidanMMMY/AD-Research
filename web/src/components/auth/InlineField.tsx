import {
  forwardRef,
  useEffect,
  useRef,
  useState,
  type InputHTMLAttributes,
  type ReactNode,
} from 'react';

export interface InlineFieldProps {
  /** Input id — also used to derive the aria-describedby target. */
  id: string;
  /** Visible-to-screen-readers label (visually hidden, the icon is the visual cue). */
  label: string;
  /** Leading icon, e.g. <UserOutlined />. */
  icon: ReactNode;
  value: string;
  onChange: (value: string) => void;
  /**
   * Debounced live validator. Returns a human-friendly error message or null.
   * May be async (e.g. the check-username probe). Runs `debounceMs` after the
   * last keystroke; an empty value clears the message immediately.
   */
  validate?: (value: string) => string | null | Promise<string | null>;
  /**
   * Externally controlled error (typically a server field error after submit).
   * Takes precedence over internal validation. Pass null for "no error".
   */
  error?: string | null;
  placeholder?: string;
  type?: InputHTMLAttributes<HTMLInputElement>['type'];
  /** Debounce window for `validate`. Default 400ms (design doc §1). */
  debounceMs?: number;
  /** Always-rendered extra content under the field (suggestions, policy hints). */
  extra?: ReactNode;
  /** Enter presses chain to the next action (keyboard-all-the-way UX). */
  onEnter?: () => void;
  /** Show a subtle "✓ 可用" mark once the validator passes. */
  showValidMark?: boolean;
  inputMode?: InputHTMLAttributes<HTMLInputElement>['inputMode'];
  autoComplete?: string;
  maxLength?: number;
}

/**
 * Login-styled input with inline, debounced validation feedback.
 * Renders the shared .login-input-wrapper chrome so register pages stay
 * visually identical to the login card; error/success copy sits directly
 * under the field with aria-live so screen readers hear every outcome.
 */
const InlineField = forwardRef<HTMLInputElement, InlineFieldProps>(function InlineField(
  {
    id,
    label,
    icon,
    value,
    onChange,
    validate,
    error,
    placeholder,
    type = 'text',
    debounceMs = 400,
    extra,
    onEnter,
    showValidMark = false,
    inputMode,
    autoComplete,
    maxLength,
  },
  ref,
) {
  const [internalError, setInternalError] = useState<string | null>(null);
  const [valid, setValid] = useState(false);

  // Keep the latest validator in a ref so the debounce effect only re-runs
  // on value changes while still invoking the freshest closure.
  const validateRef = useRef(validate);
  useEffect(() => {
    validateRef.current = validate;
  }, [validate]);

  useEffect(() => {
    if (!validateRef.current) return;
    if (!value) {
      setInternalError(null);
      setValid(false);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      const result = await validateRef.current?.(value);
      if (cancelled) return;
      setInternalError(result ?? null);
      setValid(result == null);
    }, debounceMs);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [value, debounceMs]);

  const shownError = error !== undefined ? error : internalError;
  const showOkMark = showValidMark && valid && !shownError && !!value;
  const hasBelow = Boolean(shownError || showOkMark || extra);

  return (
    <div
      className={`register-field${shownError ? ' register-field--error' : ''}${
        showOkMark ? ' register-field--valid' : ''
      }`}
    >
      <div className="login-input-wrapper">
        <span className="login-input-icon" aria-hidden="true">
          {icon}
        </span>
        <label htmlFor={id} className="ad-sr-only">
          {label}
        </label>
        <input
          ref={ref}
          id={id}
          type={type}
          value={value}
          placeholder={placeholder}
          className="login-input"
          aria-label={label}
          aria-required="true"
          aria-invalid={shownError ? true : undefined}
          aria-describedby={hasBelow ? `${id}-msg` : undefined}
          inputMode={inputMode}
          autoComplete={autoComplete}
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          maxLength={maxLength}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              onEnter?.();
            }
          }}
        />
      </div>
      {hasBelow && (
        <div id={`${id}-msg`} className="register-field-msg" aria-live="polite">
          {shownError ? (
            <p className="register-field-error">{shownError}</p>
          ) : showOkMark ? (
            <p className="register-field-ok">✓ 可用</p>
          ) : null}
          {extra}
        </div>
      )}
    </div>
  );
});

export default InlineField;
