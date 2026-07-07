import client from './client';

export interface StatsOverview {
  etf_count: number;
  category_count: number;
  market_count: number;
  indicator_count: number;
  score_count: number;
  template_count: number;
  latest_indicator_date: string | null;
  latest_score_date: string | null;
}

export type DashboardMetric = 'etf-count' | 'score-count' | 'category-count' | 'template-count';

/**
 * Hit the per-metric endpoint and unwrap the single-key payload so the
 * Dashboard's 4 KPI cards can fire 4 parallel queries and stream in
 * independently. Falls back to 0 on any non-2xx so the skeleton → number
 * transition stays smooth.
 */
async function fetchMetric(metric: DashboardMetric): Promise<number> {
  try {
    const res = await client.get<{ value: number } | number>(`/stats/overview/${metric}`);
    const data = res.data;
    if (typeof data === 'number') return data;
    if (data && typeof (data as { value?: number }).value === 'number') {
      return (data as { value: number }).value;
    }
    // The new backend returns `{etf_count: N}` for the route — accept
    // any single numeric property just in case the contract drifts.
    const obj = data as Record<string, unknown> | undefined;
    if (obj) {
      for (const v of Object.values(obj)) {
        if (typeof v === 'number') return v;
      }
    }
    return 0;
  } catch {
    return 0;
  }
}

export const statsApi = {
  overview: () => client.get<StatsOverview>('/stats/overview'),

  /** Per-metric parallel fetcher used by Dashboard KPI strip. */
  metric(metric: DashboardMetric): Promise<number> {
    return fetchMetric(metric);
  },
};