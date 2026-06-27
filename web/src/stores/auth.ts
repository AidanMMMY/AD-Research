import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { authApi } from '@/api';

interface User {
  username: string;
  role: string;
}

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: User | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  setTokens: (access: string, refresh: string) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,

      login: async (username, password) => {
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

      setTokens: (access, refresh) => {
        localStorage.setItem('token', access);
        if (refresh) localStorage.setItem('refresh_token', refresh);
        set({ token: access, refreshToken: refresh || undefined, isAuthenticated: true });
      },
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
