import { useState } from 'react';
import {
  Card, Table, Button, Modal, Form, Input, Select, Switch, Space, Tag, message,
} from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { PlusOutlined, PlayCircleOutlined, DeleteOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

interface Strategy {
  id: number;
  name: string;
  description: string;
  strategy_type: string;
  params: Record<string, any>;
  is_active: boolean;
  created_at?: string;
}

interface Template {
  name: string;
  description: string;
  strategy_type: string;
  params: Record<string, any>;
}

const TYPE_COLORS: Record<string, string> = {
  momentum: 'blue',
  mean_reversion: 'green',
  rsi: 'purple',
};

const TYPE_LABELS: Record<string, string> = {
  momentum: '动量',
  mean_reversion: '均值回归',
  rsi: 'RSI',
};

export default function StrategyList() {
  const navigate = useNavigate();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null);
  const [form] = Form.useForm();
  const queryClient = useQueryClient();

  const { data: strategies, isLoading } = useQuery({
    queryKey: ['strategies'],
    queryFn: async () => {
      const res = await fetch('/api/v1/strategies');
      return res.json();
    },
    staleTime: 30_000,
  });

  const { data: templates } = useQuery({
    queryKey: ['strategy-templates'],
    queryFn: async () => {
      const res = await fetch('/api/v1/strategies/templates');
      return res.json();
    },
    staleTime: 5 * 60_000,
  });

  const createMutation = useMutation({
    mutationFn: async (values: any) => {
      const res = await fetch('/api/v1/strategies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: values.name,
          description: selectedTemplate?.description || '',
          strategy_type: selectedTemplate?.strategy_type || '',
          params: values.params || {},
          is_active: values.is_active,
        }),
      });
      return res.json();
    },
    onSuccess: () => {
      message.success('策略创建成功');
      setIsModalOpen(false);
      form.resetFields();
      setSelectedTemplate(null);
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      await fetch(`/api/v1/strategies/${id}`, { method: 'DELETE' });
    },
    onSuccess: () => {
      message.success('删除成功');
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
    },
  });

  const handleTemplateSelect = (templateName: string) => {
    const tmpl = templates?.find((t: Template) => t.name === templateName);
    if (tmpl) {
      setSelectedTemplate(tmpl);
      form.setFieldsValue({
        name: tmpl.name,
        params: Object.fromEntries(
          Object.entries(tmpl.params).map(([k, v]) => [k, (v as any).default])
        ),
        is_active: true,
      });
    }
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '名称', dataIndex: 'name' },
    { title: '类型', dataIndex: 'strategy_type', render: (v: string) => <Tag color={TYPE_COLORS[v]}>{TYPE_LABELS[v] || v}</Tag> },
    { title: '状态', dataIndex: 'is_active', render: (v: boolean) => v ? <Tag color="success">启用</Tag> : <Tag>禁用</Tag>, width: 80 },
    {
      title: '操作',
      render: (_: any, record: Strategy) => (
        <Space>
          <Button size="small" icon={<PlayCircleOutlined />} onClick={() => navigate(`/backtests?strategy_id=${record.id}`)}>
            回测
          </Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => deleteMutation.mutate(record.id)}>
            删除
          </Button>
        </Space>
      ),
      width: 180,
    },
  ];

  return (
    <div>
      <Card title="策略管理" extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalOpen(true)}>
          新建策略
        </Button>
      }>
        <Table
          dataSource={strategies?.items || []}
          columns={columns}
          rowKey="id"
          size="small"
          loading={isLoading}
          pagination={false}
        />
      </Card>

      <Modal
        title="新建策略"
        open={isModalOpen}
        onCancel={() => { setIsModalOpen(false); setSelectedTemplate(null); form.resetFields(); }}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={(v) => createMutation.mutate(v)}>
          <Form.Item name="template" label="选择模板" rules={[{ required: true }]}>
            <Select
              placeholder="选择策略模板"
              onChange={handleTemplateSelect}
              options={templates?.map((t: Template) => ({ label: t.name, value: t.name }))}
            />
          </Form.Item>
          <Form.Item name="name" label="策略名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          {selectedTemplate && Object.entries(selectedTemplate.params).map(([key, config]: [string, any]) => (
            <Form.Item key={key} name={['params', key]} label={config.label} initialValue={config.default}>
              <Input type="number" />
            </Form.Item>
          ))}
          <Form.Item name="is_active" label="启用状态" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
