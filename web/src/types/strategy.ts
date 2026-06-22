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
