import client from './client';
import type { ETLStatusResponse } from '@/types/etl';

export interface ETLTask {
  name: string;
  label: string;
  market: string;
  last_run: string | null;
  status: string;
  rows_affected: number | null;
  duration_seconds: number | null;
  error: string | null;
}

export interface ETLDashboardResponse {
  last_run_at: string | null;
  generated_at: string;
  stale_markets: string[];
  tasks: ETLTask[];
  data_freshness: {
    a_share: string | null;
    us_stock: string | null;
    crypto: string | null;
  };
}

export const etlApi = {
  status: (params?: {
    job_name?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }) => client.get<ETLStatusResponse>('/etl/status', { params }),
  dashboard: () => client.get<ETLDashboardResponse>('/etl/dashboard'),
};
