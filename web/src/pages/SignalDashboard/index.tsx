import './styles.css';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Table, Select, Row, Col, Space, Slider, Tooltip, message } from 'antd';
import {
  CaretUpOutlined,
  CaretDownOutlined,
  MinusOutlined,
  StarFilled,
  LinkOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import PageShell from '@/components/PageShell';
import PageHeader from '@/components/PageHeader';
import Panel from '@/components/Panel';
import FilterToolbar from '@/components/FilterToolbar';
import EmptyState from '@/components/EmptyState';
import ThemeTag, { ThemeTagVariant } from '@/components/ThemeTag';
import InstrumentCodeTag from '@/components/InstrumentCodeTag';
import HelpTrigger from '@/components/HelpTrigger';
import ContextHint from '@/components/ContextHint';
import DataFreshnessHint from '@/components/DataFreshnessHint';
import SignalDetailDrawer from '@/components/SignalDetailDrawer';
import ExportButton from '@/components/ExportButton';
import { useSignals } from '@/hooks/useSignals';
import { useAIHelp } from '@/hooks/useAIHelp';
import { clickableRow, clickableProps } from '@/utils/a11y';
import { buildSignalDashboardContext } from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';
import { formatRelative, formatDateTime } from '@/utils/datetime';
import { newsApi, signalApi } from '@/api';
import type { Signal } from '@/types/signal';
import type { EventSignal, NewsMarket } from '@/types/news';

const SIGNAL_VARIANTS: Record<string, ThemeTagVariant> = {
  BUY: 'rise',
  SELL: 'fall',
  HOLD: 'default',
};

const SIGNAL_LABELS: Record<string, string> = {
  BUY: '买入',
  SELL: '卖出',
  HOLD: '持有',
};

/**
 * WCAG SC 1.4.1 (Use of Color): BUY/SELL/HOLD must not rely on color alone.
 * Each variant gets a distinct icon (up / down / minus) that mirrors the
 * semantic direction; combined with the explicit text label, colorblind
 * users still get the signal from shape + words.
 */
const SIGNAL_ICONS: Record<string, React.ReactNode> = {
  BUY: <CaretUpOutlined aria-hidden="true" className="signal-dashboard__type-icon" />,
  SELL: <CaretDownOutlined aria-hidden="true" className="signal-dashboard__type-icon" />,
  HOLD: <MinusOutlined aria-hidden="true" className="signal-dashboard__type-icon" />,
};

const FAMILY_LABELS: Record<string, string> = {
  trend_following: '趋势跟踪',
  mean_reversion: '均值回归',
  momentum: '动量',
  volatility: '波动率',
  volume: '成交量',
  composite: '复合因子',
  cross_sectional: '横截面',
  event: '事件驱动',
};

/** Event category display labels (mirrors backend LLM prompt taxonomy). */
const EVENT_CATEGORY_LABELS: Record<string, string> = {
  earnings: '财报',
  'm&a': '并购',
  product: '产品',
  macro: '宏观',
  regulation: '监管',
  guidance: '指引',
  analyst: '分析师',
  legal: '法律',
  rumor: '传闻',
  geopolitics: '地缘',
  central_bank: '央行',
  election: '选举',
  trade_war: '贸易战',
  sanction: '制裁',
  other: '其他',
};

const EVENT_CATEGORY_OPTIONS = [
  { label: '全部', value: 'all' },
  ...Object.entries(EVENT_CATEGORY_LABELS).map(([value, label]) => ({ label, value })),
];

const MARKET_OPTIONS: { label: string; value: NewsMarket | 'all' }[] = [
  { label: '全部', value: 'all' },
  { label: 'A股', value: 'cn_a' },
  { label: '美股', value: 'us' },
  { label: '加密', value: 'crypto' },
];

const DIRECTION_VARIANTS: Record<EventSignal['signal_direction'], ThemeTagVariant> = {
  bullish: 'rise',
  bearish: 'fall',
  neutral: 'neutral',
};

const DIRECTION_ICONS: Record<EventSignal['signal_direction'], React.ReactNode> = {
  bullish: <CaretUpOutlined aria-hidden="true" className="signal-dashboard__type-icon" />,
  bearish: <CaretDownOutlined aria-hidden="true" className="signal-dashboard__type-icon" />,
  neutral: <MinusOutlined aria-hidden="true" className="signal-dashboard__type-icon" />,
};

const DIRECTION_LABELS: Record<EventSignal['signal_direction'], string> = {
  bullish: '看多',
  bearish: '看空',
  neutral: '中性',
};

function formatSummary(value: string | null, max = 120): string {
  if (!value) return '';
  const trimmed = value.replace(/\s+/g, ' ').trim();
  return trimmed.length > max ? `${trimmed.slice(0, max)}…` : trimmed;
}

export default function SignalDashboard() {
  const navigate = useNavigate();
  const { data: signals, isLoading, dataUpdatedAt } = useSignals();
  const { open } = useAIHelp();
  const [familyFilter, setFamilyFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [selectedSignal, setSelectedSignal] = useState<Signal | null>(null);

  // Event signals state and filters
  const [eventCategoryFilter, setEventCategoryFilter] = useState<string>('all');
  const [eventMarketFilter, setEventMarketFilter] = useState<NewsMarket | 'all'>('all');
  const [eventImportanceMin, setEventImportanceMin] = useState<number>(1);

  const {
    data: eventSignalsData,
    isLoading: eventSignalsLoading,
    dataUpdatedAt: eventSignalsUpdatedAt,
  } = useQuery({
    queryKey: ['news-event-signals', eventMarketFilter, eventCategoryFilter, eventImportanceMin],
    queryFn: async () => {
      const params = {
        days: 7,
        limit: 50,
        market: eventMarketFilter === 'all' ? undefined : eventMarketFilter,
        event_category: eventCategoryFilter === 'all' ? undefined : [eventCategoryFilter],
        importance_min: eventImportanceMin as 1 | 2 | 3 | 4 | 5,
      };
      const res = await newsApi.eventSignals(params);
      return res.data;
    },
    refetchInterval: 60_000,
    staleTime: 60_000,
  });

  const eventSignals: EventSignal[] = eventSignalsData?.items || [];

  const filteredEventSignals = useMemo(() => {
    return eventSignals.filter((item) => {
      if (eventCategoryFilter !== 'all' && item.event_category !== eventCategoryFilter) {
        return false;
      }
      if (eventMarketFilter !== 'all' && item.market !== eventMarketFilter) {
        return false;
      }
      if (item.importance < eventImportanceMin) {
        return false;
      }
      return true;
    });
  }, [eventSignals, eventCategoryFilter, eventMarketFilter, eventImportanceMin]);

  const items: Signal[] = signals?.items || [];

  const filteredItems = useMemo(() => {
    if (typeFilter === 'all' && familyFilter === 'all') {
      return items;
    }
    return items.filter((item) => {
      if (typeFilter !== 'all' && item.signal_type !== typeFilter) {
        return false;
      }
      if (familyFilter !== 'all' && item.strategy_type !== familyFilter) {
        return false;
      }
      return true;
    });
  }, [items, typeFilter, familyFilter]);

  const buyCount = filteredItems.filter((s) => s.signal_type === 'BUY').length;
  const sellCount = filteredItems.filter((s) => s.signal_type === 'SELL').length;
  const holdCount = filteredItems.filter((s) => s.signal_type === 'HOLD').length;

  const handleGenerateSignal = async (signal: EventSignal, symbol: string) => {
    try {
      await signalApi.generate({
        strategy_type: 'event',
        etf_code: symbol,
        event_signal_id: signal.id,
      });
      message.success(`已为 ${symbol} 生成事件驱动信号`);
    } catch (err) {
      message.error('生成信号失败，请稍后重试');
    }
  };

  const columns = [
    { title: '策略ID', dataIndex: 'strategy_id', width: 80, responsive: ['md'] as Array<'md' | 'lg' | 'xl' | 'sm' | 'xs' | 'xxl'>, render: (v: any) => <span className="tabular-nums">{v}</span> },
    {
      title: '标的',
      dataIndex: 'etf_code',
      render: (_: string, record: Signal) => (
        <InstrumentCodeTag code={record.etf_code} name={record.etf_name} name_zh={record.name_zh} />
      ),
    },
    { title: '日期', dataIndex: 'trade_date', responsive: ['sm'] as Array<'sm' | 'md' | 'lg' | 'xl' | 'xs' | 'xxl'> },
    {
      title: '信号',
      dataIndex: 'signal_type',
      render: (v: string) => (
        <ThemeTag variant={SIGNAL_VARIANTS[v]}>
          {/* WCAG SC 1.4.1: icon + text label so meaning isn't color-only */}
          {SIGNAL_ICONS[v]}
          <span>{SIGNAL_LABELS[v] || v}</span>
        </ThemeTag>
      ),
      width: 80,
    },
    { title: '强度', dataIndex: 'strength', width: 80, render: (v: any) => <span className="tabular-nums">{v}</span> },
    {
      title: '',
      key: 'view-instrument',
      width: 80,
      render: (_: unknown, record: Signal) => (
        <span
          role="link"
          tabIndex={0}
          className="signal-dashboard__view-link"
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/instruments/${record.etf_code}`);
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              e.stopPropagation();
              navigate(`/instruments/${record.etf_code}`);
            }
          }}
        >
          查看标的
        </span>
      ),
    },
  ];

  const eventColumns = [
    {
      title: '事件分类',
      dataIndex: 'event_category',
      width: 100,
      render: (v: string) => {
        const label = v ? EVENT_CATEGORY_LABELS[v] || v : '未分类';
        return <ThemeTag variant="accent">{label}</ThemeTag>;
      },
    },
    {
      title: '标题',
      dataIndex: 'title',
      render: (v: string, record: EventSignal) => (
        <span className="signal-dashboard__event-title">
          <LinkOutlined
            className="signal-dashboard__event-link"
            {...clickableProps((e) => {
              e.stopPropagation();
              window.open(record.url, '_blank', 'noopener,noreferrer');
            })}
          />
          <span>{v}</span>
        </span>
      ),
    },
    {
      title: '来源+时间',
      dataIndex: 'source',
      width: 160,
      responsive: ['md'] as Array<'md' | 'lg' | 'xl' | 'sm' | 'xs' | 'xxl'>,
      render: (_: string, record: EventSignal) => (
        <div className="signal-dashboard__event-meta">
          <span>{record.source}</span>
          <Tooltip title={formatDateTime(record.published_at)}>
            <span className="signal-dashboard__event-time">
              {formatRelative(record.published_at)}
            </span>
          </Tooltip>
        </div>
      ),
    },
    {
      title: '重要性',
      dataIndex: 'importance',
      width: 110,
      render: (v: number | null) => {
        const filled = v ? Math.max(0, Math.min(5, v)) : 0;
        return (
          <span className="signal-dashboard__importance" aria-label={`重要性 ${filled} / 5`}>
            {Array.from({ length: 5 }).map((_, i) => (
              <StarFilled
                key={i}
                className={`signal-dashboard__star ${i < filled ? 'signal-dashboard__star--filled' : 'signal-dashboard__star--empty'}`}
                aria-hidden="true"
              />
            ))}
          </span>
        );
      },
    },
    {
      title: '信号方向',
      dataIndex: 'signal_direction',
      width: 90,
      render: (v: EventSignal['signal_direction']) => (
        <ThemeTag variant={DIRECTION_VARIANTS[v]}>
          {DIRECTION_ICONS[v]}
          <span>{DIRECTION_LABELS[v]}</span>
        </ThemeTag>
      ),
    },
    {
      title: '标的',
      dataIndex: 'symbols',
      width: 180,
      render: (symbols: EventSignal['symbols']) => (
        <Space size="small" wrap className="signal-dashboard__symbols">
          {symbols.length > 0 ? (
            symbols.map((s) => (
              <span
                key={s.symbol}
                className="signal-dashboard__symbol-wrapper"
                {...clickableProps((e) => {
                  e.stopPropagation();
                  navigate(`/instruments/${s.symbol}`);
                })}
              >
                <InstrumentCodeTag
                  code={s.symbol}
                  name={s.name}
                  name_zh={s.name_zh}
                />
              </span>
            ))
          ) : (
            <span className="signal-dashboard__no-symbol">—</span>
          )}
        </Space>
      ),
    },
    {
      title: '摘要',
      dataIndex: 'summary',
      responsive: ['lg'] as Array<'lg' | 'xl' | 'md' | 'sm' | 'xs' | 'xxl'>,
      render: (v: string | null) => {
        const text = formatSummary(v);
        return (
          <Tooltip title={v || ''}>
            <span className="signal-dashboard__event-summary">{text || '—'}</span>
          </Tooltip>
        );
      },
    },
    {
      title: '',
      key: 'generate-signal',
      width: 80,
      render: (_: unknown, record: EventSignal) => {
        const firstSymbol = record.symbols[0]?.symbol;
        return (
          <span
            role="button"
            tabIndex={0}
            className="signal-dashboard__generate-link"
            {...clickableProps((e) => {
              e.stopPropagation();
              if (firstSymbol) {
                handleGenerateSignal(record, firstSymbol);
              } else {
                message.warning('该事件未关联标的');
              }
            })}
          >
            <ThunderboltOutlined /> 生成
          </span>
        );
      },
    },
  ];

  const handleOpenHelp = () => {
    open({
      pageType: 'signal_dashboard',
      pageTitle: '交易信号',
      contextData: buildSignalDashboardContext(filteredItems, columns),
      quickQuestions: getQuickQuestions('signal_dashboard'),
    });
  };

  const familyOptions = [
    { label: '全部家族', value: 'all' },
    ...Object.entries(FAMILY_LABELS).map(([key, label]) => ({ label, value: key })),
  ];

  const typeOptions = [
    { label: '全部信号', value: 'all' },
    { label: '买入', value: 'BUY' },
    { label: '卖出', value: 'SELL' },
    { label: '持有', value: 'HOLD' },
  ];

  return (
    <PageShell maxWidth="wide">
      <PageHeader
        eyebrow="交易"
        title="信号看板"
        description="查看最新交易信号汇总，监控买入、卖出、持有信号分布"
        extra={<DataFreshnessHint at={dataUpdatedAt} />}
      />

      <div className="ad-kpi-strip ad-kpi-strip--cols-3 ad-section">
        {[
          { title: '买入信号', value: buyCount, color: 'rise' },
          { title: '卖出信号', value: sellCount, color: 'fall' },
          { title: '持有信号', value: holdCount, color: 'primary' },
        ].map((m) => (
          <div key={m.title} className="ad-kpi-cell">
            <div className="ad-kpi-cell__label">{m.title}</div>
            <div className={`ad-kpi-cell__value tabular-nums ad-kpi-cell__value--${m.color}`}>
              {m.value}
            </div>
          </div>
        ))}
      </div>

      <div data-onboard="signals-panel">
        <Panel
          variant="default"
          title="最新交易信号"
          extra={
            <Space size="small">
              <HelpTrigger tooltip="AI 解释信号含义" onClick={handleOpenHelp} />
              <ExportButton
                rows={filteredItems as unknown as Record<string, unknown>[]}
                filename={`signals-${
                  typeFilter !== 'all' || familyFilter !== 'all'
                    ? `${typeFilter}-${familyFilter}`
                    : 'all'
                }`}
                headers={['strategy_id', 'etf_code', 'etf_name', 'trade_date', 'signal_type', 'strength', 'strategy_type']}
                successPrefix="已导出信号"
              />
            </Space>
          }
        >
          <ContextHint
            hintId="signal-dashboard-table"
            title="信号怎么读"
            placement="top"
            content={
              <>
                每一行是一次「策略 → 标的」的判断。点击行可跳到策略说明，看为什么生成这条信号；强度 ≥ 70 通常视为强信号。
              </>
            }
          >
            <FilterToolbar total={filteredItems.length}>
              <Row gutter={[12, 12]}>
                <Col xs={12} sm={8} md={6}>
                  <Select
                    value={typeFilter}
                    onChange={setTypeFilter}
                    options={typeOptions}
                    className="ad-w-full"
                  />
                </Col>
                <Col xs={12} sm={8} md={6}>
                  <Select
                    value={familyFilter}
                    onChange={setFamilyFilter}
                    options={familyOptions}
                    placeholder="按策略家族筛选"
                    className="ad-w-full"
                  />
                </Col>
              </Row>
            </FilterToolbar>
          </ContextHint>

          <div className="ad-table-scroll">
            <Table
              dataSource={filteredItems}
              columns={columns}
              rowKey="id"
              size="small"
              loading={isLoading}
              scroll={{ x: 'max-content' }}
              pagination={{ pageSize: 20 }}
              locale={{
                emptyText: <EmptyState title="暂无信号" description="当前没有符合条件的交易信号" />,
              }}
              // Row click opens the signal detail drawer. To navigate to
              // the underlying instrument detail page, use the explicit
              // "查看标的" link in the right-most column.
              onRow={(record) => clickableRow(() => setSelectedSignal(record))}
            />
          </div>
        </Panel>
      </div>

      {/* Event-driven signals panel */}
      <div data-onboard="event-signals-panel" className="signal-dashboard__event-panel">
        <Panel
          variant="default"
          title="事件信号"
          extra={
            <Space size="small">
              <DataFreshnessHint at={eventSignalsUpdatedAt} />
              <ExportButton
                rows={filteredEventSignals as unknown as Record<string, unknown>[]}
                filename={`event-signals-${eventCategoryFilter}-${eventMarketFilter}`}
                headers={['id', 'title', 'source', 'published_at', 'market', 'event_category', 'importance', 'signal_direction']}
                successPrefix="已导出事件信号"
              />
            </Space>
          }
        >
          <ContextHint
            hintId="event-signals-table"
            title="事件信号怎么读"
            placement="top"
            content={
              <>
                事件信号从分类新闻中提炼，标注方向、重要性及受影响标的。每 60 秒自动刷新，点击标题可阅读原文，点击「生成」可为首个关联标的创建事件驱动策略信号。
              </>
            }
          >
            <FilterToolbar total={filteredEventSignals.length}>
              <Row gutter={[12, 12]} align="middle">
                <Col xs={12} sm={8} md={5}>
                  <Select
                    value={eventCategoryFilter}
                    onChange={setEventCategoryFilter}
                    options={EVENT_CATEGORY_OPTIONS}
                    placeholder="事件分类"
                    className="ad-w-full"
                  />
                </Col>
                <Col xs={12} sm={8} md={4}>
                  <Select
                    value={eventMarketFilter}
                    onChange={setEventMarketFilter}
                    options={MARKET_OPTIONS}
                    placeholder="市场"
                    className="ad-w-full"
                  />
                </Col>
                <Col xs={24} sm={8} md={6}>
                  <div className="signal-dashboard__importance-filter">
                    <span className="signal-dashboard__importance-label">重要性 ≥ {eventImportanceMin}</span>
                    <Slider
                      min={1}
                      max={5}
                      step={1}
                      value={eventImportanceMin}
                      onChange={setEventImportanceMin}
                      marks={{ 1: '1', 5: '5' }}
                    />
                  </div>
                </Col>
              </Row>
            </FilterToolbar>
          </ContextHint>

          <div className="ad-table-scroll">
            <Table
              dataSource={filteredEventSignals}
              columns={eventColumns}
              rowKey="id"
              size="small"
              loading={eventSignalsLoading}
              scroll={{ x: 'max-content' }}
              pagination={{ pageSize: 20 }}
              locale={{
                emptyText: (
                  <EmptyState
                    title="暂无事件信号"
                    description="当前没有符合条件的事件驱动信号，请调整筛选或稍后重试"
                  />
                ),
              }}
              onRow={(record) =>
                clickableRow(() => {
                  if (record.url) {
                    window.open(record.url, '_blank', 'noopener,noreferrer');
                  }
                })
              }
            />
          </div>
        </Panel>
      </div>

      <SignalDetailDrawer
        signal={selectedSignal}
        onClose={() => setSelectedSignal(null)}
      />
    </PageShell>
  );
}
