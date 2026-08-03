import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Button, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  DollarOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import EmptyState from '@/components/EmptyState';
import ErrorState from '@/components/ErrorState';
import LoadingBlock from '@/components/LoadingBlock';
import SectionHeading from '@/components/SectionHeading';
import ThemeTag from '@/components/ThemeTag';
import ReturnTag from '@/components/ReturnTag';
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

/** 模拟账户状态枚举 → 中文 + ThemeTag variant（审计 P1：不再裸英文） */
const PAPER_STATUS_MAP: Record<string, { label: string; variant: 'success' | 'neutral' }> = {
  active: { label: '运行中', variant: 'success' },
  archived: { label: '已归档', variant: 'neutral' },
};

export default function Portfolio() {
  // 解构 isError / refetch：接口失败时显示错误态（带重试），不能落入
  // 「尚未创建账户」假空态（审计 P1，2026-08-03）。
  const {
    data: accountsData,
    isLoading: accountsLoading,
    isError: accountsError,
    refetch: refetchAccounts,
  } = usePaperAccounts();
  const {
    data: liveConfigs,
    isLoading: liveLoading,
    isError: liveError,
    refetch: refetchLive,
  } = useLiveConfigs();

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
      // 审计 P1：状态枚举中文化 + ThemeTag（不再裸英文 antd 预设色）
      render: (s: string) => {
        const meta = PAPER_STATUS_MAP[s] ?? { label: s, variant: 'neutral' as const };
        return <ThemeTag variant={meta.variant}>{meta.label}</ThemeTag>;
      },
    },
    {
      title: '当前权益',
      dataIndex: 'equity',
      width: 140,
      align: 'right' as const,
      sorter: (a, b) => a.equity - b.equity,
      render: (v: number) => fmtUSD(v),
    },
    {
      title: '收益率',
      dataIndex: 'pnlPct',
      width: 110,
      align: 'right' as const,
      sorter: (a, b) => (a.pnlPct ?? -Infinity) - (b.pnlPct ?? -Infinity),
      // 后端 pnl_pct 是百分比语义（5.2 = 5.2%），ReturnTag 走小数语义
      // （×100），传入前需 /100 换算（审计 P1：复用 ReturnTag 统一涨跌样式）。
      render: (_: unknown, row: PaperAccountRow) => (
        <ReturnTag value={row.pnlPct != null ? row.pnlPct / 100 : null} />
      ),
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
      width: 100,
      render: (t: boolean) => (
        <ThemeTag variant={t ? 'warning' : 'error'}>{t ? '测试网' : '主网'}</ThemeTag>
      ),
    },
    {
      title: '启用',
      dataIndex: 'isEnabled',
      width: 90,
      render: (e: boolean) => (
        <ThemeTag variant={e ? 'success' : 'neutral'}>{e ? '已启用' : '已停用'}</ThemeTag>
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
        ) : accountsError ? (
          <ErrorState
            className="empty-state--in-card"
            description="模拟账户加载失败，请稍后重试"
            onRetry={() => refetchAccounts()}
          />
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
        ) : liveError ? (
          <ErrorState
            className="empty-state--in-card"
            description="真实账户配置加载失败，请稍后重试"
            onRetry={() => refetchLive()}
          />
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