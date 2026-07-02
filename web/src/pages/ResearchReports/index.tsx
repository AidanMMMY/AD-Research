import { useMemo, useState } from 'react';
import {
  Table, Input, Select, Button, Space, Tag, Skeleton, message, Empty, Modal,
  Descriptions, Typography, Spin,
} from 'antd';
import { SearchOutlined, ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons';
import Panel from '@/components/Panel';
import PageHeader from '@/components/PageHeader';
import LastUpdated from '@/components/LastUpdated';
import {
  useResearchReportList,
  useResearchReportFacets,
  useResearchReportDetail,
  useRefreshResearchReports,
  useSummarizeResearchReport,
} from '@/api/researchReports';
import type { ResearchReportOut } from '@/api/researchReports';

const { Title, Paragraph } = Typography;

const RATING_COLOR: Record<string, string> = {
  买入: 'red',
  增持: 'orange',
  中性: 'default',
  减持: 'blue',
  卖出: 'green',
};

function ratingColor(r: string | null | undefined): string {
  if (!r) return 'default';
  return RATING_COLOR[r] ?? 'default';
}

function formatPrice(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-';
  return v.toFixed(2);
}

export default function ResearchReports() {
  const [search, setSearch] = useState('');
  const [industry, setIndustry] = useState<string | undefined>();
  const [orgName, setOrgName] = useState<string | undefined>();
  const [rating, setRating] = useState<string | undefined>();
  const [hasSummary, setHasSummary] = useState<'all' | 'yes' | 'no'>('all');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const listParams = useMemo(
    () => ({
      page,
      page_size: pageSize,
      ts_code: search || undefined,
      industry,
      org_name: orgName,
      sort_by: 'publish_date' as const,
      sort_dir: 'desc' as const,
      has_summary: hasSummary === 'all' ? undefined : hasSummary === 'yes',
    }),
    [page, pageSize, search, industry, orgName, hasSummary],
  );

  const { data, isLoading, refetch, dataUpdatedAt, isFetching } = useResearchReportList(listParams);
  const { data: facets } = useResearchReportFacets();
  const { data: detail, isLoading: detailLoading } = useResearchReportDetail(detailId);
  const refreshMutation = useRefreshResearchReports();
  const summarizeMutation = useSummarizeResearchReport();

  const handleReset = () => {
    setSearch('');
    setIndustry(undefined);
    setOrgName(undefined);
    setRating(undefined);
    setHasSummary('all');
    setPage(1);
  };

  const handleOpenDetail = (id: number) => {
    setDetailId(id);
    setDetailOpen(true);
  };

  const handleCloseDetail = () => {
    setDetailOpen(false);
    setDetailId(null);
  };

  const handleRefresh = async () => {
    try {
      const res = await refreshMutation.mutateAsync();
      message.success(`刷新成功：写入 ${res.records} 条记录`);
      refetch();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? '刷新失败';
      message.error(detail);
    }
  };

  const handleSummarize = async (id: number) => {
    try {
      const res = await summarizeMutation.mutateAsync(id);
      if (res.summary) {
        message.success('摘要生成成功');
      } else {
        message.info('摘要为空（可能未配置 API Key 或 LLM 暂不可用）');
      }
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? '摘要失败';
      message.error(detail);
    }
  };

  const columns = [
    {
      title: '证券代码',
      dataIndex: 'ts_code',
      width: 110,
      render: (v: string, record: ResearchReportOut) => (
        <button
          type="button"
          onClick={() => handleOpenDetail(record.id)}
          className="tabular-nums"
          style={{
            background: 'none',
            border: 'none',
            padding: 0,
            color: 'var(--accent)',
            fontFamily: 'var(--font-mono)',
            cursor: 'pointer',
            fontSize: 'var(--text-small-size)',
          }}
        >
          {v}
        </button>
      ),
    },
    {
      title: '简称',
      dataIndex: 'name',
      width: 90,
      render: (v: string) => (
        <span style={{ color: 'var(--text-primary)' }}>{v}</span>
      ),
    },
    {
      title: '机构',
      dataIndex: 'org_name',
      width: 140,
      ellipsis: true,
      render: (v: string) => (
        <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-secondary)' }}>{v}</span>
      ),
    },
    {
      title: '行业',
      dataIndex: 'industry',
      width: 110,
      render: (v: string | null) =>
        v ? (
          <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-secondary)' }}>{v}</span>
        ) : (
          '-'
        ),
    },
    {
      title: '发布日期',
      dataIndex: 'publish_date',
      width: 110,
      render: (v: string) => (
        <span className="tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
          {v ?? '-'}
        </span>
      ),
    },
    {
      title: '评级',
      dataIndex: 'rating',
      width: 80,
      render: (v: string | null) => (v ? <Tag color={ratingColor(v)}>{v}</Tag> : '-'),
    },
    {
      title: '目标价',
      dataIndex: 'target_price',
      width: 80,
      render: (v: number | null) => (
        <span className="tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
          {formatPrice(v)}
        </span>
      ),
    },
    {
      title: '标题',
      dataIndex: 'title',
      ellipsis: true,
      render: (v: string, record: ResearchReportOut) => (
        <button
          type="button"
          onClick={() => handleOpenDetail(record.id)}
          style={{
            background: 'none',
            border: 'none',
            padding: 0,
            color: 'var(--text-primary)',
            cursor: 'pointer',
            textAlign: 'left',
          }}
        >
          {v}
        </button>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_: unknown, record: ResearchReportOut) => (
        <Space size="small">
          {record.pdf_url ? (
            <a href={record.pdf_url} target="_blank" rel="noreferrer">
              PDF
            </a>
          ) : null}
          <Button
            type="link"
            size="small"
            icon={<ThunderboltOutlined />}
            loading={summarizeMutation.isPending && summarizeMutation.variables === record.id}
            onClick={() => handleSummarize(record.id)}
          >
            摘要
          </Button>
        </Space>
      ),
    },
  ];

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const filteredByRating = rating
    ? items.filter((it) => it.rating === rating)
    : items;

  return (
    <div>
      <PageHeader
        eyebrow="研究"
        title="研报库"
        description="A股分析师研报聚合，覆盖个股研报、机构、评级、行业；可选 DeepSeek 自动摘要"
        extra={
          <Space size="middle">
            <LastUpdated at={dataUpdatedAt} loading={isFetching && !data} />
            <Button
              icon={<ReloadOutlined />}
              loading={refreshMutation.isPending}
              onClick={handleRefresh}
            >
              刷新
            </Button>
          </Space>
        }
      />

      <Panel variant="minimal" title="筛选条件">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-3)', alignItems: 'center' }}>
          <Input
            placeholder="搜索证券代码"
            allowClear
            prefix={<SearchOutlined style={{ color: 'var(--text-tertiary)' }} />}
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            style={{ width: 200 }}
          />
          <Select
            placeholder="行业"
            allowClear
            style={{ width: 160 }}
            value={industry}
            onChange={(v) => {
              setIndustry(v);
              setPage(1);
            }}
            options={(facets?.industries ?? []).map((i) => ({ label: i, value: i }))}
          />
          <Select
            placeholder="机构"
            allowClear
            style={{ width: 200 }}
            value={orgName}
            onChange={(v) => {
              setOrgName(v);
              setPage(1);
            }}
            options={(facets?.orgs ?? []).map((o) => ({ label: o, value: o }))}
          />
          <Select
            placeholder="评级"
            allowClear
            style={{ width: 120 }}
            value={rating}
            onChange={(v) => {
              setRating(v);
              setPage(1);
            }}
            options={(facets?.ratings ?? []).map((r) => ({ label: r, value: r }))}
          />
          <Select
            value={hasSummary}
            style={{ width: 130 }}
            onChange={(v) => {
              setHasSummary(v);
              setPage(1);
            }}
            options={[
              { label: '全部', value: 'all' },
              { label: '已有摘要', value: 'yes' },
              { label: '未生成', value: 'no' },
            ]}
          />
          <Button onClick={handleReset}>重置</Button>
        </div>
      </Panel>

      <div style={{ marginTop: 'var(--space-4)' }}>
        {isLoading ? (
          <Skeleton active paragraph={{ rows: 10 }} />
        ) : filteredByRating.length === 0 && items.length === 0 ? (
          <Empty description="暂无符合条件的研报" />
        ) : (
          <Table
            dataSource={filteredByRating}
            columns={columns}
            rowKey="id"
            scroll={{ x: 'max-content' }}
            pagination={{
              current: page,
              pageSize,
              total,
              onChange: setPage,
              showSizeChanger: false,
              showTotal: (t) => `共 ${t} 条`,
            }}
            onRow={(record) => ({
              onClick: () => handleOpenDetail(record.id),
              style: { cursor: 'pointer' },
            })}
          />
        )}
      </div>

      <Modal
        open={detailOpen}
        title={detail?.title ?? '研报详情'}
        onCancel={handleCloseDetail}
        width={720}
        footer={[
          <Button key="close" onClick={handleCloseDetail}>
            关闭
          </Button>,
        ]}
      >
        {detailLoading || !detail ? (
          <Spin />
        ) : (
          <>
            <Descriptions column={2} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="证券代码">{detail.ts_code}</Descriptions.Item>
              <Descriptions.Item label="简称">{detail.name}</Descriptions.Item>
              <Descriptions.Item label="机构">{detail.org_name}</Descriptions.Item>
              <Descriptions.Item label="行业">{detail.industry ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="发布日期">{detail.publish_date}</Descriptions.Item>
              <Descriptions.Item label="评级">
                {detail.rating ? <Tag color={ratingColor(detail.rating)}>{detail.rating}</Tag> : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="目标价">{formatPrice(detail.target_price)}</Descriptions.Item>
              <Descriptions.Item label="发布时价格">
                {formatPrice(detail.current_price_at_publish)}
              </Descriptions.Item>
              <Descriptions.Item label="PDF" span={2}>
                {detail.pdf_url ? (
                  <a href={detail.pdf_url} target="_blank" rel="noreferrer">
                    {detail.pdf_url}
                  </a>
                ) : (
                  '-'
                )}
              </Descriptions.Item>
            </Descriptions>

            <Title level={5}>摘要</Title>
            {detail.summary ? (
              <Paragraph>{detail.summary}</Paragraph>
            ) : (
              <Paragraph type="secondary">尚未生成摘要（点击上方"摘要"按钮可触发）</Paragraph>
            )}

            {detail.key_points && detail.key_points.length > 0 ? (
              <>
                <Title level={5}>核心要点</Title>
                <ul>
                  {detail.key_points.map((p, i) => (
                    <li key={i}>{p}</li>
                  ))}
                </ul>
              </>
            ) : null}
          </>
        )}
      </Modal>
    </div>
  );
}