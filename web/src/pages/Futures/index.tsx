import { useMemo } from 'react';
import {
  Tabs, Table, Tag, Skeleton, Space, Statistic, Row, Col, Tooltip, Card,
} from 'antd';
import { CaretUpOutlined, CaretDownOutlined } from '@ant-design/icons';
import PageShell from '@/components/PageShell';
import Panel from '@/components/Panel';
import PageHeader from '@/components/PageHeader';
import StatCard from '@/components/StatCard';
import EmptyState from '@/components/EmptyState';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import LastUpdated from '@/components/LastUpdated';
import HelpPopover from '@/components/HelpPopover';
import { useSettingsStore } from '@/stores/settings';
import {
  useFuturesDashboard,
  useFuturesLeaderboard,
  useFuturesStats,
} from '@/api/futures';
import type { FuturesDailyBarOut, FuturesDashboardSection } from '@/api/futures';

const PRODUCTS = ['金属', '能源化工', '农产品', '金融期货'] as const;
type Product = (typeof PRODUCTS)[number];

const PRODUCT_ICON: Record<Product, string> = {
  金属: '🟡',
  能源化工: '🛢️',
  农产品: '🌾',
  金融期货: '📊',
};

function fmtNum(v: string | number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return '-';
  const n = typeof v === 'string' ? Number(v) : v;
  if (Number.isNaN(n)) return '-';
  return n.toFixed(digits);
}

function fmtVol(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-';
  const n = Number(v);
  if (Number.isNaN(n)) return '-';
  if (n >= 1e8) return `${(n / 1e8).toFixed(2)} 亿`;
  if (n >= 1e4) return `${(n / 1e4).toFixed(2)} 万`;
  return n.toFixed(0);
}

function changeCell(pct: number | null | undefined) {
  if (pct === null || pct === undefined) return <span className="ad-text-tertiary">-</span>;
  const positive = pct >= 0;
  const Icon = positive ? CaretUpOutlined : CaretDownOutlined;
  const cls = positive ? 'ad-change-cell ad-change-cell--rise' : 'ad-change-cell ad-change-cell--fall';
  return (
    <span className={`tabular-nums font-mono ${cls}`}>
      <Icon className="ad-icon-xs" />
      {Math.abs(pct).toFixed(2)}%
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
        <InstrumentCodeTag code={v} name={record.name} />
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
    <div className="ad-table-scroll ad-table-sticky">
      <Table
        dataSource={bars.slice(0, maxRows)}
        columns={columns}
        rowKey="code"
        size="small"
        pagination={false}
        showHeader={showHeader}
      />
    </div>
  );
}

interface ProductSummaryProps {
  section: FuturesDashboardSection | undefined;
}

function ProductSummary({ section }: ProductSummaryProps) {
  const mode = useSettingsStore((s) => s.mode);
  if (!section) {
    return (
      <Row gutter={16}>
        <Col xs={24} sm={8}>
          <Statistic title={<HelpPopover termKey="dominant_contract" mode={mode}>主力合约数</HelpPopover>} value={0} />
        </Col>
        <Col xs={24} sm={8}>
          <Statistic title="涨幅最大" value="-" />
        </Col>
        <Col xs={24} sm={8}>
          <Statistic title="跌幅最大" value="-" />
        </Col>
      </Row>
    );
  }

  const { best_performer, worst_performer, count } = section;

  return (
    <Row gutter={16}>
      <Col xs={24} sm={8}>
        <Statistic title={<HelpPopover termKey="dominant_contract" mode={mode}>主力合约数</HelpPopover>} value={count} />
      </Col>
      <Col xs={24} sm={8}>
        <Statistic
          title={
            <Tooltip title="当日涨幅最大合约">
              <span className="ad-text-rise">涨幅最大</span>
            </Tooltip>
          }
          value={best_performer?.code ?? '-'}
          valueRender={() =>
            best_performer ? (
              <InstrumentCodeTag code={best_performer.code} name={best_performer.name} />
            ) : (
              '-'
            )
          }
          suffix={
            best_performer ? (
              <span className={`ad-statistic-suffix ${(best_performer.settle_change_pct ?? 0) >= 0 ? 'detail-kpi-rise' : 'detail-kpi-fall'}`}>
                {best_performer.settle_change_pct !== null && best_performer.settle_change_pct !== undefined
                  ? `${best_performer.settle_change_pct >= 0 ? '+' : ''}${best_performer.settle_change_pct.toFixed(2)}%`
                  : '-'}
              </span>
            ) : null
          }
        />
      </Col>
      <Col xs={24} sm={8}>
        <Statistic
          title={
            <Tooltip title="当日跌幅最大合约">
              <span className="ad-text-fall">跌幅最大</span>
            </Tooltip>
          }
          value={worst_performer?.code ?? '-'}
          valueRender={() =>
            worst_performer ? (
              <InstrumentCodeTag code={worst_performer.code} name={worst_performer.name} />
            ) : (
              '-'
            )
          }
          suffix={
            worst_performer ? (
              <span className={`ad-statistic-suffix ${(worst_performer.settle_change_pct ?? 0) >= 0 ? 'detail-kpi-rise' : 'detail-kpi-fall'}`}>
                {worst_performer.settle_change_pct !== null && worst_performer.settle_change_pct !== undefined
                  ? `${worst_performer.settle_change_pct >= 0 ? '+' : ''}${worst_performer.settle_change_pct.toFixed(2)}%`
                  : '-'}
              </span>
            ) : null
          }
        />
      </Col>
    </Row>
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
      <Panel title="板块概况" className="ad-mb-5">
        <ProductSummary section={section} />
      </Panel>

      <Row gutter={16} className="ad-mb-5">
        <Col xs={24} md={12}>
          <Card
            size="small"
            className="ad-table-card"
            title={
              <Space>
                <CaretUpOutlined className="ad-text-rise" />
                <span>涨幅榜 TOP 5</span>
              </Space>
            }
          >
            {gainers.length === 0 ? <EmptyState title="暂无数据" /> : <BarTable bars={gainers} />}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card
            size="small"
            className="ad-table-card"
            title={
              <Space>
                <CaretDownOutlined className="ad-text-fall" />
                <span>跌幅榜 TOP 5</span>
              </Space>
            }
          >
            {losers.length === 0 ? <EmptyState title="暂无数据" /> : <BarTable bars={losers} />}
          </Card>
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
  const { data: dashboard, isLoading: dashLoading, dataUpdatedAt } = useFuturesDashboard();
  const { data: gainers } = useFuturesLeaderboard('gainers');
  const { data: losers } = useFuturesLeaderboard('losers');
  const { data: stats } = useFuturesStats();

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
        <span>{PRODUCT_ICON[p]}</span>
        <span>{p}</span>
        <Tag color={sectionsByProduct[p] ? 'blue' : 'default'} className="ad-ml-2">
          {sectionsByProduct[p]?.count ?? 0}
        </Tag>
      </Space>
    ),
    children: dashLoading ? (
      <Skeleton active paragraph={{ rows: 6 }} />
    ) : (
      <ProductTab product={p} section={sectionsByProduct[p]} />
    ),
  }));

  const topGainer = (gainers?.items ?? [])[0];
  const topLoser = (losers?.items ?? [])[0];
  const latestDate = dashboard?.trade_date ?? stats?.latest_trade_date ?? null;

  return (
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
            value={latestDate ?? '-'}
          />
          <StatCard
            title="领头羊 / 领跌"
            value={
              topGainer && topLoser ? (
                <span className="ad-flex ad-gap-2 ad-items-center">
                  <InstrumentCodeTag code={topGainer.code} name={topGainer.name} />
                  <span>/</span>
                  <InstrumentCodeTag code={topLoser.code} name={topLoser.name} />
                </span>
              ) : topGainer ? (
                <InstrumentCodeTag code={topGainer.code} name={topGainer.name} />
              ) : topLoser ? (
                <InstrumentCodeTag code={topLoser.code} name={topLoser.name} />
              ) : (
                '-'
              )
            }
          />
        </ResponsiveGrid>
      </Panel>

      <Tabs items={tabItems} defaultActiveKey="金属" />
    </PageShell>
  );
}
