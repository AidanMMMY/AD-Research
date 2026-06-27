import { useState, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { Tabs, Table, Button, Slider, message, Row, Col, Statistic, Dropdown, Space, Input, Popconfirm, Select } from 'antd';
import { EditOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import type { MenuProps } from 'antd';
import {
  usePoolDetail,
  usePoolWeights,
  usePoolAnalytics,
  usePoolCorrelation,
  useUpdateWeight,
  usePoolSnapshots,
  useCreateSnapshot,
  useSuggestWeights,
  useUpdatePool,
  useAddPoolMember,
  useRemovePoolMember,
} from '@/hooks/usePoolDetail';
import { useETFList } from '@/hooks/useETFList';
import { useAIHelp } from '@/hooks/useAIHelp';
import CategoryPie from '@/components/CategoryPie';
import CorrelationHeatmap from '@/components/CorrelationHeatmap';
import ETFCodeTag from '@/components/ETFCodeTag';
import Panel from '@/components/Panel';
import HelpTrigger from '@/components/HelpTrigger';
import HelpPopover from '@/components/HelpPopover';
import { buildPoolDetailContext } from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';

const SUGGEST_ALGORITHMS: { key: string; label: string }[] = [
  { key: 'equal', label: '等权' },
  { key: 'score', label: '评分加权' },
  { key: 'risk_parity', label: '风险平价（逆波动率）' },
];

const ALGORITHM_TERM_KEYS: Record<string, string> = {
  equal: 'equal_weight',
  score: 'score_weighted',
  risk_parity: 'risk_parity',
};

const round2 = (v: number) => Math.round(v * 100) / 100;

export default function PoolDetail() {
  const { id } = useParams<{ id: string }>();
  const poolId = Number(id);
  const { open } = useAIHelp();
  const [editing, setEditing] = useState(false);
  const [localWeights, setLocalWeights] = useState<Record<string, number>>({});
  const [activeAlgorithm, setActiveAlgorithm] = useState<string | undefined>();
  const [editingMeta, setEditingMeta] = useState(false);
  const [editName, setEditName] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [selectedCodeForAdd, setSelectedCodeForAdd] = useState<string | undefined>();

  const { data: pool } = usePoolDetail(poolId);
  const { data: weights } = usePoolWeights(poolId);
  const { data: analytics } = usePoolAnalytics(poolId);
  const { data: correlation } = usePoolCorrelation(poolId);
  const { data: snapshots } = usePoolSnapshots(poolId, 20);
  const { data: etfList } = useETFList({ page_size: 500 });
  const updateWeight = useUpdateWeight();
  const createSnapshot = useCreateSnapshot();
  const suggestWeights = useSuggestWeights();
  const updatePool = useUpdatePool();
  const addMember = useAddPoolMember();
  const removeMember = useRemovePoolMember();

  // Current weights in the editor: local overrides fall back to API values
  const currentWeights = useMemo(() => {
    const base: Record<string, number> = {};
    weights?.forEach((w: any) => {
      base[w.etf_code] = localWeights[w.etf_code] ?? w.target_weight ?? 0;
    });
    return base;
  }, [weights, localWeights]);

  const weightSum = useMemo(
    () => Object.values(currentWeights).reduce((a, b) => a + b, 0),
    [currentWeights]
  );

  const handleWeightChange = (code: string, value: number) => {
    setLocalWeights((prev) => ({ ...prev, [code]: value }));
  };

  const normalizeWeights = (weightsMap: Record<string, number>): Record<string, number> => {
    const entries = Object.entries(weightsMap);
    const sum = entries.reduce((acc, [, v]) => acc + v, 0);
    if (sum === 0) return weightsMap;
    const scaled: Record<string, number> = {};
    entries.forEach(([code, v]) => {
      scaled[code] = round2((v / sum) * 100);
    });
    // Fix rounding drift on the largest weight so the total is exactly 100
    const drift = round2(100 - Object.values(scaled).reduce((a, b) => a + b, 0));
    if (drift !== 0) {
      const largestCode = Object.entries(scaled).sort((a, b) => b[1] - a[1])[0][0];
      scaled[largestCode] = round2(scaled[largestCode] + drift);
    }
    return scaled;
  };

  const handleSaveWeights = async () => {
    const normalized = normalizeWeights(currentWeights);
    for (const [code, weight] of Object.entries(normalized)) {
      await updateWeight.mutateAsync({ poolId, code, weight });
    }
    message.success('权重已更新并自动归一化至 100%');
    setEditing(false);
    setLocalWeights({});
  };

  const handleEqualWeights = () => {
    const codes = weights?.map((w: any) => w.etf_code) || [];
    if (codes.length === 0) return;
    const equal = round2(100 / codes.length);
    const newWeights: Record<string, number> = {};
    codes.forEach((code: string, idx: number) => {
      newWeights[code] = idx === codes.length - 1 ? round2(100 - equal * (codes.length - 1)) : equal;
    });
    setLocalWeights(newWeights);
  };

  const handleSuggest = async (algorithm: string) => {
    try {
      await suggestWeights.mutateAsync({ poolId, algorithm });
      setActiveAlgorithm(algorithm);
      message.success(`已生成${SUGGEST_ALGORITHMS.find((a) => a.key === algorithm)?.label}建议`);
    } catch {
      message.error('建议权重生成失败');
    }
  };

  const handleCreateSnapshot = async () => {
    try {
      await createSnapshot.mutateAsync(poolId);
      message.success('快照已创建');
    } catch {
      message.error('快照创建失败');
    }
  };

  const handleUpdatePool = async () => {
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
    const existing = weights?.some((w: any) => w.etf_code === code);
    if (existing) {
      message.warning('该标的已在池中');
      return;
    }
    try {
      await addMember.mutateAsync({ poolId, etf_code: code });
      message.success('标的已添加');
      setSelectedCodeForAdd(undefined);
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

  const existingCodes = useMemo(() => new Set(weights?.map((w: any) => w.etf_code) || []), [weights]);

  const etfOptions = useMemo(() => {
    return (etfList?.items || [])
      .filter((item) => !existingCodes.has(item.code))
      .map((item) => ({
        label: `${item.code} ${item.name}`,
        value: item.code,
      }));
  }, [etfList, existingCodes]);

  const suggestMenuItems: MenuProps['items'] = SUGGEST_ALGORITHMS.map((algo) => ({
    key: algo.key,
    label: (
      <HelpPopover termKey={ALGORITHM_TERM_KEYS[algo.key]}>
        {algo.label}
      </HelpPopover>
    ),
    onClick: () => handleSuggest(algo.key),
  }));

  const weightColumns = [
    {
      title: '标的',
      render: (_: unknown, record: any) => <ETFCodeTag code={record.etf_code} name={record.etf_name} />,
    },
    {
      title: <HelpPopover termKey="target_weight">目标权重</HelpPopover>,
      render: (_: unknown, record: any) => (
        editing ? (
          <Slider
            min={0} max={100} step={1}
            value={currentWeights[record.etf_code]}
            onChange={(v) => handleWeightChange(record.etf_code, v)}
            style={{ width: 120 }}
          />
        ) : `${record.target_weight ?? 0}%`
      ),
    },
    { title: <HelpPopover termKey="suggested_weight">建议权重</HelpPopover>, dataIndex: 'suggested_weight', render: (v: number) => v ? `${v.toFixed(1)}%` : '-' },
    { title: <HelpPopover termKey="weight_source">来源</HelpPopover>, dataIndex: 'weight_source' },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: any) => (
        !editing ? (
          <Popconfirm
            title="确认移除该标的？"
            onConfirm={() => handleRemoveMember(record.etf_code)}
            okText="确认"
            cancelText="取消"
          >
            <Button type="text" danger icon={<DeleteOutlined />} size="small" />
          </Popconfirm>
        ) : null
      ),
    },
  ];

  const snapshotColumns = [
    { title: '快照日期', dataIndex: 'snapshot_date' },
    { title: '创建时间', dataIndex: 'created_at' },
    {
      title: '成员数',
      render: (_: unknown, record: any) => record.data?.members?.length ?? '-',
    },
  ];

  const tabItems = [
    {
      key: 'weights',
      label: '成员与权重',
      children: (
        <div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
            <HelpTrigger
              tooltip="AI 解释权重算法"
              onClick={() =>
                open({
                  pageType: 'pool_detail',
                  pageTitle: '标的池 - 成员与权重',
                  contextData: buildPoolDetailContext(pool, weights, analytics, correlation, activeAlgorithm),
                  quickQuestions: getQuickQuestions('pool_detail'),
                })
              }
            />
          </div>
          <Space style={{ marginBottom: 16 }} wrap>
            {editing ? (
              <>
                <Button type="primary" onClick={handleSaveWeights}>保存</Button>
                <Button onClick={() => { setEditing(false); setLocalWeights({}); }}>取消</Button>
                <Button onClick={handleEqualWeights}>重置为等权</Button>
              </>
            ) : (
              <Button onClick={() => setEditing(true)}>编辑权重</Button>
            )}
            <Dropdown menu={{ items: suggestMenuItems }} placement="bottomLeft">
              <Button>生成建议权重</Button>
            </Dropdown>
            {!editing && (
              <>
                <Select
                  showSearch
                  placeholder="选择要添加的标的"
                  value={selectedCodeForAdd}
                  onChange={setSelectedCodeForAdd}
                  options={etfOptions}
                  style={{ minWidth: 220 }}
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
              </>
            )}
            {editing && (
              <span style={{ color: Math.abs(weightSum - 100) < 0.01 ? 'var(--text-secondary)' : 'var(--color-error)' }}>
                当前合计：{weightSum.toFixed(2)}%（保存时自动归一化）
              </span>
            )}
          </Space>
          <Table dataSource={weights || []} columns={weightColumns} rowKey="etf_code" scroll={{ x: 'max-content' }} pagination={false} />
        </div>
      ),
    },
    {
      key: 'distribution',
      label: '持仓分布',
      children: analytics?.category_distribution ? (
        <div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
            <HelpTrigger
              tooltip="AI 解释持仓分析"
              onClick={() =>
                open({
                  pageType: 'pool_detail',
                  pageTitle: '标的池 - 持仓分布',
                  contextData: buildPoolDetailContext(pool, weights, analytics, correlation, activeAlgorithm),
                  quickQuestions: getQuickQuestions('pool_detail'),
                })
              }
            />
          </div>
          <Row gutter={[16, 16]}>
            <Col xs={24} md={12}>
              <Panel title="分类分布"><CategoryPie data={analytics.category_distribution} mode="count" /></Panel>
            </Col>
            <Col xs={24} md={12}>
              <Panel title="权重分布"><CategoryPie data={analytics.category_distribution} mode="weight" /></Panel>
            </Col>
            <Col xs={24}>
              <Row gutter={16}>
                <Col span={6}><Statistic title={<HelpPopover termKey="return_1m">1月收益</HelpPopover>} value={analytics.performance?.return_1m} suffix="%" precision={2} /></Col>
                <Col span={6}><Statistic title={<HelpPopover termKey="return_3m">3月收益</HelpPopover>} value={analytics.performance?.return_3m} suffix="%" precision={2} /></Col>
                <Col span={6}><Statistic title={<HelpPopover termKey="sharpe_1y">夏普</HelpPopover>} value={analytics.performance?.sharpe_1y} precision={2} /></Col>
                <Col span={6}><Statistic title={<HelpPopover termKey="max_drawdown_1y">最大回撤</HelpPopover>} value={analytics.performance?.max_drawdown} suffix="%" precision={2} /></Col>
              </Row>
            </Col>
          </Row>
        </div>
      ) : <div>暂无分析数据</div>,
    },
    {
      key: 'correlation',
      label: (
        <HelpPopover termKey="correlation_heatmap">
          相关性热力图
        </HelpPopover>
      ),
      children: correlation ? (
        <div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
            <HelpTrigger
              tooltip="AI 解释相关性"
              onClick={() =>
                open({
                  pageType: 'pool_detail',
                  pageTitle: '标的池 - 相关性热力图',
                  contextData: buildPoolDetailContext(pool, weights, analytics, correlation, activeAlgorithm),
                  quickQuestions: getQuickQuestions('pool_detail'),
                })
              }
            />
          </div>
          <CorrelationHeatmap codes={correlation.codes} matrix={correlation.matrix} />
        </div>
      ) : <div>暂无数据</div>,
    },
    {
      key: 'snapshots',
      label: <HelpPopover termKey="snapshot">快照记录</HelpPopover>,
      children: (
        <div>
          <Button type="primary" onClick={handleCreateSnapshot} style={{ marginBottom: 16 }}>
            创建快照
          </Button>
          <Table
            dataSource={snapshots || []}
            columns={snapshotColumns}
            rowKey="id"
            scroll={{ x: 'max-content' }}
            pagination={false}
            locale={{ emptyText: '暂无快照' }}
          />
        </div>
      ),
    },
  ];

  return (
    <div>
      <Panel style={{ marginBottom: 16 }}>
        {editingMeta ? (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Input
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              placeholder="标的池名称"
              style={{ maxWidth: 400, fontSize: 'var(--text-h3-size)', fontWeight: 600 }}
            />
            <Input
              value={editDescription}
              onChange={(e) => setEditDescription(e.target.value)}
              placeholder="描述（可选）"
              style={{ maxWidth: 400 }}
            />
            <Space>
              <Button type="primary" onClick={handleUpdatePool} loading={updatePool.isPending}>
                保存
              </Button>
              <Button onClick={() => setEditingMeta(false)}>取消</Button>
            </Space>
          </Space>
        ) : (
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
            <div>
              <h2 style={{ margin: 0, color: 'var(--text-primary)' }}>{pool?.name}</h2>
              <div style={{ color: 'var(--text-secondary)' }}>
                {pool?.description || '暂无描述'} | {pool?.members?.length || 0} 只标的
              </div>
            </div>
            <Button icon={<EditOutlined />} onClick={startEditMeta}>
              编辑信息
            </Button>
          </div>
        )}
      </Panel>
      <Tabs items={tabItems} />
    </div>
  );
}
