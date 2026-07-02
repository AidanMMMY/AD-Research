import { useQuery } from '@tanstack/react-query';
import { macroApi, MacroIndicatorSeries } from '@/api/macro';

/** List indicators + their latest value. region='us' for FRED, 'cn' for akshare. */
export function useMacroIndicators(region?: string) {
  return useQuery({
    queryKey: ['macro-indicators', region ?? 'all'],
    queryFn: () => macroApi.listIndicators(region).then((r) => r.data),
    staleTime: 60_000,
  });
}

/** Time-series for a single indicator. */
export function useMacroSeries(
  code: string | null,
  opts: { start_date?: string; end_date?: string; limit?: number } = {},
) {
  return useQuery<MacroIndicatorSeries | null>({
    queryKey: ['macro-series', code, opts],
    queryFn: async () => {
      if (!code) return null;
      const r = await macroApi.getSeries(code, opts);
      return r.data;
    },
    enabled: !!code,
    staleTime: 5 * 60_000,
  });
}

/** Latest snapshot across all (code, region) pairs. */
export function useMacroLatest(region?: string) {
  return useQuery({
    queryKey: ['macro-latest', region ?? 'all'],
    queryFn: () => macroApi.latest(region).then((r) => r.data),
    staleTime: 60_000,
  });
}