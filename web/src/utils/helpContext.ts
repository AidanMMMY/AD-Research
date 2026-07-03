import type { HelpPageType } from '@/types/help';

/** 安全地截取数组并返回 JSON 字符串，避免上下文过长 */
function summarizeList<T>(items: T[] | undefined, limit = 10): string {
  if (!items || items.length === 0) return '无';
  const slice = items.slice(0, limit);
  return JSON.stringify(slice, null, 2) + (items.length > limit ? `\n...（共 ${items.length} 条，仅展示前 ${limit} 条）` : '');
}

function summarizeObject(obj: Record<string, unknown> | undefined): string {
  if (!obj || Object.keys(obj).length === 0) return '无';
  return JSON.stringify(obj, null, 2);
}

export function buildScoreRankingContext(
  scoresData: any,
  templateName: string | undefined,
  templateId: number | undefined
): string {
  const items = scoresData?.items || [];
  const topItems = items.slice(0, 10).map((item: any) => ({
    rank_overall: item.rank_overall,
    rank_category: item.rank_category,
    etf_code: item.etf_code,
    etf_name: item.etf_name,
    composite_score: item.composite_score,
    score_return: item.score_return,
    score_risk: item.score_risk,
    score_sharpe: item.score_sharpe,
    score_liquidity: item.score_liquidity,
    score_trend: item.score_trend,
    category: item.category,
  }));

  return [
    '页面：评分排名',
    `当前评分模板：${templateName || '默认模板'}（ID: ${templateId || '默认'}）`,
    `展示标的数量：${items.length}`,
    `Top 10 评分数据：`,
    summarizeList(topItems, 10),
  ].join('\n');
}

export function buildInstrumentDetailContext(
  code: string | undefined,
  instrument: any,
  score: any,
  indicator: any,
  sentiment: any,
  timeRange: number
): string {
  const instrumentSummary = instrument
    ? {
        code: instrument.code,
        name: instrument.name,
        category: instrument.category,
        sub_category: instrument.sub_category,
        market: instrument.market,
        fund_manager: instrument.fund_manager,
        fund_size: instrument.fund_size,
      }
    : { code };

  const scoreSummary = score
    ? {
        composite_score: score.composite_score,
        rank_overall: score.rank_overall,
        rank_category: score.rank_category,
        score_return: score.score_return,
        score_risk: score.score_risk,
        score_sharpe: score.score_sharpe,
        score_liquidity: score.score_liquidity,
        score_trend: score.score_trend,
      }
    : '无评分数据';

  const indicatorSummary = indicator
    ? {
        rsi14: indicator.rsi14,
        sharpe_1y: indicator.sharpe_1y,
        volatility_20d: indicator.volatility_20d,
        max_drawdown_1y: indicator.max_drawdown_1y,
        return_1m: indicator.return_1m,
        return_3m: indicator.return_3m,
        return_1y: indicator.return_1y,
        ma5: indicator.ma5,
        ma20: indicator.ma20,
        macd_dif: indicator.macd_dif,
        macd_dea: indicator.macd_dea,
      }
    : '无指标数据';

  const sentimentSummary = sentiment
    ? {
        avg_score: sentiment.avg_score,
        label: sentiment.label,
        period_days: sentiment.period_days,
      }
    : '无情绪数据';

  return [
    '页面：标的详情',
    `标的代码：${code}`,
    '标的概览：',
    summarizeObject(instrumentSummary as Record<string, unknown>),
    '综合评分：',
    typeof scoreSummary === 'string' ? scoreSummary : summarizeObject(scoreSummary as Record<string, unknown>),
    '关键技术指标：',
    typeof indicatorSummary === 'string' ? indicatorSummary : summarizeObject(indicatorSummary as Record<string, unknown>),
    '情绪分析：',
    typeof sentimentSummary === 'string' ? sentimentSummary : summarizeObject(sentimentSummary as Record<string, unknown>),
    `K 线时间范围：${timeRange} 日`,
  ].join('\n');
}

export function buildStrategyListContext(strategies: any[] | undefined, templates: any[] | undefined): string {
  const strategySummary = (strategies || []).map((s) => ({
    id: s.id,
    name: s.name,
    strategy_type: s.strategy_type,
    is_active: s.is_active,
  }));

  const templateSummary = (templates || []).map((t) => ({
    name: t.name,
    strategy_type: t.strategy_type,
    description: t.description,
    params: t.params,
  }));

  return [
    '页面：策略管理',
    `已创建策略数量：${strategySummary.length}`,
    '策略列表：',
    summarizeList(strategySummary, 20),
    '可用策略模板：',
    summarizeList(templateSummary, 10),
  ].join('\n');
}

export function buildBacktestDetailContext(data: any): string {
  if (!data) return '页面：回测详情\n数据加载中';

  const metrics = data.metrics || {};
  const metricsSummary = {
    total_return: metrics.total_return,
    annualized_return: metrics.annualized_return,
    max_drawdown: metrics.max_drawdown,
    sharpe_ratio: metrics.sharpe_ratio,
    win_rate: metrics.win_rate,
    trade_count: metrics.trade_count,
  };

  const trades = data.trades || [];
  const tradeSummary = trades.slice(0, 5).map((t: any) => ({
    entry_date: t.entry_date,
    exit_date: t.exit_date,
    pnl_pct: t.pnl_pct,
  }));

  return [
    '页面：回测详情',
    `回测 ID：${data.id}`,
    `策略 ID：${data.strategy_id}`,
    `回测区间：${data.start_date} 至 ${data.end_date}`,
    '绩效指标：',
    summarizeObject(metricsSummary),
    `交易次数：${trades.length}`,
    '最近 5 笔交易：',
    summarizeList(tradeSummary, 5),
  ].join('\n');
}

export function buildScreenContext(
  filters: Record<string, any>,
  preset: string | null,
  results: any
): string {
  const resultItems = results?.items || [];
  const resultSummary = resultItems.slice(0, 10).map((r: any) => ({
    code: r.code,
    name: r.name,
    category: r.category,
    composite_score: r.composite_score,
    rsi14: r.rsi14,
    sharpe_1y: r.sharpe_1y,
    return_1m: r.return_1m,
    volatility_20d: r.volatility_20d,
  }));

  return [
    '页面：全市场筛选器',
    `当前预设：${preset || '无'}`,
    '当前筛选条件：',
    summarizeObject(filters),
    `筛选结果数量：${results?.total ?? resultItems.length}`,
    'Top 10 筛选结果：',
    summarizeList(resultSummary, 10),
  ].join('\n');
}

export function buildPoolDetailContext(
  pool: any,
  weights: any[] | undefined,
  analytics: any,
  correlation: any,
  activeAlgorithm: string | undefined
): string {
  const poolSummary = pool
    ? {
        id: pool.id,
        name: pool.name,
        description: pool.description,
        member_count: pool.members?.length,
      }
    : '无池数据';

  const weightSummary = (weights || []).map((w) => ({
    etf_code: w.etf_code,
    target_weight: w.target_weight,
    suggested_weight: w.suggested_weight,
    weight_source: w.weight_source,
  }));

  const analyticsSummary = analytics
    ? {
        category_distribution: analytics.category_distribution,
        return_1m: analytics.return_1m,
        return_3m: analytics.return_3m,
        sharpe: analytics.sharpe,
        max_drawdown: analytics.max_drawdown,
        rebalance_alerts: analytics.rebalance_alerts?.length,
      }
    : '无分析数据';

  const correlationSummary = correlation
    ? {
        codes: correlation.codes,
        matrix_size: correlation.matrix?.length,
      }
    : '无相关性数据';

  return [
    '页面：标的池详情',
    typeof poolSummary === 'string' ? poolSummary : summarizeObject(poolSummary as Record<string, unknown>),
    `当前建议权重算法：${activeAlgorithm || '未选择'}`,
    '权重配置：',
    summarizeList(weightSummary, 20),
    '池分析：',
    typeof analyticsSummary === 'string' ? analyticsSummary : summarizeObject(analyticsSummary as Record<string, unknown>),
    '相关性矩阵：',
    typeof correlationSummary === 'string' ? correlationSummary : summarizeObject(correlationSummary as Record<string, unknown>),
  ].join('\n');
}

export function buildListingPreviewContext(data: Record<string, any>): string {
  const items = Array.isArray(data.items) ? data.items : [];
  const itemSummary = items.slice(0, 10).map((it: any) => ({
    id: it.id,
    ts_code: it.ts_code,
    name: it.name,
    market: it.market,
    board: it.board,
    industry: it.industry,
    issue_date: it.issue_date,
    list_date: it.list_date,
    issue_price: it.issue_price,
    pe_ratio: it.pe_ratio,
    funds_raised: it.funds_raised,
    status: it.status,
    sponsor: it.sponsor,
  }));

  return [
    '页面：上市预告',
    `符合条件的总数：${data.total ?? 0}`,
    '当前筛选条件：',
    summarizeObject((data.filters ?? {}) as Record<string, unknown>),
    '前 10 条记录：',
    summarizeList(itemSummary, 10),
  ].join('\n');
}

export function buildSignalDashboardContext(rows: any[], columns: any[]): string {
  const items = Array.isArray(rows) ? rows : [];

  const typeCount: Record<string, number> = {};
  const strategyCount: Record<string, number> = {};
  const etfSet = new Set<string>();

  for (const it of items) {
    const t = it.signal_type || 'UNKNOWN';
    typeCount[t] = (typeCount[t] || 0) + 1;
    const s = it.strategy_type || it.strategy_name || 'UNKNOWN';
    strategyCount[s] = (strategyCount[s] || 0) + 1;
    if (it.etf_code) etfSet.add(it.etf_code);
  }

  const topByStrength = items
    .filter((it) => typeof it.strength === 'number')
    .sort((a, b) => (b.strength ?? 0) - (a.strength ?? 0))
    .slice(0, 5)
    .map((it) => ({
      etf_code: it.etf_code,
      etf_name: it.etf_name,
      strategy_name: it.strategy_name,
      strategy_type: it.strategy_type,
      signal_type: it.signal_type,
      strength: it.strength,
      trade_date: it.trade_date,
    }));

  const sampleExtraData = items
    .map((it) => it.extra_data)
    .filter((e) => e && typeof e === 'object' && Object.keys(e).length > 0)
    .slice(0, 2);

  const columnTitles = (columns || [])
    .map((c: any) => c?.title ?? c?.dataIndex)
    .filter(Boolean);

  return [
    '页面：信号看板',
    `当前表格标的数量：${items.length}`,
    `覆盖标的（etf_code）数量：${etfSet.size}`,
    '信号类型分布：',
    summarizeObject(typeCount),
    '策略分布（按 strategy_type 聚合）：',
    summarizeObject(strategyCount),
    '按强度排序的 Top 5：',
    summarizeList(topByStrength, 5),
    'extra_data 样例（最多 2 条）：',
    summarizeList(sampleExtraData as Record<string, unknown>[], 2),
    `当前表格列：${columnTitles.join('、')}`,
  ].join('\n');
}

export function buildContext(
  pageType: HelpPageType,
  data: Record<string, any>
): string {
  switch (pageType) {
    case 'score_ranking':
      return buildScoreRankingContext(data.scoresData, data.templateName, data.templateId);
    case 'instrument_detail':
      return buildInstrumentDetailContext(
        data.code,
        data.instrument,
        data.score,
        data.indicator,
        data.sentiment,
        data.timeRange
      );
    case 'strategy_list':
      return buildStrategyListContext(data.strategies, data.templates);
    case 'backtest_detail':
      return buildBacktestDetailContext(data.data);
    case 'screen':
      return buildScreenContext(data.filters, data.preset, data.results);
    case 'pool_detail':
      return buildPoolDetailContext(
        data.pool,
        data.weights,
        data.analytics,
        data.correlation,
        data.activeAlgorithm
      );
    case 'listing_preview':
      return buildListingPreviewContext(data);
    case 'signal_dashboard':
      return buildSignalDashboardContext(data.rows ?? [], data.columns ?? []);
    default:
      return summarizeObject(data);
  }
}
