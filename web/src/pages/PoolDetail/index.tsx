import { useState, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { Tabs, Table, Button, Slider, message, Row, Col, Statistic, Dropdown, Space } from 'antd';
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
} from '@/hooks/usePoolDetail';
import CategoryPie from '@/components/CategoryPie';
import CorrelationHeatmap from '@/components/CorrelationHeatmap';
import ETFCodeTag from '@/components/ETFCodeTag';
import GlassCard from '@/components/GlassCard';

const SUGGEST_ALGORITHMS: { key: string; label: string }[] = [
  { key: 'equal', label: '等权' },
  { key: 'score', label: '评分加权' },
  { key: 'risk_parity', label: '风险平价' },
];

export default function PoolDetail() {
  const { id } = useParams<{ id: string }>();
  const poolId = Number(id);
  const [editing, setEditing] = useState(false);
  const [localWeights, setLocalWeights] = useState<Record<string, number>>({});

  const { data: pool } = usePoolDetail(poolId);
  const { data: weights } = usePoolWeights(poolId);
  const { data: analytics } = usePoolAnalytics(poolId);
  const { data: correlation } = usePoolCorrelation(poolId);
  const { data: snapshots } = usePoolSnapshots(poolId, 20);
  const updateWeight = useUpdateWeight();
  const createSnapshot = useCreateSnapshot();
  const suggestWeights = useSuggestWeights();

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
    if (sum === 0 || Math.abs(sum - 100) < 0.01) return weightsMap;
    const scaled: Record<string, number> = {};
    entries.forEach(([code, v]) => {
      scaled[code] = Math.round((v / sum) * 100 * 100) / 100;
    });
    // Fix rounding drift on the largest weight so the total is exactly 100
    const scaledSum = Object.values(scaled).reduce((a, b) => a + b, 0);
    const drift = Math.round((100 - scaledSum) * 100) / 100;
    if (drift !== 0) {
      const largestCode = Object.entries(scaled).sort((a, b) => b[1] - a[1])[0][0];
      scaled[largestCode] = Math.round((scaled[largestCode] + drift) * 100) / 100;
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
    const equal = Math.floor(10000 / codes.length) / 100;
    const newWeights: Record<string, number> = {};
    codes.forEach((code: string, idx: number) => {
      newWeights[code] = idx === codes.length - 1 ? Math.round((100 - equal * (codes.length - 1)) * 100) / 100 : equal;
    });
    setLocalWeights(newWeights);
  };

  const handleSuggest = async (algorithm: string) => {
    try {
      await suggestWeights.mutateAsync({ poolId, algorithm });
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

  const suggestMenuItems: MenuProps['items'] = SUGGEST_ALGORITHMS.map((algo) => ({
    key: algo.key,
    label: algo.label,
    onClick: () => handleSuggest(algo.key),
  }));

  const weightColumns = [
    {
      title: 'ETF',
      render: (_: unknown, record: any) => <ETFCodeTag code={record.etf_code} name={record.etf_name} />,
    },
    {
      title: '目标权重',
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
    { title: '建议权重', dataIndex: 'suggested_weight', render: (v: number) => v ? `${v.toFixed(1)}%` : '-' },
    { title: '来源', dataIndex: 'weight_source' },
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
            {editing && (
              <span style={{ color: Math.abs(weightSum - 100) < 0.01 ? '#22c55e' : '#ef4444' }}>
                当前合计：{weightSum.toFixed(2)}%（保存时自动归一化）
              </span>
            )}
          </Space>
          <Table dataSource={weights || []} columns={weightColumns} rowKey="etf_code" pagination={false} />
        </div>
      ),
    },
    {
      key: 'distribution',
      label: '持仓分布',
      children: analytics?.category_distribution ? (
        <Row gutter={[16, 16]}>
          <Col xs={24} md={12}>
            <GlassCard title="分类分布"><CategoryPie data={analytics.category_distribution} mode="count" /></GlassCard>
          </Col>
          <Col xs={24} md={12}>
            <GlassCard title="权重分布"><CategoryPie data={analytics.category_distribution} mode="weight" /></GlassCard>
          </Col>
          <Col xs={24}>
            <GlassCard title="池整体表现">
              <Row gutter={16}>
                <Col span={6}><Statistic title="1月收益" value={analytics.performance?.return_1m} suffix="%" precision={2} /></Col>
                <Col span={6}><Statistic title="3月收益" value={analytics.performance?.return_3m} suffix="%" precision={2} /></Col>
                <Col span={6}><Statistic title="夏普" value={analytics.performance?.sharpe_1y} precision={2} /></Col>
                <Col span={6}><Statistic title="最大回撤" value={analytics.performance?.max_drawdown} suffix="%" precision={2} /></Col>
              </Row>
            </GlassCard>
          </Col>
        </Row>
      ) : <div>暂无分析数据</div>,
    },
    {
      key: 'correlation',
      label: '相关性热力图',
      children: correlation ? (
        <CorrelationHeatmap codes={correlation.codes} matrix={correlation.matrix} />
      ) : <div>暂无数据</div>,
    },
    {
      key: 'snapshots',
      label: '快照记录',
      children: (
        <div>
          <Button type="primary" onClick={handleCreateSnapshot} style={{ marginBottom: 16 }}>
            创建快照
          </Button>
          <Table
            dataSource={snapshots || []}
            columns={snapshotColumns}
            rowKey="id"
            pagination={false}
            locale={{ emptyText: '暂无快照' }}
          />
        </div>
      ),
    },
  ];

  return (
    <div>
      <GlassCard style={{ marginBottom: 16 }}>
        <h2 style={{ margin: 0, color: '#f1f5f9' }}>{pool?.name}</h2>
        <div style={{ color: '#94a3b8' }}>{pool?.description} | {pool?.members?.length || 0} 只ETF</div>
      </GlassCard>
      <Tabs items={tabItems} />
    </div>
  );
}
