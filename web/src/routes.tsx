import { lazy, Suspense } from 'react';
import { Navigate } from 'react-router-dom';

const Login = lazy(() => import('./pages/Login'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const ETFList = lazy(() => import('./pages/ETFList'));
const ETFDetail = lazy(() => import('./pages/ETFDetail'));
const Screen = lazy(() => import('./pages/Screen'));
const PoolList = lazy(() => import('./pages/PoolList'));
const PoolDetail = lazy(() => import('./pages/PoolDetail'));
const ScoreRanking = lazy(() => import('./pages/ScoreRanking'));
const ReportBrowser = lazy(() => import('./pages/ReportBrowser'));
const CorrelationAnalysis = lazy(() => import('./pages/CorrelationAnalysis'));
const ReturnComparison = lazy(() => import('./pages/ReturnComparison'));
const SectorRotation = lazy(() => import('./pages/SectorRotation'));
const ETFScanner = lazy(() => import('./pages/ETFScanner'));
const NotificationConfig = lazy(() => import('./pages/NotificationConfig'));
const StrategyList = lazy(() => import('./pages/StrategyList'));
const BacktestList = lazy(() => import('./pages/BacktestList'));
const BacktestDetail = lazy(() => import('./pages/BacktestDetail'));
const SignalDashboard = lazy(() => import('./pages/SignalDashboard'));
const AdminUsers = lazy(() => import('./pages/AdminUsers'));
const AdminDeployments = lazy(() => import('./pages/AdminDeployments'));
const ResearchNotes = lazy(() => import('./pages/ResearchNotes'));
const SentimentDashboard = lazy(() => import('./pages/SentimentDashboard'));
const AIChat = lazy(() => import('./pages/AIChat'));
const CryptoList = lazy(() => import('./pages/CryptoList'));
// CryptoDetail disabled until backend endpoints are ready
// const CryptoDetail = lazy(() => import('./pages/CryptoDetail'));
const PaperTrading = lazy(() => import('./pages/PaperTrading'));

export interface RouteConfig {
  path: string;
  element: React.ReactNode;
  auth?: boolean;
  menu?: {
    name: string;
    icon?: string;
    /** Render a divider line before this item */
    dividerBefore?: boolean;
  };
}

const wrap = (Component: React.ComponentType) => (
  <Suspense fallback={<div style={{ padding: 40, textAlign: 'center' }}>加载中...</div>}>
    <Component />
  </Suspense>
);

export const routes: RouteConfig[] = [
  { path: '/login', element: wrap(Login), auth: false },
  { path: '/dashboard', element: wrap(Dashboard), auth: true, menu: { name: '首页看板', icon: 'DashboardOutlined' } },
  { path: '/etfs', element: wrap(ETFList), auth: true, menu: { name: '标的列表', icon: 'OrderedListOutlined' } },
  { path: '/etfs/:code', element: wrap(ETFDetail), auth: true },
  { path: '/screen', element: wrap(Screen), auth: true, menu: { name: '全市场筛选器', icon: 'FilterOutlined' } },
  { path: '/pools', element: wrap(PoolList), auth: true, menu: { name: '标的池管理', icon: 'AppstoreOutlined' } },
  { path: '/pools/:id', element: wrap(PoolDetail), auth: true },
  { path: '/scores', element: wrap(ScoreRanking), auth: true, menu: { name: '评分排名', icon: 'TrophyOutlined', dividerBefore: true } },
  { path: '/reports', element: wrap(ReportBrowser), auth: true, menu: { name: '报告浏览', icon: 'FileTextOutlined' } },
  { path: '/correlation', element: wrap(CorrelationAnalysis), auth: true, menu: { name: '相关性分析', icon: 'ApartmentOutlined' } },
  { path: '/comparison', element: wrap(ReturnComparison), auth: true, menu: { name: '收益对比', icon: 'LineChartOutlined' } },
  { path: '/sector-rotation', element: wrap(SectorRotation), auth: true, menu: { name: '板块轮动', icon: 'BarChartOutlined' } },
  { path: '/scanner', element: wrap(ETFScanner), auth: true, menu: { name: '全市场扫描', icon: 'ScanOutlined' } },
  { path: '/notifications', element: wrap(NotificationConfig), auth: true, menu: { name: '推送配置', icon: 'NotificationOutlined', dividerBefore: true } },
  { path: '/strategies', element: wrap(StrategyList), auth: true, menu: { name: '策略管理', icon: 'SettingOutlined' } },
  { path: '/backtests', element: wrap(BacktestList), auth: true, menu: { name: '回测管理', icon: 'ExperimentOutlined' } },
  { path: '/backtests/:id', element: wrap(BacktestDetail), auth: true },
  { path: '/signals', element: wrap(SignalDashboard), auth: true, menu: { name: '交易信号', icon: 'ThunderboltOutlined' } },
  // ---- 加密货币 ----
  { path: '/crypto', element: wrap(CryptoList), auth: true, menu: { name: '加密货币', icon: 'BitcoinOutlined', dividerBefore: true } },
  // { path: '/crypto/:code', element: wrap(CryptoDetail), auth: true }, // disabled until backend ready
  { path: '/paper-trading', element: wrap(PaperTrading), auth: true, menu: { name: '模拟交易', icon: 'DollarOutlined' } },
  // ---- AI 研究 ----
  { path: '/research', element: wrap(ResearchNotes), auth: true, menu: { name: 'AI研究笔记', icon: 'ReadOutlined' } },
  { path: '/sentiment', element: wrap(SentimentDashboard), auth: true, menu: { name: '情绪分析', icon: 'SmileOutlined' } },
  { path: '/chat', element: wrap(AIChat), auth: true, menu: { name: 'AI助手', icon: 'RobotOutlined' } },
  { path: '/admin/users', element: wrap(AdminUsers), auth: true, menu: { name: '用户管理', icon: 'TeamOutlined', dividerBefore: true } },
  { path: '/admin/deployments', element: wrap(AdminDeployments), auth: true, menu: { name: '部署管理', icon: 'CloudServerOutlined' } },
  { path: '/', element: <Navigate to="/dashboard" replace />, auth: true },
];

export const menuRoutes = routes.filter((r) => r.menu);
