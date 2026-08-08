/**
 * A11y smoke — DetailDrawer (added 2026-08-06 frontend audit).
 *
 * DetailDrawer is one of the most interaction-dense shared shells
 * (scrim dismiss, ESC handler, focus trap, aria-modal dialog) yet was
 * never axe-tested. It previously carried the only eslint error in src/
 * (jsx-a11y/no-noninteractive-element-interactions on the scrim). This
 * suite pins the open-state dialog contract so that regression fails CI.
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, fireEvent } from '@testing-library/react';
import axeCore, { type Result as AxeResult } from 'axe-core';

async function runAxe(container: Element): Promise<AxeResult> {
  const axeNs = (axeCore as unknown as { run?: typeof axeCore.run }).run
    ? (axeCore as unknown as { run: typeof axeCore.run })
    : (axeCore as unknown as { default: { run: typeof axeCore.run } }).default;
  return axeNs.run(container, {
    rules: {
      // jsdom has no layout; color-contrast is asserted visually elsewhere.
      'color-contrast': { enabled: false },
    },
  });
}

describe('DetailDrawer a11y smoke', () => {
  it('open dialog: no serious/critical axe violations', async () => {
    const DetailDrawer = (await import('@/components/DetailDrawer')).default;
    const { container } = render(
      <DetailDrawer open onClose={vi.fn()} title="标的详情" ariaLabel="标的详情">
        <p>测试内容</p>
      </DetailDrawer>,
    );

    const dialog = container.querySelector('[role="dialog"]') as HTMLElement;
    expect(dialog).not.toBeNull();
    // dialog must be labelled (title -> aria-labelledby) and modal.
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.getAttribute('aria-labelledby')).toBeTruthy();

    const results = await runAxe(container);
    const serious = (results.violations || []).filter(
      (v) => v.impact === 'serious' || v.impact === 'critical',
    );
    expect(serious).toEqual([]);
  });

  it('scrim is a real dismissible control (a11y lint regression)', async () => {
    const DetailDrawer = (await import('@/components/DetailDrawer')).default;
    const onClose = vi.fn();
    const { container } = render(
      <DetailDrawer open onClose={onClose} ariaLabel="关闭面板">
        <p>测试内容</p>
      </DetailDrawer>,
    );

    // Scrim must be a <button> (interactive, lint-clean) not a bare
    // <div onClick>; aria-hidden because the in-panel close button + Escape
    // are the AT-visible dismissal paths. Click still closes.
    const scrim = container.querySelector('.ad-detail-drawer-overlay') as HTMLElement;
    expect(scrim.tagName.toLowerCase()).toBe('button');
    expect(scrim.getAttribute('aria-hidden')).toBe('true');
    fireEvent.click(scrim);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
