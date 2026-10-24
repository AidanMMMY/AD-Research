import client from './client';

export interface LoginRequest {
  username: string;
  password: string;
}

export interface UserProfile {
  id: number;
  username: string;
  role: 'admin' | 'user';
  /** True ⇒ the app forces a redirect to /change-password */
  must_change_password?: boolean;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: UserProfile;
}

export interface RefreshResponse {
  access_token: string;
  refresh_token: string;
}

export interface DeviceInfo {
  id: number;
  device_name: string;
  platform: string;
  last_active_at: string;
  created_at: string;
}

export const authApi = {
  login: (data: LoginRequest) => client.post<LoginResponse>('/auth/login', data),
  me: () => client.get<UserProfile>('/auth/me'),
  refresh: (refreshToken: string) =>
    client.post<RefreshResponse>('/auth/refresh', { refresh_token: refreshToken }),
  logout: () => client.post('/auth/logout'),
  changePassword: (data: { old_password: string; new_password: string }) =>
    client.post<{
      detail: string;
      access_token: string;
      refresh_token: string;
      token_type: string;
    }>('/auth/change-password', data),
  registerDevice: (data: { device_name: string; platform: string; push_token?: string }) =>
    client.post<DeviceInfo>('/auth/devices', data),
  listDevices: () => client.get<DeviceInfo[]>('/auth/devices'),
  removeDevice: (id: number) => client.delete(`/auth/devices/${id}`),
};
