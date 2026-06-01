import { useState } from 'react';
import {
  Card, Table, Button, Modal, Form, Input, Select, Switch, Tag, Space, message, Alert,
} from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { PlusOutlined, DeleteOutlined, SendOutlined } from '@ant-design/icons';

interface NotificationConfig {
  id: number;
  name: string;
  channel_type: string;
  config_json: Record<string, any>;
  is_active: boolean;
  created_at?: string;
}

const PLATFORM_OPTIONS = [
  { label: '企业微信', value: 'wechat' },
  { label: '飞书', value: 'feishu' },
  { label: '钉钉', value: 'dingtalk' },
];

export default function NotificationConfigPage() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [form] = Form.useForm();
  const queryClient = useQueryClient();

  const { data: configs, isLoading } = useQuery({
    queryKey: ['notification-configs'],
    queryFn: async () => {
      const res = await fetch('/api/v1/notifications/configs');
      return res.json();
    },
    staleTime: 30_000,
  });

  const createMutation = useMutation({
    mutationFn: async (values: any) => {
      const res = await fetch('/api/v1/notifications/configs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: values.name,
          channel_type: 'webhook',
          config_json: {
            platform: values.platform,
            webhook_url: values.webhook_url,
          },
          is_active: values.is_active,
        }),
      });
      return res.json();
    },
    onSuccess: () => {
      message.success('创建成功');
      setIsModalOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ['notification-configs'] });
    },
    onError: () => message.error('创建失败'),
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      await fetch(`/api/v1/notifications/configs/${id}`, { method: 'DELETE' });
    },
    onSuccess: () => {
      message.success('删除成功');
      queryClient.invalidateQueries({ queryKey: ['notification-configs'] });
    },
  });

  const testMutation = useMutation({
    mutationFn: async (id: number) => {
      const res = await fetch(`/api/v1/notifications/configs/${id}/test`, { method: 'POST' });
      return res.json();
    },
    onSuccess: (data) => {
      if (data.success) {
        message.success('测试发送成功');
      } else {
        message.error(`测试发送失败: ${data.error}`);
      }
    },
  });

  const columns = [
    { title: '名称', dataIndex: 'name' },
    { title: '渠道', dataIndex: 'config_json', render: (v: any) => PLATFORM_OPTIONS.find(p => p.value === v?.platform)?.label || v?.platform },
    { title: 'Webhook', dataIndex: 'config_json', render: (v: any) => v?.webhook_url ? `${v.webhook_url.slice(0, 30)}...` : '-' },
    { title: '状态', dataIndex: 'is_active', render: (v: boolean) => v ? <Tag color="success">启用</Tag> : <Tag>禁用</Tag> },
    {
      title: '操作',
      render: (_: any, record: NotificationConfig) => (
        <Space>
          <Button size="small" icon={<SendOutlined />} onClick={() => testMutation.mutate(record.id)} loading={testMutation.isPending}>
            测试
          </Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => deleteMutation.mutate(record.id)} loading={deleteMutation.isPending}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  const handleSubmit = (values: any) => {
    createMutation.mutate(values);
  };

  return (
    <div>
      <Card title="推送配置管理" extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalOpen(true)}>
          新增配置
        </Button>
      }>
        <Alert
          message="推送说明"
          description="支持企业微信、飞书、钉钉的Webhook机器人推送。配置Webhook地址后，报告生成完成时会自动推送通知。"
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />
        <Table
          dataSource={configs || []}
          columns={columns}
          rowKey="id"
          size="small"
          loading={isLoading}
          pagination={false}
        />
      </Card>

      <Modal
        title="新增推送配置"
        open={isModalOpen}
        onCancel={() => { setIsModalOpen(false); form.resetFields(); }}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item name="name" label="配置名称" rules={[{ required: true }]}>
            <Input placeholder="如：企业微信通知" />
          </Form.Item>
          <Form.Item name="platform" label="推送平台" rules={[{ required: true }]} initialValue="wechat">
            <Select options={PLATFORM_OPTIONS} />
          </Form.Item>
          <Form.Item name="webhook_url" label="Webhook地址" rules={[{ required: true }]}>
            <Input.TextArea placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..." rows={2} />
          </Form.Item>
          <Form.Item name="is_active" label="启用状态" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
