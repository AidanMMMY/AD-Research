import { useMemo, useState } from 'react';
import {
  Button, Form, Input, Modal, Tabs, message, Space,
} from 'antd';
import { BookOutlined, ExperimentOutlined, ThunderboltOutlined } from '@ant-design/icons';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import StrategyCard from '@/components/StrategyCard';
import StrategyParamForm from '@/components/StrategyParamForm';
import InstrumentSelector from '@/components/InstrumentSelector';
import { useStrategyCatalog } from '@/hooks/useStrategyCatalog';
import { useRunStrategy } from '@/hooks/useRunStrategy';
import { useStrategies } from '@/hooks/useStrategies';
import type { StrategyCatalogItem, ParamSpec } from '@/types/strategy';
import { useNavigate } from 'react-router-dom';

const FAMILY_TABS = [
  { key: 'all', label: '全部' },
  { key: 'trend_following', label: '趋势跟踪' },
  { key: 'mean_reversion', label: '均值回归' },
  { key: 'momentum', label: '动量' },
  { key: 'volatility', label: '波动率' },
  { key: 'volume', label: '成交量' },
  { key: 'composite', label: '复合因子' },
  { key: 'cross_sectional', label: '横截面' },
  { key: 'event', label: '事件驱动' },
];

export default function StrategyLibrary() {
  const navigate = useNavigate();
  const [activeFamily, setActiveFamily] = useState('all');
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [runModalOpen, setRunModalOpen] = useState(false);
  const [selectedStrategy, setSelectedStrategy] = useState<StrategyCatalogItem | null>(null);
  const [createForm] = Form.useForm();
  const [runForm] = Form.useForm();
  const [runCodes, setRunCodes] = useState<string[]>([]);

  const { data: catalog } = useStrategyCatalog(
    activeFamily === 'all' ? undefined : activeFamily,
  );
  const { create } = useStrategies();
  const runStrategy = useRunStrategy();

  const strategies = useMemo(() => catalog || [], [catalog]);

  const handleCreateConfig = (strategy: StrategyCatalogItem) => {
    setSelectedStrategy(strategy);
    createForm.resetFields();
    createForm.setFieldsValue({
      name: strategy.name,
      description: strategy.description,
      strategy_type: strategy.strategy_type,
      params: buildDefaultParams(strategy.param_specs),
      is_active: true,
    });
    setCreateModalOpen(true);
  };

  const handleRunStrategy = (strategy: StrategyCatalogItem) => {
    setSelectedStrategy(strategy);
    runForm.resetFields();
    runForm.setFieldsValue({
      strategy_type: strategy.strategy_type,
      params: buildDefaultParams(strategy.param_specs),
    });
    setRunCodes([]);
    setRunModalOpen(true);
  };

  const handleBacktest = (strategy: StrategyCatalogItem) => {
    navigate(`/backtests?strategy_type=${strategy.strategy_type}`);
  };

  const handleCreateSubmit = async (values: any) => {
    try {
      await create({
        name: values.name,
        description: values.description,
        strategy_type: values.strategy_type,
        params: values.params,
        is_active: values.is_active,
      });
      message.success('策略配置创建成功');
      setCreateModalOpen(false);
      createForm.resetFields();
    } catch {
      message.error('创建失败');
    }
  };

  const handleRunSubmit = async (values: any) => {
    if (runCodes.length === 0) {
      message.warning('请至少选择一个标的');
      return;
    }
    try {
      const res = await runStrategy.mutateAsync({
        strategy_type: values.strategy_type,
        params: values.params,
        etf_codes: runCodes,
      });
      message.success(`运行成功，生成 ${res.signal_count} 个信号`);
      setRunModalOpen(false);
      runForm.resetFields();
      setRunCodes([]);
    } catch {
      message.error('运行失败');
    }
  };

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="策略"
        title="策略库"
        description="浏览系统内置策略，按家族快速筛选，一键创建配置或运行回测"
        extra={
          <Button icon={<BookOutlined />} onClick={() => navigate('/strategies')}>
            策略管理
          </Button>
        }
      />

      <Tabs
        activeKey={activeFamily}
        onChange={setActiveFamily}
        items={FAMILY_TABS.map((tab) => ({
          key: tab.key,
          label: tab.label,
        }))}
        className="phase5c-tabs--padded"
      />

      <Panel variant="default" title={`共 ${strategies.length} 个策略`}>
        <ResponsiveGrid cols={3} gap="md">
          {strategies.map((strategy) => (
            <StrategyCard
              key={strategy.strategy_type}
              strategy={strategy}
              onCreateConfig={handleCreateConfig}
              onRunStrategy={handleRunStrategy}
              onBacktest={handleBacktest}
            />
          ))}
        </ResponsiveGrid>
      </Panel>

      <Modal
        title={<Space>
          <ExperimentOutlined />
          创建策略配置：{selectedStrategy?.name}
        </Space>}
        open={createModalOpen}
        onCancel={() => { setCreateModalOpen(false); createForm.resetFields(); }}
        onOk={() => createForm.submit()}
        width={600}
        destroyOnClose
      >
        <Form form={createForm} layout="vertical" onFinish={handleCreateSubmit}>
          <Form.Item name="strategy_type" hidden>
            <Input />
          </Form.Item>
          <Form.Item name="name" label="策略名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} />
          </Form.Item>
          {selectedStrategy && (
            <StrategyParamForm paramSpecs={selectedStrategy.param_specs} />
          )}
        </Form>
      </Modal>

      <Modal
        title={<Space>
          <ThunderboltOutlined />
          运行策略：{selectedStrategy?.name}
        </Space>}
        open={runModalOpen}
        onCancel={() => { setRunModalOpen(false); runForm.resetFields(); setRunCodes([]); }}
        onOk={() => runForm.submit()}
        width={720}
        destroyOnClose
        confirmLoading={runStrategy.isPending}
      >
        <Form form={runForm} layout="vertical" onFinish={handleRunSubmit}>
          <Form.Item name="strategy_type" hidden>
            <Input />
          </Form.Item>
          <Form.Item label="选择标的" required>
            <InstrumentSelector
              value={runCodes}
              onChange={setRunCodes}
              showPresets
              showPoolImport
              showClear
              maxCount={50}
            />
            {runCodes.length === 0 && (
              <div className="phase5c-error-hint">
                请至少选择一个标的
              </div>
            )}
          </Form.Item>
          {selectedStrategy && (
            <StrategyParamForm paramSpecs={selectedStrategy.param_specs} />
          )}
        </Form>
      </Modal>
    </PageShell>
  );
}

function buildDefaultParams(paramSpecs: Record<string, ParamSpec>): Record<string, any> {
  return Object.fromEntries(
    Object.entries(paramSpecs).map(([key, spec]) => [key, spec.default]),
  );
}
