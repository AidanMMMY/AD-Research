/**
 * 池相关响应类型，逐字段对齐后端 app/schemas/pool.py（2026-10-25
 * 契约修复：此前前端臆造了 name/correlation_matrix/note 等后端不存在的
 * 字段、漏了 pool_name/member_count，导致池分析数据无法真实显示）。
 */

export interface Pool {
  id: number;
  name: string;
  description?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  /** PoolMemberResponse[]（后端不带 pool_id/is_active）。 */
  members: PoolMember[];
  /** Owner user id. NULL/undefined = 系统预置的全局共享池（仅管理员可删改）。 */
  user_id?: number | null;
}

export interface PoolMember {
  etf_code: string;
  etf_name?: string | null;
  name_zh?: string | null;
  added_at?: string | null;
  notes?: string | null;
}

/** GET /pools/{id}/weights 响应元素（PoolWeightResponse）。 */
export interface PoolWeight {
  etf_code: string;
  etf_name?: string | null;
  name_zh?: string | null;
  target_weight: number;
  suggested_weight?: number | null;
  /** 后端为自由字符串，常见值 manual/equal/score/risk_parity。 */
  weight_source: string;
  updated_at?: string | null;
}

/** /pools/{id}/analytics 的成员元素（PoolAnalyticsMember）。 */
export interface PoolAnalyticsMember {
  etf_code: string;
  etf_name?: string | null;
  name_zh?: string | null;
  category?: string | null;
  target_weight: number;
  added_at?: string | null;
}

/** 按权重加权的组合表现（_calculate_weighted_performance，仅有数据的键）。 */
export interface PoolPerformance {
  return_1w?: number;
  return_1m?: number;
  return_3m?: number;
  return_6m?: number;
  return_1y?: number;
  volatility_20d?: number;
  sharpe_1y?: number;
  max_drawdown_1y?: number;
}

/** 单条再平衡告警（_check_rebalance 产出的 dict）。 */
export interface PoolRebalanceAlert {
  etf_code: string;
  etf_name?: string | null;
  name_zh?: string | null;
  target_weight: number;
  actual_weight: number;
  /** 偏离百分比（百分点），如 2.5 = 2.5%。 */
  deviation: number;
}

/** GET /pools/{id}/analytics 响应（PoolAnalyticsResponse）。 */
export interface PoolAnalytics {
  pool_id: number;
  pool_name?: string | null;
  member_count: number;
  members: PoolAnalyticsMember[];
  category_distribution: Record<string, { count: number; weight: number }>;
  performance: PoolPerformance;
  rebalance_needed: boolean;
  rebalance_alerts: PoolRebalanceAlert[];
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
