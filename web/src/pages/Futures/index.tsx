import { useMemo, useState, type ReactNode } from 'react';
import './styles.css';
import {
  Tabs, Table, Space, Row, Col,
} from 'antd';
import {
  CaretUpOutlined, CaretDownOutlined, GoldOutlined, FireOutlined, SunOutlined, BarChartOutlined,
} from '@ant-design/icons';
import PageShell from '@/components/PageShell';
import Panel from '@/components/Panel';
import LoadingBlock from '@/components/LoadingBlock';
import PageHeader from '@/components/PageHeader';
import StatCard from '@/components/StatCard';
import EmptyState from '@/components/EmptyState';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import LastUpdated from '@/components/LastUpdated';
import HelpPopover from '@/components/HelpPopover';
import { useSettingsStore } from '@/stores/settings';
import { useChartMotion } from '@/hooks/useChartMotion';
import { NULL_PLACEHOLDER } from '@/utils/format';
import {
  useFuturesDashboard,
  useFuturesLeaderboard,
  useFuturesStats,
} from '@/api/futures';
import type { FuturesDailyBarOut, FuturesDashboardSection } from '@/api/futures';

const PRODUCTS = ['金属', '能源化工', '农产品', '金融期货'] as const;
type Product = (typeof PRODUCTS)[number];

const PRODUCT_ICON: Record<Product, ReactNode> = {
  金属: <GoldOutlined />,
  能源化工: <FireOutlined />,
  农产品: <SunOutlined />,
  金融期货: <BarChartOutlined />,
};

function fmtNum(v: string | number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return NULL_PLACEHOLDER;
  const n = typeof v === 'string' ? Number(v) : v;
  if (Number.isNaN(n)) return NULL_PLACEHOLDER;
  return n.toFixed(digits);
}

function fmtVol(v: number | null | undefined): string {
  if (v === null || v === undefined) return NULL_PLACEHOLDER;
  const n = Number(v);
  if (Number.isNaN(n)) return NULL_PLACEHOLDER;
  if (n >= 1e8) return `${(n / 1e8).toFixed(2)} 亿`;
  if (n >= 1e4) return `${(n / 1e4).toFixed(2)} 万`;
  return n.toFixed(0);
}

function changeCell(pct: number | null | undefined) {
  if (pct === null || pct === undefined) return <span className="ad-text-tertiary">{NULL_PLACEHOLDER}</span>;
  const positive = pct >= 0;
  const Icon = positive ? CaretUpOutlined : CaretDownOutlined;
  const cls = positive ? 'ad-change-cell ad-change-cell--rise' : 'ad-change-cell ad-change-cell--fall';
  return (
    <span className={`tabular-nums font-mono ${cls}`}>
      <Icon className="ad-icon-xs" />
      {`${positive ? '+' : ''}${pct.toFixed(2)}%`}
    </span>
  );
}

interface BarTableProps {
  bars: FuturesDailyBarOut[];
  showHeader?: boolean;
  maxRows?: number;
}

function BarTable({ bars, showHeader = false, maxRows = 10 }: BarTableProps) {
  const mode = useSettingsStore((s) => s.mode);
  const columns = [
    {
      title: '代码',
      dataIndex: 'code',
      width: 120,
      render: (v: string, record: FuturesDailyBarOut) => (
        /* 期货主力合约独立于 instruments 体系（app/models/futures.py 注明
           distinct from ETF/Instrument），没有 /instruments/:code 详情页，
           用 static 中性变体避免假可点外观。 */
        <InstrumentCodeTag code={v} name={record.name} variant="static" />
      ),
    },
    {
      title: '收盘',
      dataIndex: 'close',
      width: 90,
      render: (v: string | null) => (
        <span className="tabular-nums font-mono">
          {fmtNum(v)}
        </span>
      ),
    },
    {
      title: <HelpPopover termKey="settle" mode={mode}>结算</HelpPopover>,
      dataIndex: 'settle',
      width: 90,
      render: (v: string | null) => (
        <span className="tabular-nums font-mono">
          {fmtNum(v)}
        </span>
      ),
    },
    {
      title: '涨跌',
      dataIndex: 'settle_change_pct',
      width: 90,
      render: changeCell,
    },
    {
      title: '成交量',
      dataIndex: 'volume',
      width: 100,
      render: (v: number | null) => (
        <span className="tabular-nums font-mono">
          {fmtVol(v)}
        </span>
      ),
    },
  ];
  return (
    <div className="ad-table-scroll ad-table-sticky ad-scroll-hint">
      <Table
        dataSource={bars.slice(0, maxRows)}
        columns={columns}
        rowKey="code"
        size="small"
        scroll={{ x: 'max-content' }}
        pagination={false}
        showHeader={showHeader}
      />
    </div>
  );
}

interface TabContentProps {
  product: Product;
  section: FuturesDashboardSection | undefined;
}

function ProductTab({ product, section }: TabContentProps) {
  const bars = section?.items ?? [];
  const gainers = useMemo(
    () => [...bars].sort((a, b) => (b.settle_change_pct ?? 0) - (a.settle_change_pct ?? 0)).slice(0, 5),
    [bars],
  );
  const losers = useMemo(
    () => [...bars].sort((a, b) => (a.settle_change_pct ?? 0) - (b.settle_change_pct ?? 0)).slice(0, 5),
    [bars],
  );

  return (
    <div>
      {/* 「板块概况」已并入页首「市场概况」StatCard 网格（当前板块主力合约数），
          不再单独占位一个稀疏 Panel。 */}
      <Row gutter={16} className="ad-mb-5">
        <Col xs={24} md={12}>
          <Panel
            padding="sm"
            className="ad-table-card"
            title={
              <Space>
                <CaretUpOutlined className="futures-kpi-rise" />
                <span>涨幅榜 TOP 5</span>
              </Space>
            }
          >
            {gainers.length === 0 ? <EmptyState title="暂无数据" /> : <BarTable bars={gainers} />}
          </Panel>
        </Col>
        <Col xs={24} md={12}>
          <Panel
            padding="sm"
            className="ad-table-card"
            title={
              <Space>
                <CaretDownOutlined className="futures-kpi-fall" />
                <span>跌幅榜 TOP 5</span>
              </Space>
            }
          >
            {losers.length === 0 ? <EmptyState title="暂无数据" /> : <BarTable bars={losers} />}
          </Panel>
        </Col>
      </Row>

      <Panel title="全板块合约" className="ad-mb-5">
        {bars.length === 0 ? (
          <EmptyState title={`暂无${product}合约数据`} />
        ) : (
          <BarTable bars={bars} showHeader maxRows={20} />
        )}
      </Panel>
    </div>
  );
}

export default function Futures() {
  // Injects the shared `.adx-motion` stylesheet (Apple-pattern press/hover).
  useChartMotion();
  const { data: dashboard, isLoading: dashLoading, dataUpdatedAt } = useFuturesDashboard();
  const { data: gainers } = useFuturesLeaderboard('gainers');
  const { data: losers } = useFuturesLeaderboard('losers');
  const { data: stats } = useFuturesStats();
  // 当前选中的板块 tab —— 页首「市场概况」网格里的「主力合约数」跟随它。
  const [activeProduct, setActiveProduct] = useState<Product>('金属');

  const sectionsByProduct = useMemo(() => {
    const map: Record<string, FuturesDashboardSection> = {};
    for (const sec of dashboard?.sections ?? []) {
      map[sec.product] = sec;
    }
    return map;
  }, [dashboard]);

  const tabItems = PRODUCTS.map((p) => ({
    key: p,
    label: (
      <Space size={6}>
        {PRODUCT_ICON[p]}
        <span>{p}</span>
      </Space>
    ),
    children: dashLoading ? (
      <LoadingBlock size="md" />
    ) : (
      <ProductTab product={p} section={sectionsByProduct[p]} />
    ),
  }));

  const topGainer = (gainers?.items ?? [])[0];
  const topLoser = (losers?.items ?? [])[0];
  const latestDate = dashboard?.trade_date ?? stats?.latest_trade_date ?? null;
  // 当前板块的主力合约数（原「板块概况」Panel 的唯一内容，2026-08-25 并入此网格）。
  const activeSectionCount = sectionsByProduct[activeProduct]?.count ?? 0;

  return (
    <div className="adx-motion">
      <PageShell maxWidth="wide">
        <PageHeader
          eyebrow="期货"
          title="商品期货"
          description="国内期货主力合约行情（金属 / 能源化工 / 农产品 / 金融期货），每日收盘后更新"
          extra={<LastUpdated at={dataUpdatedAt} loading={dashLoading} />}
        />

      <Panel title="市场概况" className="ad-mb-5">
        <ResponsiveGrid cols={4} gap="md">
          <StatCard
            title="主力合约总数"
            value={stats?.total_contracts ?? dashboard?.total_contracts ?? 0}
            suffix="个"
          />
          <StatCard
            title="K线记录总数"
            value={stats?.total_bars ?? 0}
            suffix="条"
          />
          <StatCard
            title="数据日期"
            value={latestDate ?? NULL_PLACEHOLDER}
          />
          <StatCard
            title={`${activeProduct}主力合约数`}
            value={activeSectionCount}
            suffix="个"
          />
          <StatCard
            title="领头羊 / 领跌"
            value={
              topGainer && topLoser ? (
                <span className="ad-flex ad-gap-2 ad-items-center">
                  {/* 期货合约无标的详情页，用 static 中性变体（纯展示） */}
                  <InstrumentCodeTag code={topGainer.code} name={topGainer.name} variant="static" />
                  <span className="ad-text-tertiary ad-text-small">/</span>
                  <InstrumentCodeTag code={topLoser.code} name={topLoser.name} variant="static" />
                </span>
              ) : topGainer ? (
                <InstrumentCodeTag code={topGainer.code} name={topGainer.name} variant="static" />
              ) : topLoser ? (
                <InstrumentCodeTag code={topLoser.code} name={topLoser.name} variant="static" />
              ) : (
                NULL_PLACEHOLDER
              )
            }
          />
        </ResponsiveGrid>
      </Panel>

        <Tabs
          items={tabItems}
          activeKey={activeProduct}
          onChange={(key) => setActiveProduct(key as Product)}
        />
      </PageShell>
    </div>
  );
}
