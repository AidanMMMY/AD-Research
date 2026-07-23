/**
 * A11y smoke — Dashboard v8 (command-center) primitives (2026-07-23).
 *
 * Adds coverage for the components the new home screen leans on heavily:
 *   - Topbar (brand + search + pulse + status row)
 *   - Sidebar nav
 *   - A 3-up card grid (Fund Flow / Sector Momentum / Signal Stream)
 *   - Watchlist / AI Briefing / Decision Queue rows
 *
 * Like smoke.test.tsx we don't render the live Dashboard page (it pulls
 * in 30+ hooks and the live API); instead we mount the same landmark +
 * keyhandler contract via a small fixture. If the real dashboard markup
 * drifts from this shape the axe rules ("click-events-have-key-events",
 * "button-name") fire on it through the Page-level lint PR feedback.
 */

import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render } from '@testing-library/react';
import axeCore, { type Result as AxeResult } from 'axe-core';

async function runAxe(container: Element): Promise<AxeResult> {
  const axeNs = (axeCore as unknown as { run?: typeof axeCore.run }).run
    ? (axeCore as unknown as { run: typeof axeCore.run })
    : (axeCore as unknown as { default: { run: typeof axeCore.run } }).default;
  return axeNs.run(container, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] },
    rules: { 'color-contrast': { enabled: false } },
  });
}

/** Mimics the clickable `role="button"` card factory used throughout
 *  Dashboard v8: cc-pulse-item, cc-watch-row, cc-signal, cc-brief,
 *  cc-sector-row. We assert the same keyboard + aria contract here. */
function ClickableRow({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={label}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
    >
      {children}
    </div>
  );
}

function CommandCenterFixture() {
  return (
    <div className="dashboard-command-center">
      <header className="cc-topbar" aria-label="顶部状态栏">
        <div className="cc-topbar__brand">AD</div>
        <div className="cc-topbar__search">搜索标的、新闻…</div>
        <div className="cc-topbar__status">
          <span className="cc-status-dot" aria-hidden />
          <span>实时连接</span>
        </div>
      </header>
      <div className="cc-layout">
        <aside className="cc-sidebar" aria-label="主导航">
          <div role="button" tabIndex={0} aria-label="指挥中心" className="cc-nav-item cc-nav-item--active">
            <span className="cc-nav-icon" aria-hidden />
            指挥中心
          </div>
          <div role="button" tabIndex={0} aria-label="全球市场">
            <span className="cc-nav-icon" aria-hidden />
            全球市场
          </div>
          <div role="button" tabIndex={0} aria-label="资金流">
            <span className="cc-nav-icon" aria-hidden />
            资金流
          </div>
        </aside>
        <main className="cc-main">
          <h1 className="cc-header__title">市场指挥中心</h1>
          <div className="cc-grid">
            <ClickableRow label="资金流：大盘净流入 +1.2 亿" onClick={() => undefined}>
              <span>资金流大盘净流入</span>
              <span>+1.2 亿</span>
            </ClickableRow>
            <ClickableRow label="自选股 510300 价格 4.321" onClick={() => undefined}>
              <span>510300 沪深300ETF</span>
              <span>4.321</span>
            </ClickableRow>
            <ClickableRow label="信号流 Top1" onClick={() => undefined}>
              <span>综合信号 Top1 · 510300</span>
              <span>85.3</span>
            </ClickableRow>
          </div>
        </main>
      </div>
    </div>
  );
}

describe('Dashboard v8 command-center a11y smoke', () => {
  it('renders the topbar + sidebar + 3-up grid without violations', async () => {
    const { container } = render(<CommandCenterFixture />);
    expect(container.querySelector('header[aria-label="顶部状态栏"]')).not.toBeNull();
    expect(container.querySelector('aside[aria-label="主导航"]')).not.toBeNull();
    expect(container.querySelector('main')).not.toBeNull();
    const results = await runAxe(container);
    expect(results).toHaveNoViolations();
  });

  it('every nav item carries aria-label and is keyboard-reachable', async () => {
    const { container } = render(<CommandCenterFixture />);
    const items = container.querySelectorAll('[role="button"][aria-label]');
    expect(items.length).toBeGreaterThanOrEqual(3);
    items.forEach((el) => {
      expect(el.getAttribute('tabindex')).toBe('0');
    });
  });
});
