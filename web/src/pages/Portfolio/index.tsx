import './styles.css';
import { useMemo } from 'react';
import { Card, Skeleton, Table, Tag, Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  DollarOutlined,
  ThunderboltOutlined,
  AppstoreOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import EmptyState from '@/components/EmptyState';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import SectionHeading from '@/components/SectionHeading';
import ThemeTag from '@/components/ThemeTag';
import { usePaperAccounts } from '@/hooks/usePaperTrading';
import { useLiveConfigs } from '@/hooks/useLiveTrading';
import { usePoolList } from '@/hooks/usePoolDetail';
import type { PaperAccount, LiveConfig } from '@/types/trading';
import type { Pool } from '@/types/pool';

interface PaperAccountRow {
  key: string;
  id: number;
  name: string;
  status: string;
  equity: number;
  pnlPct: number | null;
}

interface LiveAccountRow {
  key: string;
  id: number;
  name: string;
  isTestnet: boolean;
  isEnabled: boolean;
}

interface DiffItem {
  code: string;
  targetWeight: number;
  actualWeight: number;
  drift: number;
  reason: string;
}

/** Format a number as USDT with appropriate precision. */
function fmtUSD(v: number | null | undefined): string {
  if (v == null) return '-';
  if (Math.abs(v) >= 1000)
    return `$${v.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  return `$${v.toFixed(2)}`;
}

function fmtPct(v: number | null | undefined): { text: string; color: string } {
  if (v == null) return { text: '-', color: 'var(--text-tertiary)' };
  const sign = v >= 0 ? '+' : '';
  return {
    text: `${sign}${v.toFixed(2)}%`,
    color:
      v > 0
        ? 'var(--color-rise)'
        : v < 0
          ? 'var(--color-fall)'
          : 'var(--text-tertiary)',
  };
}

/** Build a small set of "target vs actual" diff items from a pool + mock data.
 *
 * The diff surface is intentionally mocked when actual holding data is not
 * wired up yet: we surface the *target* weights from the chosen pool and
 * invent a plausible "actual" weight so the user can see drift. If no pool
 * exists yet, we return an empty array and the UI shows an EmptyState.
 */
function buildMockDiff(pool: Pool | undefined): DiffItem[] {
  if (!pool || !pool.members || pool.members.length === 0) return [];
  // Equal-weight as the baseline target (this matches the default
  // PoolEnhancementService.suggest_weights("equal") behaviour).
  const targetPerMember = 100 / pool.members.length;
  // Plausible "actual" weights derived deterministically from the etf_code
  // length so the diff is stable across renders but still varies by member.
  return pool.members.slice(0, 2).map((m) => {
    const code = m.etf_code;
    const drift = (code.length % 7) - 3; // -3 .. +3 percentage points
    const actual = Math.max(0, targetPerMember + drift);
    return {
      code,
      targetWeight: targetPerMember,
      actualWeight: actual,
      drift: actual - targetPerMember,
      reason:
        drift === 0
          ? '与目标权重一致'
          : drift > 0
            ? '当前超配（可能因近期上涨或近期买入未再平衡）'
            : '当前欠配（可能因近期下跌或卖出后未补回）',
    };
  });
}

export default function Portfolio() {
  const { data: accountsData, isLoading: accountsLoading } = usePaperAccounts();
  const { data: liveConfigs, isLoading: liveLoading } = useLiveConfigs();
  const { data: pools, isLoading: poolsLoading } = usePoolList();

  const accounts: PaperAccountRow[] = useMemo(() => {
    const items: PaperAccount[] = accountsData?.items || [];
    return items.map((a) => ({
      key: `paper-${a.id}`,
      id: a.id,
      name: a.name,
      status: a.status,
      equity: a.total_value ?? a.initial_balance,
      pnlPct: a.pnl_pct ?? null,
    }));
  }, [accountsData]);

  const liveRows: LiveAccountRow[] = useMemo(() => {
    const items: LiveConfig[] = liveConfigs || [];
    return items.map((c) => ({
      key: `live-${c.id}`,
      id: c.id,
      name: c.name,
      isTestnet: c.is_testnet,
      isEnabled: c.is_enabled,
    }));
  }, [liveConfigs]);

  // Pick the first pool as the "target pool" for the diff demo.
  const targetPool: Pool | undefined = pools && pools.length > 0 ? pools[0] : undefined;
  const diffItems = buildMockDiff(targetPool);

  const accountColumns: ColumnsType<PaperAccountRow> = [
    { title: '账户 ID', dataIndex: 'id', width: 90, responsive: ['md'] },
    { title: '账户名', dataIndex: 'name' },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      responsive: ['md'],
      render: (s: string) => <Tag color={s === 'active' ? 'green' : 'default'}>{s}</Tag>,
    },
    {
      title: '当前权益',
      dataIndex: 'equity',
      width: 140,
      align: 'right' as const,
      render: (v: number) => fmtUSD(v),
    },
    {
      title: '收益率',
      dataIndex: 'pnlPct',
      width: 110,
      align: 'right' as const,
      render: (_: unknown, row: PaperAccountRow) => {
        const r = fmtPct(row.pnlPct);
        return <span style={{ color: r.color }}>{r.text}</span>;
      },
    },
    {
      title: '持仓',
      width: 100,
      render: (_: unknown, row: PaperAccountRow) => (
        <a href={`/paper-trading?account=${row.id}`}>查看</a>
      ),
    },
  ];

  const liveColumns: ColumnsType<LiveAccountRow> = [
    { title: '配置 ID', dataIndex: 'id', width: 90, responsive: ['md'] },
    { title: '名称', dataIndex: 'name' },
    {
      title: '环境',
      dataIndex: 'isTestnet',
      width: 90,
      render: (t: boolean) => (
        <Tag color={t ? 'orange' : 'red'}>{t ? 'testnet' : 'mainnet'}</Tag>
      ),
    },
    {
      title: '启用',
      dataIndex: 'isEnabled',
      width: 90,
      render: (e: boolean) => (
        <Tag color={e ? 'green' : 'default'}>{e ? 'enabled' : 'disabled'}</Tag>
      ),
    },
  ];

  const diffColumns: ColumnsType<DiffItem> = [
    { title: '代码', dataIndex: 'code', width: 110 },
    {
      title: '目标权重',
      dataIndex: 'targetWeight',
      width: 110,
      align: 'right' as const,
      render: (v: number) => `${v.toFixed(2)}%`,
    },
    {
      title: '实际权重',
      dataIndex: 'actualWeight',
      width: 110,
      align: 'right' as const,
      render: (v: number) => `${v.toFixed(2)}%`,
    },
    {
      title: '漂移',
      dataIndex: 'drift',
      width: 110,
      align: 'right' as const,
      render: (v: number) => {
        const sign = v >= 0 ? '+' : '';
        return (
          <span style={{ color: v > 0 ? 'var(--color-rise)' : v < 0 ? 'var(--color-fall)' : 'var(--text-tertiary)' }}>
            {sign}
            {v.toFixed(2)}%
          </span>
        );
      },
    },
    {
      title: '原因',
      dataIndex: 'reason',
      width: 220,
      ellipsis: true,
      render: (v: string) => (
        <Tooltip title={v} placement="topLeft">
          <span>{v}</span>
        </Tooltip>
      ),
    },
  ];

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="投资组合"
        title="投资组合中心"
        description="跨模拟与真实账户聚合查看你的实际持仓与目标组合的偏离度。"
        tutorial="组合中心把模拟账户、真实账户与目标池三类资产放在同一视图，方便做再平衡决策。"
      />

      {/* 区块 1：模拟账户列表 */}
      <Panel variant="default" padding="md">
        <SectionHeading
          title={
            <span>
              <DollarOutlined className="ad-mr-2" />
              模拟账户
            </span>
          }
          action={
            <a href="/paper-trading" className="ad-text-small">
              管理模拟账户 →
            </a>
          }
        />
        {accountsLoading ? (
          <Skeleton active />
        ) : accounts.length === 0 ? (
          <EmptyState
            title="尚未创建模拟账户"
            description="前往模拟交易页面创建一个模拟账户即可在此查看权益与持仓。"
            action={
              <a href="/paper-trading">
                <Tag color="gold" className="ad-cursor-pointer">
                  新建模拟账户
                </Tag>
              </a>
            }
          />
        ) : (
          <div className="ad-table-scroll">
            <Table<PaperAccountRow>
              rowKey="key"
              size="middle"
              columns={accountColumns}
              dataSource={accounts}
              pagination={false}
              scroll={{ x: 'max-content' }}
            />
          </div>
        )}
      </Panel>

      <div className="ad-mb-4" />

      {/* 区块 2：真实账户列表 */}
      <Panel variant="default" padding="md">
        <SectionHeading
          title={
            <span>
              <ThunderboltOutlined className="ad-mr-2" />
              真实账户
            </span>
          }
          action={
            <a href="/live-trading" className="ad-text-small">
              管理真实配置 →
            </a>
          }
        />
        {liveLoading ? (
          <Skeleton active />
        ) : liveRows.length === 0 ? (
          <EmptyState
            title="尚未配置真实交易账户"
            description="前往真实交易页面创建 Binance 配置即可在此查看实际持仓与盈亏。"
            action={
              <a href="/live-trading">
                <Tag color="magenta" className="ad-cursor-pointer">
                  新建真实配置
                </Tag>
              </a>
            }
          />
        ) : (
          <div className="ad-table-scroll">
            <Table<LiveAccountRow>
              rowKey="key"
              size="middle"
              columns={liveColumns}
              dataSource={liveRows}
              pagination={false}
              scroll={{ x: 'max-content' }}
            />
          </div>
        )}
      </Panel>

      <div className="ad-mb-4" />

      {/* 区块 3：目标 Pool vs 实际持仓 diff */}
      <Panel variant="default" padding="md">
        <SectionHeading
          title={
            <span>
              <AppstoreOutlined className="ad-mr-2" />
              目标 Pool vs 实际持仓
            </span>
          }
          action={
            targetPool ? (
              <a href={`/pools/${targetPool.id}`} className="ad-text-small">
                管理目标池 ({targetPool.name}) →
              </a>
            ) : (
              <a href="/pools" className="ad-text-small">
                新建目标池 →
              </a>
            )
          }
        />
        {poolsLoading ? (
          <Skeleton active />
        ) : !targetPool ? (
          <EmptyState
            title="尚未建立目标组合"
            description="在「标的池管理」中创建一个目标池（例如：核心 ETF、卫星 ETF），组合中心会按目标权重与实际持仓做偏离度对比。"
            action={
              <a href="/pools">
                <Tag color="default" className="ad-cursor-pointer">
                  创建目标池
                </Tag>
              </a>
            }
          />
        ) : diffItems.length === 0 ? (
          <EmptyState
            title="目标池暂无成员"
            description={`目标池「${targetPool.name}」还没有添加任何成员，无法计算偏离度。`}
          />
        ) : (
          <>
            <ResponsiveGrid cols={2} gap="sm" className="portfolio-diff-summary" stretch>
              {diffItems.map((d) => (
                <Card
                  key={d.code}
                  size="small"
                  title={
                    <span>
                      <WarningOutlined className="ad-mr-1" />
                      {d.code}
                    </span>
                  }
                  extra={
                    <ThemeTag variant={d.drift > 0 ? 'rise' : d.drift < 0 ? 'fall' : 'neutral'}>
                      漂移 {d.drift >= 0 ? '+' : ''}
                      {d.drift.toFixed(2)}%
                    </ThemeTag>
                  }
                >
                  <div className="ad-text-small ad-text-secondary">
                    目标 {d.targetWeight.toFixed(2)}% · 实际 {d.actualWeight.toFixed(2)}%
                  </div>
                  <div className="ad-text-small ad-mt-2">{d.reason}</div>
                </Card>
              ))}
            </ResponsiveGrid>
            <div className="ad-mb-3" />
            <div className="ad-table-scroll">
              <Table<DiffItem>
                rowKey="code"
                size="small"
                columns={diffColumns}
                dataSource={diffItems}
                pagination={false}
                scroll={{ x: 'max-content' }}
              />
            </div>
            <div className="ad-mt-2 ad-text-small ad-text-tertiary">
              注：实际权重当前为前端 mock（用于演示 diff 视图），待真实账户持仓聚合接口稳定后将切换为后端实时计算。
            </div>
          </>
        )}
      </Panel>
    </PageShell>
  );
}