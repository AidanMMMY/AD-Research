/** Valuation & market data for an A-share individual stock. */
export interface StockFundamental {
  stock_code: string;
  trade_date: string;
  /** PE (TTM) */
  pe_ttm?: number | null;
  /** Price to Book */
  pb?: number | null;
  /** Total market cap (万元 CNY) */
  total_mv?: number | null;
  /** Circulating market cap (万元 CNY) */
  circ_mv?: number | null;
  /** Free float turnover rate (%) */
  turnover_rate_f?: number | null;
  /** Volume ratio (vs 5-day avg) */
  volume_ratio?: number | null;
  /** Total shares (万股) */
  total_share?: number | null;
  /** Float shares (万股) */
  float_share?: number | null;
  /** Basic EPS (元) — from latest income statement */
  eps?: number | null;
  /** ROE (%) — from latest income statement */
  roe?: number | null;
  /** Revenue YoY growth (%) */
  revenue_yoy?: number | null;
  /** Gross profit margin (%) */
  grossprofit_margin?: number | null;
  /** Net profit margin (%) */
  netprofit_margin?: number | null;
}
