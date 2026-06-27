import { useNavigate } from 'react-router-dom';
import { Table, List, Spin } from 'antd';
import {
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

  return (
    <div>
      <h1
        style={{
          fontSize: 'var(--text-h1-size)',
          fontWeight: 500,
          color: 'var(--text-primary)',
          margin: '0 0 8px',
          letterSpacing: '-0.03em',
        }}
      >
        首页看板
      </h1>
      <p
        style={{
          margin: '0 0 32px',
          color: 'var(--text-tertiary)',
          fontSize: 'var(--text-body-size)',
        }}
      >
        综合评分、收藏与标的池概览 · {new Date().toISOString().slice(0, 10)}
      </p>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: '20px',
          marginBottom: '28px',
        }}
      >
        <StatCard title="标的总数" value={stats?.etf_count ?? 0} loading={statsLoading} onClick={() => navigate('/etfs')} bordered />
        <StatCard title="评分覆盖" value={stats?.score_count ?? 0} suffix={`/ ${stats?.etf_count ?? 0}`} loading={statsLoading} onClick={() => navigate('/scores')} bordered />
        <StatCard title="分类数" value={stats?.category_count ?? 0} loading={statsLoading} bordered />
        <StatCard title="评分模板" value={stats?.template_count ?? 0} loading={statsLoading} onClick={() => navigate('/scores')} bordered />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.55fr 1fr', gap: '28px' }}>
        <div style={{
          background: 'var(--card-bg)',
          border: '1px solid var(--card-border)',
          borderRadius: 'var(--card-radius)',
          padding: '24px',
          boxShadow: 'var(--shadow-card)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
            <span style={{ fontSize: 'var(--text-small-size)', fontWeight: 500, color: 'var(--text-tertiary)', letterSpacing: '0.12em', textTransform: 'uppercase' }}>
              综合评分 Top 10
            </span>
            <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)', cursor: 'pointer' }} onClick={() => navigate('/scores')}>
              查看全部 →
            </span>
          </div>
          <Table
            dataSource={scoresData?.items || []}
            columns={scoreColumns}
            rowKey="etf_code"
            size="small"
            scroll={{ x: 'max-content' }}
            pagination={false}
            showHeader={false}
            onRow={(record) => ({ onClick: () => navigate(`/etfs/${record.etf_code}`) })}
          />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div style={{
            background: 'var(--card-bg)',
            border: '1px solid var(--card-border)',
            borderRadius: 'var(--card-radius)',
            padding: '24px',
            boxShadow: 'var(--shadow-card)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
              <span style={{ fontSize: 'var(--text-small-size)', fontWeight: 500, color: 'var(--text-tertiary)', letterSpacing: '0.12em', textTransform: 'uppercase' }}>
                我的收藏
              </span>
              {favCount > 0 && (
                <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)', cursor: 'pointer' }} onClick={() => navigate('/etfs')}>查看全部 →</span>
              )}
            </div>
            {favLoading ? (
              <div style={{ textAlign: 'center', padding: '40px 0' }}><Spin /></div>
            ) : favCount === 0 ? (
              <div style={{ textAlign: 'center', padding: '44px 0', color: 'var(--text-tertiary)' }}>
                <div style={{ fontSize: 'var(--text-body-size)', marginBottom: 4 }}>暂无收藏的标的</div>
                <div style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-muted)' }}>在详情页点击收藏，这里会显示你关注的标的</div>
              </div>
            ) : (
              <List
                dataSource={favorites}
                renderItem={(item: any) => (
                  <List.Item onClick={() => navigate(`/etfs/${item.etf_code}`)} style={{ padding: '12px 0', cursor: 'pointer' }}>
                    <List.Item.Meta
                      title={<div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}><ETFCodeTag code={item.etf_code} name={item.etf_name} /></div>}
                      description={
                        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginTop: 'var(--space-1)' }}>
                          <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>{item.category}</span>
                          <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-muted)' }}>|</span>
                          <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>{item.market}</span>
                        </div>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </div>

          <div style={{
            background: 'var(--card-bg)',
            border: '1px solid var(--card-border)',
            borderRadius: 'var(--card-radius)',
            padding: '24px',
            boxShadow: 'var(--shadow-card)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
              <span style={{ fontSize: 'var(--text-small-size)', fontWeight: 500, color: 'var(--text-tertiary)', letterSpacing: '0.12em', textTransform: 'uppercase' }}>
                我的标的池
              </span>
              {(pools?.length || 0) > 0 && (
                <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)', cursor: 'pointer' }} onClick={() => navigate('/pools')}>查看全部 →</span>
              )}
            </div>
            {poolsLoading ? (
              <div style={{ textAlign: 'center', padding: '40px 0' }}><Spin /></div>
            ) : (pools?.length || 0) === 0 ? (
              <div style={{ textAlign: 'center', padding: '44px 0', color: 'var(--text-tertiary)' }}>
                <div style={{ fontSize: 'var(--text-body-size)', marginBottom: 4 }}>暂无标的池</div>
                <div style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-muted)' }}>在标的池管理中创建池并添加标的，这里会汇总展示</div>
              </div>
            ) : (
              <List
                dataSource={pools?.slice(0, 6) || []}
                renderItem={(pool: any) => (
                  <List.Item onClick={() => navigate(`/pools/${pool.id}`)} style={{ padding: '12px 0', cursor: 'pointer' }}>
                    <List.Item.Meta
                      title={
                        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                          <FolderOpenOutlined style={{ color: 'var(--accent)', fontSize: 'var(--text-body-size)' }} />
                          <span style={{ fontSize: 'var(--text-body-size)', color: 'var(--text-primary)', fontWeight: 500 }}>{pool.name}</span>
                        </div>
                      }
                      description={
                        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginTop: 'var(--space-1)' }}>
                          <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>{pool.members?.length || 0} 只标的</span>
                          {pool.description && (
                            <>
                              <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-muted)' }}>|</span>
                              <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>{pool.description}</span>
                            </>
                          )}
                        </div>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
