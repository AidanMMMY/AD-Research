import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { adminUsersApi } from '@/api';
import type {
  UserCreateRequest,
  UserUpdateRequest,
  PasswordResetRequest,
} from '@/types/user';

export function useAdminUsers() {
  const queryClient = useQueryClient();

  const usersQuery = useQuery({
    queryKey: ['admin-users'],
    queryFn: async () => {
      const res = await adminUsersApi.list();
      return res.data;
    },
    staleTime: 30_000,
  });

  const createMutation = useMutation({
    mutationFn: (data: UserCreateRequest) => adminUsersApi.create(data),
    // Creation can return a one-time plaintext password. Once the page has
    // copied it to local state and reset the observer, collect it immediately.
    gcTime: 0,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: UserUpdateRequest }) =>
      adminUsersApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => adminUsersApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] });
    },
  });

  const resetPasswordMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: PasswordResetRequest }) =>
      adminUsersApi.resetPassword(id, data),
    // Reset responses can contain the same one-time plaintext secret.
    gcTime: 0,
  });

  return {
    users: usersQuery.data || [],
    isLoading: usersQuery.isLoading,
    error: usersQuery.error,
    create: createMutation.mutateAsync,
    update: updateMutation.mutateAsync,
    delete: deleteMutation.mutateAsync,
    resetPassword: resetPasswordMutation.mutateAsync,
    resetCreateMutation: createMutation.reset,
    resetResetPasswordMutation: resetPasswordMutation.reset,
    isCreating: createMutation.isPending,
    isUpdating: updateMutation.isPending,
    isDeleting: deleteMutation.isPending,
    isResettingPassword: resetPasswordMutation.isPending,
  };
}
