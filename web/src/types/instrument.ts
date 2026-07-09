export interface InstrumentInfo {
  code: string;
  name: string;
  name_zh?: string | null;
  market: string;
  exchange?: string;
  category?: string;
  sub_category?: string;
  manager?: string;
  fund_manager?: string;
  fund_size?: number;
  underlying_index?: string;
  expense_ratio?: number;
  currency?: string;
  is_qdii?: boolean;
  inception_date?: string;
  status?: string;
  created_at?: string;
  updated_at?: string;
  instrument_type?: string;
  sector?: string;
  industry?: string;
  market_cap?: number;
  country?: string;
  /** A-share listing market (上海/深圳/北京) — null for non-A-share instruments. */
  listing_market?: string | null;
  /** A-share board (主板/创业板/科创板/北交所) — null for non-A-share instruments. */
  board?: string | null;
}

export interface InstrumentListResponse {
  items: InstrumentInfo[];
  total: number;
  page: number;
  page_size: number;
}

export interface InstrumentFilterParams {
  market?: string;
  category?: string;
  instrument_type?: string;
  search?: string;
  page?: number;
  page_size?: number;
  sub_category?: string;
  sector?: string;
  industry?: string;
  country?: string;
  manager?: string;
  underlying_index?: string;
  currency?: string;
  is_qdii?: boolean;
  status?: string;
  min_fund_size?: number;
  max_fund_size?: number;
  listing_market?: string;
  board?: string;
}

export interface MarketSnapshot {
  code: string;
  name: string;
  close: number;
  change_percent: number;
  volume: number;
  amount: number;
}

export interface OHLCV {
  trade_date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  adj_factor?: number | null;
}

export interface IndicatorData {
  code: string;
  trade_date: string;
  ma5?: number;
  ma10?: number;
  ma20?: number;
  ma60?: number;
  rsi14?: number;
  macd_dif?: number;
  macd_dea?: number;
  macd_hist?: number;
  bb_upper?: number;
  bb_lower?: number;
  atr14?: number;
  volatility_20d?: number;
  volatility_60d?: number;
  sharpe_1y?: number;
  max_drawdown_1y?: number;
  return_1w?: number;
  return_1m?: number;
  return_3m?: number;
  return_6m?: number;
  return_1y?: number;
}

export interface ETFHoldingItem {
  etf_code: string;
  holding_code: string;
  holding_name: string | null;
  weight: number | null;
  shares: number | null;
  market_value: number | null;
  holdings_as_of_date: string | null;
}

export interface ETFHoldingResponse {
  holdings: ETFHoldingItem[];
  holdings_as_of_date: string | null;
}

/**
 * One row in the per-ETF holdings-snapshot index returned by
 * ``GET /etfs/{code}/holdings/snapshots``. The list is ordered newest
 * first so the frontend can default to the latest period without
 * sorting. ``holding_count`` lets the UI render a quick weight hint
 * ("10 holdings") next to the date in the selector. ``total_weight``
 * is the sum of holding weights for the period (typically close to
 * 1.0 for the top-10 disclosed window, less for sparse snapshots).
 */
export interface ETFHoldingSnapshot {
  /** ISO date string of the period the holdings are reported as of. */
  holdings_as_of_date: string;
  /** Number of holdings rows in that snapshot. */
  holding_count: number;
  /** Sum of `weight` across the period, in decimal fraction (0.42 = 42%). */
  total_weight?: number | null;
  /** Optional data source tag (csindex, sse, manual, …). */
  source?: string | null;
}

export interface ETFHoldingSnapshotsResponse {
  items: ETFHoldingSnapshot[];
}

/**
 * Single per-holding diff row returned by
 * ``GET /etfs/{code}/holdings/diff?from=…&to=…``.
 *
 * ``status`` is one of:
 *   - ``added`` — holding only exists in the ``to`` period
 *   - ``removed`` — holding only exists in the ``from`` period
 *   - ``increased`` / ``decreased`` / ``unchanged`` — exists in both
 */
export interface ETFHoldingDiffEntry {
  holding_code: string;
  holding_name: string | null;
  from_weight: number | null;
  to_weight: number | null;
  weight_change: number | null;
  from_shares: number | null;
  to_shares: number | null;
  shares_change: number | null;
  status: 'added' | 'removed' | 'increased' | 'decreased' | 'unchanged' | string;
}

export interface ETFHoldingDiffResponse {
  from_date: string | null;
  to_date: string | null;
  entries: ETFHoldingDiffEntry[];
  added_count: number;
  removed_count: number;
  increased_count: number;
  decreased_count: number;
  unchanged_count: number;
  total_weight_change: number | null;
  from_total_weight: number | null;
  to_total_weight: number | null;
}
