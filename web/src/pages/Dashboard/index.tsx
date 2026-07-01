import { useNavigate } from 'react-router-dom';
import { Table, List, Spin, Empty, Skeleton, Tag, Badge, Tooltip } from 'antd';
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
import Panel from '@/components/Panel';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import ReturnTag from '@/components/ReturnTag';
import ScoreBar from '@/components/ScoreBar';
import { usePriceStream } from '@/hooks/usePriceStream';
import { useMarketStream } from '@/hooks/useMarketStream';
import type { NewsArticle, SentimentLabel } from '@/types/news';
import dayjs from 'dayjs';

const SENTIMENT_COLORS: Record<SentimentLabel, string> = {
  positive: '#52c41a',
  neutral: '#8c8c8c',
  negative: '#f5222d',
};

const SENTIMENT_LABELS: Record<SentimentLabel, string> = {
  positive: '看多',
  neutral: '中性',
  negative: '看空',
};

const IMPORTANCE_COLOR = 'var(--color-warning-bright)';

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
      onClick={() => onOpen(article.id)}
      style={{
        padding: '10px 0',
        borderBottom: '1px solid var(--border-default)',
        cursor: 'pointer',
        transition: 'background var(--transition-fast)',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = 'var(--bg-hover)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = 'transparent';
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          fontSize: 11,
          color: 'var(--text-tertiary)',
          marginBottom: 4,
        }}
      >
        <span>{article.source}</span>
        <span style={{ color: 'var(--text-muted)' }}>·</span>
        <Tooltip title={dayjs(article.published_at).format('YYYY-MM-DD HH:mm')}>
          <span>{formatRelative(article.published_at)}</span>
        </Tooltip>
        {article.importance ? (
          <span style={{ marginLeft: 'auto', letterSpacing: 1 }}>
            {Array.from({ length: 5 }).map((_, i) => (
              <StarFilled
                key={i}
                style={{
                  color: i < filled ? IMPORTANCE_COLOR : 'var(--text-muted)',
                  opacity: i < filled ? 1 : 0.4,
                  fontSize: 9,
                  marginRight: 1,
                }}
              />
            ))}
          </span>
        ) : null}
      </div>
      <div
        style={{
          fontSize: 13,
          color: 'var(--text-primary)',
          lineHeight: 1.5,
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
          marginBottom: 4,
        }}
      >
        {article.title}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        {article.symbols.slice(0, 4).map((s) => (
          <Tag key={`${s.symbol}-${s.match_type}`} style={{ margin: 0, fontSize: 10 }}>
            {s.symbol}
          </Tag>
        ))}
        <span style={{ flex: 1 }} />
        {article.sentiment_label && (
          <Badge
            color={SENTIMENT_COLORS[article.sentiment_label]}
            text={
              <span
                style={{
                  fontSize: 11,
                  color: SENTIMENT_COLORS[article.sentiment_label],
                  fontWeight: 500,
                }}
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
          style={{
            fontSize: 'var(--text-body-size)',
            fontWeight: v <= 3 ? 700 : 500,
            color: v <= 3 ? 'var(--accent)' : 'var(--text-secondary)',
            fontFamily: 'var(--font-mono)',
          }}
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
          <ArrowUpOutlined style={{ color: 'var(--color-rise)', fontSize: 'var(--text-body-size)' }} />
        ) : (
          <ArrowDownOutlined style={{ color: 'var(--color-fall)', fontSize: 'var(--text-body-size)' }} />
        ),
    },
  ];

  return (
    <div>
      <h1
        style={{
          fontSize: 'var(--text-h1-size)',
          fontWeight: 500,
          color: 'var(--text-primary)',
          margin: '0 0 8px',
          letterSpacing: '-0.03em',
        }}
      >
        首页看板
      </h1>
      <p
        style={{
          margin: '0 0 32px',
          color: 'var(--text-tertiary)',
          fontSize: 'var(--text-body-size)',
        }}
      >
        综合评分、收藏与标的池概览 · {new Date().toISOString().slice(0, 10)}
      </p>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          borderTop: '1px solid var(--border-default)',
          borderBottom: '1px solid var(--border-default)',
          marginBottom: '32px',
        }}
      >
        {[
          { title: '标的总数', value: stats?.etf_count ?? 0, suffix: undefined, onClick: () => navigate('/etfs') },
          { title: '评分覆盖', value: stats?.score_count ?? 0, suffix: `/ ${stats?.etf_count ?? 0}`, onClick: () => navigate('/scores') },
          { title: '分类数', value: stats?.category_count ?? 0, suffix: undefined },
          { title: '评分模板', value: stats?.template_count ?? 0, suffix: undefined, onClick: () => navigate('/scores') },
        ].map((item, i) => (
          <div
            key={item.title}
            onClick={item.onClick}
            style={{
              padding: '24px 20px',
              cursor: item.onClick ? 'pointer' : 'default',
              borderRight: i < 3 ? '1px solid var(--border-default)' : 'none',
              transition: 'background var(--transition-fast)',
            }}
            onMouseEnter={(e) => {
              if (item.onClick) e.currentTarget.style.background = 'var(--bg-hover)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'transparent';
            }}
          >
            <div
              style={{
                fontSize: 'var(--text-label-size)',
                color: 'var(--text-tertiary)',
                fontWeight: 500,
                marginBottom: '14px',
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
              }}
            >
              {item.title}
            </div>
            {statsLoading ? (
              <div
                style={{
                  height: '36px',
                  width: '80px',
                  background: 'var(--bg-hover)',
                  borderRadius: 'var(--radius-md)',
                  animation: 'pulse 1.5s ease-in-out infinite',
                }}
              />
            ) : (
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
                <span
                  style={{
                    fontSize: 'var(--text-data-xl-size)',
                    fontWeight: 400,
                    color: 'var(--text-primary)',
                    lineHeight: 1.1,
                    fontFamily: 'var(--font-mono)',
                    letterSpacing: '-0.02em',
                  }}
                >
                  {item.value}
                </span>
                {item.suffix && (
                  <span
                    style={{
                      fontSize: 'var(--text-small-size)',
                      color: 'var(--text-tertiary)',
                      fontWeight: 500,
                    }}
                  >
                    {item.suffix}
                  </span>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      <div style={{ marginBottom: '32px' }}>
        <h2
          style={{
            fontSize: 'var(--text-h4-size)',
            fontWeight: 500,
            color: 'var(--text-primary)',
            margin: '0 0 16px',
            letterSpacing: '-0.02em',
          }}
        >
          实时行情
        </h2>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            borderTop: '1px solid var(--border-default)',
            borderBottom: '1px solid var(--border-default)',
          }}
        >
          {INDEX_CODES.map((code, i) => {
            const tick = marketLatest[code] ?? (prices[code]
              ? { ...prices[code], ts: 0, name: undefined, market: undefined }
              : undefined);
            return (
              <div
                key={code}
                style={{
                  padding: '20px 16px',
                  borderRight: i < 3 ? '1px solid var(--border-default)' : 'none',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: '12px',
                  }}
                >
                  <span
                    style={{
                      fontSize: 'var(--text-label-size)',
                      color: 'var(--text-tertiary)',
                      fontWeight: 500,
                      letterSpacing: '0.12em',
                      textTransform: 'uppercase',
                    }}
                  >
                    {code}
                  </span>
                  {i === 0 ? (
                    <Tooltip
                      title={marketConnected ? 'SSE 已连接，3 秒刷新' : 'SSE 未连接，正在重连'}
                    >
                      <span
                        aria-label={marketConnected ? '实时连接中' : '连接断开'}
                        style={{
                          display: 'inline-block',
                          width: 6,
                          height: 6,
                          borderRadius: '50%',
                          background: marketConnected ? 'var(--color-rise, #52c41a)' : 'var(--text-muted)',
                        }}
                      />
                    </Tooltip>
                  ) : null}
                </div>
                <div
                  style={{
                    fontSize: 'var(--text-data-lg-size)',
                    fontWeight: 400,
                    color: 'var(--text-primary)',
                    fontFamily: 'var(--font-mono)',
                    lineHeight: 1.2,
                  }}
                >
                  {tick ? tick.price.toFixed(2) : '-'}
                </div>
                <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
                  {tick ? (
                    <>
                      <ReturnTag value={tick.change_pct} />
                      {tick.ts ? (
                        <Tooltip title={dayjs(tick.ts).format('YYYY-MM-DD HH:mm:ss')}>
                          <span
                            style={{
                              fontSize: 'var(--text-small-size)',
                              color: 'var(--text-tertiary)',
                              fontFamily: 'var(--font-mono)',
                            }}
                          >
                            {dayjs(tick.ts).format('MM-DD HH:mm')}
                          </span>
                        </Tooltip>
                      ) : null}
                    </>
                  ) : (
                    <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>
                      暂无数据
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* News row: hot news + favorites news */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '28px',
          marginBottom: '32px',
        }}
      >
        <Panel
          variant="minimal"
          title={
            <span>
              <FireOutlined style={{ marginRight: 'var(--space-1-5)', color: 'var(--accent)' }} />
              今日热点
            </span>
          }
          extra={
            <span
              style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)', cursor: 'pointer' }}
              onClick={() => navigate('/news')}
            >
              查看全部 →
            </span>
          }
        >
          {hotNewsLoading ? (
            <Skeleton active paragraph={{ rows: 5 }} />
          ) : !hotNews || hotNews.length === 0 ? (
            <Empty description="暂无重要资讯" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ padding: '24px 0' }} />
          ) : (
            hotNews.map((a) => (
              <NewsRow key={a.id} article={a} onOpen={(id) => navigate(`/news/${id}`)} />
            ))
          )}
        </Panel>

        <Panel
          variant="minimal"
          title={
            <span>
              <ReadOutlined style={{ marginRight: 'var(--space-1-5)' }} />
              自选股动态
            </span>
          }
          extra={
            favCount > 0 ? (
              <span
                style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)', cursor: 'pointer' }}
                onClick={() => navigate('/news')}
              >
                查看全部 →
              </span>
            ) : undefined
          }
        >
          {favNewsLoading ? (
            <Skeleton active paragraph={{ rows: 5 }} />
          ) : favCount === 0 ? (
            <Empty
              description="收藏自选股后，这里会汇总相关新闻"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              style={{ padding: '24px 0' }}
            />
          ) : !favoritesNews || favoritesNews.length === 0 ? (
            <Empty description="暂无自选股相关资讯" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ padding: '24px 0' }} />
          ) : (
            favoritesNews.map((a) => (
              <NewsRow key={a.id} article={a} onOpen={(id) => navigate(`/news/${id}`)} />
            ))
          )}
        </Panel>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.55fr 1fr', gap: '28px' }}>
        <Panel
          variant="minimal"
          title="综合评分 Top 10"
          extra={<span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)', cursor: 'pointer' }} onClick={() => navigate('/scores')}>查看全部 →</span>}
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

        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <Panel
            variant="minimal"
            title="我的收藏"
            extra={favCount > 0 ? <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)', cursor: 'pointer' }} onClick={() => navigate('/etfs')}>查看全部 →</span> : undefined}
          >
            {favLoading ? (
              <div style={{ textAlign: 'center', padding: '40px 0' }}><Spin /></div>
            ) : favCount === 0 ? (
              <div style={{ textAlign: 'center', padding: '44px 0', color: 'var(--text-tertiary)' }}>
                <div style={{ fontSize: 'var(--text-body-size)', marginBottom: 4 }}>暂无收藏的标的</div>
                <div style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-muted)' }}>在详情页点击收藏，这里会显示你关注的标的</div>
              </div>
            ) : (
              <List
                dataSource={favorites}
                renderItem={(item: any) => (
                  <List.Item onClick={() => navigate(`/etfs/${item.etf_code}`)} style={{ padding: '12px 0', cursor: 'pointer' }}>
                    <List.Item.Meta
                      title={<div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}><InstrumentCodeTag code={item.etf_code} name={item.etf_name} /></div>}
                      description={
                        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginTop: 'var(--space-1)' }}>
                          <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>{item.category}</span>
                          <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-muted)' }}>|</span>
                          <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>{item.market}</span>
                        </div>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Panel>

          <Panel
            variant="minimal"
            title="我的标的池"
            extra={(pools?.length || 0) > 0 ? <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)', cursor: 'pointer' }} onClick={() => navigate('/pools')}>查看全部 →</span> : undefined}
          >
            {poolsLoading ? (
              <div style={{ textAlign: 'center', padding: '40px 0' }}><Spin /></div>
            ) : (pools?.length || 0) === 0 ? (
              <div style={{ textAlign: 'center', padding: '44px 0', color: 'var(--text-tertiary)' }}>
                <div style={{ fontSize: 'var(--text-body-size)', marginBottom: 4 }}>暂无标的池</div>
                <div style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-muted)' }}>在标的池管理中创建池并添加标的，这里会汇总展示</div>
              </div>
            ) : (
              <List
                dataSource={pools?.slice(0, 6) || []}
                renderItem={(pool: any) => (
                  <List.Item onClick={() => navigate(`/pools/${pool.id}`)} style={{ padding: '12px 0', cursor: 'pointer' }}>
                    <List.Item.Meta
                      title={
                        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                          <FolderOpenOutlined style={{ color: 'var(--accent)', fontSize: 'var(--text-body-size)' }} />
                          <span style={{ fontSize: 'var(--text-body-size)', color: 'var(--text-primary)', fontWeight: 500 }}>{pool.name}</span>
                        </div>
                      }
                      description={
                        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginTop: 'var(--space-1)' }}>
                          <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>{pool.members?.length || 0} 只标的</span>
                          {pool.description && (
                            <>
                              <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-muted)' }}>|</span>
                              <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>{pool.description}</span>
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
      </div>
    </div>
  );
}
