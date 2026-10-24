import { useEffect, useState } from 'react';
import { RedoOutlined } from '@ant-design/icons';

export interface ResendButtonProps {
  /** Fires on click once the cooldown elapsed. Must not throw — surface errors itself. */
  onResend: () => Promise<void> | void;
  /** Cooldown window in seconds. Default 60 (backend resend cooldown). */
  cooldownSeconds?: number;
  /** Visually lift the control (e.g. after the code expired). */
  emphasize?: boolean;
}

const RING_RADIUS = 20;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

/**
 * 60-second resend control (design doc §4.2): a 44px round button wrapped in
 * an SVG progress ring that depletes as the cooldown burns down. When it hits
 * zero the button bounces once to say "I'm clickable now". The countdown
 * restarts after every click — the server enforces its own 60s window, so an
 * immediate re-click would only ever earn a 429.
 */
export default function ResendButton({
  onResend,
  cooldownSeconds = 60,
  emphasize = false,
}: ResendButtonProps) {
  const [secondsLeft, setSecondsLeft] = useState(cooldownSeconds);
  const [sending, setSending] = useState(false);
  const ready = secondsLeft <= 0;

  useEffect(() => {
    if (secondsLeft <= 0) return;
    const timer = window.setInterval(() => {
      setSecondsLeft((s) => (s <= 1 ? 0 : s - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [secondsLeft]);

  const handleClick = async () => {
    if (!ready || sending) return;
    setSending(true);
    try {
      await onResend();
    } catch {
      // The page-level handler owns error surfacing (toasts); swallowing here
      // keeps the unhandled-rejection noise out of the console.
    } finally {
      setSecondsLeft(cooldownSeconds);
      setSending(false);
    }
  };

  const remaining = Math.max(0, Math.min(secondsLeft, cooldownSeconds));
  const progress = ready ? 0 : remaining / cooldownSeconds;

  return (
    <div className={`resend${emphasize ? ' resend--emphasize' : ''}`}>
      <button
        type="button"
        className={`resend-btn${ready ? ' resend-btn--ready' : ''}${
          sending ? ' resend-btn--sending' : ''
        }`}
        onClick={handleClick}
        disabled={!ready || sending}
        aria-label={ready ? '重新发送验证邮件' : `冷却中，还有 ${remaining} 秒可以重新发送`}
      >
        <svg className="resend-ring" viewBox="0 0 48 48" aria-hidden="true">
          <circle className="resend-ring-track" cx="24" cy="24" r={RING_RADIUS} />
          <circle
            className="resend-ring-progress"
            cx="24"
            cy="24"
            r={RING_RADIUS}
            style={{
              strokeDasharray: RING_CIRCUMFERENCE,
              strokeDashoffset: RING_CIRCUMFERENCE * (1 - progress),
            }}
          />
        </svg>
        <span className="resend-btn-content" aria-hidden="true">
          {ready ? <RedoOutlined /> : remaining}
        </span>
      </button>
      <span className="resend-hint" aria-live="polite">
        {ready ? '没收到邮件？点这里重发' : `${remaining} 秒后可重新发送`}
      </span>
    </div>
  );
}
