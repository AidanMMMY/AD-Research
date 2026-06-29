import client from './client';
import type { ScreenResult, ScreenFilters, ScreenPreset, CategoryCount } from '@/types/screen';

export const screenApi = {
  query: (params?: ScreenFilters) => client.get<ScreenResult>('/screen', { params }),
  presets: () => client.get<{ presets: ScreenPreset[] }>('/screen/presets'),
  categories: (params?: { market?: string }) =>
    client.get<{ categories: CategoryCount[] }>('/screen/categories', { params }),
};
