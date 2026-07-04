import { lazy, Suspense } from 'react';
import { Navigate, useParams } from 'react-router-dom';

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
const Portfolio = lazy(() => import('./pages/Portfolio'));
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
const GlobalMarkets = lazy(() => import('./pages/GlobalMarkets'));
const Learning = lazy(() => import('./pages/Learning'));

export type SidebarGroupKey =
  | 'home'
  | 'market'
  | 'screen'
  | 'research'
  | 'macro'
  | 'quant'
  | 'trade'
  | 'learn'
  | 'notify'
  | 'ops'
  | 'admin';

export interface RouteConfig {
  path: string;
  element: React.ReactNode;
  auth?: boolean;
  menu?: {
    name: string;
    icon?: string;
    /** Optional label override (defaults to menu.name) */
    label?: string;
    /** Logical sidebar group used to render 1-level + 2-level collapsible UI */
    group?: SidebarGroupKey;
  };
}

const wrap = (Component: React.ComponentType) => (
  <Suspense fallback={<div className="route-suspense">加载中...</div>}>
    <Component />
  </Suspense>
);

const LegacyEtfRedirect = () => {
  const { code } = useParams<{ code: string }>();
  return <Navigate to={`/instruments/${code}`} replace />;
};

export const routes: RouteConfig[] = [
  { path: '/login', element: wrap(Login), auth: false },
  // === 首页 ===
  { path: '/dashboard', element: wrap(Dashboard), auth: true, menu: { name: '首页看板', icon: 'HomeOutlined', group: 'home' } },
  { path: '/global', element: wrap(GlobalMarkets), auth: true, menu: { name: '全球速览', label: '全球速览', icon: 'CompassOutlined', group: 'home' } },
  { path: '/instruments', element: wrap(InstrumentList), auth: true, menu: { name: '标的列表', icon: 'OrderedListOutlined', group: 'market' } },
  { path: '/instruments/:code', element: wrap(InstrumentDetail), auth: true },
  // Backward-compatible redirects
  { path: '/etfs', element: <Navigate to="/instruments" replace />, auth: true },
  { path: '/etfs/:code', element: <LegacyEtfRedirect />, auth: true },
  // ---- 个股（合并到标的列表，通过 instrument_type=STOCK 筛选） ----
  { path: '/stocks', element: wrap(StocksList), auth: true },
  { path: '/stocks/:code', element: wrap(StockDetail), auth: true },
  // === 行情与市场 ===
  { path: '/sector-rotation', element: wrap(SectorRotation), auth: true, menu: { name: '板块轮动', icon: 'BarChartOutlined', group: 'market' } },
  { path: '/correlation', element: wrap(CorrelationAnalysis), auth: true, menu: { name: '相关性分析', icon: 'ApartmentOutlined', group: 'market' } },
  { path: '/comparison', element: wrap(ReturnComparison), auth: true, menu: { name: '收益对比', icon: 'LineChartOutlined', group: 'market' } },
  { path: '/futures', element: wrap(Futures), auth: true, menu: { name: '商品期货', icon: 'BlockOutlined', group: 'market' } },
  // === 选股工具 ===
  { path: '/screen', element: wrap(Screen), auth: true, menu: { name: '全市场筛选器', icon: 'FilterOutlined', group: 'screen' } },
  { path: '/scanner', element: wrap(MarketScanner), auth: true, menu: { name: '全市场扫描', icon: 'ScanOutlined', group: 'screen' } },
  { path: '/scores', element: wrap(ScoreRanking), auth: true, menu: { name: '评分排名', icon: 'TrophyOutlined', group: 'screen' } },
  { path: '/pools', element: wrap(PoolList), auth: true, menu: { name: '标的池管理', icon: 'AppstoreOutlined', group: 'screen' } },
  { path: '/pools/:id', element: wrap(PoolDetail), auth: true },
  // === 资讯与研究 ===
  { path: '/news', element: wrap(NewsFeed), auth: true, menu: { name: '资讯', icon: 'ReadOutlined', group: 'research' } },
  { path: '/news/:id', element: wrap(NewsDetail), auth: true },
  { path: '/research', element: wrap(ResearchNotes), auth: true, menu: { name: 'AI 研究笔记', label: 'AI 研究笔记', icon: 'BulbOutlined', group: 'research' } },
  { path: '/reports', element: wrap(ReportBrowser), auth: true, menu: { name: '报告浏览', icon: 'FileTextOutlined', group: 'research' } },
  { path: '/research-reports', element: wrap(ResearchReports), auth: true, menu: { name: '研报库', icon: 'FilePdfOutlined', group: 'research' } },
  { path: '/cninfo-reports', element: wrap(CninfoReports), auth: true, menu: { name: '巨潮报告', icon: 'FilePdfOutlined', group: 'research' } },
  { path: '/sec-filings', element: wrap(SECFilings), auth: true, menu: { name: 'SEC 公告', icon: 'BankOutlined', group: 'research' } },
  { path: '/listing-preview', element: wrap(ListingPreview), auth: true, menu: { name: '上市预告', icon: 'CalendarOutlined', group: 'research' } },
  // === 宏观与情绪 ===
  { path: '/macro', element: wrap(Macro), auth: true, menu: { name: '宏观经济', icon: 'FundProjectionScreenOutlined', group: 'macro' } },
  { path: '/sentiment', element: wrap(SentimentOverview), auth: true, menu: { name: '市场情绪', icon: 'HeartOutlined', group: 'macro' } },
  { path: '/search-trends', element: wrap(SearchTrends), auth: true, menu: { name: '搜索热度', icon: 'FireOutlined', group: 'macro' } },
  // === 量化与回测 ===
  { path: '/strategies', element: wrap(StrategyList), auth: true, menu: { name: '策略管理', icon: 'SettingOutlined', group: 'quant' } },
  { path: '/strategy-library', element: wrap(StrategyLibrary), auth: true, menu: { name: '策略库', icon: 'BookOutlined', group: 'quant' } },
  { path: '/backtests', element: wrap(BacktestList), auth: true, menu: { name: '回测管理', icon: 'ExperimentOutlined', group: 'quant' } },
  { path: '/backtests/:id', element: wrap(BacktestDetail), auth: true },
  { path: '/signals', element: wrap(SignalDashboard), auth: true, menu: { name: '交易信号', icon: 'ThunderboltOutlined', group: 'quant' } },
  // === 交易 ===
  { path: '/paper-trading', element: wrap(PaperTrading), auth: true, menu: { name: '模拟交易', icon: 'DollarOutlined', group: 'trade' } },
  { path: '/live-trading', element: wrap(TradingPanel), auth: true, menu: { name: '真实交易', icon: 'ThunderboltOutlined', group: 'trade' } },
  // Portfolio Center (P1) — aggregation page reachable from the Dashboard
  // "组合中心" chip row AND from the sidebar (trade group).
  { path: '/portfolio', element: wrap(Portfolio), auth: true, menu: { name: '我的组合', icon: 'WalletOutlined', group: 'trade' } },
  { path: '/crypto', element: wrap(CryptoList), auth: true, menu: { name: '加密货币', icon: 'GoldOutlined', group: 'trade' } },
  { path: '/crypto/:code', element: wrap(CryptoDetail), auth: true },
  // === 学习 & 另类数据 ===
  { path: '/microstructure', element: wrap(Microstructure), auth: true, menu: { name: '微结构数据', icon: 'FundOutlined', group: 'learn' } },
  { path: '/learning', element: wrap(Learning), auth: true, menu: { name: '教程中心', label: '教程中心', icon: 'BookOutlined', group: 'learn' } },
  { path: '/chat', element: wrap(AIChat), auth: true, menu: { name: 'AI 助手', label: 'AI 助手', icon: 'RobotOutlined', group: 'learn' } },
  // === 通知 ===
  { path: '/notifications', element: wrap(NotificationConfig), auth: true, menu: { name: '推送配置', icon: 'NotificationOutlined', group: 'notify' } },
  { path: '/notification-logs', element: wrap(NotificationLogs), auth: true, menu: { name: '通知日志', icon: 'FileTextOutlined', group: 'notify' } },
  // === 运维 ===
  { path: '/etl-status', element: wrap(ETLStatus), auth: true, menu: { name: 'ETL 状态', label: 'ETL 状态', icon: 'ClockCircleOutlined', group: 'ops' } },
  { path: '/admin/etl-status', element: wrap(ETLOpsDashboard), auth: true, menu: { name: 'ETL 运维看板', icon: 'MonitorOutlined', group: 'ops' } },
  { path: '/news/health', element: wrap(NewsHealth), auth: true, menu: { name: '资讯健康度', icon: 'MonitorOutlined', group: 'ops' } },
  // === 管理 ===
  { path: '/admin/users', element: wrap(AdminUsers), auth: true, menu: { name: '用户管理', icon: 'TeamOutlined', group: 'admin' } },
  { path: '/admin/deployments', element: wrap(AdminDeployments), auth: true, menu: { name: '部署管理', icon: 'CloudServerOutlined', group: 'admin' } },
  { path: '/', element: <Navigate to="/dashboard" replace />, auth: true },
];

export const menuRoutes = routes.filter((r) => r.menu);

/**
 * Group order + display metadata used by the sidebar's 1-level + 2-level
 * collapsible UI. Defined here (single source of truth) so routes.tsx and
 * AppLayout share the same canonical group ordering.
 */
export interface SidebarGroup {
  key: SidebarGroupKey;
  label: string;
  icon: string;
}

export const sidebarGroups: SidebarGroup[] = [
  { key: 'home',     label: '首页',             icon: 'HomeOutlined' },
  { key: 'market',   label: '行情与市场',       icon: 'LineChartOutlined' },
  { key: 'screen',   label: '选股工具',         icon: 'FilterOutlined' },
  { key: 'research', label: '资讯与研究',       icon: 'ReadOutlined' },
  { key: 'macro',    label: '宏观与情绪',       icon: 'FundProjectionScreenOutlined' },
  { key: 'quant',    label: '量化与回测',       icon: 'ExperimentOutlined' },
  { key: 'trade',    label: '交易',             icon: 'DollarOutlined' },
  { key: 'learn',    label: '学习 & 另类数据',  icon: 'BookOutlined' },
  { key: 'notify',   label: '通知',             icon: 'BellOutlined' },
  { key: 'ops',      label: '运维',             icon: 'ToolOutlined' },
  { key: 'admin',    label: '管理',             icon: 'SafetyCertificateOutlined' },
];
