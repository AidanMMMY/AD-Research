import { useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import {
  Table, Input, Select, Button, Space, message, Modal,
  Descriptions, Typography, Pagination,
} from 'antd';
import type { TableProps } from 'antd/es/table';
import { SearchOutlined, ReloadOutlined, ThunderboltOutlined, FileTextOutlined } from '@ant-design/icons';
import PageShell from '@/components/PageShell';
import Panel from '@/components/Panel';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import EmptyState from '@/components/EmptyState';
import ErrorState from '@/components/ErrorState';
import ThemeTag from '@/components/ThemeTag';
import LastUpdated from '@/components/LastUpdated';
import LoadingBlock from '@/components/LoadingBlock';
import { FilterSheetButton } from '@/components/BottomSheet';
import {
  useResearchReportList,
  useResearchReportFacets,
  useResearchReportDetail,
  useRefreshResearchReports,
  useSummarizeResearchReport,
} from '@/api/researchReports';
import type { ResearchReportOut } from '@/api/researchReports';
import { useDebounce } from '@/hooks/useDebounce';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { clickableRow } from '@/utils/a11y';
import { NULL_PLACEHOLDER } from '@/utils/format';

/**
 * Apple Design fixes scoped to this page: rows open a detail modal on
 * click, so they get an affordance cursor and pointer-down feedback
 * (:active highlight on touch-down, not release — Apple's Response
 * principle). Reduced-motion users get no transition.
 */
const RESEARCH_REPORTS_PAGE_STYLE = `
.research-reports-row {
  cursor: pointer;
  transition: background var(--transition-fast, 150ms ease);
}
.research-reports-row:active {
  background: var(--bg-active) !important;
}
/* Apple "Spatial consistency": the detail modal scales out from the
   row that opened it instead of popping in centered. The
   transform-origin is set inline via CSS variables on the modal
   wrap (modalOriginX/modalOriginY). */
.ant-modal.research-reports-detail-modal .ant-modal-content {
  animation: research-reports-modal-spring var(--transition-spring) both;
  transform-origin: var(--modal-origin-x, 50%) var(--modal-origin-y, 50%);
}
@keyframes research-reports-modal-spring {
  from { opacity: 0; transform: scale(0.95); }
  to   { opacity: 1; transform: scale(1); }
}
@media (prefers-reduced-motion: reduce) {
  .research-reports-row { transition: none; }
  .ant-modal.research-reports-detail-modal .ant-modal-content {
    animation: none;
    transform: none;
  }
}

/* ---- Mobile (≤767px): table → hairline row-list (direction A) ----
   C4（2026-08-03）：筛选条已迁 FilterSheetButton，原横向滚动筛选条
   CSS（.research-reports__filters .filter-toolbar__filters …）随之下线。 */
@media (max-width: 767px) {
  .research-reports-mrow:active {
    background: var(--bg-active);
  }
  .research-reports-mrow__main {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .research-reports-mrow__title {
    font-size: var(--text-body-size);
    font-weight: 500;
    color: var(--text-primary);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .research-reports-mrow__meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-1) var(--space-2);
    font-size: var(--text-small-size);
    color: var(--text-tertiary);
  }
  .research-reports-mrow__side {
    flex-shrink: 0;
    margin-left: auto;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 2px;
  }
  .research-reports-mrow__price {
    font-family: var(--num-font);
    font-size: var(--text-small-size);
    color: var(--text-secondary);
  }
  .research-reports__pagination {
    display: flex;
    justify-content: center;
    margin-top: var(--space-3);
  }
}
`;

const { Title, Paragraph } = Typography;

/** 评级 → ThemeTag variant（审计 P1：弃用 antd 预设色 Tag，全部走 token） */
const RATING_VARIANT: Record<string, 'rise' | 'warning' | 'neutral' | 'accent' | 'fall'> = {
  买入: 'rise',
  增持: 'warning',
  中性: 'neutral',
  减持: 'accent',
  卖出: 'fall',
};

function ratingVariant(r: string | null | undefined) {
  return (r && RATING_VARIANT[r]) || 'neutral';
}

function formatPrice(v: number | null | undefined): string {
  if (v === null || v === undefined) return NULL_PLACEHOLDER;
  return v.toFixed(2);
}

export default function ResearchReports() {
  const isMobile = useIsMobile();
  const [search, setSearch] = useState('');
  const [industry, setIndustry] = useState<string | undefined>();
  const [orgName, setOrgName] = useState<string | undefined>();
  const [rating, setRating] = useState<string | undefined>();
  const [hasSummary, setHasSummary] = useState<'all' | 'yes' | 'no'>('all');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  // 受控排序（审计 P1）：API 已支持 sort_by/sort_dir，表头 sorter 直接
  // 驱动服务端排序，避免客户端只排当前页的假象。
  const [sortBy, setSortBy] = useState<'publish_date' | 'target_price'>('publish_date');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [detailId, setDetailId] = useState<number | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  /* Apple "Spatial consistency": capture the row position so the
     detail modal scales out from the row that opened it. */
  const [detailAnchor, setDetailAnchor] = useState<{ x: number; y: number } | null>(null);
  const debouncedSearch = useDebounce(search, 300);

  const listParams = useMemo(
    () => ({
      page,
      page_size: pageSize,
      ts_code: debouncedSearch || undefined,
      industry,
      org_name: orgName,
      rating,
      sort_by: sortBy,
      sort_dir: sortDir,
      has_summary: hasSummary === 'all' ? undefined : hasSummary === 'yes',
    }),
    [page, pageSize, debouncedSearch, industry, orgName, rating, sortBy, sortDir, hasSummary],
  );

  // 解构 isError：接口失败时显示错误态（带重试），不能落入假空态（审计 P1）。
  const { data, isLoading, isError, refetch, dataUpdatedAt, isFetching } = useResearchReportList(listParams);
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

  const handleOpenDetail = (id: number, anchorEl?: HTMLElement | null) => {
    if (anchorEl) {
      const rect = anchorEl.getBoundingClientRect();
      setDetailAnchor({
        x: rect.left + rect.width / 2,
        y: rect.top + rect.height / 2,
      });
    } else {
      setDetailAnchor(null);
    }
    setDetailId(id);
    setDetailOpen(true);
  };

  const handleCloseDetail = () => {
    setDetailOpen(false);
    setDetailId(null);
    setDetailAnchor(null);
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

  // 受控服务端排序：表头点击 → sortBy/sortDir → 重新查询（整表排序，
  // 非当前页客户端重排）。onChange 在分页变化时也会触发，需守卫 no-op。
  const handleTableChange: TableProps<ResearchReportOut>['onChange'] = (
    _pagination,
    _filters,
    sorter,
  ) => {
    const s = Array.isArray(sorter) ? sorter[0] : sorter;
    const field = s?.field === 'target_price' ? 'target_price' : 'publish_date';
    const dir = s?.order === 'ascend' ? 'asc' : 'desc';
    if (field === sortBy && dir === sortDir) return;
    setSortBy(field);
    setSortDir(dir);
    setPage(1);
  };

  const sortOrderFor = (field: 'publish_date' | 'target_price') =>
    sortBy === field ? (sortDir === 'asc' ? ('ascend' as const) : ('descend' as const)) : null;

  const columns = [
    {
      title: '证券代码',
      dataIndex: 'ts_code',
      width: 110,
      render: (v: string, record: ResearchReportOut) => (
        <Button
          type="link"
          size="small"
          className="tabular-nums"
          onClick={(e) => {
            e.stopPropagation();
            handleOpenDetail(
              record.id,
              (e.currentTarget as HTMLElement | null) ?? null,
            );
          }}
        >
          {v}
        </Button>
      ),
    },
    {
      title: '简称',
      dataIndex: 'name',
      width: 90,
    },
    {
      title: '机构',
      dataIndex: 'org_name',
      width: 140,
      ellipsis: true,
    },
    {
      title: '行业',
      dataIndex: 'industry',
      width: 110,
      render: (v: string | null) => v ?? NULL_PLACEHOLDER,
    },
    {
      title: '发布日期',
      dataIndex: 'publish_date',
      width: 120,
      sorter: true,
      sortOrder: sortOrderFor('publish_date'),
      render: (v: string) => (
        <span className="tabular-nums">{v ?? NULL_PLACEHOLDER}</span>
      ),
    },
    {
      title: '评级',
      dataIndex: 'rating',
      width: 80,
      render: (v: string | null) =>
        v ? <ThemeTag variant={ratingVariant(v)}>{v}</ThemeTag> : NULL_PLACEHOLDER,
    },
    {
      title: '目标价',
      dataIndex: 'target_price',
      width: 90,
      align: 'right' as const,
      sorter: true,
      sortOrder: sortOrderFor('target_price'),
      render: (v: number | null) => (
        <span className="tabular-nums">{formatPrice(v)}</span>
      ),
    },
    {
      title: '标题',
      dataIndex: 'title',
      ellipsis: true,
      render: (v: string, record: ResearchReportOut) => (
        <Button
          type="link"
          size="small"
          onClick={(e) => {
            e.stopPropagation();
            handleOpenDetail(
              record.id,
              (e.currentTarget as HTMLElement | null) ?? null,
            );
          }}
          className="ad-text-left"
        >
          {v}
        </Button>
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

  // 筛选控件（桌面 FilterToolbar / 移动端 FilterSheetButton 共用，
  // 保持 JSX 元素形式以保住焦点 — 模板参照 News/index.tsx）。
  const filterControls = (
    <>
      <Input
        placeholder="搜索证券代码"
        allowClear
        prefix={<SearchOutlined />}
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setPage(1);
        }}
        style={{ width: 240 }}
        className="ad-w-full"
      />
      <Select
        placeholder="行业"
        allowClear
        value={industry}
        onChange={(v) => {
          setIndustry(v);
          setPage(1);
        }}
        options={(facets?.industries ?? []).map((i) => ({ label: i, value: i }))}
        className="ad-w-full"
      />
      <Select
        placeholder="机构"
        allowClear
        value={orgName}
        onChange={(v) => {
          setOrgName(v);
          setPage(1);
        }}
        options={(facets?.orgs ?? []).map((o) => ({ label: o, value: o }))}
        className="ad-w-full"
      />
      <Select
        placeholder="评级"
        allowClear
        value={rating}
        onChange={(v) => {
          setRating(v);
          setPage(1);
        }}
        options={(facets?.ratings ?? []).map((r) => ({ label: r, value: r }))}
        className="ad-w-full"
      />
      <Select
        value={hasSummary}
        onChange={(v) => {
          setHasSummary(v);
          setPage(1);
        }}
        options={[
          { label: '全部', value: 'all' },
          { label: '已有摘要', value: 'yes' },
          { label: '未生成', value: 'no' },
        ]}
        className="ad-w-full"
      />
    </>
  );

  // 移动端「筛选」按钮角标：非默认筛选条件个数。
  const activeFilterCount =
    (search.trim() ? 1 : 0) +
    (industry ? 1 : 0) +
    (orgName ? 1 : 0) +
    (rating ? 1 : 0) +
    (hasSummary !== 'all' ? 1 : 0);

  return (
    <PageShell maxWidth="wide">
      <style>{RESEARCH_REPORTS_PAGE_STYLE}</style>
      <PageHeader
        eyebrow="研究"
        title="券商研报"
        description="A股券商分析师研报聚合，覆盖个股研报、机构、评级、行业；可选 DeepSeek 自动摘要"
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

      {isMobile ? (
        /* C4（2026-08-03）：移动端筛选条迁 FilterSheetButton，原横向滚动
           迷你条下线（双月 RangePicker / 多 Select 在窄屏超视口）。 */
        <div className="mobile-filter-bar">
          <FilterSheetButton
            activeCount={activeFilterCount}
            onReset={handleReset}
          >
            {filterControls}
          </FilterSheetButton>
          <span className="mobile-filter-bar__meta">
            共 {total.toLocaleString()} 条
          </span>
        </div>
      ) : (
        /* 审计 P1：total 用服务端 total，而非当前页 items.length（翻页后
           计数不再跳变）；rating 筛选已服务端化，原恒等死过滤同步删除。 */
        <FilterToolbar total={total} className="research-reports__filters">
          {filterControls}
          <Button onClick={handleReset}>重置</Button>
        </FilterToolbar>
      )}

      <Panel variant="default" padding="none">
        {isLoading ? (
          <LoadingBlock size="lg" />
        ) : isError ? (
          <ErrorState
            description="研报列表加载失败，请稍后重试"
            onRetry={() => refetch()}
          />
        ) : items.length === 0 ? (
          <EmptyState
            icon={<FileTextOutlined />}
            title="暂无符合条件的研报"
            description="尝试调整筛选条件或刷新数据"
          />
        ) : isMobile ? (
          /* Mobile: hairline row-list; row click opens the same detail
             modal (with the row-anchored spring) as desktop rows. */
          <>
            <div className="row-list">
              {items.map((it) => (
                <div
                  key={it.id}
                  className="hairline-row hairline-row--clickable research-reports-mrow"
                  {...clickableRow(
                    (e) =>
                      handleOpenDetail(
                        it.id,
                        (e.currentTarget as HTMLElement | null) ?? null,
                      ),
                    { role: 'button' },
                  )}
                >
                  <div className="research-reports-mrow__main">
                    <div className="research-reports-mrow__title">{it.title}</div>
                    <div className="research-reports-mrow__meta">
                      <span className="tabular-nums">{it.ts_code}</span>
                      <span>{it.name}</span>
                      <span>{it.org_name}</span>
                      <span className="tabular-nums">{it.publish_date ?? NULL_PLACEHOLDER}</span>
                    </div>
                  </div>
                  <div className="research-reports-mrow__side">
                    {it.rating ? <ThemeTag variant={ratingVariant(it.rating)}>{it.rating}</ThemeTag> : null}
                    <span className="research-reports-mrow__price tabular-nums">
                      {formatPrice(it.target_price)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
            <Pagination
              current={page}
              pageSize={pageSize}
              total={total}
              onChange={setPage}
              size="small"
              showSizeChanger={false}
              className="research-reports__pagination"
            />
          </>
        ) : (
          <div className="ad-table-scroll ad-table-sticky">
            <Table
              dataSource={items}
              columns={columns}
              rowKey="id"
              rowClassName={() => 'research-reports-row'}
              onChange={handleTableChange}
              pagination={{
                current: page,
                pageSize,
                total,
                onChange: setPage,
                showSizeChanger: false,
                showTotal: (t) => `共 ${t} 条`,
              }}
              onRow={(record) => clickableRow((e) =>
                handleOpenDetail(
                  record.id,
                  (e.currentTarget as HTMLElement | null) ?? null,
                ),
              )}
            />
          </div>
        )}
      </Panel>

      <Modal
        open={detailOpen}
        title={detail?.title ?? '研报详情'}
        onCancel={handleCloseDetail}
        afterClose={() => setDetailAnchor(null)}
        width={isMobile ? '100%' : 720}
        className="research-reports-detail-modal"
        wrapClassName="research-reports-detail-modal-wrap"
        style={
          detailAnchor
            ? ({
                ['--modal-origin-x' as string]: `${detailAnchor.x}px`,
                ['--modal-origin-y' as string]: `${detailAnchor.y}px`,
              } as CSSProperties)
            : undefined
        }
        footer={[
          detail && !detail.summary ? (
            <Button
              key="summarize"
              type="primary"
              icon={<ThunderboltOutlined />}
              loading={summarizeMutation.isPending && summarizeMutation.variables === detail.id}
              onClick={() => handleSummarize(detail.id)}
            >
              生成摘要
            </Button>
          ) : null,
          <Button key="close" onClick={handleCloseDetail}>
            关闭
          </Button>,
        ].filter(Boolean)}
      >
        {detailLoading || !detail ? (
          <LoadingBlock size="sm" />
        ) : (
          <>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="证券代码">{detail.ts_code}</Descriptions.Item>
              <Descriptions.Item label="简称">{detail.name}</Descriptions.Item>
              <Descriptions.Item label="机构">{detail.org_name}</Descriptions.Item>
              <Descriptions.Item label="行业">{detail.industry ?? NULL_PLACEHOLDER}</Descriptions.Item>
              <Descriptions.Item label="发布日期">{detail.publish_date}</Descriptions.Item>
              <Descriptions.Item label="评级">
                {detail.rating ? <ThemeTag variant={ratingVariant(detail.rating)}>{detail.rating}</ThemeTag> : NULL_PLACEHOLDER}
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
                  NULL_PLACEHOLDER
                )}
              </Descriptions.Item>
            </Descriptions>

            <Title level={5}>摘要</Title>
            {detail.summary ? (
              <Paragraph>{detail.summary}</Paragraph>
            ) : (
              <Paragraph type="secondary">
                尚未生成摘要（点击下方“生成摘要”按钮可触发）
              </Paragraph>
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
    </PageShell>
  );
}
