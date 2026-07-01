import { useMemo, useState } from 'react';
import {
  Table, Button, Modal, Form, Input, Select, Switch, Space, message,
} from 'antd';
import Panel from '@/components/Panel';
import ThemeTag from '@/components/ThemeTag';
import HelpTrigger from '@/components/HelpTrigger';
import HelpPopover from '@/components/HelpPopover';
import { useStrategies } from '@/hooks/useStrategies';
import { useStrategyCatalog } from '@/hooks/useStrategyCatalog';
import { useAIHelp } from '@/hooks/useAIHelp';
import { PlusOutlined, PlayCircleOutlined, DeleteOutlined, BookOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { buildStrategyListContext } from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';
import type { StrategyCatalogItem } from '@/types/strategy';

const TYPE_TERM_KEYS: Record<string, string> = {
  momentum: 'momentum',
  mean_reversion: 'mean_reversion',
  rsi: 'rsi_strategy',
  ma_crossover: 'ma_crossover',
  macd_signal: 'macd_signal',
  rsi_mean_reversion: 'rsi_mean_reversion',
};

const FAMILY_LABELS: Record<string, string> = {
  trend_following: '趋势跟踪',
  mean_reversion: '均值回归',
  momentum: '动量',
  volatility: '波动率',
  volume: '成交量',
  composite: '复合因子',
  cross_sectional: '横截面',
  event: '事件驱动',
};

export default function StrategyList() {
  const navigate = useNavigate();
  const { open } = useAIHelp();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<StrategyCatalogItem | null>(null);
  const [form] = Form.useForm();

  const { strategies, templates, isLoading, create, delete: deleteStrategy } = useStrategies();
  const { data: catalog } = useStrategyCatalog();

  // Build a type -> catalog entry map for label lookup
  const catalogByType = useMemo(() => {
    const map: Record<string, StrategyCatalogItem> = {};
    (catalog || []).forEach((item) => {
      map[item.strategy_type] = item;
    });
    return map;
  }, [catalog]);

  // Use the catalog (which includes the legacy 3 strategies) for templates
  const allTemplates = useMemo(() => {
    if (catalog && catalog.length > 0) {
      // Convert catalog items to the legacy template format for the existing modal
      return catalog.map((item) => ({
        name: item.name,
        description: item.description,
        strategy_type: item.strategy_type,
        params: item.param_specs,
        family: item.family,
      })) as any;
    }
    return templates || [];
  }, [catalog, templates]);

  const handleOpenHelp = () => {
    open({
      pageType: 'strategy_list',
      pageTitle: '策略管理',
      contextData: buildStrategyListContext(strategies, allTemplates),
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
    const tmpl = allTemplates?.find((t: any) => t.name === templateName);
    if (tmpl) {
      setSelectedTemplate(tmpl as unknown as StrategyCatalogItem);
      const defaultParams = Object.fromEntries(
        Object.entries((tmpl as any).params).map(([k, v]: [string, any]) => [k, v.default]),
      );
      form.setFieldsValue({
        name: tmpl.name,
        params: defaultParams,
        is_active: true,
      });
    }
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '名称', dataIndex: 'name' },
    {
      title: <HelpPopover termKey="strategy_type">类型</HelpPopover>,
      key: 'strategy_type',
      render: (_: any, record: any) => {
        const catalogEntry = catalogByType[record.strategy_type];
        const label = catalogEntry?.name || record.strategy_type;
        const family = catalogEntry?.family;
        const termKey = TYPE_TERM_KEYS[record.strategy_type];
        const tag = (
          <Space size={4}>
            <ThemeTag variant="accent">{label}</ThemeTag>
            {family && family in FAMILY_LABELS && (
              <ThemeTag variant="default">{FAMILY_LABELS[family]}</ThemeTag>
            )}
          </Space>
        );
        if (termKey) {
          return <HelpPopover termKey={termKey}>{tag}</HelpPopover>;
        }
        return tag;
      },
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      render: (v: boolean) => v ? <ThemeTag variant="success">启用</ThemeTag> : <ThemeTag variant="default">禁用</ThemeTag>,
      width: 80,
    },
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 'var(--text-h1-size)', fontWeight: 500, color: 'var(--text-primary)', margin: '0 0 8px', letterSpacing: '-0.03em' }}>策略管理</h1>
          <p style={{ margin: 0, color: 'var(--text-tertiary)', fontSize: 'var(--text-body-size)' }}>创建和管理交易策略，配置策略参数与启用状态</p>
        </div>
        <Button icon={<BookOutlined />} onClick={() => navigate('/strategy-library')}>
          浏览策略库
        </Button>
      </div>
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
              options={allTemplates?.map((t: any) => ({ label: t.name, value: t.name }))}
            />
          </Form.Item>
          <Form.Item name="name" label="策略名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          {selectedTemplate && Object.entries((selectedTemplate as any).params).map(([key, config]: [string, any]) => {
            const initial = config.default;
            if (config.type === 'bool') {
              return (
                <Form.Item
                  key={key}
                  name={['params', key]}
                  label={config.label || key}
                  initialValue={initial}
                  valuePropName="checked"
                >
                  <Switch />
                </Form.Item>
              );
            }
            if (config.type === 'choice') {
              return (
                <Form.Item
                  key={key}
                  name={['params', key]}
                  label={config.label || key}
                  initialValue={initial}
                >
                  <Select options={config.options?.map((o: string) => ({ label: o, value: o }))} />
                </Form.Item>
              );
            }
            return (
              <Form.Item
                key={key}
                name={['params', key]}
                label={config.label || key}
                initialValue={initial}
              >
                <Input
                  type="number"
                  step={config.type === 'int' ? 1 : 0.01}
                />
              </Form.Item>
            );
          })}
          <Form.Item name="is_active" label="启用状态" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
