import { useState } from 'react';
import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  message,
  Modal,
  Select,
  Skeleton,
  Space,
  Statistic,
  Table,
} from 'antd';
import {
  PlusOutlined,
  SyncOutlined,
  ThunderboltOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
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
import type { PaperPosition } from '@/types/trading';

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

export default function PaperTrading() {
  const { data: accountsData, isLoading: accountsLoading } = usePaperAccounts();
  const accounts = accountsData?.items || [];

  const [selectedAccountId, setSelectedAccountId] = useState<number | undefined>(
    accounts.length > 0 ? accounts[0].id : undefined,
  );

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
          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{r.instrument_code}</span>
          {r.instrument_name && (
            <span style={{ marginLeft: 8, color: 'var(--text-tertiary)' }}>{r.instrument_name}</span>
          )}
        </span>
      ),
    },
    {
      title: '持仓量',
      dataIndex: 'quantity',
      key: 'qty',
      render: (v: number) => (
        <span style={{ fontFamily: 'var(--font-mono)' }}>{v}</span>
      ),
    },
    {
      title: '均价',
      dataIndex: 'avg_cost',
      key: 'avg',
      render: (v: number) => (
        <span style={{ fontFamily: 'var(--font-mono)' }}>{fmtUSDT(v)}</span>
      ),
    },
    {
      title: '现价',
      dataIndex: 'current_price',
      key: 'price',
      render: (v: number | null) => (
        <span style={{ fontFamily: 'var(--font-mono)' }}>{fmtUSDT(v)}</span>
      ),
    },
    {
      title: '市值',
      dataIndex: 'market_value',
      key: 'mv',
      render: (v: number | null) => (
        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{fmtUSDT(v)}</span>
      ),
    },
    {
      title: '未实现盈亏',
      dataIndex: 'unrealized_pnl',
      key: 'upnl',
      render: (v: number | null, r: PaperPosition) => {
        const p = fmtPnL(v);
        const pct = fmtPercent(r.pnl_pct);
        return (
          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: p.color }}>
            {p.text} ({pct.text})
          </span>
        );
      },
    },
    {
      title: '已实现盈亏',
      dataIndex: 'realized_pnl',
      key: 'rpnl',
      render: (v: number | null) => {
        const p = fmtPnL(v);
        return (
          <span style={{ fontFamily: 'var(--font-mono)', color: p.color }}>{p.text}</span>
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
      render: (v: string | null) =>
        v ? new Date(v).toLocaleString('zh-CN') : '-',
    },
    {
      title: '方向',
      dataIndex: 'order_type',
      key: 'type',
      render: (v: string) => (
        <span
          style={{
            fontWeight: 600,
            color: v === 'BUY' ? 'var(--color-rise)' : 'var(--color-fall)',
          }}
        >
          {v === 'BUY' ? '买入' : '卖出'}
        </span>
      ),
    },
    {
      title: '币种',
      dataIndex: 'instrument_code',
      key: 'code',
      render: (v: string) => (
        <span style={{ fontFamily: 'var(--font-mono)' }}>{v}</span>
      ),
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'qty',
      render: (v: number) => (
        <span style={{ fontFamily: 'var(--font-mono)' }}>{v}</span>
      ),
    },
    {
      title: '价格',
      dataIndex: 'price',
      key: 'price',
      render: (v: number | null) => (
        <span style={{ fontFamily: 'var(--font-mono)' }}>{fmtUSDT(v)}</span>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (v: string) => {
        const colorMap: Record<string, string> = {
          filled: 'var(--color-rise)',
          pending: 'var(--accent)',
          cancelled: 'var(--text-tertiary)',
          rejected: 'var(--color-fall)',
        };
        return <span style={{ color: colorMap[v] || 'var(--text-secondary)' }}>{v}</span>;
      },
    },
  ];

  // --- Render ---
  return (
    <div>
      {/* Header */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 'var(--space-6)',
          gap: 'var(--space-4)',
        }}
      >
        <h1
          style={{
            fontSize: 'var(--text-h1-size)',
            fontWeight: 500,
            color: 'var(--text-primary)',
            margin: 0,
            letterSpacing: '-0.03em',
          }}
        >
          模拟交易
        </h1>
        <Space>
          <Button
            icon={<PlusOutlined />}
            type="primary"
            onClick={() => setCreateModalOpen(true)}
          >
            创建账户
          </Button>
        </Space>
      </div>

      {/* Account selector */}
      <div style={{ marginBottom: 'var(--space-6)' }}>
        {accountsLoading ? (
          <Skeleton active paragraph={{ rows: 1 }} />
        ) : accounts.length === 0 ? (
          <Card
            style={{
              textAlign: 'center',
              padding: 60,
              color: 'var(--text-tertiary)',
              border: '1px dashed var(--border-default)',
            }}
          >
            <div style={{ fontSize: 'var(--text-h2-size)', marginBottom: 16 }}>
              还没有模拟账户
            </div>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setCreateModalOpen(true)}
            >
              创建第一个账户
            </Button>
          </Card>
        ) : (
          <Select
            value={selectedAccountId}
            onChange={setSelectedAccountId}
            style={{ minWidth: 260 }}
            options={accounts.map((a) => ({
              value: a.id,
              label: (
                <span>
                  {a.name}
                  <span
                    style={{
                      marginLeft: 8,
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--text-tertiary)',
                    }}
                  >
                    {fmtUSDT(a.total_value || a.cash)}
                  </span>
                </span>
              ),
            }))}
          />
        )}
      </div>

      {selectedAccountId && (
        <>
          {/* Account overview + PnL cards */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
              gap: 'var(--space-4)',
              marginBottom: 'var(--space-6)',
            }}
          >
            {/* Equity */}
            <Card size="small">
              <Statistic
                title="总权益"
                value={pnl?.total_equity ?? account?.total_value ?? account?.cash}
                precision={2}
                prefix="$"
                loading={pnlLoading && accountLoading}
                valueStyle={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}
              />
            </Card>
            {/* Cash */}
            <Card size="small">
              <Statistic
                title="可用现金"
                value={account?.cash}
                precision={2}
                prefix="$"
                loading={accountLoading}
                valueStyle={{ fontFamily: 'var(--font-mono)' }}
              />
            </Card>
            {/* Market value */}
            <Card size="small">
              <Statistic
                title="持仓市值"
                value={pnl?.market_value}
                precision={2}
                prefix="$"
                loading={pnlLoading}
                valueStyle={{ fontFamily: 'var(--font-mono)' }}
              />
            </Card>
            {/* Total PnL */}
            <Card size="small">
              <Statistic
                title="总盈亏"
                value={pnl?.total_pnl ?? 0}
                precision={2}
                prefix={pnl && pnl.total_pnl >= 0 ? '+$' : '-$'}
                loading={pnlLoading}
                valueStyle={{
                  fontFamily: 'var(--font-mono)',
                  fontWeight: 600,
                  color:
                    pnl && pnl.total_pnl > 0
                      ? 'var(--color-rise)'
                      : pnl && pnl.total_pnl < 0
                        ? 'var(--color-fall)'
                        : undefined,
                }}
              />
              {pnl?.pnl_pct != null && (
                <div
                  style={{
                    fontSize: 'var(--text-small-size)',
                    color:
                      pnl.pnl_pct > 0
                        ? 'var(--color-rise)'
                        : pnl.pnl_pct < 0
                          ? 'var(--color-fall)'
                          : 'var(--text-tertiary)',
                  }}
                >
                  {pnl.pnl_pct >= 0 ? '+' : ''}
                  {pnl.pnl_pct.toFixed(2)}%
                </div>
              )}
            </Card>
            {/* Win rate */}
            <Card size="small">
              <Statistic
                title="交易次数"
                value={pnl?.trade_count ?? 0}
                loading={pnlLoading}
                valueStyle={{ fontFamily: 'var(--font-mono)' }}
              />
              {pnl?.win_rate != null && (
                <div style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>
                  胜率: {(pnl.win_rate * 100).toFixed(0)}%
                </div>
              )}
            </Card>
          </div>

          {/* Action buttons */}
          <div
            style={{
              display: 'flex',
              gap: 'var(--space-3)',
              marginBottom: 'var(--space-6)',
              flexWrap: 'wrap',
            }}
          >
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
            <Button
              icon={<DeleteOutlined />}
              danger
              onClick={() => handleDeleteAccount(selectedAccountId)}
              loading={deleteAccount.isPending}
            >
              归档账户
            </Button>
          </div>

          {/* Positions */}
          <Card
            title="当前持仓"
            style={{ marginBottom: 'var(--space-6)' }}
            styles={{ body: { padding: 0 } }}
          >
            {positionsLoading ? (
              <Skeleton active paragraph={{ rows: 5 }} style={{ padding: 16 }} />
            ) : positions && positions.length > 0 ? (
              <Table
                columns={positionColumns}
                dataSource={positions}
                rowKey="id"
                pagination={false}
                size="small"
              />
            ) : (
              <div
                style={{
                  padding: 40,
                  textAlign: 'center',
                  color: 'var(--text-tertiary)',
                }}
              >
                暂无持仓
              </div>
            )}
          </Card>

          {/* Orders */}
          <Card
            title="最近订单"
            styles={{ body: { padding: 0 } }}
          >
            {ordersLoading ? (
              <Skeleton active paragraph={{ rows: 5 }} style={{ padding: 16 }} />
            ) : orders && orders.items.length > 0 ? (
              <Table
                columns={orderColumns}
                dataSource={orders.items}
                rowKey="id"
                pagination={{ pageSize: 20, size: 'small' }}
                size="small"
              />
            ) : (
              <div
                style={{
                  padding: 40,
                  textAlign: 'center',
                  color: 'var(--text-tertiary)',
                }}
              >
                暂无订单
              </div>
            )}
          </Card>
        </>
      )}

      {/* Create account modal */}
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
            <InputNumber min={100} max={10000000} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Place order modal */}
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
            <InputNumber min={0.00000001} step={0.001} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="price" label="限价 (留空则市价成交)">
            <InputNumber min={0} style={{ width: '100%' }} placeholder="市价" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
