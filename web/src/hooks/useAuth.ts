import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { authApi } from '@/api';
import { useAuthStore } from '@/stores/auth';

export function useLogin() {
  return useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      authApi.login({ username, password }),
  });
}

export const meQueryKey = (token: string | null) => ['me', token] as const;

export function useMe() {
  const setUser = useAuthStore((s) => s.setUser);
  const token = useAuthStore((s) => s.token);
  const queryClient = useQueryClient();
  const query = useQuery({
    // Identity responses must never be shared across sessions. The token key
    // also isolates direct account switches; staleTime=0 forces revalidation
    // instead of trusting a previous authentication for five minutes.
    queryKey: meQueryKey(token),
    queryFn: () => authApi.me(),
    enabled: !!token,
    retry: false,
    staleTime: 0,
  });

  useEffect(() => {
    // Every logout path updates the store, including axios interceptors.
    // Clear all token-scoped identities as defense in depth; the key above
    // still protects a direct A→B transition that skips the logged-out render.
    if (!token) {
      queryClient.removeQueries({ queryKey: ['me'] });
    }
  }, [queryClient, token]);

  useEffect(() => {
    if (query.data) {
      setUser(query.data.data);
    }
  }, [query.data, setUser]);

  return query;
}
