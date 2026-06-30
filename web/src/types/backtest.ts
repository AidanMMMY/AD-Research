export interface BacktestMetrics {
  initial_capital: number;
  final_nav: number;
  total_return: number;
  annualized_return: number;
  max_drawdown: number;
  sharpe_ratio: number;
  win_rate: number;
  trade_count: number;
  avg_win: number;
  avg_loss: number;
  trading_days: number;
}

export interface BacktestTrade {
  entry_date: string;
  exit_date?: string;
  entry_price: number;
  exit_price: number;
  side: string;
  pnl: number;
  pnl_pct: number;
}

export interface BacktestNAV {
  date: string;
  nav: number;
}

export interface BacktestSignal {
  date: string;
  signal_type: string;
  price: number;
}

export interface Backtest {
  id: number;
  strategy_id: number;
  start_date: string;
  end_date: string;
  metrics: Record<string, any>;
  trades: BacktestTrade[];
  daily_nav: BacktestNAV[];
  signals: BacktestSignal[];
  config_snapshot?: Record<string, any>;
  created_at?: string;
}

export interface BacktestListItem {
  id: number;
  strategy_id: number;
  start_date?: string;
  end_date?: string;
  metrics: Record<string, any>;
  trade_count: number;
  created_at?: string;
}

export interface BacktestListResponse {
  items: BacktestListItem[];
}

export interface BacktestCreate {
  strategy_id: number;
  etf_code: string;
  start_date: string;
  end_date: string;
  initial_capital?: number;
  commission_rate?: number;
  slippage_rate?: number;
  position_size?: number;
}

export interface AttributionEffect {
  sector?: string;
  allocation?: number;
  selection?: number;
  interaction?: number;
  total?: number;
}

export interface AttributionSummary {
  allocation_pct?: number;
  selection_pct?: number;
  interaction_pct?: number;
}

export interface AttributionTradeStats {
  total_trades?: number;
  winning_trades?: number;
  losing_trades?: number;
  win_rate?: number;
  avg_return?: number;
}

export interface AttributionResponse {
  backtest_id?: number;
  total_return: number;
  benchmark_return: number;
  excess_return: number;
  effects?: AttributionEffect[];
  summary?: AttributionSummary;
  trade_stats?: AttributionTradeStats;
}
