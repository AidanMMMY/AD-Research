import axios from 'axios';

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      // Keep zustand auth store in sync so the login page does not immediately
      // redirect back to /dashboard while the 401 response is handling logout.
      import('@/stores/auth')
        .then(({ useAuthStore }) => {
          useAuthStore.getState().logout();
        })
        .catch(() => {
          // Fallback: if the store module can't be loaded, at least clear the
          // persisted storage entry so the next render starts unauthenticated.
          localStorage.removeItem('auth-storage');
        });
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default client;
