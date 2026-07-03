import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { authApi } from '@/api';
import { useAuthStore } from '@/stores/auth';

export function useLogin() {
  return useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      authApi.login({ username, password }),
  });
}

export function useMe() {
  const setUser = useAuthStore((s) => s.setUser);
  const query = useQuery({
    queryKey: ['me'],
    queryFn: () => authApi.me(),
    enabled: !!localStorage.getItem('token'),
    retry: false,
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    if (query.data) {
      setUser(query.data.data);
    }
  }, [query.data, setUser]);

  return query;
}
