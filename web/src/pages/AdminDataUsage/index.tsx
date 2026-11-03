import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Segmented, Table, Typography } from 'antd';
import { ApiOutlined } from '@ant-design/icons';
import { adminDataUsageApi } from '@/api/adminDataUsage';
import Panel from '@/components/Panel';
import LoadingBlock from '@/components/LoadingBlock';

/**
 * 数据 API 通道使用看板（admin-only，2026-11-04）。
 *
 * 外部只读数据消费方（X-API-Key）每一次请求都会落审计行；本页聚合展示
 * 近 N 天的调用量、耗时、错误与热门端点。该通道的存在不对外文档化。
 */

const DAY_OPTIONS = [
  { label: '7 天', value: 7 },
  { label: '14 天', value: 14 },
  { label: '30 天', value: 30 },
  { label: '90 天', value: 90 },
];

export default function AdminDataUsage() {
  const [days, setDays] = useState(7);
  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'data-api-usage', days],
    queryFn: async () => (await adminDataUsageApi.usage(days)).data,
  });

  const totals = data?.totals ?? { requests: 0, errors: 0, avg_ms: null };
  const maxDay = Math.max(1, ...(data?.by_day.map((d) => d.requests) ?? [1]));

  if (isLoading && !data) {
    return (
      <div className="ad-p-5">
        <LoadingBlock size="lg" />
      </div>
    );
  }

  return (
    <div className="ad-p-5">
      <header
        className="ad-mb-4"
        style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}
      >
        <ApiOutlined aria-hidden="true" />
        <Typography.Title level={4} style={{ margin: 0 }}>
          数据通道使用情况
        </Typography.Title>
        <Segmented options={DAY_OPTIONS} value={days} onChange={(v) => setDays(v as number)} />
      </header>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 12,
          marginBottom: 16,
        }}
      >
        <Panel padding="sm">
          <Typography.Text type="secondary">请求总量</Typography.Text>
          <Typography.Title level={3} style={{ margin: 0 }} className="tnum">
            {totals.requests.toLocaleString()}
          </Typography.Title>
        </Panel>
        <Panel padding="sm">
          <Typography.Text type="secondary">错误（≥400）</Typography.Text>
          <Typography.Title level={3} style={{ margin: 0 }} className="tnum">
            {totals.errors.toLocaleString()}
          </Typography.Title>
        </Panel>
        <Panel padding="sm">
          <Typography.Text type="secondary">平均耗时</Typography.Text>
          <Typography.Title level={3} style={{ margin: 0 }} className="tnum">
            {totals.avg_ms != null ? `${totals.avg_ms} ms` : '—'}
          </Typography.Title>
        </Panel>
        <Panel padding="sm">
          <Typography.Text type="secondary">日均请求</Typography.Text>
          <Typography.Title level={3} style={{ margin: 0 }} className="tnum">
            {data && data.by_day.length > 0
              ? Math.round(totals.requests / data.by_day.length).toLocaleString()
              : '—'}
          </Typography.Title>
        </Panel>
      </div>

      <Panel padding="sm" title="按日调用量" style={{ marginBottom: 16 }}>
        {data && data.by_day.length > 0 ? (
          <div
            role="img"
            aria-label="按日调用量柱状图"
            style={{
              display: 'flex',
              alignItems: 'flex-end',
              gap: 6,
              height: 120,
              padding: '0 4px',
            }}
          >
            {data.by_day.map((d) => (
              <div
                key={d.date}
                title={`${d.date}：${d.requests} 次${d.errors ? `（错误 ${d.errors}）` : ''}`}
                style={{
                  flex: 1,
                  minWidth: 8,
                  height: `${Math.max(3, (d.requests / maxDay) * 100)}%`,
                  borderRadius: 3,
                  background:
                    d.errors > 0 ? 'var(--accent)' : 'var(--accent-dim, var(--accent))',
                  opacity: d.errors > 0 ? 1 : 0.7,
                }}
              />
            ))}
          </div>
        ) : (
          <Typography.Text type="secondary">窗口内暂无调用</Typography.Text>
        )}
        {data && data.by_day.length > 0 ? (
          <div
            style={{ display: 'flex', gap: 6, marginTop: 4 }}
            aria-hidden="true"
          >
            {data.by_day.map((d) => (
              <Typography.Text
                key={d.date}
                type="secondary"
                style={{ flex: 1, minWidth: 8, textAlign: 'center', fontSize: 11 }}
                className="tnum"
              >
                {d.date.slice(5)}
              </Typography.Text>
            ))}
          </div>
        ) : null}
      </Panel>

      <Panel padding="sm" title="热门端点" style={{ marginBottom: 16 }}>
        <Table
          size="small"
          rowKey="path"
          pagination={false}
          dataSource={data?.top_paths ?? []}
          columns={[
            { title: '端点', dataIndex: 'path', ellipsis: true },
            {
              title: '调用次数',
              dataIndex: 'requests',
              width: 110,
              align: 'right' as const,
              className: 'tnum',
            },
            {
              title: '平均耗时',
              dataIndex: 'avg_ms',
              width: 110,
              align: 'right' as const,
              render: (v: number | null) => (v != null ? `${v} ms` : '—'),
            },
          ]}
        />
      </Panel>

      <Panel padding="sm" title="最近 100 次调用">
        <Table
          size="small"
          rowKey={(r) => `${r.created_at}-${r.path}-${r.status_code}`}
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
          dataSource={data?.recent ?? []}
          columns={[
            {
              title: '时间 (UTC)',
              dataIndex: 'created_at',
              width: 170,
              render: (v: string | null) => (v ? v.replace('T', ' ').slice(0, 19) : '—'),
            },
            { title: '方法', dataIndex: 'method', width: 70 },
            { title: '端点', dataIndex: 'path', ellipsis: true },
            {
              title: '状态',
              dataIndex: 'status_code',
              width: 70,
              align: 'right' as const,
              render: (v: number) => (
                <span style={{ color: v >= 400 ? 'var(--danger, #e5484d)' : undefined }}>{v}</span>
              ),
            },
            {
              title: '耗时',
              dataIndex: 'duration_ms',
              width: 80,
              align: 'right' as const,
              render: (v: number | null) => (v != null ? `${v}ms` : '—'),
            },
            { title: '来源 IP', dataIndex: 'client_ip', width: 130, ellipsis: true },
            { title: '客户端', dataIndex: 'user_agent', ellipsis: true },
          ]}
        />
      </Panel>
    </div>
  );
}
