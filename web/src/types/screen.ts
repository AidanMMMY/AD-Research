export interface ScreenFilters {
  market?: string;
  category?: string;
  rsi_min?: number;
  rsi_max?: number;
  sharpe_min?: number;
  sharpe_max?: number;
  volatility_min?: number;
  volatility_max?: number;
  return_1m_min?: number;
  return_1m_max?: number;
  return_3m_min?: number;
  return_3m_max?: number;
  return_1y_min?: number;
  return_1y_max?: number;
  max_drawdown_1y_min?: number;
  max_drawdown_1y_max?: number;
  score_min?: number;
  score_max?: number;
  template_id?: number;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  offset?: number;
  limit?: number;
  preset?: string;
}

export interface ScreenResultItem {
  code: string;
  name: string;
  name_zh?: string | null;
  market: string;
  category?: string;
  rsi14?: number;
  sharpe_1y?: number;
  volatility_20d?: number;
  return_1m?: number;
  return_3m?: number;
  return_1y?: number;
  composite_score?: number;
}

export interface ScreenResult {
  items: ScreenResultItem[];
  count: number;
  offset: number;
  limit: number;
  preset?: {
    key: string;
    name: string;
    description: string;
  } | null;
}

export interface ScreenPreset {
  key: string;
  name: string;
  description: string;
}

export interface CategoryCount {
  category: string;
  count: number;
}
