import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { deploymentsApi } from '@/api';
import { useState, useRef, useCallback, useEffect } from 'react';
import type { LogLine } from '@/types/deployment';

export function useDeployments() {
  const queryClient = useQueryClient();

  const deploymentsQuery = useQuery({
    queryKey: ['deployments'],
    queryFn: async () => {
      const res = await deploymentsApi.list();
      return res.data;
    },
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const healthQuery = useQuery({
    queryKey: ['server-health'],
    queryFn: async () => {
      const res = await deploymentsApi.health();
      return res.data;
    },
    refetchInterval: 10_000,
  });

  const triggerMutation = useMutation({
    mutationFn: () => deploymentsApi.trigger(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deployments'] });
    },
  });

  return {
    deployments: deploymentsQuery.data || [],
    isLoadingDeployments: deploymentsQuery.isLoading,
    health: healthQuery.data,
    isLoadingHealth: healthQuery.isLoading,
    triggerDeploy: triggerMutation.mutateAsync,
    isTriggering: triggerMutation.isPending,
    triggerError: triggerMutation.error,
  };
}

/** Hook for fetching historical container logs (snapshot). */
export function useContainerLogs(container: string, tail = 200) {
  return useQuery({
    queryKey: ['container-logs', container, tail],
    queryFn: async () => {
      const res = await deploymentsApi.containerLogs(container, tail);
      return res.data;
    },
    staleTime: 10_000,
    enabled: !!container,
  });
}

/** Hook for live SSE log streaming. */
export function useLogStream(container: string) {
  const [lines, setLines] = useState<LogLine[]>([]);
  const [connected, setConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  const connect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const token = localStorage.getItem('token') || '';
    const es = new EventSource(
      `/api/v1/admin/logs/stream?container=${encodeURIComponent(container)}&token=${encodeURIComponent(token)}`
    );

    es.addEventListener('connected', () => {
      setConnected(true);
      setLines([]);
    });

    es.addEventListener('log', (e) => {
      try {
        const line: LogLine = JSON.parse(e.data);
        setLines((prev) => {
          const next = [...prev, line];
          // Keep max 500 lines in memory
          return next.length > 500 ? next.slice(-500) : next;
        });
      } catch {
        // ignore parse errors
      }
    });

    es.onerror = () => {
      setConnected(false);
      es.close();
    };

    eventSourceRef.current = es;
  }, [container]);

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setConnected(false);
  }, []);

  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return { lines, connected, connect, disconnect };
}
