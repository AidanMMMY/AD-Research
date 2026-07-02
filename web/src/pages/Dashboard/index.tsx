import { useNavigate } from 'react-router-dom';
import { Table, List, Spin, Skeleton, Tag, Badge, Tooltip } from 'antd';
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
  FolderOpenOutlined,
  FireOutlined,
  StarFilled,
  ReadOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useScores } from '@/hooks/useScores';
import { useFavorites } from '@/hooks/useFavorites';
import { usePoolList } from '@/hooks/usePoolDetail';
import { statsApi } from '@/api/stats';
import { newsApi } from '@/api/news';
import PageShell from '@/components/PageShell';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import SectionHeading from '@/components/SectionHeading';
import StatCard from '@/components/StatCard';
import EmptyState from '@/components/EmptyState';
import Panel from '@/components/Panel';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import ReturnTag from '@/components/ReturnTag';
import ScoreBar from '@/components/ScoreBar';
import TickerTape from '@/components/TickerTape';
import { usePriceStream } from '@/hooks/usePriceStream';
import { useMarketStream } from '@/hooks/useMarketStream';
import type { NewsArticle, SentimentLabel } from '@/types/news';
import dayjs from 'dayjs';

const SENTIMENT_COLORS: Record<SentimentLabel, string> = {
  positive: 'var(--color-rise)',
  neutral: 'var(--text-tertiary)',
  negative: 'var(--color-fall)',
};

const SENTIMENT_LABELS: Record<SentimentLabel, string> = {
  positive: '看多',
  neutral: '中性',
  negative: '看空',
};

function formatRelative(iso: string): string {
  const t = dayjs(iso);
  if (!t.isValid()) return '';
  const diff = dayjs().diff(t, 'minute');
  if (diff < 60) return diff < 1 ? '刚刚' : `${diff} 分钟前`;
  const h = Math.floor(diff / 60);
  if (h < 24) return `${h} 小时前`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d} 天前`;
  return t.format('MM-DD');
}

/** Compact news row used in dashboard cards. */
function NewsRow({
  article,
  onOpen,
}: {
  article: NewsArticle;
  onOpen: (id: number) => void;
}) {
  const filled = article.importance ? Math.max(0, Math.min(5, article.importance)) : 0;
  return (
    <div
      className="dashboard-news-row"
      onClick={() => onOpen(article.id)}
    >
      <div className="dashboard-news-row__meta">
        <span>{article.source}</span>
        <span className="dashboard-news-row__divider">·</span>
        <Tooltip title={dayjs(article.published_at).format('YYYY-MM-DD HH:mm')}>
          <span>{formatRelative(article.published_at)}</span>
        </Tooltip>
        {article.importance ? (
          <span className="dashboard-news-row__importance">
            {Array.from({ length: 5 }).map((_, i) => (
              <StarFilled
                key={i}
                className={`dashboard-news-row__star ${
                  i < filled ? 'dashboard-news-row__star--filled' : 'dashboard-news-row__star--empty'
                }`}
              />
            ))}
          </span>
        ) : null}
      </div>
      <div className="dashboard-news-row__title">{article.title}</div>
      <div className="dashboard-news-row__tags">
        {article.symbols.slice(0, 4).map((s) => (
          <Tag key={`${s.symbol}-${s.match_type}`} className="dashboard-news-row__tag">
            {s.symbol}
          </Tag>
        ))}
        <span className="dashboard-news-row__spacer" />
        {article.sentiment_label && (
          <Badge
            color={SENTIMENT_COLORS[article.sentiment_label]}
            text={
              <span
                className="dashboard-news-row__sentiment"
                style={{ color: SENTIMENT_COLORS[article.sentiment_label] }}
              >
                {SENTIMENT_LABELS[article.sentiment_label]}
              </span>
            }
          />
        )}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { data: scoresData } = useScores({ limit: 10 });
  const { favorites, count: favCount, isLoading: favLoading } = useFavorites(10);
  const { data: pools, isLoading: poolsLoading } = usePoolList();
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['stats-overview'],
    queryFn: () => statsApi.overview().then((r) => r.data),
    staleTime: 60_000,
  });

  // Hot news: importance >= 4, latest 6.
  const { data: hotNews, isLoading: hotNewsLoading } = useQuery({
    queryKey: ['dashboard-hot-news'],
    queryFn: () =>
      newsApi
        .list({ importance_min: 4, page: 1, page_size: 6 })
        .then((r) => r.data.items),
    staleTime: 60_000,
  });

  // Favorites news: pull each favorite's news, dedup, sort by recency.
  const { data: favoritesNews, isLoading: favNewsLoading } = useQuery({
    queryKey: ['dashboard-favorites-news', favorites?.map((f: any) => f.etf_code).join(',')],
    queryFn: async () => {
      if (!favorites || favorites.length === 0) return [] as NewsArticle[];
      const codes = favorites.slice(0, 5).map((f: any) => f.etf_code);
      const results = await Promise.all(
        codes.map((code: string) =>
          newsApi
            .list({ symbol: code, page: 1, page_size: 4 })
            .then((r) => r.data.items)
            .catch(() => [] as NewsArticle[])
        )
      );
      const merged = results
        .flat()
        .sort(
          (a, b) =>
            new Date(b.published_at).getTime() - new Date(a.published_at).getTime()
        );
      // Dedup by id.
      const seen = new Set<number>();
      const dedup: NewsArticle[] = [];
      for (const n of merged) {
        if (seen.has(n.id)) continue;
        seen.add(n.id);
        dedup.push(n);
      }
      return dedup.slice(0, 6);
    },
    enabled: favCount > 0,
    staleTime: 60_000,
  });

  const INDEX_CODES = ['510300.SH', '159915.SZ', 'SPY.US', 'BTC.US'];
  const { prices } = usePriceStream(INDEX_CODES);
  // MarketStream supersedes the price stream for the live tickers: it
  // surfaces timestamps and the upstream connection state, so the four
  // dashboard cards can show "updated 3s ago" hints.
  const { latest: marketLatest, isConnected: marketConnected } = useMarketStream(INDEX_CODES);

  const scoreColumns = [
    {
      title: '排名',
      dataIndex: 'rank_overall',
      width: 70,
      render: (v: number) => (
        <span
          className={`tabular-nums dashboard-rank-cell ${v <= 3 ? 'dashboard-rank-cell--top3' : 'dashboard-rank-cell--normal'}`}
        >
          {v}
        </span>
      ),
    },
    {
      title: '标的',
      render: (_: unknown, record: any) => (
        <InstrumentCodeTag code={record.etf_code} name={record.etf_name} />
      ),
    },
    {
      title: '评分',
      render: (_: unknown, record: any) => (
        <ScoreBar score={record.composite_score} size="small" />
      ),
      width: 160,
    },
    {
      title: '1月收益',
      render: (_: unknown, record: any) => <ReturnTag value={record.return_1m} />,
      width: 110,
    },
    {
      title: '趋势',
      width: 60,
      render: (_: unknown, record: any) =>
        record.return_1m >= 0 ? (
          <ArrowUpOutlined className="ad-icon-rise" />
        ) : (
          <ArrowDownOutlined className="ad-icon-fall" />
        ),
    },
  ];

  return (
    <PageShell maxWidth="full">
      <TickerTape limit={20} />
      <header className="masthead">
        <div className="masthead-dateline">
          AD-RESEARCH ·{' '}
          {new Date().toLocaleDateString('zh-CN', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
          })}{' '}
          · A股全市场综述
        </div>
        <h1 className="display-heading masthead-title">首页看板</h1>
        <p className="masthead-kicker">
          综合评分 · 收藏 · 标的池概览 · {new Date().toISOString().slice(0, 10)}
        </p>
      </header>

      <ResponsiveGrid cols={4} gap="md" className="dashboard-section">
        {[
          { title: '标的总数', value: stats?.etf_count ?? 0, suffix: undefined, onClick: () => navigate('/etfs') },
          { title: '评分覆盖', value: stats?.score_count ?? 0, suffix: `/ ${stats?.etf_count ?? 0}`, onClick: () => navigate('/scores') },
          { title: '分类数', value: stats?.category_count ?? 0, suffix: undefined },
          { title: '评分模板', value: stats?.template_count ?? 0, suffix: undefined, onClick: () => navigate('/scores') },
        ].map((item) => (
          <StatCard
            key={item.title}
            title={item.title}
            value={item.value}
            suffix={item.suffix}
            loading={statsLoading}
            onClick={item.onClick}
          />
        ))}
      </ResponsiveGrid>

      <section className="dashboard-section">
        <SectionHeading title="实时行情" />
        <ResponsiveGrid cols={4} gap="md">
          {INDEX_CODES.map((code, i) => {
            const tick = marketLatest[code] ?? (prices[code]
              ? { ...prices[code], ts: 0, name: undefined, market: undefined }
              : undefined);
            return (
              <Panel key={code} variant="default" padding="md" className="dashboard-index-card">
                <div className="dashboard-index-card__header">
                  <span className="dashboard-index-card__code">{code}</span>
                  {i === 0 ? (
                    <Tooltip
                      title={marketConnected ? 'SSE 已连接，3 秒刷新' : 'SSE 未连接，正在重连'}
                    >
                      <span
                        aria-label={marketConnected ? '实时连接中' : '连接断开'}
                        className={`dashboard-index-card__dot ${marketConnected ? 'dashboard-index-card__dot--connected' : ''}`}
                      />
                    </Tooltip>
                  ) : null}
                </div>
                <div className="dashboard-index-card__price">
                  {tick ? tick.price.toFixed(2) : '-'}
                </div>
                <div className="dashboard-index-card__footer">
                  {tick ? (
                    <>
                      <ReturnTag value={tick.change_pct} />
                      {tick.ts ? (
                        <Tooltip title={dayjs(tick.ts).format('YYYY-MM-DD HH:mm:ss')}>
                          <span className="dashboard-index-card__timestamp">
                            {dayjs(tick.ts).format('MM-DD HH:mm')}
                          </span>
                        </Tooltip>
                      ) : null}
                    </>
                  ) : (
                    <span className="dashboard-index-card__empty">暂无数据</span>
                  )}
                </div>
              </Panel>
            );
          })}
        </ResponsiveGrid>
      </section>

      {/* News row: hot news + favorites news */}
      <ResponsiveGrid cols={2} gap="lg" className="dashboard-section">
        <Panel
          variant="default"
          title={
            <span>
              <FireOutlined className="ad-icon-accent" />
              今日热点
            </span>
          }
          extra={
            <span className="panel-extra-link" onClick={() => navigate('/news')}>
              查看全部 →
            </span>
          }
        >
          {hotNewsLoading ? (
            <Skeleton active paragraph={{ rows: 5 }} />
          ) : !hotNews || hotNews.length === 0 ? (
            <EmptyState title="暂无重要资讯" />
          ) : (
            hotNews.map((a) => (
              <NewsRow key={a.id} article={a} onOpen={(id) => navigate(`/news/${id}`)} />
            ))
          )}
        </Panel>

        <Panel
          variant="default"
          title={
            <span>
              <ReadOutlined className="ad-icon-leading" />
              自选股动态
            </span>
          }
          extra={
            favCount > 0 ? (
              <span className="panel-extra-link" onClick={() => navigate('/news')}>
                查看全部 →
              </span>
            ) : undefined
          }
        >
          {favNewsLoading ? (
            <Skeleton active paragraph={{ rows: 5 }} />
          ) : favCount === 0 ? (
            <EmptyState
              title="暂无收藏的标的"
              description="收藏自选股后，这里会汇总相关新闻"
            />
          ) : !favoritesNews || favoritesNews.length === 0 ? (
            <EmptyState title="暂无自选股相关资讯" />
          ) : (
            favoritesNews.map((a) => (
              <NewsRow key={a.id} article={a} onOpen={(id) => navigate(`/news/${id}`)} />
            ))
          )}
        </Panel>
      </ResponsiveGrid>

      <ResponsiveGrid cols={2} gap="lg" className="dashboard-score-grid dashboard-section">
        <Panel
          variant="default"
          title="综合评分 Top 10"
          extra={
            <span className="panel-extra-link" onClick={() => navigate('/scores')}>
              查看全部 →
            </span>
          }
        >
          <Table
            dataSource={scoresData?.items || []}
            columns={scoreColumns}
            rowKey="etf_code"
            size="small"
            scroll={{ x: 'max-content' }}
            pagination={false}
            showHeader={false}
            onRow={(record) => ({ onClick: () => navigate(`/etfs/${record.etf_code}`) })}
          />
        </Panel>

        <div className="dashboard-side-stack">
          <Panel
            variant="default"
            title="我的收藏"
            extra={
              favCount > 0 ? (
                <span className="panel-extra-link" onClick={() => navigate('/etfs')}>
                  查看全部 →
                </span>
              ) : undefined
            }
          >
            {favLoading ? (
              <div className="ad-text-center ad-py-7">
                <Spin />
              </div>
            ) : favCount === 0 ? (
              <EmptyState
                title="暂无收藏的标的"
                description="在详情页点击收藏，这里会显示你关注的标的"
              />
            ) : (
              <List
                dataSource={favorites}
                renderItem={(item: any) => (
                  <List.Item
                    onClick={() => navigate(`/etfs/${item.etf_code}`)}
                    className="dashboard-favorite-item"
                  >
                    <List.Item.Meta
                      title={
                        <div className="dashboard-favorite-item__title">
                          <InstrumentCodeTag code={item.etf_code} name={item.etf_name} />
                        </div>
                      }
                      description={
                        <div className="dashboard-favorite-item__desc">
                          <span>{item.category}</span>
                          <span className="ad-text-muted">|</span>
                          <span>{item.market}</span>
                        </div>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Panel>

          <Panel
            variant="default"
            title="我的标的池"
            extra={
              (pools?.length || 0) > 0 ? (
                <span className="panel-extra-link" onClick={() => navigate('/pools')}>
                  查看全部 →
                </span>
              ) : undefined
            }
          >
            {poolsLoading ? (
              <div className="ad-text-center ad-py-7">
                <Spin />
              </div>
            ) : (pools?.length || 0) === 0 ? (
              <EmptyState
                title="暂无标的池"
                description="在标的池管理中创建池并添加标的，这里会汇总展示"
              />
            ) : (
              <List
                dataSource={pools?.slice(0, 6) || []}
                renderItem={(pool: any) => (
                  <List.Item
                    onClick={() => navigate(`/pools/${pool.id}`)}
                    className="dashboard-pool-item"
                  >
                    <List.Item.Meta
                      title={
                        <div className="dashboard-pool-item__title">
                          <FolderOpenOutlined className="ad-icon-accent" />
                          <span className="dashboard-pool-item__name">{pool.name}</span>
                        </div>
                      }
                      description={
                        <div className="dashboard-pool-item__desc">
                          <span>{pool.members?.length || 0} 只标的</span>
                          {pool.description && (
                            <>
                              <span className="ad-text-muted">|</span>
                              <span>{pool.description}</span>
                            </>
                          )}
                        </div>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Panel>
        </div>
      </ResponsiveGrid>
    </PageShell>
  );
}
