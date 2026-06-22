export interface ScoreTemplate {
  id: number;
  name: string;
  description?: string;
  weights: Record<string, { weight: number; direction: 'asc' | 'desc' }>;
  is_default: boolean;
  created_at: string;
}

export interface ETFScore {
  etf_code: string;
  etf_name?: string;
  market?: string;
  category?: string;
  trade_date: string;
  template_id: number;
  composite_score: number;
  score_return: number;
  score_risk: number;
  score_sharpe: number;
  score_liquidity: number;
  score_trend: number;
  rank_overall: number;
  rank_category: number;
  return_1m?: number;
  return_3m?: number;
  return_1y?: number;
}

export interface ETFScoreListResponse {
  items: ETFScore[];
  total: number;
  template_id: number;
  trade_date: string;
}
