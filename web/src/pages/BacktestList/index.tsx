import { useState } from 'react';
import {
  Card, Table, Button, Modal, Form, Select, DatePicker, InputNumber, Space, message,
} from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { PlusOutlined, EyeOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';

interface Backtest {
  id: number;
  strategy_id: number;
  etf_code: string;
  start_date: string;
  end_date: string;
  metrics: Record<string, any>;
  trade_count: number;
  created_at: string;
}

interface Strategy {
  id: number;
  name: string;
}

export default function BacktestList() {
  const navigate = useNavigate();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [form] = Form.useForm();
  const queryClient = useQueryClient();

  const { data: backtests, isLoading } = useQuery({
    queryKey: ['backtests'],
    queryFn: async () => {
      const res = await fetch('/api/v1/backtests');
      return res.json();
    },
    staleTime: 30_000,
  });

  const { data: strategies } = useQuery({
    queryKey: ['strategies'],
    queryFn: async () => {
      const res = await fetch('/api/v1/strategies');
      return res.json();
    },
    staleTime: 60_000,
  });

  const createMutation = useMutation({
    mutationFn: async (values: any) => {
      const res = await fetch('/api/v1/backtests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          strategy_id: values.strategy_id,
          etf_code: values.etf_code,
          start_date: values.start_date.format('YYYY-MM-DD'),
          end_date: values.end_date.format('YYYY-MM-DD'),
          initial_capital: values.initial_capital || 100000,
        }),
      });
      return res.json();
    },
    onSuccess: () => {
      message.success('回测已触发');
      setIsModalOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['backtests'] });
    },
    onError: () => message.error('回测失败'),
  });

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '策略ID', dataIndex: 'strategy_id', width: 80 },
    { title: '起始日期', dataIndex: 'start_date' },
    { title: '结束日期', dataIndex: 'end_date' },
    {
      title: '总收益',
      dataIndex: 'metrics',
      render: (v: any) => `${v?.total_return?.toFixed?.(2) ?? v?.total_return ?? 0}%`,
      width: 100,
    },
    {
      title: '最大回撤',
      dataIndex: 'metrics',
      render: (v: any) => `${v?.max_drawdown?.toFixed?.(2) ?? v?.max_drawdown ?? 0}%`,
      width: 100,
    },
    {
      title: '夏普比率',
      dataIndex: 'metrics',
      render: (v: any) => v?.sharpe_ratio?.toFixed?.(2) ?? v?.sharpe_ratio ?? '-',
      width: 90,
    },
    { title: '交易次数', dataIndex: 'trade_count', width: 90 },
    {
      title: '操作',
      render: (_: any, record: Backtest) => (
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
    <div>
      <Card title="回测管理" extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalOpen(true)}>
          新建回测
        </Button>
      }>
        <Table
          dataSource={backtests?.items || []}
          columns={columns}
          rowKey="id"
          size="small"
          loading={isLoading}
          pagination={{ pageSize: 20 }}
        />
      </Card>

      <Modal
        title="新建回测"
        open={isModalOpen}
        onCancel={() => { setIsModalOpen(false); form.resetFields(); }}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending}
      >
        <Form form={form} layout="vertical" onFinish={(v) => createMutation.mutate(v)}>
          <Form.Item name="strategy_id" label="选择策略" rules={[{ required: true }]}>
            <Select
              placeholder="选择策略"
              options={strategies?.items?.map((s: Strategy) => ({ label: s.name, value: s.id }))}
            />
          </Form.Item>
          <Form.Item name="etf_code" label="ETF代码" rules={[{ required: true }]}>
            <Select
              showSearch
              placeholder="输入ETF代码"
              options={[{ label: '沪深300ETF (510300)', value: '510300' }, { label: '上证50ETF (510050)', value: '510050' }, { label: '中证500ETF (510500)', value: '510500' }, { label: '创业板ETF (159915)', value: '159915' }]}
            />
          </Form.Item>
          <Form.Item name="start_date" label="开始日期" rules={[{ required: true }]} initialValue={dayjs().subtract(1, 'year')}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="end_date" label="结束日期" rules={[{ required: true }]} initialValue={dayjs()}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="initial_capital" label="初始资金" initialValue={100000}>
            <InputNumber style={{ width: '100%' }} min={10000} step={10000} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
