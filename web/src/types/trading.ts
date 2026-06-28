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

// ---------------------------------------------------------------------------
// Phase 3 – Live trading
// ---------------------------------------------------------------------------

/** Live-trade configuration (secrets are never returned). */
export interface LiveConfig {
  id: number;
  name: string;
  is_testnet: boolean;
  is_enabled: boolean;
  max_order_value: number;
  max_daily_loss: number;
  max_daily_orders: number;
  allowed_symbols: string | null;
  created_at: string | null;
  updated_at: string | null;
}

/** Request body to create a live-trade config. */
export interface LiveConfigCreate {
  name: string;
  api_key: string;
  api_secret: string;
  is_testnet?: boolean;
  max_order_value?: number;
  max_daily_loss?: number;
  max_daily_orders?: number;
  allowed_symbols?: string;
}

/** Request body to update a live-trade config. */
export interface LiveConfigUpdate {
  name?: string;
  is_enabled?: boolean;
  max_order_value?: number;
  max_daily_loss?: number;
  max_daily_orders?: number;
  allowed_symbols?: string;
}

/** Live-trade order. */
export interface LiveOrder {
  id: number;
  config_id: number;
  order_id_from_exchange: string | null;
  instrument_code: string;
  side: 'BUY' | 'SELL';
  order_type: 'LIMIT' | 'MARKET';
  price: number | null;
  quantity: number;
  filled_quantity: number;
  status: string;
  reject_reason: string | null;
  signal_id: number | null;
  created_at: string | null;
  updated_at: string | null;
}

/** Live-trade position. */
export interface LivePosition {
  id: number;
  config_id: number;
  instrument_code: string;
  quantity: number;
  avg_cost: number;
  current_price: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  realized_pnl: number | null;
  updated_at: string | null;
}

/** Binance account summary. */
export interface LiveAccount {
  balances: Array<{ asset: string; free: string; locked: string; total: string }>;
  can_trade: boolean;
  account_type: string | null;
}

/** Request body to place a live-trade order. */
export interface LiveOrderCreate {
  instrument_code: string;
  side: 'BUY' | 'SELL';
  order_type?: 'LIMIT' | 'MARKET';
  quantity: number;
  price?: number;
  signal_id?: number;
}

/** Risk-control status. */
export interface RiskStatus {
  config_id: number;
  circuit_breaker_active: boolean;
  circuit_breaker_reason: string | null;
  orders_today: number;
  realized_pnl_today: string;
  last_error: string | null;
}

/** Risk rule. */
export interface RiskRule {
  id: number;
  name: string;
  rule_type: string;
  param_key: string;
  param_value: string;
  is_active: boolean;
}
