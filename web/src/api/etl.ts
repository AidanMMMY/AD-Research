import client from './client';
import type { ETLStatusResponse } from '@/types/etl';

export const etlApi = {
  status: (params?: {
    job_name?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }) => client.get<ETLStatusResponse>('/etl/status', { params }),
};
