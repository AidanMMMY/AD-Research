export interface ScoreTemplate {
  id: number;
  name: string;
  description?: string;
  /**
   * Dimension -> weight (0..1).  The server-side calculator decorates
   * this with its own `metrics` and `direction` from a fixed DIMENSION_MAP
   * at runtime, so the wire format is intentionally flat.
   * Common keys: return / risk / sharpe / liquidity / trend.
   */
  weights: Record<string, number>;
  is_default: boolean;
  created_at?: string;
  updated_at?: string;
}

export type ScoreTemplateCreate = Omit<ScoreTemplate, 'id' | 'created_at' | 'updated_at'>;
export type ScoreTemplateUpdate = Partial<ScoreTemplateCreate>;

export interface InstrumentScore {
  etf_code: string;
  etf_name?: string;
  name_zh?: string | null;
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
  items: InstrumentScore[];
  total: number;
  template_id: number;
  trade_date: string;
}
