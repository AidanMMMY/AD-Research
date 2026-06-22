import client from './client';
import type { FavoriteListResponse, FavoriteToggleResponse, FavoriteStatusResponse } from '@/types/favorite';

export const favoriteApi = {
  list: (limit?: number) =>
    client.get<FavoriteListResponse>('/favorites', { params: { limit } }),
  status: (etf_code: string) =>
    client.get<FavoriteStatusResponse>(`/favorites/${etf_code}/status`),
  toggle: (etf_code: string) =>
    client.post<FavoriteToggleResponse>(`/favorites/${etf_code}/toggle`),
  add: (etf_code: string) =>
    client.post<FavoriteToggleResponse>(`/favorites/${etf_code}/add`),
  remove: (etf_code: string) =>
    client.delete<FavoriteToggleResponse>(`/favorites/${etf_code}`),
};
