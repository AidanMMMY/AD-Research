export type NotificationChannelType = 'webhook' | 'email';

export interface NotificationConfig {
  id: number;
  name: string;
  channel_type: string;
  config_json: Record<string, any>;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface NotificationConfigCreate {
  name: string;
  channel_type: string;
  config_json: Record<string, any>;
  is_active?: boolean;
}

export interface NotificationConfigUpdate {
  name?: string;
  channel_type?: string;
  config_json?: Record<string, any>;
  is_active?: boolean;
}

export interface NotificationLog {
  id: number;
  config_id: number;
  user_id?: string;
  channel?: string;
  target?: string;
  report_id?: number;
  status: string;
  error?: string;
  sent_at?: string;
  created_at?: string;
}

export interface NotificationLogListResponse {
  items: NotificationLog[];
  total: number;
  page: number;
  page_size: number;
}

export interface SendTestResponse {
  success: boolean;
  error?: string;
}
