/**
 * NewsCard 收藏按钮 + 已读样式测试（学习中心 P1, 2026-08-02）。
 *
 * 覆盖：
 *  - 默认（/news 语境，不传 showBookmark）不渲染收藏按钮；
 *  - showBookmark=true 时渲染按钮，未收藏=空心图标 / 已收藏=高亮 +
 *    aria-pressed；
 *  - 点击按钮只触发 onToggleBookmark，不冒泡成 onOpen（卡片打开）；
 *  - read=true 时标题带降透明度 class。
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { fireEvent, render } from '@testing-library/react';
import NewsCard from '@/components/NewsCard';
import type { NewsArticle } from '@/types/news';

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

describe('NewsCard 收藏按钮（showBookmark）', () => {
  it('默认不渲染收藏按钮（/news 语境）', () => {
    const { queryByRole } = render(
      <NewsCard article={makeArticle()} onOpen={noop} onPickSymbol={noop} />
    );
    expect(queryByRole('button', { name: /收藏/ })).toBeNull();
  });

  it('showBookmark=true 渲染按钮，点击只触发 onToggleBookmark', () => {
    const onToggle = vi.fn();
    const onOpen = vi.fn();
    const article = makeArticle({ bookmarked: false });
    const { getByRole } = render(
      <NewsCard
        article={article}
        onOpen={onOpen}
        onPickSymbol={noop}
        showBookmark
        onToggleBookmark={onToggle}
      />
    );
    const btn = getByRole('button', { name: '收藏（稍后读）' });
    expect(btn.getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(btn);
    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onToggle.mock.calls[0][0].id).toBe(42);
    // stopPropagation：点收藏不应打开详情
    expect(onOpen).not.toHaveBeenCalled();
  });

  it('已收藏时按钮高亮且 aria-pressed=true', () => {
    const { getByRole } = render(
      <NewsCard
        article={makeArticle({ bookmarked: true })}
        onOpen={noop}
        onPickSymbol={noop}
        showBookmark
        onToggleBookmark={noop}
      />
    );
    const btn = getByRole('button', { name: '取消收藏' });
    expect(btn.getAttribute('aria-pressed')).toBe('true');
    expect(btn.className).toContain('ad-news-card__bookmark--active');
  });
});

describe('NewsCard 已读样式', () => {
  it('read=true 时标题带降透明度 class', () => {
    const { container } = render(
      <NewsCard
        article={makeArticle({ read: true })}
        onOpen={noop}
        onPickSymbol={noop}
        showBookmark
        onToggleBookmark={noop}
      />
    );
    expect(
      container.querySelector('.ad-news-card__title--read')
    ).not.toBeNull();
  });

  it('read 缺省（/news 响应无此字段）不降透明度', () => {
    const { container } = render(
      <NewsCard article={makeArticle()} onOpen={noop} onPickSymbol={noop} />
    );
    expect(container.querySelector('.ad-news-card__title--read')).toBeNull();
  });
});
