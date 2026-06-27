import client from './client';
import type { DeploymentRun, ServerHealth, LogLine } from '@/types/deployment';

export const deploymentsApi = {
  list: () => client.get<DeploymentRun[]>('/admin/deployments'),

  getLogs: (runId: number) =>
    client.get<{ run_id: number; logs: string }>(`/admin/deployments/${runId}/logs`),

  trigger: () => client.post<{ message: string }>('/admin/deployments/trigger'),

  health: () => client.get<ServerHealth>('/admin/server/health'),

  containerLogs: (container: string, tail: number = 200) =>
    client.get<{ container: string; lines: LogLine[] }>(
      `/admin/containers/${container}/logs`,
      { params: { tail } }
    ),

  startLogStream: (container: string) =>
    client.post<{ message: string }>(`/admin/logs/stream/${container}/start`),

  stopLogStream: (container: string) =>
    client.post<{ message: string }>(`/admin/logs/stream/${container}/stop`),
};

/** Create an EventSource for live container log streaming via SSE. */
export function createLogEventSource(container: string): EventSource {
  const token = localStorage.getItem('token');
  const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1';
  const url = `${baseUrl}/admin/logs/stream?container=${encodeURIComponent(container)}&token=${encodeURIComponent(token || '')}`;
  return new EventSource(url);
}
