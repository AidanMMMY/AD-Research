export interface UserAdminItem {
  id: number;
  username: string;
  role: 'admin' | 'user';
  is_active: boolean;
  must_change_password?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface UserCreateRequest {
  username: string;
  /** Optional — omitted means the server generates a random password */
  password?: string;
  role: 'admin' | 'user';
  is_active?: boolean;
}

export interface UserCreateResponse extends UserAdminItem {
  /** One-time plaintext password, only present in the create response */
  initial_password?: string | null;
}

export interface UserUpdateRequest {
  role?: 'admin' | 'user';
  is_active?: boolean;
}

export interface PasswordResetRequest {
  /** Optional — omitted means the server generates a random password */
  new_password?: string;
}

export interface PasswordResetResponse {
  message: string;
  /** One-time plaintext password, only present in the reset response */
  initial_password?: string | null;
}
