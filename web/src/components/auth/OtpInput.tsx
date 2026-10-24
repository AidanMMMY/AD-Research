import {
  useEffect,
  useRef,
  useState,
  type ClipboardEvent as ReactClipboardEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';

export interface OtpInputProps {
  /** The OTP as a plain digit string (contiguous, ≤ length). */
  value: string;
  onChange: (value: string) => void;
  /** Enter (or a full paste + Enter) submits. */
  onSubmit?: () => void;
  length?: number;
  status?: 'idle' | 'error' | 'success';
  disabled?: boolean;
  /** Focus the first empty cell on mount (named to avoid the a11y "autoFocus" lint). */
  focusOnMount?: boolean;
  groupLabel?: string;
}

/**
 * Six-cell numeric OTP input (design doc §4.2):
 * - typing auto-advances, Backspace steps back and clears,
 * - pasting a whole code splits it across the cells,
 * - Enter submits from any cell,
 * - a newly arrived 'error' status shakes the cells once,
 * - 'success' paints them green with a soft ripple before the page navigates.
 * Cells are 44px square (touch target) and mono-digit for easy proofreading.
 */
export default function OtpInput({
  value,
  onChange,
  onSubmit,
  length = 6,
  status = 'idle',
  disabled = false,
  focusOnMount = false,
  groupLabel = '邮箱验证码',
}: OtpInputProps) {
  const inputsRef = useRef<Array<HTMLInputElement | null>>([]);
  const prevStatusRef = useRef(status);
  // Set while focusCell() moves focus programmatically so the onFocus
  // "jump back to the first empty cell" guard doesn't fight the auto-advance
  // (the focus event fires before React re-renders with the new value).
  const programmaticFocusRef = useRef(false);
  const [shaking, setShaking] = useState(false);

  // Edge-triggered shake: only a fresh error→ transition restarts the
  // animation, so two failures in a row each get their own shake while the
  // parent flips status idle → error between attempts.
  useEffect(() => {
    const previous = prevStatusRef.current;
    prevStatusRef.current = status;
    if (status !== 'error' || previous === 'error') return;
    setShaking(true);
    const timer = window.setTimeout(() => setShaking(false), 480);
    return () => window.clearTimeout(timer);
  }, [status]);

  const cells = Array.from({ length }, (_, i) => value[i] ?? '');

  const focusCell = (index: number) => {
    const clamped = Math.max(0, Math.min(index, length - 1));
    const el = inputsRef.current[clamped];
    if (!el) return;
    programmaticFocusRef.current = true;
    el.focus();
    el.select();
    programmaticFocusRef.current = false;
  };

  const commitCells = (next: string[], focusIndex: number) => {
    onChange(next.join(''));
    focusCell(focusIndex);
  };

  const handleChange = (index: number, raw: string) => {
    if (disabled) return;
    const digits = raw.replace(/\D/g, '');
    const next = [...cells];
    if (!digits) {
      // The cell was emptied (cut / delete selection): remove just that slot.
      next.splice(index, 1);
      commitCells(next, index);
      return;
    }
    // Single digit fills the cell; a longer burst (IME / manager autofill)
    // distributes across the following cells like a paste.
    for (let k = 0; k < digits.length && index + k < length; k++) {
      next[index + k] = digits[k];
    }
    commitCells(next, index + digits.length);
  };

  const handleKeyDown = (index: number, e: ReactKeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      onSubmit?.();
      return;
    }
    if (e.key === 'Backspace') {
      e.preventDefault();
      if (disabled) return;
      const next = [...cells];
      if (next[index]) {
        next.splice(index, 1);
        commitCells(next, index);
      } else if (index > 0) {
        next.splice(index - 1, 1);
        commitCells(next, index - 1);
      }
      return;
    }
    if (e.key === 'Delete') {
      e.preventDefault();
      if (disabled || !cells[index]) return;
      const next = [...cells];
      next.splice(index, 1);
      commitCells(next, index);
      return;
    }
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      focusCell(index - 1);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      focusCell(index + 1);
    }
  };

  const handlePaste = (index: number, e: ReactClipboardEvent<HTMLInputElement>) => {
    if (disabled) return;
    e.preventDefault();
    const digits = e.clipboardData.getData('text').replace(/\D/g, '');
    if (!digits) return;
    const next = [...cells];
    for (let k = 0; k < digits.length && index + k < length; k++) {
      next[index + k] = digits[k];
    }
    commitCells(next, index + digits.length);
  };

  // Focus the first empty cell once on mount. Deliberately mount-only:
  // re-running on every value change would steal the caret while typing.
  useEffect(() => {
    if (focusOnMount) focusCell(Math.min(value.length, length - 1));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className={`otp-group${shaking ? ' otp-group--shake' : ''}${
        status === 'error' ? ' otp-group--error' : ''
      }${status === 'success' ? ' otp-group--success' : ''}`}
      role="group"
      aria-label={`${length} 位${groupLabel}`}
    >
      {cells.map((cell, i) => (
        <input
          key={i}
          ref={(el) => {
            inputsRef.current[i] = el;
          }}
          type="text"
          inputMode="numeric"
          autoComplete={i === 0 ? 'one-time-code' : 'off'}
          className="otp-cell"
          value={cell}
          maxLength={1}
          aria-label={`第 ${i + 1} 位${groupLabel}`}
          aria-invalid={status === 'error' ? true : undefined}
          disabled={disabled}
          onFocus={() => {
            // Clicking past the filled prefix jumps to the first empty cell
            // so the next digit lands in sequence — but never during our own
            // programmatic focus moves (see programmaticFocusRef).
            if (!programmaticFocusRef.current && i > value.length) {
              focusCell(value.length);
            }
          }}
          onChange={(e) => handleChange(i, e.target.value)}
          onKeyDown={(e) => handleKeyDown(i, e)}
          onPaste={(e) => handlePaste(i, e)}
        />
      ))}
    </div>
  );
}
