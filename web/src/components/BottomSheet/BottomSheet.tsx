import './BottomSheet.css';

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';
import type {
  KeyboardEvent as ReactKeyboardEvent,
  PointerEvent as ReactPointerEvent,
  ReactNode,
} from 'react';
import { Button } from 'antd';
import { CloseOutlined } from '@ant-design/icons';
import { useFocusRestore } from '@/hooks/useFocusRestore';

export type SheetSnap = 'peek' | 'half' | 'full';

/** Visible height of each detent, as a fraction of the viewport height. */
const SNAP_FRACTION: Record<SheetSnap, number> = {
  peek: 0.32,
  half: 0.6,
  full: 0.92,
};

/**
 * How long the exit slide is allowed to run before unmount. Mirrors
 * ``--spring-response`` (350ms) with a small buffer — same contract as
 * DetailDrawer's EXIT_ANIMATION_MS.
 */
const EXIT_ANIMATION_MS = 380;

/**
 * Velocity projection window (ms): on pointer-up the release velocity is
 * extrapolated this far into the future before picking the nearest
 * detent, so a fast fling crosses detent boundaries instead of snapping
 * back to where the finger left the glass.
 */
const FLING_PROJECT_MS = 160;

/** Drag distance (px) below which a pointer-up counts as a tap. */
const TAP_SLOP_PX = 4;

export interface BottomSheetProps {
  open: boolean;
  onClose: () => void;
  /** Visible header title; also wired up as the dialog label. */
  title?: ReactNode;
  /** Accessible label used when no visible ``title`` is provided. */
  ariaLabel?: string;
  /**
   * Detents offered, ascending by visible height. Default
   * ``['half', 'full']``. Include ``'peek'`` for glanceable surfaces.
   */
  snaps?: SheetSnap[];
  /** Detent the sheet opens at. Default: first entry of ``snaps``. */
  initialSnap?: SheetSnap;
  onSnapChange?: (snap: SheetSnap) => void;
  /** Optional pinned footer (e.g. primary action row). */
  footer?: ReactNode;
  children: ReactNode;
}

interface DragState {
  pointerId: number;
  startY: number;
  startTranslate: number;
  lastY: number;
  lastT: number;
  /** Exponentially-smoothed release velocity, px/ms (positive = down). */
  velocity: number;
  moved: boolean;
}

/**
 * Mobile bottom sheet with three detents (peek / half / full), pointer
 * drag (touch + mouse via Pointer Events + setPointerCapture),
 * swipe-down dismissal, scrim, ESC close, body scroll lock and focus
 * restoration. Rendered through a portal so a transformed/overflowing
 * ancestor can never break ``position: fixed``.
 *
 * Drag ownership: the gesture starts only from the drag zone (grabber +
 * header); the body keeps native ``pan-y`` scrolling, which sidesteps
 * the classic nested-scroll conflict.
 *
 * Callers must gate rendering on ``useIsMobile()`` — the CSS hides the
 * sheet ≥768px as a safety net.
 */
export default function BottomSheet({
  open,
  onClose,
  title,
  ariaLabel,
  snaps,
  initialSnap,
  onSnapChange,
  footer,
  children,
}: BottomSheetProps) {
  const titleId = useId();
  const detents = useMemo<SheetSnap[]>(
    () => (snaps && snaps.length > 0 ? snaps : ['half', 'full']),
    [snaps],
  );
  const initialIndex = Math.max(
    0,
    initialSnap ? detents.indexOf(initialSnap) : 0,
  );

  const sheetRef = useRef<HTMLDivElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<DragState | null>(null);
  /** Set when a drag ends so the trailing click on the grabber is
   *  swallowed (pointerup → click would otherwise cycle a detent). */
  const suppressClickRef = useRef(false);
  /** Current translateY in px — source of truth between renders. */
  const translateRef = useRef(0);

  const [mounted, setMounted] = useState(open);
  const [leaving, setLeaving] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [snapIndex, setSnapIndex] = useState(initialIndex);

  const sheetHeight = useCallback(() => {
    return sheetRef.current?.offsetHeight ?? window.innerHeight * SNAP_FRACTION.full;
  }, []);

  const translateFor = useCallback(
    (snap: SheetSnap) => {
      const visible = window.innerHeight * SNAP_FRACTION[snap];
      return Math.max(0, sheetHeight() - visible);
    },
    [sheetHeight],
  );

  const setTranslate = useCallback((px: number) => {
    translateRef.current = px;
    const el = sheetRef.current;
    if (el) el.style.transform = `translateY(${px}px)`;
  }, []);

  /**
   * The outer sheet is always 92dvh tall and parks below the fold via
   * translateY; the inner content column is exactly one detent tall and
   * hugs the sheet top, so the footer is always inside the visible
   * region at rest. Detent changes animate transform + height together.
   */
  const setContentHeight = useCallback((px: number) => {
    const el = contentRef.current;
    if (el) el.style.height = `${px}px`;
  }, []);

  const applyDetent = useCallback(
    (snap: SheetSnap) => {
      setTranslate(translateFor(snap));
      setContentHeight(window.innerHeight * SNAP_FRACTION[snap]);
    },
    [setTranslate, setContentHeight, translateFor],
  );

  // ---- Open / close lifecycle (same enter/exit pattern as DetailDrawer) ----
  useEffect(() => {
    if (open) {
      setLeaving(false);
      setSnapIndex(initialIndex);
      if (mounted) {
        // Re-open inside the exit window: the node is still mounted and
        // parked off-screen — glide back to the detent.
        const el = sheetRef.current;
        if (el) el.style.transition = '';
        const raf = requestAnimationFrame(() =>
          applyDetent(detents[initialIndex] ?? detents[0]),
        );
        return () => cancelAnimationFrame(raf);
      }
      setMounted(true);
      return;
    }
    if (!mounted) return;
    setLeaving(true);
    // Slide fully below the viewport; the CSS transition carries it.
    setTranslate(sheetHeight() + 24);
    const t = setTimeout(() => {
      setMounted(false);
      setLeaving(false);
    }, EXIT_ANIMATION_MS);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Entrance: mount parked off-screen (transition suppressed), then on
  // the next painted frame glide to the initial detent (double rAF —
  // the same trick DetailDrawer uses for its --entering class).
  useEffect(() => {
    if (!mounted || leaving) return;
    const el = sheetRef.current;
    if (!el) return;
    if (!open) return;
    el.style.transition = 'none';
    setTranslate(sheetHeight() + 24);
    setContentHeight(window.innerHeight * SNAP_FRACTION[detents[snapIndex] ?? detents[0]]);
    let inner = 0;
    const outer = requestAnimationFrame(() => {
      inner = requestAnimationFrame(() => {
        el.style.transition = '';
        applyDetent(detents[snapIndex] ?? detents[0]);
      });
    });
    return () => {
      cancelAnimationFrame(outer);
      cancelAnimationFrame(inner);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mounted]);

  // Re-apply the detent translate when the viewport is resized (e.g.
  // URL-bar collapse changes 100dvh mid-session).
  useEffect(() => {
    if (!mounted || leaving) return;
    const onResize = () => {
      if (dragRef.current) return;
      applyDetent(detents[snapIndex] ?? detents[0]);
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [mounted, leaving, snapIndex, detents, applyDetent]);

  // ESC closes the sheet while it is open.
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

  // Lock background scrolling while the sheet is on screen.
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

  // ---- Detent changes ----
  const goToSnap = useCallback(
    (index: number) => {
      const clamped = Math.max(0, Math.min(detents.length - 1, index));
      setSnapIndex(clamped);
      applyDetent(detents[clamped]);
      onSnapChange?.(detents[clamped]);
    },
    [detents, onSnapChange, applyDetent],
  );

  // ---- Pointer drag (touch + mouse) ----
  const onPointerDown = (e: ReactPointerEvent<HTMLElement>) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    // Interactive children inside the header (close button, links) keep
    // their native behaviour instead of starting a drag.
    if (
      (e.target as HTMLElement).closest(
        'button:not(.bottom-sheet__grabber), a, input, select, textarea, [data-no-drag]',
      )
    ) {
      return;
    }
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = {
      pointerId: e.pointerId,
      startY: e.clientY,
      startTranslate: translateRef.current,
      lastY: e.clientY,
      lastT: performance.now(),
      velocity: 0,
      moved: false,
    };
    setDragging(true);
  };

  const onPointerMove = (e: ReactPointerEvent<HTMLElement>) => {
    const d = dragRef.current;
    if (!d || e.pointerId !== d.pointerId) return;
    const dy = e.clientY - d.startY;
    if (Math.abs(dy) > TAP_SLOP_PX) d.moved = true;
    const sheetH = sheetHeight();
    let next = d.startTranslate + dy;
    // Slight resistance above the top detent; hard floor at fully hidden.
    if (next < 0) next *= 0.25;
    next = Math.min(next, sheetH + 40);
    setTranslate(next);

    const now = performance.now();
    const dt = now - d.lastT;
    if (dt > 0) {
      const v = (e.clientY - d.lastY) / dt;
      d.velocity = d.velocity * 0.7 + v * 0.3;
      d.lastY = e.clientY;
      d.lastT = now;
    }
  };

  const endDrag = (e: ReactPointerEvent<HTMLElement>) => {
    const d = dragRef.current;
    if (!d || e.pointerId !== d.pointerId) return;
    dragRef.current = null;
    setDragging(false);
    if (d.moved) suppressClickRef.current = true;
    if (!d.moved) {
      // Tap, not a drag — restore the current detent.
      applyDetent(detents[snapIndex] ?? detents[0]);
      return;
    }
    const sheetH = sheetHeight();
    const projected = translateRef.current + d.velocity * FLING_PROJECT_MS;
    const detentYs = detents.map((s) => translateFor(s));

    // Swipe-down dismissal: once the release point (projected) is past
    // the midpoint between the lowest detent and fully-hidden, close.
    const closeThreshold = detentYs[0] + (sheetH - detentYs[0]) * 0.5;
    if (projected > closeThreshold) {
      onClose();
      return;
    }

    // Nearest detent wins.
    let best = 0;
    for (let i = 1; i < detentYs.length; i += 1) {
      if (Math.abs(detentYs[i] - projected) < Math.abs(detentYs[best] - projected)) {
        best = i;
      }
    }
    goToSnap(best);
  };

  // Keyboard detent control on the grabber (WCAG 2.1.1 — the drag
  // gesture must have a keyboard equivalent).
  const onGrabberKeyDown = (e: ReactKeyboardEvent<HTMLElement>) => {
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      goToSnap(snapIndex + 1);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (snapIndex === 0) onClose();
      else goToSnap(snapIndex - 1);
    } else if (e.key === 'Home') {
      e.preventDefault();
      goToSnap(detents.length - 1);
    } else if (e.key === 'End') {
      e.preventDefault();
      goToSnap(0);
    }
  };

  // Tap the grabber to cycle detents (mouse / non-drag affordance).
  const onGrabberClick = () => {
    if (suppressClickRef.current) {
      suppressClickRef.current = false;
      return;
    }
    goToSnap((snapIndex + 1) % detents.length);
  };

  if (!mounted) return null;

  const currentSnap = detents[snapIndex] ?? detents[0];

  return createPortal(
    <div className="bottom-sheet-root">
      <div
        className={`bottom-sheet-scrim ${leaving ? 'bottom-sheet-scrim--leaving' : ''}`}
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={sheetRef}
        className={`bottom-sheet ${dragging ? 'bottom-sheet--dragging' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        aria-label={title ? undefined : (ariaLabel ?? '面板')}
      >
        <div ref={contentRef} className="bottom-sheet__content">
        <div
          className="bottom-sheet__dragzone"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
        >
          <button
            type="button"
            className="bottom-sheet__grabber"
            aria-label={`拖拽调整面板高度，当前${currentSnap === 'full' ? '全屏' : currentSnap === 'half' ? '半屏' : '半隐藏'}；方向键上下切换`}
            onClick={onGrabberClick}
            onKeyDown={onGrabberKeyDown}
          />
          {/* The header always renders so the close affordance (×) is
              guaranteed visible even for title-less sheets — NN/g bottom
              sheet guideline: never rely on the gesture alone. */}
          <div className="bottom-sheet__header">
            {title ? (
              <h3 id={titleId} className="bottom-sheet__title">
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
              className="bottom-sheet__close"
            />
          </div>
        </div>
        <div
          className={`bottom-sheet__body ${footer ? '' : 'bottom-sheet__body--last'}`}
        >
          {children}
        </div>
        {footer ? <div className="bottom-sheet__footer">{footer}</div> : null}
        </div>
      </div>
    </div>,
    document.body,
  );
}
