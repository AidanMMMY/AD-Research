import { useEffect, useId, useState } from 'react';
import type { ReactNode } from 'react';
import { Button } from 'antd';
import { CloseOutlined } from '@ant-design/icons';
import { useFocusRestore } from '@/hooks/useFocusRestore';
import './DetailDrawer.css';

/**
 * How long the exit animation is allowed to run before the drawer
 * unmounts. Mirrors ``--spring-response`` (0.35s) with a small buffer,
 * matching the Cninfo page drawer this component generalizes.
 */
const EXIT_ANIMATION_MS = 360;

interface DetailDrawerProps {
  open: boolean;
  onClose: () => void;
  /** Visible header title; also wired up as the dialog label. */
  title?: ReactNode;
  /** Accessible label used when no visible ``title`` is provided. */
  ariaLabel?: string;
  /** Optional pinned footer (e.g. action buttons). */
  footer?: ReactNode;
  children: ReactNode;
}

/**
 * Shared right-side detail drawer: overlay scrim + sliding panel with
 * interruptible spring enter/exit motion (the same pattern the
 * CninfoReports page pioneered), ESC / overlay-click dismissal, body
 * scroll locking and focus restoration. Reduced-motion users get a
 * plain cross-fade (see DetailDrawer.css).
 *
 * Layout primitives (overlay position, panel width/padding) come from
 * the global ``.ad-detail-drawer*`` rules; this component only adds the
 * motion layer and the interaction shell.
 */
export default function DetailDrawer({
  open,
  onClose,
  title,
  ariaLabel,
  footer,
  children,
}: DetailDrawerProps) {
  const titleId = useId();

  // Keep mounted during the exit animation so the drawer can reverse
  // its entrance (Apple "Spatial consistency" — enter and exit must
  // share the same axis). ``mounted`` is true from the moment ``open``
  // flips on and stays true for one animation window after it flips
  // back off, so the reverse slide-out completes before unmount.
  const [mounted, setMounted] = useState(open);
  const [leaving, setLeaving] = useState(false);
  // ``entering`` is only true for the first painted frame(s): the drawer
  // mounts with translateX(100%) (the --entering modifier), then the class
  // is dropped on the next frame so the spring transition carries it to
  // translateX(0). Without this removal the modifier (same specificity as
  // the base rule, defined later) kept the drawer off-screen forever.
  const [entering, setEntering] = useState(open);
  useEffect(() => {
    if (open) {
      setMounted(true);
      setLeaving(false);
      setEntering(true);
      return;
    }
    if (!mounted) return;
    setLeaving(true);
    const t = setTimeout(() => {
      setMounted(false);
      setLeaving(false);
      setEntering(false);
    }, EXIT_ANIMATION_MS);
    return () => clearTimeout(t);
  }, [open, mounted]);

  // Wait until the entering styles have been painted (double rAF), then
  // remove the --entering class so the drawer slides into place.
  useEffect(() => {
    if (!mounted || !entering || leaving) return;
    let inner = 0;
    const outer = requestAnimationFrame(() => {
      inner = requestAnimationFrame(() => setEntering(false));
    });
    return () => {
      cancelAnimationFrame(outer);
      cancelAnimationFrame(inner);
    };
  }, [mounted, entering, leaving]);

  // ESC closes the drawer while it is open.
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  // Lock background scrolling while the drawer is on screen.
  useEffect(() => {
    if (!mounted) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [mounted]);

  // WCAG 2.4.3: return keyboard focus to the triggering element on close.
  useFocusRestore(open);

  if (!mounted) return null;

  const drawerClasses = [
    'ad-detail-drawer',
    leaving
      ? 'ad-detail-drawer--leaving'
      : entering
        ? 'ad-detail-drawer--entering'
        : '',
  ].join(' ');
  const overlayClasses = [
    'ad-detail-drawer-overlay',
    leaving ? 'ad-detail-drawer-overlay--leaving' : '',
  ].join(' ');

  return (
    // Close only when the scrim itself is clicked (``e.target`` is the
    // overlay); clicks inside the panel bubble up with a different
    // target and are ignored — no stopPropagation needed on the panel.
    <div
      className={overlayClasses}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={drawerClasses}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        aria-label={title ? undefined : ariaLabel}
      >
        <div className="ad-detail-drawer__header">
          {title ? (
            <h3 id={titleId} className="ad-detail-drawer__title">
              {title}
            </h3>
          ) : (
            <span className="ad-flex-1" />
          )}
          <Button
            type="text"
            icon={<CloseOutlined />}
            onClick={onClose}
            aria-label="关闭"
            className="ad-detail-drawer__close"
          />
        </div>
        <div className="ad-detail-drawer__content">{children}</div>
        {footer ? (
          <div className="ad-detail-drawer__footer">{footer}</div>
        ) : null}
      </div>
    </div>
  );
}
