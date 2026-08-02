/**
 * NewsCard 难度标签测试（学习中心 P2, 2026-08-02）。
 *
 * 覆盖：
 *  - 默认（/news 语境，不传 showDifficulty）即使文章带
 *    difficulty_default 也不渲染标签——共享组件零变化；
 *  - showDifficulty=true 时 beginner 渲染「入门」（绿系 class）、
 *    advanced 渲染「进阶」（橙系 class）；
 *  - difficulty_default=null（混合/不确定源）不渲染。
 */
import { describe, it, expect, afterEach } from 'vitest';
import React from 'react';
import { cleanup, render } from '@testing-library/react';
import NewsCard from '@/components/NewsCard';
import type { NewsArticle } from '@/types/news';

// vitest.config 设了 globals:false，@testing-library 的自动 cleanup
// 不生效——必须手动清，否则上一个用例的渲染结果会污染后面的查询。
afterEach(cleanup);

function makeArticle(overrides: Partial<NewsArticle> = {}): NewsArticle {
  return {
    id: 42,
    source: 'xinhua',
    url: 'https://example.com/a/42',
    market: 'cn_a',
    language: 'zh',
    title: '测试文章标题',
    title_zh: null,
    summary_zh: null,
    body: null,
    summary: null,
    author: null,
    published_at: '2026-08-01T02:00:00+00:00',
    fetched_at: '2026-08-01T02:00:00+00:00',
    engagement: {},
    sentiment_score: null,
    sentiment_label: null,
    sentiment_confidence: null,
    sentiment_drivers: null,
    event_category: null,
    importance: null,
    symbols: [],
    full_content: null,
    full_content_fetched_at: null,
    translated_zh: null,
    translation_generated_at: null,
    ai_cleanup_status: null,
    ai_cleaned_at: null,
    ...overrides,
  };
}

const noop = () => {};

describe('NewsCard 难度标签（showDifficulty）', () => {
  it('默认不渲染——/news 语境下即使带 difficulty_default 也不显示', () => {
    const { container, queryByText } = render(
      <NewsCard
        article={makeArticle({ difficulty_default: 'beginner' })}
        onOpen={noop}
        onPickSymbol={noop}
      />
    );
    expect(queryByText('入门')).toBeNull();
    expect(container.querySelector('.ad-news-card__difficulty')).toBeNull();
  });

  it('beginner 渲染「入门」且带 beginner 修饰 class', () => {
    const { container, getByText } = render(
      <NewsCard
        article={makeArticle({ difficulty_default: 'beginner' })}
        onOpen={noop}
        onPickSymbol={noop}
        showDifficulty
      />
    );
    const tag = getByText('入门');
    expect(tag.className).toContain('ad-news-card__difficulty--beginner');
    expect(
      container.querySelector('.ad-news-card__difficulty--advanced')
    ).toBeNull();
  });

  it('advanced 渲染「进阶」且带 advanced 修饰 class', () => {
    const { container, getByText } = render(
      <NewsCard
        article={makeArticle({ difficulty_default: 'advanced' })}
        onOpen={noop}
        onPickSymbol={noop}
        showDifficulty
      />
    );
    const tag = getByText('进阶');
    expect(tag.className).toContain('ad-news-card__difficulty--advanced');
    expect(
      container.querySelector('.ad-news-card__difficulty--beginner')
    ).toBeNull();
  });

  it('difficulty_default=null（混合/不确定源）不渲染', () => {
    const { container, queryByText } = render(
      <NewsCard
        article={makeArticle({ difficulty_default: null })}
        onOpen={noop}
        onPickSymbol={noop}
        showDifficulty
      />
    );
    expect(queryByText('入门')).toBeNull();
    expect(queryByText('进阶')).toBeNull();
    expect(container.querySelector('.ad-news-card__difficulty')).toBeNull();
  });

  it('difficulty_default 缺省（字段不存在）不渲染', () => {
    const { container } = render(
      <NewsCard
        article={makeArticle()}
        onOpen={noop}
        onPickSymbol={noop}
        showDifficulty
      />
    );
    expect(container.querySelector('.ad-news-card__difficulty')).toBeNull();
  });
});
