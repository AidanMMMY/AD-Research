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
  report_id?: number;
  status: string;
  error_msg?: string;
  sent_at?: string;
  created_at?: string;
}

export interface NotificationLogListResponse {
  items: NotificationLog[];
}

export interface SendTestResponse {
  success: boolean;
  error?: string;
}
