import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { authApi } from '@/api';

interface User {
  id: number;
  username: string;
  role: 'admin' | 'user';
}

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: User | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  setTokens: (access: string, refresh: string) => Promise<void>;
  setUser: (user: User | null) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,

      login: async (username, password) => {
        // Let axios errors propagate so the caller (Login page) can
        // distinguish 401 (bad credentials) from 5xx (server fault)
        // instead of collapsing them into one generic message.
        const { data } = await authApi.login({ username, password });
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('refresh_token', data.refresh_token);
        set({
          token: data.access_token,
          refreshToken: data.refresh_token,
          user: data.user,
          isAuthenticated: true,
        });
      },

      logout: async () => {
        try {
          await authApi.logout();
        } catch {
          // Ignore network errors during logout
        }
        localStorage.removeItem('token');
        localStorage.removeItem('refresh_token');
        set({ token: null, refreshToken: null, user: null, isAuthenticated: false });
      },

      setTokens: async (access, refresh) => {
        localStorage.setItem('token', access);
        if (refresh) localStorage.setItem('refresh_token', refresh);
        set({ token: access, refreshToken: refresh || null, isAuthenticated: true });
        try {
          const { data: user } = await authApi.me();
          set({ user });
        } catch {
          // 如果 me 失败，保持现有 user；useMe 的错误边界会处理 logout
        }
      },

      setUser: (user) => set({ user }),
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        token: state.token,
        refreshToken: state.refreshToken,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
