import { Badge, Space, Tag, Tooltip } from 'antd';
import {
  StarFilled,
  LinkOutlined,
  LikeOutlined,
  MessageOutlined,
  ShareAltOutlined,
  EyeOutlined,
  BookFilled,
  BookOutlined,
} from '@ant-design/icons';
import { SENTIMENT_COLORS, SENTIMENT_LABELS } from '@/utils/sentiment';
import type {
  NewsArticle,
  NewsMarket,
  ImportanceLevel,
} from '@/types/news';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import ThemeTag from '@/components/ThemeTag';
import type { ThemeTagVariant } from '@/components/ThemeTag';
import {
  formatDateTimeSeconds,
  formatRelative as formatRelativeTz,
} from '@/utils/datetime';
import './NewsCard.css';

/**
 * Shared news-article card — extracted from ``pages/News/index.tsx``
 * (2026-08-02, learning-center sprint) so the /learning 知识库 feed can
 * render the exact same card without duplicating ~200 lines.
 *
 * The card styles (``.ad-news-card*``) live in the global stylesheet
 * ``styles/global/pages-tools.css``, so no CSS moves with this file.
 *
 * This module also hosts the shared news meta helpers the detail
 * drawer needs (``NewsDetailDrawer.tsx`` imports them from here):
 * ``SOURCE_LABELS`` / ``MARKET_BADGE`` / ``EventCategoryTag`` /
 * ``ImportanceStars`` / ``formatBigNumber``.
 */

export const MARKET_BADGE: Record<NewsMarket, { variant: ThemeTagVariant; label: string }> = {
  cn_a: { variant: 'neutral', label: 'A 股' },
  us: { variant: 'accent', label: '美股' },
  crypto: { variant: 'warning', label: '加密' },
  global: { variant: 'accent', label: '全球' },
};

/**
 * Map an ``event_category`` value to a visual tag variant. Political /
 * macro categories get a coloured Tag so the eye lands on them
 * immediately in a feed dominated by earnings headlines; the legacy
 * categories stay neutral grey.
 */
const EVENT_CATEGORY_VARIANT: Record<string, ThemeTagVariant> = {
  geopolitics: 'warning',
  central_bank: 'neutral',
  election: 'neutral',
  trade_war: 'error',
  sanction: 'neutral',
  earnings: 'default',
  regulation: 'default',
  macro: 'default',
};

const EVENT_CATEGORY_LABELS: Record<string, string> = {
  geopolitics: '地缘',
  central_bank: '央行',
  election: '选举',
  trade_war: '贸易战',
  sanction: '制裁',
  earnings: '财报',
  'm&a': '并购',
  product: '产品',
  macro: '宏观',
  regulation: '监管',
  guidance: '指引',
  analyst: '分析师',
  legal: '法律',
  rumor: '传闻',
  other: '其他',
};

/** Render an event_category as a coloured Tag (with Chinese label). */
export function EventCategoryTag({ value }: { value: string | null }) {
  if (!value) return null;
  const variant = EVENT_CATEGORY_VARIANT[value] ?? 'default';
  const label = EVENT_CATEGORY_LABELS[value] ?? value;
  return (
    <ThemeTag variant={variant} className="ad-event-tag">
      {label}
    </ThemeTag>
  );
}

export const SOURCE_LABELS: Record<string, { emoji: string; label: string }> = {
  xinhua: { emoji: '📰', label: '新华' },
  sina: { emoji: '📰', label: '新浪财经' },
  sina_finance: { emoji: '📰', label: '新浪财经' },
  eastmoney: { emoji: '📊', label: '东方财富' },
  cls: { emoji: '⚡', label: '财联社' },
  wallstreetcn: { emoji: '📈', label: '华尔街见闻' },
  chinanews_finance: { emoji: '📰', label: '中新网财经' },
  xueqiu: { emoji: '📈', label: '雪球' },
  reddit: { emoji: '🦍', label: 'Reddit' },
  coindesk: { emoji: '🪙', label: 'CoinDesk' },
  cointelegraph: { emoji: '🪙', label: 'Cointelegraph' },
  bloomberg: { emoji: '🏛', label: 'Bloomberg' },
  reuters: { emoji: '🏛', label: '路透' },
  marketwatch: { emoji: '📈', label: 'MarketWatch' },
  zerohedge: { emoji: '📉', label: 'ZeroHedge' },
  seekingalpha: { emoji: '🔍', label: 'Seeking Alpha' },
  ft: { emoji: '📰', label: '金融时报' },
  investing: { emoji: '💹', label: 'Investing.com' },
  decrypt: { emoji: '🪙', label: 'Decrypt' },
  federal_reserve: { emoji: '🏛', label: '美联储' },
  ecb: { emoji: '🏛', label: '欧洲央行' },
  bankofengland: { emoji: '🏛', label: '英格兰银行' },
  bbc_business: { emoji: '📺', label: 'BBC 商业' },
  arxiv_qfin: { emoji: '📐', label: 'arXiv 量化金融' },
};

const IMPORTANCE_COLOR = 'var(--color-warning-bright)';

/** Approximate "x 分钟前" / "x 小时前" formatter. UTC-safe — see ``utils/datetime``. */
function formatRelative(iso: string): string {
  return formatRelativeTz(iso);
}

/** Render a 1..5 star row. */
export function ImportanceStars({ level }: { level: ImportanceLevel | null }) {
  if (!level) return null;
  const filled = Math.max(0, Math.min(5, level));
  return (
    <Tooltip title={`重要性 ${level}/5`}>
      <span className="ad-text-small ad-text-tertiary ad-letter-spacing">
        {Array.from({ length: 5 }).map((_, i) => (
          <StarFilled
            key={i}
            className="ad-text-xs ad-mr-1"
            style={{
              color: i < filled ? IMPORTANCE_COLOR : 'var(--text-muted)',
              opacity: i < filled ? 1 : 0.4,
            }}
          />
        ))}
      </span>
    </Tooltip>
  );
}

export function formatBigNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

/** 学习中心 P2：难度标签（入门/进阶）——只在知识库语境渲染。 */
const DIFFICULTY_LABELS: Record<string, string> = {
  beginner: '入门',
  advanced: '进阶',
};

/** Single article card in the feed. */
export default function NewsCard({
  article,
  onOpen,
  onPickSymbol,
  showBookmark = false,
  onToggleBookmark,
  showDifficulty = false,
}: {
  article: NewsArticle;
  onOpen: (a: NewsArticle) => void;
  onPickSymbol: (sym: string) => void;
  /**
   * 学习中心 P1（2026-08-02）：是否渲染收藏（稍后读）按钮。
   * 只在知识库语境传 true——/news 页不传，卡片保持原样。
   * 状态来自 ``article.bookmarked``（/learning/feed LEFT JOIN
   * user_article_state 返回），点击通过 ``onToggleBookmark`` 上抛，
   * 由父组件调 API + 乐观更新（卡片自身不持有 API client）。
   */
  showBookmark?: boolean;
  onToggleBookmark?: (a: NewsArticle) => void;
  /**
   * 学习中心 P2（2026-08-02）：是否渲染难度标签（入门/进阶）。
   * 数据来自 ``article.difficulty_default``（源级打标，/learning
   * 端点 JOIN news_source_meta 返回）；null 时不渲染。与
   * showBookmark 同模式——/news 页不传，默认零变化。
   */
  showDifficulty?: boolean;
}) {
  // Fallback for unmapped sources shows the raw key only — the
  // sourceOptions dropdown label carries a "(count)" suffix that must
  // never leak into the card meta row.
  const source = SOURCE_LABELS[article.source] ?? {
    emoji: '🔗',
    label: article.source,
  };
  const market = MARKET_BADGE[article.market];
  const sentiment = article.sentiment_label;
  // 收藏/已读布尔只在 /learning 端点里返回（/news 没有这两个字段），
  // 缺省视为 false。
  const bookmarked = article.bookmarked ?? false;
  const isRead = article.read ?? false;
  // 难度标签：仅 showDifficulty 且源已打标（beginner/advanced）时渲染。
  const difficulty =
    showDifficulty && article.difficulty_default
      ? article.difficulty_default
      : null;

  return (
    // Custom button: a semantic ``<article>`` cannot carry
    // ``role="button"`` (jsx-a11y error), so the card is a plain div
    // with the full button contract (role + tabIndex + Enter/Space).
    <div
      className="ad-news-card"
      role="button"
      tabIndex={0}
      aria-label={article.title_zh ?? article.title}
      onClick={() => onOpen(article)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onOpen(article);
        }
      }}
    >
      {/* Row 1: source · market · time · importance */}
      <div className="ad-news-card__meta">
        <span>{source.emoji} {source.label}</span>
        <span className="ad-text-muted">·</span>
        {market && <ThemeTag variant={market.variant} className="ad-detail-tag">{market.label}</ThemeTag>}
        <EventCategoryTag value={article.event_category} />
        {/* 难度标签（P2）——入门绿 / 进阶橙，颜色走 theme.css token
            （NewsCard.css .ad-news-card__difficulty--*）。 */}
        {difficulty && (
          <span
            className={`ad-news-card__difficulty ad-news-card__difficulty--${difficulty}`}
          >
            {DIFFICULTY_LABELS[difficulty] ?? difficulty}
          </span>
        )}
        <span className="ad-flex-1" />
        <Tooltip title={formatDateTimeSeconds(article.published_at)}>
          <span>{formatRelative(article.published_at)}</span>
        </Tooltip>
        <ImportanceStars level={article.importance} />
        {/* 收藏（稍后读）按钮——只在知识库语境渲染（showBookmark）。
            已收藏用实心高亮；点击 stopPropagation 避免触发卡片打开。 */}
        {showBookmark && (
          <Tooltip title={bookmarked ? '取消收藏' : '收藏（稍后读）'}>
            <button
              type="button"
              className={`ad-news-card__bookmark ${bookmarked ? 'ad-news-card__bookmark--active' : ''}`}
              aria-label={bookmarked ? '取消收藏' : '收藏（稍后读）'}
              aria-pressed={bookmarked}
              onClick={(e) => {
                e.stopPropagation();
                onToggleBookmark?.(article);
              }}
              onKeyDown={(e) => e.stopPropagation()}
            >
              {bookmarked ? <BookFilled /> : <BookOutlined />}
            </button>
          </Tooltip>
        )}
      </div>

      {/* Title — Chinese-first: the ingestion pipeline auto-translates
          non-Chinese articles into ``title_zh``; when present we render
          it with a small 「译」 badge and keep the original title one
          hover away (Tooltip). 已读文章（/learning feed 的 read 布尔）
          标题降透明度，视觉上退到背景层。 */}
      <div
        className={`ad-news-card__title ${isRead ? 'ad-news-card__title--read' : ''}`}
      >
        {article.title_zh ?? article.title}
        {article.title_zh && (
          <Tooltip title={`原标题：${article.title}`}>
            <span className="ad-news-card__translated-badge">译</span>
          </Tooltip>
        )}
      </div>

      {/* AI one-sentence Chinese digest (方向 D) — rendered on mobile
          AND desktop (the body preview drops out on mobile, but this
          line stays: it is the feed's main scanning aid). Renders
          nothing when the drain job hasn't summarized the row yet. */}
      {article.summary_zh && (
        <div className="ad-news-card__ai-summary">{article.summary_zh}</div>
      )}

      {/* Body preview */}
      {article.body && (
        <div className="ad-news-card__body">
          {article.body}
        </div>
      )}

      {/* Row 3: symbols + sentiment + engagement */}
      <div className="ad-news-card__footer">
        <Space size={8} wrap>
          {article.symbols.slice(0, 6).map((s) => (
            <Tag
              key={`${s.symbol}-${s.match_type}`}
              color="default"
              className="ad-mr-1 ad-chip-tag"
              role="button"
              tabIndex={0}
              aria-label={`筛选 ${s.symbol}`}
              onClick={(e) => {
                e.stopPropagation();
                onPickSymbol(s.symbol);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  e.stopPropagation();
                  onPickSymbol(s.symbol);
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

        <span className="ad-flex-1" />

        {sentiment && (
          <Tooltip
            title={
              article.sentiment_score != null
                ? `分数 ${article.sentiment_score.toFixed(2)} · 置信度 ${(
                    (article.sentiment_confidence ?? 0) * 100
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

        {article.engagement?.likes != null && (
          <span className="ad-news-card__engagement">
            <LikeOutlined /> {formatBigNumber(article.engagement.likes)}
          </span>
        )}
        {article.engagement?.comments != null && (
          <span className="ad-news-card__engagement">
            <MessageOutlined /> {formatBigNumber(article.engagement.comments)}
          </span>
        )}
        {article.engagement?.shares != null && (
          <span className="ad-news-card__engagement">
            <ShareAltOutlined /> {formatBigNumber(article.engagement.shares)}
          </span>
        )}
        {article.engagement?.views != null && (
          <span className="ad-news-card__engagement">
            <EyeOutlined /> {formatBigNumber(article.engagement.views)}
          </span>
        )}
        <Tooltip title="查看原文">
          <a
            href={article.url}
            target="_blank"
            rel="noopener noreferrer"
            className="ad-news-card__link"
            aria-label={`原文链接: ${article.title}`}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
          >
            <LinkOutlined />
          </a>
        </Tooltip>
      </div>
    </div>
  );
}
