import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { screenApi } from '@/api';
import type { ScreenFilters } from '@/types/screen';

export function useScreenResults(filters?: ScreenFilters) {
  return useQuery({
    queryKey: ['screen', filters],
    queryFn: () => screenApi.query(filters).then((r) => r.data),
    staleTime: 30_000,
  });
}

export function useScreenPresets() {
  return useQuery({
    queryKey: ['screen-presets'],
    queryFn: () => screenApi.presets().then((r) => r.data.presets),
    staleTime: 300_000,
  });
}

export function useScreenCategories(filters?: { market?: string }) {
  return useQuery({
    queryKey: ['screen-categories', filters],
    queryFn: () => screenApi.categories(filters).then((r) => r.data.categories),
    staleTime: 300_000,
    // Keep previous market's categories visible while the new market's list loads,
    // avoiding a brief empty state in the dropdown. The useEffect in Screen/index.tsx
    // still clears the stale selected category when the new list arrives.
    placeholderData: keepPreviousData,
  });
}
