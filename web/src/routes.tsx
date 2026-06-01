import { Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import ETFList from './pages/ETFList';
import ETFDetail from './pages/ETFDetail';
import Screen from './pages/Screen';
import PoolList from './pages/PoolList';
import PoolDetail from './pages/PoolDetail';
import ScoreRanking from './pages/ScoreRanking';
import ReportBrowser from './pages/ReportBrowser';
import CorrelationAnalysis from './pages/CorrelationAnalysis';
import ReturnComparison from './pages/ReturnComparison';
import SectorRotation from './pages/SectorRotation';
import ETFScanner from './pages/ETFScanner';
import NotificationConfig from './pages/NotificationConfig';
import StrategyList from './pages/StrategyList';
import BacktestList from './pages/BacktestList';
import BacktestDetail from './pages/BacktestDetail';
import SignalDashboard from './pages/SignalDashboard';

export interface RouteConfig {
  path: string;
  element: React.ReactNode;
  auth?: boolean;
  menu?: {
    name: string;
    icon?: string;
  };
}

export const routes: RouteConfig[] = [
  { path: '/login', element: <Login />, auth: false },
  { path: '/dashboard', element: <Dashboard />, auth: true, menu: { name: '首页看板', icon: 'DashboardOutlined' } },
  { path: '/etfs', element: <ETFList />, auth: true, menu: { name: 'ETF列表', icon: 'OrderedListOutlined' } },
  { path: '/etfs/:code', element: <ETFDetail />, auth: true },
  { path: '/screen', element: <Screen />, auth: true, menu: { name: '全市场筛选器', icon: 'FilterOutlined' } },
  { path: '/pools', element: <PoolList />, auth: true, menu: { name: '标的池管理', icon: 'AppstoreOutlined' } },
  { path: '/pools/:id', element: <PoolDetail />, auth: true },
  { path: '/scores', element: <ScoreRanking />, auth: true, menu: { name: '评分排名', icon: 'TrophyOutlined' } },
  { path: '/reports', element: <ReportBrowser />, auth: true, menu: { name: '报告浏览', icon: 'FileTextOutlined' } },
  { path: '/correlation', element: <CorrelationAnalysis />, auth: true, menu: { name: '相关性分析', icon: 'ApartmentOutlined' } },
  { path: '/comparison', element: <ReturnComparison />, auth: true, menu: { name: '收益对比', icon: 'LineChartOutlined' } },
  { path: '/sector-rotation', element: <SectorRotation />, auth: true, menu: { name: '板块轮动', icon: 'BarChartOutlined' } },
  { path: '/scanner', element: <ETFScanner />, auth: true, menu: { name: '全市场扫描', icon: 'ScanOutlined' } },
  { path: '/notifications', element: <NotificationConfig />, auth: true, menu: { name: '推送配置', icon: 'NotificationOutlined' } },
  { path: '/strategies', element: <StrategyList />, auth: true, menu: { name: '策略管理', icon: 'SettingOutlined' } },
  { path: '/backtests', element: <BacktestList />, auth: true, menu: { name: '回测管理', icon: 'ExperimentOutlined' } },
  { path: '/backtests/:id', element: <BacktestDetail />, auth: true },
  { path: '/signals', element: <SignalDashboard />, auth: true, menu: { name: '交易信号', icon: 'ThunderboltOutlined' } },
  { path: '/', element: <Navigate to="/dashboard" replace />, auth: true },
];

export const menuRoutes = routes.filter((r) => r.menu);
