import { useQuery } from '@tanstack/react-query';
import { stocksApi } from '@/api/stocks';
import type { StockFilterParams } from '@/api/stocks';

/**
 * List A-share individual stocks with the standard filter set.
 * Backend auto-filters instrument_type=STOCK so the frontend does not
 * need to repeat that constraint.
 */
export function useStockList(params?: StockFilterParams) {
  return useQuery({
    queryKey: ['stocks', params],
    queryFn: () => stocksApi.list(params).then((r) => r.data),
    staleTime: 60_000,
  });
}

export function useStockDetail(code: string) {
  return useQuery({
    queryKey: ['stock', code],
    queryFn: () => stocksApi.get(code).then((r) => r.data),
    enabled: !!code,
  });
}
