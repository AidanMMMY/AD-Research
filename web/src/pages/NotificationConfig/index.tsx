import { useState } from 'react';
import {
  Table, Button, Modal, Form, Input, Select, Switch, Space, message, Alert, Tabs,
} from 'antd';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import FilterToolbar from '@/components/FilterToolbar';
import EmptyState from '@/components/EmptyState';
import ThemeTag from '@/components/ThemeTag';
import { useNotifications } from '@/hooks/useNotifications';
import { PlusOutlined, DeleteOutlined, SendOutlined, MailOutlined, LinkOutlined } from '@ant-design/icons';

const CHANNEL_OPTIONS = [
  { label: 'Webhook 机器人', value: 'webhook' },
  { label: '邮件 SMTP', value: 'email' },
];

const PLATFORM_OPTIONS = [
  { label: '企业微信', value: 'wechat' },
  { label: '飞书', value: 'feishu' },
  { label: '钉钉', value: 'dingtalk' },
];

export default function NotificationConfigPage() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [channelType, setChannelType] = useState('webhook');
  const [activeTab, setActiveTab] = useState('all');

  const { configs, isLoading, create, delete: deleteConfig, test } = useNotifications();

  const handleCreate = async (values: any) => {
    try {
      const config_json: Record<string, any> = {};
      if (values.channel_type === 'webhook') {
        config_json.platform = values.platform;
        config_json.webhook_url = values.webhook_url;
      } else {
        config_json.to_emails = values.to_emails;
        config_json.subject_prefix = values.subject_prefix || '投研平台';
        if (values.smtp_host) config_json.smtp_host = values.smtp_host;
        if (values.smtp_port) config_json.smtp_port = values.smtp_port;
        if (values.smtp_user) config_json.smtp_user = values.smtp_user;
        if (values.smtp_password) config_json.smtp_password = values.smtp_password;
        config_json.use_tls = values.use_tls !== false;
      }

      await create({
        name: values.name,
        channel_type: values.channel_type,
        config_json,
        is_active: values.is_active,
      });
      message.success('创建成功');
      setIsModalOpen(false);
      form.resetFields();
      setChannelType('webhook');
    } catch {
      message.error('创建失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteConfig(id);
      message.success('删除成功');
    } catch {
      message.error('删除失败');
    }
  };

  const handleTest = async (id: number) => {
    try {
      const response = await test(id);
      const result = response.data;
      if (result.success) {
        message.success('测试发送成功');
      } else {
        message.error(`测试发送失败: ${result.error}`);
      }
    } catch {
      message.error('测试发送失败');
    }
  };

  const filteredConfigs = activeTab === 'all'
    ? configs
    : configs.filter((c: any) => c.channel_type === activeTab);

  const columns = [
    { title: '名称', dataIndex: 'name', width: 180 },
    {
      title: '渠道',
      dataIndex: 'channel_type',
      width: 120,
      render: (v: string) => {
        if (v === 'webhook') return <ThemeTag variant="accent"><LinkOutlined /> Webhook</ThemeTag>;
        if (v === 'email') return <ThemeTag variant="success"><MailOutlined /> 邮件</ThemeTag>;
        return <ThemeTag variant="default">{v}</ThemeTag>;
      },
    },
    {
      title: '详情',
      dataIndex: 'config_json',
      render: (v: any, record: any) => {
        if (record.channel_type === 'webhook') {
          const platform = PLATFORM_OPTIONS.find(p => p.value === v?.platform)?.label || v?.platform;
          return (
            <span>
              <ThemeTag variant="default">{platform}</ThemeTag>
              <span className="ad-text-small ad-text-secondary ad-ml-2">
                {v?.webhook_url ? `${v.webhook_url.slice(0, 40)}...` : '-'}
              </span>
            </span>
          );
        }
        if (record.channel_type === 'email') {
          return (
            <span>
              <ThemeTag variant="success">{v?.to_emails}</ThemeTag>
              <span className="ad-text-small ad-text-secondary ad-ml-2">
                {v?.subject_prefix ? `主题: ${v.subject_prefix}` : ''}
              </span>
            </span>
          );
        }
        return null;
      },
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 90,
      render: (v: boolean) => v ? <ThemeTag variant="success">启用</ThemeTag> : <ThemeTag variant="default">禁用</ThemeTag>,
    },
    {
      title: '操作',
      width: 160,
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" icon={<SendOutlined />} onClick={() => handleTest(record.id)}>
            测试
          </Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record.id)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="系统"
        title="推送配置"
        description="配置消息推送渠道，支持企业微信、飞书、钉钉 Webhook 和邮件通知"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalOpen(true)}>
            新增配置
          </Button>
        }
      />

      <Panel variant="default">
        <Alert
          message="推送说明"
          description={
            <div>
              <p><strong>Webhook 机器人</strong>：支持企业微信、飞书、钉钉的机器人推送，配置 Webhook 地址即可。</p>
              <p><strong>邮件 SMTP</strong>：支持通过 SMTP 发送邮件通知。SMTP 服务器地址、用户名和密码建议通过环境变量全局配置，每个配置只需设置收件人邮箱。</p>
            </div>
          }
          type="info"
          showIcon
          className="ad-mb-4"
        />

        <FilterToolbar total={filteredConfigs.length}>
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={[
              { key: 'all', label: `全部 (${configs.length})` },
              { key: 'webhook', label: `Webhook (${configs.filter((c: any) => c.channel_type === 'webhook').length})` },
              { key: 'email', label: `邮件 (${configs.filter((c: any) => c.channel_type === 'email').length})` },
            ]}
          />
        </FilterToolbar>

        <div className="phase5c-table-wrap">
          <Table
            dataSource={filteredConfigs}
            columns={columns}
            rowKey="id"
            size="small"
            loading={isLoading}
            scroll={{ x: 'max-content' }}
            pagination={false}
            locale={{
              emptyText: <EmptyState title="暂无推送配置" description="点击右上角「新增配置」创建第一个推送渠道" />,
            }}
          />
        </div>
      </Panel>

      <Modal
        title="新增推送配置"
        open={isModalOpen}
        onCancel={() => { setIsModalOpen(false); form.resetFields(); setChannelType('webhook'); }}
        onOk={() => form.submit()}
        width={560}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleCreate}
          initialValues={{ channel_type: 'webhook', is_active: true }}
        >
          <Form.Item name="name" label="配置名称" rules={[{ required: true }]}>
            <Input placeholder="如：企业微信通知" />
          </Form.Item>

          <Form.Item name="channel_type" label="推送渠道" rules={[{ required: true }]}>
            <Select
              options={CHANNEL_OPTIONS}
              onChange={(value) => {
                setChannelType(value);
                form.setFieldsValue({
                  platform: undefined,
                  webhook_url: undefined,
                  to_emails: undefined,
                  subject_prefix: undefined,
                  smtp_host: undefined,
                  smtp_port: undefined,
                  smtp_user: undefined,
                  smtp_password: undefined,
                });
              }}
            />
          </Form.Item>

          {channelType === 'webhook' && (
            <>
              <Form.Item name="platform" label="推送平台" rules={[{ required: true }]} initialValue="wechat">
                <Select options={PLATFORM_OPTIONS} />
              </Form.Item>
              <Form.Item name="webhook_url" label="Webhook 地址" rules={[{ required: true }]}>
                <Input.TextArea placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..." rows={2} />
              </Form.Item>
            </>
          )}

          {channelType === 'email' && (
            <>
              <Form.Item
                name="to_emails"
                label="收件人邮箱"
                rules={[{ required: true }]}
                extra="多个邮箱用逗号分隔，如: user1@example.com, user2@example.com"
              >
                <Input placeholder="user@example.com" />
              </Form.Item>

              <Form.Item name="subject_prefix" label="邮件主题前缀" initialValue="投研平台">
                <Input placeholder="投研平台" />
              </Form.Item>

              <Form.Item name="use_tls" label="使用 TLS 加密" valuePropName="checked" initialValue={true}>
                <Switch />
              </Form.Item>

              <Alert
                message="SMTP 配置说明"
                description={
                  <span>
                    SMTP 服务器地址、用户名和密码建议通过 <strong>环境变量</strong> 全局配置（SMTP_HOST, SMTP_USER, SMTP_PASSWORD），
                    这样所有邮件配置共享同一个 SMTP 账号。如需单独配置，可在下方填写。
                  </span>
                }
                type="warning"
                showIcon
                className="ad-mb-4 ad-mt-2"
              />

              <Form.Item name="smtp_host" label="SMTP 服务器">
                <Input placeholder="smtp.example.com（可选，优先使用环境变量）" />
              </Form.Item>
              <Form.Item name="smtp_port" label="SMTP 端口">
                <Input placeholder="587（可选）" />
              </Form.Item>
              <Form.Item name="smtp_user" label="SMTP 用户名">
                <Input placeholder="user@example.com（可选）" />
              </Form.Item>
              <Form.Item name="smtp_password" label="SMTP 密码">
                <Input.Password placeholder="（可选）" />
              </Form.Item>
            </>
          )}

          <Form.Item name="is_active" label="启用状态" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </PageShell>
  );
}
