import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge, Button, Space, Tag, Tooltip } from 'antd';
import {
  LinkOutlined,
  LikeOutlined,
  MessageOutlined,
  ShareAltOutlined,
  EyeOutlined,
} from '@ant-design/icons';
import { SENTIMENT_COLORS, SENTIMENT_LABELS } from '@/utils/sentiment';
import type { NewsArticle } from '@/types/news';
import DetailDrawer from '@/components/DetailDrawer';
import Markdown from '@/components/Markdown';
import EmptyState from '@/components/EmptyState';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import ThemeTag from '@/components/ThemeTag';
import { formatDateTimeSeconds } from '@/utils/datetime';
import {
  EventCategoryTag,
  ImportanceStars,
  MARKET_BADGE,
  SOURCE_LABELS,
  formatBigNumber,
} from '@/components/NewsCard';
import './NewsDetailDrawer.css';

/**
 * Article detail drawer — extracted from ``pages/News/index.tsx``
 * (2026-08-02, learning-center sprint) so both the /news feed and the
 * /learning 知识库 feed open the same reading view.
 *
 * Opens in place of the old ``/news/:id`` navigation so reading a story
 * no longer loses the feed's scroll position, matching the Modal/drawer
 * pattern used by 研报/公告. Renders only the fields the list payload
 * already carries (no extra request). The cleaned full text
 * (``full_content``) is fetched and stored at ingestion time, so the
 * body is usually already here; the deep-link route stays for on-demand
 * re-fetch / AI translation, reachable via the "打开完整页面" footer
 * button.
 */
export default function NewsDetailDrawer({
  article,
  onClose,
  onPickSymbol,
}: {
  article: NewsArticle | null;
  onClose: () => void;
  onPickSymbol: (sym: string) => void;
}) {
  const navigate = useNavigate();
  // Keep the last non-null article so the exit animation still has
  // content to render after ``onClose`` clears the selection.
  const [lastArticle, setLastArticle] = useState<NewsArticle | null>(null);
  useEffect(() => {
    if (article) setLastArticle(article);
  }, [article]);
  const shown = article ?? lastArticle;

  const source = shown
    ? (SOURCE_LABELS[shown.source] ?? { emoji: '🔗', label: shown.source })
    : null;
  const market = shown ? MARKET_BADGE[shown.market] : null;
  const sentiment = shown?.sentiment_label ?? null;
  const engagement = shown?.engagement;
  const hasEngagement =
    engagement != null &&
    (engagement.likes != null ||
      engagement.comments != null ||
      engagement.shares != null ||
      engagement.views != null);

  return (
    <DetailDrawer
      open={!!article}
      onClose={onClose}
      title={shown?.title}
      ariaLabel="资讯详情"
      footer={
        shown ? (
          <Space size={8} wrap>
            <Button
              type="primary"
              icon={<LinkOutlined />}
              onClick={() =>
                window.open(shown.url, '_blank', 'noopener,noreferrer')
              }
            >
              查看原文
            </Button>
            <Button onClick={() => navigate(`/news/${shown.id}`)}>
              打开完整页面
            </Button>
          </Space>
        ) : undefined
      }
    >
      {shown && source && (
        <>
          {/* Meta row: source · market · category · importance */}
          <div className="ad-flex ad-items-center ad-gap-2 ad-flex-wrap ad-text-small ad-text-tertiary">
            <span>{source.emoji} {source.label}</span>
            {market && (
              <ThemeTag variant={market.variant} className="ad-detail-tag">
                {market.label}
              </ThemeTag>
            )}
            <EventCategoryTag value={shown.event_category} />
            <ImportanceStars level={shown.importance} />
          </div>
          <div className="ad-text-small ad-text-tertiary ad-mt-2">
            {formatDateTimeSeconds(shown.published_at)}
            {shown.author ? ` · ${shown.author}` : ''}
          </div>

          {/* Related symbols — clicking pivots the feed filter, same as
              the chip on the card. */}
          {shown.symbols.length > 0 && (
            <div className="ad-mt-4">
              <div className="ad-text-small ad-text-tertiary ad-mb-2">
                相关标的
              </div>
              <Space size={4} wrap>
                {shown.symbols.map((s) => (
                  <Tag
                    key={`${s.symbol}-${s.match_type}`}
                    color="default"
                    className="ad-mr-1 ad-chip-tag"
                    role="button"
                    tabIndex={0}
                    aria-label={`筛选 ${s.symbol}`}
                    onClick={() => {
                      onPickSymbol(s.symbol);
                      onClose();
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onPickSymbol(s.symbol);
                        onClose();
                      }
                    }}
                  >
                    <InstrumentCodeTag
                      code={s.symbol}
                      name={s.name ?? undefined}
                      name_zh={s.name_zh}
                    />
                  </Tag>
                ))}
              </Space>
            </div>
          )}

          {/* Sentiment + engagement */}
          {(sentiment || hasEngagement) && (
            <div className="ad-flex ad-items-center ad-gap-3 ad-flex-wrap ad-mt-4">
              {sentiment && (
                <Tooltip
                  title={
                    shown.sentiment_score != null
                      ? `分数 ${shown.sentiment_score.toFixed(2)} · 置信度 ${(
                          (shown.sentiment_confidence ?? 0) * 100
                        ).toFixed(0)}%`
                      : SENTIMENT_LABELS[sentiment]
                  }
                >
                  <Badge
                    color={SENTIMENT_COLORS[sentiment]}
                    text={
                      <span
                        className="ad-sentiment-label"
                        style={{ color: SENTIMENT_COLORS[sentiment] }}
                      >
                        {SENTIMENT_LABELS[sentiment]}
                      </span>
                    }
                  />
                </Tooltip>
              )}
              {engagement?.likes != null && (
                <span className="ad-news-card__engagement">
                  <LikeOutlined /> {formatBigNumber(engagement.likes)}
                </span>
              )}
              {engagement?.comments != null && (
                <span className="ad-news-card__engagement">
                  <MessageOutlined /> {formatBigNumber(engagement.comments)}
                </span>
              )}
              {engagement?.shares != null && (
                <span className="ad-news-card__engagement">
                  <ShareAltOutlined /> {formatBigNumber(engagement.shares)}
                </span>
              )}
              {engagement?.views != null && (
                <span className="ad-news-card__engagement">
                  <EyeOutlined /> {formatBigNumber(engagement.views)}
                </span>
              )}
            </div>
          )}

          {/* Body — prefer the cleaned full text stored locally at
              ingestion time (``full_content``); fall back to the
              crawler's intro body when no fetch has landed yet. */}
          {shown.full_content ? (
            <div className="news-drawer-body ad-mt-4">
              <Markdown source={shown.full_content} />
            </div>
          ) : shown.body || shown.summary ? (
            <div className="news-drawer-body ad-mt-4">
              {shown.body ?? shown.summary}
            </div>
          ) : (
            <EmptyState
              className="ad-mt-4"
              title="暂无正文"
              description="可点击下方「查看原文」阅读完整内容"
            />
          )}
        </>
      )}
    </DetailDrawer>
  );
}
