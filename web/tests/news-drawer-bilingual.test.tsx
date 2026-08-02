/**
 * NewsDetailDrawer 双语渲染测试（2026-08-02）。
 *
 * 背景：用户截图反馈——韩文文章（global_donga）库里 title_zh /
 * translated_zh 齐全，但详情抽屉从头到尾只渲染原文（title/full_content），
 * 列表卡片却是中文优先，抽屉成了翻译盲区。修复后抽屉与
 * pages/News/detail.tsx 同模式：中文标题优先 + 中文译文默认 +
 * 中文/原文切换 + 翻译未就绪时 slim 提示（绝不留空白）。
 *
 * 覆盖：
 *  - 有译文：标题中文优先 + 「原文标题」次行 + 正文默认中文译文；
 *  - 切到「原文」后显示原始 full_content；
 *  - 无译文非中文：显示「翻译进行中」提示且原文仍可见（无空白面板）；
 *  - 中文文章：不出现语言切换条/提示。
 */
import { describe, it, expect, afterEach } from 'vitest';
import React from 'react';
import { cleanup, render, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import NewsDetailDrawer from '@/components/NewsDetailDrawer';
import type { NewsArticle } from '@/types/news';

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

function makeArticle(overrides: Partial<NewsArticle> = {}): NewsArticle {
  return {
    id: 5315156,
    source: 'global_donga',
    url: 'https://example.com/a/5315156',
    market: 'us',
    language: 'ko',
    title: '김숙, 톱스타 실체 폭로',
    title_zh: '金淑爆料顶级明星真面目',
    summary_zh: null,
    body: null,
    summary: null,
    author: null,
    published_at: '2026-08-02T15:27:48+00:00',
    fetched_at: '2026-08-02T15:29:41+00:00',
    engagement: {},
    sentiment_score: null,
    sentiment_label: null,
    sentiment_confidence: null,
    sentiment_drivers: null,
    event_category: null,
    importance: null,
    symbols: [],
    full_content: '코미디언 김숙이 과거 한 톱스타의 태도를 언급했다.',
    full_content_fetched_at: '2026-08-02T15:29:41+00:00',
    translated_zh: '喜剧演员金淑提到了过去一位顶级明星的态度。',
    translation_generated_at: '2026-08-02T15:31:49+00:00',
    ai_cleanup_status: null,
    ai_cleaned_at: null,
    ...overrides,
  };
}

const noop = () => {};

function renderDrawer(article: NewsArticle) {
  return render(
    <MemoryRouter>
      <NewsDetailDrawer article={article} onClose={noop} onPickSymbol={noop} />
    </MemoryRouter>,
  );
}

describe('NewsDetailDrawer 双语渲染', () => {
  it('有译文：中文标题优先 + 原文标题次行 + 正文默认中文译文', () => {
    const { getByText, getAllByText, queryByText } = renderDrawer(makeArticle());
    // 标题（抽屉 header 与 aria 可能出现多处，至少一处可见）
    expect(getAllByText('金淑爆料顶级明星真面目').length).toBeGreaterThan(0);
    // 原文标题次行
    expect(getByText(/原文标题：김숙, 톱스타 실체 폭로/)).toBeTruthy();
    // 正文默认中文译文，原文默认不渲染
    expect(getByText(/喜剧演员金淑提到了过去一位顶级明星的态度/)).toBeTruthy();
    expect(queryByText(/코미디언 김숙이 과거/)).toBeNull();
    // 语言切换条存在
    expect(getByText('中文译文')).toBeTruthy();
    expect(getByText('KO 原文')).toBeTruthy();
  });

  it('切到「原文」后显示原始 full_content', () => {
    const { getByText, queryByText } = renderDrawer(makeArticle());
    fireEvent.click(getByText('KO 原文'));
    expect(getByText(/코미디언 김숙이 과거/)).toBeTruthy();
    expect(queryByText(/喜剧演员金淑提到了过去一位顶级明星的态度/)).toBeNull();
  });

  it('无译文非中文：显示翻译进行中提示且原文仍可见（无空白面板）', () => {
    const { getByText } = renderDrawer(
      makeArticle({ translated_zh: null, title_zh: null }),
    );
    expect(getByText(/中文译文尚未就绪，后台翻译中/)).toBeTruthy();
    // 原文标题与原文正文仍然可见
    expect(getByText(/코미디언 김숙이 과거/)).toBeTruthy();
  });

  it('中文文章：不出现语言切换条与翻译提示', () => {
    const { queryByText } = renderDrawer(
      makeArticle({
        language: 'zh',
        title: '测试中文标题',
        title_zh: null,
        translated_zh: null,
        full_content: '中文正文内容',
      }),
    );
    expect(queryByText('中文译文')).toBeNull();
    expect(queryByText(/中文译文尚未就绪/)).toBeNull();
  });
});
