import client from './client';
import type {
  UserAdminItem,
  UserCreateRequest,
  UserCreateResponse,
  UserUpdateRequest,
  PasswordResetRequest,
  PasswordResetResponse,
} from '@/types/user';

export const adminUsersApi = {
  list: () => client.get<UserAdminItem[]>('/admin/users'),
  create: (data: UserCreateRequest) => client.post<UserCreateResponse>('/admin/users', data),
  update: (id: number, data: UserUpdateRequest) =>
    client.put<UserAdminItem>(`/admin/users/${id}`, data),
  delete: (id: number) => client.delete(`/admin/users/${id}`),
  resetPassword: (id: number, data: PasswordResetRequest) =>
    client.post<PasswordResetResponse>(`/admin/users/${id}/reset-password`, data),
};
