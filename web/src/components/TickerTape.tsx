import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { analysisApi } from '@/api/analysis';
import { useMarketStream } from '@/hooks/useMarketStream';

export interface TickerTapeItem {
  code: string;
  name: string;
  /** Live price (from SSE) when available; otherwise null. */
  price: number | null;
  /** Live change pct (from SSE) when available; otherwise null. */
  change_pct: number | null;
}

interface RankingItem {
  etf_code: string;
  etf_name?: string | null;
  return_1m?: number | null;
}

interface TickerTapeProps {
  /** Maximum number of unique instruments to show. */
  limit?: number;
  /** Field used to drive the initial ordering. `return_1m` is the closest
   *  proxy for "today's biggest movers" since the ranking endpoint sorts on
   *  indicator fields rather than live change_pct. */
  sortBy?: 'return_1m' | 'return_3m' | 'return_1y';
  /** CSS animation duration in seconds. */
  durationSeconds?: number;
}

/**
 * Bloomberg-style horizontally scrolling ticker tape.
 *
 * Pulls top instruments from `/analysis/ranking` and overlays live price +
 * change_pct from the shared SSE `/stream/prices` connection. Renders the
 * track twice (concatenated) and uses a CSS translateX(-50%) keyframe so the
 * loop is seamless. Hover pauses; prefers-reduced-motion freezes the tape.
 *
 * Phase 2 (2026-07-05):
 * - 高度降到 32px（移动端 44px touch-friendly）。
 * - 去掉重边框，使用 `--bg-elevated` 背景 + `--radius-lg` 圆角。
 * - 价格 / 涨跌颜色全部走 `--color-rise` / `--color-fall` token，
 *   自动跟随 China/US 颜色约定切换与 light/dark 主题。
 */
export default function TickerTape({
  limit = 20,
  sortBy = 'return_1m',
  durationSeconds = 60,
}: TickerTapeProps) {
  const navigate = useNavigate();

  const { data: ranking } = useQuery({
    queryKey: ['ticker-tape-ranking', sortBy, limit],
    queryFn: async () => {
      const res = await analysisApi.ranking(sortBy, 'desc', limit);
      return (res.data.items || []) as unknown as RankingItem[];
    },
    staleTime: 60_000,
  });

  const codes = useMemo(
    () => (ranking || []).map((r) => r.etf_code).filter(Boolean),
    [ranking]
  );

  // Subscribe to live ticks for the same set so prices/change_pct update
  // every ~3 seconds. useMarketStream is shared with the rest of the page
  // via a single SSE connection.
  const { latest } = useMarketStream(codes);

  const items: TickerTapeItem[] = useMemo(() => {
    return (ranking || []).map((r) => {
      const tick = latest[r.etf_code];
      return {
        code: r.etf_code,
        name: r.etf_name || r.etf_code,
        price: tick ? tick.price : null,
        change_pct: tick ? tick.change_pct : null,
      };
    });
  }, [ranking, latest]);

  if (items.length === 0) return null;

  // Doubled array — animation translates by -50%, so once the first half has
  // scrolled off the second identical half appears seamlessly.
  const track: TickerTapeItem[] = [...items, ...items];

  return (
    <div className="ticker-tape" aria-label="实时行情滚动条">
      <div
        className="ticker-track"
        style={{ animationDuration: `${durationSeconds}s` }}
      >
        {track.map((item, idx) => {
          const cp = item.change_pct;
          const dir: 'up' | 'down' | 'flat' =
            cp == null ? 'flat' : cp > 0 ? 'up' : cp < 0 ? 'down' : 'flat';
          const dirClass =
            dir === 'up' ? 'rise' : dir === 'down' ? 'fall' : 'flat';
          const priceDisplay =
            item.price != null
              ? item.price.toFixed(2)
              : '-';
          const cpDisplay =
            cp != null
              ? `${cp > 0 ? '+' : ''}${cp.toFixed(2)}%`
              : '-';
          return (
            <span
              key={`${item.code}-${idx}`}
              className={`ticker-cell tabular-nums ${dirClass}`}
              role="button"
              tabIndex={0}
              onClick={() => navigate(`/instruments/${item.code}`)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  navigate(`/instruments/${item.code}`);
                }
              }}
            >
              <span className="ticker-code">{item.code}</span>
              <span className="ticker-name">{item.name}</span>
              <span className="ticker-price">{priceDisplay}</span>
              <span className={`ticker-change ${dirClass}`}>
                {dir === 'up' ? (
                  <ArrowUpOutlined className="ticker-arrow" />
                ) : dir === 'down' ? (
                  <ArrowDownOutlined className="ticker-arrow" />
                ) : null}
                <span>{cpDisplay}</span>
              </span>
            </span>
          );
        })}
      </div>
    </div>
  );
}