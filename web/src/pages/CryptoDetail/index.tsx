import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Tabs, Row, Col, Statistic, Spin, Alert, Table, List, Radio, Checkbox, Space } from 'antd';
import { RobotOutlined, ReadOutlined } from '@ant-design/icons';
import {
  useCryptoDetail,
  useCryptoHistory,
  useCryptoIndicators,
  useCryptoSignals,
  useCryptoResearch,
} from '@/hooks/useCrypto';
import KLineChart, { DEFAULT_OVERLAYS } from '@/components/KLineChart';
import Panel from '@/components/Panel';
import ThemeTag from '@/components/ThemeTag';
import ReturnTag from '@/components/ReturnTag';
import NewsListPanel from '@/components/NewsListPanel';
import type { DailyBar, ResearchNote } from '@/types/crypto';
import type { OHLCV } from '@/types/instrument';

const TIME_RANGE_OPTIONS = [
  { label: '30日', value: 30 },
  { label: '60日', value: 60 },
  { label: '120日', value: 120 },
  { label: '250日', value: 250 },
];

const INDICATOR_OPTIONS = [
  { label: 'MA5', value: 'ma5' },
  { label: 'MA10', value: 'ma10' },
  { label: 'MA20', value: 'ma20' },
  { label: 'MA60', value: 'ma60' },
  { label: '布林带', value: 'bb' },
  { label: 'RSI14', value: 'rsi' },
  { label: 'MACD', value: 'macd' },
];

const SENTIMENT_LABELS: Record<string, string> = {
  bullish: '看多',
  positive: '看多',
  bearish: '看空',
  negative: '看空',
  neutral: '中性',
};

function toOHLCV(data: DailyBar[]): OHLCV[] {
  return data
    .filter((d) => d.trade_date && d.open != null && d.high != null && d.low != null && d.close != null)
    .map((d) => ({
      trade_date: d.trade_date,
      open: d.open!,
      high: d.high!,
      low: d.low!,
      close: d.close!,
      volume: d.volume ?? 0,
    }));
}

export default function CryptoDetail() {
  const { code } = useParams<{ code: string }>();
  const { data: crypto, isLoading: detailLoading, error: detailError } = useCryptoDetail(code || '');
  const { data: historyData, isLoading: historyLoading } = useCryptoHistory(code || '', { limit: 120 });
  const { data: indicator } = useCryptoIndicators(code || '');
  const { data: signals } = useCryptoSignals(code || '', 20);
  const { data: researchNotes } = useCryptoResearch(code || '', 5);

  const [timeRange, setTimeRange] = useState(120);
  const [overlays, setOverlays] = useState(() => {
    try {
      const saved = localStorage.getItem('crypto-detail-overlays');
      return saved ? { ...DEFAULT_OVERLAYS, ...JSON.parse(saved) } : DEFAULT_OVERLAYS;
    } catch {
      return DEFAULT_OVERLAYS;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem('crypto-detail-overlays', JSON.stringify(overlays));
    } catch {
      // ignore storage errors
    }
  }, [overlays]);

  if (detailLoading) return <Spin size="large" style={{ display: 'block', margin: 'var(--space-9) auto' }} />;
  if (detailError) return <Alert message="加载加密货币详情失败" description={(detailError as Error).message} type="error" style={{ margin: 'var(--space-6)' }} />;
  if (!crypto) return <Alert message="币种不存在" description={`未找到代码为 ${code} 的加密货币`} type="warning" style={{ margin: 'var(--space-6)' }} />;

  const ohlcv = toOHLCV(historyData || []);

  const latestNote: ResearchNote | null = researchNotes?.[0] || null;

  const tabItems = [
    {
      key: 'kline',
      label: 'K线行情',
      children: (
        <div>
          <div style={{ padding: 'var(--space-3) 0', borderBottom: '1px solid var(--border-default)', marginBottom: 'var(--space-4)' }}>
            <Space size="large" wrap>
              <Space>
                <span>时间范围：</span>
                <Radio.Group
                  value={timeRange}
                  onChange={(e) => setTimeRange(e.target.value)}
                  optionType="button"
                  buttonStyle="solid"
                  size="small"
                >
                  {TIME_RANGE_OPTIONS.map((opt) => (
                    <Radio.Button key={opt.value} value={opt.value}>
                      {opt.label}
                    </Radio.Button>
                  ))}
                </Radio.Group>
              </Space>
              <Space>
                <span>技术指标：</span>
                <Checkbox.Group
                  value={Object.entries(overlays)
                    .filter(([, v]) => v)
                    .map(([k]) => k)}
                  onChange={(checkedValues) => {
                    const newOverlays: Record<string, boolean> = {};
                    INDICATOR_OPTIONS.forEach((opt) => {
                      newOverlays[opt.value] = checkedValues.includes(opt.value);
                    });
                    setOverlays(newOverlays as typeof overlays);
                  }}
                >
                  {INDICATOR_OPTIONS.map((opt) => (
                    <Checkbox key={opt.value} value={opt.value}>
                      {opt.label}
                    </Checkbox>
                  ))}
                </Checkbox.Group>
              </Space>
            </Space>
          </div>
          {historyLoading ? (
            <Spin />
          ) : ohlcv.length ? (
            <KLineChart data={ohlcv} overlays={overlays} />
          ) : (
            <Alert message="暂无历史行情数据" type="info" showIcon />
          )}
        </div>
      ),
    },
    {
      key: 'signals',
      label: '交易信号',
      children: (
        <Panel title="最近信号" padding="md">
          <Table
            dataSource={signals || []}
            rowKey="id"
            size="small"
            pagination={{ pageSize: 10 }}
            columns={[
              { title: '日期', dataIndex: 'trade_date' },
              { title: '信号', dataIndex: 'signal_type' },
              { title: '强度', dataIndex: 'strength', render: (v: any) => <span className="tabular-nums">{v}</span> },
            ]}
          />
        </Panel>
      ),
    },
    {
      key: 'news',
      label: (
        <span>
          <ReadOutlined style={{ marginRight: 'var(--space-1)' }} />
          相关新闻
        </span>
      ),
      children: <NewsListPanel symbol={code || ''} limit={15} bare />,
    },
    {
      key: 'ai',
      label: (
        <span>
          <RobotOutlined style={{ marginRight: 'var(--space-1)' }} />
          AI研究
        </span>
      ),
      children: (
        <Panel
          variant="minimal"
          title={<span><ReadOutlined style={{ marginRight: 'var(--space-1-5)' }} />AI 研究笔记</span>}
          padding="md"
        >
          {latestNote ? (
            <div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 'var(--space-2)' }}>
                {latestNote.sentiment && (
                  <ThemeTag
                    variant={
                      latestNote.sentiment === 'bullish' || latestNote.sentiment === 'positive'
                        ? 'rise'
                        : latestNote.sentiment === 'bearish' || latestNote.sentiment === 'negative'
                          ? 'fall'
                          : 'neutral'
                    }
                  >
                    {SENTIMENT_LABELS[latestNote.sentiment] || latestNote.sentiment}
                  </ThemeTag>
                )}
                {latestNote.confidence && (
                  <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                    置信度 {latestNote.confidence}/10
                  </span>
                )}
                <span style={{ fontSize: 11, color: 'var(--text-tertiary)', marginLeft: 'auto' }}>
                  {latestNote.generated_at?.slice(0, 16)}
                </span>
              </div>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                {latestNote.summary}
              </p>
              <p style={{ fontSize: 13, color: 'var(--text-tertiary)', lineHeight: 1.6, marginTop: 'var(--space-3)', whiteSpace: 'pre-wrap' }}>
                {latestNote.content}
              </p>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: 'var(--space-6)', color: 'var(--text-tertiary)' }}>
              <RobotOutlined style={{ fontSize: 32, marginBottom: 'var(--space-2)', display: 'block' }} />
              <p>暂无AI研报</p>
            </div>
          )}

          {researchNotes && researchNotes.length > 1 && (
            <List
              style={{ marginTop: 'var(--space-4)' }}
              dataSource={researchNotes.slice(1)}
              renderItem={(note: ResearchNote) => (
                <List.Item>
                  <List.Item.Meta
                    title={
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{note.note_type}</span>
                        {note.sentiment && (
                          <ThemeTag
                            variant={
                              note.sentiment === 'bullish' || note.sentiment === 'positive'
                                ? 'rise'
                                : note.sentiment === 'bearish' || note.sentiment === 'negative'
                                  ? 'fall'
                                  : 'neutral'
                            }
                          >
                            {SENTIMENT_LABELS[note.sentiment] || note.sentiment}
                          </ThemeTag>
                        )}
                        <span style={{ fontSize: 11, color: 'var(--text-tertiary)', marginLeft: 'auto' }}>
                          {note.generated_at?.slice(0, 16)}
                        </span>
                      </div>
                    }
                    description={
                      <p style={{ fontSize: 12, color: 'var(--text-tertiary)', lineHeight: 1.5, marginTop: 4, whiteSpace: 'pre-wrap' }}>
                        {note.summary}
                      </p>
                    }
                  />
                </List.Item>
              )}
            />
          )}
        </Panel>
      ),
    },
  ];

  return (
    <div>
      <div
        style={{
          borderBottom: '1px solid var(--border-default)',
          paddingBottom: 'var(--space-5)',
          marginBottom: 'var(--space-5)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 'var(--space-4)' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
              <h2 style={{ margin: 0, fontSize: 'var(--text-h1-size)', fontWeight: 500, letterSpacing: '-0.03em' }}>
                {crypto.code} {crypto.name}
              </h2>
              {crypto.category && <ThemeTag>{crypto.category}</ThemeTag>}
              {crypto.market && <ThemeTag variant="accent">{crypto.market}</ThemeTag>}
            </div>
            <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-body-size)' }}>
              {crypto.exchange && `交易所: ${crypto.exchange}`}
              {crypto.currency && ` | 计价: ${crypto.currency}`}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div className="tabular-nums" style={{ fontSize: 'var(--text-data-lg-size)', fontWeight: 400, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
              {crypto.price != null ? `$${crypto.price < 0.01 ? crypto.price.toFixed(6) : crypto.price < 1 ? crypto.price.toFixed(4) : crypto.price.toFixed(2)}` : '-'}
            </div>
            <div style={{ marginTop: 4 }}>
              {/* Prefer canonical change_pct; fallback to deprecated change_24h. */}
              <ReturnTag value={crypto.change_pct ?? crypto.change_24h} />
            </div>
          </div>
        </div>

        <Row gutter={[16, 16]} style={{ marginTop: 'var(--space-4)' }}>
          <Col xs={12} sm={8} md={6}>
            <div className="tabular-nums" style={{ borderBottom: '1px solid var(--border-default)', padding: 'var(--space-3) 0' }}>
              <Statistic title="24h最高" value={crypto.high_24h} precision={crypto.high_24h != null && crypto.high_24h < 1 ? 4 : 2} prefix="$" />
            </div>
          </Col>
          <Col xs={12} sm={8} md={6}>
            <div className="tabular-nums" style={{ borderBottom: '1px solid var(--border-default)', padding: 'var(--space-3) 0' }}>
              <Statistic title="24h最低" value={crypto.low_24h} precision={crypto.low_24h != null && crypto.low_24h < 1 ? 4 : 2} prefix="$" />
            </div>
          </Col>
          <Col xs={12} sm={8} md={6}>
            <div className="tabular-nums" style={{ borderBottom: '1px solid var(--border-default)', padding: 'var(--space-3) 0' }}>
              <Statistic title="24h成交量" value={crypto.volume_24h} precision={2} />
            </div>
          </Col>
          <Col xs={12} sm={8} md={6}>
            <div className="tabular-nums" style={{ borderBottom: '1px solid var(--border-default)', padding: 'var(--space-3) 0' }}>
              <Statistic title="RSI14" value={indicator?.rsi14} precision={1} />
            </div>
          </Col>
          <Col xs={12} sm={8} md={6}>
            <div className="tabular-nums" style={{ borderBottom: '1px solid var(--border-default)', padding: 'var(--space-3) 0' }}>
              <Statistic title="波动率20日" value={indicator?.volatility_20d} precision={2} suffix="%" />
            </div>
          </Col>
          <Col xs={12} sm={8} md={6}>
            <div className="tabular-nums" style={{ borderBottom: '1px solid var(--border-default)', padding: 'var(--space-3) 0' }}>
              <Statistic title="最大回撤1年" value={indicator?.max_drawdown_1y} precision={2} suffix="%" />
            </div>
          </Col>
          <Col xs={12} sm={8} md={6}>
            <div className="tabular-nums" style={{ borderBottom: '1px solid var(--border-default)', padding: 'var(--space-3) 0' }}>
              <Statistic title="1月收益" value={indicator?.return_1m} precision={2} suffix="%" />
            </div>
          </Col>
          <Col xs={12} sm={8} md={6}>
            <div className="tabular-nums" style={{ borderBottom: '1px solid var(--border-default)', padding: 'var(--space-3) 0' }}>
              <Statistic title="MA5" value={indicator?.ma5} precision={2} prefix="$" />
            </div>
          </Col>
        </Row>
      </div>

      <Tabs items={tabItems} defaultActiveKey="kline" />
    </div>
  );
}
