import { useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Tabs, Descriptions, Radio, Checkbox, Skeleton,
} from 'antd';
import { ReadOutlined } from '@ant-design/icons';
import { useCryptoDetail, useCryptoScore, useCryptoSignals, useCryptoResearch } from '@/hooks/useCrypto';
import { useAIHelp } from '@/hooks/useAIHelp';
import { useQuery } from '@tanstack/react-query';
import { cryptoApi } from '@/api/crypto';
import KLineChart, { DEFAULT_OVERLAYS } from '@/components/KLineChart';
import ScoreRadar from '@/components/ScoreRadar';
import ReturnTag from '@/components/ReturnTag';
import HelpTrigger from '@/components/HelpTrigger';
import ThemeTag from '@/components/ThemeTag';
import { formatPercent } from '@/utils/format';
import type { OHLCV } from '@/types/etf';

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

const SENTIMENT_COLORS: Record<string, string> = {
  bullish: 'var(--color-rise)',
  bearish: 'var(--color-fall)',
  neutral: 'var(--text-tertiary)',
};

const SENTIMENT_LABELS: Record<string, string> = {
  bullish: '看多',
  bearish: '看空',
  neutral: '中性',
};

export default function CryptoDetail() {
  const { code } = useParams<{ code: string }>();
  const { open } = useAIHelp();

  const { data: crypto, isLoading: cryptoLoading } = useCryptoDetail(code || '');
  const { data: score } = useCryptoScore(code || '');
  const { data: signals } = useCryptoSignals(code || '', 20);
  const { data: research } = useCryptoResearch(code || '', 5);

  const [timeRange, setTimeRange] = useState(120);

  // Persist K-line overlay preferences in localStorage
  const [overlays, setOverlays] = useState(() => {
    try {
      const saved = localStorage.getItem('crypto-detail-overlays');
      return saved ? JSON.parse(saved) : { ...DEFAULT_OVERLAYS };
    } catch {
      return { ...DEFAULT_OVERLAYS };
    }
  });

  const { data: bars, isLoading: barsLoading } = useQuery({
    queryKey: ['crypto-bars', code, timeRange],
    queryFn: () =>
      cryptoApi.history(code!, { limit: timeRange }).then((data) =>
        data.map((b) => ({
          trade_date: b.trade_date,
          open: b.open ?? 0,
          high: b.high ?? 0,
          low: b.low ?? 0,
          close: b.close ?? 0,
          volume: b.volume ?? 0,
        })),
      ),
    enabled: !!code,
    staleTime: 120_000,
  });

  if (!code) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-tertiary)' }}>
        请输入币种代码
      </div>
    );
  }

  // --- Build AI help context (simple text block) ---
  const helpContextText = crypto
    ? [
        `代码: ${crypto.code}`,
        `名称: ${crypto.name}`,
        `分类: ${crypto.category || '-'}`,
        `交易所: ${crypto.exchange || '-'}`,
        crypto.price != null ? `价格: $${crypto.price}` : null,
        crypto.change_24h != null ? `24h涨跌: ${crypto.change_24h.toFixed(2)}%` : null,
        score ? `综合评分: ${score.composite_score?.toFixed(1)}` : null,
        crypto.latest_indicator?.rsi14 != null
          ? `RSI14: ${crypto.latest_indicator.rsi14.toFixed(1)}`
          : null,
      ]
        .filter(Boolean)
        .join('\n')
    : undefined;

  // --- Tab items ---
  const tabItems = [
    // 1) K-line
    {
      key: 'chart',
      label: 'K线图',
      children: (
        <div>
          {/* Controls */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 'var(--space-4)',
              gap: 'var(--space-3)',
            }}
          >
            <Radio.Group
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value)}
              optionType="button"
              size="small"
              options={TIME_RANGE_OPTIONS}
            />
            <Checkbox.Group
              value={Object.entries(INDICATOR_OPTIONS)
                .filter(([, opt]) => overlays[opt.value as keyof typeof overlays])
                .map(([, opt]) => opt.value)}
              onChange={(vals) => {
                const next = { ...overlays };
                for (const opt of INDICATOR_OPTIONS) {
                  (next as any)[opt.value] = vals.includes(opt.value);
                }
                setOverlays(next);
                localStorage.setItem('crypto-detail-overlays', JSON.stringify(next));
              }}
              options={INDICATOR_OPTIONS}
            />
          </div>

          {barsLoading ? (
            <Skeleton active paragraph={{ rows: 10 }} />
          ) : (
            <div style={{ width: '100%', height: 420 }}>
              <KLineChart data={(bars ?? []) as OHLCV[]} overlays={overlays} />
            </div>
          )}
        </div>
      ),
    },
    // 2) Indicators
    {
      key: 'indicators',
      label: '技术指标',
      children: crypto?.latest_indicator ? (
        <Descriptions column={{ xs: 1, sm: 2, md: 3 }} size="small" bordered>
          <Descriptions.Item label="MA5">
            {crypto.latest_indicator.ma5?.toFixed(4) ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label="MA10">
            {crypto.latest_indicator.ma10?.toFixed(4) ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label="MA20">
            {crypto.latest_indicator.ma20?.toFixed(4) ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label="MA60">
            {crypto.latest_indicator.ma60?.toFixed(4) ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label="RSI14">
            {crypto.latest_indicator.rsi14 != null ? (
              <span
                style={{
                  color:
                    crypto.latest_indicator.rsi14 > 70
                      ? 'var(--color-fall)'
                      : crypto.latest_indicator.rsi14 < 30
                        ? 'var(--color-rise)'
                        : 'var(--text-secondary)',
                  fontWeight: 600,
                }}
              >
                {crypto.latest_indicator.rsi14.toFixed(1)}
              </span>
            ) : (
              '-'
            )}
          </Descriptions.Item>
          <Descriptions.Item label="MACD DIF">
            {crypto.latest_indicator.macd_dif?.toFixed(4) ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label="MACD DEA">
            {crypto.latest_indicator.macd_dea?.toFixed(4) ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label="MACD Hist">
            {crypto.latest_indicator.macd_hist?.toFixed(4) ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label="ATR14">
            {crypto.latest_indicator.atr14?.toFixed(4) ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label="BB 上轨">
            {crypto.latest_indicator.bb_upper?.toFixed(4) ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label="BB 下轨">
            {crypto.latest_indicator.bb_lower?.toFixed(4) ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label="20日波动率">
            {crypto.latest_indicator.volatility_20d != null
              ? formatPercent(crypto.latest_indicator.volatility_20d)
              : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="60日波动率">
            {crypto.latest_indicator.volatility_60d != null
              ? formatPercent(crypto.latest_indicator.volatility_60d)
              : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="1年最大回撤">
            {crypto.latest_indicator.max_drawdown_1y != null
              ? formatPercent(crypto.latest_indicator.max_drawdown_1y)
              : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="1年夏普">
            {crypto.latest_indicator.sharpe_1y?.toFixed(2) ?? '-'}
          </Descriptions.Item>
          <Descriptions.Item label="1周收益">
            <ReturnTag value={crypto.latest_indicator.return_1w} />
          </Descriptions.Item>
          <Descriptions.Item label="1月收益">
            <ReturnTag value={crypto.latest_indicator.return_1m} />
          </Descriptions.Item>
          <Descriptions.Item label="3月收益">
            <ReturnTag value={crypto.latest_indicator.return_3m} />
          </Descriptions.Item>
          <Descriptions.Item label="6月收益">
            <ReturnTag value={crypto.latest_indicator.return_6m} />
          </Descriptions.Item>
          <Descriptions.Item label="1年收益">
            <ReturnTag value={crypto.latest_indicator.return_1y} />
          </Descriptions.Item>
        </Descriptions>
      ) : (
        <div style={{ color: 'var(--text-tertiary)', padding: 40, textAlign: 'center' }}>
          暂无指标数据。请等待后台计算完成后刷新。
        </div>
      ),
    },
    // 3) Score
    {
      key: 'score',
      label: '评分',
      children: score ? (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-6)' }}>
          <ScoreRadar
            data={{
              score_return: score.return_score ?? 0,
              score_risk: score.risk_score ?? 0,
              score_sharpe: score.sharpe_score ?? 0,
              score_liquidity: score.liquidity_score ?? 0,
              score_trend: score.trend_score ?? 0,
            }}
          />
          <Descriptions column={1} size="small" bordered style={{ flex: 1, minWidth: 200 }}>
            <Descriptions.Item label="综合评分">
              <span style={{ fontSize: 'var(--text-h2-size)', fontWeight: 700, color: 'var(--accent)' }}>
                {score.composite_score?.toFixed(1) ?? '-'}
              </span>
            </Descriptions.Item>
            <Descriptions.Item label="总排名">
              {score.rank_overall ?? '-'}
            </Descriptions.Item>
            <Descriptions.Item label="分类排名">
              {score.rank_category ?? '-'}
            </Descriptions.Item>
          </Descriptions>
        </div>
      ) : (
        <div style={{ color: 'var(--text-tertiary)', padding: 40, textAlign: 'center' }}>
          暂无评分数据。请等待后台计算完成后刷新。
        </div>
      ),
    },
    // 4) Signals
    {
      key: 'signals',
      label: '交易信号',
      children: signals && signals.length > 0 ? (
        <Descriptions column={1} size="small" bordered>
          {signals.slice(0, 10).map((s) => (
            <Descriptions.Item
              key={s.id}
              label={s.trade_date}
            >
              <span
                style={{
                  fontWeight: 600,
                  color:
                    s.signal_type === 'BUY'
                      ? 'var(--color-rise)'
                      : s.signal_type === 'SELL'
                        ? 'var(--color-fall)'
                        : 'var(--text-secondary)',
                }}
              >
                {s.signal_type}
              </span>
              <span style={{ marginLeft: 16, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                强度: {s.strength}
              </span>
            </Descriptions.Item>
          ))}
        </Descriptions>
      ) : (
        <div style={{ color: 'var(--text-tertiary)', padding: 40, textAlign: 'center' }}>
          暂无信号数据
        </div>
      ),
    },
    // 5) AI Research
    {
      key: 'research',
      label: (
        <span>
          <ReadOutlined style={{ marginRight: 4 }} />
          AI 研究
        </span>
      ),
      children: research && research.length > 0 ? (
        <div>
          {research.map((n) => (
            <div
              key={n.id}
              style={{
                marginBottom: 'var(--space-5)',
                padding: 'var(--space-4)',
                border: '1px solid var(--border-default)',
                borderRadius: 'var(--radius-md)',
                background: 'var(--bg-surface)',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 'var(--space-2)',
                }}
              >
                <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>
                  {n.generated_at}
                </span>
                <span
                  style={{
                    fontWeight: 600,
                    color: SENTIMENT_COLORS[n.sentiment] || 'var(--text-tertiary)',
                  }}
                >
                  {SENTIMENT_LABELS[n.sentiment] || n.sentiment}
                </span>
              </div>
              <div
                style={{
                  fontSize: 'var(--text-body-size)',
                  color: 'var(--text-primary)',
                  lineHeight: 1.8,
                }}
                dangerouslySetInnerHTML={{ __html: n.content }}
              />
            </div>
          ))}
        </div>
      ) : (
        <div style={{ color: 'var(--text-tertiary)', padding: 40, textAlign: 'center' }}>
          暂无 AI 研究笔记
        </div>
      ),
    },
  ];

  return (
    <div>
      {cryptoLoading ? (
        <Skeleton active paragraph={{ rows: 4 }} />
      ) : crypto ? (
        <>
          {/* Header */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              marginBottom: 'var(--space-6)',
              gap: 'var(--space-4)',
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 4 }}>
                <h1
                  style={{
                    fontSize: 'var(--text-h1-size)',
                    fontWeight: 500,
                    color: 'var(--text-primary)',
                    margin: 0,
                    letterSpacing: '-0.03em',
                  }}
                >
                  {crypto.name}
                </h1>
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 'var(--text-body-size)',
                    color: 'var(--text-tertiary)',
                  }}
                >
                  {crypto.code}
                </span>
                {crypto.category && <ThemeTag>{crypto.category}</ThemeTag>}
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)' }}>
                {crypto.price != null && (
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 'var(--text-h2-size)',
                      fontWeight: 600,
                      color: 'var(--text-primary)',
                    }}
                  >
                    ${crypto.price < 0.01 ? crypto.price.toFixed(6) : crypto.price < 1 ? crypto.price.toFixed(4) : crypto.price.toFixed(2)}
                  </span>
                )}
                <ReturnTag value={crypto.change_24h} />
              </div>
            </div>

            <HelpTrigger
              tooltip="让 AI 帮你分析"
              onClick={() => {
                if (!helpContextText) return;
                open({
                  pageType: 'etf_detail',
                  pageTitle: `${crypto.name} (${crypto.code})`,
                  contextData: helpContextText,
                  quickQuestions: [
                    `${crypto.name} 近期走势如何？`,
                    `${crypto.name} 现在适合买入吗？`,
                    `${crypto.name} 的主要风险是什么？`,
                  ],
                  initialQuestion: `请分析 ${crypto.name} (${crypto.code}) 的当前技术面和投资价值`,
                });
              }}
            />
          </div>

          {/* Stats row */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 'var(--space-4)',
              marginBottom: 'var(--space-6)',
            }}
          >
            {crypto.high_24h != null && (
              <div>
                <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>24h 高</span>
                <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  ${crypto.high_24h.toFixed(2)}
                </div>
              </div>
            )}
            {crypto.low_24h != null && (
              <div>
                <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>24h 低</span>
                <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  ${crypto.low_24h.toFixed(2)}
                </div>
              </div>
            )}
            {crypto.volume_24h != null && (
              <div>
                <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>24h 成交量</span>
                <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  {crypto.volume_24h >= 1e9
                    ? `${(crypto.volume_24h / 1e9).toFixed(1)}B`
                    : crypto.volume_24h >= 1e6
                      ? `${(crypto.volume_24h / 1e6).toFixed(1)}M`
                      : crypto.volume_24h.toFixed(0)}
                </div>
              </div>
            )}
            <div>
              <span style={{ fontSize: 'var(--text-small-size)', color: 'var(--text-tertiary)' }}>交易所</span>
              <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-secondary)' }}>
                {crypto.exchange || '-'}
              </div>
            </div>
          </div>

          {/* Tabs */}
          <Tabs
            defaultActiveKey="chart"
            items={tabItems}
            style={{ marginTop: 0 }}
          />
        </>
      ) : (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-tertiary)' }}>
          未找到币种信息
        </div>
      )}
    </div>
  );
}
