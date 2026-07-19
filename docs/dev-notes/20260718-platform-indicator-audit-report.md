# 平台指标正确性与数据完整性全面审计报告

**审计日期：** 2026-07-18  
**审计范围：** A 股个股/ETF、美股、数字货币、综合评分/排名、板块轮动/资金流向、数据 pipeline 与 ETL 稳定性  
**审计方式：** 6 个独立子 agent 并行代码审查 + 权威数据源交叉验证  
**执笔：** Claude Code 审计团队

---

## 一、执行摘要

本次审计共发现 **P0 级问题 9 项、P1 级问题 19 项、P2/P3 级问题若干**。所有发现可归纳为 6 类根因：

1. **前端显示单位错误**：百分比指标未乘以 100，导致收益率等全部显示缩小 100 倍。
2. **复权语义前后端不一致**：UI 标“前复权”，但实际使用 `close × adj_factor`（后复权/连续可比价）；历史 bar 的 `adj_factor` 未回填。
3. **后端指标计算基准错误**：收益/MA/BB/RSI/MACD/ATR 基于 raw close，对拆股/送转/分红个股会系统性失真。
4. **ETL 稳定性与数据新鲜度缺失**：任务被 kill 后会 stuck 在 `running`；指标计算目标日期从数据库推导，数据停滞时不会告警。
5. **市场特异性处理缺失**：美股/Crypto 交易日历、年化因子、窗口长度未与 A 股区分。
6. **评分/板块/资金流聚合逻辑缺陷**：风险维度符号混用、分类排名失效、行业收益口径不对、大盘资金流为 stub 等。

**已立即修复的 P0/P1 问题：**

- `formatPercent` / `formatSigned` 漏乘 100（前端所有收益率显示）。
- `KLineChart` 改为真正前复权（`close × adj_factor / latest_factor`）。
- `StockDetail` 新增前复权/不复权切换。
- `KLineChart` 布林带改为样本标准差，与后端一致。
- 评分风险维度对 `max_drawdown` 取绝对值后再平均。
- 评分服务按市场分别取最新指标日，避免 A 股被跳过。
- Crypto ETL 时区 bug 修复（UTC 时间戳 + 90 天窗口）。
- ETL stuck 清理脚本 `scripts/cleanup_stuck_etl_logs.py` 与调度器每小时/启动时自动清理。
- yfinance batch fallback 从 `Adj Close/Close` 推导 `adj_factor`，不再硬编码 1.0。
- 新增 `scripts/recalculate_scores.py` 用于评分全量重跑。
- 后端指标统一改为 `qfq_close`（pandas + SQL 双路径）。
- SQL/pandas 风险指标门限对齐为 60，volatility 增加 min_periods 对齐。
- `AdjFactorHistory` 表 Alembic 迁移 `i9j0k1l2m3n4_add_adj_factor_history_table.py` 已创建。
- 板块轮动相对强弱（RS）改为超额收益差值，轮动信号窗口改为 5 个交易日（Phase 2.11）。
- Crypto 指标使用 365 天/年、自然日窗口 7/30/90/180/365，与 A 股/美股参数分离（Phase 2.6）。

---

## 二、各子系统关键发现

### 2.1 A 股技术指标（含 600026.SH）

**P0**
- 前端 `formatPercent` 漏乘 100。

**P1**
- `StockDetail` 无复权切换，默认 raw close。
- `KLineChart` 布林带用总体标准差（N），后端用样本标准差（N-1）。
- 日线 ETL 只回填当日 `adj_factor`，历史因子不更新。
- 后端收益/MA/BB/RSI/MACD/ATR 基于 raw close；对高分红/高股价个股（600519、000001）MA 与权威前复权差异可达百倍。

**P2**
- SQL 风险指标 `max_drawdown_1y` / `sharpe_1y` 门限 119 行，pandas 路径 60 行，不一致。
- `volatility_20d/60d` SQL 无 `min_periods`，比 pandas 更早出值。
- `InstrumentDetail` 复权 K 线与指标面板口径不一致。

**样本偏差（2026-07-16）**

| 代码 | 指标 | 平台当前（raw） | 权威前复权 | 偏差 |
|---|---|---|---|---|
| 600026.SH | return_1y | 44.35% | 47.37% | -3.02 pp |
| 600026.SH | ma5 | 15.44 | 29.23 | -13.79 |
| 600519.SH | return_1y | -10.68% | -7.01% | -3.67 pp |
| 600519.SH | ma5 | 1228.18 | 10619.21 | -9391.03 |
| 000001.SZ | return_1y | -12.58% | -7.79% | -4.79 pp |
| 000001.SZ | ma5 | 10.66 | 1481.55 | -1470.89 |

### 2.2 美股指标

**P0**
- 569 只 active 美股仅 14 只有日线，最新只到 2026-06-26；调度器心跳为空，疑似未运行。

**P1**
- ~~yfinance batch fallback 把 `adj_factor` 硬编码为 1.0，复权完全失效。~~ **已修复**：batch 路径从 `Adj Close/Close` 推导 `adj_factor`。
- 收益指标用 raw close（price-return），未反映分红再投资（total-return）；待后端指标统一改为 `qfq_close` 后自然解决。

**P2**
- `StockDetail` 无复权切换；前后端指标口径不一致。
- `StocksList` 默认过滤 A 股，美股入口不友好。
- 美股个股元数据缺失（list_date、sector、industry 等）。

### 2.3 数字货币指标

**P0**
- `BinanceProvider.fetch_daily_bars` 在上海时区容器内生成本地时间戳，导致目标日 UTC 日 K 线被排除，ETL 永远写不进数据。

**P1**
- Crypto 沿用 A 股/美股的 252 天/年、21/63/126/252 交易日窗口；正确应为 365 天/年、30/90/180/365 自然日窗口。
- 波动率因 `sqrt(252)` 被低估约 20.4%（`sqrt(365/252)=1.204`）。
- `CryptoDailyPipeline` 只拉 7 天窗口，无法回补超过 7 天的缺失。

**P2**
- 前端“24h 涨跌”与日线口径混用。
- `change_pct` 按 `open → close` 计算，非 `(close - pre_close)/pre_close`。

**P3**
- `CryptoDetail` 未展示 1m/3m/1y 收益、volatility、max_drawdown、sharpe 等核心指标。

### 2.4 综合评分 / 排名 / 股票池 / 筛选

**P0**
- `rank_category` 与 `rank_overall` 完全相同（旧逻辑写入，未启用分类桶）。
- `formatPercent` 漏乘 100（已修复）。

**P1**
- 已存 `composite_score` 与当前代码逻辑不一致（1505/1509 差异 >0.01）。
- 风险维度把正波动率与负回撤直接平均，语义错误（已修复）。
- 美股/Crypto 无评分。

**P2**
- 使用全局最新指标日，跨市场时可能漏算 A 股（已修复按市场取最新日）。
- 评分数据滞后，前端无提示。

### 2.5 板块轮动 / 资金流向

**P0**
- 市场资金流大盘卡片已接入 ``market_fund_flow`` 真实表（沪深整体来自 akshare，SH/SZ 由 individual_fund_flow 派生）。
- 资金流页面未指定日期时返回全历史，首屏不是当日。
- 个股资金流“沪市/深市/创业板/科创板/北交所” tab 过滤不生效。

**高**
- 相对强弱 RS 在下跌市中颜色/方向反转（Phase 2.11 已修复：改为超额收益差值）。
- 轮动信号“一周内”文案实际只比较相邻交易日（Phase 2.11 已修复：改为 5 个交易日对比）。
- 行业收益用成分股等权平均，不等于官方申万/中信行业指数。

**中**
- GICS / 申万行业映射存在明显偏差。
- 综合资金信号中 AH 溢价为空仍占 5% 权重；融资融券仅覆盖沪市。
- ETF 净流入估算用市价而非 NAV，日期贴标可能错位。

### 2.6 数据完整性与 ETL 稳定性

**P0**
- A 股 ETL pipeline 可能卡在 `running` 状态，无心跳/lease 自动清理。
- 美股日终 ETL 已 21 天无成功记录；Crypto 从未写入 ETL 日志（与 P0 时区 bug 一致）。

**P1**
- 指标计算目标日期从数据库最新 bar 推导，数据停滞时不告警。
- 美股、Crypto 无交易日历过滤，节假日空跑。
- 美股日终覆盖策略依赖 yfinance 兜底，Tiingo 50 req/hour 轮询覆盖不足。
- 监控脚本只覆盖 A 股 ETF，不检查数据新鲜度、不覆盖美股/Crypto、不检查 ETL stuck。

---

## 三、统一修复计划（按优先级）

### Phase 1：P0 级修复（立即实施）

| # | 任务 | 关键文件 | 说明 |
|---|---|---|---|
| 1.1 | 修复 Crypto ETL 时区 bug | `app/data/providers/binance_provider.py` | UTC 时间戳，或 `end_date + 1 day` |
| 1.2 | 修复 A 股前复权显示 | `web/src/components/KLineChart.tsx`（已完成） | 已改为 `close × adj_factor / latest_factor` |
| 1.3 | 修复前端百分比显示 | `web/src/utils/format.ts`（已完成） | 已乘以 100 |
| 1.4 | 修复评分风险维度符号 | `app/data/indicators/scoring.py`（已完成） | 已对 max_drawdown 取绝对值 |
| 1.5 | 修复评分按市场取最新日 | `app/services/scoring_service.py`（已完成） | 已按 market 分组 |
| 1.6 | ETL stuck 清理与监控 | `scripts/cleanup_stuck_etl_logs.py`、`app/core/scheduler.py` | 脚本 + 启动/每小时自动清理 |
| 1.7 | 修复资金流日期默认与过滤 | `app/services/fund_flow_service.py`、`app/api/v1/fund_flow.py` | 默认最新日、支持 market 参数 |

### Phase 2：P1 级修复（1-2 周内）

| # | 任务 | 关键文件 | 说明 |
|---|---|---|---|
| 2.1 | A 股 `adj_factor` 全历史回填 | `app/data/pipelines/a_share_stock_daily.py`、`app/scripts/backfill_a_share_adj_factor.py`、`app/core/scheduler.py` | 新增 `AdjFactorHistory` 表、日终同步、每周日 03:30 自动回填 |
| 2.2 | 后端指标统一基于前复权 close | `app/data/indicators/calculator.py`、`app/data/indicators/sql_calculator.py` | 收益/MA/BB/RSI/MACD/ATR 用 `qfq_close`；**已完成** |
| 2.3 | SQL 与 pandas 路径门限对齐 | `app/data/indicators/sql_calculator.py`、`app/data/indicators/risk.py` | 风险指标门限 60 行、volatility min_periods；**已完成** |
| 2.4 | 评分数据重跑 | `scripts/recalculate_scores.py` | 全量重跑所有模板评分，修复 `rank_category` |
| 2.5 | 美股/Crypto 收益与夏普补齐 | `app/data/pipelines/us_etf.py`、`app/data/pipelines/crypto_daily.py` | 恢复调度、补历史、复权因子、收益指标；yfinance batch `adj_factor` 已修 |
| 2.6 | Crypto 指标窗口年化改造 | `app/data/indicators/market_config.py`、`app/data/indicators/risk.py`、`app/data/indicators/technical.py`、`app/data/indicators/calculator.py`、`app/data/indicators/sql_calculator.py` | 365 天/年、自然日窗口 7/30/90/180/365；配置模块已集成 **（已完成）** |
| 2.7 | 指标计算目标日期新鲜度检查 | `app/core/scheduler.py` | `_resolve_a_share_target_date` 已对滞后 >2 天的 A 股日线打印告警 |
| 2.8 | 市场交易日历统一 | `app/data/pipelines/us_etf.py`、`app/data/pipelines/crypto_daily.py` | 美股节假日跳过、Crypto UTC 日界 |
| 2.9 | 监控脚本扩展 | `scripts/audit_indicator_completeness.py`、`scripts/audit_etl_freshness.py` | 覆盖多市场、检查新鲜度、检查 ETL stuck；freshness 脚本已建 |
| 2.10 | 资金流大盘数据接入 | `app/data/pipelines/market_fund_flow.py`、`app/models/fund_flow.py`、`app/services/fund_flow_service.py`、`app/api/v1/fund_flow.py`、`app/core/scheduler.py`、`scripts/backfill_market_fund_flow.py` | 已完成：新建 `market_fund_flow` 表，akshare 接入整体大盘资金流，派生 SH/SZ，每日 18:35 定时任务，支持 `--start-date/--end-date/--dry-run` 回补 |
| 2.11 | 板块轮动 RS 颜色/窗口修复 | `app/services/sector_rotation_service.py`、`web/src/pages/SectorRotation/index.tsx`、`app/tests/services/test_sector_rotation_service.py` | 差值替代比值、5 日排名对比 **（已完成）** |

### Phase 3：P2/P3 级修复（后续迭代）

- 行业映射校正（GICS/申万）与官方指数收益视图。
- 综合资金信号补全（AH 溢价、深市融资、股东户数日期对齐）。
- ETF 净流入估算改用 NAV、修复日期贴标。
- `CryptoDetail` 展示 1m/3m/1y 收益、volatility、max_drawdown、sharpe。
- 术语文档与实际实现对齐。

---

## 四、数据回补与验证清单

1. **Alembic 迁移**：执行 `alembic upgrade head` 生成 `adj_factor_history` 与 `market_fund_flow` 表。
2. **A 股复权因子**：跑 `python -m app.scripts.backfill_a_share_adj_factor.py`。
3. **A 股指标重算**：对所有 A 股跑 `full_history=True` 指标任务（pandas/SQL 路径均已改为 `qfq_close`）。
4. **评分重跑**：跑 `scripts/recalculate_scores.py`（或调用 `ScoringService.calculate_daily_scores`）。
5. **大盘资金流回补**：跑 `python scripts/backfill_market_fund_flow.py --start-date 2026-06-01 --end-date 2026-07-18`。
6. **美股历史**：手动触发 `us_historical_backfill` / `scripts/backfill_us_deep_history.py`。
7. **Crypto 历史**：修复时区 bug 后，全量回补所有交易对日线。
8. **验证**：
   - 600026.SH 前复权 K 线最新价 = 14.21， older bars 与 Tushare qfq 对齐。
   - 前端收益率显示为 `+3.00%` 而非 `+0.03%`。
   - `rank_category` 在股票型/货币型内分别为独立排名。
   - `/health/etl` 或监控脚本无 CRITICAL。

---

## 五、监控与告警建议

- `/health/etl` 暴露：各市场最新 bar 日期、各 ETL job 最近成功时间、当前 running >1h 任务列表。
- A 股日线滞后 >1 个交易日 → P0 告警。
- 美股日线滞后 >1 个交易日 → P1 告警。
- 任何 ETL job `running` 超过 2 小时 → P1 告警。
- 指标覆盖率脚本每天运行并输出 OK/WARN/CRITICAL。

---

## 六、结论

平台当前指标问题不是单一 bug，而是“显示层单位错误 + 复权语义混乱 + 指标计算基准不一致 + ETL/监控缺失”叠加的结果。600026.SH 的 K 线与收益 discrepancy 只是最显性的表现。建议按 Phase 1 → Phase 2 → Phase 3 顺序推进，每完成一个 Phase 做一次端到端验证，避免再次引入口径不一致。
