# 资深用户挑刺 - 综合问题清单（2026-07-16）

本报告汇总 11 个资深用户视角的静态审查结论，按模块归类、优先级排序。涉及 ETF 持仓、资金流、期货、标的详情、量化研究、信号、回测、策略引擎、运维管理、数据口径等。所有引用位置均为相对路径。

## P0 阻塞级问题（建议立即修复）

### A. FundFlow 资金流模块（前后端契约错位）

| 位置 | 问题 | 修复 |
|---|---|---|
| `web/src/api/fundFlow.ts:97-120` vs `app/api/v1/fund_flow.py:54,109,192,217` | 前端列表接口传 `date`，后端 Query 参数为 `trade_date`，FastAPI 静默忽略 → 日期筛选失效 | 统一参数名为 `trade_date` |
| `app/api/v1/fund_flow.py:50-74` | `/fund-flow/individual` 无 `market` Query 参数 → 沪市/深市/创业板/科创板/北交所子标签切换不生效 | 后端新增 `market` 参数，按 `ts_code` 后缀过滤 |
| `web/src/pages/FundFlow/index.tsx:629-633` | 列标题"换手率"实际是 `turnover`（成交额，元），被 `formatPct` 当百分比渲染 | 列标题改为"成交额"，新增真实换手率列 |
| `app/api/v1/fund_flow.py:170-180` & `app/services/fund_flow_service.py:153-202` | 大盘资金流接口契约错误（前端期望 `{data:MarketFundFlow}`，后端返回列表，且服务端为 stub 返回 None） | 后端返回最新单日对象，并补充历史数据 |
| `app/data/pipelines/fund_flow.py:62,294-296,319-327` | AH 溢价方向逻辑错误（应为负面信号，代码按正面信号处理） | 取反归一化：`ah_for_score = -ah` |

### B. Backtests 回测模块（前视偏差 / 持久化缺失）

| 位置 | 问题 | 修复 |
|---|---|---|
| `app/services/backtest_engine.py:263-267,536-538` | 默认 `execution_price_model="open"` 在信号当天开盘成交，但信号基于当日收盘生成 → 前视偏差系统性高估收益 | 默认改为 `next_open`，对原 `open` 模型做 1 日滞后 |
| `app/services/backtest_service.py:148` & `BacktestResult` 模型 | `daily_nav: []` 历史回测时返回空数组，详情页无法绘制净值曲线 | 在 `BacktestResult` 持久化 `daily_nav` 与 `signals` JSON |
| `app/services/backtest_service.py:52-64` | `BacktestService.run_backtest` 未透传 `market`/`execution_price_model`/`apply_friction`，硬编码 `cn_a` | 透传参数；前端根据市场动态显示费率 |

### C. Signal 信号仪表盘（数据时效性 / 一致性）

| 位置 | 问题 | 修复 |
|---|---|---|
| `web/src/components/DataFreshnessHint.tsx:16-50` & `web/src/pages/SignalDashboard/index.tsx:145` | 新鲜度提示基于 HTTP 请求时间，而非信号实际交易日 | 用最新信号的 `trade_date`/`created_at` 与当前市场时间比较 |
| `app/services/strategy_engine.py:67-73` | 未校验最新 Bar 是否等于目标交易日，节假日 ETL 失败时仍生成"今日信号" | 在 `generate()` 前检查，不匹配返回空或标记 `stale` |
| `app/services/backtest_engine.py:263-267` vs `app/services/strategy_engine.py:22-81` | 回测使用 OPEN 执行价 + A 股摩擦模型，实盘信号仅基于收盘价生成，无执行价假设 | `execution_price_model` 与 `market` 纳入策略参数，实盘信号按同一模型 |

### D. Strategies 策略引擎（参数验证 / 类型污染）

| 位置 | 问题 | 修复 |
|---|---|---|
| `app/strategies/base.py:77-88` | `_validate_params` 仅做缺省和越界钳制，无类型校验、无 choice 枚举校验、无跨参数约束 | 严格验证层：类型强制、枚举白名单、`required`/`validators`、失败抛 `StrategyValidationError` |
| `web/src/pages/StrategyList/index.tsx:294-306` | 新建策略表单用 `Input type="number"`（返回字符串），与 `StrategyParamForm`（InputNumber）并存导致后端参数类型污染 | 统一替换为 `StrategyParamForm` |
| `app/services/strategy_service.py:58-79` | `create_strategy` 未校验 `strategy_type` 是否在 `StrategyRegistry` 中注册 | 在 service 层 `StrategyRegistry.get(strategy_type)` 校验 |
| `app/strategies/volume.py:36-71` | `VolumeBreakoutStrategy` 在 `price_confirm=False` 时仅 BUY 永不 SELL | 完善参数语义或禁止该组合 |

### E. ETF Holdings 持仓（披露时效 / 报告类型 / 4 月窗口）

| 位置 | 问题 | 修复 |
|---|---|---|
| `app/data/pipelines/etf_holdings.py:422-455` | 模型未记录 `report_type`（年报/中报/一季报/三季报）和 `disclosure_date` | 增加字段；前端 timeline 展示标签与披露日 |
| `app/data/providers/cninfo_etf_holdings_provider.py:103-145` & `app/data/pipelines/etf_holdings.py:216-221` | `period="semi"` 默认值，4 月/年报与 10 月/三季报窗口只查半年报 | 调度器按当前季度计算应抓取的 `period`，透传给 provider |
| `web/src/pages/EtfHoldingsHistory/index.tsx:468-474` | 前端缺数据新鲜度/滞后提示 | API 暴露 `is_stale`/`days_since_disclosure` |

### F. Futures 期货（连续合约 / 品种分类）

| 位置 | 问题 | 修复 |
|---|---|---|
| `app/data/pipelines/futures.py:999-1003` & `_pick_main_per_day()` | 主力连续合约按 OI 拼接，换月日 `pre_settle` 跨合约取值导致价差跳空 | 换月调整因子（roll adjustment），新增 `settle_adjusted`/`change_pct_adjusted` |
| `app/data/pipelines/futures.py:97-181` `_PRODUCT_MAP` | 静态分类表不完整，缺失 AO/BR/SP/PG 等新品种；I/J/JM/SF/SM 分类错误 | 补充新品种，调整 I/J/JM/SF/SM 分类，外置为配置表 |
| `app/models/futures.py:78-83` | 合约规格缺 `expiry_date`/`last_trading_day`/`first_notice_day`/`delivery_month` | 通过 `ak.futures_contract_info` 抓取填充 |

### G. Instrument Detail 标的详情（净值/折溢价/QDII/资金流）

| 位置 | 问题 | 修复 |
|---|---|---|
| `web/src/pages/InstrumentDetail/index.tsx:386-467` | K 线未叠加 NAV/IOPV，未展示折溢价 | 数据库 `instrument_daily_bar` 已有 `nav` 与 `discount_rate`，前端展示 |
| `web/src/pages/InstrumentDetail/index.tsx:343-384,469-482` | QDII 缺风险标签、外汇额度、暂停申购提示 | 顶部增加 QDII Alert |
| `web/src/pages/InstrumentDetail/index.tsx:510-516` | 未接入 `/fund-flow/etf` | 增加 `instrumentApi.fundFlow(code, days)` 与 ETF 资金流卡片 |

### H. Trader 交易（P0 阻塞）

| 位置 | 问题 | 修复 |
|---|---|---|
| `app/services/paper_trading_service.py` + `AkshareProvider.fetch_realtime_quotes` | A 股模拟交易无法下单：provider 返回中文列名，service 期望 `price`/`etf_code` | 字段映射或 service 适配 |
| `app/api/v1/trading.py` 等 | 真实交易配置/下单/撤单/重置熔断全部 `require_admin` | 下放为用户级权限 |

### I. Platform Admin 运维（权限 / 日志 / 告警）

| 位置 | 问题 | 修复 |
|---|---|---|
| `app/api/v1/etl.py` | `/api/v1/etl/status` 无身份校验 | 添加 `Depends(get_current_user)` 或 `require_admin` |
| `app/api/v1/etl_status.py` | `/api/v1/etl/dashboard` 未限定 admin | 改为 `require_admin` |
| `app/core/scheduler.py` | `run_score_calculation`/`run_signal_generation`/`paper_trade_*` 等核心任务不写 `etl_log` | 统一用 `@record_etl` 或 `ETLPipeline` 包裹 |
| `app/services/notification_service.py` | 通知服务从未被 ETL 失败路径调用 | 在 `@record_etl` 失败分支触发通知 |

### J. Freshness / Metric Consistency（口径统一）

| 位置 | 问题 | 修复 |
|---|---|---|
| `app/services/etf_service.py:86-88` | A 股个股 `total_mv` × 10,000 填充 `fund_size`，与 `stockFundamental` 接口的万元单位不一致 | `stockFundamental` 接口统一输出元；前端统一 `/1e8` |
| `app/models/etf.py:80` + `etf_service.py:86-88` | `market_cap` 同时承载 USD/CNY 两种语义 | 增加 `market_cap_currency` 字段 |
| Macro FRED（>1d）/ Macro realtime（>24h）/ ETL Ops（>3d） | 新鲜度阈值不同页面不一致 | 统一配置 `FRESHNESS_THRESHOLDS` |
| `app/services/screening_service.py:226-259` | 筛选器入参按百分比传入，service 统一 `_pct(v) = v/100` 但 Schema 注释不明确 | Field 描述明确"百分比，如 15 表示 15%" |

## P1 重要问题（按模块汇总）

### ETF 持仓（EtfHoldings）

- 权重列缺口径说明（NAV/股票市值/债券/商品）；`total_weight` 口径未标注。
- 持仓未区分债券型/商品型/QDII 资产类别；cninfo 解析器只处理 §7.3.1 股票明细。
- 不同数据源 `holding_code` 格式不一致，导致同一期重复、diff 状态误判。
- 快照表未明确限定"前 10"并展示 rank；UI 应标注"前十大重仓"。
- Diff 默认取最新两期，不提示"非相邻报告期"。
- `holdings_as_of_date` 缺失时用 `today` 填充 `snapshot_date`，可能污染历史。
- 覆盖度分母未按资产类别拆分，对债券/商品/QDII 设置独立阈值。
- 多源合并未定义优先级，Akshare 可能覆盖 Eastmoney。
- Diff 的 DatePicker 未限定可选日期。
- 缺少权重变化柱状图、行业汇总 diff 表、单只股票多期权重折线。
- 空状态提示过于笼统，应区分黑名单/抓取失败/无持仓。
- 缺少按资产类别拆分覆盖度 KPI。

### FundFlow 资金流

- 主力/单量阈值（≥100 万/20-100 万/4-20 万/<4 万）仅在 ORM 注释，无 Schema/文档。
- 复合信号归一化阈值未经验证且与注释不符（"sigmoid 风格"实际是线性 clip）。
- 板块排序字段映射缺失（`SectorFundFlow.main_net_inflow` 未映射）。
- 缺成交额/流通市值展示，无法判断"主力净流入"在什么成交背景下产生。
- 多日期累计指标被错误标记为单日（写 `trade_date = today`）。
- ETF 推算净流入用 `shares_change × price` 而非 `net_value`，高溢价会高估。
- 未区分 ETF 一级申赎与二级交易；份额变化 ≠ 资金流入。
- 不支持周/月粒度或多日累计排名。
- 板块历史接口在 API 路由层直接写 SQL。
- Pipeline 在全部子任务返回空时仍标记成功。
- 综合信号榜缺 `name` 字段，前端只能显示代码。
- 缺少数据源发布时间/数据新鲜度字段。

### Futures 期货

- 未计算近月-远月价差、升贴水、年化展期收益。
- 品种合约乘数/最小变动价位/手续费未记录，无法计算净展期收益。
- 期货与 ETF/LOF 商品基金模块未打通，无法估算 roll cost 和 tracking error。
- 主力合约选择只用 OI 最大值，无交割月/最后交易日/换月窗口约束。
- 次主力（sub-main）和全合约 OI 加权指数缺失。
- 未识别合约暂停/退市/限制开仓状态。
- 数据校验仅 high≥low，缺价格非负/涨跌停/零成交量等异常检测。
- `pre_settle` 首日无回填导致首日涨跌幅缺失。
- `warehouse_receipts` 始终为 None，未真正采集仓单。
- `change_pct` 直接用 `settle_change_pct`，无基于收盘价变化。
- 前端只展示四个固定分类，"其他"合约被排除。
- 无单合约详情页/K 线/持仓量/成交量走势。
- `/futures/daily` `code` 可选语义模糊。
- 合约列表默认只展示主力，无次主力和全合约。

### Instrument Detail 标的详情

- `ETFInfoResponse` 缺 `list_date`/`delist_date`/`fund_size_source`/`expense_ratio`。
- 个股详情页只有最新估值，缺季度财报历史（收入/利润/ROE/资产结构）。
- `/fund-flow/etf` 无单基金历史接口。
- 缺净值-价格对比图和折溢价率历史走势图。
- `instrumentApi` 命名仍以 `/etfs` 为前缀造成误导。
- `StockFundamentalsModule` 与 `StockDetail` 估值 Tab 重复实现。
- 商品期货 ETF/黄金 ETF 缺现货/期货价格/展期成本/持仓结构。

### Trader 交易

- 模拟交易零佣金、零滑点，收益失真。
- 真实交易持仓 `avg_cost` 恒为 0，未实现盈亏计算错误。
- 熔断器仅存进程内存，重启即失效，不适合多 worker 部署。
- 缺仓位集中度/行业集中度/最大回撤熔断风控。
- 投资组合中心的目标池/实际持仓偏离度为 mock 数据。
- 缺夏普/最大回撤/盈亏比/基准对比等绩效指标。
- 标的详情页无交易入口和当前持仓联动。
- 未区分实时行情与延迟行情（美股 YFinance EOD 本质延迟）。
- 真实交易订单状态下单后未与交易所同步。

### Signal 信号仪表盘

- 前端无 `refetchInterval`，60s staleTime 无实时刷新。
- 信号缺目标成交价/建议仓位/滑点/手续费假设，不可直接转化为交易指令。
- 模拟交易 auto-trade 仓位固定 10%，未按强度或风险调整。
- 信号强度计算策略间不统一（*1000 vs *33），容易饱和。
- `generate` 与 `generate_series` 实盘/回测可能漂移。
- 横截面策略无 portfolio 回测，实盘/回测完全脱节。
- 策略参数变更无版本记录。
- 信号详情页未展示因子贡献（`extra_data`）。
- 信号排序按 `created_at`，可能混入旧交易日信号。
- 信号无过期/失效机制。
- 无信号执行跟踪与订单映射。

### Strategies 策略引擎

- 参数类型仅支持 `int/float/bool/choice`，缺 `string/date/timeframe/array/expression/conditional`。
- 缺参数优化（网格/贝叶斯）。
- walk-forward 后端已实现但 API/前端无入口。
- 缺敏感性分析、蒙特卡洛、信号归因。
- 无自定义策略/公式导入入口。
- 复合/多因子策略构建器缺失，仅 `TripleScreenStrategy` 硬编码。
- 横截面策略无法通过现有单标的回测。
- 事件驱动策略的 `event_types` 选项包含未实现的 earnings/macro。
- 策略库 UX 信息深度不足（无搜索/排序/标签/文档）。
- 策略无版本/编辑/复制能力。
- 策略参数与回测执行参数耦合（`holding_period`）。
- 缺策略级别组织共享与权限管理。
- 回测对比服务缺统计显著性检验。

### Backtests 回测

- 成交价用未复权原始价，市值用复权收盘价，分红/拆股后 PnL 计算错。
- 缺乏基准对比与相对收益指标（alpha/beta/IR）。
- 缺 Sortino/Calmar/VaR/回撤持续期等风险度量。
- 无换手率计算。
- 仅支持全进全出长仓，无法做空/加减仓。
- 缺止损/止盈/trailing stop。
- 事件驱动策略可能使用前视新闻。
- walk-forward 在后端但无 API/前端入口。
- 缺样本量/统计显著性提示。
- 缺回撤图/基准对比图/导出功能。
- 交易记录缺持仓天数/退出原因/MAE/MFE/最大回撤。
- 前端表单缺关键参数（`risk_free_rate`/`execution_price_model`/`market`）。
- 交易记录行 key 可能重复。
- 绩效归因模型过于简化。

### Strategies 策略定义

- 同上策略引擎 P1 项。

### Market Scanner（MarketScanner）

- 模块定位严重偏离（实际是 ETF universe 维护，不是选股器）。
- 完全无筛选条件覆盖。
- 无多条件组合与嵌套逻辑。
- 无自定义公式/表达式构建器。
- 结果无行动能力（加入自选/创建池/运行回测）。
- 无排序/排名能力。
- 扫描频率低、无实时性。
- 单数据源/单市场/覆盖范围窄。
- 无缓存与性能优化。
- 策略引擎未与扫描器/筛选器打通。

### Freshness / Metric Consistency

- Sector Rotation RS 在市场平均收益接近 0 时可能产生极端值。
- ETL Ops 新鲜度判断未考虑交易日历（周末/节假日）。
- `LastUpdated` 组件在缺时间戳时返回 null（用户体验不一致）。
- 资金流"大盘"为 stub 实现，未接入独立 market 表。
- 数据新鲜度文案不统一（"数据时间"/"更新于"/"上次更新"）。
- React Query `staleTime` 硬编码未对齐数据刷新频率。
- `StockFundamentalResponse` 单位仅注释说明，未强制。
- Crypto `last_updated` 为服务端请求时间，非数据源实际时间。

### Backend ETL/Scheduler

- 评分/信号/交易类不写 `etl_log`（`/etl/dashboard` 显示 `never_run`）。
- 通知服务从未被 ETL 失败路径调用。
- 无死信队列，无失败任务持久化。
- 大量任务 `max_attempts=1`（microstructure/fund_flow/sec_edgar/search_trends）。
- `misfire_grace_time` 缺失，APScheduler 默认 grace=0。
- `.env.example` `DATABASE_URL` asyncpg/psycopg2 不兼容。
- `scripts/data_completeness_check.py` 硬编码绝对路径。
- `_create_log`/`_update_log` 用 naive datetime。
- `_TRACKED_JOBS` 硬编码与 scheduler 不同步。
- `run_with_retry` 用 print 而非 logger。
- 任务 `running` 永久挂死（被 kill 后）。
- Celery 队列路由未生效（任务未按 queue 入队）。
- `paper_trade_auto` 不检查信号生成是否成功。
- `/api/v1/etl/status` 无身份校验。

## P2 优化项（按模块）

详见各模块原文，主要包括：

- ETF 持仓：Diff DatePicker 限定、权重变化柱状图、行业汇总 diff、空状态细分。
- FundFlow：北向/南向资金、融资融券明细、ETF 真实申赎、资金-价格背离、龙虎榜/大宗明细、盘中资金、信号回测与归因。
- Futures：商品期货 ETF/LOF 影响分析、合约规格与到期日管理、数据质量监控面板、次主力与连续指数、合约详情页与 K 线/持仓图、测试覆盖换月跳空/期限结构/展期收益。
- InstrumentDetail：QDII 专有能力（净值/IOPV/外汇额度/限购）、ETF/LOF 研究能力（折溢价历史/跟踪误差/PCF）、股票基本面（财报历史/同业对比/股息率）。
- Trader：API 字段命名一致性（`order_type` vs `side`）、WebSocket 行情、风险规则前端、TCA 分析、港股模拟、多市场实盘接入。
- Signal：信号订阅规则、回测入口、信号失效机制、执行跟踪、风控规则。
- Strategies：参数类型扩展（timeframe/array/expression/conditional）、策略文档与发现、版本与编辑、团队共享、统计显著性对比。
- Backtests：交易记录字段补齐、表单参数化、归因模型升级、统计可信度提示。
- Freshness：文案统一（"数据时间"或"更新于"）、`staleTime` 按数据类别分级、单位明确化。

## 已成功完成并 push

详见 `13670dd`：CorrelationHeatmap null 防御、News detail、global.css 等修复。