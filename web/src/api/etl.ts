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

export interface SchedulerJob {
  id: string;
  name: string;
  next_run: string | null;
  last_run: string | null;
  last_status: string | null;
  last_duration_ms: number | null;
  last_error: string | null;
  runnable: boolean;
}

export interface RunNowResponse {
  task_id: string;
  job_name: string;
  queued_at: string;
}

export const etlApi = {
  status: (params?: {
    job_name?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }) => client.get<ETLStatusResponse>('/etl/status', { params }),
  dashboard: () => client.get<ETLDashboardResponse>('/etl/dashboard'),
  schedulerJobs: () =>
    client.get<{ jobs: SchedulerJob[] }>('/etl/scheduler/jobs'),
  runJobNow: (jobId: string) =>
    client.post<RunNowResponse>(
      `/etl/scheduler/jobs/${encodeURIComponent(jobId)}/run-now`,
    ),
  reRun: (jobName: string, force = false) =>
    client.post<{ task_id: string; queued_at: string }>('/etl/re-run', {
      job_name: jobName,
      force,
    }),
};
