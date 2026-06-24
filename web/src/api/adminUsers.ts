import client from './client';
import type {
  UserAdminItem,
  UserCreateRequest,
  UserUpdateRequest,
  PasswordResetRequest,
} from '@/types/user';

export const adminUsersApi = {
  list: () => client.get<UserAdminItem[]>('/admin/users'),
  create: (data: UserCreateRequest) => client.post<UserAdminItem>('/admin/users', data),
  update: (id: number, data: UserUpdateRequest) =>
    client.put<UserAdminItem>(`/admin/users/${id}`, data),
  delete: (id: number) => client.delete(`/admin/users/${id}`),
  resetPassword: (id: number, data: PasswordResetRequest) =>
    client.post(`/admin/users/${id}/reset-password`, data),
};
