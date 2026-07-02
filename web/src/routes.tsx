import { lazy, Suspense } from 'react';
import { Navigate } from 'react-router-dom';

const Login = lazy(() => import('./pages/Login'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const InstrumentList = lazy(() => import('./pages/InstrumentList'));
const InstrumentDetail = lazy(() => import('./pages/InstrumentDetail'));
const StocksList = lazy(() => import('./pages/StocksList'));
const StockDetail = lazy(() => import('./pages/StockDetail'));
const Screen = lazy(() => import('./pages/Screen'));
const PoolList = lazy(() => import('./pages/PoolList'));
const PoolDetail = lazy(() => import('./pages/PoolDetail'));
const ScoreRanking = lazy(() => import('./pages/ScoreRanking'));
const ReportBrowser = lazy(() => import('./pages/ReportBrowser'));
const CorrelationAnalysis = lazy(() => import('./pages/CorrelationAnalysis'));
const ReturnComparison = lazy(() => import('./pages/ReturnComparison'));
const SectorRotation = lazy(() => import('./pages/SectorRotation'));
const Macro = lazy(() => import('./pages/Macro'));
const MarketScanner = lazy(() => import('./pages/MarketScanner'));
const NotificationConfig = lazy(() => import('./pages/NotificationConfig'));
const StrategyList = lazy(() => import('./pages/StrategyList'));
const StrategyLibrary = lazy(() => import('./pages/StrategyLibrary'));
const BacktestList = lazy(() => import('./pages/BacktestList'));
const BacktestDetail = lazy(() => import('./pages/BacktestDetail'));
const SignalDashboard = lazy(() => import('./pages/SignalDashboard'));
const AdminUsers = lazy(() => import('./pages/AdminUsers'));
const AdminDeployments = lazy(() => import('./pages/AdminDeployments'));
const ResearchNotes = lazy(() => import('./pages/ResearchNotes'));
const AIChat = lazy(() => import('./pages/AIChat'));
const CryptoList = lazy(() => import('./pages/CryptoList'));
const CryptoDetail = lazy(() => import('./pages/CryptoDetail'));
const ETLStatus = lazy(() => import('./pages/ETLStatus'));
const ETLOpsDashboard = lazy(() => import('./pages/ETLOpsDashboard'));
const NotificationLogs = lazy(() => import('./pages/NotificationLogs'));
const PaperTrading = lazy(() => import('./pages/PaperTrading'));
const TradingPanel = lazy(() => import('./pages/TradingPanel'));
const NewsFeed = lazy(() => import('./pages/News'));
const NewsDetail = lazy(() => import('./pages/News/detail'));
const NewsHealth = lazy(() => import('./pages/NewsHealth'));
const SentimentOverview = lazy(() => import('./pages/Sentiment'));
const ListingPreview = lazy(() => import('./pages/ListingPreview'));
const SECFilings = lazy(() => import('./pages/SECFilings'));
const Microstructure = lazy(() => import('./pages/Microstructure'));
const SearchTrends = lazy(() => import('./pages/SearchTrends'));
const ResearchReports = lazy(() => import('./pages/ResearchReports'));
const Futures = lazy(() => import('./pages/Futures'));
const CninfoReports = lazy(() => import('./pages/CninfoReports'));

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
  // New canonical routes
  { path: '/instruments', element: wrap(InstrumentList), auth: true, menu: { name: '标的列表', icon: 'OrderedListOutlined' } },
  { path: '/instruments/:code', element: wrap(InstrumentDetail), auth: true },
  // Backward-compatible redirects
  { path: '/etfs', element: <Navigate to="/instruments" replace />, auth: true },
  { path: '/etfs/:code', element: <Navigate to="/instruments/:code" replace />, auth: true },
  // ---- 个股（合并到标的列表，通过 instrument_type=STOCK 筛选） ----
  { path: '/stocks', element: wrap(StocksList), auth: true },
  { path: '/stocks/:code', element: wrap(StockDetail), auth: true },
  { path: '/screen', element: wrap(Screen), auth: true, menu: { name: '全市场筛选器', icon: 'FilterOutlined' } },
  { path: '/pools', element: wrap(PoolList), auth: true, menu: { name: '标的池管理', icon: 'AppstoreOutlined' } },
  { path: '/pools/:id', element: wrap(PoolDetail), auth: true },
  { path: '/scores', element: wrap(ScoreRanking), auth: true, menu: { name: '评分排名', icon: 'TrophyOutlined', dividerBefore: true } },
  { path: '/reports', element: wrap(ReportBrowser), auth: true, menu: { name: '报告浏览', icon: 'FileTextOutlined' } },
  { path: '/correlation', element: wrap(CorrelationAnalysis), auth: true, menu: { name: '相关性分析', icon: 'ApartmentOutlined' } },
  { path: '/comparison', element: wrap(ReturnComparison), auth: true, menu: { name: '收益对比', icon: 'LineChartOutlined' } },
  { path: '/sector-rotation', element: wrap(SectorRotation), auth: true, menu: { name: '板块轮动', icon: 'BarChartOutlined' } },
  { path: '/macro', element: wrap(Macro), auth: true, menu: { name: '宏观经济', icon: 'LineChartOutlined' } },
  { path: '/scanner', element: wrap(MarketScanner), auth: true, menu: { name: '全市场扫描', icon: 'ScanOutlined' } },
  { path: '/notifications', element: wrap(NotificationConfig), auth: true, menu: { name: '推送配置', icon: 'NotificationOutlined', dividerBefore: true } },
  { path: '/notification-logs', element: wrap(NotificationLogs), auth: true, menu: { name: '通知日志', icon: 'FileTextOutlined' } },
  { path: '/strategies', element: wrap(StrategyList), auth: true, menu: { name: '策略管理', icon: 'SettingOutlined' } },
  { path: '/strategy-library', element: wrap(StrategyLibrary), auth: true, menu: { name: '策略库', icon: 'BookOutlined' } },
  { path: '/backtests', element: wrap(BacktestList), auth: true, menu: { name: '回测管理', icon: 'ExperimentOutlined' } },
  { path: '/backtests/:id', element: wrap(BacktestDetail), auth: true },
  { path: '/signals', element: wrap(SignalDashboard), auth: true, menu: { name: '交易信号', icon: 'ThunderboltOutlined' } },
  // ---- 加密货币 ----
  { path: '/crypto', element: wrap(CryptoList), auth: true, menu: { name: '加密货币', icon: 'GoldOutlined', dividerBefore: true } },
  { path: '/crypto/:code', element: wrap(CryptoDetail), auth: true },
  { path: '/paper-trading', element: wrap(PaperTrading), auth: true, menu: { name: '模拟交易', icon: 'DollarOutlined' } },
  { path: '/live-trading', element: wrap(TradingPanel), auth: true, menu: { name: '真实交易', icon: 'ThunderboltOutlined' } },
  // ---- AI 研究 ----
  { path: '/research', element: wrap(ResearchNotes), auth: true, menu: { name: 'AI研究笔记', icon: 'ReadOutlined' } },
  { path: '/sentiment', element: wrap(SentimentOverview), auth: true, menu: { name: '情绪', icon: 'HeartOutlined' } },
  { path: '/listing-preview', element: wrap(ListingPreview), auth: true, menu: { name: '上市预告', icon: 'CalendarOutlined' } },
  { path: '/sec-filings', element: wrap(SECFilings), auth: true, menu: { name: 'SEC 公告', icon: 'BankOutlined' } },
  { path: '/microstructure', element: wrap(Microstructure), auth: true, menu: { name: '微结构数据', icon: 'FundOutlined' } },
  { path: '/search-trends', element: wrap(SearchTrends), auth: true, menu: { name: '搜索热度', icon: 'FireOutlined' } },
  { path: '/cninfo-reports', element: wrap(CninfoReports), auth: true, menu: { name: '巨潮报告', icon: 'FilePdfOutlined' } },
  { path: '/research-reports', element: wrap(ResearchReports), auth: true, menu: { name: '研报库', icon: 'FilePdfOutlined' } },
  { path: '/futures', element: wrap(Futures), auth: true, menu: { name: '商品期货', icon: 'BlockOutlined' } },
  { path: '/news', element: wrap(NewsFeed), auth: true, menu: { name: '资讯', icon: 'ReadOutlined' } },
  { path: '/news/:id', element: wrap(NewsDetail), auth: true },
  { path: '/news/health', element: wrap(NewsHealth), auth: true, menu: { name: '资讯健康度', icon: 'MonitorOutlined' } },
  { path: '/chat', element: wrap(AIChat), auth: true, menu: { name: 'AI助手', icon: 'RobotOutlined' } },
  { path: '/etl-status', element: wrap(ETLStatus), auth: true, menu: { name: 'ETL状态', icon: 'ClockCircleOutlined' } },
  { path: '/admin/users', element: wrap(AdminUsers), auth: true, menu: { name: '用户管理', icon: 'TeamOutlined', dividerBefore: true } },
  { path: '/admin/deployments', element: wrap(AdminDeployments), auth: true, menu: { name: '部署管理', icon: 'CloudServerOutlined' } },
  { path: '/admin/etl-status', element: wrap(ETLOpsDashboard), auth: true, menu: { name: 'ETL 运维看板', icon: 'MonitorOutlined' } },
  { path: '/', element: <Navigate to="/dashboard" replace />, auth: true },
];

export const menuRoutes = routes.filter((r) => r.menu);
