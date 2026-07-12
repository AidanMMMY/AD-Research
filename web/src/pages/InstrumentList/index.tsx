import './styles.css';

import { useState, useEffect, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Table,
  Input,
  Select,
  InputNumber,
  List,
  Skeleton,
  Row,
  Col,
  Button,
  Tooltip,
  Collapse,
} from 'antd';
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  useInstrumentList,
  useInstrumentCategories,
  useInstrumentMarkets,
  useInstrumentSectors,
  useInstrumentIndustries,
  useInstrumentSubCategories,
  useInstrumentManagers,
  useInstrumentCurrencies,
  useInstrumentCountries,
  useInstrumentUnderlyingIndices,
  useInstrumentListingMarkets,
  useInstrumentBoards,
} from '@/hooks/useInstrumentList';
import { useMarketStream } from '@/hooks/useMarketStream';
import { useDebounce } from '@/hooks/useDebounce';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import FilterToolbar from '@/components/FilterToolbar';
import Panel from '@/components/Panel';
import EmptyState from '@/components/EmptyState';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import ThemeTag from '@/components/ThemeTag';
import SparklineCell from '@/components/SparklineCell';
import ReturnTag from '@/components/ReturnTag';
import LastUpdated from '@/components/LastUpdated';
import { useIsMobile } from '@/hooks/useBreakpoint';
import { NULL_PLACEHOLDER } from '@/utils/format';

/** Row-level live price cell. Reads from the shared MarketStream map so we
 *  do not open one SSE connection per row. */
function LivePriceCell({ tick }: { code: string; tick: ReturnType<typeof useMarketStream>['latest'][string] | undefined }) {
  if (!tick) {
    return (
      <span className="tabular-nums mobile-list-item__meta font-mono">
        {NULL_PLACEHOLDER}
      </span>
    );
  }
  return (
    <div className="live-price-cell">
      <span className="tabular-nums live-price-cell__price">
        {tick.price.toFixed(2)}
      </span>
      <ReturnTag value={tick.change_pct} />
    </div>
  );
}

const PAGE_SIZE = 50;

const STATUS_OPTIONS = [
  { label: '上市', value: 'active' },
  { label: '退市', value: 'delisted' },
  { label: '暂停', value: 'suspended' },
];

const QDII_OPTIONS = [
  { label: '是', value: true },
  { label: '否', value: false },
];

export default function InstrumentList() {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const [searchParams, setSearchParams] = useSearchParams();

  const [search, setSearch] = useState(searchParams.get('q') ?? '');
  const [market, setMarket] = useState<string | undefined>(searchParams.get('market') ?? undefined);
  const [category, setCategory] = useState<string | undefined>(searchParams.get('category') ?? undefined);
  const [instrumentType, setInstrumentType] = useState<string | undefined>(searchParams.get('type') ?? undefined);
  const [subCategory, setSubCategory] = useState<string | undefined>(searchParams.get('sub_category') ?? undefined);
  const [sector, setSector] = useState<string | undefined>(searchParams.get('sector') ?? undefined);
  const [industry, setIndustry] = useState<string | undefined>(searchParams.get('industry') ?? undefined);
  const [country, setCountry] = useState<string | undefined>(searchParams.get('country') ?? undefined);
  const [manager, setManager] = useState<string | undefined>(searchParams.get('manager') ?? undefined);
  const [underlyingIndex, setUnderlyingIndex] = useState<string | undefined>(searchParams.get('underlying_index') ?? undefined);
  const [currency, setCurrency] = useState<string | undefined>(searchParams.get('currency') ?? undefined);
  const [isQdii, setIsQdii] = useState<boolean | undefined>(() => {
    const raw = searchParams.get('is_qdii');
    if (raw === 'true') return true;
    if (raw === 'false') return false;
    return undefined;
  });
  const [status, setStatus] = useState<string | undefined>(searchParams.get('status') ?? undefined);
  const [minFundSize, setMinFundSize] = useState<number | undefined>(() => {
    const raw = searchParams.get('min_fund_size');
    return raw ? Number(raw) : undefined;
  });
  const [maxFundSize, setMaxFundSize] = useState<number | undefined>(() => {
    const raw = searchParams.get('max_fund_size');
    return raw ? Number(raw) : undefined;
  });
  const [listingMarket, setListingMarket] = useState<string | undefined>(
    searchParams.get('listing_market') ?? undefined,
  );
  const [board, setBoard] = useState<string | undefined>(
    searchParams.get('board') ?? undefined,
  );
  const [exchange, setExchange] = useState<string | undefined>(
    searchParams.get('exchange') ?? undefined,
  );
  const [page, setPage] = useState(() => {
    const raw = searchParams.get('page');
    return raw ? Number(raw) : 1;
  });

  const debouncedSearch = useDebounce(search, 300);

  // Sync URL params when filters change.
  useEffect(() => {
    const next: Record<string, string> = {};
    if (search) next.q = search;
    if (market) next.market = market;
    if (category) next.category = category;
    if (instrumentType) next.type = instrumentType;
    if (subCategory) next.sub_category = subCategory;
    if (sector) next.sector = sector;
    if (industry) next.industry = industry;
    if (country) next.country = country;
    if (manager) next.manager = manager;
    if (underlyingIndex) next.underlying_index = underlyingIndex;
    if (currency) next.currency = currency;
    if (isQdii != null) next.is_qdii = String(isQdii);
    if (status) next.status = status;
    if (minFundSize != null) next.min_fund_size = String(minFundSize);
    if (maxFundSize != null) next.max_fund_size = String(maxFundSize);
    if (listingMarket) next.listing_market = listingMarket;
    if (board) next.board = board;
    if (exchange) next.exchange = exchange;
    if (page !== 1) next.page = String(page);
    setSearchParams(next, { replace: true });
  }, [
    search, market, category, instrumentType, subCategory, sector, industry,
    country, manager, underlyingIndex, currency, isQdii, status, minFundSize,
    maxFundSize, listingMarket, board, exchange, page, setSearchParams,
  ]);

  const listParams = {
    search: debouncedSearch || undefined,
    market,
    category,
    instrument_type: instrumentType,
    sub_category: subCategory,
    sector,
    industry,
    country,
    manager,
    underlying_index: underlyingIndex,
    currency,
    is_qdii: isQdii,
    status,
    min_fund_size: minFundSize,
    max_fund_size: maxFundSize,
    listing_market: listingMarket,
    board,
    exchange,
    page,
    page_size: PAGE_SIZE,
  };

  const { data, isLoading, dataUpdatedAt, isFetching } = useInstrumentList(listParams);

  // Stage-2 visibility. Coarse filters (市场 / 类型) decide which advanced
  // groups are exposed. When only one of (market, type) is set we show every
  // type for that market (or every market for that type) — i.e. an
  // unset coarse filter is a wildcard, not a hard block.
  const isA = market === 'A股';
  const isUS = market === 'US';
  const isHK = market === 'HK';
  const isCryptoType = instrumentType === 'CRYPTO';
  const showA_shareEtfFilters =
    isA && (!instrumentType || instrumentType === 'ETF');
  const showA_shareStockFilters =
    isA && (!instrumentType || instrumentType === 'STOCK');
  const showUsFilters =
    isUS && (!instrumentType || instrumentType === 'ETF' || instrumentType === 'STOCK');
  const showHkFilters = isHK && (!instrumentType || instrumentType === 'STOCK' || instrumentType === 'ETF');
  const showCryptoFilters =
    isCryptoType || (!market && !instrumentType);
  const stage2Summary = useMemo(() => {
    const parts: string[] = [];
    if (market) parts.push(market);
    if (instrumentType) parts.push(instrumentType);
    return parts.join(' · ');
  }, [market, instrumentType]);

  // Cascade filters for facet options: all current selections except the facet
  // itself are sent so each dropdown only shows values that still yield results.
  const cascadeFilters = {
    market,
    category,
    instrument_type: instrumentType,
    sub_category: subCategory,
    sector,
    industry,
    country,
    manager,
    underlying_index: underlyingIndex,
    currency,
    is_qdii: isQdii,
    status,
    exchange,
  };
  const { data: categories } = useInstrumentCategories(cascadeFilters);
  const { data: sectors } = useInstrumentSectors(cascadeFilters);
  const { data: industries } = useInstrumentIndustries(cascadeFilters);
  const { data: subCategories } = useInstrumentSubCategories(cascadeFilters);
  const { data: managers } = useInstrumentManagers(cascadeFilters);
  const { data: currencies } = useInstrumentCurrencies(cascadeFilters);
  const { data: countries } = useInstrumentCountries(cascadeFilters);
  const { data: underlyingIndices } = useInstrumentUnderlyingIndices(cascadeFilters);
  const { data: markets } = useInstrumentMarkets();
  // Board / listing-market facets only matter for A-share stocks; querying
  // them for every type is cheap because the backend filters by market.
  const { data: listingMarkets } = useInstrumentListingMarkets(cascadeFilters);
  const { data: boards } = useInstrumentBoards(cascadeFilters);

  // Helpers for building dropdown options and deciding visibility.
  const toOptions = (values?: string[] | null) =>
    (values || [])
      .filter((v): v is string => v != null && v !== '')
      .map((v) => ({ label: v, value: v }));
  const hasOptions = (values?: string[] | null) => toOptions(values).length > 0;
  // QDII only makes sense for ETFs; hide it for other instrument types.
  const showQdiiFilter = !instrumentType || instrumentType === 'ETF';

  // Clear selected facet values if they no longer exist under the current
  // market / instrument type filters.
  useEffect(() => {
    if (category && categories && !categories.includes(category)) setCategory(undefined);
  }, [categories, category]);
  useEffect(() => {
    if (subCategory && subCategories && !subCategories.includes(subCategory)) setSubCategory(undefined);
  }, [subCategories, subCategory]);
  useEffect(() => {
    if (sector && sectors && !sectors.includes(sector)) setSector(undefined);
  }, [sectors, sector]);
  useEffect(() => {
    if (industry && industries && !industries.includes(industry)) setIndustry(undefined);
  }, [industries, industry]);
  useEffect(() => {
    if (country && countries && !countries.includes(country)) setCountry(undefined);
  }, [countries, country]);
  useEffect(() => {
    if (manager && managers && !managers.includes(manager)) setManager(undefined);
  }, [managers, manager]);
  useEffect(() => {
    if (currency && currencies && !currencies.includes(currency)) setCurrency(undefined);
  }, [currencies, currency]);
  useEffect(() => {
    if (underlyingIndex && underlyingIndices && !underlyingIndices.includes(underlyingIndex)) setUnderlyingIndex(undefined);
  }, [underlyingIndices, underlyingIndex]);
  useEffect(() => {
    // QDII only applies to ETFs; clear it when the type is set to something else.
    if (instrumentType && instrumentType !== 'ETF' && isQdii != null) setIsQdii(undefined);
  }, [instrumentType, isQdii]);
  useEffect(() => {
    // Exchange filter only applies to US equities.
    if (market && market !== 'US' && exchange != null) setExchange(undefined);
  }, [market, exchange]);
  useEffect(() => {
    // A-share listing market / board only make sense for A股.
    if (market && market !== 'A股') {
      if (listingMarket != null) setListingMarket(undefined);
      if (board != null) setBoard(undefined);
    }
  }, [market, listingMarket, board]);

  const handleReset = () => {
    setSearch('');
    setMarket(undefined);
    setCategory(undefined);
    setInstrumentType(undefined);
    setSubCategory(undefined);
    setSector(undefined);
    setIndustry(undefined);
    setCountry(undefined);
    setManager(undefined);
    setUnderlyingIndex(undefined);
    setCurrency(undefined);
    setIsQdii(undefined);
    setStatus(undefined);
    setMinFundSize(undefined);
    setMaxFundSize(undefined);
    setListingMarket(undefined);
    setBoard(undefined);
    setExchange(undefined);
    setPage(1);
  };

  // Stream live prices for the current page only. The backend page_size is
  // already capped at 50, so this keeps the SSE query param list small and
  // avoids re-subscribing on every keystroke in the search box.
  const pageCodes = useMemo(
    () => (data?.items || []).map((it: { code: string }) => it.code).filter(Boolean),
    [data?.items]
  );
  const { latest: liveLatest } = useMarketStream(pageCodes);

  const tableWrapClass = 'ad-table-scroll ad-table-sticky';

  const columns = [
    {
      title: '标的',
      render: (_: unknown, record: any) => (
        <InstrumentCodeTag code={record.code} name={record.name} name_zh={record.name_zh} />
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      render: (v: string) => v ? <ThemeTag>{v}</ThemeTag> : NULL_PLACEHOLDER,
    },
    {
      title: '市场',
      dataIndex: 'market',
      width: 80,
      render: (v: string) => (
        <span className="tabular-nums mobile-list-item__meta font-mono">{v}</span>
      ),
    },
    {
      title: '上市地',
      dataIndex: 'listing_market',
      width: 80,
      render: (v: string | null | undefined) => {
        if (!v) return <span className="mobile-list-item__meta">{NULL_PLACEHOLDER}</span>;
        return <ThemeTag title={`上市市场: ${v}`}>{v}</ThemeTag>;
      },
    },
    {
      title: '板块',
      dataIndex: 'board',
      width: 90,
      render: (v: string | null | undefined) => {
        if (!v) return <span className="mobile-list-item__meta">{NULL_PLACEHOLDER}</span>;
        const variantMap: Record<string, 'default' | 'accent' | 'warning'> = {
          主板: 'default',
          创业板: 'accent',
          科创板: 'accent',
          北交所: 'warning',
        };
        return (
          <ThemeTag variant={variantMap[v] || 'default'} title={`所属板块: ${v}`}>
            {v}
          </ThemeTag>
        );
      },
    },
    {
      title: '类型',
      dataIndex: 'instrument_type',
      width: 70,
      render: (v: string) => {
        const labelMap: Record<string, string> = {
          STOCK: '个股',
          CRYPTO: '数字货币',
          ETF: 'ETF',
        };
        const variantMap: Record<string, 'accent' | 'default'> = {
          STOCK: 'accent',
          CRYPTO: 'accent',
          ETF: 'default',
        };
        return <ThemeTag variant={variantMap[v] || 'default'}>{labelMap[v] || v}</ThemeTag>;
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 80,
      render: (v: string) => {
        const variantMap: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
          active: 'success',
          listed: 'success',
          suspended: 'warning',
          delisted: 'error',
        };
        const labelMap: Record<string, string> = {
          active: '上市',
          listed: '上市',
          suspended: '停牌',
          delisted: '退市',
        };
        return (
          <ThemeTag variant={variantMap[v] || 'default'}>
            {labelMap[v] || v || NULL_PLACEHOLDER}
          </ThemeTag>
        );
      },
    },
    {
      title: '管理公司',
      dataIndex: 'fund_manager',
      render: (v: string) => v ? (
        <span className="ad-text-secondary">{v}</span>
      ) : NULL_PLACEHOLDER,
    },
    {
      title: '跟踪指数',
      dataIndex: 'underlying_index',
      render: (v: string) => v ? (
        <span className="mobile-list-item__meta instrument-index-cell">
          {v}
        </span>
      ) : NULL_PLACEHOLDER,
    },
    {
      title: '规模',
      dataIndex: 'fund_size',
      sorter: (a: any, b: any) => (a.fund_size ?? -Infinity) - (b.fund_size ?? -Infinity),
      render: (v: number, record: any) => {
        // For US stocks, show market cap in USD; for ETFs show fund size
        if (record.market_cap) {
          const cap = record.market_cap;
          if (cap >= 1e12) return <span className="tabular-nums mobile-list-item__value">{(cap / 1e12).toFixed(2)}T</span>;
          if (cap >= 1e9) return <span className="tabular-nums mobile-list-item__value">{(cap / 1e9).toFixed(1)}B</span>;
          if (cap >= 1e6) return <span className="tabular-nums mobile-list-item__value">{(cap / 1e6).toFixed(1)}M</span>;
        }
        if (v) return (
          <span className="tabular-nums mobile-list-item__value">
            {(v / 1e8).toFixed(1)}亿
          </span>
        );
        return NULL_PLACEHOLDER;
      },
      width: 110,
    },
    {
      title: '近 30 日',
      key: 'sparkline_30d',
      width: 100,
      render: (_: unknown, record: any) => <SparklineCell code={record.code} />,
    },
    {
      title: (
        <Tooltip title="最新日收盘价，非 tick 级实时行情">
          <span>最新价</span>
        </Tooltip>
      ),
      key: 'live_price',
      width: 110,
      sorter: (a: any, b: any) => {
        const priceA = liveLatest[a.code]?.price ?? -Infinity;
        const priceB = liveLatest[b.code]?.price ?? -Infinity;
        return priceA - priceB;
      },
      render: (_: unknown, record: any) => (
        <LivePriceCell code={record.code} tick={liveLatest[record.code]} />
      ),
    },
  ];

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="全市场"
        title="标的列表"
        description="浏览和搜索全市场标的，按市场、分类、类型筛选"
        extra={<LastUpdated at={dataUpdatedAt} loading={isFetching && !data} />}
      />

      <Panel variant="default" padding="md">
        <FilterToolbar
          title="筛选条件"
          total={`共 ${data?.total || 0} 只`}
          extra={
          <Button icon={<ReloadOutlined />} onClick={handleReset}>
            重置条件
          </Button>
        }
      >
        <div className="instrument-filter-groups">
          {/* Stage 1 — coarse filters (always visible).
              Picking 市场 + 类型 narrows the universe and decides which
              stage-2 (advanced) filters get exposed below. */}
          <div className="instrument-filter-group">
            <div className="instrument-filter-group__title">基础筛选</div>
            <Row gutter={[16, 12]}>
              <Col xs={12} sm={8} md={6}>
                <Input
                  placeholder="搜索标的代码或名称"
                  allowClear
                  className="ad-w-full"
                  prefix={<SearchOutlined className="ad-icon-tertiary" />}
                  value={search}
                  onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                />
              </Col>
              <Col xs={12} sm={8} md={6}>
                <Select
                  placeholder="市场"
                  allowClear
                  className="ad-w-full"
                  options={toOptions(markets)}
                  value={market}
                  onChange={(v) => { setMarket(v); setPage(1); }}
                />
              </Col>
              <Col xs={12} sm={8} md={6}>
                <Select
                  placeholder="类型"
                  allowClear
                  className="ad-w-full"
                  options={[
                    { label: 'ETF', value: 'ETF' },
                    { label: '个股', value: 'STOCK' },
                    { label: '数字货币', value: 'CRYPTO' },
                  ]}
                  value={instrumentType}
                  onChange={(v) => { setInstrumentType(v); setPage(1); }}
                />
              </Col>
              {hasOptions(countries) && (
                <Col xs={12} sm={8} md={6}>
                  <Select
                    placeholder="国家"
                    allowClear
                    className="ad-w-full"
                    options={toOptions(countries)}
                    value={country}
                    onChange={(v) => { setCountry(v); setPage(1); }}
                  />
                </Col>
              )}
              {hasOptions(currencies) && (
                <Col xs={12} sm={8} md={6}>
                  <Select
                    placeholder="币种"
                    allowClear
                    className="ad-w-full"
                    options={toOptions(currencies)}
                    value={currency}
                    onChange={(v) => { setCurrency(v); setPage(1); }}
                  />
                </Col>
              )}
            </Row>
          </div>

          {/* Stage 2 — fine / cascade filters. Only shown when at least one
              of (市场, 类型) is selected, so users do not see a flat grid of
              mostly-irrelevant dropdowns. Each filter is gated by a prerequisite
              and only renders values that still yield rows given the
              parent's other selections (cascade context is sent on every
              facet call). */}
          {(market || instrumentType) && (
            <Collapse
              ghost
              defaultActiveKey={['advanced']}
              items={[
                {
                  key: 'advanced',
                  label: (
                    <span className="ad-text-secondary">
                      高级筛选
                      {stage2Summary ? (
                        <span className="ad-text-tertiary ad-ml-2">{stage2Summary}</span>
                      ) : null}
                    </span>
                  ),
                  children: (
                    <div className="instrument-filter-groups">
                      {/* A股 ETF — 分类 / 行业 / 板块 / 跟踪指数 / 管理公司 / 上市板块 */}
                      {showA_shareEtfFilters && (
                        <div className="instrument-filter-group">
                          <div className="instrument-filter-group__title">A 股 ETF</div>
                          <Row gutter={[16, 12]}>
                            {hasOptions(categories) && (
                              <Col xs={12} sm={8} md={6}>
                                <Select
                                  placeholder="分类"
                                  allowClear
                                  className="ad-w-full"
                                  options={toOptions(categories)}
                                  value={category}
                                  onChange={(v) => { setCategory(v); setPage(1); }}
                                />
                              </Col>
                            )}
                            {hasOptions(industries) && (
                              <Col xs={12} sm={8} md={6}>
                                <Select
                                  placeholder="行业"
                                  allowClear
                                  className="ad-w-full"
                                  options={toOptions(industries)}
                                  value={industry}
                                  onChange={(v) => { setIndustry(v); setPage(1); }}
                                />
                              </Col>
                            )}
                            {hasOptions(sectors) && (
                              <Col xs={12} sm={8} md={6}>
                                <Select
                                  placeholder="板块"
                                  allowClear
                                  className="ad-w-full"
                                  options={toOptions(sectors)}
                                  value={sector}
                                  onChange={(v) => { setSector(v); setPage(1); }}
                                />
                              </Col>
                            )}
                            {hasOptions(underlyingIndices) && (
                              <Col xs={12} sm={8} md={6}>
                                <Select
                                  placeholder="跟踪指数"
                                  allowClear
                                  className="ad-w-full"
                                  options={toOptions(underlyingIndices)}
                                  value={underlyingIndex}
                                  onChange={(v) => { setUnderlyingIndex(v); setPage(1); }}
                                />
                              </Col>
                            )}
                            {hasOptions(managers) && (
                              <Col xs={12} sm={8} md={6}>
                                <Select
                                  placeholder="管理公司"
                                  allowClear
                                  className="ad-w-full"
                                  options={toOptions(managers)}
                                  value={manager}
                                  onChange={(v) => { setManager(v); setPage(1); }}
                                />
                              </Col>
                            )}
                            {hasOptions(listingMarkets) && (
                              <Col xs={12} sm={8} md={6}>
                                <Select
                                  placeholder="上市地"
                                  allowClear
                                  className="ad-w-full"
                                  options={toOptions(listingMarkets)}
                                  value={listingMarket}
                                  onChange={(v) => { setListingMarket(v); setPage(1); }}
                                />
                              </Col>
                            )}
                            {hasOptions(boards) && (
                              <Col xs={12} sm={8} md={6}>
                                <Select
                                  placeholder="上市板块"
                                  allowClear
                                  className="ad-w-full"
                                  options={toOptions(boards)}
                                  value={board}
                                  onChange={(v) => { setBoard(v); setPage(1); }}
                                />
                              </Col>
                            )}
                          </Row>
                        </div>
                      )}

                      {/* A股 STOCK — 行业 / 板块 / 上市板块 / 状态 */}
                      {showA_shareStockFilters && (
                        <div className="instrument-filter-group">
                          <div className="instrument-filter-group__title">A 股个股</div>
                          <Row gutter={[16, 12]}>
                            {hasOptions(industries) && (
                              <Col xs={12} sm={8} md={6}>
                                <Select
                                  placeholder="行业"
                                  allowClear
                                  className="ad-w-full"
                                  options={toOptions(industries)}
                                  value={industry}
                                  onChange={(v) => { setIndustry(v); setPage(1); }}
                                />
                              </Col>
                            )}
                            {hasOptions(sectors) && (
                              <Col xs={12} sm={8} md={6}>
                                <Select
                                  placeholder="板块"
                                  allowClear
                                  className="ad-w-full"
                                  options={toOptions(sectors)}
                                  value={sector}
                                  onChange={(v) => { setSector(v); setPage(1); }}
                                />
                              </Col>
                            )}
                            {hasOptions(listingMarkets) && (
                              <Col xs={12} sm={8} md={6}>
                                <Select
                                  placeholder="上市地"
                                  allowClear
                                  className="ad-w-full"
                                  options={toOptions(listingMarkets)}
                                  value={listingMarket}
                                  onChange={(v) => { setListingMarket(v); setPage(1); }}
                                />
                              </Col>
                            )}
                            {hasOptions(boards) && (
                              <Col xs={12} sm={8} md={6}>
                                <Select
                                  placeholder="上市板块"
                                  allowClear
                                  className="ad-w-full"
                                  options={toOptions(boards)}
                                  value={board}
                                  onChange={(v) => { setBoard(v); setPage(1); }}
                                />
                              </Col>
                            )}
                            <Col xs={12} sm={8} md={6}>
                              <Select
                                placeholder="状态"
                                allowClear
                                className="ad-w-full"
                                options={STATUS_OPTIONS}
                                value={status}
                                onChange={(v) => { setStatus(v); setPage(1); }}
                              />
                            </Col>
                          </Row>
                        </div>
                      )}

                      {/* 美股 — 行业 / 交易所 / 状态 */}
                      {showUsFilters && (
                        <div className="instrument-filter-group">
                          <div className="instrument-filter-group__title">美股</div>
                          <Row gutter={[16, 12]}>
                            {hasOptions(industries) && (
                              <Col xs={12} sm={8} md={6}>
                                <Select
                                  placeholder="行业 (GICS)"
                                  allowClear
                                  className="ad-w-full"
                                  options={toOptions(industries)}
                                  value={industry}
                                  onChange={(v) => { setIndustry(v); setPage(1); }}
                                />
                              </Col>
                            )}
                            <Col xs={12} sm={8} md={6}>
                              <Select
                                placeholder="交易所 (NYSE / NASDAQ)"
                                allowClear
                                className="ad-w-full"
                                options={[
                                  { label: 'NYSE', value: 'NYSE' },
                                  { label: 'NASDAQ', value: 'NASDAQ' },
                                ]}
                                value={exchange}
                                onChange={(v) => { setExchange(v); setPage(1); }}
                              />
                            </Col>
                            <Col xs={12} sm={8} md={6}>
                              <Select
                                placeholder="状态"
                                allowClear
                                className="ad-w-full"
                                options={STATUS_OPTIONS}
                                value={status}
                                onChange={(v) => { setStatus(v); setPage(1); }}
                              />
                            </Col>
                          </Row>
                        </div>
                      )}

                      {/* 港股 — 行业 / 状态 */}
                      {showHkFilters && (
                        <div className="instrument-filter-group">
                          <div className="instrument-filter-group__title">港股</div>
                          <Row gutter={[16, 12]}>
                            {hasOptions(industries) && (
                              <Col xs={12} sm={8} md={6}>
                                <Select
                                  placeholder="行业"
                                  allowClear
                                  className="ad-w-full"
                                  options={toOptions(industries)}
                                  value={industry}
                                  onChange={(v) => { setIndustry(v); setPage(1); }}
                                />
                              </Col>
                            )}
                            <Col xs={12} sm={8} md={6}>
                              <Select
                                placeholder="状态"
                                allowClear
                                className="ad-w-full"
                                options={STATUS_OPTIONS}
                                value={status}
                                onChange={(v) => { setStatus(v); setPage(1); }}
                              />
                            </Col>
                          </Row>
                        </div>
                      )}

                      {/* CRYPTO — 赛道 (分类) / 链 (子分类) */}
                      {showCryptoFilters && (
                        <div className="instrument-filter-group">
                          <div className="instrument-filter-group__title">数字货币</div>
                          <Row gutter={[16, 12]}>
                            {hasOptions(categories) && (
                              <Col xs={12} sm={8} md={6}>
                                <Select
                                  placeholder="赛道 (Layer1 / DeFi / Meme / ...)"
                                  allowClear
                                  className="ad-w-full"
                                  options={toOptions(categories)}
                                  value={category}
                                  onChange={(v) => { setCategory(v); setPage(1); }}
                                />
                              </Col>
                            )}
                            {hasOptions(subCategories) && (
                              <Col xs={12} sm={8} md={6}>
                                <Select
                                  placeholder="链 (Ethereum / Solana / BSC / ...)"
                                  allowClear
                                  className="ad-w-full"
                                  options={toOptions(subCategories)}
                                  value={subCategory}
                                  onChange={(v) => { setSubCategory(v); setPage(1); }}
                                />
                              </Col>
                            )}
                          </Row>
                        </div>
                      )}

                      {/* Size — applies to ETFs only */}
                      {showQdiiFilter && (
                        <div className="instrument-filter-group">
                          <div className="instrument-filter-group__title">规模 / QDII</div>
                          <Row gutter={[16, 12]}>
                            <Col xs={12} sm={8} md={6}>
                              <Select
                                placeholder="QDII"
                                allowClear
                                className="ad-w-full"
                                options={QDII_OPTIONS}
                                value={isQdii}
                                onChange={(v) => { setIsQdii(v); setPage(1); }}
                              />
                            </Col>
                            <Col xs={12} sm={8} md={6}>
                              <InputNumber
                                placeholder="最小规模 (元)"
                                className="ad-w-full"
                                value={minFundSize}
                                onChange={(v) => { setMinFundSize(v ?? undefined); setPage(1); }}
                              />
                            </Col>
                            <Col xs={12} sm={8} md={6}>
                              <InputNumber
                                placeholder="最大规模 (元)"
                                className="ad-w-full"
                                value={maxFundSize}
                                onChange={(v) => { setMaxFundSize(v ?? undefined); setPage(1); }}
                              />
                            </Col>
                          </Row>
                        </div>
                      )}
                    </div>
                  ),
                },
              ]}
            />
          )}
        </div>
        </FilterToolbar>

        {isMobile ? (
          isLoading ? (
            <Skeleton active paragraph={{ rows: 10 }} />
          ) : (data?.items?.length || 0) === 0 ? (
            <EmptyState
              title="没有符合条件的标的"
              description="尝试调整上方筛选条件，或清空搜索关键词查看全部标的"
            />
          ) : (
          /* Mobile: card-style list */
          <List
            className="ad-list-compact"
            dataSource={data?.items || []}
            renderItem={(item: any) => (
              <div
                onClick={() => navigate(`/instruments/${item.code}`)}
                className="mobile-list-item"
              >
                <div className="mobile-list-item__row">
                  <div className="mobile-list-item__main">
                    <InstrumentCodeTag code={item.code} name={item.name} name_zh={item.name_zh} />
                  </div>
                  <div className="mobile-list-item__metrics">
                    <LivePriceCell code={item.code} tick={liveLatest[item.code]} />
                    <span className="tabular-nums mobile-list-item__value">
                      {item.fund_size ? `${(item.fund_size / 1e8).toFixed(1)}亿` : NULL_PLACEHOLDER}
                    </span>
                  </div>
                </div>
                <div className="mobile-list-item__tags">
                  {item.category && (
                    <ThemeTag>{item.category}</ThemeTag>
                  )}
                  {item.market && (
                    <ThemeTag>{item.market}</ThemeTag>
                  )}
                  {item.listing_market && (
                    <ThemeTag title={`上市市场: ${item.listing_market}`}>
                      {item.listing_market}
                    </ThemeTag>
                  )}
                  {item.board && (
                    <ThemeTag
                      variant={
                        item.board === '创业板' || item.board === '科创板'
                          ? 'accent'
                          : item.board === '北交所'
                            ? 'warning'
                            : 'default'
                      }
                      title={`所属板块: ${item.board}`}
                    >
                      {item.board}
                    </ThemeTag>
                  )}
                  {item.fund_manager && (
                    <span className="mobile-list-item__meta">{item.fund_manager}</span>
                  )}
                </div>
              </div>
            )}
            pagination={{
              current: page,
              pageSize: 50,
              total: data?.total || 0,
              onChange: setPage,
              showSizeChanger: false,
              className: 'mobile-list-pagination',
            }}
          />
          )
        ) : (
          /* Desktop: table view */
          <div className={tableWrapClass}>
            <Table
              dataSource={data?.items || []}
              columns={columns}
              rowKey="code"
              loading={isLoading}
              size="small"
              scroll={{ x: 'max-content' }}
              pagination={{
                current: page,
                pageSize: 50,
                total: data?.total || 0,
                onChange: setPage,
                showSizeChanger: true,
              }}
              locale={{
                emptyText: <EmptyState title="暂无数据" />,
              }}
              onRow={(record) => ({
                onClick: () => navigate(`/instruments/${record.code}`),
              })}
            />
          </div>
        )}
      </Panel>
    </PageShell>
  );
}
