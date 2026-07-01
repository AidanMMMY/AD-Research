export interface ParamSpec {
  label: string;
  type: 'int' | 'float' | 'bool' | 'choice';
  default: any;
  min?: number;
  max?: number;
  options?: string[];
  description?: string;
}

export interface StrategyCatalogItem {
  strategy_type: string;
  name: string;
  description: string;
  family: string;
  param_specs: Record<string, ParamSpec>;
  min_bars: number;
}

export interface StrategyTemplate {
  name: string;
  description: string;
  strategy_type: string;
  params: Record<string, any>;
}

export interface Strategy {
  id: number;
  name: string;
  description?: string;
  strategy_type: string;
  params: Record<string, any>;
  is_active: boolean;
  created_at?: string;
}

export interface StrategyCreate {
  name: string;
  description?: string;
  strategy_type: string;
  params: Record<string, any>;
  is_active?: boolean;
}

export interface StrategyUpdate {
  name?: string;
  description?: string;
  strategy_type?: string;
  params?: Record<string, any>;
  is_active?: boolean;
}

export interface StrategyListResponse {
  items: Strategy[];
}

export interface StrategyRunRequest {
  strategy_type: string;
  params: Record<string, any>;
  etf_codes: string[];
  trade_date?: string;
  lookback_days?: number;
}

export interface StrategyRunResponse {
  signals: Array<{
    etf_code?: string;
    type: string;
    strength: number;
    metadata?: Record<string, any>;
  }>;
  strategy_type: string;
  trade_date: string;
  instrument_count: number;
  signal_count: number;
}
