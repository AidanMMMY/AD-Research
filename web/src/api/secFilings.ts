import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import client from './client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SecFiling {
  id: number;
  cik: string;
  ticker: string;
  company_name?: string | null;
  form_type: string;
  filing_date: string;
  report_period?: string | null;
  accession_number: string;
  primary_document?: string | null;
  filing_url?: string | null;
  extraction_status: string;
  source: string;
  extracted_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface SecFilingDetail extends SecFiling {
  extracted_metrics?: Record<string, unknown> | null;
  xbrl_file_path?: string | null;
}

export interface SecFilingListParams {
  page?: number;
  page_size?: number;
  ticker?: string;
  cik?: string;
  form_type?: string;
  start_date?: string;
  end_date?: string;
  q?: string;
  sort_by?: string;
  sort_dir?: 'asc' | 'desc';
}

export interface SecFilingListResponse {
  items: SecFiling[];
  total: number;
  page: number;
  page_size: number;
}

export interface SecFilingCoverage {
  total_filings: number;
  tracked_tickers: number;
  by_form_type: Record<string, number>;
  latest_filing_date?: string | null;
  extractions_completed: number;
  extractions_failed: number;
  extractions_pending: number;
}

// ---------------------------------------------------------------------------
// Query string builder
// ---------------------------------------------------------------------------

function buildQueryString(params: SecFilingListParams | undefined): string {
  if (!params) return '';
  const parts: string[] = [];
  const append = (key: string, value: unknown) => {
    if (value === undefined || value === null || value === '') return;
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
  };
  append('page', params.page);
  append('page_size', params.page_size);
  append('ticker', params.ticker);
  append('cik', params.cik);
  append('form_type', params.form_type);
  append('start_date', params.start_date);
  append('end_date', params.end_date);
  append('q', params.q);
  append('sort_by', params.sort_by);
  append('sort_dir', params.sort_dir);
  return parts.length === 0 ? '' : `?${parts.join('&')}`;
}

// ---------------------------------------------------------------------------
// API + hooks
// ---------------------------------------------------------------------------

export const secFilingsApi = {
  list: (params?: SecFilingListParams) =>
    client.get<SecFilingListResponse>(`/sec-filings${buildQueryString(params)}`),
  get: (id: number) => client.get<SecFilingDetail>(`/sec-filings/${id}`),
  coverage: () => client.get<SecFilingCoverage>('/sec-filings/coverage'),
  refresh: (batch_size: number = 50) =>
    client.post<{ status: string; records: string; warnings: string[] }>(
      `/sec-filings/refresh?batch_size=${batch_size}`,
    ),
  syncTicker: (ticker: string) =>
    client.post<{ status: string; ticker: string; written: number }>(
      `/sec-filings/sync/${ticker}`,
    ),
  extractMetrics: (id: number) =>
    client.post<{ status: string; filing_id: number }>(`/sec-filings/${id}/extract-metrics`),
};

export function useSecFilingList(params?: SecFilingListParams) {
  return useQuery({
    queryKey: ['sec-filings', 'list', params],
    queryFn: async () => {
      const res = await secFilingsApi.list(params);
      return res.data;
    },
    staleTime: 30_000,
  });
}

export function useSecFilingDetail(id: number | null) {
  return useQuery({
    queryKey: ['sec-filings', 'detail', id],
    queryFn: async () => {
      if (id == null) return null;
      const res = await secFilingsApi.get(id);
      return res.data;
    },
    enabled: id != null,
    staleTime: 60_000,
  });
}

export function useSecFilingCoverage() {
  return useQuery({
    queryKey: ['sec-filings', 'coverage'],
    queryFn: async () => {
      const res = await secFilingsApi.coverage();
      return res.data;
    },
    staleTime: 60_000,
  });
}

export function useRefreshSecFilings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (batchSize?: number) => {
      const res = await secFilingsApi.refresh(batchSize ?? 50);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sec-filings'] });
    },
  });
}

export function useSyncSecTicker() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (ticker: string) => {
      const res = await secFilingsApi.syncTicker(ticker);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sec-filings'] });
    },
  });
}