/**
 * InstrumentSentimentPanel ?code= 回写测试（2026-08-02）。
 *
 * 覆盖：
 *  - 手动分析某标的成功后，URL 回写 ?tab=instrument&code=XXX；
 *  - 带 code 深链跳入自动分析时，URL 保持不变（不重复回写）；
 *  - ingest 失败时 URL 不回写。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import InstrumentSentimentPanel from '@/pages/SentimentDashboard';
import { AIHelpProvider } from '@/components/AIHelpProvider';
import { researchApi } from '@/api/research';

vi.mock('@/api/research', () => ({
  researchApi: {
    getAIStatus: vi.fn(),
    getSentiment: vi.fn(),
    ingestSentiment: vi.fn(),
  },
}));

// jsdom 无 matchMedia，antd 组件（Slider/Tag 等）需要
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

const mocked = vi.mocked(researchApi);

const SENTIMENT = {
  instrument_code: 'AAPL.US',
  name: 'Apple',
  name_zh: null,
  avg_score: 0.5,
  label: 'positive',
  positive_count: 3,
  negative_count: 1,
  neutral_count: 2,
  total_articles: 6,
  period_days: 7,
};

let currentSearch = '';

function LocationProbe() {
  currentSearch = useLocation().search;
  return null;
}

function renderPanel(initialEntry: string, initialCode?: string) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <AIHelpProvider>
          <InstrumentSentimentPanel initialCode={initialCode} />
        </AIHelpProvider>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('InstrumentSentimentPanel ?code= 回写', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentSearch = '';
    mocked.getAIStatus.mockResolvedValue({ data: { available: true } } as any);
    mocked.getSentiment.mockResolvedValue({ data: SENTIMENT } as any);
    mocked.ingestSentiment.mockResolvedValue({ data: {} } as any);
  });

  // vitest globals=false，RTL 不自动 cleanup，需手动卸载避免跨用例 DOM 累积
  afterEach(() => cleanup());

  it('手动分析成功后回写 ?tab=instrument&code=XXX', async () => {
    const { getByPlaceholderText, getByRole } = renderPanel('/sentiment?tab=instrument');
    fireEvent.change(getByPlaceholderText('标的代码 (如 AAPL.US)'), {
      target: { value: 'aapl.us' },
    });
    fireEvent.click(getByRole('button', { name: /分析情绪/ }));
    await waitFor(() => {
      expect(mocked.ingestSentiment).toHaveBeenCalledWith('AAPL.US', 7);
    });
    await waitFor(() => {
      expect(currentSearch).toContain('code=AAPL.US');
    });
    expect(currentSearch).toContain('tab=instrument');
  });

  it('带 code 深链跳入自动分析，URL 保持不变', async () => {
    renderPanel('/sentiment?tab=instrument&code=510300.SH', '510300.SH');
    await waitFor(() => {
      expect(mocked.ingestSentiment).toHaveBeenCalledWith('510300.SH', 7);
    });
    // 等查询也完成后，URL 应与进入时一致（守卫避免多余 replace）
    await waitFor(() => {
      expect(mocked.getSentiment).toHaveBeenCalled();
    });
    expect(currentSearch).toBe('?tab=instrument&code=510300.SH');
  });

  it('深链跳入后换标的分析，URL 更新为新 code', async () => {
    const { getByPlaceholderText, getByRole } = renderPanel(
      '/sentiment?tab=instrument&code=510300.SH',
      '510300.SH'
    );
    await waitFor(() => {
      expect(mocked.ingestSentiment).toHaveBeenCalledWith('510300.SH', 7);
    });
    fireEvent.change(getByPlaceholderText('标的代码 (如 AAPL.US)'), {
      target: { value: 'SPY.US' },
    });
    fireEvent.click(getByRole('button', { name: /分析情绪/ }));
    await waitFor(() => {
      expect(currentSearch).toContain('code=SPY.US');
    });
    expect(currentSearch).toContain('tab=instrument');
  });

  it('ingest 失败时 URL 不回写', async () => {
    mocked.ingestSentiment.mockRejectedValue(new Error('boom'));
    const { getByPlaceholderText, getByRole } = renderPanel('/sentiment?tab=instrument');
    fireEvent.change(getByPlaceholderText('标的代码 (如 AAPL.US)'), {
      target: { value: 'AAPL.US' },
    });
    fireEvent.click(getByRole('button', { name: /分析情绪/ }));
    await waitFor(() => {
      expect(mocked.ingestSentiment).toHaveBeenCalled();
    });
    // 给 onSuccess 一个（不应发生的）机会后仍不应回写
    await new Promise((r) => setTimeout(r, 50));
    expect(currentSearch).toBe('?tab=instrument');
  });
});
