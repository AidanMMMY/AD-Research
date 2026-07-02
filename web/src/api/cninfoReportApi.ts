import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import client from './client';
import type {
  CninfoReportCoverage,
  CninfoReportDetail,
  CninfoReportListParams,
  CninfoReportListResponse,
} from '@/types/cninfoReport';

function buildQueryString(params: CninfoReportListParams | undefined): string {
  if (!params) return '';
  const parts: string[] = [];
  const append = (key: string, value: unknown) => {
    if (value === undefined || value === null || value === '') return;
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
  };
  append('ts_code', params.ts_code);
  append('fiscal_year', params.fiscal_year);
  append('fiscal_quarter', params.fiscal_quarter);
  append('adjunct_type', params.adjunct_type);
  append('start_date', params.start_date);
  append('end_date', params.end_date);
  append('has_text', params.has_text);
  append('page', params.page);
  append('page_size', params.page_size);
  return parts.length === 0 ? '' : `?${parts.join('&')}`;
}

export const cninfoReportApi = {
  list: (params?: CninfoReportListParams) =>
    client.get<CninfoReportListResponse>(
      `/cninfo-reports${buildQueryString(params)}`,
    ),
  get: (id: number) =>
    client.get<CninfoReportDetail>(`/cninfo-reports/${id}`),
  getCoverage: () =>
    client.get<CninfoReportCoverage>('/cninfo-reports/coverage'),
  refresh: () =>
    client.post<{ status: string; records: string }>(
      '/cninfo-reports/refresh',
    ),
};

export function useCninfoReportList(params?: CninfoReportListParams) {
  return useQuery({
    queryKey: ['cninfo-reports', 'list', params],
    queryFn: async () => {
      const res = await cninfoReportApi.list(params);
      return res.data;
    },
    staleTime: 30_000,
  });
}

export function useCninfoReportDetail(id: number | null) {
  return useQuery({
    queryKey: ['cninfo-reports', 'detail', id],
    queryFn: async () => {
      if (id == null) return null;
      const res = await cninfoReportApi.get(id);
      return res.data;
    },
    enabled: id != null,
    staleTime: 60_000,
  });
}

export function useCninfoReportCoverage() {
  return useQuery({
    queryKey: ['cninfo-reports', 'coverage'],
    queryFn: async () => {
      const res = await cninfoReportApi.getCoverage();
      return res.data;
    },
    staleTime: 300_000,
  });
}

export function useRefreshCninfoReports() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const res = await cninfoReportApi.refresh();
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cninfo-reports'] });
    },
  });
}