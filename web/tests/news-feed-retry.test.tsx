/**
 * News 列表错误态「重试」按钮测试（N1, 2026-08-03）。
 *
 * 背景：此前 useInfiniteQuery 失败时只渲染一句"加载失败，请稍后重试"，
 * 没有任何重试出口——用户只能整页刷新。现在 EmptyState 携带
 * 「重试」按钮触发 refetch。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { cleanup, render, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import NewsFeed from '@/pages/News';
import { newsApi } from '@/api/news';

vi.mock('@/api/news', () => ({
  newsApi: {
    list: vi.fn(),
    watchlist: vi.fn(),
    sourceStats: vi.fn(),
  },
}));

// vitest globals:false，RTL 不自动 cleanup，需手动卸载避免跨用例 DOM 累积
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

// jsdom 没有 IntersectionObserver（无限滚动 sentinel 依赖）。
if (!window.IntersectionObserver) {
  window.IntersectionObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
  } as unknown as typeof window.IntersectionObserver;
}

const mocked = vi.mocked(newsApi);

function renderFeed() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <NewsFeed />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('News 列表加载失败重试（N1）', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.sourceStats.mockResolvedValue({ data: { sources: [] } } as any);
  });

  it('加载失败时渲染「重试」按钮，点击触发 refetch', async () => {
    mocked.list.mockRejectedValue(new Error('network down'));
    const { getByRole, getByText } = renderFeed();

    await waitFor(() => {
      expect(getByText('加载失败，请稍后重试')).toBeTruthy();
    });
    // antd 对两字中文按钮自动插空格（autoInsertSpaceInButton），
    // 可访问名是「重 试」。
    const retryBtn = getByRole('button', { name: /重\s*试/ });
    expect(retryBtn).toBeTruthy();

    const callsBefore = mocked.list.mock.calls.length;
    // 点重试时让接口恢复成功，验证 refetch 真的发出去
    mocked.list.mockResolvedValue({
      data: { items: [], total: 0, page: 1, page_size: 20 },
    } as any);
    fireEvent.click(retryBtn);
    await waitFor(() => {
      expect(mocked.list.mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });
});
