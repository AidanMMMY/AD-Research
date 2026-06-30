/** Cryptocurrency instrument summary (list row). */
export interface CryptoInfo {
  code: string;
  name: string;
  exchange?: string;
  market?: string;
  category?: string;
  currency?: string;
  instrument_type?: string;
  status?: string;
  /** Latest price in USDT */
  price?: number;
  /**
   * 24h price change percent (canonical field).
   * New code should prefer this over the deprecated `change_24h`.
   */
  change_pct?: number;
  /**
   * @deprecated Use `change_pct` instead. Same value, kept for
   * backward compatibility with existing UI components.
   */
  change_24h?: number;
  /** 24h base-asset volume */
  volume_24h?: number;
}

/** Paginated list response. */
export interface CryptoListResponse {
  items: CryptoInfo[];
  total: number;
  page: number;
  page_size: number;
}

/** Full instrument detail. */
export interface CryptoDetail {
  code: string;
  name: string;
  exchange?: string;
  market?: string;
  category?: string;
  currency?: string;
  instrument_type?: string;
  status?: string;
  price?: number;
  /**
   * 24h price change percent (canonical field).
   * New code should prefer this over the deprecated `change_24h`.
   */
  change_pct?: number;
  /**
   * @deprecated Use `change_pct` instead. Same value, kept for
   * backward compatibility with existing UI components.
   */
  change_24h?: number;
  high_24h?: number;
  low_24h?: number;
  volume_24h?: number;
  amount_24h?: number;
  latest_indicator?: IndicatorSummary;
}

/** Single OHLCV bar. */
export interface DailyBar {
  trade_date: string;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  volume?: number;
  amount?: number;
  change_pct?: number;
}

/** Technical indicator summary. */
export interface IndicatorSummary {
  etf_code: string;
  trade_date?: string;
  ma5?: number;
  ma10?: number;
  ma20?: number;
  ma60?: number;
  rsi14?: number;
  macd_dif?: number;
  macd_dea?: number;
  macd_hist?: number;
  atr14?: number;
  bb_upper?: number;
  bb_lower?: number;
  volatility_20d?: number;
  volatility_60d?: number;
  max_drawdown_1y?: number;
  sharpe_1y?: number;
  return_1w?: number;
  return_1m?: number;
  return_3m?: number;
  return_6m?: number;
  return_1y?: number;
}

/** Indicator history wrapper. */
export interface IndicatorHistory {
  items: IndicatorSummary[];
  count: number;
}

/** Research note. */
export interface ResearchNote {
  id: number;
  note_type: string;
  summary: string;
  content: string;
  sentiment: string;
  confidence: number;
  generated_at: string;
}

/** Score summary. */
export interface CryptoScore {
  etf_code: string;
  trade_date: string;
  template_id: number;
  composite_score: number;
  return_score?: number;
  risk_score?: number;
  sharpe_score?: number;
  liquidity_score?: number;
  trend_score?: number;
  rank_overall?: number;
  rank_category?: number;
}

/** Trading signal. */
export interface CryptoSignal {
  id: number;
  strategy_id: number;
  etf_code: string;
  trade_date: string;
  signal_type: string;
  strength: number;
}

/** List filter params. */
export interface CryptoFilterParams {
  market?: string;
  exchange?: string;
  category?: string;
  search?: string;
  sort_by?: string;
  sort_order?: string;
  page?: number;
  page_size?: number;
}
