/**
 * 每日研报（B6）前端测试（2026-08-02）。
 *
 * 后端 API 并行开发中，全部 mock @/api/digest 的 digestApi 层，
 * 契约以 api/digest.ts 顶部注释为准（/digest /latest /latest/summary /by-date）。
 *
 * 覆盖：
 *  - DigestSummaryCard：有报告（标题+日期+摘要+阅读全文）/ 404 降级（生成中）；
 *  - Digest 页：partial 徽章「部分章节数据缺失」+ markdown 章节冒烟 + 目录锚点；
 *  - Digest 页：?date= 404 空态「今日研报生成中」+「查看最近一篇」回落到 latest。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DigestSummaryCard from '@/components/DigestSummaryCard';
import Digest, { splitContent } from '@/pages/Digest';
import { digestApi } from '@/api/digest';
import type { DigestLatestSummary, DigestReport } from '@/api/digest';

vi.mock('@/api/digest', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/digest')>();
  return {
    ...actual,
    digestApi: {
      getList: vi.fn(),
      getLatest: vi.fn(),
      getLatestSummary: vi.fn(),
      getByDate: vi.fn(),
    },
  };
});

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

// jsdom 未实现 scrollIntoView，目录锚点点击会调它
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

const mocked = vi.mocked(digestApi);

const SUMMARY: DigestLatestSummary = {
  id: 7,
  report_date: '2026-08-02',
  title: '隔夜美股创新高，A 股关注北向回流',
  status: 'success',
  summary_md: '## 要点\n- 标普 500 收涨 1.2%\n- 美债 10Y 回落至 4.1%\n- 北向资金净流入 80 亿',
  content_chars: 5432,
};

const REPORT: DigestReport = {
  id: 7,
  report_date: '2026-08-02',
  title: '隔夜美股创新高，A 股关注北向回流',
  status: 'partial',
  summary_md: '- 标普 500 收涨 1.2%\n- 北向资金净流入 80 亿',
  content_md:
    '开场段落：隔夜海外风险偏好回升。\n\n## 全球市场\n美股三大指数齐涨。\n\n## 宏观数据\n美债收益率回落。\n\n## 资金流\n北向净流入 80 亿。',
  sections_json: [
    { key: 'global', title: '全球市场', status: 'ok', chars: 1200, retries: 0 },
    { key: 'macro', title: '宏观数据', status: 'degraded', chars: 300, retries: 2 },
    { key: 'flow', title: '资金流', status: 'ok', chars: 900, retries: 0 },
  ],
  llm_model: 'minimax-m3',
  finished_at: '2026-08-02T22:30:00+00:00',
};

const notFoundError = () => ({ response: { status: 404 } });

function renderWithProviders(ui: React.ReactElement, initialEntry = '/digest') {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialEntry]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('DigestSummaryCard', () => {
  beforeEach(() => vi.clearAllMocks());

  it('有报告：标题 + 日期 + 摘要前 3 行 + 阅读全文入口', async () => {
    mocked.getLatestSummary.mockResolvedValue({ data: SUMMARY } as any);
    const { getByText, getByRole } = renderWithProviders(<DigestSummaryCard />);
    await waitFor(() => {
      expect(getByText('隔夜美股创新高，A 股关注北向回流')).toBeTruthy();
    });
    expect(getByText(/2026-08-02/)).toBeTruthy();
    // 摘要拍平为纯文本（markdown 记号已去除）
    expect(getByText(/标普 500 收涨 1.2%/)).toBeTruthy();
    expect(getByText('阅读全文 →')).toBeTruthy();
    expect(
      getByRole('button', { name: /阅读每日研报全文：隔夜美股创新高/ }),
    ).toBeTruthy();
  });

  it('404（无报告）：降级为「今日研报生成中」', async () => {
    mocked.getLatestSummary.mockRejectedValue(notFoundError());
    const { getByText, queryByText } = renderWithProviders(<DigestSummaryCard />);
    await waitFor(() => {
      expect(getByText(/今日研报生成中，每日 6:30 发布/)).toBeTruthy();
    });
    expect(queryByText('阅读全文 →')).toBeNull();
  });
});

describe('splitContent', () => {
  it('剥掉 intro 里残留的一级标题行（旧数据双标题防御，2026-08-21）', () => {
    // 2026-08-21 前入库的 content_md 以 `# {title}` H1 开头，hero 卡
    // 已渲染 title → 不剥会在正文区再显示一次标题
    const md = '# 2026-08-02 每日综合研报\n\n开场段落：风险偏好回升。\n\n## 全球市场\n美股齐涨。';
    const { intro, sections } = splitContent(md);
    expect(intro).toBe('开场段落：风险偏好回升。');
    expect(sections).toHaveLength(1);
    expect(sections[0].title).toBe('全球市场');
    expect(sections[0].body).toBe('美股齐涨。');
  });

  it('无 H1 时 intro 原样保留；章节正文内的 # 行不剥', () => {
    const md = '开场段落。\n\n## 全球市场\n# 这是正文里的行\n正文。';
    const { intro, sections } = splitContent(md);
    expect(intro).toBe('开场段落。');
    expect(sections[0].body).toContain('# 这是正文里的行');
  });

  it('连续多个 H1 + 空行全剥', () => {
    const md = '# 标题一\n# 标题二\n\n\n## 章节\n正文。';
    const { intro, sections } = splitContent(md);
    expect(intro).toBe('');
    expect(sections).toHaveLength(1);
  });
});

describe('Digest 页', () => {
  beforeEach(() => vi.clearAllMocks());

  it('旧数据（content_md 自带 # 标题 H1）：标题只显示一次，不出双标题', async () => {
    // 回归：2026-08-21 前 generator 把 `# {title}` 焊进 content_md，
    // hero 卡 + 正文 intro 双重渲染（用户截图实锤）。服务端清洗 + splitContent
    // 防御后，即使拿到旧格式数据页面也只显示一次标题。
    const LEGACY: DigestReport = {
      ...REPORT,
      title: '2026-08-02 每日综合研报',
      content_md:
        '# 2026-08-02 每日综合研报\n\n## 全球市场\n美股三大指数齐涨。\n\n## 宏观数据\n美债收益率回落。',
    };
    mocked.getLatest.mockResolvedValue({ data: LEGACY } as any);
    const { getAllByText } = renderWithProviders(<Digest />);
    await waitFor(() => {
      expect(getAllByText('2026-08-02 每日综合研报')).toHaveLength(1);
    });
    // 正文区没有任何一级标题元素
    expect(document.querySelector('.digest-body h1')).toBeNull();
    expect(document.querySelector('.digest-body__intro')).toBeNull();
  });

  it('partial 报告：徽章「部分章节数据缺失」+ markdown 章节 + 目录锚点', async () => {
    mocked.getLatest.mockResolvedValue({ data: REPORT } as any);
    const { getByText, getAllByText } = renderWithProviders(<Digest />);
    await waitFor(() => {
      expect(getByText('部分章节数据缺失')).toBeTruthy();
    });
    // 标题与摘要
    expect(getByText('隔夜美股创新高，A 股关注北向回流')).toBeTruthy();
    // markdown 正文按 ## 切章渲染
    expect(getByText('美股三大指数齐涨。')).toBeTruthy();
    expect(getByText('北向净流入 80 亿。')).toBeTruthy();
    // 目录（移动端 details + 桌面端 aside 各渲染一份）
    expect(getAllByText('全球市场').length).toBeGreaterThanOrEqual(2);
    // 章节锚点 id 存在，可滚动定位
    expect(document.getElementById('digest-sec-0')).toBeTruthy();
    expect(document.getElementById('digest-sec-2')).toBeTruthy();
    // 降级章节在目录里有状态点
    expect(document.querySelector('.digest-toc__dot--degraded')).toBeTruthy();
  });

  it('?date= 404：空态「今日研报生成中」+「查看最近一篇」回落 latest', async () => {
    mocked.getByDate.mockRejectedValue(notFoundError());
    mocked.getLatest.mockResolvedValue({ data: REPORT } as any);
    const { getByText, findByText } = renderWithProviders(
      <Digest />,
      '/digest?date=2026-08-01',
    );
    // 空态（PageHeader 描述也含「每日 6:30 发布」，用 getAllByText）
    expect(await findByText('今日研报生成中')).toBeTruthy();
    expect(getByText(/请稍后再来/)).toBeTruthy();
    // 点击「查看最近一篇」→ 清掉 date 参数 → 走 latest
    fireEvent.click(getByText('查看最近一篇'));
    await waitFor(() => {
      expect(mocked.getLatest).toHaveBeenCalled();
    });
    await findByText('部分章节数据缺失');
  });
});
