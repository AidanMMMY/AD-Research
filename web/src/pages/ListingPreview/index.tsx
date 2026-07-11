import { useMemo, useState } from 'react';
import {
  Table, Input, Select, DatePicker, Button, Space, Tag, Skeleton, message, Row, Col,
} from 'antd';
import { SearchOutlined, ReloadOutlined, CalendarOutlined, FileTextOutlined } from '@ant-design/icons';
import { type Dayjs } from 'dayjs';
import PageShell from '@/components/PageShell';
import Panel from '@/components/Panel';
import FilterToolbar from '@/components/FilterToolbar';
import PageHeader from '@/components/PageHeader';
import SectionHeading from '@/components/SectionHeading';
import EmptyState from '@/components/EmptyState';
import HelpTrigger from '@/components/HelpTrigger';
import ThemeTag from '@/components/ThemeTag';
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
import './styles.css';
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
      className={`ad-status-chip ${active ? 'ad-status-chip--active' : ''}`}
    >
      <Tag color={STATUS_COLOR[status]} className="ad-detail-tag">
        {STATUS_LABEL[status]}
      </Tag>
      <span className="tabular-nums">{count}</span>
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

  const rowSize = 'small';
  const tableWrapClass = 'ad-table-scroll ad-table-sticky';

  const columns = [
    {
      title: '证券代码',
      dataIndex: 'ts_code',
      width: 110,
      render: (v: string, record: ListingEvent) => (
        <Button
          type="link"
          size="small"
          className="tabular-nums"
          onClick={() => handleOpenDetail(record.id)}
        >
          {v}
        </Button>
      ),
    },
    {
      title: '简称',
      dataIndex: 'name',
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
      render: (v: string | null) => v ?? '-',
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
        <span className="tabular-nums">{formatPrice(v)}</span>
      ),
    },
    {
      title: '市盈率',
      dataIndex: 'pe_ratio',
      width: 90,
      render: (v: number | null) => (
        <span className="tabular-nums">{formatPe(v)}</span>
      ),
    },
    {
      title: '募集资金',
      dataIndex: 'funds_raised',
      width: 110,
      render: (v: number | null) => (
        <span className="tabular-nums">{formatMoney(v)}</span>
      ),
    },
    {
      title: '保荐机构',
      dataIndex: 'sponsor',
      width: 180,
      ellipsis: true,
      render: (v: string | null) => v ?? '-',
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
    <PageShell maxWidth="wide">
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

      <FilterToolbar total={total}>
        {/* Section 1: Status quick chips - all on one line */}
        <div className="ad-flex ad-flex-wrap ad-gap-2 ad-mb-3 ad-w-full">
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
        </div>

        {/* Section 2: Filter inputs in a Row/Col grid */}
        <Row gutter={[12, 8]} className="ad-w-full">
          <Col xs={24} sm={12} md={8} lg={5}>
            <Input
              placeholder="搜索代码或简称"
              allowClear
              prefix={<SearchOutlined />}
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              className="ad-w-full"
            />
          </Col>
          <Col xs={24} sm={12} md={8} lg={5}>
            <Select
              mode="multiple"
              placeholder="状态"
              allowClear
              className="ad-w-full"
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
          </Col>
          <Col xs={24} sm={12} md={8} lg={5}>
            <Select
              mode="multiple"
              placeholder="板块"
              allowClear
              className="ad-w-full"
              value={boards}
              onChange={(v) => {
                setBoards(v);
                setPage(1);
              }}
              options={(facets?.boards ?? []).map((b) => ({ label: b, value: b }))}
            />
          </Col>
          <Col xs={24} sm={12} md={8} lg={5}>
            <Select
              mode="multiple"
              placeholder="交易所"
              allowClear
              className="ad-w-full"
              value={markets}
              onChange={(v) => {
                setMarkets(v);
                setPage(1);
              }}
              options={(facets?.markets ?? []).map((m) => ({ label: m, value: m }))}
            />
          </Col>
          <Col xs={24} sm={12} md={8} lg={4}>
            <Select
              placeholder="行业"
              allowClear
              className="ad-w-full"
              value={industry}
              onChange={(v) => {
                setIndustry(v);
                setPage(1);
              }}
              options={(facets?.industries ?? []).map((i) => ({ label: i, value: i }))}
            />
          </Col>
          <Col xs={24} sm={12} md={12} lg={18}>
            <DatePicker.RangePicker
              value={dateRange as [Dayjs, Dayjs] | null}
              onChange={(v) => {
                setDateRange(v);
                setPage(1);
              }}
              placeholder={['上市日期 起', '上市日期 止']}
              suffixIcon={<CalendarOutlined />}
              className="ad-w-full"
            />
          </Col>
          <Col xs={24} sm={12} md={4} lg={6}>
            <Button onClick={handleReset} className="ad-w-full">重置</Button>
          </Col>
        </Row>
      </FilterToolbar>

      <SectionHeading title="上市预告列表" />

      <Panel variant="default" padding="none">
        {isLoading ? (
          <Skeleton active paragraph={{ rows: 10 }} />
        ) : items.length === 0 ? (
          <div className="ad-p-5">
            <EmptyState
              icon={<FileTextOutlined />}
              title="暂无符合条件的上市预告数据"
              description="尝试调整筛选条件或刷新数据"
            />
          </div>
        ) : (
          <div className={tableWrapClass}>
            <Table
              dataSource={items}
              columns={columns}
              rowKey="id"
              size={rowSize as any}
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
              })}
            />
          </div>
        )}
      </Panel>

      <ListingEventDetailModal
        open={detailOpen}
        loading={detailLoading}
        event={detail ?? null}
        onClose={handleCloseDetail}
      />
    </PageShell>
  );
}
