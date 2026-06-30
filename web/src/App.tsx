import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { routes } from './routes';
import AppLayout from './components/AppLayout';
import { AIHelpProvider } from './components/AIHelpProvider';
import AIHelpDrawer from './components/AIHelpDrawer';
import { useAuthStore } from './stores/auth';
import { useMe } from './hooks/useAuth';
import { useEffect } from 'react';

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore();
  const { isError } = useMe();
  const { logout } = useAuthStore();

  useEffect(() => {
    if (isError) {
      logout();
    }
  }, [isError, logout]);

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

export default function App() {
  return (
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
                      route.path === '/admin/users' || route.path === '/admin/deployments' ? (
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
  );
}
