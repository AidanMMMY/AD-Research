import { useEffect, useId, useRef, useState } from 'react';
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

  // DR2（2026-08-03）焦点管理三件套：
  // 1) 打开时焦点移入抽屉（优先关闭按钮，退化为面板本身）；
  // 2) Tab / Shift+Tab 在抽屉内循环（简易 focus trap，见面板 onKeyDown）；
  // 3) 背景兄弟容器 inert（移出 Tab 序 + 命中测试），配合上面的
  //    useFocusRestore 在关闭后把焦点还给触发元素。
  const overlayRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);

  // (1) Focus into the drawer on open. Wait one frame so the panel is
  // painted (it mounts with the --entering transform).
  useEffect(() => {
    if (!open || !mounted) return;
    const raf = requestAnimationFrame(() => {
      const panel = panelRef.current;
      if (!panel) return;
      const closeBtn = panel.querySelector<HTMLElement>(
        '.ad-detail-drawer__close',
      );
      (closeBtn ?? panel).focus();
    });
    return () => cancelAnimationFrame(raf);
  }, [open, mounted]);

  // (3) Mark the drawer's sibling containers inert while open so keyboard
  // / pointer interaction stays inside the dialog (aria-modal 的行为补全）。
  // The overlay is rendered in place (inside the page tree), so its parent
  // chain's other children are the background content.
  useEffect(() => {
    if (!open) return;
    const overlay = overlayRef.current;
    const parent = overlay?.parentElement;
    if (!parent) return;
    const panel = panelRef.current;
    const siblings = Array.from(parent.children).filter(
      (el): el is HTMLElement =>
        el instanceof HTMLElement && el !== overlay && el !== panel,
    );
    siblings.forEach((el) => el.setAttribute('inert', ''));
    return () => {
      siblings.forEach((el) => el.removeAttribute('inert'));
    };
  }, [open]);

  // (2) Simple focus trap — 挂在 document 上而不是 dialog 元素上：
  // WAI-ARIA 对话框模式的 Tab 循环逻辑不依赖元素上的事件 handler，避免
  // jsx-a11y/no-noninteractive-element-interactions 对 role="dialog" 的误报。
  useEffect(() => {
    if (!open || !mounted) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      const panel = panelRef.current;
      if (!panel) return;
      const focusables = Array.from(
        panel.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement as HTMLElement | null;
      const focusInside = active != null && panel.contains(active);
      if (e.shiftKey) {
        if (!focusInside || active === first) {
          e.preventDefault();
          last.focus();
        }
      } else if (!focusInside || active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open, mounted]);

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
    <>
      {/* Scrim 作为真实可交互控件（button）满足 jsx-a11y 规则；与 panel
          平级避免 button 嵌套（axe nested-interactive）。对读屏隐藏
          aria-hidden——显式关闭按钮 + Escape 已提供可访问的关闭路径，
          避免读屏读出两个"关闭"（面板内关闭按钮才是 AT 的入口）。 */}
      <button
        type="button"
        ref={overlayRef}
        className={overlayClasses}
        aria-hidden="true"
        tabIndex={-1}
        onClick={onClose}
      />
      <div
        ref={panelRef}
        className={drawerClasses}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        aria-label={title ? undefined : ariaLabel}
        tabIndex={-1}
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
    </>
  );
}
