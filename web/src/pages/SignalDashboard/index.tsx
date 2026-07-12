import './styles.css';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Select, Row, Col } from 'antd';
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
import { useSignals } from '@/hooks/useSignals';
import { useAIHelp } from '@/hooks/useAIHelp';
import { buildSignalDashboardContext } from '@/utils/helpContext';
import { getQuickQuestions } from '@/utils/helpPrompts';
import type { Signal } from '@/types/signal';

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

export default function SignalDashboard() {
  const navigate = useNavigate();
  const { data: signals, isLoading, dataUpdatedAt } = useSignals();
  const { open } = useAIHelp();
  const [familyFilter, setFamilyFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [selectedSignal, setSelectedSignal] = useState<Signal | null>(null);

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
      render: (v: string) => <ThemeTag variant={SIGNAL_VARIANTS[v]}>{SIGNAL_LABELS[v] || v}</ThemeTag>,
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
          extra={<HelpTrigger tooltip="AI 解释信号含义" onClick={handleOpenHelp} />}
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
              onRow={(record) => ({
                // Row click opens the signal detail drawer. To navigate to
                // the underlying instrument detail page, use the explicit
                // "查看标的" link in the right-most column.
                onClick: () => setSelectedSignal(record),
              })}
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
