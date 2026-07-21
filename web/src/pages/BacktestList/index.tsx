import { useState, useMemo } from 'react';
import {
  Table, Button, Modal, Form, Select, DatePicker, InputNumber, Space, message,
} from 'antd';
import './styles.css';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import Panel from '@/components/Panel';
import SectionHeading from '@/components/SectionHeading';
import EmptyState from '@/components/EmptyState';
import { useBacktests } from '@/hooks/useBacktests';
import { useStrategies } from '@/hooks/useStrategies';
import { useInstrumentList } from '@/hooks/useInstrumentList';
import { usePrefersReducedMotion } from '@/hooks/usePrefersReducedMotion';
import { PlusOutlined, EyeOutlined } from '@ant-design/icons';
import { useNavigate, useSearchParams } from 'react-router-dom';
import dayjs from 'dayjs';
import type { BacktestListItem, BacktestMetrics } from '@/types/backtest';
import type { InstrumentInfo } from '@/types/instrument';

export default function BacktestList() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [form] = Form.useForm();
  // Apple Design #14: under reduced motion, suppress antd's default zoom
  // keyframe so the modal opens/closes with an instant cut instead.
  const reducedMotion = usePrefersReducedMotion();
  const modalMotionProps = reducedMotion
    ? { transitionName: '', maskTransitionName: '' }
    : {};

  // Deep-link params: /backtests?strategy_id=N (from StrategyList) filters
  // server-side; /backtests?strategy_type=xxx (from StrategyLibrary) has no
  // backend filter, so it is applied client-side via the strategies list.
  const strategyIdParam = Number(searchParams.get('strategy_id')) || undefined;
  const strategyTypeParam = searchParams.get('strategy_type') || undefined;

  const { backtests, isLoading, create, isCreating } = useBacktests(strategyIdParam);
  const { strategies } = useStrategies();
  const { data: etfList, isLoading: etfLoading } = useInstrumentList({ page_size: 10000 });

  const strategyNameById = useMemo(
    () => new Map<number, string>((strategies || []).map((s: any) => [s.id, s.name])),
    [strategies]
  );

  const displayedBacktests = useMemo(() => {
    if (!strategyTypeParam) return backtests;
    return backtests.filter(
      (bt) => (strategies || []).some(
        (s: any) => s.id === bt.strategy_id && s.strategy_type === strategyTypeParam
      )
    );
  }, [backtests, strategies, strategyTypeParam]);

  const etfOptions = (etfList?.items || []).map((item: InstrumentInfo) => ({
    label: `${item.code} ${item.name}`,
    value: item.code,
  }));

  interface BacktestCreateFormValues {
    strategy_id: number;
    etf_code: string;
    start_date: dayjs.Dayjs;
    end_date: dayjs.Dayjs;
    initial_capital?: number;
    commission_rate?: number;
    slippage_rate?: number;
    position_size?: number;
  }

  const handleCreate = async (values: BacktestCreateFormValues) => {
    try {
      await create({
        strategy_id: values.strategy_id,
        etf_code: values.etf_code,
        start_date: values.start_date.format('YYYY-MM-DD'),
        end_date: values.end_date.format('YYYY-MM-DD'),
        initial_capital: values.initial_capital ?? 100000,
        commission_rate: values.commission_rate ?? 0.001,
        slippage_rate: values.slippage_rate ?? 0.001,
        position_size: values.position_size ?? 1.0,
      });
      message.success('回测完成');
      setIsModalOpen(false);
      form.resetFields();
    } catch {
      message.error('回测失败');
    }
  };

  // Open the create modal, preselecting the strategy carried by deep-link params.
  const openCreateModal = () => {
    const presetStrategyId =
      strategyIdParam ??
      (strategies || []).find((s: any) => s.strategy_type === strategyTypeParam)?.id;
    if (presetStrategyId) form.setFieldsValue({ strategy_id: presetStrategyId });
    setIsModalOpen(true);
  };

  const rowSize = 'small';
  const tableWrapClass = 'ad-table-scroll ad-table-sticky';

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60, render: (v: number) => <span className="tabular-nums">{v}</span> },
    {
      title: '策略',
      dataIndex: 'strategy_id',
      width: 140,
      render: (v: number) => strategyNameById.get(v) || <span className="tabular-nums">#{v}</span>,
    },
    { title: '标的代码', dataIndex: 'etf_code', width: 100, render: (v: string | null) => v || '-' },
    { title: '起始日期', dataIndex: 'start_date' },
    { title: '结束日期', dataIndex: 'end_date' },
    {
      title: '总收益',
      dataIndex: 'metrics',
      // Missing metrics must not masquerade as 0%; colour real values by sign.
      render: (v: BacktestMetrics | undefined) => {
        const r = v?.total_return;
        if (r == null) return <span className="tabular-nums">-</span>;
        const cls = r > 0 ? 'paper-pnl--rise' : r < 0 ? 'paper-pnl--fall' : 'paper-pnl--neutral';
        return <span className={`tabular-nums ${cls}`}>{`${r.toFixed(2)}%`}</span>;
      },
      width: 100,
    },
    {
      title: '最大回撤',
      dataIndex: 'metrics',
      render: (v: BacktestMetrics | undefined) => {
        const d = v?.max_drawdown;
        return <span className="tabular-nums">{d == null ? '-' : `${d.toFixed(2)}%`}</span>;
      },
      width: 100,
    },
    {
      title: '夏普比率',
      dataIndex: 'metrics',
      render: (v: BacktestMetrics | undefined) => <span className="tabular-nums">{v?.sharpe_ratio?.toFixed?.(2) ?? v?.sharpe_ratio ?? '-'}</span>,
      width: 90,
    },
    { title: '交易次数', dataIndex: 'trade_count', width: 90, render: (v: number) => <span className="tabular-nums">{v}</span> },
    {
      title: '操作',
      render: (_: unknown, record: BacktestListItem) => (
        <Space>
          <Button size="small" icon={<EyeOutlined />} onClick={() => navigate(`/backtests/${record.id}`)}>
            详情
          </Button>
        </Space>
      ),
      width: 100,
    },
  ];

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="回测"
        title="回测管理"
        description="创建和查看策略回测结果，评估策略历史表现与风险指标"
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={openCreateModal}
          >
            新建回测
          </Button>
        }
      />

      <FilterToolbar total={`共 ${displayedBacktests.length} 个`} />

      <SectionHeading title="回测列表" />

      <Panel variant="default" padding="none">
        {!isLoading && displayedBacktests.length === 0 ? (
          // No rows: skip the empty 10-column header and show a direct CTA.
          <div className="ad-p-5">
            <EmptyState
              title="暂无回测"
              description="点击「新建回测」创建第一个回测任务"
              action={
                <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
                  新建回测
                </Button>
              }
            />
          </div>
        ) : (
          <div className={tableWrapClass}>
            <Table
              dataSource={displayedBacktests}
              columns={columns}
              rowKey="id"
              size={rowSize as any}
              loading={isLoading}
              scroll={{ x: 'max-content' }}
              pagination={{ pageSize: 20 }}
            />
          </div>
        )}
      </Panel>

      <Modal
        title="新建回测"
        open={isModalOpen}
        onCancel={() => { setIsModalOpen(false); form.resetFields(); }}
        onOk={() => form.submit()}
        confirmLoading={isCreating}
        {...modalMotionProps}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="strategy_id" label="选择策略" rules={[{ required: true }]}>
            <Select
              placeholder="选择策略"
              options={strategies?.map((s: any) => ({ label: s.name, value: s.id }))}
            />
          </Form.Item>
          <Form.Item name="etf_code" label="标的代码" rules={[{ required: true }]}>
            <Select
              showSearch
              loading={etfLoading}
              placeholder="输入标的代码或名称搜索"
              options={etfOptions}
              filterOption={(input, option) =>
                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
            />
          </Form.Item>
          <Form.Item name="start_date" label="开始日期" rules={[{ required: true }]} initialValue={dayjs().subtract(1, 'year')}>
            <DatePicker className="ad-form-input--full" />
          </Form.Item>
          <Form.Item name="end_date" label="结束日期" rules={[{ required: true }]} initialValue={dayjs()}>
            <DatePicker className="ad-form-input--full" />
          </Form.Item>
          <Form.Item name="initial_capital" label="初始资金" initialValue={100000}>
            <InputNumber className="ad-form-input--full" min={10000} step={10000} />
          </Form.Item>
          <Form.Item name="commission_rate" label="交易成本（单边，默认千1）" initialValue={0.001}>
            <InputNumber className="ad-form-input--full" min={0} max={0.5} step={0.0005} precision={4} />
          </Form.Item>
          <Form.Item name="slippage_rate" label="滑点（单边，默认千1）" initialValue={0.001}>
            <InputNumber className="ad-form-input--full" min={0} max={0.5} step={0.0005} precision={4} />
          </Form.Item>
          <Form.Item name="position_size" label="仓位比例（0-1，默认全仓）" initialValue={1.0}>
            <InputNumber className="ad-form-input--full" min={0} max={1} step={0.05} precision={2} />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}
