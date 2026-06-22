export interface ETFInfo {
  code: string;
  name: string;
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
}

export interface ETFListResponse {
  items: ETFInfo[];
  total: number;
  page: number;
  page_size: number;
}

export interface ETFFilterParams {
  market?: string;
  category?: string;
  search?: string;
  page?: number;
  page_size?: number;
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
