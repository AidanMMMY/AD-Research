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

// ---- Self-service registration (docs/dev-notes/20261025-self-registration-design.md §3.2) ----
// Contract shared with the backend agent — do not change unilaterally:
//   POST /auth/register               201 {"detail":"verification email sent"}
//                                     400 {"detail":"username already taken"} (email conflict
//                                     also answers 201 to prevent account enumeration)
//   POST /auth/verify-registration    200 tokens+user | 400 invalid code (+remaining_attempts)
//                                     | 410 code expired
//   POST /auth/resend-verification    202 | 429 {"detail":"cooldown"}
//   GET  /auth/check-username         {"available": bool, "suggestions": [...] | null}
export interface RegisterRequest {
  email: string;
  username: string;
  password: string;
}

export interface CheckUsernameResponse {
  available: boolean;
  suggestions: string[] | null;
}

export interface VerifyRegistrationResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: UserProfile;
}

// ---- Password reset (2026-10-25; reuses the registration OTP machinery) ----
// Contract shared with the backend — do not change unilaterally:
//   POST /auth/forgot-password  202 {"detail":"reset email sent"} for ANY
//                               well-formed email (anti-enumeration);
//                               429 {"detail":"cooldown"} / rate limit
//   POST /auth/reset-password   200 tokens+user | 400 invalid code
//                               (+remaining_attempts) | 410 code/link expired
//                               | 422 password policy / same-as-old | 404 disabled
//   GET  /auth/reset-link       302 → /reset-password?token=…&email=…
//                               | ?error=expired|invalid
export type ResetPasswordPayload =
  | { email: string; code: string; new_password: string }
  | { token: string; new_password: string };

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
  register: (data: RegisterRequest) =>
    client.post<{ detail: string }>('/auth/register', data),
  verifyRegistration: (data: { email: string; code: string }) =>
    client.post<VerifyRegistrationResponse>('/auth/verify-registration', data),
  resendVerification: (email: string) =>
    client.post<{ detail?: string }>('/auth/resend-verification', { email }),
  checkUsername: (username: string) =>
    client.get<CheckUsernameResponse>('/auth/check-username', { params: { username } }),
  forgotPassword: (email: string) =>
    client.post<{ detail: string }>('/auth/forgot-password', { email }),
  resetPassword: (data: ResetPasswordPayload) =>
    client.post<VerifyRegistrationResponse>('/auth/reset-password', data),
  listDevices: () => client.get<DeviceInfo[]>('/auth/devices'),
  removeDevice: (id: number) => client.delete(`/auth/devices/${id}`),
};
