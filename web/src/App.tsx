import { Component, type ReactNode, type ErrorInfo } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
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
  const { isError, error, isLoading, refetch } = useMe();
  const { logout } = useAuthStore();

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
  return <>{children}</>;
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
    // eslint-disable-next-line no-console
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
            <Route
              path="/login"
              element={routes.find((r) => r.path === '/login')?.element}
            />
            <Route element={<AppLayout />}>
              {routes
                .filter((r) => r.auth !== false && r.path !== '/login')
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
          <AIHelpDrawer />
        </AIHelpProvider>
      </BrowserRouter>
    </GlobalErrorBoundary>
  );
}
