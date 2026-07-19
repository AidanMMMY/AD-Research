export interface Pool {
  id: number;
  name: string;
  description?: string;
  created_at: string;
  updated_at: string;
  members: PoolMember[];
}

export interface PoolMember {
  pool_id: number;
  etf_code: string;
  etf_name?: string;
  name_zh?: string | null;
  added_at?: string;
  is_active?: boolean;
  note?: string;
}

export interface PoolWeight {
  pool_id: number;
  etf_code: string;
  etf_name?: string;
  name_zh?: string | null;
  target_weight: number;
  suggested_weight?: number;
  weight_source: 'manual' | 'equal' | 'score' | 'risk_parity';
}

export interface PoolAnalytics {
  pool_id: number;
  name: string;
  members: PoolWeight[];
  category_distribution: Record<string, { count: number; weight: number }>;
  correlation_matrix?: {
    codes: string[];
    matrix: number[][];
  };
  performance: {
    return_1m?: number;
    return_3m?: number;
    volatility_20d?: number;
    sharpe_1y?: number;
    max_drawdown_1y?: number;
  };
  rebalance_needed?: Array<{
    code: string;
    target: number;
    actual: number;
    diff: number;
  }>;
}

export interface PoolSnapshot {
  id: number;
  pool_id: number;
  snapshot_date: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface PoolCreate {
  name: string;
  description?: string;
}

export interface PoolUpdate {
  name?: string;
  description?: string;
}
