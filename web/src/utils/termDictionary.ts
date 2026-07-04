export type HelpPageType =
  | 'score_ranking'
  | 'instrument_detail'
  | 'strategy_list'
  | 'backtest_detail'
  | 'screen'
  | 'pool_detail'
  | 'listing_preview'
  | 'signal_dashboard';

export interface TermEntry {
  /** 唯一标识，也用于 i18n key */
  key: string;
  /** 术语显示标题 */
  title: string;
  /** L1：一句话定义（用于 Tooltip） */
  shortDesc: string;
  /** L2：详细说明（用于 Popover） */
  fullDesc: string;
  /** 计算公式，可选 */
  formula?: string;
  /** 数值解读方法，可选 */
  interpretation?: string;
  /** 教学案例，可选 */
  example?: string;
  /** 关联的 AI 帮助页面类型，用于“问 AI”时带上下文 */
  relatedPageType?: HelpPageType;
  /**
   * M20: 相关术语 key 列表，用于在 HelpPopover 底部以 chip 形式推荐相邻概念。
   * 落地仅展示（点击打 log），P2 可接跳词条详情页。
   */
  relatedTerms?: string[];
}

/**
 * 跨页术语统一（仅文档用途，不做运行时 rename，避免破坏 i18n / DB 列）。
 *
 * 平台历史上对「收藏 / 关注 / 自选股 / Watchlist / favorites / stars」
 * 混用过，对「ETF / STOCK / CRYPTO」的中文标签也各自命名。下面是当前
 * 推荐的规范映射：
 *
 *   TERMINOLOGY_ALIASES
 *     '收藏'        → '自选股'
 *     '关注'        → '自选股'
 *     'Watchlist'   → '自选股'
 *     'favorites'   → '自选股'
 *     'stars'       → '自选股'
 *
 *   INSTRUMENT_TYPE_ALIASES
 *     'ETF'         → '基金'
 *     'STOCK'       → '个股'
 *     'CRYPTO'      → '数字货币'
 *
 * 注意：
 *   - 这只是给开发 / 客服 / 文档参考用的"事实表"，不要在代码里做全局替换。
 *   - 历史 UI 文本（如 Dashboard "暂无收藏的标的"、InstrumentDetail "已收藏"）
 *     保留原措辞，避免一次性改文案导致翻译 key 失配、test snapshot 红屏。
 *   - 新页面/新文案请直接使用右侧的"规范名"以减少后续收敛成本。
 */
export const TERMINOLOGY_ALIASES: Record<string, string> = {
  '收藏': '自选股',
  '关注': '自选股',
  'Watchlist': '自选股',
  'favorites': '自选股',
  'stars': '自选股',
};

export const INSTRUMENT_TYPE_ALIASES: Record<string, string> = {
  ETF: '基金',
  STOCK: '个股',
  CRYPTO: '数字货币',
};

const entries: TermEntry[] = [
  // ===== 评分体系 =====
  {
    key: 'composite_score',
    title: '综合评分',
    shortDesc: '从收益、风险、夏普、流动性、趋势五个维度加权计算出的 0-100 分综合得分。',
    fullDesc: `综合评分是平台对每只 ETF 的多维度量化打分。它先把各维度指标转换成 0-100 的百分位得分，再按模板权重加权求和。得分越高，说明该 ETF 在当前评分模板下综合表现越好。`,
    formula: '综合得分 = Σ（维度得分 × 维度权重）',
    interpretation: '80 分以上通常视为优秀；60 分以下说明至少有一个维度明显偏弱。',
    example: '某 ETF 收益维度 90 分、风险维度 70 分、夏普维度 85 分，按均衡模板（30%/25%/25%/10%/10%）计算，综合得分约为 83.5 分。',
    relatedPageType: 'score_ranking',
    relatedTerms: ['score_return', 'score_risk', 'score_sharpe', 'score_liquidity', 'score_trend'],
  },
  {
    key: 'score_return',
    title: '收益能力',
    shortDesc: '衡量 ETF 近期收益表现的维度，基于 1 月、3 月、1 年收益率。',
    fullDesc: '收益能力维度综合考察 ETF 在不同时间窗口下的收益表现。窗口越长，越能反映中长期趋势；窗口越短，越能捕捉近期动量。',
    formula: '对 return_1m、return_3m、return_1y 取平均后做百分位排名',
    interpretation: '得分越高说明近期收益表现越好，但高得分不代表未来一定上涨。',
    example: 'A ETF 近 1 月涨 5%、近 3 月涨 12%、近 1 年涨 30%，在所有 ETF 中收益排名靠前，收益能力得分可能达到 90 分以上。',
    relatedPageType: 'score_ranking',
    relatedTerms: ['composite_score', 'return_1m', 'return_3m', 'return_1y'],
  },
  {
    key: 'score_risk',
    title: '风险控制',
    shortDesc: '衡量 ETF 波动和回撤水平的维度，基于 20 日波动率和 1 年最大回撤。',
    fullDesc: '风险控制维度希望识别出价格波动较小、历史最大亏损可控的 ETF。该维度采用反向计分：波动率越低、回撤越小，得分越高。',
    formula: '对 volatility_20d、max_drawdown_1y 取平均后做百分位排名，再反向',
    interpretation: '高分代表走势相对稳健，适合风险厌恶型投资者；低分代表波动剧烈。',
    example: '某债券 ETF 20 日波动率仅 2%、最大回撤 1.5%，风险控制得分通常高于高波动股票 ETF。',
    relatedPageType: 'score_ranking',
    relatedTerms: ['composite_score', 'volatility_20d', 'max_drawdown_1y'],
  },
  {
    key: 'score_sharpe',
    title: '夏普比率',
    shortDesc: '衡量每承担一单位风险能获得多少超额收益的维度。',
    fullDesc: '夏普维度反映风险调整后的收益能力。它把收益和风险结合起来看：同样的收益，波动越小，夏普越高。',
    formula: '对 sharpe_1y 做百分位排名',
    interpretation: '通常夏普 > 1 算不错，> 2 算优秀；< 0 说明收益还跑不赢无风险利率。',
    example: 'ETF A 年化收益 15%、波动 10%，夏普约 1.1；ETF B 年化收益 20%、波动 25%，夏普约 0.7。A 的夏普更高。',
    relatedPageType: 'score_ranking',
    relatedTerms: ['composite_score', 'sharpe_1y', 'volatility_20d', 'max_drawdown_1y'],
  },
  {
    key: 'score_liquidity',
    title: '流动性',
    shortDesc: '衡量 ETF 日均成交额的维度，反映买卖便利程度。',
    fullDesc: '流动性维度基于日均成交额。成交额越高，越容易以接近净值的价格买入或卖出，冲击成本越低。',
    formula: '对 amount（日均成交额）做百分位排名',
    interpretation: '高分代表交易活跃，适合大资金进出；低分可能面临滑点或买卖价差大。',
    example: '宽基 ETF 日均成交额可能达几十亿，流动性得分高；小众行业 ETF 可能只有几千万，得分偏低。',
    relatedPageType: 'score_ranking',
  },
  {
    key: 'score_trend',
    title: '趋势强度',
    shortDesc: '衡量 ETF 当前趋势强弱的维度，基于 RSI14 和均线位置。',
    fullDesc: '趋势强度维度综合 RSI 和价格在均线之上的位置，判断当前是否处于较强上升趋势。其中均线位置使用平台自定义的 ma_position = MA5 / MA20，不是市场通用指标；该值大于 1 表示价格站上年线以上。',
    formula: '综合 rsi14、ma_position（MA5/MA20）等指标后做百分位排名',
    interpretation: '高分不一定代表“值得买”，也可能是短期过热；要结合其他维度一起看。',
    example: '某 ETF 价格站上年线且 RSI 在 60 附近，趋势强度得分较高；若 RSI 已接近 80，则可能超买。',
    relatedPageType: 'score_ranking',
    relatedTerms: ['composite_score', 'rsi14', 'ma5', 'ma20', 'macd'],
  },
  {
    key: 'rank_overall',
    title: '全市场排名',
    shortDesc: '该 ETF 在所有被评分 ETF 中的综合排名。',
    fullDesc: '按综合得分对所有 ETF 降序排列后生成的名次，1 表示当前得分最高。',
    interpretation: '排名越靠前，说明在当前评分模板下综合表现越好。',
    relatedPageType: 'score_ranking',
  },
  {
    key: 'rank_category',
    title: '分类排名',
    shortDesc: '该 ETF 在同分类（如科技、医药）内的综合排名。',
    fullDesc: '按综合得分在同分类 ETF 中降序排列的名次，便于同类资产内部比较。',
    interpretation: '在同类中排名靠前，说明它比同类型 ETF 综合表现更优。',
    relatedPageType: 'score_ranking',
  },

  // ===== 技术指标 =====
  {
    key: 'rsi14',
    title: 'RSI14',
    shortDesc: '相对强弱指标，14 日周期，衡量价格涨跌动量的强弱和超买超卖。',
    fullDesc: 'RSI（Relative Strength Index）通过比较一段时间内上涨日和下跌日的平均幅度，判断市场是否超买或超卖。取值范围 0-100。',
    formula: 'RS = 平均上涨幅度 / 平均下跌幅度；RSI = 100 - 100 / (1 + RS)',
    interpretation: 'RSI > 70 通常视为超买，可能回调；RSI < 30 通常视为超卖，可能反弹。但强势趋势中可能长期超买或超卖。',
    example: '某 ETF 的 RSI14 = 75，说明近期上涨动能较强，短期存在过热风险；RSI14 = 25 则可能处于短期低点。',
    relatedPageType: 'instrument_detail',
    relatedTerms: ['macd', 'bollinger_bands', 'kline', 'score_trend'],
  },
  {
    key: 'sharpe_1y',
    title: '夏普1年',
    shortDesc: '基于近 1 年数据计算的风险调整后收益指标。',
    fullDesc: '用近 1 年的收益率和波动率计算夏普比率，反映过去一年每承担一单位风险获得的超额收益。',
    formula: 'Sharpe = (年化收益 - 无风险利率) / 年化波动率',
    interpretation: '数值越高越好。>1 通常认为风险补偿较充分。',
    relatedPageType: 'instrument_detail',
    relatedTerms: ['volatility_20d', 'max_drawdown_1y', 'score_sharpe'],
  },
  {
    key: 'volatility_20d',
    title: '波动率20日',
    shortDesc: '近 20 个交易日收益率的年化标准差，衡量价格波动剧烈程度。',
    fullDesc: '波动率反映资产价格波动的剧烈程度。20 日波动率用最近 20 个交易日数据计算，并年化处理。由于计算允许样本不足（min_periods=5），前几个交易日的波动率可能基于较少样本。',
    formula: 'std(近20日收益率) × √252 × 100%',
    interpretation: '数值越高，价格波动越大，风险也越高。适合用于仓位控制和止损设置。早期数据样本不足时需谨慎参考。',
    example: '波动率 10% 的 ETF 日内波动通常远小于波动率 40% 的行业主题 ETF。',
    relatedPageType: 'instrument_detail',
    relatedTerms: ['sharpe_1y', 'max_drawdown_1y', 'bollinger_bands'],
  },
  {
    key: 'max_drawdown_1y',
    title: '最大回撤',
    shortDesc: '近 1 年内从最高点跌到最低点的最大亏损幅度。',
    fullDesc: '最大回撤衡量投资者在过去一年中可能面临的最惨亏损。它是评估下行风险的重要指标。',
    formula: 'Max Drawdown = (历史高点 - 后续最低点) / 历史高点 × 100%',
    interpretation: '回撤越小，持有体验越好。回撤大的品种需要更强的风险承受能力。',
    example: '某 ETF 去年最高净值 1.5，随后最低跌到 1.2，最大回撤为 20%。',
    relatedPageType: 'instrument_detail',
    relatedTerms: ['volatility_20d', 'sharpe_1y', 'score_risk'],
  },
  {
    key: 'return_1m',
    title: '1月收益',
    shortDesc: '近 1 个月（约 21 个交易日）的累计收益率。',
    fullDesc: '反映 ETF 短期表现。1 个月窗口对近期趋势敏感，但噪音也较大。',
    interpretation: '正值表示上涨，负值表示下跌。单独看容易受短期情绪影响。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'return_3m',
    title: '3月收益',
    shortDesc: '近 3 个月（约 63 个交易日）的累计收益率。',
    fullDesc: '反映 ETF 中期表现，比 1 个月更能过滤短期噪音。',
    interpretation: '正值且排名靠前，说明中期趋势较强。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'return_1y',
    title: '1年收益',
    shortDesc: '近 1 年（约 252 个交易日）的累计收益率。',
    fullDesc: '反映 ETF 中长期表现，是评估一年持有回报的重要参考。',
    interpretation: '长期正收益代表趋势向上，但也要结合回撤和波动一起看。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'ma5',
    title: 'MA5',
    shortDesc: '5 日移动平均线，反映短期平均成本。',
    fullDesc: 'MA5 是最近 5 个交易日收盘价的平均值，常作为短期支撑或阻力位参考。',
    formula: 'MA5 = (近 5 日收盘价之和) / 5',
    interpretation: '价格在 MA5 上方，短期偏强；跌破 MA5，短期可能转弱。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'ma20',
    title: 'MA20',
    shortDesc: '20 日移动平均线，反映中期趋势。',
    fullDesc: 'MA20 是最近 20 个交易日收盘价的平均值，常被看作中期趋势的参考线。',
    interpretation: '价格在 MA20 上方且 MA20 向上，中期趋势偏多；反之偏空。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'bollinger_bands',
    title: '布林带',
    shortDesc: '由中轨（MA20）和上下轨（±2 倍标准差）组成的通道指标。',
    fullDesc: '布林带通过价格的标准差构建波动通道。价格触及上轨可能超买，触及下轨可能超卖。平台使用 MA20 和 2 倍标准差；由于计算时允许样本不足（min_periods=1），前 19 根 K 线的布林带可能基于较少样本，稳定性较差。',
    formula: '中轨 = MA20；上轨 = MA20 + 2 × std20；下轨 = MA20 - 2 × std20',
    interpretation: '通道收窄预示波动即将放大；价格突破上轨或下轨可能意味着趋势延续或反转。早期数据样本不足时需谨慎使用。',
    relatedPageType: 'instrument_detail',
    relatedTerms: ['ma20', 'volatility_20d', 'rsi14'],
  },
  {
    key: 'macd',
    title: 'MACD',
    shortDesc: '异同移动平均线，用于判断趋势方向和动能变化。',
    fullDesc: 'MACD 由快线 DIF、慢线 DEA 和柱状图组成，常用于识别趋势转折和动能强弱。',
    formula: 'DIF = EMA12 - EMA26；DEA = EMA9(DIF)；Histogram = DIF - DEA',
    interpretation: 'DIF 上穿 DEA 为金叉，偏多；DIF 下穿 DEA 为死叉，偏空。柱状图放大代表动能增强。',
    relatedPageType: 'instrument_detail',
    relatedTerms: ['rsi14', 'ma5', 'ma20', 'kline'],
  },
  {
    key: 'ma10',
    title: 'MA10',
    shortDesc: '10 日移动平均线，反映短期趋势。',
    fullDesc: 'MA10 是最近 10 个交易日收盘价的平均值，介于 MA5 和 MA20 之间，常用于观察短期趋势变化。',
    formula: 'MA10 = (近 10 日收盘价之和) / 10',
    interpretation: '价格站稳 MA10 上方，短期偏强；跌破 MA10 可能进入短期调整。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'ma60',
    title: 'MA60',
    shortDesc: '60 日移动平均线，反映中长期趋势。',
    fullDesc: 'MA60 是最近 60 个交易日收盘价的平均值，常被看作季度趋势的参考线，也常被称为“生命线”。',
    formula: 'MA60 = (近 60 日收盘价之和) / 60',
    interpretation: '价格在 MA60 上方且 MA60 向上，中长期趋势偏多；有效跌破 MA60 可能意味着趋势转弱。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'kline',
    title: 'K 线图',
    shortDesc: '用蜡烛线展示开盘价、收盘价、最高价、最低价的行情图表。',
    fullDesc: 'K 线图（Candlestick Chart）每根蜡烛代表一个时间周期，实体表示开盘到收盘的涨跌，上下影线表示该周期的最高最低价。',
    interpretation: '阳线（通常红色）表示收盘价高于开盘价，阴线（通常绿色）表示收盘价低于开盘价。长上影线说明上方抛压大，长下影线说明下方有支撑。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'time_range',
    title: '时间范围',
    shortDesc: 'K 线图展示的历史交易日数量。',
    fullDesc: '时间范围决定 K 线图上显示多少根蜡烛。范围越短，越能看清近期细节；范围越长，越能把握中长期趋势。',
    interpretation: '30 日/60 日适合短期交易参考；120 日/250 日适合中长期趋势判断。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'ai_analysis',
    title: 'AI 分析',
    shortDesc: '基于历史数据和文本信息的自动化分析结论。',
    fullDesc: 'AI 分析模块利用大语言模型对 ETF 的技术指标、市场情绪、研究笔记等信息进行整合，生成可读性较强的分析结论。',
    interpretation: 'AI 分析是辅助参考，不构成投资建议。重要决策仍需结合自己的判断和风险承受能力。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'ai_research_note',
    title: 'AI 研究笔记',
    shortDesc: '平台自动生成的关于某只 ETF 的研究摘要报告。',
    fullDesc: 'AI 研究笔记基于公开数据、技术指标和市场信息，由大语言模型生成的简短研报。可以点击“生成研报”按钮重新生成。',
    interpretation: '研究笔记提供快速概览，但不能替代深度研究和尽职调查。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'market_sentiment',
    title: '市场情绪',
    shortDesc: '基于相关新闻或研报文本计算出的看多/看空/中性倾向分数。',
    fullDesc: '市场情绪通过自然语言处理分析近期相关文本，给出一个 -1 到 +1 之间的情绪分数。越接近 +1 越偏乐观，越接近 -1 越偏悲观。',
    interpretation: '情绪指标反映市场短期共识，常用于判断是否存在过热或过冷风险，但不应作为唯一买卖依据。',
    relatedPageType: 'instrument_detail',
  },

  // ===== 策略 =====
  {
    key: 'momentum',
    title: '动量策略',
    shortDesc: '假设上涨趋势会延续，按收益率是否突破阈值发出买卖信号。',
    fullDesc: '动量策略基于“强者恒强”的假设。当 ETF 在 N 日内的涨幅超过阈值时产生买入信号，跌幅超过阈值时产生卖出信号。',
    formula: 'N 日收益率 ≥ threshold → BUY；N 日收益率 ≤ -threshold → SELL',
    interpretation: '适合趋势明显的市场；在震荡市中容易反复打脸。',
    example: '窗口 20 天、阈值 5%：某 ETF 近 20 日涨 7%，触发 BUY；近 20 日跌 6%，触发 SELL。',
    relatedPageType: 'strategy_list',
    relatedTerms: ['mean_reversion', 'rsi_strategy', 'trend_following'],
  },
  {
    key: 'mean_reversion',
    title: '均值回归策略',
    shortDesc: '假设价格偏离均值后会回归，按 Z-score 阈值发出买卖信号。',
    fullDesc: '均值回归策略认为价格会围绕均值波动。当价格显著高于均值时卖出，显著低于均值时买入。',
    formula: 'Z-score = (价格 - 均值) / 标准差；Z-score ≥ threshold → SELL；Z-score ≤ -threshold → BUY',
    interpretation: '适合震荡市；在强趋势行情中会被持续套住。',
    example: 'Z-score 阈值 2.0：某 ETF 价格显著高于 60 日均线，Z-score = 2.3，触发 SELL。',
    relatedPageType: 'strategy_list',
  },
  {
    key: 'strategy_template',
    title: '策略模板',
    shortDesc: '平台内置的策略类型和默认参数配置，用于快速创建新策略。',
    fullDesc: '策略模板封装了常见量化策略（动量、均值回归、RSI）的参数结构和默认值。选择一个模板后，系统会自动填充策略类型和参数，你只需要命名并启用即可。',
    interpretation: '模板是起点，不是终点。你可以基于模板修改参数，形成自己的策略。',
    relatedPageType: 'strategy_list',
  },
  {
    key: 'rsi_strategy',
    title: 'RSI 策略',
    shortDesc: '基于 RSI 超买超卖判断反转机会的策略。',
    fullDesc: 'RSI 策略在 RSI 进入超买区时卖出，进入超卖区时买入，适合捕捉短期反转。',
    formula: 'RSI ≥ overbought（默认70）→ SELL；RSI ≤ oversold（默认30）→ BUY',
    interpretation: '适合震荡市；在单边趋势中可能过早出场。',
    example: '某 ETF 的 RSI14 跌到 28，触发 BUY；随后 RSI 涨到 72，触发 SELL。',
    relatedPageType: 'strategy_list',
    relatedTerms: ['rsi14', 'mean_reversion', 'momentum'],
  },

  // ===== 回测 =====
  {
    key: 'trade_record',
    title: '交易记录',
    shortDesc: '回测期间策略每次买入卖出的明细清单。',
    fullDesc: '交易记录列出策略在回测期间产生的每一笔交易，包括入场日期、出场日期、入场价、出场价和单笔收益。通过逐笔复盘可以看出策略的止盈止损特点和连续亏损情况。',
    interpretation: '盈利交易占比高说明胜率高；连续多笔亏损可能意味着策略在当前市场环境下失效。',
    relatedPageType: 'backtest_detail',
  },
  {
    key: 'total_return',
    title: '总收益',
    shortDesc: '策略在整个回测期内的累计收益率。',
    fullDesc: '总收益反映策略从回测开始到结束的总体盈利或亏损幅度，不考虑时间长度。',
    formula: '总收益 = (期末净值 - 期初净值) / 期初净值 × 100%',
    interpretation: '正值代表盈利，负值代表亏损。需要结合回测时长看才有意义。',
    relatedPageType: 'backtest_detail',
  },
  {
    key: 'annualized_return',
    title: '年化收益',
    shortDesc: '把总收益按回测时长折算到一年的收益率。',
    fullDesc: '年化收益让不同回测时长的策略具有可比性。回测 6 个月赚 10%，年化收益约为 21%。',
    formula: '年化收益 = (1 + 总收益)^(252 / 回测交易日数) - 1',
    interpretation: '便于横向对比不同策略，但高年化可能来自短期运气。',
    relatedPageType: 'backtest_detail',
  },
  {
    key: 'sharpe_ratio',
    title: '夏普比率',
    shortDesc: '每承担一单位总风险获得的超额收益。',
    fullDesc: '夏普比率把收益和风险放在同一个尺度下比较。数值越高，说明单位风险换来的回报越多。',
    formula: 'Sharpe = (年化收益 - 无风险利率) / 年化波动率',
    interpretation: '>1 通常认为不错，>2 优秀；<0 说明跑输无风险利率。',
    example: '策略 A 年化 12%、波动 8%，夏普约 1.0；策略 B 年化 15%、波动 20%，夏普约 0.55。',
    relatedPageType: 'backtest_detail',
  },
  {
    key: 'win_rate',
    title: '胜率',
    shortDesc: '盈利交易次数占总交易次数的比例。',
    fullDesc: '胜率衡量策略发出信号后盈利的概率。高胜率不一定代表高收益，因为单次盈亏幅度可能差异很大。',
    formula: '胜率 = 盈利交易次数 / 总交易次数 × 100%',
    interpretation: '通常 50% 以上就算不错，但要结合盈亏比一起看。',
    relatedPageType: 'backtest_detail',
  },
  {
    key: 'trade_count',
    title: '交易次数',
    shortDesc: '回测期间策略发出的买卖信号总次数。',
    fullDesc: '交易次数反映策略的活跃程度。次数过多可能意味着过度交易、佣金侵蚀收益；次数过少可能样本不足。',
    interpretation: '结合总收益和胜率看：同样的收益，交易次数越少越好。',
    relatedPageType: 'backtest_detail',
  },
  {
    key: 'nav_curve',
    title: '净值曲线',
    shortDesc: '策略在回测期间每日净值的变化曲线。',
    fullDesc: '净值曲线直观展示策略资金随时间的增长或回撤过程，是评估策略稳定性的重要工具。',
    interpretation: '曲线越平滑向上越好；大幅回撤代表策略在历史上经历过较大亏损。',
    relatedPageType: 'backtest_detail',
  },

  // ===== 筛选 =====
  {
    key: 'screen_presets',
    title: '快速筛选',
    shortDesc: '平台内置的常用筛选条件组合，一键应用。',
    fullDesc: '快速筛选把常用的多条件组合保存为预设，比如“高夏普低波动”“趋势强劲”等，方便用户快速找到目标标的。',
    interpretation: '预设是起点，不是终点。建议在此基础上再根据自己的需求调整。',
    relatedPageType: 'screen',
  },
  {
    key: 'composite_score_filter',
    title: '评分',
    shortDesc: '按综合评分区间筛选 ETF。',
    fullDesc: '通过设置综合评分的最小值/最大值，筛选出在多维度评分体系中处于特定区间的 ETF。',
    interpretation: '分数越高，综合表现越好；但高分标的也可能已经涨幅较大。',
    relatedPageType: 'screen',
  },

  // ===== 标的池 =====
  {
    key: 'snapshot',
    title: '快照记录',
    shortDesc: '保存标的池在某一时刻的成员和权重配置，便于回溯对比。',
    fullDesc: '快照记录把标的池当前的成员、权重和配置信息保存为一个历史版本。你可以在后续随时查看之前的快照，对比组合结构的变化，或在需要时恢复到某个历史状态。',
    interpretation: '建议在调仓前后、策略参数变更后创建快照，形成可追溯的投研日志。',
    relatedPageType: 'pool_detail',
  },
  {
    key: 'equal_weight',
    title: '等权',
    shortDesc: '标的池内所有成员平均分配权重。',
    fullDesc: '等权算法把资金平均分配给池内每只 ETF，不偏向任何一只。实现简单，但忽视了各标的的风险和收益差异。',
    formula: '每只权重 = 100% / 成员数',
    interpretation: '适合对成员没有明显偏好、希望简单分散的情况。',
    relatedPageType: 'pool_detail',
  },
  {
    key: 'score_weighted',
    title: '评分加权',
    shortDesc: '按综合评分占比分配权重，评分越高权重越大。',
    fullDesc: '评分加权算法让综合评分更高的 ETF 占据更大仓位，相当于把“多因子评分”直接映射到仓位配置。',
    formula: '某只权重 = 该只评分 / 池内成员评分总和 × 100%',
    interpretation: '适合相信评分体系、希望让数据驱动仓位的用户。',
    relatedPageType: 'pool_detail',
  },
  {
    key: 'risk_parity',
    title: '风险平价（逆波动率）',
    shortDesc: '按波动率倒数加权的简化风险平价，低波动品种权重更高。',
    fullDesc: '平台当前采用“逆波动率加权（Inverse Volatility）”作为风险平价的简化实现：某只 ETF 的权重与其 20 日波动率成反比。它能在不考虑资产间相关性的情况下，让低波动品种占据更大仓位，从而降低组合整体波动。严格意义上的风险平价（Equal Risk Contribution, ERC）还需要利用协方差矩阵优化，使每只资产对组合风险的边际贡献相等；本平台尚未实现 ERC。',
    formula: '某只权重 ∝ 1 / 该只波动率',
    interpretation: '适合希望降低组合波动、让风险更分散的投资者。注意：该方法忽略资产间相关性，当成员间相关性差异较大时，组合风险可能被低估。',
    example: 'ETF A 波动 5%，ETF B 波动 20%，逆波动率加权下 A 的权重约为 B 的 4 倍。',
    relatedPageType: 'pool_detail',
  },
  {
    key: 'rebalance',
    title: '再平衡提醒',
    shortDesc: '当实际权重偏离目标权重超过阈值时，系统发出调仓提醒。',
    fullDesc: '由于市场价格波动，实际市值权重会偏离目标权重。再平衡功能会按最新收盘价计算实际权重（当前版本按“等股数”假设做简化估算），当偏离幅度超过 10% 时生成提醒。平台目前只生成提醒，不会自动执行买卖；你需要根据提醒自行决定是否调仓。',
    interpretation: '再平衡能纪律性地“高抛低吸”，但过于频繁会增加交易成本。当前估算基于等股数假设，若各标的价格差异较大，估算结果可能与真实持仓有偏差。',
    relatedPageType: 'pool_detail',
  },
  {
    key: 'target_weight',
    title: '目标权重',
    shortDesc: '用户为标的池内每只 ETF 设定的计划持仓权重。',
    fullDesc: '目标权重是你希望每只 ETF 在标的池中占有的比例。所有成员的目标权重之和应为 100%。平台会在保存时自动归一化。',
    interpretation: '目标权重是配置意图的体现，实际市值权重会随市场波动偏离目标，偏离过大时需要再平衡。',
    relatedPageType: 'pool_detail',
  },
  {
    key: 'suggested_weight',
    title: '建议权重',
    shortDesc: '平台根据等权、评分加权或风险平价算法自动生成的权重建议。',
    fullDesc: '建议权重由平台算法根据当前数据计算得出，供你参考。你可以接受建议并保存为目标权重，也可以在此基础上手动调整。',
    interpretation: '不同算法会给出不同建议：等权最简单，评分加权偏向高分标的，风险平价偏向低波动标的。',
    relatedPageType: 'pool_detail',
  },
  {
    key: 'weight_source',
    title: '权重来源',
    shortDesc: '当前权重的生成方式，如手动、等权、评分加权、风险平价。',
    fullDesc: '权重来源标识当前建议权重是通过哪种算法生成的，帮助你追踪权重配置的依据。',
    relatedPageType: 'pool_detail',
  },
  {
    key: 'pool_performance',
    title: '池整体表现',
    shortDesc: '标的池按当前权重加权计算后的收益、夏普、回撤等综合表现（近似值）。',
    fullDesc: '池整体表现把池内各只 ETF 的权重和收益结合起来，计算加权后的 1 月/3 月收益、夏普比率和最大回撤，反映整个组合的历史表现。其中“最大回撤”是各成员历史最大回撤的加权平均，不是按组合净值路径计算的真实组合最大回撤；夏普、收益等指标也是加权近似，供快速参考。',
    interpretation: '组合表现不仅取决于单只 ETF，还取决于权重配置和相关性结构。加权回撤不等于真实组合回撤，若需精确评估，应使用组合净值回测。',
    relatedPageType: 'pool_detail',
  },
  {
    key: 'strategy_type',
    title: '策略类型',
    shortDesc: '量化策略的核心逻辑分类，如动量、均值回归、RSI。',
    fullDesc: '策略类型决定了策略产生买卖信号的基本逻辑。不同策略类型适用于不同的市场环境，参数设置也有所不同。',
    interpretation: '动量适合趋势市场，均值回归和 RSI 更适合震荡市场。',
    relatedPageType: 'strategy_list',
  },
  {
    key: 'correlation_heatmap',
    title: '相关性热力图',
    shortDesc: '展示标的池内各 ETF 收益相关性的可视化图表。',
    fullDesc: '相关性热力图基于近 60 日日收益率计算 Pearson 相关系数。颜色越深，相关性越强。',
    interpretation: '高相关品种会同步涨跌，无法有效分散风险；配置时应尽量纳入低相关或负相关品种。',
    example: '两只科技 ETF 相关系数 0.9，同时上涨或下跌概率高；科技 ETF 与债券 ETF 相关系数可能为 -0.1，分散效果更好。',
    relatedPageType: 'pool_detail',
  },

  // ===== 估值与基本面 =====
  {
    key: 'pe_ttm',
    title: 'PE (TTM)',
    shortDesc: '滚动市盈率，股价除以最近四个季度每股收益之和。',
    fullDesc: 'PE（Price-to-Earnings Ratio）衡量投资者为每单位盈利支付的价格。TTM（Trailing Twelve Months）表示使用最近 12 个月实际盈利数据，比单季度盈利更能反映最新经营状况。',
    formula: 'PE (TTM) = 股价 / 最近四个季度 EPS 之和',
    interpretation: 'PE 越高，市场对未来增长预期越高，也可能意味着估值偏贵；PE 低不一定便宜，可能反映盈利下滑或行业低迷。不同行业 PE 中枢差异大，宜同行业比较。',
    example: '某股价 100 元，近四个季度 EPS 合计 5 元，PE (TTM) = 20 倍。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'pb',
    title: 'PB',
    shortDesc: '市净率，股价除以每股净资产。',
    fullDesc: 'PB（Price-to-Book Ratio）把股价与公司账面净资产对比，常用于评估资产密集型行业（银行、地产、能源）的估值。',
    formula: 'PB = 股价 / 每股净资产',
    interpretation: 'PB < 1 表示股价低于账面净资产，可能被低估，也可能意味着资产质量差或盈利能力弱。高 PB 通常对应轻资产高成长公司。',
    example: '某股价 50 元，每股净资产 25 元，PB = 2 倍。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'roe',
    title: 'ROE',
    shortDesc: '净资产收益率，衡量股东权益的盈利能力。',
    fullDesc: 'ROE（Return on Equity）反映公司用股东投入的资本创造利润的效率，是巴菲特等价值投资者关注的核心指标之一。',
    formula: 'ROE = 净利润 / 平均净资产 × 100%',
    interpretation: '持续高 ROE（如 > 15%）通常说明公司具备护城河或竞争优势；但高负债也可能推高 ROE，需结合杠杆一起看。',
    example: '某公司年度净利润 30 亿元，平均净资产 200 亿元，ROE = 15%。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'eps',
    title: 'EPS',
    shortDesc: '每股收益，净利润分摊到每股股票的金额。',
    fullDesc: 'EPS（Earnings Per Share）是衡量公司盈利能力的直接指标，常用于计算 PE。平台展示的是最新财报期的基本每股收益。',
    formula: 'EPS = 净利润 / 总股本',
    interpretation: 'EPS 同比增长说明盈利在改善；若股本扩张过快，EPS 可能被稀释。',
    example: '某公司净利润 10 亿元，总股本 5 亿股，EPS = 2 元。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'revenue_yoy',
    title: '营收 YoY',
    shortDesc: '营业收入同比增长率，反映业务扩张速度。',
    fullDesc: 'YoY（Year-over-Year）把本期营业收入与去年同期比较，剔除季节性波动，观察公司业务增长趋势。',
    formula: '营收 YoY = (本期营收 - 去年同期营收) / 去年同期营收 × 100%',
    interpretation: '持续正增长说明业务在扩张；增速放缓或负增长需警惕需求下滑。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'grossprofit_margin',
    title: '毛利率',
    shortDesc: '毛利占营业收入的比例，反映产品定价权与成本控制能力。',
    fullDesc: '毛利率 = (营业收入 - 营业成本) / 营业收入。高毛利率通常意味着品牌溢价、技术壁垒或成本优势。',
    formula: '毛利率 = (营收 - 营业成本) / 营收 × 100%',
    interpretation: '毛利率提升说明盈利能力增强；下滑可能源于价格战或成本上升。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'turnover_rate_f',
    title: '换手率（自由流通）',
    shortDesc: '当日成交量占自由流通股本的百分比。',
    fullDesc: '自由流通换手率用成交量除以实际可交易股本（剔除大股东锁定部分），比总股本换手率更能反映市场真实交易活跃度。',
    formula: '换手率（自由流通）= 当日成交量 / 自由流通股本 × 100%',
    interpretation: '换手率高说明交易活跃、关注度高；过高可能伴随短期炒作风险。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'volume_ratio',
    title: '量比',
    shortDesc: '当前成交量与近期平均成交量的比值。',
    fullDesc: '量比衡量相对近期平均水平的放量/缩量程度。值越大，说明当前交易越活跃。',
    formula: '量比 = 当日开盘至今累计成交量 / 过去 5 个交易日同一时段平均成交量',
    interpretation: '量 > 1 表示放量，< 1 表示缩量。放量上涨通常被视为资金介入信号。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'total_mv',
    title: '总市值',
    shortDesc: '公司总股本乘以当前股价，表示整体市场价值。',
    fullDesc: '总市值 = 股价 × 总股本。它反映市场给整家公司的定价，常用于划分大盘、中盘、小盘股。',
    interpretation: '大盘股波动通常较小，小盘股弹性大但流动性风险高。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'circ_mv',
    title: '流通市值',
    shortDesc: '可在二级市场交易的股票市值。',
    fullDesc: '流通市值 = 股价 × 流通股本。它排除了限售股、大股东持股等暂不可交易部分，是判断真实流通盘规模的关键指标。',
    interpretation: '流通市值小的股票更容易被资金推动，波动也更大。',
    relatedPageType: 'instrument_detail',
  },

  // ===== 策略家族 =====
  {
    key: 'trend_following',
    title: '趋势跟踪',
    shortDesc: '顺应价格趋势方向发出买卖信号，追涨杀跌。',
    fullDesc: '趋势跟踪策略认为“趋势会延续”，当价格突破均线或创出新高时买入，跌破趋势时卖出。适合趋势明显的市场。',
    interpretation: '趋势强时收益可观，但在震荡市中容易反复打脸、产生连续亏损。',
    relatedPageType: 'signal_dashboard',
  },
  {
    key: 'volatility',
    title: '波动率策略',
    shortDesc: '基于价格波动幅度或波动率变化生成信号。',
    fullDesc: '波动率策略利用价格波动的扩张/收缩判断趋势或反转机会，例如波动率突破、布林带等。',
    interpretation: '波动率放大常伴随趋势启动；波动率收窄可能预示变盘。',
    relatedPageType: 'signal_dashboard',
  },
  {
    key: 'volume',
    title: '成交量策略',
    shortDesc: '结合成交量放量/缩量辅助判断价格走势。',
    fullDesc: '成交量策略认为“价涨量增”更可靠、“价涨量缩”可能乏力。通过放量确认或缩量背离生成信号。',
    interpretation: '放量突破通常被视为有效信号；缩量回调可能代表洗盘或整理。',
    relatedPageType: 'signal_dashboard',
  },
  {
    key: 'composite',
    title: '复合因子策略',
    shortDesc: '把多个因子综合打分后生成交易信号。',
    fullDesc: '复合因子策略同时考虑动量、价值、质量、情绪等多个维度，按权重合成一个综合得分，再据此发出信号。',
    interpretation: '多因子组合比单一指标更稳健，但因子选择和权重设置会显著影响表现。',
    relatedPageType: 'signal_dashboard',
  },
  {
    key: 'cross_sectional',
    title: '横截面策略',
    shortDesc: '在标的池内做相对强弱排序，选择最强或最弱的标的。',
    fullDesc: '横截面策略不关心单个标的的绝对涨跌，而是比较同一池内各标的在同一因子上的排名，做多排名靠前、做空排名靠后。',
    interpretation: '适合构建多空组合或相对强弱交易；对标的池的代表性要求较高。',
    relatedPageType: 'signal_dashboard',
  },
  {
    key: 'event',
    title: '事件驱动策略',
    shortDesc: '基于分红、公告、财报、定增等事件触发的信号。',
    fullDesc: '事件驱动策略利用特定事件前后的价格规律（如财报超预期、分红除权）生成交易机会。',
    interpretation: '事件窗口期波动大，机会与风险并存；需警惕事件落地后的“利好兑现”回调。',
    relatedPageType: 'signal_dashboard',
  },

  // ===== 信号与数据字段 =====
  {
    key: 'signal_type',
    title: '信号类型',
    shortDesc: '策略生成的方向性建议：买入、卖出或持有。',
    fullDesc: '信号类型表示策略对当前标的的判断。BUY 建议建仓/加仓，SELL 建议减仓/清仓，HOLD 表示没有明确方向、维持现状。',
    interpretation: '同一 (策略, 标的, 交易日) 仅保留一条信号，因此 BUY/SELL 与 HOLD 互斥。',
    relatedPageType: 'signal_dashboard',
  },
  {
    key: 'strength',
    title: '信号强度',
    shortDesc: '0-100 的整数，表示策略对信号的置信度。',
    fullDesc: '信号强度由策略内部规则打分，反映触发条件的偏离程度。数值越高，策略对该信号越有信心。',
    interpretation: '≥ 70 通常视为强信号，40-69 为中性偏弱，< 40 多为噪音。不同策略的 strength 计算方式不同，横向比较时需注意。',
    relatedPageType: 'signal_dashboard',
  },
  {
    key: 'extra_data',
    title: 'extra_data',
    shortDesc: '策略运行时写入的中间指标与参数，用于解释信号来源。',
    fullDesc: 'extra_data 存储生成信号时的关键中间值，例如 RSI 策略的 rsi、均值回归的 z_score、动量策略的 return_n 等。不同策略写入的 key 不同。',
    interpretation: '调试或复盘时可查看 extra_data，作为“为什么生成这条信号”的证据链。',
    relatedPageType: 'signal_dashboard',
  },
  {
    key: 'strategy_type',
    title: '策略类型',
    shortDesc: '策略的核心逻辑分类，决定信号生成方式。',
    fullDesc: '策略类型标识策略属于动量、均值回归、RSI、趋势跟踪、事件驱动等哪一类。同一类型下可创建多个不同参数的策略配置。',
    interpretation: '选择策略类型时要考虑当前市场环境：趋势市用趋势/动量，震荡市用均值回归/RSI。',
    relatedPageType: 'signal_dashboard',
  },
  {
    key: 'family',
    title: '策略家族',
    shortDesc: '对策略类型的归类标签，用于策略库筛选。',
    fullDesc: '策略家族把相似逻辑的策略归为一组，如趋势跟踪、均值回归、动量、波动率、成交量、复合因子、横截面、事件驱动。',
    interpretation: '在策略库中按家族筛选，可快速找到同一大类下的不同策略实现。',
    relatedPageType: 'strategy_list',
  },
  {
    key: 'importance',
    title: '重要性',
    shortDesc: '新闻或报告的重要程度，1-5 星表示。',
    fullDesc: '重要性由采集端或 LLM 根据事件影响范围、标的关联度、市场关注度等因素打分，5 星为最高。',
    interpretation: '高重要性事件更可能引发价格波动或市场情绪变化，值得优先关注。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'sentiment_score',
    title: '情绪分数',
    shortDesc: '反映文本看多/看空程度的数值，范围通常为 -1 到 +1。',
    fullDesc: '情绪分数由 NLP/LLM 对新闻、研报等文本进行分析得出。越接近 +1 越偏乐观，越接近 -1 越偏悲观。',
    interpretation: '> 0.2 通常视为偏多，< -0.2 偏空。情绪分数反映短期共识，不应作为唯一买卖依据。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'match_type',
    title: 'match_type',
    shortDesc: '新闻中标的匹配方式，如代码匹配、名称匹配等。',
    fullDesc: 'match_type 标识资讯与标的的关联方式，帮助区分标题/正文提及、代码精确匹配、同义词匹配等不同来源。',
    interpretation: '精确代码匹配的关联度通常高于正文泛匹配，但具体语义需结合上下文判断。',
    relatedPageType: 'instrument_detail',
  },

  // ===== 情绪看板 =====
  {
    key: 'bull_bear_ratio',
    title: '多空比',
    shortDesc: '看多相关文章数量与看空数量的比值。',
    fullDesc: '多空比 = 看多文章权重 / 看空文章权重。比值 > 1 表示看多力量占优，< 1 则看空占优。',
    interpretation: '多空比极高可能意味着情绪过热，极低可能意味着过度悲观，两者都可能出现短期反转。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'sentiment_heat',
    title: '热度',
    shortDesc: '某标的在近期资讯中被提及的频繁程度。',
    fullDesc: '热度基于相关文章数量计算，反映市场关注度。热度高通常伴随高波动。',
    interpretation: '热度突增往往与事件驱动或情绪爆发有关。',
    relatedPageType: 'instrument_detail',
  },

  // ===== 期货 =====
  {
    key: 'dominant_contract',
    title: '主力合约',
    shortDesc: '成交量或持仓量最大的期货合约，代表该品种当前最活跃的月份。',
    fullDesc: '期货同一品种有多个到期月份合约，主力合约是交易最活跃、流动性最好的合约，通常被用作价格基准。',
    interpretation: '主力合约即将到期时会发生“换月”，价格可能因近远月价差出现跳空。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'settle',
    title: '结算价',
    shortDesc: '交易所根据规则计算出的当日官方收盘价，用于持仓盯市和保证金结算。',
    fullDesc: '结算价通常由收盘前一段时间成交加权平均得出，可能与最后一笔成交价不同。期货的当日盈亏按结算价计算。',
    interpretation: '结算价是保证金、交割、基金净值计算的基础，比简单收盘价更稳定。',
    relatedPageType: 'instrument_detail',
  },

  // ===== 宏观指标 =====
  {
    key: 'cpi',
    title: 'CPI',
    shortDesc: '居民消费价格指数，衡量一篮子消费品和服务的价格变动。',
    fullDesc: 'CPI（Consumer Price Index）是观察通货膨胀水平的核心指标。CPI 同比持续上升意味着通胀压力加大。',
    interpretation: 'CPI 过高可能促使央行加息，过低则提示通缩风险。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'ppi',
    title: 'PPI',
    shortDesc: '工业生产者出厂价格指数，反映工业企业产品出厂价格变动。',
    fullDesc: 'PPI（Producer Price Index）是上游通胀指标。PPI 向 CPI 传导可能影响企业利润和消费者物价。',
    interpretation: 'PPI 上升利好资源类企业，但可能挤压下游制造业利润。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'gdp',
    title: 'GDP',
    shortDesc: '国内生产总值，衡量一个国家或地区经济总量。',
    fullDesc: 'GDP（Gross Domestic Product）反映经济整体规模与增长速度。GDP 同比增速是判断经济周期的关键指标。',
    interpretation: 'GDP 增速回升通常利好风险资产，放缓则可能压制股市盈利预期。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'm2',
    title: 'M2',
    shortDesc: '广义货币供应量，反映社会总流动性。',
    fullDesc: 'M2 包括流通现金、活期存款、定期存款等广义货币。M2 增速代表货币供应扩张速度。',
    interpretation: 'M2 增速回升通常意味着流动性宽松，利好资产价格；过快则可能引发通胀担忧。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'pmi',
    title: 'PMI',
    shortDesc: '采购经理指数，反映制造业景气度。',
    fullDesc: 'PMI（Purchasing Managers\' Index）由新订单、生产、就业、配送、库存等分项合成，50 为荣枯线。',
    formula: 'PMI > 50 表示扩张，< 50 表示收缩',
    interpretation: 'PMI 是领先经济指标，高于预期通常利好股市，低于预期则偏空。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'shibor',
    title: 'SHIBOR',
    shortDesc: '上海银行间同业拆放利率，反映银行间短期资金成本。',
    fullDesc: 'SHIBOR（Shanghai Interbank Offered Rate）是中国货币市场基准利率之一，3 个月 SHIBOR 常用于观察中期流动性松紧。',
    interpretation: 'SHIBOR 上升代表资金紧张，下降代表宽松。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'vix',
    title: 'VIX',
    shortDesc: '芝加哥期权交易所波动率指数，衡量标普 500 期权隐含波动率，被称为“恐慌指数”。',
    fullDesc: 'VIX 反映市场对未来 30 天波动率的预期。VIX 飙升通常伴随市场大跌和避险情绪升温。',
    interpretation: 'VIX > 30 通常表示市场恐慌，< 20 表示情绪平稳。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'fed_funds',
    title: '联邦基金利率',
    shortDesc: '美国银行间隔夜拆借利率目标区间，由美联储设定。',
    fullDesc: '联邦基金利率是美国货币政策的核心基准利率，影响全球资本流动、美元汇率和风险资产定价。',
    interpretation: '加息周期通常压制估值，降息周期利好风险资产。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'unemployment_rate',
    title: '失业率',
    shortDesc: '劳动力中失业人口所占比例，反映就业市场状况。',
    fullDesc: '失业率是经济健康程度的重要指标。失业率低通常意味着经济强劲，但也可能预示工资和通胀压力。',
    interpretation: '失业率意外上升可能促使央行转向宽松，下降则可能支持紧缩。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'treasury_yield',
    title: '国债收益率',
    shortDesc: '政府债券的到期收益率，被视为无风险利率基准。',
    fullDesc: '国债收益率（如美国 10 年期国债收益率）是全球资产定价的锚。收益率上升通常压制股票估值，尤其对成长股。',
    interpretation: '长短期国债收益率倒挂常被视为经济衰退信号。',
    relatedPageType: 'instrument_detail',
  },

  // ===== 交易 =====
  {
    key: 'unrealized_pnl',
    title: '未实现盈亏',
    shortDesc: '当前持仓按最新价计算的浮动盈亏，尚未平仓结算。',
    fullDesc: '未实现盈亏 = (当前价 - 持仓均价) × 持仓数量。只要仓位未平，盈亏只是账面浮动。',
    interpretation: '未实现盈亏随价格波动而变化，不应视为已锁定收益。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'realized_pnl',
    title: '已实现盈亏',
    shortDesc: '已经平仓的交易所产生的实际盈亏。',
    fullDesc: '已实现盈亏是落袋为安的部分，反映账户真实的交易结果。',
    interpretation: '已实现盈亏计入账户现金，是评估策略实际表现的重要依据。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'market_value',
    title: '市值',
    shortDesc: '当前持仓按最新价计算的总价值。',
    fullDesc: '市值 = 当前价 × 持仓数量。它反映当前仓位在市场上的价值。',
    interpretation: '市值随价格波动，是计算仓位占比和风险敞口的基础。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'avg_cost',
    title: '均价',
    shortDesc: '持仓的平均买入成本。',
    fullDesc: '均价 = 总买入成本 / 总持仓数量。多次交易后按加权平均计算。',
    interpretation: '当前价高于均价则浮盈，低于均价则浮亏。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'limit_order',
    title: '限价单',
    shortDesc: '指定价格成交的订单，价格更优但不保证成交。',
    fullDesc: '限价单只有在市场价格达到或优于指定价格时才会成交，适合对价格敏感、愿意承担不成交风险的用户。',
    interpretation: '买入限价单设在市场价下方，卖出限价单设在市场价上方。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'market_order',
    title: '市价单',
    shortDesc: '以当前市场最优价格立即成交的订单。',
    fullDesc: '市价单追求快速成交，不保证成交价格。在流动性差或波动剧烈时可能产生较大滑点。',
    interpretation: '适合急需成交的场景，但需承担滑点风险。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'circuit_breaker',
    title: '熔断',
    shortDesc: '当风险指标触及阈值时自动暂停交易的风控机制。',
    fullDesc: '熔断机制用于防止亏损扩大或异常交易。触发后系统会暂停该交易配置的下单，直到手动重置。',
    interpretation: '熔断能纪律性止损，但也可能在震荡行情中被误触发。',
    relatedPageType: 'instrument_detail',
  },

  // ===== 板块轮动 =====
  {
    key: 'relative_strength',
    title: '相对强弱',
    shortDesc: '某板块收益相对市场平均收益的比值。',
    fullDesc: '相对强弱 = 板块收益 / 市场平均收益。值 > 1 表示跑赢市场，< 1 表示跑输。',
    interpretation: '持续相对强弱 > 1 的板块可能是当前市场主线；轮动策略会增配强势板块。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'rotation_signal',
    title: '轮动信号',
    shortDesc: '板块轮动模型提示的板块强弱切换建议。',
    fullDesc: '轮动信号基于板块收益排名和相对强弱变化，提示哪些板块正在走强或走弱。',
    interpretation: '轮动信号用于资产配置和行业择时，但频繁轮动会增加交易成本。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'momentum_rank',
    title: '动量排名',
    shortDesc: '按近期收益对板块排序得到的名次。',
    fullDesc: '动量排名把各板块按 1 月/3 月收益等维度排序，用于识别当前领涨板块。',
    interpretation: '排名靠前的板块动量较强，但也要结合估值和基本面避免追高风险。',
    relatedPageType: 'instrument_detail',
  },

  // ===== 相关性 =====
  {
    key: 'correlation_method',
    title: '计算方法',
    shortDesc: '相关性分析使用的算法，常见有 Pearson 和 Spearman。',
    fullDesc: 'Pearson 衡量线性相关，Spearman 衡量排名相关。选择不同方法会影响对标的间关系强弱的判断。',
    relatedPageType: 'pool_detail',
  },
  {
    key: 'pearson',
    title: 'Pearson 相关系数',
    shortDesc: '衡量两组数据线性相关程度的指标，范围 -1 到 +1。',
    fullDesc: 'Pearson 相关系数反映日收益率之间的线性关系。+1 完全同向，-1 完全反向，0 无线性关系。',
    interpretation: '高正相关品种无法有效分散风险；负相关或低相关品种能平滑组合波动。',
    relatedPageType: 'pool_detail',
  },
  {
    key: 'spearman',
    title: 'Spearman 相关系数',
    shortDesc: '基于排名的非线性相关指标，范围 -1 到 +1。',
    fullDesc: 'Spearman 用排名的相关性代替原始值，对异常值不敏感，能捕捉单调关系（不限于线性）。',
    interpretation: '当收益率分布有明显偏态或异常值时，Spearman 比 Pearson 更稳健。',
    relatedPageType: 'pool_detail',
  },

  // ===== 收益对比 =====
  {
    key: 'normalized_return',
    title: '归一化收益',
    shortDesc: '把各标的起始价值统一为 100 后计算的累计收益曲线。',
    fullDesc: '归一化收益让不同价格水平的标的在同一起跑线上比较，曲线反映从起点开始的累计涨跌百分比。',
    formula: '归一化值 = (当前价 / 起始价 - 1) × 100%',
    interpretation: '便于直观对比多只标的的相对表现。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'daily_return',
    title: '日收益率',
    shortDesc: '每个交易日相对于前一日的涨跌百分比。',
    fullDesc: '日收益率 = (当日收盘价 - 前一日收盘价) / 前一日收盘价 × 100%。',
    interpretation: '日收益率模式更适合观察波动特征和相关性，而不是累计走势。',
    relatedPageType: 'instrument_detail',
  },

  // ===== 新闻与研究 =====
  {
    key: 'sentiment_confidence',
    title: 'LLM 置信度',
    shortDesc: '大模型对情绪判断的把握程度，0-100%。',
    fullDesc: '置信度反映 LLM 对当前情绪标签和分数的确信程度。高置信度说明文本情绪表达清晰，低置信度则可能语义模糊。',
    interpretation: '置信度高时情绪分数更可靠；置信度低时应结合原文谨慎判断。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'sentiment_drivers',
    title: '情绪驱动',
    shortDesc: 'LLM 提取出的影响情绪的关键事件或主题。',
    fullDesc: '情绪驱动是模型总结的支撑当前看多/看空判断的核心因素，帮助用户理解情绪来源。',
    interpretation: '可作为快速了解新闻焦点的线索，但仍需阅读原文核实。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'note_type',
    title: '研报类型',
    shortDesc: 'AI 研究笔记的类别，如日报、周报、财报反应等。',
    fullDesc: '研报类型标识研究笔记的生成场景和侧重，帮助用户快速了解报告性质。',
    interpretation: '不同类型关注的时间框架和结论侧重点不同。',
    relatedPageType: 'instrument_detail',
  },

  // ===== 加密货币 =====
  {
    key: 'high_24h',
    title: '24h最高',
    shortDesc: '过去 24 小时内达到的最高成交价格。',
    fullDesc: '24 小时最高价反映加密货币在最近一天内的价格上限，常用于观察短期阻力水平。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'low_24h',
    title: '24h最低',
    shortDesc: '过去 24 小时内达到的最低成交价格。',
    fullDesc: '24 小时最低价反映加密货币在最近一天内的价格下限，常用于观察短期支撑水平。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'volume_24h',
    title: '24h成交量',
    shortDesc: '过去 24 小时内的累计成交数量或金额。',
    fullDesc: '24 小时成交量衡量加密货币在最近一天内的交易活跃度。高成交量通常意味着市场关注度高、流动性好。',
    interpretation: '价格上涨伴随成交量放大，趋势更可靠；价格创新高但成交量萎缩，需警惕假突破。',
    relatedPageType: 'instrument_detail',
  },

  // ===== 通用金融概念 =====
  {
    key: 'etf',
    title: 'ETF',
    shortDesc: '交易型开放式指数基金，可在二级市场像股票一样买卖。',
    fullDesc: 'ETF（Exchange-Traded Fund）通常跟踪某个指数，兼具股票的交易便利和基金的分散投资特点。平台覆盖 A 股、美股、港股等多市场 ETF。',
    interpretation: 'ETF 适合进行资产配置、行业轮动和低成本指数化投资。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'qdii',
    title: 'QDII',
    shortDesc: '合格境内机构投资者，允许国内投资者通过基金间接投资境外市场。',
    fullDesc: 'QDII 基金让境内投资者无需开设海外账户即可配置美股、港股、商品、债券等境外资产，但受外汇额度限制。',
    interpretation: 'QDII ETF 可用于分散单一市场风险，但需关注汇率波动和额度限购。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'leverage',
    title: '杠杆',
    shortDesc: '借入资金放大投资规模，同时放大收益和亏损。',
    fullDesc: '杠杆通过借贷或衍生品放大本金 exposure。杠杆 ETF 通常追求每日收益的倍数，长期持有会有复利损耗。',
    interpretation: '杠杆能放大收益，也会加速亏损；不适合长期持有，更适合短期交易。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'discount_premium',
    title: '贴水 / 升水',
    shortDesc: 'ETF 交易价格相对其净值的折价或溢价。',
    fullDesc: '贴水 = 价格 < 净值，升水 = 价格 > 净值。跨境、QDII、商品类 ETF 因外汇额度、交易时差等因素常出现升贴水。',
    interpretation: '高溢价买入意味着以高于实际资产价值的价格建仓，存在溢价回归风险。',
    relatedPageType: 'instrument_detail',
  },
  {
    key: 'implied_volatility',
    title: '隐含波动率',
    shortDesc: '期权市场对未来波动率的预期，由期权价格反推得出。',
    fullDesc: '隐含波动率反映市场对未来不确定性的定价。波动率越高，期权价格越贵。',
    interpretation: '隐含波动率飙升常伴随恐慌情绪；回落则表明市场预期趋于稳定。',
    relatedPageType: 'instrument_detail',
  },
];

const termMap = new Map(entries.map((e) => [e.key, e]));

export function getTerm(key: string): TermEntry | undefined {
  return termMap.get(key);
}

export function hasTerm(key: string): boolean {
  return termMap.has(key);
}

export function getAllTerms(): TermEntry[] {
  return entries;
}
