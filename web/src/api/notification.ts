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
  getLogs: (params?: { page?: number; page_size?: number }) =>
    client.get<NotificationLogListResponse>('/notifications/logs', { params }),
  logs: (page = 1, pageSize = 20) =>
    client.get<NotificationLogListResponse>('/notifications/logs', {
      params: { page, page_size: pageSize },
    }),
};
