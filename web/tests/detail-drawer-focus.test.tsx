/**
 * DetailDrawer 焦点管理测试（DR2, 2026-08-03）。
 *
 * 覆盖：
 *  - 打开时焦点移入抽屉（落在关闭按钮上）；
 *  - Tab 在最后一个可聚焦元素上循环回第一个；Shift+Tab 在第一个上
 *    循环到最后一个；
 *  - 关闭后焦点还给触发元素（useFocusRestore 收尾）；
 *  - 打开期间背景兄弟容器被 inert（移出 Tab 序）。
 */
import { describe, it, expect, afterEach } from 'vitest';
import React from 'react';
import { cleanup, render, fireEvent, act } from '@testing-library/react';
import DetailDrawer from '@/components/DetailDrawer';

// vitest.config 设了 globals:false，@testing-library 的自动 cleanup
// 不生效——必须手动清，否则上一个用例的渲染结果会污染后面的查询。
afterEach(cleanup);

// jsdom 没有 matchMedia，antd 组件依赖它。
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

function renderDrawer(open: boolean, onClose = () => {}) {
  return render(
    <div>
      <button type="button" data-testid="trigger">
        打开
      </button>
      <div data-testid="background">背景内容</div>
      <DetailDrawer
        open={open}
        onClose={onClose}
        ariaLabel="测试抽屉"
        footer={<button type="button">底部按钮</button>}
      >
        <button type="button">内容按钮</button>
      </DetailDrawer>
    </div>,
  );
}

describe('DetailDrawer 焦点管理（DR2）', () => {
  it('打开时焦点移入抽屉（关闭按钮）', async () => {
    const { getByLabelText } = renderDrawer(true);
    // focus 在 requestAnimationFrame 后发生
    await act(async () => {
      await new Promise((r) => requestAnimationFrame(() => r(null)));
    });
    expect(document.activeElement).toBe(getByLabelText('关闭'));
  });

  it('Tab 在最后一个元素上循环回第一个', async () => {
    const { getByLabelText, getByText } = renderDrawer(true);
    await act(async () => {
      await new Promise((r) => requestAnimationFrame(() => r(null)));
    });
    const closeBtn = getByLabelText('关闭');
    const lastBtn = getByText('底部按钮');
    (lastBtn as HTMLElement).focus();
    fireEvent.keyDown(closeBtn.closest('[role="dialog"]')!, { key: 'Tab' });
    expect(document.activeElement).toBe(closeBtn);
  });

  it('Shift+Tab 在第一个元素上循环到最后一个', async () => {
    const { getByLabelText, getByText } = renderDrawer(true);
    await act(async () => {
      await new Promise((r) => requestAnimationFrame(() => r(null)));
    });
    const closeBtn = getByLabelText('关闭');
    (closeBtn as HTMLElement).focus();
    fireEvent.keyDown(closeBtn.closest('[role="dialog"]')!, {
      key: 'Tab',
      shiftKey: true,
    });
    expect(document.activeElement).toBe(getByText('底部按钮'));
  });

  it('打开期间背景兄弟容器 inert，关闭后移除', async () => {
    const { rerender, getByTestId } = render(
      <div>
        <div data-testid="background">背景内容</div>
        <DetailDrawer open={true} onClose={() => {}} ariaLabel="测试抽屉">
          <button type="button">内容按钮</button>
        </DetailDrawer>
      </div>,
    );
    expect(getByTestId('background').hasAttribute('inert')).toBe(true);
    rerender(
      <div>
        <div data-testid="background">背景内容</div>
        <DetailDrawer open={false} onClose={() => {}} ariaLabel="测试抽屉">
          <button type="button">内容按钮</button>
        </DetailDrawer>
      </div>,
    );
    expect(getByTestId('background').hasAttribute('inert')).toBe(false);
  });

  it('关闭后焦点还给触发元素', async () => {
    function Harness() {
      const [open, setOpen] = React.useState(false);
      return (
        <div>
          <button type="button" data-testid="trigger" onClick={() => setOpen(true)}>
            打开
          </button>
          <DetailDrawer open={open} onClose={() => setOpen(false)} ariaLabel="测试抽屉">
            <button type="button">内容按钮</button>
          </DetailDrawer>
        </div>
      );
    }
    const { getByTestId, getByLabelText } = render(<Harness />);
    // jsdom 的 fireEvent.click 不会自动聚焦按钮——真实浏览器里点击
    // 触发元素时它已持焦，这里显式补上，useFocusRestore 才有快照可存。
    (getByTestId('trigger') as HTMLElement).focus();
    fireEvent.click(getByTestId('trigger'));
    await act(async () => {
      await new Promise((r) => requestAnimationFrame(() => r(null)));
    });
    expect(document.activeElement).toBe(getByLabelText('关闭'));
    fireEvent.click(getByLabelText('关闭'));
    expect(document.activeElement).toBe(getByTestId('trigger'));
  });
});
