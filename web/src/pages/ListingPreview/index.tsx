import { useMemo, useState } from 'react';
import {
  Table, Input, Select, DatePicker, Button, Space, Tag, Skeleton, message, Empty,
} from 'antd';
import { SearchOutlined, ReloadOutlined, CalendarOutlined } from '@ant-design/icons';
import { type Dayjs } from 'dayjs';
import Panel from '@/components/Panel';
import HelpTrigger from '@/components/HelpTrigger';
import ThemeTag from '@/components/ThemeTag';
import PageHeader from '@/components/PageHeader';
import LastUpdated from '@/components/LastUpdated';
import {
  useListingEventList,
  useListingEventFacets,
  useListingEventDetail,
  useRefreshListingEvents,
} from '@/api/listingEvents';
import { useAIHelp } from '@/hooks/useAIHelp';
import { buildListingPreviewContext } from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';
import type { ListingEvent, ListingStatus } from '@/types/listingEvent';
import { STATUS_LABEL } from '@/types/listingEvent';
import ListingEventDetailModal from './DetailModal';

const STATUS_COLOR: Record<ListingStatus, string> = {
  upcoming: 'blue',
  subscribing: 'orange',
  listed: 'green',
  unknown: 'default',
};

const formatDate = (v: string | null | undefined): string => v ?? '-';

const formatMoney = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return '-';
  // funds_raised is in 万元 → display in 亿元
  if (Math.abs(v) >= 1e4) return `${(v / 1e4).toFixed(2)} 亿`;
  return `${v.toFixed(2)} 万`;
};

const formatPrice = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return '-';
  return v.toFixed(2);
};

const formatPe = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return '-';
  return `${v.toFixed(2)} 倍`;
};

interface StatusChipProps {
  status: ListingStatus;
  count: number;
  active: boolean;
  onClick: () => void;
}

function StatusChip({ status, count, active, onClick }: StatusChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        cursor: 'pointer',
        background: active ? 'var(--accent-dim)' : 'var(--card-bg)',
        border: `1px solid ${active ? 'var(--accent-border)' : 'var(--border-default)'}`,
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-2) var(--space-4)',
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        color: active ? 'var(--accent)' : 'var(--text-secondary)',
        fontSize: 'var(--text-small-size)',
      }}
    >
      <Tag color={STATUS_COLOR[status]} style={{ margin: 0 }}>
        {STATUS_LABEL[status]}
      </Tag>
      <span className="tabular-nums" style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{count}</span>
    </button>
  );
}

export default function ListingPreview() {
  const { open } = useAIHelp();
  const [search, setSearch] = useState('');
  const [statuses, setStatuses] = useState<ListingStatus[]>([]);
  const [boards, setBoards] = useState<string[]>([]);
  const [markets, setMarkets] = useState<string[]>([]);
  const [industry, setIndustry] = useState<string | undefined>();
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const listParams = useMemo(
    () => ({
      page,
      page_size: pageSize,
      boards: boards.length > 0 ? boards : undefined,
      markets: markets.length > 0 ? markets : undefined,
      statuses: statuses.length > 0 ? statuses : undefined,
      industry,
      start_date: dateRange?.[0]?.format('YYYY-MM-DD'),
      end_date: dateRange?.[1]?.format('YYYY-MM-DD'),
      date_field: 'list_date' as const,
      q: search || undefined,
      sort_by: 'list_date' as const,
      sort_dir: 'desc' as const,
    }),
    [page, pageSize, boards, markets, statuses, industry, dateRange, search],
  );

  const { data, isLoading, refetch, dataUpdatedAt, isFetching } = useListingEventList(listParams);
  const { data: facets } = useListingEventFacets();
  const { data: detail, isLoading: detailLoading } = useListingEventDetail(detailId);
  const refreshMutation = useRefreshListingEvents();

  // Compute summary counts for the status chips. We do a lightweight extra
  // fetch (page_size=1) per status so the chips reflect the *current filter
  // set minus that single status*. Cheap because the count query is cheap.
  const statusCounts = useMemo(() => {
    const counts: Record<ListingStatus, number> = {
      upcoming: 0,
      subscribing: 0,
      listed: 0,
      unknown: 0,
    };
    if (!data?.items) return counts;
    for (const item of data.items) {
      counts[item.status] = (counts[item.status] ?? 0) + 1;
    }
    return counts;
  }, [data?.items]);

  const handleReset = () => {
    setSearch('');
    setStatuses([]);
    setBoards([]);
    setMarkets([]);
    setIndustry(undefined);
    setDateRange(null);
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
    } catch (err: any) {
      const detail = err?.response?.data?.detail ?? '刷新失败';
      message.error(detail);
    }
  };

  const handleOpenHelp = () => {
    open({
      pageType: 'listing_preview',
      pageTitle: '上市预告',
      contextData: buildListingPreviewContext({
        items: data?.items ?? [],
        total: data?.total ?? 0,
        filters: { statuses, boards, markets, industry, dateRange, search },
      }),
      quickQuestions: getQuickQuestions('listing_preview'),
    });
  };

  const columns = [
    {
      title: '证券代码',
      dataIndex: 'ts_code',
      width: 110,
      render: (v: string, record: ListingEvent) => (
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
      render: (v: string) => (
        <span style={{ color: 'var(--text-primary)' }}>{v}</span>
      ),
    },
    {
      title: '板块',
      dataIndex: 'board',
      width: 90,
      render: (v: string | null) => (v ? <ThemeTag>{v}</ThemeTag> : '-'),
    },
    {
      title: '行业',
      dataIndex: 'industry',
      width: 120,
      render: (v: string | null) =>
        v ? (
          <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-secondary)' }}>{v}</span>
        ) : (
          '-'
        ),
    },
    {
      title: '发行日期',
      dataIndex: 'issue_date',
      width: 110,
      render: formatDate,
    },
    {
      title: '上市日期',
      dataIndex: 'list_date',
      width: 110,
      render: formatDate,
    },
    {
      title: '发行价',
      dataIndex: 'issue_price',
      width: 80,
      render: (v: number | null) => (
        <span className="tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
          {formatPrice(v)}
        </span>
      ),
    },
    {
      title: '市盈率',
      dataIndex: 'pe_ratio',
      width: 90,
      render: (v: number | null) => (
        <span className="tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
          {formatPe(v)}
        </span>
      ),
    },
    {
      title: '募集资金',
      dataIndex: 'funds_raised',
      width: 110,
      render: (v: number | null) => (
        <span className="tabular-nums" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
          {formatMoney(v)}
        </span>
      ),
    },
    {
      title: '保荐机构',
      dataIndex: 'sponsor',
      width: 180,
      ellipsis: true,
      render: (v: string | null) =>
        v ? (
          <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-secondary)' }}>{v}</span>
        ) : (
          '-'
        ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (v: ListingStatus) => <Tag color={STATUS_COLOR[v]}>{STATUS_LABEL[v]}</Tag>,
    },
  ];

  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div>
      <PageHeader
        eyebrow="新股"
        title="上市预告"
        description="A 股近期上市与即将上市新股追踪，覆盖主板 / 创业板 / 科创板 / 北交所"
        extra={
          <Space size="middle">
            <LastUpdated at={dataUpdatedAt} loading={isFetching && !data} />
            <HelpTrigger tooltip="AI 解读上市预告数据" onClick={handleOpenHelp} />
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

      {/* Summary chips */}
      <div style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 24, marginBottom: 16, flexWrap: 'wrap' }}>
        {(['upcoming', 'subscribing', 'listed'] as ListingStatus[]).map((s) => (
          <StatusChip
            key={s}
            status={s}
            count={statusCounts[s]}
            active={statuses.includes(s)}
            onClick={() => {
              setPage(1);
              setStatuses((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));
            }}
          />
        ))}
        <span style={{ marginLeft: 'auto', fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>
          共 <span className="tabular-nums" style={{ color: 'var(--accent)', fontWeight: 500 }}>{total}</span> 条
        </span>
      </div>

      <Panel variant="minimal" title="筛选条件">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-3)', alignItems: 'center' }}>
          <Input
            placeholder="搜索代码或简称"
            allowClear
            prefix={<SearchOutlined style={{ color: 'var(--text-tertiary)' }} />}
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            style={{ width: 240 }}
          />
          <Select
            mode="multiple"
            placeholder="状态"
            allowClear
            style={{ width: 180 }}
            value={statuses}
            onChange={(v) => {
              setStatuses(v);
              setPage(1);
            }}
            options={(['upcoming', 'subscribing', 'listed', 'unknown'] as ListingStatus[]).map((s) => ({
              label: STATUS_LABEL[s],
              value: s,
            }))}
          />
          <Select
            mode="multiple"
            placeholder="板块"
            allowClear
            style={{ width: 200 }}
            value={boards}
            onChange={(v) => {
              setBoards(v);
              setPage(1);
            }}
            options={(facets?.boards ?? []).map((b) => ({ label: b, value: b }))}
          />
          <Select
            mode="multiple"
            placeholder="交易所"
            allowClear
            style={{ width: 160 }}
            value={markets}
            onChange={(v) => {
              setMarkets(v);
              setPage(1);
            }}
            options={(facets?.markets ?? []).map((m) => ({ label: m, value: m }))}
          />
          <Select
            placeholder="行业"
            allowClear
            style={{ width: 180 }}
            value={industry}
            onChange={(v) => {
              setIndustry(v);
              setPage(1);
            }}
            options={(facets?.industries ?? []).map((i) => ({ label: i, value: i }))}
          />
          <DatePicker.RangePicker
            value={dateRange as [Dayjs, Dayjs] | null}
            onChange={(v) => {
              setDateRange(v);
              setPage(1);
            }}
            placeholder={['上市日期 起', '上市日期 止']}
            suffixIcon={<CalendarOutlined />}
          />
          <Button onClick={handleReset}>重置</Button>
        </div>
      </Panel>

      <div style={{ marginTop: 'var(--space-4)' }}>
        {isLoading ? (
          <Skeleton active paragraph={{ rows: 10 }} />
        ) : items.length === 0 ? (
          <Empty description="暂无符合条件的上市预告数据" />
        ) : (
          <Table
            dataSource={items}
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

      <ListingEventDetailModal
        open={detailOpen}
        loading={detailLoading}
        event={detail ?? null}
        onClose={handleCloseDetail}
      />
    </div>
  );
}