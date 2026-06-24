export interface UserAdminItem {
  id: number;
  username: string;
  role: 'admin' | 'user';
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface UserCreateRequest {
  username: string;
  password: string;
  role: 'admin' | 'user';
  is_active?: boolean;
}

export interface UserUpdateRequest {
  role?: 'admin' | 'user';
  is_active?: boolean;
}

export interface PasswordResetRequest {
  new_password: string;
}
