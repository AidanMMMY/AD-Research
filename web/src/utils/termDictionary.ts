export type HelpPageType =
  | 'score_ranking'
  | 'etf_detail'
  | 'strategy_list'
  | 'backtest_detail'
  | 'screen'
  | 'pool_detail';

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
}

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
    relatedPageType: 'etf_detail',
  },
  {
    key: 'sharpe_1y',
    title: '夏普1年',
    shortDesc: '基于近 1 年数据计算的风险调整后收益指标。',
    fullDesc: '用近 1 年的收益率和波动率计算夏普比率，反映过去一年每承担一单位风险获得的超额收益。',
    formula: 'Sharpe = (年化收益 - 无风险利率) / 年化波动率',
    interpretation: '数值越高越好。>1 通常认为风险补偿较充分。',
    relatedPageType: 'etf_detail',
  },
  {
    key: 'volatility_20d',
    title: '波动率20日',
    shortDesc: '近 20 个交易日收益率的年化标准差，衡量价格波动剧烈程度。',
    fullDesc: '波动率反映资产价格波动的剧烈程度。20 日波动率用最近 20 个交易日数据计算，并年化处理。由于计算允许样本不足（min_periods=5），前几个交易日的波动率可能基于较少样本。',
    formula: 'std(近20日收益率) × √252 × 100%',
    interpretation: '数值越高，价格波动越大，风险也越高。适合用于仓位控制和止损设置。早期数据样本不足时需谨慎参考。',
    example: '波动率 10% 的 ETF 日内波动通常远小于波动率 40% 的行业主题 ETF。',
    relatedPageType: 'etf_detail',
  },
  {
    key: 'max_drawdown_1y',
    title: '最大回撤',
    shortDesc: '近 1 年内从最高点跌到最低点的最大亏损幅度。',
    fullDesc: '最大回撤衡量投资者在过去一年中可能面临的最惨亏损。它是评估下行风险的重要指标。',
    formula: 'Max Drawdown = (历史高点 - 后续最低点) / 历史高点 × 100%',
    interpretation: '回撤越小，持有体验越好。回撤大的品种需要更强的风险承受能力。',
    example: '某 ETF 去年最高净值 1.5，随后最低跌到 1.2，最大回撤为 20%。',
    relatedPageType: 'etf_detail',
  },
  {
    key: 'return_1m',
    title: '1月收益',
    shortDesc: '近 1 个月（约 21 个交易日）的累计收益率。',
    fullDesc: '反映 ETF 短期表现。1 个月窗口对近期趋势敏感，但噪音也较大。',
    interpretation: '正值表示上涨，负值表示下跌。单独看容易受短期情绪影响。',
    relatedPageType: 'etf_detail',
  },
  {
    key: 'return_3m',
    title: '3月收益',
    shortDesc: '近 3 个月（约 63 个交易日）的累计收益率。',
    fullDesc: '反映 ETF 中期表现，比 1 个月更能过滤短期噪音。',
    interpretation: '正值且排名靠前，说明中期趋势较强。',
    relatedPageType: 'etf_detail',
  },
  {
    key: 'return_1y',
    title: '1年收益',
    shortDesc: '近 1 年（约 252 个交易日）的累计收益率。',
    fullDesc: '反映 ETF 中长期表现，是评估一年持有回报的重要参考。',
    interpretation: '长期正收益代表趋势向上，但也要结合回撤和波动一起看。',
    relatedPageType: 'etf_detail',
  },
  {
    key: 'ma5',
    title: 'MA5',
    shortDesc: '5 日移动平均线，反映短期平均成本。',
    fullDesc: 'MA5 是最近 5 个交易日收盘价的平均值，常作为短期支撑或阻力位参考。',
    formula: 'MA5 = (近 5 日收盘价之和) / 5',
    interpretation: '价格在 MA5 上方，短期偏强；跌破 MA5，短期可能转弱。',
    relatedPageType: 'etf_detail',
  },
  {
    key: 'ma20',
    title: 'MA20',
    shortDesc: '20 日移动平均线，反映中期趋势。',
    fullDesc: 'MA20 是最近 20 个交易日收盘价的平均值，常被看作中期趋势的参考线。',
    interpretation: '价格在 MA20 上方且 MA20 向上，中期趋势偏多；反之偏空。',
    relatedPageType: 'etf_detail',
  },
  {
    key: 'bollinger_bands',
    title: '布林带',
    shortDesc: '由中轨（MA20）和上下轨（±2 倍标准差）组成的通道指标。',
    fullDesc: '布林带通过价格的标准差构建波动通道。价格触及上轨可能超买，触及下轨可能超卖。平台使用 MA20 和 2 倍标准差；由于计算时允许样本不足（min_periods=1），前 19 根 K 线的布林带可能基于较少样本，稳定性较差。',
    formula: '中轨 = MA20；上轨 = MA20 + 2 × std20；下轨 = MA20 - 2 × std20',
    interpretation: '通道收窄预示波动即将放大；价格突破上轨或下轨可能意味着趋势延续或反转。早期数据样本不足时需谨慎使用。',
    relatedPageType: 'etf_detail',
  },
  {
    key: 'macd',
    title: 'MACD',
    shortDesc: '异同移动平均线，用于判断趋势方向和动能变化。',
    fullDesc: 'MACD 由快线 DIF、慢线 DEA 和柱状图组成，常用于识别趋势转折和动能强弱。',
    formula: 'DIF = EMA12 - EMA26；DEA = EMA9(DIF)；Histogram = DIF - DEA',
    interpretation: 'DIF 上穿 DEA 为金叉，偏多；DIF 下穿 DEA 为死叉，偏空。柱状图放大代表动能增强。',
    relatedPageType: 'etf_detail',
  },
  {
    key: 'ma10',
    title: 'MA10',
    shortDesc: '10 日移动平均线，反映短期趋势。',
    fullDesc: 'MA10 是最近 10 个交易日收盘价的平均值，介于 MA5 和 MA20 之间，常用于观察短期趋势变化。',
    formula: 'MA10 = (近 10 日收盘价之和) / 10',
    interpretation: '价格站稳 MA10 上方，短期偏强；跌破 MA10 可能进入短期调整。',
    relatedPageType: 'etf_detail',
  },
  {
    key: 'ma60',
    title: 'MA60',
    shortDesc: '60 日移动平均线，反映中长期趋势。',
    fullDesc: 'MA60 是最近 60 个交易日收盘价的平均值，常被看作季度趋势的参考线，也常被称为“生命线”。',
    formula: 'MA60 = (近 60 日收盘价之和) / 60',
    interpretation: '价格在 MA60 上方且 MA60 向上，中长期趋势偏多；有效跌破 MA60 可能意味着趋势转弱。',
    relatedPageType: 'etf_detail',
  },
  {
    key: 'kline',
    title: 'K 线图',
    shortDesc: '用蜡烛线展示开盘价、收盘价、最高价、最低价的行情图表。',
    fullDesc: 'K 线图（Candlestick Chart）每根蜡烛代表一个时间周期，实体表示开盘到收盘的涨跌，上下影线表示该周期的最高最低价。',
    interpretation: '阳线（通常红色）表示收盘价高于开盘价，阴线（通常绿色）表示收盘价低于开盘价。长上影线说明上方抛压大，长下影线说明下方有支撑。',
    relatedPageType: 'etf_detail',
  },
  {
    key: 'time_range',
    title: '时间范围',
    shortDesc: 'K 线图展示的历史交易日数量。',
    fullDesc: '时间范围决定 K 线图上显示多少根蜡烛。范围越短，越能看清近期细节；范围越长，越能把握中长期趋势。',
    interpretation: '30 日/60 日适合短期交易参考；120 日/250 日适合中长期趋势判断。',
    relatedPageType: 'etf_detail',
  },
  {
    key: 'ai_analysis',
    title: 'AI 分析',
    shortDesc: '基于历史数据和文本信息的自动化分析结论。',
    fullDesc: 'AI 分析模块利用大语言模型对 ETF 的技术指标、市场情绪、研究笔记等信息进行整合，生成可读性较强的分析结论。',
    interpretation: 'AI 分析是辅助参考，不构成投资建议。重要决策仍需结合自己的判断和风险承受能力。',
    relatedPageType: 'etf_detail',
  },
  {
    key: 'ai_research_note',
    title: 'AI 研究笔记',
    shortDesc: '平台自动生成的关于某只 ETF 的研究摘要报告。',
    fullDesc: 'AI 研究笔记基于公开数据、技术指标和市场信息，由大语言模型生成的简短研报。可以点击“生成研报”按钮重新生成。',
    interpretation: '研究笔记提供快速概览，但不能替代深度研究和尽职调查。',
    relatedPageType: 'etf_detail',
  },
  {
    key: 'market_sentiment',
    title: '市场情绪',
    shortDesc: '基于相关新闻或研报文本计算出的看多/看空/中性倾向分数。',
    fullDesc: '市场情绪通过自然语言处理分析近期相关文本，给出一个 -1 到 +1 之间的情绪分数。越接近 +1 越偏乐观，越接近 -1 越偏悲观。',
    interpretation: '情绪指标反映市场短期共识，常用于判断是否存在过热或过冷风险，但不应作为唯一买卖依据。',
    relatedPageType: 'etf_detail',
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
