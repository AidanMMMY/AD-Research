import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { favoriteApi } from '@/api/favorite';

export function useFavorites(limit?: number) {
  const queryClient = useQueryClient();

  const favoritesQuery = useQuery({
    queryKey: ['favorites', limit],
    queryFn: async () => {
      const res = await favoriteApi.list(limit);
      return res.data;
    },
    staleTime: 30_000,
  });

  const toggleMutation = useMutation({
    mutationFn: (etf_code: string) => favoriteApi.toggle(etf_code),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['favorites'] });
    },
  });

  return {
    favorites: favoritesQuery.data?.items || [],
    count: favoritesQuery.data?.count || 0,
    isLoading: favoritesQuery.isLoading,
    toggle: toggleMutation.mutateAsync,
  };
}

export function useFavoriteStatus(etf_code: string) {
  const queryClient = useQueryClient();
  const isAuthenticated = !!localStorage.getItem('token');

  const statusQuery = useQuery({
    queryKey: ['favorite-status', etf_code],
    queryFn: async () => {
      const res = await favoriteApi.status(etf_code);
      return res.data;
    },
    enabled: !!etf_code && isAuthenticated,
    staleTime: 60_000,
  });

  const toggleMutation = useMutation({
    mutationFn: () => favoriteApi.toggle(etf_code),
    onSuccess: (result) => {
      queryClient.setQueryData(['favorite-status', etf_code], result.data);
      queryClient.invalidateQueries({ queryKey: ['favorites'] });
    },
  });

  return {
    isFavorite: statusQuery.data?.is_favorite || false,
    isLoading: statusQuery.isLoading,
    toggle: toggleMutation.mutateAsync,
    isToggling: toggleMutation.isPending,
  };
}
