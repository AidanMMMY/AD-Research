import { useState } from 'react';
import {
  Table, Button, Modal, Form, Input, Select, Switch, Space, message,
} from 'antd';
import Panel from '@/components/Panel';
import ThemeTag from '@/components/ThemeTag';
import HelpTrigger from '@/components/HelpTrigger';
import HelpPopover from '@/components/HelpPopover';
import { useStrategies } from '@/hooks/useStrategies';
import { useAIHelp } from '@/hooks/useAIHelp';
import { PlusOutlined, PlayCircleOutlined, DeleteOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { buildStrategyListContext } from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';

const TYPE_LABELS: Record<string, string> = {
  momentum: '动量',
  mean_reversion: '均值回归',
  rsi: 'RSI',
};

const TYPE_TERM_KEYS: Record<string, string> = {
  momentum: 'momentum',
  mean_reversion: 'mean_reversion',
  rsi: 'rsi_strategy',
};

export default function StrategyList() {
  const navigate = useNavigate();
  const { open } = useAIHelp();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<any>(null);
  const [form] = Form.useForm();

  const { strategies, templates, isLoading, create, delete: deleteStrategy } = useStrategies();

  const handleOpenHelp = () => {
    open({
      pageType: 'strategy_list',
      pageTitle: '策略管理',
      contextData: buildStrategyListContext(strategies, templates),
      quickQuestions: getQuickQuestions('strategy_list'),
    });
  };

  const handleCreate = async (values: any) => {
    try {
      await create({
        name: values.name,
        description: selectedTemplate?.description || '',
        strategy_type: selectedTemplate?.strategy_type || '',
        params: values.params || {},
        is_active: values.is_active,
      });
      message.success('策略创建成功');
      setIsModalOpen(false);
      form.resetFields();
      setSelectedTemplate(null);
    } catch {
      message.error('创建失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteStrategy(id);
      message.success('删除成功');
    } catch {
      message.error('删除失败');
    }
  };

  const handleTemplateSelect = (templateName: string) => {
    const tmpl = templates?.find((t: any) => t.name === templateName);
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
    {
      title: <HelpPopover termKey="strategy_type">类型</HelpPopover>,
      dataIndex: 'strategy_type',
      render: (v: string) => {
        const termKey = TYPE_TERM_KEYS[v];
        const label = TYPE_LABELS[v] || v;
        return termKey ? (
          <HelpPopover termKey={termKey}>
            <ThemeTag variant="accent">{label}</ThemeTag>
          </HelpPopover>
        ) : (
          <ThemeTag variant="accent">{label}</ThemeTag>
        );
      },
    },
    { title: '状态', dataIndex: 'is_active', render: (v: boolean) => v ? <ThemeTag variant="success">启用</ThemeTag> : <ThemeTag variant="default">禁用</ThemeTag>, width: 80 },
    {
      title: '操作',
      render: (_: any, record: any) => (
        <Space>
          <Button size="small" icon={<PlayCircleOutlined />} onClick={() => navigate(`/backtests?strategy_id=${record.id}`)}>
            回测
          </Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record.id)}>
            删除
          </Button>
        </Space>
      ),
      width: 180,
    },
  ];

  return (
    <div>
      <h1 style={{ fontSize: 'var(--text-h1-size)', fontWeight: 500, color: 'var(--text-primary)', margin: '0 0 8px', letterSpacing: '-0.03em' }}>策略管理</h1>
      <p style={{ margin: '0 0 32px', color: 'var(--text-tertiary)', fontSize: 'var(--text-body-size)' }}>创建和管理交易策略，配置策略参数与启用状态</p>
      <Panel variant="minimal" title="策略管理" extra={
        <Space>
          <HelpTrigger tooltip="AI 解释策略逻辑" onClick={handleOpenHelp} />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setIsModalOpen(true)}>
            新建策略
          </Button>
        </Space>
      }>
        <Table
          dataSource={strategies}
          columns={columns}
          rowKey="id"
          size="small"
          loading={isLoading}
          scroll={{ x: 'max-content' }}
          pagination={false}
        />
      </Panel>

      <Modal
        title="新建策略"
        open={isModalOpen}
        onCancel={() => { setIsModalOpen(false); setSelectedTemplate(null); form.resetFields(); }}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="template" label={<HelpPopover termKey="strategy_template">选择模板</HelpPopover>} rules={[{ required: true }]}>
            <Select
              placeholder="选择策略模板"
              onChange={handleTemplateSelect}
              options={templates?.map((t: any) => ({ label: t.name, value: t.name }))}
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
