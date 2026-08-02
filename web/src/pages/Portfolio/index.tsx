import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Button, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  DollarOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import EmptyState from '@/components/EmptyState';
import LoadingBlock from '@/components/LoadingBlock';
import SectionHeading from '@/components/SectionHeading';
import { usePaperAccounts } from '@/hooks/usePaperTrading';
import { useLiveConfigs } from '@/hooks/useLiveTrading';
import type { PaperAccount, LiveConfig } from '@/types/trading';

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

export default function Portfolio() {
  const { data: accountsData, isLoading: accountsLoading } = usePaperAccounts();
  const { data: liveConfigs, isLoading: liveLoading } = useLiveConfigs();

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
        <Link to={`/paper-trading?account=${row.id}`}>查看</Link>
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

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="投资组合"
        title="投资组合中心"
        description="跨模拟与真实账户聚合查看你的账户权益与持仓概况。"
        tutorial="组合中心把模拟账户与真实账户放在同一视图，方便统一跟踪权益与盈亏。"
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
            <Link to="/paper-trading" className="ad-text-small">
              管理模拟账户 →
            </Link>
          }
        />
        {accountsLoading ? (
          <LoadingBlock size="md" />
        ) : accounts.length === 0 ? (
          <EmptyState
            className="empty-state--in-card"
            title="尚未创建模拟账户"
            description="前往模拟交易页面创建一个模拟账户即可在此查看权益与持仓。"
            action={
              <Link to="/paper-trading">
                <Button type="primary" size="small">
                  新建模拟账户
                </Button>
              </Link>
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
            <Link to="/live-trading" className="ad-text-small">
              管理真实配置 →
            </Link>
          }
        />
        {liveLoading ? (
          <LoadingBlock size="md" />
        ) : liveRows.length === 0 ? (
          <EmptyState
            className="empty-state--in-card"
            title="尚未配置真实交易账户"
            description="前往真实交易页面创建 Binance 配置即可在此查看实际持仓与盈亏。"
            action={
              <Link to="/live-trading">
                <Button type="primary" size="small">
                  新建真实配置
                </Button>
              </Link>
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

      {/*
        TODO(审计 P0-2)：「目标 Pool vs 实际持仓」偏离度区块已下线。
        原实现为前端 mock（buildMockDiff：目标权重取池子等权、实际权重/漂移/原因均为编造），
        决策类假数据仅有小 Badge 提示，风险过高，故在真实账户持仓聚合接口就绪前直接不渲染。
        恢复时请改为后端实时 diff 数据（并同步恢复 usePoolList / DiffItem / diffColumns）。
      */}
    </PageShell>
  );
}