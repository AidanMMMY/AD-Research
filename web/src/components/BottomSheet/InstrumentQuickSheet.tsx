import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from 'antd';
import { ArrowRightOutlined } from '@ant-design/icons';
import BottomSheet from './BottomSheet';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import ReturnTagPct from '@/components/ReturnTagPct';
import ThemeTag from '@/components/ThemeTag';
import Sparkline from '@/components/Sparkline';
import LoadingBlock from '@/components/LoadingBlock';
import { useInstrumentDetail } from '@/hooks/useInstrumentList';
import { useSparkline } from '@/hooks/useSparkline';
import { NULL_PLACEHOLDER } from '@/utils/format';

export interface QuickMetric {
  label: string;
  value: React.ReactNode;
}

export interface InstrumentQuickSheetProps {
  open: boolean;
  onClose: () => void;
  /** Instrument code; null while nothing is selected. */
  code: string | null;
  /** Fallback display name (list payload) shown before the detail fetch lands. */
  name?: string | null;
  nameZh?: string | null;
  /** Live/latest price snapshot supplied by the parent (market stream or
   *  list payload) — the sheet never opens its own stream. */
  price?: number | null;
  changePct?: number | null;
  /** Price formatter (crypto needs 4-6 decimals). Default: 2 decimals. */
  formatPrice?: (v: number) => string;
  /** Full detail route. Default ``/instruments/${code}``. */
  detailPath?: string;
  /** Fetch + render fundamentals (market / category / size …) via
   *  ``/etfs/{code}``. Disable for universes the endpoint does not
   *  cover and pass ``metrics`` instead. Default true. */
  withFundamentals?: boolean;
  /** Extra caller-supplied metric cells (e.g. crypto 24h volume). */
  metrics?: QuickMetric[];
}

function formatSize(v: number | undefined | null): string | null {
  if (v == null) return null;
  if (v >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e8) return `${(v / 1e8).toFixed(1)}亿`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  return String(v);
}

/**
 * 个股速览 half-sheet (P3 / 方向 C): mobile row taps open this sheet
 * instead of navigating, so the list context (scroll position, filters)
 * is preserved; 「查看详情」commits to the full detail page.
 *
 * Data: the parent passes the price snapshot it already holds (no new
 * stream); fundamentals reuse ``useInstrumentDetail`` and the 30d
 * sparkline reuses ``useSparkline`` — both React-Query cached, so a
 * second tap on the same row is instant.
 */
export default function InstrumentQuickSheet({
  open,
  onClose,
  code,
  name,
  nameZh,
  price,
  changePct,
  formatPrice,
  detailPath,
  withFundamentals = true,
  metrics,
}: InstrumentQuickSheetProps) {
  const navigate = useNavigate();
  const { data: detail, isLoading: detailLoading } = useInstrumentDetail(
    withFundamentals && open && code ? code : '',
  );
  const { data: spark } = useSparkline({ code, days: 30, enabled: open && !!code });

  const shownName = detail?.name ?? name ?? code ?? '';
  const shownNameZh = detail?.name_zh ?? nameZh;

  const metricCells = useMemo<QuickMetric[]>(() => {
    const cells: QuickMetric[] = [];
    if (withFundamentals && detail) {
      if (detail.market) cells.push({ label: '市场', value: detail.market });
      if (detail.category) cells.push({ label: '分类', value: detail.category });
      const size = formatSize(detail.market_cap ?? detail.fund_size);
      if (size) {
        cells.push({ label: detail.market_cap ? '市值' : '规模', value: size });
      }
      if (detail.listing_market) cells.push({ label: '上市地', value: detail.listing_market });
      if (detail.board) cells.push({ label: '板块', value: detail.board });
      if (detail.fund_manager) cells.push({ label: '管理公司', value: detail.fund_manager });
    }
    if (metrics) cells.push(...metrics);
    return cells;
  }, [withFundamentals, detail, metrics]);

  const goDetail = () => {
    if (!code) return;
    onClose();
    navigate(detailPath ?? `/instruments/${code}`);
  };

  return (
    <BottomSheet
      open={open}
      onClose={onClose}
      title={shownName}
      ariaLabel="标的速览"
      snaps={['half', 'full']}
      footer={
        <Button
          type="primary"
          block
          icon={<ArrowRightOutlined />}
          onClick={goDetail}
        >
          查看详情
        </Button>
      }
    >
      {code && (
        <>
          <div className="ad-flex ad-items-center ad-gap-2">
            <InstrumentCodeTag code={code} name={shownName} name_zh={shownNameZh} />
          </div>

          <div className="quick-sheet__price-row">
            <span className="tabular-nums quick-sheet__price">
              {price != null
                ? (formatPrice ? formatPrice(price) : price.toFixed(2))
                : NULL_PLACEHOLDER}
            </span>
            {changePct != null && <ReturnTagPct value={changePct} />}
          </div>

          <div className="quick-sheet__sparkline">
            {spark?.points && spark.points.length > 0 ? (
              <Sparkline data={spark.points} width="100%" height={56} strokeWidth={1.5} />
            ) : (
              <span className="mobile-list-item__meta">近 30 日走势暂无数据</span>
            )}
          </div>

          {withFundamentals && detailLoading ? (
            <LoadingBlock size="sm" />
          ) : metricCells.length > 0 ? (
            <div className="quick-sheet__metrics">
              {metricCells.map((m) => (
                <div key={m.label}>
                  <div className="quick-sheet__metric-label">{m.label}</div>
                  <div className="quick-sheet__metric-value">{m.value}</div>
                </div>
              ))}
            </div>
          ) : null}

          {(detail?.sector || detail?.industry || detail?.underlying_index) && (
            <div className="quick-sheet__tags">
              {detail?.sector && <ThemeTag>{detail.sector}</ThemeTag>}
              {detail?.industry && <ThemeTag>{detail.industry}</ThemeTag>}
              {detail?.underlying_index && (
                <ThemeTag title={`跟踪指数: ${detail.underlying_index}`}>
                  {detail.underlying_index}
                </ThemeTag>
              )}
            </div>
          )}
        </>
      )}
    </BottomSheet>
  );
}
