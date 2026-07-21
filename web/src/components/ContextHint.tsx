import { useEffect, useState } from 'react';
import { Popover, Button } from 'antd';
import { InfoCircleOutlined, CloseOutlined } from '@ant-design/icons';

interface ContextHintProps {
  /** Unique key per page; persisted as `ad-research:hint:<hintId>:dismissed`. */
  hintId: string;
  /** Short title shown in the popover header. */
  title: string;
  /** Main message — keep ≤ 80 字 for one-screen readability. */
  content: React.ReactNode;
  /** Position relative to the wrapped element. */
  placement?: 'top' | 'bottom' | 'left' | 'right' | 'topLeft' | 'topRight' | 'bottomLeft' | 'bottomRight';
  /** When false, never auto-show even if not yet dismissed. */
  enabled?: boolean;
  /** Override trigger (default 'hover'). 'click' also disables the
   *  first-visit auto-open so the bubble never covers nearby controls. */
  trigger?: 'hover' | 'click';
  /** What to wrap (an inline marker; popover anchors to it). */
  children: React.ReactNode;
}

const STORAGE_PREFIX = 'ad-research:hint:';
const STORAGE_SUFFIX = ':dismissed';

function readDismissed(hintId: string): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(`${STORAGE_PREFIX}${hintId}${STORAGE_SUFFIX}`) === '1';
  } catch {
    return false;
  }
}

function writeDismissed(hintId: string) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(`${STORAGE_PREFIX}${hintId}${STORAGE_SUFFIX}`, '1');
  } catch {
    // localStorage may be disabled; fail silently — better UX than crashing.
  }
}

/**
 * ContextHint is a one-shot contextual hint bubble that wraps an inline
 * element (e.g. a page heading, a filter row, a table toolbar). It auto-shows
 * the first time the user lands on the page, and remembers dismissal via
 * localStorage so the user is never re-annoyed.
 *
 * Usage:
 *   <ContextHint hintId="screen-filter" title="先选条件再查询" content="...">
 *     <FilterToolbar>...</FilterToolbar>
 *   </ContextHint>
 */
export default function ContextHint({
  hintId,
  title,
  content,
  placement = 'top',
  enabled = true,
  trigger,
  children,
}: ContextHintProps) {
  const [dismissed, setDismissed] = useState<boolean>(() => readDismissed(hintId));
  const [autoOpen, setAutoOpen] = useState(false);

  // Auto-open once on mount if not yet dismissed. Click-triggered hints
  // never auto-open — they wait for an explicit click on the anchor.
  useEffect(() => {
    if (!enabled) return;
    if (dismissed) return;
    if (trigger === 'click') return;
    // Wait one frame so the wrapped element is rendered.
    const t = window.setTimeout(() => setAutoOpen(true), 350);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hintId]);

  // If the user later dismisses via localStorage changes (e.g. another tab),
  // honor it.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === `${STORAGE_PREFIX}${hintId}${STORAGE_SUFFIX}` && e.newValue === '1') {
        setDismissed(true);
        setAutoOpen(false);
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [hintId]);

  if (!enabled) {
    return <>{children}</>;
  }

  const handleDismiss = () => {
    setDismissed(true);
    setAutoOpen(false);
    writeDismissed(hintId);
  };

  const popoverContent = (
    <div className="context-hint">
      <div className="context-hint__title">
        <InfoCircleOutlined className="context-hint__icon" />
        <span>{title}</span>
      </div>
      <div className="context-hint__body">{content}</div>
      <div className="context-hint__footer">
        <Button
          type="text"
          size="small"
          icon={<CloseOutlined />}
          onClick={handleDismiss}
          className="context-hint__close"
        >
          知道了
        </Button>
      </div>
    </div>
  );

  return (
    <Popover
      content={popoverContent}
      placement={placement}
      trigger={trigger}
      open={dismissed ? false : autoOpen ? autoOpen : undefined}
      onOpenChange={(next) => {
        if (!next) {
          // closing without the "知道了" button should still mark dismissed
          // so the bubble doesn't keep reappearing on hover.
          setAutoOpen(false);
        }
      }}
      overlayClassName="context-hint-popover"
      overlayStyle={{ maxWidth: 'min(320px, 88vw)' }}
    >
      <span className="context-hint__anchor">{children}</span>
    </Popover>
  );
}