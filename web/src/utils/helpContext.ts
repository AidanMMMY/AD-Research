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

export function buildETFDetailContext(
  code: string | undefined,
  etf: any,
  score: any,
  indicator: any,
  sentiment: any,
  timeRange: number
): string {
  const etfSummary = etf
    ? {
        code: etf.code,
        name: etf.name,
        category: etf.category,
        sub_category: etf.sub_category,
        market: etf.market,
        fund_manager: etf.fund_manager,
        fund_size: etf.fund_size,
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
    '页面：ETF 详情',
    `标的代码：${code}`,
    '标的概览：',
    summarizeObject(etfSummary as Record<string, unknown>),
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

export function buildContext(
  pageType: HelpPageType,
  data: Record<string, any>
): string {
  switch (pageType) {
    case 'score_ranking':
      return buildScoreRankingContext(data.scoresData, data.templateName, data.templateId);
    case 'etf_detail':
      return buildETFDetailContext(
        data.code,
        data.etf,
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
    default:
      return summarizeObject(data);
  }
}
