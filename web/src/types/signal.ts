export type SignalType = 'BUY' | 'SELL' | 'HOLD';

export interface Signal {
  id: number;
  strategy_id: number;
  strategy_name?: string;
  strategy_type?: string;
  etf_code: string;
  etf_name?: string;
  name_zh?: string | null;
  trade_date?: string;
  signal_type: SignalType;
  strength?: number;
  extra_data?: Record<string, unknown>;
  created_at?: string;
}

export interface SignalListResponse {
  items: Signal[];
}

export interface SignalGenerateRequest {
  strategy_id?: number;
  strategy_type?: string;
  etf_code: string;
  trade_date?: string;
  event_signal_id?: number;
}

export interface SignalGenerateResponse {
  signals: Signal[];
}
