import './styles.css';
import { useState, useEffect } from 'react';
import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  message,
  Modal,
  Popconfirm,
  Select,
  Skeleton,
  Statistic,
  Table,
} from 'antd';
import {
  PlusOutlined,
  SyncOutlined,
  ThunderboltOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import SectionHeading from '@/components/SectionHeading';
import EmptyState from '@/components/EmptyState';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import HelpPopover from '@/components/HelpPopover';
import { useSettingsStore } from '@/stores/settings';
import ContextHint from '@/components/ContextHint';
import {
  usePaperAccounts,
  usePaperAccount,
  useCreateAccount,
  useDeleteAccount,
  usePaperOrders,
  usePlaceOrder,
  usePaperPositions,
  usePaperPnL,
  useSyncMarketValues,
  useAutoTrade,
} from '@/hooks/usePaperTrading';
import type { PaperOrder, PaperPosition } from '@/types/trading';

/** Format a number as USDT with appropriate precision. */
function fmtUSDT(v: number | null | undefined): string {
  if (v == null) return '-';
  if (Math.abs(v) >= 1000) return `$${v.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  if (Math.abs(v) >= 1) return `$${v.toFixed(2)}`;
  if (v === 0) return '$0.00';
  return `$${v.toFixed(6)}`;
}

function fmtPnL(v: number | null | undefined): { text: string; color: string } {
  if (v == null) return { text: '-', color: 'var(--text-tertiary)' };
  const sign = v >= 0 ? '+' : '';
  return {
    text: `${sign}${fmtUSDT(v)}`,
    color: v > 0 ? 'var(--color-rise)' : v < 0 ? 'var(--color-fall)' : 'var(--text-tertiary)',
  };
}

function fmtPercent(v: number | null | undefined): { text: string; color: string } {
  if (v == null) return { text: '-', color: 'var(--text-tertiary)' };
  const sign = v >= 0 ? '+' : '';
  return {
    text: `${sign}${v.toFixed(2)}%`,
    color: v > 0 ? 'var(--color-rise)' : v < 0 ? 'var(--color-fall)' : 'var(--text-tertiary)',
  };
}

function formatDateTime(v: string | null | undefined): string {
  if (!v) return '-';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return '-';
  return d.toLocaleString('zh-CN');
}

export default function PaperTrading() {
  const mode = useSettingsStore((s) => s.mode);
  const { data: accountsData, isLoading: accountsLoading } = usePaperAccounts();
  const accounts = accountsData?.items || [];

  const [selectedAccountId, setSelectedAccountId] = useState<number | undefined>(
    accounts.length > 0 ? accounts[0].id : undefined,
  );

  useEffect(() => {
    if (!selectedAccountId && accounts.length > 0) {
      setSelectedAccountId(accounts[0].id);
    }
  }, [accounts, selectedAccountId]);

  const {
    data: account,
    isLoading: accountLoading,
  } = usePaperAccount(selectedAccountId);
  const { data: positions, isLoading: positionsLoading } =
    usePaperPositions(selectedAccountId);
  const { data: orders, isLoading: ordersLoading } =
    usePaperOrders(selectedAccountId, 50);
  const { data: pnl, isLoading: pnlLoading } = usePaperPnL(selectedAccountId);

  const createAccount = useCreateAccount();
  const deleteAccount = useDeleteAccount();
  const placeOrder = usePlaceOrder();
  const syncMarket = useSyncMarketValues();
  const autoTrade = useAutoTrade();

  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [orderModalOpen, setOrderModalOpen] = useState(false);
  const [createForm] = Form.useForm();
  const [orderForm] = Form.useForm();

  // --- Handlers ---
  const handleCreateAccount = async (values: { name: string; initial_balance: number }) => {
    try {
      const res = await createAccount.mutateAsync({
        name: values.name,
        initial_balance: values.initial_balance,
      });
      message.success(`账户 "${res.data.name}" 创建成功`);
      setSelectedAccountId(res.data.id);
      setCreateModalOpen(false);
      createForm.resetFields();
    } catch {
      message.error('创建账户失败');
    }
  };

  const handlePlaceOrder = async (values: {
    instrument_code: string;
    order_type: 'BUY' | 'SELL';
    quantity: number;
    price?: number;
  }) => {
    if (!selectedAccountId) return;
    try {
      await placeOrder.mutateAsync({
        accountId: selectedAccountId,
        data: values,
      });
      message.success(`${values.order_type === 'BUY' ? '买入' : '卖出'} 订单已成交`);
      setOrderModalOpen(false);
      orderForm.resetFields();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '下单失败');
    }
  };

  const handleSync = async () => {
    if (!selectedAccountId) return;
    try {
      const res = await syncMarket.mutateAsync(selectedAccountId);
      message.success(`已更新 ${res.data.updated} 个仓位的市值`);
    } catch {
      message.error('同步失败');
    }
  };

  const handleAutoTrade = async () => {
    if (!selectedAccountId) return;
    try {
      const res = await autoTrade.mutateAsync({ accountId: selectedAccountId });
      message.success(`自动交易完成，执行了 ${res.data.length} 笔订单`);
    } catch {
      message.error('自动交易失败');
    }
  };

  const handleDeleteAccount = async (id: number) => {
    try {
      await deleteAccount.mutateAsync(id);
      message.success('账户已归档');
      if (selectedAccountId === id) {
        setSelectedAccountId(undefined);
      }
    } catch {
      message.error('删除失败');
    }
  };

  // --- Position table columns ---
  const positionColumns = [
    {
      title: '币种',
      dataIndex: 'instrument_code',
      key: 'code',
      render: (_: unknown, r: PaperPosition) => (
        <span>
          <span className="phase5c-inline-code--bold">{r.instrument_code}</span>
          {r.instrument_name && (
            <span className="phase5c-detail-line">{r.instrument_name}</span>
          )}
        </span>
      ),
    },
    {
      title: '持仓量',
      dataIndex: 'quantity',
      key: 'qty',
      render: (v: number) => <span className="font-mono">{v}</span>,
    },
    {
      title: <HelpPopover termKey="avg_cost" mode={mode}>均价</HelpPopover>,
      dataIndex: 'avg_cost',
      key: 'avg',
      render: (v: number) => <span className="font-mono">{fmtUSDT(v)}</span>,
    },
    {
      title: '现价',
      dataIndex: 'current_price',
      key: 'price',
      render: (v: number | null) => <span className="font-mono">{fmtUSDT(v)}</span>,
    },
    {
      title: <HelpPopover termKey="market_value" mode={mode}>市值</HelpPopover>,
      dataIndex: 'market_value',
      key: 'mv',
      render: (v: number | null) => (
        <span className="font-mono ad-font-semibold">{fmtUSDT(v)}</span>
      ),
    },
    {
      title: <HelpPopover termKey="unrealized_pnl" mode={mode}>未实现盈亏</HelpPopover>,
      dataIndex: 'unrealized_pnl',
      key: 'upnl',
      render: (v: number | null, r: PaperPosition) => {
        const p = fmtPnL(v);
        const pct = fmtPercent(r.pnl_pct);
        const cls = p.color.includes('--color-rise')
          ? 'paper-pnl--rise'
          : p.color.includes('--color-fall')
            ? 'paper-pnl--fall'
            : 'paper-pnl--neutral';
        return (
          <span className={`font-mono ad-font-semibold ${cls}`}>
            {p.text} ({pct.text})
          </span>
        );
      },
    },
    {
      title: <HelpPopover termKey="realized_pnl" mode={mode}>已实现盈亏</HelpPopover>,
      dataIndex: 'realized_pnl',
      key: 'rpnl',
      render: (v: number | null) => {
        const p = fmtPnL(v);
        const cls = p.color.includes('--color-rise')
          ? 'paper-pnl--rise'
          : p.color.includes('--color-fall')
            ? 'paper-pnl--fall'
            : 'paper-pnl--neutral';
        return (
          <span className={`font-mono ${cls}`}>{p.text}</span>
        );
      },
    },
  ];

  // --- Order table columns ---
  const orderColumns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'time',
      render: (v: string | null) => formatDateTime(v),
    },
    {
      title: '方向',
      dataIndex: 'order_type',
      key: 'type',
      render: (v: string) => (
        <span className={v === 'BUY' ? 'phase5c-order-side--buy' : 'phase5c-order-side--sell'}>
          {v === 'BUY' ? '买入' : '卖出'}
        </span>
      ),
    },
    {
      title: '币种',
      dataIndex: 'instrument_code',
      key: 'code',
      render: (_: string, r: PaperOrder) => (
        <InstrumentCodeTag code={r.instrument_code} name={r.instrument_name} />
      ),
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'qty',
      render: (v: number) => <span className="font-mono">{v}</span>,
    },
    {
      title: '价格',
      dataIndex: 'price',
      key: 'price',
      render: (v: number | null) => <span className="font-mono">{fmtUSDT(v)}</span>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (v: string) => {
        const classMap: Record<string, string> = {
          filled: 'phase5c-status--filled',
          pending: 'phase5c-status--pending',
          cancelled: 'phase5c-status--cancelled',
          rejected: 'phase5c-status--rejected',
        };
        return <span className={classMap[v] || 'ad-text-secondary'}>{v}</span>;
      },
    },
  ];

  // --- Render ---
  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="交易"
        title="模拟交易"
        description="使用虚拟资金测试交易策略，零风险验证信号执行效果"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
            创建账户
          </Button>
        }
      />

      <ContextHint
        hintId="paper-trading-intro"
        title="先开一个模拟账户"
        placement="bottom"
        content={
          <>
            平台不会动用真实资金。先创建账户，下一笔小单练手；熟练后再到「策略管理」开启自动交易，让平台按信号自动下单。
          </>
        }
      >
        <div className="phase5c-account-selector" data-onboard="paper-account">
          {accountsLoading ? (
            <Skeleton active paragraph={{ rows: 1 }} />
          ) : accounts.length === 0 ? (
            <EmptyState
              title="还没有模拟账户"
              description="创建第一个模拟账户，开始零风险交易验证"
              action={
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
                  创建第一个账户
                </Button>
              }
            />
          ) : (
            <Select
              value={selectedAccountId}
              onChange={setSelectedAccountId}
              className="phase5c-select--lg"
              options={accounts.map((a) => ({
                value: a.id,
                label: (
                  <span>
                    {a.name}
                    <span className="font-mono ad-ml-2 ad-text-tertiary">
                      {fmtUSDT(a.total_value || a.cash)}
                    </span>
                  </span>
                ),
              }))}
            />
          )}
        </div>
      </ContextHint>

      {selectedAccountId && (
        <>
          <SectionHeading title="账户概览" />
          <ResponsiveGrid cols={4} gap="md" className="phase5c-section">
            <Card size="small" className="phase5c-trading-card">
              <Statistic
                title="总权益"
                value={pnl?.total_equity ?? account?.total_value ?? account?.cash}
                precision={2}
                prefix="$"
                loading={pnlLoading && accountLoading}
              />
            </Card>
            <Card size="small" className="phase5c-trading-card">
              <Statistic
                title="可用现金"
                value={account?.cash}
                precision={2}
                prefix="$"
                loading={accountLoading}
              />
            </Card>
            <Card size="small" className="phase5c-trading-card">
              <Statistic
                title="持仓市值"
                value={pnl?.market_value}
                precision={2}
                prefix="$"
                loading={pnlLoading}
              />
            </Card>
            <Card size="small" className="phase5c-trading-card">
              <div className={pnl && pnl.total_pnl > 0 ? 'phase5c-pnl-stat--rise' : pnl && pnl.total_pnl < 0 ? 'phase5c-pnl-stat--fall' : 'phase5c-pnl-stat--neutral'}>
                <Statistic
                  title="总盈亏"
                  value={pnl?.total_pnl ?? 0}
                  precision={2}
                  prefix={pnl && pnl.total_pnl >= 0 ? '+$' : '-$'}
                  loading={pnlLoading}
                />
              </div>
              {pnl?.pnl_pct != null && (
                <div className={pnl.pnl_pct > 0 ? 'phase5c-pnl-pct--rise' : pnl.pnl_pct < 0 ? 'phase5c-pnl-pct--fall' : 'phase5c-pnl-pct--neutral'}>
                  {pnl.pnl_pct >= 0 ? '+' : ''}
                  {pnl.pnl_pct.toFixed(2)}%
                </div>
              )}
            </Card>
            <Card size="small" className="phase5c-trading-card">
              <Statistic
                title="交易次数"
                value={pnl?.trade_count ?? 0}
                loading={pnlLoading}
              />
              {pnl?.win_rate != null && (
                <div className="ad-text-small ad-text-tertiary">
                  胜率: {(pnl.win_rate * 100).toFixed(0)}%
                </div>
              )}
            </Card>
          </ResponsiveGrid>

          <SectionHeading title="操作" />
          <div className="phase5c-action-bar phase5c-section">
            <Button
              icon={<PlusOutlined />}
              onClick={() => setOrderModalOpen(true)}
              type="primary"
            >
              手动下单
            </Button>
            <Button
              icon={<SyncOutlined />}
              onClick={handleSync}
              loading={syncMarket.isPending}
            >
              刷新市值
            </Button>
            <Button
              icon={<ThunderboltOutlined />}
              onClick={handleAutoTrade}
              loading={autoTrade.isPending}
            >
              信号自动交易
            </Button>
            <Popconfirm
              title="确认归档该账户？"
              description="归档后账户将不可见，相关持仓与订单记录仍保留。"
              onConfirm={() => handleDeleteAccount(selectedAccountId)}
              okText="确认归档"
              cancelText="取消"
            >
              <Button
                icon={<DeleteOutlined />}
                danger
                loading={deleteAccount.isPending}
              >
                归档账户
              </Button>
            </Popconfirm>
          </div>

          <SectionHeading title="当前持仓" />
          <Panel variant="default" className="phase5c-section">
            <div className="phase5c-table-wrap">
              {positionsLoading ? (
                <Skeleton active paragraph={{ rows: 5 }} className="phase5c-skeleton-pad" />
              ) : positions && positions.length > 0 ? (
                <Table
                  columns={positionColumns}
                  dataSource={positions}
                  rowKey="id"
                  pagination={false}
                  size="small"
                  scroll={{ x: 'max-content' }}
                />
              ) : (
                <div className="phase5c-empty">
                  <EmptyState title="暂无持仓" description="当前账户没有持仓记录" />
                </div>
              )}
            </div>
          </Panel>

          <SectionHeading title="最近订单" />
          <Panel variant="default">
            <div className="phase5c-table-wrap">
              {ordersLoading ? (
                <Skeleton active paragraph={{ rows: 5 }} className="phase5c-skeleton-pad" />
              ) : orders && orders.items.length > 0 ? (
                <Table
                  columns={orderColumns}
                  dataSource={orders.items}
                  rowKey="id"
                  pagination={{ pageSize: 20, size: 'small' }}
                  size="small"
                  scroll={{ x: 'max-content' }}
                />
              ) : (
                <div className="phase5c-empty">
                  <EmptyState title="暂无订单" description="当前账户没有订单记录" />
                </div>
              )}
            </div>
          </Panel>
        </>
      )}

      <Modal
        title="创建模拟账户"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        onOk={() => createForm.submit()}
        confirmLoading={createAccount.isPending}
      >
        <Form
          form={createForm}
          layout="vertical"
          onFinish={handleCreateAccount}
          initialValues={{ name: '', initial_balance: 10000 }}
        >
          <Form.Item
            name="name"
            label="账户名称"
            rules={[{ required: true, message: '请输入账户名称' }]}
          >
            <Input placeholder="例如：我的 BTC 策略" />
          </Form.Item>
          <Form.Item
            name="initial_balance"
            label="初始资金 (USDT)"
            rules={[{ required: true, message: '请输入初始资金' }]}
          >
            <InputNumber min={100} max={10000000} className="phase5c-form-input--full" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="手动下单"
        open={orderModalOpen}
        onCancel={() => setOrderModalOpen(false)}
        onOk={() => orderForm.submit()}
        confirmLoading={placeOrder.isPending}
      >
        <Form
          form={orderForm}
          layout="vertical"
          onFinish={handlePlaceOrder}
          initialValues={{ order_type: 'BUY', quantity: 0.01 }}
        >
          <Form.Item
            name="instrument_code"
            label="币种代码"
            rules={[{ required: true, message: '请输入代码，如 BTC.US' }]}
          >
            <Input placeholder="BTC.US" />
          </Form.Item>
          <Form.Item
            name="order_type"
            label="方向"
            rules={[{ required: true }]}
          >
            <Select
              options={[
                { value: 'BUY', label: '买入' },
                { value: 'SELL', label: '卖出' },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="quantity"
            label="数量"
            rules={[{ required: true, message: '请输入数量' }]}
          >
            <InputNumber min={0.00000001} step={0.001} className="phase5c-form-input--full" />
          </Form.Item>
          <Form.Item name="price" label="限价 (留空则市价成交)">
            <InputNumber min={0} className="phase5c-form-input--full" placeholder="市价" />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}
