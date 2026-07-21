import './styles.css';
import { useState, useEffect } from 'react';
import {
  Badge,
  Button,
  Form,
  Input,
  InputNumber,
  message,
  Modal,
  Popconfirm,
  Select,
  // eslint-disable-next-line no-restricted-imports -- Skeleton.Input/Button inline control placeholder not covered by LoadingBlock
  Skeleton,
  Space,
  Statistic,
  Switch,
  Table,
} from 'antd';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import LoadingBlock from '@/components/LoadingBlock';
import SectionHeading from '@/components/SectionHeading';
import EmptyState from '@/components/EmptyState';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import ThemeTag from '@/components/ThemeTag';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import { useIsMobile } from '@/hooks/useBreakpoint';
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
import type { LiveConfig, LiveOrder, LivePosition, RiskStatus } from '@/types/trading';

/** Format a number as USDT with appropriate precision. */
function fmtUSDT(v: number | null | undefined): string {
  if (v == null || v === undefined) return '-';
  if (Math.abs(v) >= 1000) return `$${v.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  if (Math.abs(v) >= 1) return `$${v.toFixed(2)}`;
  if (v === 0) return '$0.00';
  return `$${v.toFixed(6)}`;
}

function fmtNumberString(v: string | null | undefined, digits = 6): string {
  if (v == null || v === undefined) return '-';
  const n = Number(v);
  if (!Number.isFinite(n)) return '-';
  if (n === 0) return '0';
  if (Math.abs(n) >= 1000) return n.toLocaleString('en-US', { maximumFractionDigits: 2 });
  if (Math.abs(n) >= 1) return n.toFixed(2);
  return n.toFixed(digits);
}

function formatDateTime(v: string | null | undefined): string {
  if (!v) return '-';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return '-';
  return d.toLocaleString('zh-CN');
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
  const isMobile = useIsMobile();
  const { data: configs = [], isLoading: configsLoading } = useLiveConfigs();

  const [selectedConfigId, setSelectedConfigId] = useState<number | undefined>(
    configs.length > 0 ? configs[0].id : undefined,
  );

  useEffect(() => {
    if (!selectedConfigId && configs.length > 0) {
      setSelectedConfigId(configs[0].id);
    }
  }, [configs, selectedConfigId]);

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
      render: (_: string, r: LivePosition) => (
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
      title: '均价',
      dataIndex: 'avg_cost',
      key: 'avg',
      responsive: ['md'] as ('md' | 'lg' | 'xl' | 'xxl')[],
      render: (v: number) => <span className="font-mono">{fmtUSDT(v)}</span>,
    },
    {
      title: '现价',
      dataIndex: 'current_price',
      key: 'price',
      responsive: ['md'] as ('md' | 'lg' | 'xl' | 'xxl')[],
      render: (v: number | null) => <span className="font-mono">{fmtUSDT(v)}</span>,
    },
    {
      title: '市值',
      dataIndex: 'market_value',
      key: 'mv',
      render: (v: number | null) => (
        <span className="font-mono ad-font-semibold">{fmtUSDT(v)}</span>
      ),
    },
    {
      title: '未实现盈亏',
      dataIndex: 'unrealized_pnl',
      key: 'upnl',
      render: (v: number | null) => {
        const p = fmtPnL(v);
        const cls = p.color.includes('--color-rise')
          ? 'paper-pnl--rise'
          : p.color.includes('--color-fall')
            ? 'paper-pnl--fall'
            : 'paper-pnl--neutral';
        return (
          <span className={`font-mono ad-font-semibold ${cls}`}>
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
      responsive: ['md'] as ('md' | 'lg' | 'xl' | 'xxl')[],
      render: (v: string | null) => formatDateTime(v),
    },
    {
      title: '方向',
      dataIndex: 'side',
      key: 'side',
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
      render: (_: string, r: LiveOrder) => (
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
      title: '类型',
      dataIndex: 'order_type',
      key: 'type',
      responsive: ['md'] as ('md' | 'lg' | 'xl' | 'xxl')[],
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
              cancelOrder.mutate(
                { configId: selectedConfigId!, orderId: r.id },
                {
                  onSuccess: () => message.success('撤单成功'),
                  onError: (err: any) =>
                    message.error(err?.response?.data?.detail || '撤单失败'),
                },
              )
            }
          >
            <Button size="middle" danger>
              撤单
            </Button>
          </Popconfirm>
        ) : null,
    },
  ];

  // --- Render ---
  return (
    <PageShell maxWidth="wide" className="trading-panel-page">
      <PageHeader
        eyebrow="交易"
        title="真实交易"
        description="连接交易所 API，执行实盘交易与风险管理"
        tutorial={
          <span>
            先看顶部<b>账户与风险</b>面板确认余额和熔断状态，再去下方"下单"区域执行委托。
            实盘页面里每一个市价单都意味着立即成交，因此请先观察行情再下单。
          </span>
        }
        tutorialForce
        extra={
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
        }
      />

      <Panel variant="default" className="phase5c-account-selector">
        <div className="phase5c-flex-wrap">
          {configsLoading ? (
            <Skeleton.Input active size="small" />
          ) : configs.length === 0 ? (
            <EmptyState
              className="empty-state--in-card"
              title="还没有交易配置"
              description="请先创建至少一个交易配置，再开始下单"
              action={
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
                  创建配置
                </Button>
              }
            />
          ) : (
            <Select
              value={selectedConfigId}
              onChange={setSelectedConfigId}
              className="phase5c-select-min"
              options={configs.map((c) => ({
                value: c.id,
                label: (
                  <Space>
                    <span>{c.name}</span>
                    {c.is_testnet ? (
                      <ThemeTag variant="warning" className="phase5c-tag-xs">
                        TESTNET
                      </ThemeTag>
                    ) : (
                      <ThemeTag variant="error" className="phase5c-tag-xs">
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
      </Panel>

      {selectedConfig && (
        <>
          <SectionHeading title="风控与限额" />
          <ResponsiveGrid cols={4} gap="md" className="phase5c-section">
            <Panel padding="sm" className="phase5c-trading-card">
              <Statistic
                title="今日订单"
                value={risk?.orders_today ?? 0}
                suffix={`/ ${selectedConfig.max_daily_orders}`}
                loading={riskLoading}
              />
            </Panel>
            <Panel padding="sm" className="phase5c-trading-card">
              <Statistic
                title="单笔上限"
                value={selectedConfig.max_order_value}
                prefix="$"
                loading={configsLoading}
              />
            </Panel>
            <Panel padding="sm" className="phase5c-trading-card">
              <div className={risk && Number(risk.realized_pnl_today) > 0 ? 'phase5c-pnl-stat--rise' : risk && Number(risk.realized_pnl_today) < 0 ? 'phase5c-pnl-stat--fall' : 'phase5c-pnl-stat--neutral'}>
                <Statistic
                  title="今日已实现"
                  value={Number.isFinite(Number(risk?.realized_pnl_today)) ? Number(risk?.realized_pnl_today) : 0}
                  precision={2}
                  prefix="$"
                  loading={riskLoading}
                />
              </div>
            </Panel>
            <Panel padding="sm" className="phase5c-trading-card">
              <div className="phase5c-flex-center">
                <div>
                  <div className="phase5c-meta-label">
                    熔断状态
                  </div>
                  <RiskBadge risk={risk} />
                </div>
                {risk?.circuit_breaker_active && (
                  <Popconfirm
                    title="确认重置熔断？"
                    description="重置后将恢复下单能力，请确认风险已解除。"
                    onConfirm={handleResetBreaker}
                    okText="确认重置"
                    cancelText="取消"
                  >
                    <Button
                      size="small"
                      icon={<ReloadOutlined />}
                      loading={resetBreaker.isPending}
                    >
                      重置
                    </Button>
                  </Popconfirm>
                )}
              </div>
            </Panel>
          </ResponsiveGrid>

          <SectionHeading title="账户余额" />
          <Panel variant="default" className="phase5c-section">
            {accountLoading ? (
              <LoadingBlock size="md" />
            ) : account && account.balances.length > 0 ? (
              <div className="phase5c-balance-grid">
                {account.balances.map((b) => (
                  <Panel key={b.asset} padding="sm" className="phase5c-balance-card">
                    <div className="phase5c-balance-card__asset">
                      {b.asset}
                    </div>
                    <div className="phase5c-balance-card__row">
                      可用: {fmtNumberString(b.free)}
                    </div>
                    <div className="phase5c-balance-card__row">
                      冻结: {fmtNumberString(b.locked)}
                    </div>
                  </Panel>
                ))}
              </div>
            ) : (
              <div className="phase5c-empty">
                <EmptyState title="无余额数据" description="当前账户没有余额数据" />
              </div>
            )}
          </Panel>

          <SectionHeading title="操作" />
          <div className="phase5c-action-bar phase5c-section">
            <Button
              icon={<PlusOutlined />}
              type="primary"
              onClick={() => setOrderModalOpen(true)}
              disabled={!selectedConfig.is_enabled || risk?.circuit_breaker_active}
            >
              下单
            </Button>
          </div>

          <SectionHeading title="当前持仓" />
          <Panel variant="default" className="phase5c-section">
            <div className="phase5c-table-wrap">
              {positionsLoading ? (
                <LoadingBlock size="md" className="phase5c-skeleton-pad" />
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
                <LoadingBlock size="md" className="phase5c-skeleton-pad" />
              ) : orders && orders.length > 0 ? (
                <Table
                  columns={orderColumns}
                  dataSource={orders}
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
        title="创建交易配置"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        onOk={() => createForm.submit()}
        confirmLoading={createConfig.isPending}
        width={isMobile ? '100%' : 520}
        destroyOnClose
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
            <InputNumber min={0} className="phase5c-form-input--full" />
          </Form.Item>
          <Form.Item name="max_daily_loss" label="每日最大亏损 (USDT)">
            <InputNumber min={0} className="phase5c-form-input--full" />
          </Form.Item>
          <Form.Item name="max_daily_orders" label="每日最多下单次数">
            <InputNumber min={1} max={1000} className="phase5c-form-input--full" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={
          <Space>
            <span>下单</span>
            {selectedConfig && (
              <>
                <span className="ad-text-small ad-text-secondary">
                  {selectedConfig.name}
                </span>
                {selectedConfig.is_testnet ? (
                  <ThemeTag variant="warning" className="phase5c-tag-xs">
                    TESTNET
                  </ThemeTag>
                ) : (
                  <ThemeTag variant="error" className="phase5c-tag-xs">
                    LIVE
                  </ThemeTag>
                )}
              </>
            )}
          </Space>
        }
        open={orderModalOpen}
        onCancel={() => setOrderModalOpen(false)}
        onOk={() => orderForm.submit()}
        confirmLoading={placeOrder.isPending}
        width={isMobile ? '100%' : 520}
        destroyOnClose
        footer={
          selectedConfig && !selectedConfig.is_testnet
            ? [
                <Button key="cancel" onClick={() => setOrderModalOpen(false)}>
                  取消
                </Button>,
                <Popconfirm
                  key="confirm"
                  title="确认提交实盘订单？"
                  description={`当前配置「${selectedConfig.name}」连接真实交易环境，订单将使用真实资金成交，请再次确认。`}
                  okText="确认下单"
                  cancelText="再想想"
                  onConfirm={() => orderForm.submit()}
                >
                  <Button type="primary" danger loading={placeOrder.isPending}>
                    下单（真实资金）
                  </Button>
                </Popconfirm>,
              ]
            : undefined
        }
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
            <InputNumber min={0.00000001} step={0.001} className="phase5c-form-input--full" />
          </Form.Item>
          <Form.Item
            noStyle
            shouldUpdate={(prev, cur) => prev.order_type !== cur.order_type}
          >
            {({ getFieldValue }) => {
              const isLimit = getFieldValue('order_type') !== 'MARKET';
              return (
                <Form.Item
                  name="price"
                  label={isLimit ? '限价' : '限价（市价单无需填写）'}
                  rules={
                    isLimit
                      ? [{ required: true, message: '限价单必须填写价格' }]
                      : []
                  }
                >
                  <InputNumber
                    min={0}
                    className="phase5c-form-input--full"
                    placeholder={isLimit ? '限价' : '市价'}
                    disabled={!isLimit}
                  />
                </Form.Item>
              );
            }}
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}
