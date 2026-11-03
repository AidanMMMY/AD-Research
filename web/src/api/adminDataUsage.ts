import client from './client';

/** /admin/data-api/usage —— 外部数据通道（X-API-Key）访问审计聚合。 */
export interface DataApiUsageResponse {
  days: number;
  totals: { requests: number; errors: number; avg_ms: number | null };
  by_day: { date: string; requests: number; avg_ms: number | null; errors: number }[];
  top_paths: { path: string; requests: number; avg_ms: number | null }[];
  by_user: { username: string; requests: number }[];
  recent: {
    created_at: string | null;
    username: string;
    method: string;
    path: string;
    status_code: number;
    duration_ms: number | null;
    client_ip: string | null;
    user_agent: string | null;
  }[];
}

export const adminDataUsageApi = {
  usage: (days: number) =>
    client.get<DataApiUsageResponse>('/admin/data-api/usage', { params: { days } }),
};
