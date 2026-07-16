import { useEffect, useRef } from 'react';

/**
 * WCAG 2.4.3 (Focus Order) + 2.4.7 (Focus Visible) helper.
 *
 * When a drawer / modal / popover opens we want keyboard focus to move into
 * the new surface; when it closes we want focus to return to the element
 * that triggered it (otherwise keyboard users are dumped back at the top
 * of <body> and lose context).
 *
 * Usage:
 *   const [isOpen, setIsOpen] = useState(false);
 *   useFocusRestore(isOpen);
 *
 * The hook snapshots `document.activeElement` on every transition into
 * "open". On the close transition (cleanup of the previous effect run)
 * we restore focus to that snapshot. Falls back gracefully when the
 * snapshot is null / no longer in the DOM (defensive — a quick route
 * change can unmount the trigger before we get back).
 */
export function useFocusRestore(isOpen: boolean): void {
  const triggerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    // Snapshot the currently focused element so we can return to it on close.
    const active = document.activeElement as HTMLElement | null;
    // Only snapshot real, focusable triggers — ignore body / null.
    if (active && active !== document.body) {
      triggerRef.current = active;
    }

    return () => {
      const target = triggerRef.current;
      triggerRef.current = null;
      if (!target) return;
      // Verify the trigger is still in the DOM (it may have unmounted
      // because the parent route changed while the drawer was open).
      if (typeof target.isConnected === 'boolean' && !target.isConnected) return;
      // Restore focus. Some browsers (Safari) throw if the element is not
      // focusable; guard with try/catch.
      try {
        target.focus({ preventScroll: false });
      } catch {
        /* swallow — focus restoration is best-effort */
      }
    };
  }, [isOpen]);
}