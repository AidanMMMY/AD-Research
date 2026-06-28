/** Paper-trade account summary. */
export interface PaperAccount {
  id: number;
  name: string;
  initial_balance: number;
  cash: number;
  currency: string;
  status: string;
  created_at: string | null;
  total_value: number | null;
  total_pnl: number | null;
  pnl_pct: number | null;
}

export interface PaperAccountListResponse {
  items: PaperAccount[];
  total: number;
}

/** Request body to create a paper-trade account. */
export interface PaperAccountCreate {
  name: string;
  initial_balance?: number;
}

/** Paper-trade order. */
export interface PaperOrder {
  id: number;
  account_id: number;
  instrument_code: string;
  order_type: 'BUY' | 'SELL';
  price: number | null;
  quantity: number;
  filled_quantity: number;
  status: string;
  reject_reason: string | null;
  signal_id: number | null;
  created_at: string | null;
  filled_at: string | null;
}

export interface PaperOrderListResponse {
  items: PaperOrder[];
  total: number;
}

/** Request body to place a paper-trade order. */
export interface PaperOrderCreate {
  instrument_code: string;
  order_type: 'BUY' | 'SELL';
  quantity: number;
  price?: number;
  signal_id?: number;
}

/** Paper-trade position (enriched with live price). */
export interface PaperPosition {
  id: number;
  account_id: number;
  instrument_code: string;
  quantity: number;
  avg_cost: number;
  market_value: number | null;
  unrealized_pnl: number | null;
  realized_pnl: number | null;
  updated_at: string | null;
  instrument_name: string | null;
  current_price: number | null;
  pnl_pct: number | null;
}

/** P&L summary for an account. */
export interface PnLSummary {
  account_id: number;
  total_equity: number;
  cash: number;
  market_value: number;
  unrealized_pnl: number;
  realized_pnl: number;
  total_pnl: number;
  pnl_pct: number | null;
  trade_count: number;
  win_count: number;
  win_rate: number | null;
}
