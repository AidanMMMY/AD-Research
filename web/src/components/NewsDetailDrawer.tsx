import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge, Button, Segmented, Space, Tag, Tooltip } from 'antd';
import {
  LinkOutlined,
  LikeOutlined,
  MessageOutlined,
  ShareAltOutlined,
  TranslationOutlined,
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
 *
 * Bilingual rendering (2026-08-02): non-Chinese articles are
 * auto-translated at ingestion (``title_zh`` / ``translated_zh``), so
 * the drawer is Chinese-first like the cards — Chinese title with the
 * original as a secondary line, translated body by default with a
 * 中文/原文 switch. While the pipeline hasn't reached a row yet, the
 * original body stays visible under a slim "翻译进行中" notice (never
 * an empty pane), mirroring ``pages/News/detail.tsx``.
 */
export default function NewsDetailDrawer({
  article,
  onClose,
  onPickSymbol,
  onRead,
}: {
  article: NewsArticle | null;
  onClose: () => void;
  onPickSymbol: (sym: string) => void;
  /**
   * 学习中心 P1（2026-08-02）：抽屉打开（article 由 null 变为非空）
   * 时触发一次，供父组件标记已读。只在知识库语境传——/news 页不传，
   * 不产生任何额外请求。父组件需自行做幂等/乐观更新。
   */
  onRead?: (a: NewsArticle) => void;
}) {
  const navigate = useNavigate();
  // Keep the last non-null article so the exit animation still has
  // content to render after ``onClose`` clears the selection.
  const [lastArticle, setLastArticle] = useState<NewsArticle | null>(null);
  useEffect(() => {
    if (article) setLastArticle(article);
  }, [article]);
  // 打开即视为已读：article 由 null → 非空时回调一次（父组件幂等，
  // 重复打开同一篇不会刷新后端首次时间戳）。
  useEffect(() => {
    if (article) onRead?.(article);
    // 只关心"打开"这一刻；onRead 由父组件 useCallback 稳定化。
  }, [article, onRead]);
  const shown = article ?? lastArticle;

  // Bilingual state (mirrors pages/News/detail.tsx, 2026-07-26 pattern).
  const [viewMode, setViewMode] = useState<'zh' | 'original'>('zh');
  // Reset to the Chinese view whenever a different article is opened.
  useEffect(() => {
    setViewMode('zh');
  }, [shown?.id]);
  const CHINESE_LANGS = ['zh', 'cn', 'zh-cn', 'zh-hans', 'zh-hant', 'zh-tw', 'zh-hk'];
  const isNonChinese = shown
    ? !CHINESE_LANGS.includes((shown.language || '').toLowerCase())
    : false;
  const hasTranslation = !!shown?.translated_zh;
  const showChineseBody = viewMode === 'zh' && hasTranslation;

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
      title={shown ? (shown.title_zh ?? shown.title) : undefined}
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

          {/* Original title as secondary line (Chinese-first header,
              same as the cards). */}
          {shown.title_zh && shown.title_zh !== shown.title && (
            <div className="ad-text-small ad-text-tertiary ad-mt-2">
              原文标题：{shown.title}
            </div>
          )}

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

          {/* Language toolbar: full-article 中文/原文 switch for
              non-Chinese sources (mirrors pages/News/detail.tsx). Sits
              directly above the body it controls. */}
          {isNonChinese && (
            <div className="news-lang-toolbar ad-mt-4">
              <Segmented
                value={viewMode}
                onChange={(v) => setViewMode(v as 'zh' | 'original')}
                options={[
                  { label: '中文译文', value: 'zh' },
                  { label: `${(shown.language || 'en').toUpperCase()} 原文`, value: 'original' },
                ]}
              />
              <span className="news-lang-toolbar__meta">
                <TranslationOutlined />
                AI 翻译
              </span>
            </div>
          )}

          {/* Translation-pending notice: Chinese was asked for (default)
              but the pipeline hasn't produced one yet. Keep the original
              body visible underneath — never an empty pane. */}
          {isNonChinese && viewMode === 'zh' && !hasTranslation && (
            <div className="news-translation-notice">
              <span className="news-translation-notice__text">
                中文译文尚未就绪，后台翻译中（通常入库后几分钟内完成）
              </span>
            </div>
          )}

          {/* Body — Chinese view renders the ingestion-time AI
              translation; 原文 view prefers the cleaned full text stored
              locally (``full_content``), falling back to the crawler's
              intro body when no fetch has landed yet. */}
          {showChineseBody ? (
            <div className="news-drawer-body ad-mt-4">
              <Markdown source={shown.translated_zh!} />
            </div>
          ) : shown.full_content ? (
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
