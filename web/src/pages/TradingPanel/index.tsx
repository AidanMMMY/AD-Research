import { useState } from 'react';
import {
  Badge,
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
  Space,
  Statistic,
  Switch,
  Table,
} from 'antd';
import ThemeTag from '@/components/ThemeTag';
import {
  PlusOutlined,
  DeleteOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import {
  useLiveConfigs,
  useCreateConfig,
  useUpdateConfig,
  useDeleteConfig,
  useLiveAccount,
  useLivePositions,
  useLiveOrders,
  usePlaceLiveOrder,
  useCancelLiveOrder,
  useRiskStatus,
  useResetCircuitBreaker,
} from '@/hooks/useLiveTrading';
import type { LiveConfig, LiveOrder, RiskStatus } from '@/types/trading';

/** Format a number as USDT with appropriate precision. */
function fmtUSDT(v: number | null | undefined): string {
  if (v == null || v === undefined) return '-';
  if (Math.abs(v) >= 1000) return `$${v.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  if (Math.abs(v) >= 1) return `$${v.toFixed(2)}`;
  if (v === 0) return '$0.00';
  return `$${v.toFixed(6)}`;
}

function fmtPnL(v: number | null | undefined): { text: string; color: string } {
  if (v == null || v === undefined) return { text: '-', color: 'var(--text-tertiary)' };
  const sign = v >= 0 ? '+' : '';
  return {
    text: `${sign}${fmtUSDT(v)}`,
    color: v > 0 ? 'var(--color-rise)' : v < 0 ? 'var(--color-fall)' : 'var(--text-tertiary)',
  };
}

/** Risk status badge component. */
function RiskBadge({ risk }: { risk: RiskStatus | undefined }) {
  if (!risk) return <Skeleton.Button active size="small" />;

  if (risk.circuit_breaker_active) {
    return (
      <Badge status="error" text="熔断中" title={risk.circuit_breaker_reason || undefined} />
    );
  }
  return <Badge status="success" text="正常" />;
}

export default function TradingPanel() {
  const { data: configs = [], isLoading: configsLoading } = useLiveConfigs();

  const [selectedConfigId, setSelectedConfigId] = useState<number | undefined>(
    configs.length > 0 ? configs[0].id : undefined,
  );

  const { data: account, isLoading: accountLoading } = useLiveAccount(selectedConfigId);
  const { data: positions, isLoading: positionsLoading } = useLivePositions(selectedConfigId);
  const { data: orders, isLoading: ordersLoading } = useLiveOrders(selectedConfigId);
  const { data: risk, isLoading: riskLoading } = useRiskStatus(selectedConfigId);

  const createConfig = useCreateConfig();
  const updateConfig = useUpdateConfig();
  const deleteConfig = useDeleteConfig();
  const placeOrder = usePlaceLiveOrder();
  const cancelOrder = useCancelLiveOrder();
  const resetBreaker = useResetCircuitBreaker();

  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [orderModalOpen, setOrderModalOpen] = useState(false);
  const [createForm] = Form.useForm();
  const [orderForm] = Form.useForm();

  const selectedConfig = configs.find((c) => c.id === selectedConfigId);

  // --- Handlers ---
  const handleCreateConfig = async (values: Record<string, unknown>) => {
    try {
      await createConfig.mutateAsync({
        name: values.name as string,
        api_key: values.api_key as string,
        api_secret: values.api_secret as string,
        is_testnet: (values.is_testnet as boolean) ?? true,
        max_order_value: values.max_order_value as number,
        max_daily_loss: values.max_daily_loss as number,
        max_daily_orders: values.max_daily_orders as number,
      });
      message.success('交易配置创建成功');
      setCreateModalOpen(false);
      createForm.resetFields();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '创建失败');
    }
  };

  const handlePlaceOrder = async (values: Record<string, unknown>) => {
    if (!selectedConfigId) return;
    try {
      await placeOrder.mutateAsync({
        configId: selectedConfigId,
        data: {
          instrument_code: values.instrument_code as string,
          side: values.side as 'BUY' | 'SELL',
          order_type: (values.order_type as 'LIMIT' | 'MARKET') || 'LIMIT',
          quantity: values.quantity as number,
          price: values.price as number | undefined,
        },
      });
      message.success('订单已提交');
      setOrderModalOpen(false);
      orderForm.resetFields();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '下单失败');
    }
  };

  const handleToggleEnabled = async (config: LiveConfig) => {
    try {
      await updateConfig.mutateAsync({
        id: config.id,
        data: { is_enabled: !config.is_enabled },
      });
      message.success(config.is_enabled ? '已禁用' : '已启用');
    } catch {
      message.error('状态切换失败');
    }
  };

  const handleResetBreaker = async () => {
    if (!selectedConfigId) return;
    try {
      await resetBreaker.mutateAsync(selectedConfigId);
      message.success('熔断已重置');
    } catch {
      message.error('重置失败');
    }
  };

  // --- Position table columns ---
  const positionColumns = [
    {
      title: '币种',
      dataIndex: 'instrument_code',
      key: 'code',
      render: (v: string) => (
        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{v}</span>
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
      render: (v: number | null) => {
        const p = fmtPnL(v);
        return (
          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: p.color }}>
            {p.text}
          </span>
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
      render: (v: string | null) => (v ? new Date(v).toLocaleString('zh-CN') : '-'),
    },
    {
      title: '方向',
      dataIndex: 'side',
      key: 'side',
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
      title: '类型',
      dataIndex: 'order_type',
      key: 'type',
      render: (v: string) => <ThemeTag variant="default">{v}</ThemeTag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (v: string) => {
        const variantMap: Record<string, any> = {
          filled: 'success',
          partially_filled: 'warning',
          pending: 'accent',
          new: 'accent',
          cancelled: 'neutral',
          rejected: 'error',
          expired: 'neutral',
        };
        return <ThemeTag variant={variantMap[v] || 'neutral'}>{v}</ThemeTag>;
      },
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: unknown, r: LiveOrder) =>
        r.status === 'pending' || r.status === 'new' ? (
          <Popconfirm
            title="确认撤单？"
            onConfirm={() =>
              cancelOrder.mutate({ configId: selectedConfigId!, orderId: r.id })
            }
          >
            <Button size="small" danger>
              撤单
            </Button>
          </Popconfirm>
        ) : null,
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
          真实交易
        </h1>
        <Space>
          {selectedConfig && risk && (
            <RiskBadge risk={risk} />
          )}
          <Button
            icon={<PlusOutlined />}
            type="primary"
            onClick={() => setCreateModalOpen(true)}
          >
            创建配置
          </Button>
        </Space>
      </div>

      {/* Config selector & info */}
      <Card size="small" style={{ marginBottom: 'var(--space-6)' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center' }}>
          {configsLoading ? (
            <Skeleton.Input active size="small" />
          ) : configs.length === 0 ? (
            <span style={{ color: 'var(--text-tertiary)' }}>
              还没有交易配置 — 请先创建
            </span>
          ) : (
            <Select
              value={selectedConfigId}
              onChange={setSelectedConfigId}
              style={{ minWidth: 200 }}
              options={configs.map((c) => ({
                value: c.id,
                label: (
                  <Space>
                    <span>{c.name}</span>
                    {c.is_testnet ? (
                      <ThemeTag variant="warning" style={{ fontSize: 10 }}>
                        TESTNET
                      </ThemeTag>
                    ) : (
                      <ThemeTag variant="error" style={{ fontSize: 10 }}>
                        LIVE
                      </ThemeTag>
                    )}
                  </Space>
                ),
              }))}
            />
          )}

          {selectedConfig && (
            <>
              <Switch
                checked={selectedConfig.is_enabled}
                onChange={() => handleToggleEnabled(selectedConfig)}
                checkedChildren="启用"
                unCheckedChildren="禁用"
                loading={updateConfig.isPending}
              />
              <Popconfirm
                title="确认删除此配置？"
                onConfirm={() => {
                  deleteConfig.mutate(selectedConfig.id);
                  setSelectedConfigId(undefined);
                }}
              >
                <Button icon={<DeleteOutlined />} danger size="small" loading={deleteConfig.isPending} />
              </Popconfirm>
            </>
          )}
        </div>
      </Card>

      {selectedConfig && (
        <>
          {/* Risk status + limits */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
              gap: 'var(--space-4)',
              marginBottom: 'var(--space-6)',
            }}
          >
            <Card size="small">
              <Statistic
                title="今日订单"
                value={risk?.orders_today ?? 0}
                suffix={`/ ${selectedConfig.max_daily_orders}`}
                loading={riskLoading}
                valueStyle={{ fontFamily: 'var(--font-mono)' }}
              />
            </Card>
            <Card size="small">
              <Statistic
                title="单笔上限"
                value={selectedConfig.max_order_value}
                prefix="$"
                loading={configsLoading}
                valueStyle={{ fontFamily: 'var(--font-mono)' }}
              />
            </Card>
            <Card size="small">
              <Statistic
                title="今日已实现"
                value={risk?.realized_pnl_today ? parseFloat(risk.realized_pnl_today) : 0}
                precision={2}
                prefix="$"
                loading={riskLoading}
                valueStyle={{
                  fontFamily: 'var(--font-mono)',
                  color:
                    risk && parseFloat(risk.realized_pnl_today) > 0
                      ? 'var(--color-rise)'
                      : risk && parseFloat(risk.realized_pnl_today) < 0
                        ? 'var(--color-fall)'
                        : undefined,
                }}
              />
            </Card>
            <Card size="small">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div>
                  <div style={{ color: 'var(--text-tertiary)', fontSize: 12, marginBottom: 4 }}>
                    熔断状态
                  </div>
                  <RiskBadge risk={risk} />
                </div>
                {risk?.circuit_breaker_active && (
                  <Button
                    size="small"
                    icon={<ReloadOutlined />}
                    onClick={handleResetBreaker}
                    loading={resetBreaker.isPending}
                  >
                    重置
                  </Button>
                )}
              </div>
            </Card>
          </div>

          {/* Account balances summary */}
          <Card title="账户余额" size="small" style={{ marginBottom: 'var(--space-6)' }}>
            {accountLoading ? (
              <Skeleton active paragraph={{ rows: 3 }} />
            ) : account && account.balances.length > 0 ? (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
                  gap: 'var(--space-3)',
                }}
              >
                {account.balances.map((b) => (
                  <Card key={b.asset} size="small" style={{ background: 'var(--surface-secondary)' }}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                      {b.asset}
                    </div>
                    <div style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>
                      可用: {parseFloat(b.free).toFixed(6)}
                    </div>
                    <div style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>
                      冻结: {parseFloat(b.locked).toFixed(6)}
                    </div>
                  </Card>
                ))}
              </div>
            ) : (
              <div style={{ color: 'var(--text-tertiary)', textAlign: 'center', padding: 20 }}>
                无余额数据
              </div>
            )}
          </Card>

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
              type="primary"
              onClick={() => setOrderModalOpen(true)}
              disabled={!selectedConfig.is_enabled || risk?.circuit_breaker_active}
            >
              下单
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
          <Card title="最近订单" styles={{ body: { padding: 0 } }}>
            {ordersLoading ? (
              <Skeleton active paragraph={{ rows: 5 }} style={{ padding: 16 }} />
            ) : orders && orders.length > 0 ? (
              <Table
                columns={orderColumns}
                dataSource={orders}
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

      {/* Create config modal */}
      <Modal
        title="创建交易配置"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        onOk={() => createForm.submit()}
        confirmLoading={createConfig.isPending}
        width={520}
      >
        <Form
          form={createForm}
          layout="vertical"
          onFinish={handleCreateConfig}
          initialValues={{
            is_testnet: true,
            max_order_value: 100,
            max_daily_loss: 500,
            max_daily_orders: 20,
          }}
        >
          <Form.Item name="name" label="配置名称" rules={[{ required: true }]}>
            <Input placeholder="例如：现货测试" />
          </Form.Item>
          <Form.Item name="api_key" label="API Key" rules={[{ required: true }]}>
            <Input.Password placeholder="Binance API Key" />
          </Form.Item>
          <Form.Item name="api_secret" label="API Secret" rules={[{ required: true }]}>
            <Input.Password placeholder="Binance API Secret" />
          </Form.Item>
          <Form.Item name="is_testnet" label="Testnet 模式" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="max_order_value" label="单笔最大金额 (USDT)">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="max_daily_loss" label="每日最大亏损 (USDT)">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="max_daily_orders" label="每日最多下单次数">
            <InputNumber min={1} max={1000} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Place order modal */}
      <Modal
        title="下单"
        open={orderModalOpen}
        onCancel={() => setOrderModalOpen(false)}
        onOk={() => orderForm.submit()}
        confirmLoading={placeOrder.isPending}
      >
        <Form
          form={orderForm}
          layout="vertical"
          onFinish={handlePlaceOrder}
          initialValues={{ side: 'BUY', order_type: 'LIMIT', quantity: 0.001 }}
        >
          <Form.Item
            name="instrument_code"
            label="币种代码"
            rules={[{ required: true, message: '请输入代码，如 BTC.US' }]}
          >
            <Input placeholder="BTC.US" />
          </Form.Item>
          <Form.Item name="side" label="方向" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'BUY', label: '买入' },
                { value: 'SELL', label: '卖出' },
              ]}
            />
          </Form.Item>
          <Form.Item name="order_type" label="订单类型">
            <Select
              options={[
                { value: 'LIMIT', label: '限价单' },
                { value: 'MARKET', label: '市价单' },
              ]}
            />
          </Form.Item>
          <Form.Item name="quantity" label="数量" rules={[{ required: true }]}>
            <InputNumber min={0.00000001} step={0.001} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="price" label="限价 (市价单留空)">
            <InputNumber min={0} style={{ width: '100%' }} placeholder="市价" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
