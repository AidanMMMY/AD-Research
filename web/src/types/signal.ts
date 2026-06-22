export type SignalType = 'BUY' | 'SELL' | 'HOLD';

export interface Signal {
  id: number;
  strategy_id: number;
  etf_code: string;
  trade_date?: string;
  signal_type: SignalType;
  strength?: number;
  created_at?: string;
}

export interface SignalListResponse {
  items: Signal[];
}

export interface SignalGenerateRequest {
  strategy_id: number;
  etf_code: string;
  trade_date?: string;
}

export interface SignalGenerateResponse {
  signals: Signal[];
}
