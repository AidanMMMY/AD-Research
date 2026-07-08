import { useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Tabs, Table, Button, message, Space, Input, Popconfirm, Select, Alert } from 'antd';
import { ArrowLeftOutlined, EditOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import {
  usePoolDetail,
  usePoolAnalytics,
  usePoolCorrelation,
  useUpdatePool,
  useAddPoolMember,
  useRemovePoolMember,
} from '@/hooks/usePoolDetail';
import { useInstrumentList } from '@/hooks/useInstrumentList';
import { useAIHelp } from '@/hooks/useAIHelp';
import { useSettingsStore } from '@/stores/settings';
import CorrelationHeatmap from '@/components/CorrelationHeatmap';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import Panel from '@/components/Panel';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import ResponsiveGrid from '@/components/ResponsiveGrid';
import StatCard from '@/components/StatCard';
import SectionHeading from '@/components/SectionHeading';
import HelpTrigger from '@/components/HelpTrigger';
import HelpPopover from '@/components/HelpPopover';
import { buildPoolDetailContext } from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';

const formatSigned = (v?: number | null) => {
  if (v == null) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`;
};

export default function PoolDetail() {
  const { id } = useParams<{ id: string }>();
  const poolId = Number(id);
  const isValidPoolId = Number.isFinite(poolId) && poolId > 0;
  const { open } = useAIHelp();
  const mode = useSettingsStore((s) => s.mode);
  const navigate = useNavigate();
  const [editingMeta, setEditingMeta] = useState(false);
  const [editName, setEditName] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [selectedCodeForAdd, setSelectedCodeForAdd] = useState<string | undefined>();
  const queryClient = useQueryClient();

  const { data: pool } = usePoolDetail(poolId);
  const { data: analytics } = usePoolAnalytics(poolId);
  const { data: correlation } = usePoolCorrelation(poolId);
  const { data: etfList } = useInstrumentList({ page_size: 10000 });
  const updatePool = useUpdatePool();
  const addMember = useAddPoolMember();
  const removeMember = useRemovePoolMember();

  const handleUpdatePool = async () => {
    if (!editName.trim()) {
      message.warning('请输入标的池名称');
      return;
    }
    try {
      await updatePool.mutateAsync({
        poolId,
        data: { name: editName, description: editDescription },
      });
      message.success('标的池信息已更新');
      setEditingMeta(false);
    } catch {
      message.error('更新失败');
    }
  };

  const handleAddMember = async () => {
    if (!selectedCodeForAdd) return;
    const code = selectedCodeForAdd;
    const existing = pool?.members?.some((m: any) => m.etf_code === code);
    if (existing) {
      message.warning('该标的已在池中');
      return;
    }
    try {
      await addMember.mutateAsync({ poolId, etf_code: code });
      message.success('标的已添加');
      setSelectedCodeForAdd(undefined);
      queryClient.invalidateQueries({ queryKey: ['pool', poolId] });
      queryClient.invalidateQueries({ queryKey: ['pool-analytics', poolId] });
      queryClient.invalidateQueries({ queryKey: ['pool-correlation', poolId] });
    } catch {
      message.error('添加失败');
    }
  };

  const handleRemoveMember = async (code: string) => {
    try {
      await removeMember.mutateAsync({ poolId, etf_code: code });
      message.success('标的已移除');
    } catch {
      message.error('移除失败');
    }
  };

  const startEditMeta = () => {
    setEditName(pool?.name || '');
    setEditDescription(pool?.description || '');
    setEditingMeta(true);
  };

  const existingCodes = useMemo(() => new Set(pool?.members?.map((m: any) => m.etf_code) || []), [pool]);

  const etfOptions = useMemo(() => {
    return (etfList?.items || [])
      .filter((item) => !existingCodes.has(item.code))
      .map((item) => ({
        label: `${item.code} ${item.name}`,
        value: item.code,
      }));
  }, [etfList, existingCodes]);

  const memberColumns = [
    {
      title: '标的',
      render: (_: unknown, record: any) => (
        <span
          className="instrument-code-tag--clickable"
          onClick={() => navigate(`/instruments/${record.etf_code}`)}
        >
          <InstrumentCodeTag code={record.etf_code} name={record.etf_name} name_zh={record.name_zh} />
        </span>
      ),
    },
    { title: '名称', dataIndex: 'etf_name', render: (v: string, record: any) => v || record.name_zh || '-' },
    { title: '加入时间', dataIndex: 'added_at', render: (v: string) => v ? v.slice(0, 10) : '-' },
    { title: '备注', dataIndex: 'note', render: (v?: string) => v || '-' },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: unknown, record: any) => (
        <Popconfirm
          title="确认移除该标的？"
          onConfirm={() => handleRemoveMember(record.etf_code)}
          okText="确认"
          cancelText="取消"
        >
          <Button type="text" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  const perf = analytics?.performance;
  const heroStats = [
    { title: '1月收益', value: perf?.return_1m, suffix: '%', color: (perf?.return_1m ?? 0) >= 0 ? 'detail-kpi-rise' : 'detail-kpi-fall' },
    { title: '3月收益', value: perf?.return_3m, suffix: '%', color: (perf?.return_3m ?? 0) >= 0 ? 'detail-kpi-rise' : 'detail-kpi-fall' },
    { title: '夏普', value: perf?.sharpe_1y, suffix: undefined, color: 'detail-kpi-accent' },
    { title: '最大回撤', value: perf?.max_drawdown, suffix: '%', color: 'detail-kpi-fall' },
  ];

  const tabItems = [
    {
      key: 'members',
      label: '成员',
      children: (
        <Panel
          padding="md"
          extra={
            <HelpTrigger
              tooltip="AI 解释关注池"
              onClick={() =>
                open({
                  pageType: 'pool_detail',
                  pageTitle: '标的池 - 成员',
                  contextData: buildPoolDetailContext(pool, pool?.members, correlation),
                  quickQuestions: getQuickQuestions('pool_detail'),
                })
              }
            />
          }
        >
          <div className="pool-toolbar">
            <div className="pool-toolbar__actions">
              <Select
                showSearch
                placeholder="选择要添加的标的"
                value={selectedCodeForAdd}
                onChange={setSelectedCodeForAdd}
                options={etfOptions}
                className="pool-add-select"
                filterOption={(input, option) =>
                  (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                }
              />
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={handleAddMember}
                disabled={!selectedCodeForAdd || addMember.isPending}
                loading={addMember.isPending}
              >
                添加标的
              </Button>
            </div>
          </div>
          <Table dataSource={pool?.members || []} columns={memberColumns} rowKey="etf_code" scroll={{ x: 'max-content' }} pagination={false} loading={!pool} />
        </Panel>
      ),
    },
    {
      key: 'correlation',
      label: (
        <HelpPopover termKey="correlation_heatmap" mode={mode}>
          相关性热力图
        </HelpPopover>
      ),
      children: correlation ? (
        <div className="detail-tab-panel">
          <div className="detail-panel-extra">
            <HelpTrigger
              tooltip="AI 解释相关性"
              onClick={() =>
                open({
                  pageType: 'pool_detail',
                  pageTitle: '标的池 - 相关性热力图',
                  contextData: buildPoolDetailContext(pool, pool?.members, correlation),
                  quickQuestions: getQuickQuestions('pool_detail'),
                })
              }
            />
          </div>
          <Panel title="相关性热力图" padding="md">
            <CorrelationHeatmap codes={correlation.codes} matrix={correlation.matrix} />
          </Panel>
        </div>
      ) : (
        <Panel title="相关性热力图" padding="md">
          <div>暂无数据</div>
        </Panel>
      ),
    },
  ];

  if (!isValidPoolId) {
    return (
      <PageShell maxWidth="wide">
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/pools')}
          className="ad-mb-3"
        >
          返回标的池列表
        </Button>
        <PageHeader
          eyebrow="标的池"
          title="标的池详情"
          description="查看和管理关注池与研究篮子成员"
        />
        <Alert message="非法的标的池 ID" description="URL 中的标的池 ID 必须是正整数。" type="error" showIcon />
      </PageShell>
    );
  }

  return (
    <PageShell maxWidth="wide">
      <Button
        type="text"
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/pools')}
        className="ad-mb-3"
      >
        返回标的池列表
      </Button>
      <PageHeader
        eyebrow="标的池"
        title={pool?.name || '标的池详情'}
        description={editingMeta ? undefined : `${pool?.description || '暂无描述'} · ${pool?.members?.length || 0} 只标的`}
        extra={
          editingMeta ? (
            <Button onClick={() => setEditingMeta(false)}>取消</Button>
          ) : (
            <Button icon={<EditOutlined />} onClick={startEditMeta}>编辑信息</Button>
          )
        }
      />

      {editingMeta && (
        <Panel className="detail-section">
          <Space direction="vertical" className="pool-meta-editor" size="middle">
            <Input
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              placeholder="标的池名称"
              className="pool-meta-editor__name"
            />
            <Input
              value={editDescription}
              onChange={(e) => setEditDescription(e.target.value)}
              placeholder="描述（可选）"
              className="pool-meta-editor__desc"
            />
            <Space>
              <Button type="primary" onClick={handleUpdatePool} loading={updatePool.isPending} disabled={!editName.trim() || updatePool.isPending}>
                保存
              </Button>
              <Button onClick={() => setEditingMeta(false)}>取消</Button>
            </Space>
          </Space>
        </Panel>
      )}

      <SectionHeading title="核心指标" />
      <ResponsiveGrid cols={4} gap="md" className="detail-section">
        {heroStats.map((stat) => (
          <div key={stat.title} className={stat.color}>
            <StatCard
              title={stat.title}
              value={stat.value != null ? formatSigned(stat.value) : '—'}
              suffix={stat.suffix}
            />
          </div>
        ))}
      </ResponsiveGrid>

      <Tabs items={tabItems} />
    </PageShell>
  );
}
