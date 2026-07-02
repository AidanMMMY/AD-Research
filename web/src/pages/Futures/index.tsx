import { useMemo } from 'react';
import {
  Tabs, Table, Tag, Skeleton, Empty, Space, Statistic, Row, Col, Tooltip, Card,
} from 'antd';
import { CaretUpOutlined, CaretDownOutlined } from '@ant-design/icons';
import Panel from '@/components/Panel';
import PageHeader from '@/components/PageHeader';
import LastUpdated from '@/components/LastUpdated';
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

function changeColor(pct: number | null | undefined): string {
  if (pct === null || pct === undefined) return 'var(--text-tertiary)';
  if (pct > 0) return 'var(--color-up, #ef232a)';
  if (pct < 0) return 'var(--color-down, #14b143)';
  return 'var(--text-secondary)';
}

function changeCell(pct: number | null | undefined) {
  if (pct === null || pct === undefined) return <span style={{ color: 'var(--text-tertiary)' }}>-</span>;
  const positive = pct >= 0;
  const Icon = positive ? CaretUpOutlined : CaretDownOutlined;
  return (
    <span
      className="tabular-nums"
      style={{
        fontFamily: 'var(--font-mono)',
        color: changeColor(pct),
        display: 'inline-flex',
        alignItems: 'center',
        gap: 2,
        fontWeight: 600,
      }}
    >
      <Icon style={{ fontSize: 10 }} />
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
  const columns = [
    {
      title: '代码',
      dataIndex: 'code',
      width: 80,
      render: (v: string) => (
        <span className="tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>{v}</span>
      ),
    },
    {
      title: '收盘',
      dataIndex: 'close',
      width: 90,
      render: (v: string | null) => (
        <span className="tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
          {fmtNum(v)}
        </span>
      ),
    },
    {
      title: '结算',
      dataIndex: 'settle',
      width: 90,
      render: (v: string | null) => (
        <span className="tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
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
        <span className="tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)' }}>
          {fmtVol(v)}
        </span>
      ),
    },
  ];
  return (
    <Table
      dataSource={bars.slice(0, maxRows)}
      columns={columns}
      rowKey="code"
      size="small"
      pagination={false}
      showHeader={showHeader}
    />
  );
}

interface ProductSummaryProps {
  section: FuturesDashboardSection | undefined;
}

function ProductSummary({ section }: ProductSummaryProps) {
  if (!section) {
    return (
      <Row gutter={16}>
        <Col span={8}>
          <Statistic title="主力合约数" value={0} />
        </Col>
        <Col span={8}>
          <Statistic title="涨幅最大" value="-" />
        </Col>
        <Col span={8}>
          <Statistic title="跌幅最大" value="-" />
        </Col>
      </Row>
    );
  }

  const { best_performer, worst_performer, count } = section;

  return (
    <Row gutter={16}>
      <Col span={8}>
        <Statistic title="主力合约数" value={count} />
      </Col>
      <Col span={8}>
        <Statistic
          title={
            <Tooltip title="当日涨幅最大合约">
              <span style={{ color: 'var(--color-up, #ef232a)' }}>涨幅最大</span>
            </Tooltip>
          }
          value={best_performer?.code ?? '-'}
          suffix={
            best_performer ? (
              <span style={{ color: changeColor(best_performer.settle_change_pct), marginLeft: 6, fontSize: 14 }}>
                {best_performer.settle_change_pct !== null && best_performer.settle_change_pct !== undefined
                  ? `${best_performer.settle_change_pct >= 0 ? '+' : ''}${best_performer.settle_change_pct.toFixed(2)}%`
                  : '-'}
              </span>
            ) : null
          }
        />
      </Col>
      <Col span={8}>
        <Statistic
          title={
            <Tooltip title="当日跌幅最大合约">
              <span style={{ color: 'var(--color-down, #14b143)' }}>跌幅最大</span>
            </Tooltip>
          }
          value={worst_performer?.code ?? '-'}
          suffix={
            worst_performer ? (
              <span style={{ color: changeColor(worst_performer.settle_change_pct), marginLeft: 6, fontSize: 14 }}>
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
      <Panel variant="minimal" title="板块概况">
        <ProductSummary section={section} />
      </Panel>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card
            size="small"
            title={
              <Space>
                <CaretUpOutlined style={{ color: 'var(--color-up, #ef232a)' }} />
                <span>涨幅榜 TOP 5</span>
              </Space>
            }
            styles={{ header: { borderBottom: 'none' } }}
          >
            {gainers.length === 0 ? <Empty description="暂无数据" /> : <BarTable bars={gainers} />}
          </Card>
        </Col>
        <Col span={12}>
          <Card
            size="small"
            title={
              <Space>
                <CaretDownOutlined style={{ color: 'var(--color-down, #14b143)' }} />
                <span>跌幅榜 TOP 5</span>
              </Space>
            }
            styles={{ header: { borderBottom: 'none' } }}
          >
            {losers.length === 0 ? <Empty description="暂无数据" /> : <BarTable bars={losers} />}
          </Card>
        </Col>
      </Row>

      <Panel variant="minimal" title="全板块合约" style={{ marginTop: 16 }}>
        {bars.length === 0 ? (
          <Empty description={`暂无${product}合约数据`} />
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
        <Tag color={sectionsByProduct[p] ? 'blue' : 'default'} style={{ marginLeft: 4 }}>
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

  const totalUp = (gainers?.items ?? []).slice(0, 1)[0]?.code;
  const totalDown = (losers?.items ?? []).slice(0, 1)[0]?.code;
  const latestDate = dashboard?.trade_date ?? stats?.latest_trade_date ?? null;

  return (
    <div>
      <PageHeader
        eyebrow="期货"
        title="商品期货"
        description="国内期货主力合约行情（金属 / 能源化工 / 农产品 / 金融期货），每日收盘后更新"
        extra={<LastUpdated at={dataUpdatedAt} loading={dashLoading} />}
      />

      <Panel variant="minimal" title="市场概况">
        <Row gutter={16}>
          <Col span={6}>
            <Statistic title="主力合约总数" value={stats?.total_contracts ?? dashboard?.total_contracts ?? 0} />
          </Col>
          <Col span={6}>
            <Statistic title="K线记录总数" value={stats?.total_bars ?? 0} />
          </Col>
          <Col span={6}>
            <Statistic
              title="数据日期"
              value={latestDate ?? '-'}
              valueStyle={{ fontFamily: 'var(--font-mono)' }}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="领头羊 / 领跌"
              value={totalUp && totalDown ? `${totalUp} / ${totalDown}` : (totalUp ?? totalDown ?? '-')}
              valueStyle={{
                fontFamily: 'var(--font-mono)',
                fontSize: 14,
              }}
            />
          </Col>
        </Row>
      </Panel>

      <div style={{ marginTop: 'var(--space-4)' }}>
        <Tabs items={tabItems} defaultActiveKey="金属" />
      </div>
    </div>
  );
}