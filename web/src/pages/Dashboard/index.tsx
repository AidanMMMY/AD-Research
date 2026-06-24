import { useNavigate } from 'react-router-dom';
import { Table, List, Row, Col, Empty, Spin, Card } from 'antd';
import type { ReactNode } from 'react';
import {
  DatabaseOutlined,
  BarChartOutlined,
  AppstoreOutlined,
  FileTextOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  FolderOpenOutlined,
  RobotOutlined,
  ReadOutlined,
  SmileOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { useScores } from '@/hooks/useScores';
import { useFavorites } from '@/hooks/useFavorites';
import { usePoolList } from '@/hooks/usePoolDetail';
import { statsApi } from '@/api/stats';
import GradientStatCard from '@/components/GradientStatCard';
import GlassCard from '@/components/GlassCard';
import ETFCodeTag from '@/components/ETFCodeTag';
import ReturnTag from '@/components/ReturnTag';
import ScoreBar from '@/components/ScoreBar';

interface DashboardCardProps {
  title: string;
  extra?: ReactNode;
  style?: React.CSSProperties;
  loading: boolean;
  loadingPlaceholder?: ReactNode;
  empty: boolean;
  emptyPlaceholder: ReactNode;
  children: ReactNode;
}

function DashboardCard({ title, extra, style, loading, loadingPlaceholder, empty, emptyPlaceholder, children }: DashboardCardProps) {
  return (
    <GlassCard title={title} extra={extra} style={style}>
      {loading ? loadingPlaceholder : empty ? emptyPlaceholder : children}
    </GlassCard>
  );
}

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
            fontSize: 14,
            fontWeight: 700,
            color:
              v <= 3 ? '#eab308' : v <= 10 ? '#94a3b8' : '#475569',
            fontFamily: "'SF Mono', 'Fira Code', monospace",
          }}
        >
          {v <= 3 && '🏆 '}{v}
        </span>
      ),
    },
    {
      title: 'ETF',
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
          <ArrowUpOutlined style={{ color: '#ef4444', fontSize: 14 }} />
        ) : (
          <ArrowDownOutlined style={{ color: '#22c55e', fontSize: 14 }} />
        ),
    },
  ];

  return (
    <div>
      {/* Stats Row */}
      <Row gutter={[20, 20]} style={{ marginBottom: 28 }}>
        <Col xs={12} sm={6}>
          <GradientStatCard
            title="标的总数"
            value={stats?.etf_count ?? 0}
            icon={<DatabaseOutlined style={{ color: '#818cf8' }} />}
            gradient="purple"
            loading={statsLoading}
            onClick={() => navigate('/etfs')}
          />
        </Col>
        <Col xs={12} sm={6}>
          <GradientStatCard
            title="评分覆盖"
            value={stats?.score_count ?? 0}
            suffix={`/ ${stats?.etf_count ?? 0}`}
            icon={<BarChartOutlined style={{ color: '#06b6d4' }} />}
            gradient="cyan"
            loading={statsLoading}
            onClick={() => navigate('/scores')}
          />
        </Col>
        <Col xs={12} sm={6}>
          <GradientStatCard
            title="分类数"
            value={stats?.category_count ?? 0}
            icon={<AppstoreOutlined style={{ color: '#22c55e' }} />}
            gradient="green"
            loading={statsLoading}
          />
        </Col>
        <Col xs={12} sm={6}>
          <GradientStatCard
            title="评分模板"
            value={stats?.template_count ?? 0}
            icon={<FileTextOutlined style={{ color: '#f59e0b' }} />}
            gradient="orange"
            loading={statsLoading}
            onClick={() => navigate('/scores')}
          />
        </Col>
      </Row>

      {/* AI Quick Entry */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <Card
            hoverable
            size="small"
            onClick={() => navigate('/research')}
            style={{
              background: 'linear-gradient(135deg, rgba(99,102,241,0.08), rgba(139,92,246,0.04))',
              border: '1px solid rgba(99,102,241,0.15)',
              borderRadius: 12,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <ReadOutlined style={{ fontSize: 24, color: '#818cf8' }} />
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0' }}>AI 研报</div>
                <div style={{ fontSize: 11, color: '#64748b' }}>智能生成研究笔记</div>
              </div>
            </div>
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card
            hoverable
            size="small"
            onClick={() => navigate('/sentiment')}
            style={{
              background: 'linear-gradient(135deg, rgba(34,197,94,0.06), rgba(234,179,8,0.04))',
              border: '1px solid rgba(34,197,94,0.12)',
              borderRadius: 12,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <SmileOutlined style={{ fontSize: 24, color: '#22c55e' }} />
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0' }}>情绪分析</div>
                <div style={{ fontSize: 11, color: '#64748b' }}>多源新闻情绪汇聚</div>
              </div>
            </div>
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card
            hoverable
            size="small"
            onClick={() => navigate('/chat')}
            style={{
              background: 'linear-gradient(135deg, rgba(6,182,212,0.06), rgba(99,102,241,0.04))',
              border: '1px solid rgba(6,182,212,0.12)',
              borderRadius: 12,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <RobotOutlined style={{ fontSize: 24, color: '#06b6d4' }} />
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0' }}>AI 助手</div>
                <div style={{ fontSize: 11, color: '#64748b' }}>数据感知智能对话</div>
              </div>
            </div>
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card
            hoverable
            size="small"
            onClick={() => navigate('/screen')}
            style={{
              background: 'linear-gradient(135deg, rgba(245,158,11,0.06), rgba(234,179,8,0.04))',
              border: '1px solid rgba(245,158,11,0.12)',
              borderRadius: 12,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <ThunderboltOutlined style={{ fontSize: 24, color: '#f59e0b' }} />
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0' }}>全市场筛选</div>
                <div style={{ fontSize: 11, color: '#64748b' }}>中美多维度条件</div>
              </div>
            </div>
          </Card>
        </Col>
      </Row>

      {/* Main Content */}
      <Row gutter={[20, 20]}>
        <Col xs={24} lg={16}>
          <GlassCard title="🏆 综合评分 Top 10">
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
          </GlassCard>
        </Col>
        <Col xs={24} lg={8}>
          <DashboardCard
            title="⭐ 我的收藏"
            extra={
              favCount > 0 ? (
                <span
                  style={{ fontSize: 12, color: '#64748b', cursor: 'pointer' }}
                  onClick={() => navigate('/etfs')}
                >
                  查看全部 →
                </span>
              ) : null
            }
            loading={favLoading}
            loadingPlaceholder={<div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>}
            empty={favCount === 0}
            emptyPlaceholder={
              <Empty
                description="暂无收藏的标的"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                style={{ padding: 20 }}
              >
                <span style={{ fontSize: 12, color: '#64748b' }}>
                  在详情页点击⭐收藏，这里会显示你关注的标的
                </span>
              </Empty>
            }
          >
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
                        <span
                          style={{
                            fontSize: 13,
                            fontWeight: 700,
                            fontFamily: "'SF Mono', monospace",
                            color: '#818cf8',
                            background: 'rgba(99,102,241,0.12)',
                            padding: '2px 8px',
                            borderRadius: 6,
                          }}
                        >
                          {item.etf_code}
                        </span>
                        <span style={{ fontSize: 14, color: '#e2e8f0', fontWeight: 500 }}>
                          {item.etf_name}
                        </span>
                      </div>
                    }
                    description={
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                        <span style={{ fontSize: 12, color: '#64748b' }}>{item.category}</span>
                        <span style={{ fontSize: 12, color: '#475569' }}>|</span>
                        <span style={{ fontSize: 12, color: '#64748b' }}>{item.market}</span>
                      </div>
                    }
                  />
                </List.Item>
              )}
            />
          </DashboardCard>

          <DashboardCard
            title="📂 我的标的池"
            style={{ marginTop: 20 }}
            extra={
              (pools?.length || 0) > 0 ? (
                <span
                  style={{ fontSize: 12, color: '#64748b', cursor: 'pointer' }}
                  onClick={() => navigate('/pools')}
                >
                  查看全部 →
                </span>
              ) : null
            }
            loading={poolsLoading}
            loadingPlaceholder={<div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>}
            empty={(pools?.length || 0) === 0}
            emptyPlaceholder={
              <Empty
                description="暂无标的池"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                style={{ padding: 20 }}
              >
                <span style={{ fontSize: 12, color: '#64748b' }}>
                  在标的池管理中创建池并添加ETF，这里会汇总展示
                </span>
              </Empty>
            }
          >
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
                        <FolderOpenOutlined style={{ color: '#22c55e', fontSize: 14 }} />
                        <span style={{ fontSize: 14, color: '#e2e8f0', fontWeight: 500 }}>
                          {pool.name}
                        </span>
                      </div>
                    }
                    description={
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                        <span style={{ fontSize: 12, color: '#64748b' }}>
                          {pool.members?.length || 0} 只标的
                        </span>
                        {pool.description && (
                          <>
                            <span style={{ fontSize: 12, color: '#475569' }}>|</span>
                            <span style={{ fontSize: 12, color: '#64748b' }}>{pool.description}</span>
                          </>
                        )}
                      </div>
                    }
                  />
                </List.Item>
              )}
            />
          </DashboardCard>
        </Col>
      </Row>
    </div>
  );
}
