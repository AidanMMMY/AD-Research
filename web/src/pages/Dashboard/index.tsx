import { useNavigate } from 'react-router-dom';
import { Table, List, Empty, Spin } from 'antd';
import {
  DatabaseOutlined,
  BarChartOutlined,
  AppstoreOutlined,
  FileTextOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  FolderOpenOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useScores } from '@/hooks/useScores';
import { useFavorites } from '@/hooks/useFavorites';
import { usePoolList } from '@/hooks/usePoolDetail';
import { statsApi } from '@/api/stats';
import StatCard from '@/components/StatCard';
import Panel from '@/components/Panel';
import ETFCodeTag from '@/components/ETFCodeTag';
import ReturnTag from '@/components/ReturnTag';
import ScoreBar from '@/components/ScoreBar';

export default function Dashboard() {
  const navigate = useNavigate();
  const { data: scoresData } = useScores({ limit: 10 });
  const { favorites, count: favCount, isLoading: favLoading } = useFavorites(10);
  const { data: pools, isLoading: poolsLoading } = usePoolList();
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['stats-overview'],
    queryFn: () => statsApi.overview().then((r) => r.data),
    staleTime: 60_000,
  });

  const scoreColumns = [
    {
      title: '排名',
      dataIndex: 'rank_overall',
      width: 70,
      render: (v: number) => (
        <span
          style={{
            fontSize: 'var(--text-body-size)',
            fontWeight: v <= 3 ? 700 : 500,
            color: v <= 3 ? 'var(--accent)' : 'var(--text-secondary)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          {v}
        </span>
      ),
    },
    {
      title: '标的',
      render: (_: unknown, record: any) => (
        <ETFCodeTag code={record.etf_code} name={record.etf_name} />
      ),
    },
    {
      title: '评分',
      render: (_: unknown, record: any) => (
        <ScoreBar score={record.composite_score} size="small" />
      ),
      width: 160,
    },
    {
      title: '1月收益',
      render: (_: unknown, record: any) => <ReturnTag value={record.return_1m} />,
      width: 110,
    },
    {
      title: '趋势',
      width: 60,
      render: (_: unknown, record: any) =>
        record.return_1m >= 0 ? (
          <ArrowUpOutlined style={{ color: 'var(--color-rise)', fontSize: 'var(--text-body-size)' }} />
        ) : (
          <ArrowDownOutlined style={{ color: 'var(--color-fall)', fontSize: 'var(--text-body-size)' }} />
        ),
    },
  ];

  const statCards = [
    <StatCard
      title="标的总数"
      value={stats?.etf_count ?? 0}
      icon={<DatabaseOutlined style={{ color: 'var(--accent)' }} />}
      loading={statsLoading}
      onClick={() => navigate('/etfs')}
      bordered={false}
    />,
    <StatCard
      title="评分覆盖"
      value={stats?.score_count ?? 0}
      suffix={`/ ${stats?.etf_count ?? 0}`}
      icon={<BarChartOutlined style={{ color: 'var(--accent)' }} />}
      loading={statsLoading}
      onClick={() => navigate('/scores')}
      bordered={false}
    />,
    <StatCard
      title="分类数"
      value={stats?.category_count ?? 0}
      icon={<AppstoreOutlined style={{ color: 'var(--accent)' }} />}
      loading={statsLoading}
      bordered={false}
    />,
    <StatCard
      title="评分模板"
      value={stats?.template_count ?? 0}
      icon={<FileTextOutlined style={{ color: 'var(--accent)' }} />}
      loading={statsLoading}
      onClick={() => navigate('/scores')}
      bordered={false}
    />,
  ];

  return (
    <div>
      {/* Stats Hero */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 0,
          borderTop: '1px solid var(--border-default)',
          borderBottom: '1px solid var(--border-default)',
          marginBottom: 'var(--space-6)',
        }}
      >
        {statCards.map((card, idx) => (
          <div
            key={idx}
            style={{
              borderRight: idx < 3 ? '1px solid var(--border-default)' : 'none',
              padding: 'var(--space-4)',
            }}
          >
            {card}
          </div>
        ))}
      </div>

      {/* Main Content */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 'var(--space-6)' }}>
        <Panel title="综合评分 Top 10" variant="minimal" padding="md">
          <Table
            dataSource={scoresData?.items || []}
            columns={scoreColumns}
            rowKey="etf_code"
            size="small"
            scroll={{ x: 'max-content' }}
            pagination={false}
            onRow={(record) => ({
              onClick: () => navigate(`/etfs/${record.etf_code}`),
            })}
          />
        </Panel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
          <Panel
            title="我的收藏"
            variant="minimal"
            extra={
              favCount > 0 ? (
                <span
                  style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-secondary)', cursor: 'pointer' }}
                  onClick={() => navigate('/etfs')}
                >
                  查看全部 →
                </span>
              ) : null
            }
            padding="md"
          >
            {favLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : favCount === 0 ? (
              <Empty
                description="暂无收藏的标的"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                style={{ padding: 20 }}
              >
                <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-secondary)' }}>
                  在详情页点击⭐收藏，这里会显示你关注的标的
                </span>
              </Empty>
            ) : (
              <List
                dataSource={favorites}
                renderItem={(item: any) => (
                  <List.Item
                    onClick={() => navigate(`/etfs/${item.etf_code}`)}
                    style={{ padding: '12px 0', cursor: 'pointer' }}
                  >
                    <List.Item.Meta
                      title={
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <ETFCodeTag code={item.etf_code} name={item.etf_name} />
                        </div>
                      }
                      description={
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                          <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-secondary)' }}>{item.category}</span>
                          <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>|</span>
                          <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-secondary)' }}>{item.market}</span>
                        </div>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Panel>

          <Panel
            title="我的标的池"
            variant="minimal"
            extra={
              (pools?.length || 0) > 0 ? (
                <span
                  style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-secondary)', cursor: 'pointer' }}
                  onClick={() => navigate('/pools')}
                >
                  查看全部 →
                </span>
              ) : null
            }
            padding="md"
          >
            {poolsLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : (pools?.length || 0) === 0 ? (
              <Empty
                description="暂无标的池"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                style={{ padding: 20 }}
              >
                <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-secondary)' }}>
                  在标的池管理中创建池并添加标的，这里会汇总展示
                </span>
              </Empty>
            ) : (
              <List
                dataSource={pools?.slice(0, 6) || []}
                renderItem={(pool: any) => (
                  <List.Item
                    onClick={() => navigate(`/pools/${pool.id}`)}
                    style={{ padding: '10px 0', cursor: 'pointer' }}
                  >
                    <List.Item.Meta
                      title={
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <FolderOpenOutlined style={{ color: 'var(--accent)', fontSize: 'var(--text-body-size)' }} />
                          <span style={{ fontSize: 'var(--text-body-size)', color: 'var(--text-primary)', fontWeight: 500 }}>
                            {pool.name}
                          </span>
                        </div>
                      }
                      description={
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                          <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-secondary)' }}>
                            {pool.members?.length || 0} 只标的
                          </span>
                          {pool.description && (
                            <>
                              <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>|</span>
                              <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-secondary)' }}>{pool.description}</span>
                            </>
                          )}
                        </div>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
