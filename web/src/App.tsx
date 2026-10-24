import { Component, type ReactNode, type ErrorInfo } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import { routes } from './routes';
import AppLayout from './components/AppLayout';
import { AIHelpProvider } from './components/AIHelpProvider';
import AIHelpDrawer from './components/AIHelpDrawer';
import { useAuthStore } from './stores/auth';
import { useMe } from './hooks/useAuth';
import { useEffect } from 'react';
import { Spin, Alert, Button } from 'antd';

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore();
  const { data: meResponse, isError, error, isLoading, refetch } = useMe();
  const { logout } = useAuthStore();
  const location = useLocation();

  const isUnauthorized = axios.isAxiosError(error) && error.response?.status === 401;

  useEffect(() => {
    // Only a 401 means the session is truly invalid — transient failures
    // (5xx, network blips) must not kick the user out.
    if (isError && isUnauthorized) {
      logout();
    }
  }, [isError, isUnauthorized, logout]);

  // If there is a token in storage but /auth/me hasn't finished yet, wait
  // so that protected pages don't mount with a potentially stale/expired token.
  if (isAuthenticated && isLoading) {
    return (
      <div className="auth-loading">
        <Spin size="large" />
      </div>
    );
  }

  // Non-401 failure: keep the session and offer a manual retry instead of
  // logging the user out on every backend hiccup.
  if (isAuthenticated && isError && !isUnauthorized) {
    return (
      <div className="global-error-boundary">
        <Alert
          message="无法获取用户信息"
          description="网络或服务暂时异常，请稍后重试。"
          type="error"
          showIcon
          action={<Button onClick={() => refetch()}>重试</Button>}
        />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // Persisted user data can lag this query by one effect. Never mount a
  // protected page until the current /me response is available.
  const currentUser = meResponse?.data;
  if (!currentUser) {
    return (
      <div className="auth-loading">
        <Spin size="large" />
      </div>
    );
  }

  // Forced first-login password change (2026-10-24): prefer the fresh /me
  // flag over the persisted copy so children cannot mount in the gap before
  // useMe synchronizes the auth store.
  if (currentUser.must_change_password && location.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />;
  }
  return <>{children}</>;
}

function AuthenticatedAIHelpDrawer() {
  const { data: meResponse } = useMe();
  // RequireAuth guarantees a fresh identity before mounting this child. Keep
  // the forced-password surface free of AI status requests that must fail 403.
  if (meResponse?.data.must_change_password) return null;
  return <AIHelpDrawer />;
}

function AdminRouteGuard({ children }: { children: React.ReactNode }) {
  const { user } = useAuthStore();
  if (user?.role !== 'admin') {
    return <Navigate to="/dashboard" replace />;
  }
  return <>{children}</>;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
}

class GlobalErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Global error boundary caught an error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="global-error-boundary">
          <Alert
            message="页面发生错误"
            description={
              this.state.error?.message || '应用出现未知错误，请刷新页面重试。'
            }
            type="error"
            showIcon
            action={
              <Button onClick={() => window.location.reload()}>刷新页面</Button>
            }
          />
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  return (
    <GlobalErrorBoundary>
      <BrowserRouter>
        <AIHelpProvider>
          <Routes>
            {/* Public standalone auth pages (login + self-registration, 2026-10-25):
                rendered outside AppLayout/RequireAuth so guests can reach them. */}
            {routes
              .filter((r) => r.auth === false)
              .map((route) => (
                <Route key={route.path} path={route.path} element={route.element} />
              ))}
            <Route element={<AppLayout />}>
              {routes
                .filter((r) => r.auth !== false)
                .map((route) => (
                  <Route
                    key={route.path}
                    path={route.path}
                    element={
                      route.auth ? (
                        route.admin ? (
                          <RequireAuth>
                            <AdminRouteGuard>{route.element}</AdminRouteGuard>
                          </RequireAuth>
                        ) : (
                          <RequireAuth>{route.element}</RequireAuth>
                        )
                      ) : (
                        route.element
                      )
                    }
                  />
                ))}
            </Route>
          </Routes>
          {/* AIHelpDrawer 仅登录后需要；全局渲染会让 /login 在未登录时也
              调用 /research/ai/status 触发 403（2026-08-08 回归修复）。 */}
          <RequireAuth>
            <AuthenticatedAIHelpDrawer />
          </RequireAuth>
        </AIHelpProvider>
      </BrowserRouter>
    </GlobalErrorBoundary>
  );
}
