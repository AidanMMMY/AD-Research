import client from './client';
import type {
  NotificationConfig,
  NotificationConfigCreate,
  NotificationConfigUpdate,
  NotificationLogListResponse,
  SendTestResponse,
} from '@/types/notification';

export const notificationApi = {
  listConfigs: () => client.get<NotificationConfig[]>('/notifications/configs'),
  createConfig: (data: NotificationConfigCreate) =>
    client.post<NotificationConfig>('/notifications/configs', data),
  updateConfig: (id: number, data: NotificationConfigUpdate) =>
    client.put<NotificationConfig>(`/notifications/configs/${id}`, data),
  deleteConfig: (id: number) => client.delete(`/notifications/configs/${id}`),
  testConfig: (id: number) =>
    client.post<SendTestResponse>(`/notifications/configs/${id}/test`),
  getLogs: (limit?: number) =>
    client.get<NotificationLogListResponse>('/notifications/logs', { params: { limit } }),
};
