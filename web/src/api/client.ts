import axios from 'axios';

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
  paramsSerializer: {
    indexes: null,
  },
});

// Track in-flight refresh to avoid concurrent refresh attempts
let isRefreshing = false;
let refreshQueue: Array<{ resolve: (token: string) => void; reject: (err: unknown) => void }> = [];

function queueRefresh(resolve: (token: string) => void, reject: (err: unknown) => void) {
  refreshQueue.push({ resolve, reject });
}

function drainRefreshQueue(token: string | null, error: unknown | null) {
  refreshQueue.forEach(({ resolve, reject }) => {
    if (token) resolve(token);
    else reject(error);
  });
  refreshQueue = [];
}

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      const refreshToken = localStorage.getItem('refresh_token');

      if (!refreshToken) {
        // No refresh token → force logout
        localStorage.removeItem('token');
        localStorage.removeItem('refresh_token');
        import('@/stores/auth')
          .then(({ useAuthStore }) => useAuthStore.getState().logout())
          .catch(() => localStorage.removeItem('auth-storage'));
        window.location.href = '/login';
        return Promise.reject(error);
      }

      if (isRefreshing) {
        // Another request is already refreshing → queue
        return new Promise<string>((resolve, reject) => {
          queueRefresh((token: string) => {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            resolve(client(originalRequest));
          }, reject);
        });
      }

      isRefreshing = true;
      originalRequest._retry = true;

      try {
        const { data } = await axios.post(
          `${import.meta.env.VITE_API_BASE_URL || '/api/v1'}/auth/refresh`,
          { refresh_token: refreshToken }
        );
        const newAccessToken = data.access_token;

        // Store new token
        localStorage.setItem('token', newAccessToken);
        import('@/stores/auth')
          .then(({ useAuthStore }) => useAuthStore.getState().setTokens(newAccessToken, refreshToken))
          .catch(() => {});

        // Drain queued requests
        drainRefreshQueue(newAccessToken, null);

        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
        return client(originalRequest);
      } catch (refreshError) {
        drainRefreshQueue(null, refreshError);
        localStorage.removeItem('token');
        localStorage.removeItem('refresh_token');
        import('@/stores/auth')
          .then(({ useAuthStore }) => useAuthStore.getState().logout())
          .catch(() => localStorage.removeItem('auth-storage'));
        window.location.href = '/login';
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    if (error.response?.status === 401) {
      // Already retried or no refresh token — clean up
      localStorage.removeItem('token');
      localStorage.removeItem('refresh_token');
      import('@/stores/auth')
        .then(({ useAuthStore }) => useAuthStore.getState().logout())
        .catch(() => localStorage.removeItem('auth-storage'));
      window.location.href = '/login';
    }

    return Promise.reject(error);
  }
);

export default client;
