import { useQuery } from '@tanstack/react-query';
import { reportApi } from '@/api/report';
import type { ReportMetadata, ReportStatus } from '@/types/report';

const POLL_INTERVAL_MS = 2000;

function hasInFlight(reports: ReportMetadata[] | undefined): boolean {
  if (!reports || reports.length === 0) return false;
  return reports.some((r) => r.status === 'pending' || r.status === 'running');
}

export function useReportStatus(id: number | undefined, enabled = true) {
  return useQuery<ReportStatus>({
    queryKey: ['report-status', id],
    queryFn: async () => {
      if (!id) throw new Error('report id required');
      const res = await reportApi.status(id);
      return res.data;
    },
    enabled: enabled && !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'done' || status === 'failed') return false;
      return POLL_INTERVAL_MS;
    },
  });
}

export function useReports() {
  return useQuery<ReportMetadata[]>({
    queryKey: ['reports'],
    queryFn: async () => {
      const res = await reportApi.list({ limit: 50 });
      return res.data;
    },
    refetchInterval: (query) =>
      hasInFlight(query.state.data as ReportMetadata[] | undefined)
        ? POLL_INTERVAL_MS
        : false,
  });
}