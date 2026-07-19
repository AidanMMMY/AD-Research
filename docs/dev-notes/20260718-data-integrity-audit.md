# 平台指标底层数据完整性与时效性审计报告

**审计日期：** 2026-07-18  
**审计对象：** Investment-Research-Platform（A 股 / 美股 / Crypto / 指标计算 / 调度）  
**审计范围：** 日线/指标 ETL pipeline、调度与任务入口、交易日历、监控脚本  
**执笔：** Claude Code 审计子 agent  

---

## 一、审计范围

1. **ETL pipeline 代码**
   - A 股 ETF：`app/data/pipelines/a_share.py`（`AShareETLPipeline`）
   - A 股个股：`app/data/pipelines/a_share_stock_daily.py`（`AStockDailyPipeline`）
   - 美股日终：`app/data/pipelines/us_etf.py`（`USDailyPipeline`）
   - 美股历史回填：`app/data/pipelines/us_backfill.py`（`USHistoricalBackfillPipeline`）
   - 数字货币：`app/data/pipelines/crypto_daily.py`（`CryptoDailyPipeline`）
   - 基类：`app/data/pipelines/base.py`（`ETLPipeline`）
   - 数据源：Tushare / Akshare / Tiingo / yfinance / Binance 相关 provider

2. **调度与指标入口**
   - `app/core/scheduler.py`（APScheduler 任务注册与编排）
   - `app/tasks/indicator.py`（Celery 指标任务入口）
   - `app/core/celery_app.py`（Celery 配置与队列）
   - `app/core/calendar.py`（A 股交易日历）
   - `app/data/indicators/calculator.py`（pandas / SQL 双后端指标计算器）
   - `app/data/indicators/sql_calculator.py`（SQL 窗口函数指标计算）

3. **监控/告警/修复脚本**
   - `scripts/audit_indicator_completeness.py`
   - `scripts/data_completeness_check.py`
   - `app/scripts/backfill_a_share_adj_factor.py`
   - `scripts/backfill_indicators_full_history.py`

4. **数据库现状抽样**（本地连接 `postgresql+psycopg2://etf:etf_research_password@localhost:5432/ad_research`）
   - `instrument_daily_bar` 最新交易日：2026-06-26（美股），A 股 ETF 最新 2026-06-22，A 股个股无日线数据，Crypto 无日线数据。
   - `etf_log` 显示 `a_share_daily_etl`、`a_stock_daily_etl` 长期处于 `running` 状态且未结束。

---

## 二、关键发现（按严重程度排序）

### P0-1：A 股 ETL pipeline 被卡在 `running` 状态，日线数据已停滞

- **现状**：`a_share_daily_etl` 自 **2026-06-27 01:26** 起、`a_stock_daily_etl` 自 **2026-06-28 04:28** 起均处于 `running` 状态，且 `end_time` 为 `NULL`。此后 A 股 ETF 日线停留在 2026-06-22，A 股个股日线完全没有数据。
- **影响**：
  - 下游 `etf_indicator` 只能基于旧数据重算，评分/信号/回测全部建立在过期行情上。
  - Redis 分布式锁 `daily_pipeline` / `a_stock_daily_pipeline` 可能因任务未正常释放而长期被占用，进一步阻塞后续调度。

### P0-2：美股日终 ETL 已 21 天未产生成功记录，Crypto 从未写入 ETL 日志

- **现状**：`us_daily_etl` 最近成功记录为 **2026-06-27 18:40**，之后无日志。`crypto_daily_etl` 在 `etl_log` 中完全没有记录。
- **影响**：美股、Crypto 日线数据均严重滞后；依赖这些市场的指标/信号/池快照均不可用或失真。

### P1-3：指标计算目标日期无法发现数据落后

- **现状**：`run_indicator_calculation` 通过 `_resolve_a_share_target_date()` 从 `instrument_daily_bar` 中“最新 A 股 bar 日期”推断目标日期。当 A 股 ETL 长期失败时，指标计算会反复重算旧日期，而不是告警。
- **影响**：系统不会主动暴露“日线已停止更新”这一事实，审计/监控难以发现。

### P1-4：不同市场的交易日历处理不一致，周末/假日容易空跑

- **现状**：
  - A 股使用 `app/core/calendar.py` 基于 akshare 的 `calendar.json` 判断交易日。
  - 美股、Crypto 的 pipeline 直接使用 `date.today() - timedelta(days=1)`，没有过滤各自市场的节假日。美股 05:00 CST 运行时若美国昨天是周末，会请求上周五数据，但代码没有显式检查是否为上个交易日。
  - Crypto 虽然 24/7，但 `target_date` 在容器 `Asia/Shanghai` 时区下是“昨天”，而 Binance 日 K 以 UTC 00:00 收盘，二者在跨 UTC 日界时可能产生偏差。
- **影响**：非交易日会空跑并记录 `records=0`，浪费 API 配额并增加日志噪音。

### P1-5：美股日终覆盖策略依赖 yfinance 兜底，存在大面积缺失风险

- **现状**：`USDailyPipeline.extract()` 每天只通过 Tiingo 请求最多 50 个 symbol，其余 symbol 依赖 yfinance。yfinance 被注释说明“在服务器 IP 上被严重限流”。
- **影响**：Tiingo 免费层 50 req/hour、500 symbols/month 的配额下，每天 50 个 symbol 意味着约 20 天才能轮询完全部 ~500 只美股；其余靠 yfinance，若 yfinance 被封禁，则大量美股缺失。

### P1-6：监控脚本只覆盖 A 股 ETF，且不检查数据新鲜度

- **现状**：`scripts/audit_indicator_completeness.py` 仅审计 A 股 ETF 的 `etf_indicator` 对 `instrument_daily_bar` 的覆盖率，且目标日期取“最新 A 股交易日”。它不检查：
  - A 股个股、美股、Crypto；
  - `instrument_daily_bar` 最新日期是否严重落后于今天；
  - ETL 任务是否 stuck 在 `running`。
- **影响**：无法通过现有监控脚本发现 P0-1/P0-2 的问题。

### P2-7：A 股个股 ETL 的 bulk 接口对 adj_factor 的拉取存在单点失败

- **现状**：`AStockDailyPipeline.extract()` 使用 `fetch_daily_all_market()` 一次拉取全市场，然后合并 `fetch_adj_factor(trade_date=target_date)`。若后者失败，所有股票的 `adj_factor` 被默认填充为 1.0。
- **影响**：除权除息日会导致风险/收益指标失真。

### P2-8：yfinance batch 模式复权因子恒为 1.0

- **现状**：`yfinance_provider.py` 在批量下载时 `adj_factor = 1.0`，仅对单 code 下载才通过 `_compute_adj_factors` 计算。
- **影响**：若美股日终大量走 yfinance 批量路径，长周期收益/回撤指标未经过复权调整，精度下降。

### P2-9：SQL 指标后端 `max_bars` 可能截断长历史窗口

- **现状**：`sql_calculator.py` 默认 `INDICATOR_SQL_MAX_BARS=300`，对 252 日窗口是够的，但代码允许用户配置更小值。若配置低于 252，则 1 年指标精度受损；虽然代码会打印 warning，但不会阻止执行。
- **影响**：配置不当可能导致 1 年风险指标失真。

---

## 三、根因与代码位置

| 发现 | 根因 | 关键代码位置 |
|------|------|--------------|
| P0-1 ETL stuck | `ETLPipeline.run()` 在 `extract()` 之前 `_create_log()` 写入 `running`，但进程异常退出或容器重启时不会更新为 `failed`；无 watchdog 或 lease 续约机制。 | `app/data/pipelines/base.py:68-79`, `123-200` |
| P0-2 美股/Crypto 停滞 | `us_daily_etl` 在 2026-06-27 后无日志，`crypto_daily_etl` 从未写入 `etl_log`，说明调度未触发或任务未被消费。 | 数据库 `etl_log` 采样 |
| P1-3 目标日期落后 | `_resolve_a_share_target_date()` 返回数据库中 A 股最新 bar 日期，而非 `today/previous_trading_day`。 | `app/core/scheduler.py:63-84` |
| P1-4 日历不一致 | 美股、Crypto 直接 `target_date = self.target_date or (date.today() - timedelta(days=1))`，无日历过滤。 | `app/data/pipelines/us_etf.py:120-122`, `crypto_daily.py:124-127` |
| P1-5 美股覆盖不足 | `USDailyPipeline` 每天 Tiingo 轮询 50 个 symbol，其余走 yfinance。 | `app/data/pipelines/us_etf.py:124-134`, `160-181` |
| P1-6 监控缺失 | `audit_indicator_completeness.py` 仅统计 A 股 ETF 覆盖率，且 `target_date` 取最新 bar 日期。 | `scripts/audit_indicator_completeness.py:41-57`, `59-150` |
| P2-7 A 股个股 af 单点失败 | `fetch_daily_all_market()` 中 adj_factor 合并失败时整个批次降级为 1.0。 | `app/data/providers/tushare_provider.py:748-757` |
| P2-8 yfinance batch af=1.0 | `YFinanceProvider.fetch_daily_bars()` 批量分支直接设 `adj_factor=1.0`。 | `app/data/providers/yfinance_provider.py:157` |
| P2-9 SQL max_bars | `INDICATOR_SQL_MAX_BARS` 可配置低于 252，仅 warning 不阻止。 | `app/data/indicators/sql_calculator.py:101-108`, `289-299` |

---

## 四、修复建议与监控建议

### 4.1 P0 级修复（立即执行）

1. **清理 stuck 的 running ETL 日志并重启 pipeline**
   - 将 `a_share_daily_etl`（id=42、id=23）和 `a_stock_daily_etl`（id=50）的 `status` 置为 `failed`，并补充 `error_msg = "process terminated / lease expired"`。
   - 释放 Redis 锁 `daily_pipeline` 和 `a_stock_daily_pipeline`。
   - 手动触发一次 A 股 ETF + 个股 ETL，确认日线恢复写入到最新交易日。

2. **为 ETL 引入 lease/heartbeat 机制**
   - 在 `ETLPipeline.run()` 或基类中增加心跳：每 60 秒更新 `etl_log.heartbeat_at`；调度器/健康检查若发现 `heartbeat_at > 5 分钟未更新` 且 `status=running`，则自动标记为 `failed` 并释放锁。
   - 或者使用 Redis 锁的 `expire_seconds` 作为粗粒度保护，但当前已经配置（3600/7200 秒），问题在于进程挂起后没有续租也没有自动清理日志。

3. **启动美股、Crypto pipeline 的排查**
   - 检查 APScheduler 是否在运行，对应 job 是否被注册（`scheduler.get_jobs()`）。
   - 检查 Celery worker 是否监听 `celery`/`indicator`/`cninfo` 队列。
   - 检查 `crypto_daily_etl` 是否因 import 失败或 job 未注册而从未执行。

### 4.2 P1 级修复（1-2 周内）

4. **指标计算目标日期增加新鲜度检查**
   - 在 `run_indicator_calculation()` 中，若 `_resolve_a_share_target_date()` 返回的日期 < 当前 A 股上一个交易日超过 N 天（如 2 天），直接打印告警、写入 `etl_log` 并退出，而不是继续计算旧日期。
   - 新增 `run_indicator_calculation` 的 `full_history` 路径外，增加 `target_date` 参数显式化，避免静默回退。

5. **统一市场交易日历**
   - 美股：引入 `pandas_market_calendars` 或维护 `trading_calendars` 判断美股交易日；非交易日跳过 ETL。
   - Crypto：明确以 UTC 日界计算 `target_date`，避免 `Asia/Shanghai` 时区漂移。

6. **改进美股覆盖策略**
   - 方案 A：付费 Tiingo / 改用可覆盖全市场的 FMP/Polygon 付费方案。
   - 方案 B：保留轮询但增大 `us_historical_backfill` 频率/批次，同时给 yfinance 增加失败重试和失败 symbol 持久化到 `etf_holding_failed` 类似表，便于后续补录。

7. **扩展监控脚本**
   - 修改 `scripts/audit_indicator_completeness.py`：
     - 增加 `--market A股/US/CRYPTO` 参数；
     - 增加 `--max-lag-days` 检查：若最新 bar 日期 < 今天 - max_lag，直接 `CRITICAL`；
     - 检查 ETL 日志中最近 N 小时内是否存在 `running` 超过阈值的任务。
   - 新建 `scripts/audit_etl_freshness.py`：按 job 检查 `latest_success_end_time` 与当前时间差距，输出 `OK/WARN/CRITICAL`。

### 4.3 P2 级修复（后续迭代）

8. **A 股个股 adj_factor 失败降级为逐只补录**
   - 当 `fetch_daily_all_market()` 的 market-wide adj_factor 失败时，改为逐只调用 `fetch_adj_factor(ts_code)` 或至少记录失败日期，后续通过 `app/scripts/backfill_a_share_adj_factor.py` 补录。

9. **yfinance 批量下载增加复权因子计算**
   - 对 yfinance 批量路径也调用 `_compute_adj_factors()`，或至少统一使用单 code 路径获取 adj_factor。

10. **SQL 指标后端强制最低 max_bars**
    - 在 `build_indicator_query_sql()` 中，若 `max_bars < 252` 则抛出 `ValueError` 或使用 252 作为硬下限，避免误配置导致指标失真。

### 4.4 监控告警建议

- 在 `/health` 或 `/health/etl` 端点中暴露：
  - 各市场最新 `instrument_daily_bar.trade_date`；
  - 各 ETL job 最近一次 `success` 的 `end_time`；
  - 当前 `status=running` 且持续超过 1 小时的任务列表。
- 将上述指标接入 Prometheus/Grafana 或企业微信/钉钉告警，设置阈值：
  - A 股日线滞后 > 1 个交易日 → P0 告警；
  - 美股日线滞后 > 1 个交易日 → P1 告警；
  - 任何 ETL job `running` 超过 2 小时 → P1 告警。

---

## 五、结论

当前平台的数据完整性存在**多项 P0/P1 风险**，核心原因是：

1. **ETL 任务没有 stuck 检测与自动清理机制**，导致 A 股 pipeline 长期处于 `running` 而无人发现。
2. **指标计算目标日期从数据库最新 bar 推导**，数据停滞时不会告警，反而持续“成功”重算旧数据。
3. **监控脚本覆盖范围不足**，只检查 A 股 ETF 覆盖率，不检查新鲜度、不覆盖美股/Crypto、不检查 ETL 任务状态。
4. **美股数据源配额与兜底策略脆弱**，yfinance 在服务器环境不可靠，导致覆盖不全。
5. **交易日历处理不统一**，美股/Crypto 没有节假日过滤，易空跑并浪费配额。

建议立即执行 P0 修复（清理 stuck 任务、恢复 A 股/美股/Crypto 数据流），随后 1-2 周内落地 lease/heartbeat、新鲜度监控、市场日历和监控脚本扩展。

---

*报告文件：*
- Markdown: `docs/dev-notes/20260718-data-integrity-audit.md`
- HTML: `docs/dev-notes/20260718-data-integrity-audit.html`
