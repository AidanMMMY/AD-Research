/**
 * 标的池详情页 × PoolAnalytics 契约测试（2026-10-25 P0 修复）。
 *
 * 修复前前端类型与 app/schemas/pool.py 漂移：读 `name`（后端是
 * pool_name）、缺 member_count、members 误用 PoolWeight、rebalance_needed
 * 误建成数组——分析数据从未真实显示。
 *
 * 本测试用后端 schema 形状的 fixture 驱动 PoolDetail，锁定：
 *  - 描述行读 analytics.member_count（不是 pool.members.length）；
 *  - 核心指标卡读 performance.{return_1m,return_3m,...}；
 *  - rebalance_needed=true + rebalance_alerts 时展示再平衡告警；
 *  - 成员表备注列读 notes（后端字段名，非 note）。
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import PoolDetail from '@/pages/PoolDetail';
import type { Pool, PoolAnalytics } from '@/types/pool';

const { POOL, ANALYTICS } = vi.hoisted(() => ({
  // PoolResponse 形状：members[].notes（非 note），无 pool_id/is_active
  POOL: {
    id: 3,
    name: '核心池',
    description: '研究篮子',
    user_id: null,
    created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-02T00:00:00',
    members: [
      {
        etf_code: '510300',
        etf_name: '沪深300ETF',
        name_zh: '沪深300ETF',
        added_at: '2026-01-01T00:00:00',
        notes: '底仓',
      },
    ],
  } satisfies Pool,
  // PoolAnalyticsResponse 形状：pool_name / member_count / rebalance_alerts
  ANALYTICS: {
    pool_id: 3,
    pool_name: '核心池',
    member_count: 2,
    members: [
      {
        etf_code: '510300',
        etf_name: '沪深300ETF',
        name_zh: '沪深300ETF',
        category: '宽基',
        target_weight: 40,
        added_at: '2026-01-01T00:00:00',
      },
      {
        etf_code: '518880',
        etf_name: '黄金ETF',
        name_zh: '黄金ETF',
        category: '商品',
        target_weight: 60,
        added_at: '2026-01-03T00:00:00',
      },
    ],
    category_distribution: { 宽基: { count: 1, weight: 40 }, 商品: { count: 1, weight: 60 } },
    performance: {
      return_1m: 0.0123,
      return_3m: -0.045,
      volatility_20d: 0.12,
      sharpe_1y: 1.05,
      max_drawdown_1y: -0.08,
    },
    rebalance_needed: true,
    rebalance_alerts: [
      {
        etf_code: '510300',
        etf_name: '沪深300ETF',
        name_zh: '沪深300ETF',
        target_weight: 40,
        actual_weight: 50,
        deviation: 10,
      },
    ],
  } satisfies PoolAnalytics,
}));

vi.mock('@/hooks/usePoolDetail', () => ({
  usePoolDetail: () => ({ data: POOL }),
  usePoolAnalytics: () => ({ data: ANALYTICS }),
  usePoolCorrelation: () => ({ data: undefined }),
  usePoolWeights: () => ({ data: [] }),
  usePoolSnapshots: () => ({ data: [] }),
  useCreateSnapshot: () => ({ mutate: vi.fn() }),
  useSuggestWeights: () => ({ mutate: vi.fn() }),
  useUpdateWeight: () => ({ mutate: vi.fn() }),
  useUpdatePool: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAddPoolMember: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRemovePoolMember: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock('@/hooks/useInstrumentList', () => ({
  useEtfOptions: () => ({ data: [] }),
}));

vi.mock('@/hooks/useAIHelp', () => ({
  useAIHelp: () => ({
    isOpen: false,
    context: null,
    messages: [],
    isLoading: false,
    error: null,
    sessionId: null,
    open: vi.fn(),
    close: vi.fn(),
    sendMessage: vi.fn(),
    retryLast: vi.fn(),
  }),
  useAIHelpStream: () => ({ steps: [], streamedText: '' }),
}));

// vitest globals=false，RTL 自动 cleanup 不生效，手动清
afterEach(cleanup);

// jsdom 无 matchMedia，antd 组件依赖
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

// jsdom 的 getComputedStyle 不支持伪元素参数，rc-table 测量滚动阴影时
// 会触发 "Not implemented" 噪音——剥掉 pseudoElt 保持输出干净。
const rawGetComputedStyle = window.getComputedStyle.bind(window);
window.getComputedStyle = (elt: Element) => rawGetComputedStyle(elt);

function renderPoolDetail() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/pools/3']}>
        <Routes>
          <Route path="/pools/:id" element={<PoolDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PoolDetail × PoolAnalytics 契约', () => {
  it('描述行读 analytics.member_count（2 ≠ pool.members.length 1）', async () => {
    renderPoolDetail();
    expect(await screen.findByText(/研究篮子 · 2 只标的/)).toBeInTheDocument();
  });

  it('核心指标卡读 performance 字段（加权收益/夏普）', async () => {
    renderPoolDetail();
    await screen.findByText(/研究篮子 · 2 只标的/);
    // return_1m=0.0123 → +1.23%；return_3m=-0.045 → -4.50%；sharpe=1.05
    expect(screen.getByText('+1.23')).toBeInTheDocument();
    expect(screen.getByText('-4.50')).toBeInTheDocument();
    expect(screen.getByText('+1.05')).toBeInTheDocument();
  });

  it('rebalance_needed + rebalance_alerts 展示再平衡告警', async () => {
    renderPoolDetail();
    expect(
      await screen.findByText('组合偏离目标权重，建议再平衡'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        (_, el) =>
          el?.tagName === 'LI' &&
          el.textContent === '510300 沪深300ETF：目标 40.0%，实际 50.0%（偏离 10.0 个百分点）',
      ),
    ).toBeInTheDocument();
  });

  it('成员表备注列读后端 notes 字段', async () => {
    renderPoolDetail();
    expect(await screen.findByText('底仓')).toBeInTheDocument();
  });
});
