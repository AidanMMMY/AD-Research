import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import client from './client';

/** Note: this module is for the *research-reports* (analyst reports)
 *  endpoint group and is intentionally distinct from ``api/research.ts``
 *  which serves the AI research-notes feature. */

export interface ResearchReportOut {
  id: number;
  ts_code: string;
  name: string;
  title: string;
  org_name: string;
  industry: string | null;
  publish_date: string;
  rating: string | null;
  pdf_url: string | null;
  summary: string | null;
  key_points: string[] | null;
  target_price: number | null;
  current_price_at_publish: number | null;
  source: string;
  fetched_at: string | null;
  updated_at: string | null;
}

export interface ResearchReportDetail extends ResearchReportOut {
  raw_payload: Record<string, unknown> | null;
  created_at: string | null;
}

export interface ResearchReportFacets {
  industries: string[];
  orgs: string[];
  ratings: string[];
}

export interface ResearchReportListParams {
  page?: number;
  page_size?: number;
  ts_code?: string;
  industry?: string;
  org_name?: string;
  rating?: string;
  start_date?: string;
  end_date?: string;
  has_summary?: boolean;
  sort_by?: 'publish_date' | 'fetched_at' | 'updated_at';
  sort_dir?: 'asc' | 'desc';
}

export interface ResearchReportListResponse {
  items: ResearchReportOut[];
  total: number;
  page: number;
  page_size: number;
}

function buildQueryString(params: ResearchReportListParams | undefined): string {
  if (!params) return '';
  const parts: string[] = [];
  const append = (key: string, value: unknown) => {
    if (value === undefined || value === null || value === '') return;
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
  };
  append('page', params.page ?? 1);
  append('page_size', params.page_size ?? 20);
  append('ts_code', params.ts_code);
  append('industry', params.industry);
  append('org_name', params.org_name);
  append('rating', params.rating);
  append('start_date', params.start_date);
  append('end_date', params.end_date);
  if (params.has_summary !== undefined) append('has_summary', params.has_summary);
  append('sort_by', params.sort_by ?? 'publish_date');
  append('sort_dir', params.sort_dir ?? 'desc');
  return parts.length === 0 ? '' : `?${parts.join('&')}`;
}

const BASE = '/research-reports';

export const researchReportApi = {
  list: (params?: ResearchReportListParams) =>
    client.get<ResearchReportListResponse>(`${BASE}${buildQueryString(params)}`),
  get: (id: number) => client.get<ResearchReportDetail>(`${BASE}/${id}`),
  getFacets: () => client.get<ResearchReportFacets>(`${BASE}/facets`),
  refresh: () => client.post<{ status: string; records: string }>(`${BASE}/refresh`),
  summarize: (id: number) =>
    client.post<{ status: string; id: string; summary: string }>(`${BASE}/${id}/summarize`),
};

export function useResearchReportList(params?: ResearchReportListParams) {
  return useQuery({
    queryKey: ['research-reports', 'list', params],
    queryFn: async () => {
      const res = await researchReportApi.list(params);
      return res.data;
    },
    staleTime: 60_000,
  });
}

export function useResearchReportDetail(id: number | null) {
  return useQuery({
    queryKey: ['research-reports', 'detail', id],
    queryFn: async () => {
      if (id == null) return null;
      const res = await researchReportApi.get(id);
      return res.data;
    },
    enabled: id != null,
    staleTime: 120_000,
  });
}

export function useResearchReportFacets() {
  return useQuery({
    queryKey: ['research-reports', 'facets'],
    queryFn: async () => {
      const res = await researchReportApi.getFacets();
      return res.data;
    },
    staleTime: 600_000,
  });
}

export function useRefreshResearchReports() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const res = await researchReportApi.refresh();
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-reports'] });
    },
  });
}

export function useSummarizeResearchReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      const res = await researchReportApi.summarize(id);
      return res.data;
    },
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: ['research-reports'] });
      queryClient.invalidateQueries({ queryKey: ['research-reports', 'detail', id] });
    },
  });
}