# 资深量化研究员审查报告

> 审查范围：策略引擎、回测引擎、归因与信号、风险与指标、数据源、模拟/实盘交易
> 视角：私募/对冲基金专业量化（数据正确性、前瞻偏差、生存偏差、过拟合防护、统计显著性、基准对比、风险度量、交易成本、组合级一致性）
> 结论：**该平台目前只能算"教学/演示级"量化回测**，缺少专业量化所必需的多种能力：真实基准 alpha/beta/IR、Sortino/Calmar/VaR/CVaR、最大回撤持续期、波动率归因、蒙特卡洛稳健性、参数敏感性、统计显著性检验、组合级回测、做空机制、市场冲击模型、停牌处理、多空再平衡、停盘价/Volume-weighted slippage、benchmark 分红再投入、跨年化、t-stat 等。
> 我已严格只读，没有修改任何代码。

---

## 一、问题清单

### P0 阻塞级（专业量化不可接受的基础缺陷）

#### 1. Sharpe 比率计算忽略用户传入的 `risk_free_rate`，永远使用 0.02 默认值
- **位置**：`app/services/backtest_engine.py:402`
- **问题描述**：
  ```python
  sharpe = (annual_return - risk_free_rate_default()) / annual_vol
  ```
  `run_backtest` 接收 `risk_free_rate: float = 0.02` 参数并写入 `result.metrics["risk_free_rate"]`，但 `_simulate` 内部计算 Sharpe 时却调用 `risk_free_rate_default()` 而不是接收用户参数。即使前端传 3% 或动态读取 10Y CGB 利率，计算结果依然按 2% 计算 → Sharpe 显著偏低（A 股牛市中可低 0.3-0.5）。
- **专业影响**：风险溢价全部错位 → 策略排名错位 → 误选负 alpha 策略。私募晨星/Barra 风格归因直接错。
- **建议修复**：把 `risk_free_rate` 传进 `_simulate`，Sharpe 公式改为 `(annual_return - risk_free_rate) / annual_vol`。
- **优先级**：P0

#### 2. BacktestEngine 完全不支持做空（short side）
- **位置**：`app/services/backtest_engine.py:79-104`（Trade 类）、`backtest_engine.py:282-356`（_simulate 主循环）
- **问题描述**：Trade 类的 `side` 字段只接收 `"long"`，`_simulate` 在 `signal == -1` 时永远被解读为"SELL 多头平仓"。所有"-1 信号"被解释为平多信号而非做空。同时 ZScoreReversion / BBMeanReversion / DonchianBreakout 在趋势反转时 SELL 信号直接被多空单边系统覆盖，cross-sectional 的 `MomentumRankStrategy` 排名后 N 全部失效。
- **专业影响**：
  - 多空对冲、统计套利、配对交易、市场中性策略**完全无法回测**。
  - 因子测试无法做空头端 alpha。
  - momentum_rank 的 bottom_n SELL 完全没意义（"卖空"在 A 股融券是真实的）。
- **建议修复**：
  1. Trade 改为支持 side ∈ {"long", "short"}，并维护 `long_qty`、`short_qty` 双仓。
  2. _simulate 区分信号进入多/空/平多/平空。
  3. 增加 `allow_short: bool` 参数；关闭时 -1 信号仍只平多。
- **优先级**：P0

#### 3. 没有真实基准（HS300 / CSI500 / CSI1000），归因模型只能用标的自身做 benchmark
- **位置**：`app/services/attribution_service.py:30-47`、`app/services/backtest_service.py`（无 benchmark 字段）
- **问题描述**：
  - `AttributionService._calculate_benchmark_return` 用的是**回测标的本身**的 buy-and-hold adj_close 计算基准。等于和策略自己比 → "excess_return" 完全无意义（应为 0 或接近 0）。
  - 整个平台不存在沪深 300 / 中证 500 / 中证 1000 / 创业板指 / 行业指数的注册表或导入通道。
  - `BacktestResult.metrics` schema 没有任何 benchmark、alpha、beta、IR 字段。
- **专业影响**：
  - Brinson 归因的 allocation_effect/selection_effect 计算出来是无意义的零和游戏。
  - 没有任何 alpha 衡量（业内公认 CAPM-based alpha 是策略评估最基础指标）。
  - 信息比率 IR 完全无法计算。
- **建议修复**：
  1. 引入 `Benchmark` 表，code 命名规范化（如 `000300.SH`=HS300，`000905.SH`=CSI500）。
  2. `BacktestResult.metrics` 增加 `benchmark_code`, `alpha`, `beta`, `ir`, `tracking_error`, `up_capture`, `down_capture`。
  3. attribution_service 允许指定 benchmark_code，重写归因逻辑。
- **优先级**：P0

#### 4. 缺少年化交易日与闰年/自然日区分 → annualization 错误
- **位置**：`app/services/backtest_engine.py:418-420`
- **问题描述**：
  ```python
  trading_days = len(df)
  years = trading_days / 252 if trading_days > 0 else 1
  annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 and total_return > -1 else total_return
  ```
  - `trading_days = len(df)` 假设 df 全部是交易日，但 A 股实际一年 244 个交易日，平台硬编码 252（美股/港股标准）。
  - 当 total_return ≤ -1（即净值 ≤ 0）时直接返回 `total_return`（不年化），但年化负 100% 完全没意义 → silent failure。
  - 无日历维度区分（A 股用 244、港股 245、加密 365）。
- **专业影响**：跨市场横向对比、年化 Sharpe、跨期对比完全失真；加密标的年化使用 252 严重低估。
- **建议修复**：根据 `market` 选择 trading_days_per_year；负 total_return 时记录告警而非吞掉。
- **优先级**：P0

#### 5. 风险指标严重不全（缺 Sortino、Calmar、VaR、CVaR、最大回撤持续期）
- **位置**：`app/data/indicators/risk.py` 全文、`app/services/backtest_engine.py:386-441`（metrics 输出）
- **问题描述**：metrics dict 只输出 14 个字段：
  - `total_return, annualized_return, max_drawdown, sharpe_ratio, win_rate, trade_count, avg_win, avg_loss, trading_days, ...`
  - **缺失**：Sortino（下行风险调整收益）、Calmar（年化收益/最大回撤）、VaR / CVaR（尾部风险）、最大回撤持续期/恢复期、Omega ratio、Calmar ratio、Sortino、tail ratio、skewness/kurtosis。
  - 私募产品评级体系必备的三个比率全部缺失。
- **专业影响**：合规与产品尽调立即打回；研究侧无法判断"赚的是 alpha 还是 risk premium"。
- **建议修复**：增加 Sortino（ddof=1, 下行标准差）、Calmar（annualized_return / |max_drawdown|）、historical VaR（5%）、CVaR（5%）、max DD duration（peak 到 recovery 的 bar 数）、gain/pain ratio。
- **优先级**：P0

#### 6. Walk-Forward 没有重选参数逻辑 = 伪 OOS（过度乐观的 OOS 估计）
- **位置**：`app/services/backtest_engine.py:561-677`
- **问题描述**：`run_walk_forward` 在每个 fold 跑 train/test 段，但 train 段结果只用来计算 IC，并未在 train 段做参数搜索/选择再应用到 test 段。等于 "用同一参数跑两遍"，得到的 test 段结果不是真正的样本外。
- **专业影响**：
  - 平台宣称的 "out-of-sample" 完全是 in-sample 的别名。
  - 这是过拟合防护的核心失效点，比没有 walk-forward 还危险（给用户虚假安全感）。
- **建议修复**：
  1. 引入 param grid（per-strategy）+ train 段网格搜索（基于 Sharpe / Calmar / IR 选最优）。
  2. test 段用 train 段选出的 best_params，而非原始 params。
  3. 增加 embargo period（train/test 边界 +/- 5 个 bar），避免 look-ahead leakage。
  4. 报告每个 fold 选中的参数。
- **优先级**：P0

#### 7. 无蒙特卡洛稳健性 / Bootstrap 置信区间 → 不知 Sharpe 是否显著
- **位置**：`app/services/backtest_engine.py` 全文未发现 `bootstrap` / `monte_carlo` / `permutation` / `resample`
- **问题描述**：完全没有 bootstrap 抽样（block bootstrap for time series）、sharpe 显著性检验（Lo's Macaulay / Jobson-Korkie with Memmel z-stat）、参数敏感性扫描、随机化基准对比。
- **专业影响**：10 笔交易的 Sharpe 2.0 与 1000 笔的 Sharpe 0.5 无法区分；根本无法判断策略是否显著优于随机。
- **建议修复**：
  1. 增加 `monte_carlo_simulation(n=1000, block_size=21)`，对每日收益做 block bootstrap，输出 Sharpe、MaxDD 的 5/95 分位。
  2. 增加 `sharpe_significance_test`，输出 t-stat、p-value。
  3. 增加 `param_sensitivity(param_name, range)` 扫描网格，输出 heatmap 数据。
- **优先级**：P0

#### 8. 信号生成时刻的 lookahead / 数据隔离缺失
- **位置**：`app/services/strategy_engine.py:47-82`（`run_strategy_on_instrument`）、`app/strategies/cross_sectional.py:79-103`（MomentumRankStrategy.generate_universe）
- **问题描述**：
  1. `_fetch_bars` 用 `end_date=trade_date` 但**没限定 "trade_date 当日 bar 不可见"**。如果数据里有 trade_date 当日的完整 bar（含 close），策略就直接用 close 生成信号 → classic look-ahead bias。
  2. cross_sectional 的 `generate_universe` 对所有 etf 用 `df.sort_values("trade_date").groupby("etf_code").last()`，同样包含 trade_date 当日 bar。
  3. EOD 数据源 + 早盘生成信号的真实场景里，盘前只能用昨天及之前的 bar。
- **专业影响**：回测与实盘信号生成口径不一致 → 严重 look-ahead bias，预期收益虚高 30%-300%。
- **建议修复**：
  1. `_fetch_bars` 改为 `end_date=trade_date - 1 trading_day`，用上一交易日作为信号基线。
  2. cross_sectional 也限制到 `trade_date` 之前。
  3. 增加 "as_of" cutoff 参数明确语义。
- **优先级**：P0

#### 9. PaperTradingService.auto_trade 缺风控与限额 → 真实跑会乱下单
- **位置**：`app/services/paper_trading_service.py:616-689`
- **问题描述**：
  ```python
  allocation = equity * Decimal("0.1")
  quantity = allocation / market_price
  ```
  - BUY 永远是当前 equity 的 10%，没有按信号 strength 缩放（强信号不应 = 弱信号）。
  - 同一日多条 BUY 信号会**重复占仓**，最多可建满 N × 10% 仓位 → 实际杠杆远超预期。
  - 没有 cash buffer / 最小现金预留 / 单标的上限 / 行业集中度限制。
  - 单日 SELL 后再 BUY 同标的，无冷却期。
- **专业影响**：模拟账户与真实账户行为不一致；paper→live 迁移时极易爆仓或超限。
- **建议修复**：
  1. 按 signal.strength 缩放 allocation（50 strength = 5%, 100 strength = 15%）。
  2. 增加单标的 single-position cap（默认 20%）。
  3. 增加 cash buffer（5% 现金永不投入）。
  4. 增加 max_concurrent_positions 上限。
- **优先级**：P0

#### 10. 风控仅覆盖 live trading，paper trading 完全无风控
- **位置**：`app/services/paper_trading_service.py:163-289`（place_order） vs `app/services/risk_control.py`
- **问题描述**：
  - `place_order` 只检查账户余额、持仓、limit price，**没有 daily loss / max position / drawdown / circuit breaker**。
  - 任何 authenticated user 可对 paper 账户下任何规模订单（哪怕 initial_balance = 1 USDT）。
  - 风控模块 `RiskControl` 仅在 `live_trading.py:place_order` 中调用，paper 完全绕过。
- **专业影响**：paper→live 迁移时用户的肌肉记忆不一致，paper 训练无效；paper 账户可被滥用。
- **建议修复**：把 RiskControl 的 check_order 同时接入 paper_trading.place_order；至少加上 daily loss / single-position cap / max_order_value。
- **优先级**：P0

---

### P1 严重级（专业量化应具备但缺失）

#### 11. 策略完全基于 close，未考虑复权/分红/拆股的策略一致性
- **位置**：`app/data/repositories/price_repository.py:17-27`、`app/services/strategy_engine.py:36-44`
- **问题描述**：
  - `adj_close = close * adj_factor`，但 `adj_factor` 来源仅在 `InstrumentDailyBar.adj_factor` 列。
  - `_compute_adj_close` 对 `adj_factor` 为 None 时填 1.0，**没有强制要求数据源必填 adj_factor**（数据缺失会沉默退化为 close）。
  - 策略代码（如 mean_reversion 的 z-score、BB、MACD）使用 `df["close"]`，由 strategy_engine 显式重命名为 `adj_close`，看似正确。但 cross_sectional 用 `df["close"].pct_change(window)` 计算动量时——`pct_change` 同样作用于 adj_close → 正确。但 MomentumRankStrategy 在 `group.tail(rank_window + 1)` 取的是 adj_close，OK。
  - **关键问题**：数据缺失时（adj_factor = 1.0）所有指标都用 close 计算，但此时可能含未复权的跳空（分红、增发），指标全错。
- **专业影响**：分红季信号错乱；A 股每年 6-7 月分红集中，回测期内可能产生 5%-15% 的系统性误差。
- **建议修复**：
  1. 强制要求数据源 adj_factor 非空，缺失则触发数据质量告警。
  2. 策略文档明确标注依赖 adj_close。
  3. 增加 backtest engine 单元测试：含除权除息 bar 时，结果应与不复权有显著差异。
- **优先级**：P1

#### 12. 交易成本模型缺市场冲击 / 部分成交 / 滑点动态化
- **位置**：`app/services/backtest_engine.py:36-39`、`backtest_engine.py:163-183`
- **问题描述：
  - 当前 friction = 固定 0.001 commission + 0.0005 stamp duty（卖）+ 0.00001 transfer fee + ¥5 minimum。
  - **完全没有**：
    - 市场冲击（market impact）—— 大单成交价偏离；
    - 部分成交（partial fill）模拟；
    - 滑点按量动态化（小单 1bp、大单 10bp）；
    - 流动性约束（可用 volume = 日均成交量 × participation cap）；
    - bid-ask spread（A 股 ETF 普遍 1-5bp，LOF/分级可达 50bp）。
- **专业影响**：大规模策略（>100 万 / 单笔）回测虚高收益 1-3%；大资金进入 paper→live 直接滑点爆亏。
- **建议修复**：
  1. 引入 square-root impact 模型 `impact = σ * sqrt(qty / adv) * k`。
  2. 引入 participation cap（默认 5% ADV）。
  3. 暴露 bid-ask spread 参数。
- **优先级**：P1

#### 13. Backtest 不支持组合级回测 / 多标的 portfolio rebalance
- **位置**：`app/services/backtest_engine.py:456-553`
- **问题描述：`run_backtest` 仅支持 `etf_code: str`（单标的）。没有 portfolio backtest 接口。
- **专业影响**：
  - cross_sectional 策略（MomentumRankStrategy）无法回测 → generate_universe 返回信号但引擎不支持多标的资金分配。
  - 因子组合、风险预算、行业中性都无法做。
  - 整个 backtest 体系只能做 single-name 择时，**完全无法做组合管理**。
- **建议修复**：
  1. 增加 `run_portfolio_backtest(etf_codes, weights_method, rebalance_freq)`，支持等权 / 信号强度加权 / 风险平价 / 最小方差。
  2. 增加组合级 metrics：组合 IR、exposure、行业占比、turnover、concentration (HHI)。
  3. 增加 sector neutralization / factor neutralization 选项。
- **优先级**：P1

#### 14. BacktestEngine 无停牌 / 涨跌停 / 流动性筛选
- **位置**：`app/services/backtest_engine.py:45-76`、`price_repository.py:65-114`
- **问题描述：
  - 数据库没有 `is_suspended`, `upper_limit`, `lower_limit`, `volume_zero`, `trading_status` 字段（仅 trade_date/open/high/low/close/volume/amount/change_pct/turnover_rate/adj_factor）。
  - 没有 calendar 过滤（交易日历）。
  - 回测时若某日 volume = 0 但 close = prev_close（停牌日的填充），策略会照常生成信号。
  - A 股涨停（+10%）后次日开盘的 gap-down 没法模拟。
- **专业影响**：
  - 策略会被停牌日的虚假 close 误导；
  - 涨跌停无法成交导致 backtest 报单成交实际不会成交（但平台当作成交了）。
- **建议修复**：
  1. 数据库增加 `is_suspended`, `limit_up`, `limit_down` 字段（或由 change_pct 推断）。
  2. 回测模拟器：若当日触及涨跌停或停牌，BUY/SELL 信号不成交。
  3. 增加 turnover_rate 流动性过滤（默认要求 ≥ 0.5%）。
- **优先级**：P1

#### 15. Backtest 不区分建仓冷却、再加仓、连续信号去重
- **位置**：`app/services/backtest_engine.py:282-356`（_simulate 主循环）
- **问题描述：
  - 同一日出现连续 BUY 信号（如 BOLL 突破 + MACD 金叉 + Momentum 共振）→ 当日仓位不变（已经满仓）但仍记录"伪 BUY"。
  - 无 `cooldown_days` 参数（信号冷却期）。
  - 无 `max_position_increase_per_day` 限制。
  - 加仓时按 `position_size` 重新计算（`capital * position_size`），但上一笔的 cash 已经被 lock → 第二次信号时分母（capital）变小，加仓金额自动缩 → 这与现实"维持固定仓位比例"的语义不符。
- **专业影响**：信号共振日的策略表现被高估（多个信号产生多次 BUY 噪声）。
- **建议修复**：
  1. 同一日同标的同 type 信号去重。
  2. 增加 `cooldown_days` 参数。
  3. 加仓时按目标权重计算补足金额，不是按当前可用现金的 position_size。
- **优先级**：P1

#### 16. ATR/MACD/OBV 计算对 NaN/极端值处理不一致
- **位置**：`app/data/indicators/technical.py:36-52`（RSI）、`technical.py:77-101`（ATR）、`volume.py:114-122`（OBV）
- **问题描述：
  - `calc_rsi` 用 Wilder 平滑，**当 avg_loss = 0（持续上涨）时**用 `rsi.where(avg_loss > 0, 100.0)` → 永远输出 100。这导致在持续上涨行情中 RSI 永远 = 100，RSI 策略无法生成 SELL 信号（无超买信号）。
  - `calc_atr` 用 Wilder 平滑，`min_periods=window` 但**没有处理 close NaN** → ATR 在缺数据日会污染整条序列。
  - OBV 用 `pd.Series(0.0, index=df.index)` 初始化，对 close_diff=0 的 bar 不增不减（标准）——但若 close 含 NaN，diff 后是 NaN，OBV 累计用 NaN → 后续全部变 NaN。
- **专业影响**：策略在单边趋势市失效（RSI 永远 100），用户得不到 SELL；NaN 传染让回测静默失败。
- **建议修复**：
  1. RSI 在极端市仍要允许短期回落到 99 → 给一个小阈值或 lookback saturation。
  2. ATR/OBV 显式 `fillna(0)` 在累计之前。
- **优先级**：P1

#### 17. event-driven 策略的 lookback_days × n_bars 性能陷阱
- **位置**：`app/strategies/event.py:140-152`
- **问题描述：`generate_series` 用 `df.iterrows()` 对每根 bar 调一次 `EventDataService.get_news_sentiment(code, as_of, lookback)`。如果回测 3 年 × 250 bar/年 = 750 次单条 SQL 查询（event-sentiment 表通常有 100K+ 行/标的）→ 单次回测可达 10-30 分钟。
- **专业影响**：
  - 任何 batch 调度或 walk-forward 都会卡死；
  - 没有 batch query 接口；
  - `iterrows()` 本身在 50K 行+ 时比 vectorize 慢 100x。
- **建议修复**：
  1. 预取所有 sentiment 一次性写入 dict。
  2. 用 vectorized rolling mean 计算。
  3. 增加 DB 索引 `(etf_code, trade_date)`。
- **优先级**：P1

#### 18. BacktestEngine 的 `signal_strength` 仅在 absolute value 模式记录 → IC 失效
- **位置**：`app/services/backtest_engine.py:306-313`（BUY signal 记录）、`_compute_ic:716`
- **问题描述：
  ```python
  "signal_strength": abs(signal),  # BUY 时记录 abs(1) = 1
  ```
  - BUY 时 `signal = 1`（恒定），SELL 时 `signal = -1`（恒定），所有 signal_strength = 1，无信息含量。
  - 真正策略输出的 `strength` (0-100) 在主循环里**没有被持久化到 result.signals**。
  - `_compute_ic` 算的是 abs(signal_strength) 与 daily_returns 的相关性 → 永远是 0 或接近 0 → IC 失效。
- **专业影响**：walk-forward 的 IC 报告无意义（恒为 0），用户误以为是 alpha 缺失。
- **建议修复**：
  1. `result.signals` 持久化原始 strategy.strength（0-100）。
  2. IC 改用 strength 作为信号强度。
- **优先级**：P1

#### 19. ETF/股票分类标记缺失 → 策略可能误用于不可融券标的
- **位置**：`app/services/strategy_engine.py`、`app/strategies/cross_sectional.py:108-110`（bottom_n SELL）
- **问题描述：MomentumRankStrategy 返回的 bottom_n SELL 信号——但 A 股**大部分 ETF 不可融券**（仅部分 ETF 支持两融）。short 信号会在 paper/live 阶段 100% 失败。
- **专业影响**：cross_sectional 策略的 SELL 端 100% 不可执行；回测与实盘背离。
- **建议修复**：
  1. 在 ETFInfo 增加 `is_marginable` / `is_shortable` 字段。
  2. signal generation 时检查该字段，无 shortable 时 SELL 信号降级为 "skip" 或 "HOLD"。
- **优先级**：P1

#### 20. 缺少交易成本 benchmark 对比（baseline strategy）
- **位置**：`app/services/strategy_comparison_service.py:19-62`
- **问题描述：`compare_backtests` 只比较已存 backtest 的 metrics，但**没有任何 baseline strategy 自动生成**：
  - 没有 buy-and-hold benchmark 自动 run；
  - 没有 equal-weight portfolio benchmark；
  - 没有 60/40 股债 benchmark；
  - metrics dict 没有 `alpha`, `beta`, `ir`（参见 P0#3）。
- **专业影响**：用户无法回答"我的策略是否真的比买 ETF 强"。
- **建议修复**：每次 run_backtest 自动跑 3 个 baseline（buy-and-hold, equal-weight, 等额 + 沪深 300），输出对比表。
- **优先级**：P1

#### 21. Position sizing 简单粗暴（固定 position_size），无 Kelly / 波动率倒数加权
- **位置**：`app/services/backtest_engine.py:284-299`
- **问题描述：
  ```python
  cash_to_deploy = capital * position_size  # position_size=1.0 时全仓
  position = net_cash_to_invest / price
  ```
  - `position_size=1.0` 默认全仓进入单标的 → 集中度风险巨大。
  - 无波动率倒数加权（risk parity）。
  - 无 Kelly criterion (`f* = (p*b - q)/b`)。
  - 无基于 ATR 的波动率止损仓位。
- **专业影响**：风险调整后收益（risk-adjusted return）严重失真；同样策略在不同波动率期无法对比。
- **建议修复**：
  1. 增加 `position_sizing_method ∈ {fixed, kelly, volatility_inverse, atr_based}`。
  2. 默认 volatility_inverse，position size = target_vol / current_vol × max_pos。
- **优先级**：P1

#### 22. 风险敞口归因（volatility/因子归因）缺失
- **位置**：`app/services/attribution_service.py` 全文
- **问题描述：归因模型只实现了 "allocation/selection/interaction"（简化 Brinson），完全没有：
  - 因子归因（Barra-style：size, value, momentum, quality, volatility, growth）；
  - 波动率归因（每条 bar 的波动率贡献来源）；
  - 行业归因（GICS / SW 一级行业）；
  - Beta / 风格暴露归因。
- **专业影响**：私募合规、产品尽调、LP 报告必备，但平台完全缺失。
- **建议修复**：引入 Barra 风险模型（或简化的 Fama-French 三/五因子）。
- **优先级**：P1

---

### P2 应改进（专业团队会纳入 roadmap）

#### 23. BacktestResult 未保存 daily_nav，仅保存 trades
- **位置**：`app/services/backtest_service.py:148-149`
  ```python
  "daily_nav": [],  # Not persisted to save space
  ```
- **问题**：trades 持久化但 daily_nav 不持久 → 前端画 equity curve 必须重跑引擎（无法即时查询历史净值曲线）。trades 列表长达数千时 JSON 反序列化慢。
- **建议**：daily_nav 存到独立表（用 timeseries 压缩如 Gorilla）或 clickhouse；至少提供 trades → NAV 的 fast reconstruction。
- **优先级**：P2

#### 24. BacktestEngine 的 IC 计算忽略时间序列自相关 → 显著性虚高
- **位置**：`app/services/backtest_engine.py:696-736`
- **问题：`_compute_ic` 直接 `np.corrcoef(sig_strength, daily_returns)`，但日收益高度自相关（AR(1) 系数常 0.05-0.2）。显著性检验应该用 Newey-West HAC 标准误，而非 naive Pearson。
- **建议**：用 Newey-West HAC t-stat 或 block bootstrap p-value。
- **优先级**：P2

#### 25. 无 benchmark 分红再投入处理 → benchmark_return 偏低
- **位置**：`app/services/attribution_service.py:30-47`
- **问题：`_calculate_benchmark_return` 用 adj_close。adj_close 已对分红做除权处理，**buy-and-hold 直接用 adj_close 计算会得到含分红的 total return**，但实际基准是"价格回报"还是"总回报"语义混乱。
- **建议**：明确区分 price_return（用未复权 close）和 total_return（用 adj_close），归因报告两个。
- **优先级**：P2

#### 26. Strategy Library UI 暴露 parameter 但没暴露 friction / execution price model
- **位置**：`web/src/pages/SignalDashboard/`、`app/services/backtest_engine.py:456-499`
- **问题：前端 UI 暴露 strategy_type + params，但**用户无法在 UI 配置**：
  - commission_rate / slippage_rate / market
  - execution_price_model（"open"/"close"/"next_open"）
  - initial_capital / position_size
- **建议**：在 BacktestCreate schema 暴露这些字段，UI 增加 Advanced Settings。
- **优先级**：P2

#### 27. calc_ma / calc_bollinger 使用 min_periods=1 → SMA 早期不可信
- **位置**：`app/data/indicators/technical.py:21`、`technical.py:117-121`
- **问题：`series.rolling(window=window, min_periods=1).mean()` 在前 N 个 bar 用不足窗口的数据计算 SMA。在策略里用于 MA crossover、BB 信号时，最早 N 个信号是基于不全数据生成的（虽然 bars_needed 通常拦截了，但 min_periods=1 是兜底陷阱）。
- **建议**：min_periods=window；早期返回 NaN 由策略层过滤。
- **优先级**：P2

#### 28. BacktestEngine `_simulate` 使用 `for i, row in df.iterrows()` → 性能瓶颈
- **位置**：`app/services/backtest_engine.py:263`
- **问题：`iterrows()` 对万行级 DataFrame 比 vectorize 慢 50-100x。组合级回测（10 标的 × 3 年）会非常慢。
- **建议**：用 `for i in range(len(df)):` + `df.iloc[i]` 或 Numba JIT 化核心循环。
- **优先级**：P2

#### 29. BacktestEngine 没有除零保护 → NaN 蔓延
- **位置**：`app/services/backtest_engine.py:408-411`
  ```python
  avg_win = sum(t.pnl_pct for t in result.trades if t.pnl_pct > 0) / wins if wins > 0 else 0
  avg_loss = sum(...) / (len(...) - wins) if len(...) > wins else 0
  ```
  - 当 wins = 0 或所有 trade 都亏损 → avg_loss 分母为 0。
  - `wins = sum(1 for t in result.trades if t.pnl_pct > 0)` 如果结果 trades 是空 → `wins = 0` → avg_win 已被 ternary 保护。
  - 但 `(len(result.trades) - wins) == 0` 即全是 win → 分母 0 → ZeroDivisionError。
- **建议**：分母检查 + 用 NaN 替代 0。
- **优先级**：P2

#### 30. EventDrivenStrategy 固定阈值（0.6/0.4）但没暴露
- **位置**：`app/strategies/event.py:22-24`
- **问题：`_BUY_THRESHOLD = 0.6, _SELL_THRESHOLD = 0.4` 写死，ParamSpec 没暴露。
- **建议**：加 `buy_threshold`, `sell_threshold`, `min_events` 到 param_specs。
- **优先级**：P2

#### 31. live_trading 的 risk control 不支持 paper-trading 模拟账户
- **位置**：`app/services/risk_control.py` 全文
- **问题：RiskControl 完全围绕 live_trading 设计（max_daily_loss、circuit_breaker 内存存储），没有 paper_trading 集成入口。
- **建议**：抽象 RiskControl 接口，让 paper_trading_service 也调用同一套。
- **优先级**：P2

#### 32. BacktestService 持久化 trades 时丢精度
- **位置**：`app/services/backtest_service.py:73-84`
  ```python
  "pnl": round(t.pnl, 2),
  "pnl_pct": round(t.pnl_pct * 100, 2),
  ```
- **问题：把 pnl 截到 2 位小数、pnl_pct 也截到 2 位。日收益可能是 0.005% → 截断后丢失。trades 累计 1000 笔时误差可达 0.1-1%。
- **建议**：持久化原始 float 或用 Decimal；至少 pnl_pct 保留 4 位。
- **优先级**：P2

#### 33. Signal dashboard 的 strength 显示无意义（始终 1）
- **位置**：`web/src/pages/SignalDashboard/index.tsx:90`、参见 P1#18
  ```tsx
  { title: '强度', dataIndex: 'strength', width: 80, render: (v: any) => <span className="tabular-nums">{v}</span> },
  ```
- **问题：UI 显示 "强度" 列，但后端实际存的是 signal_type→1/0/-1，不是策略 strength(0-100)。前端用户看到的是假的强度数字。
- **建议**：修复后端持久化，或在 UI 改名为"信号类型"避免误导。
- **优先级**：P2

#### 34. Run_walk_forward 用 calendar days 而非 trading days 切分
- **位置**：`app/services/backtest_engine.py:613-647`
- **问题：
  ```python
  train_days = int(total_days * train_pct)  # calendar days
  fold_len = test_pool // n_folds
  ```
  - 用 calendar days 切分，但内部又调用 run_backtest 用交易日窗口 → 实际 train 段交易日数 = calendar_days × 244/365 ≈ 67% 假设值。
  - 在 A 股春节、国庆长假，train/test 边界可能穿越长假 → train 末段出现"信息断档"。
- **建议**：用 trading day 索引而非 calendar day；引入 embargo period。
- **优先级**：P2

#### 35. 无策略间相关性矩阵 / 协方差估计
- **位置**：`app/services/strategy_comparison_service.py:55-61`
  ```python
  return {"items": items, "count": len(items)}
  ```
- **问题：`compare_backtests` 只对比单一 backtest 的 metrics，无 correlation matrix，无 daily_nav 序列以计算 nav correlation。
- **建议**：补 daily_nav 字段（参见 P2#23）+ 计算 daily return correlation matrix。
- **优先级**：P2

#### 36. live_trading 的 risk-status 不持久化 → 重启丢失
- **位置**：`app/services/risk_control.py:65-91`
  ```python
  _tripped: dict[int, tuple[datetime, str]] = {}
  ```
- **问题：CircuitBreaker 状态全在内存。注释里也提到 "in production this should be backed by Redis"，但目前完全没做。后端容器重启 → circuit_breaker 丢失 → 风险敞口失控。
- **建议**：CircuitBreaker 状态写 Redis 或 DB。
- **优先级**：P2

#### 37. 无策略监控（live PnL 偏离预期阈值告警）
- **位置**：`app/services/paper_trading_service.py` 全文、`app/services/risk_control.py` 全文
- **问题：实盘 / 模拟账户运行时，若策略偏离 backtest 预期（如实际 Sharpe -1 但 backtest 期望 +1）→ 无任何告警。监控仅有 daily loss 阈值。
- **建议**：增加 `strategy_drift_check`，对比实盘 rolling Sharpe 与 backtest 期望，>2σ 告警。
- **优先级**：P2

#### 38. BacktestResult 的 schema 不可扩展
- **位置**：`app/models/etl.py:114-137`
- **问题：BacktestResult.metrics 是 JSON，但 daily_nav 字段在 model 上**根本没有**，每天新增一种 metrics 都需要新加列。
- **建议**：增加 `daily_nav` JSON 字段 / 独立 timeseries 表。
- **优先级**：P2

#### 39. attribution_service 对没有 trades 的 backtest 仍返回归因（语义错）
- **位置**：`app/services/attribution_service.py:115-121`
  ```python
  else:
      allocation_ratio = 0.0
      allocation_effect = 0
      selection_effect = 0
      interaction_effect = 0
  ```
- **问题：no-trade backtest 返回 allocation_effect=0 selection_effect=0 → interaction_effect = total_return，与 Brinson 加性分解矛盾（应为 0）。
- **建议**：no-trade 情况返回 `{"error": "no_trades"}`，或者明确语义"无信号=无市场暴露=无 alpha"。
- **优先级**：P2

---

## 二、缺失能力（必须新增）

1. **真实基准体系**：沪深 300、中证 500、中证 1000、创业板指、恒生指数、标普 500、纳指等至少 10 个基准的注册表 + 自动下载 + 分红再投入 total return 计算。
2. **CAPM / Fama-French 因子模型**：alpha、beta（vs benchmark）、R²、IR、tracking error、up/down capture、factor exposure decomposition。
3. **风险调整收益指标**：Sortino、Calmar、Omega、gain/pain ratio、tail ratio、Ulcer Index、Martin ratio。
4. **尾部风险度量**：historical VaR（1d/5d, 95/99%）、CVaR（Expected Shortfall）、最大回撤持续期（days to recovery from peak）、最大回撤发生日期。
5. **统计显著性检验**：block bootstrap、Lo's Macaulay Sharpe SE、Jobson-Korkie z-test、permutation test、multiple-testing FDR adjustment（deflated Sharpe ratio）。
6. **蒙特卡洛稳健性**：daily return block bootstrap → 1000 次重采样 → Sharpe/MaxDD 的 5/95 分位、probability of profit。
7. **参数敏感性扫描**：param grid → heatmap 表，输出 overfit indicator（IS-OOS Sharpe decay）。
8. **Walk-forward 真 OOS**：train 段 grid search → 选最优 params → test 段用该 params；含 embargo period；IC persistence metric。
9. **组合级回测**：multi-symbol portfolio、权重方法（等权 / 信号强度 / 风险平价 / 最小方差）、rebalance frequency、单标的 cap、行业 cap、turnover 控制。
10. **做空机制**：融券标的标记、short selling cost（借券利率）、short position PnL、margin call 模拟。
11. **市场冲击 / 流动性模型**：square-root impact (`k * σ * sqrt(qty/adv)`)、participation cap、ADV-based liquidity filter。
12. **停牌 / 涨跌停处理**：is_suspended 字段、涨跌停价不成交、复牌 gap 模拟、停牌日信号过滤。
13. **完整除权除息事件**：split / dividend / rights offering 事件表、ex-date 处理、price drop 模拟。
14. **Benchmark 分红再投入**：total return benchmark、自动 dividend reinvestment。
15. **年化交易日区分**：A 股 244、港股 245、加密 365、美股 252 显式选择；日历维度明确。
16. **多周期 / Intraday 支持**：1min/5min/15min/60min bar、回测粒度可调、tick-level simulation 入口。
17. **波动率归因 / Barra 风险模型**：ex-ante risk decomposition、factor exposure、marginal contribution to risk。
18. **行业 / 风格归因**：GICS / SW 行业、Barra 风格（size, value, momentum, quality, volatility, growth, liquidity, yield）。
19. **策略间相关性矩阵**：基于 daily_nav 的 correlation / covariance、多策略组合优化（min variance, max Sharpe, risk parity）。
20. **回测与实盘一致性校验**：定期 replay 实盘 trade 在 backtest engine 复现 → 偏差告警。
21. **回测 / 实盘版本快照**：strategy version, params version, data version 三元组锁定 → 可复现。
22. **实盘 PnL drift 监控**：rolling Sharpe vs backtest expectation → drift score → 告警。
23. **paper/live 共用 RiskControl**：统一接口、daily loss / single-position cap / circuit breaker 全覆盖。
24. **停牌日历 / 交易日历**：exchange_calendars 包接入，A 股 / 港股 / 美股 / 加密 explicit calendar。
25. **回测与 paper/live 的 execution model 一致性**：确保 backtest execution_price_model 选 "open"，paper/live 也是 next-candle open。
26. **策略级别的 multiple-testing correction**：deflated Sharpe ratio（Bailey & Lopez de Prado），避免 "挑最好的策略" 过拟合。
27. **数据质量审计模块**：adj_factor 完整性、OHLC 异常（high<low、close=0）、survivorship audit、look-ahead audit。
28. **cash buffer / margin requirement**：账户最小现金预留、margin call、forced liquidation 模拟。
29. **再投资 / 红利再投入假设配置**：默认 total return benchmark、策略分红再投入频率。
30. **完整 multi-leg / multi-asset backtest**：期权、ETF 套利（折溢价）、可转债、跨市场。
31. **API 端口增加 walk-forward endpoint**：`POST /api/v1/backtests/walk-forward`。
32. **Front-end 暴露 friction / execution / position sizing 参数**：Advanced Settings 面板。
33. **Backtest 结果可视化所需数据**：drawdown underwater plot、rolling Sharpe heatmap、monthly returns heatmap、position concentration pie。
34. **回测引擎 C++/Rust 加速**：当组合 50+ 标的 × 3 年时 Python 引擎太慢。
35. **paper_trading 与 live_trading 状态合并视图**：real-time combined exposure across 全部账户。

---

## 总结

该平台回测与策略基础设施**已经搭建了框架**（策略注册表、walk-forward 占位、A 股摩擦模型、circuit breaker），但距离专业量化研究**还有非常显著的距离**。最致命的缺陷：

- **真基准 / alpha-beta-IR = 0**（P0#3）—— 无法证明策略创造 alpha；
- **做空 = 0**（P0#2）—— 多空对冲 / 市场中性无法做；
- **Sharpe 虚高 + 无显著性检验**（P0#7）—— 不知策略是否真的有效；
- **walk-forward 是伪 OOS**（P0#6）—— 给用户虚假安全感；
- **look-ahead bias 隐藏**（P0#8）—— 回测与实盘口径不一致。

修完上述 P0 的 10 项后，仍需补 P1 的 12 项才算可用工具。P2 的 19 项则是合规级产品化所必需。

按照目前能力，**不建议向生产环境或真实资金使用**；适合教学、demo、初学者熟悉量化概念。