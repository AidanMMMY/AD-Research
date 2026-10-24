# 后端健康度摸底报告（app/ 全面体检）

**摸底日期**：2026-10-25（HEAD 212a9ec，main）
**摸底方式**：只读代码走查 + AST/grep 模式扫描（分层、鉴权、N+1、索引、孤儿代码、调度时序），未修改任何源代码
**范围**：`app/` 共 500 个 Python 文件——44 个 router（api/v1）、40+ service、2682 行 `app/core/scheduler.py`、4 个 Celery 任务模块、26 张模型表、~40 条 ETL pipeline
**背景基线**：AGENTS.md、`20260701-platform-logic-audit.md`、`20260718-platform-indicator-audit-report.md`、`20260718-data-integrity-audit.md`、`20260628-ROADMAP.md`、20261024 首登改密（新代码质量基线）

---

## 一、结论速览

1. **总体健康度：中上，且较 2026-07 审计基线显著改善。** 历史 P0（14 项逻辑/安全类 + 调度/数据完整性类）绝大多数已修复且在代码注释中留了根因沉淀；鉴权、密钥治理、时区、misfire、ETL stuck 清理、连接池等曾经的系统性弱点均有工程化对策。
2. **本轮发现 P0×1、P1×4、P2×6、P3×8。** 唯一 P0 不是安全或单点 bug，而是**调度时序竞态**：评分(08:30)/信号(09:00) 与指标计算 Celery 任务（08:00 投递、可跑小时级、逐 chunk 渐进落库）之间没有完成同步，指标任务一旦超过 30 分钟（7100 标的的常态），当天评分会在"半宇宙"上计算横截面百分位并落库，且评分一天只跑一次、无兜底，错误分数当天不会被自动纠正。
3. **安全基本面好**：44 个 router 全部挂鉴权依赖或 internal token（唯一匿名端点 `/stream/prices` 为文档化的公开行情设计）；admin-only 端点覆盖真实交易下单/撤单/熔断重置、部署面板、用户管理；无 SQL 字符串拼接（唯一 `text(f...)` 是常量超时设置）；`AUTH_SECRET_KEY` 弱值非 dev 直接拒启；internal token 用常数时间比较；登录/改密有 Redis 限流；日志有 sanitize。
4. **效率面**：热点表索引齐备（etl_log/news/indicator/score/signal/trading）；news 列表与关联查询已批量化；SSE 曾经的连接池占用问题已修（session 不跨 yield、查询进线程池）；scoring 按市场分组批量 + 主动缓存失效。低效主要集中在**调度链**（信号生成 O(策略×全市场) 串行、auto_trade 循环内外部行情调用）与个别 router 的小 N+1。
5. **分层**：`api → services → models` 主干清晰（28/44 router 零直查 DB）；债务集中在 `news.py`（1500 行、24 处直查 ORM，业务逻辑与路由耦合）。`data/repositories` 层仅 1 个文件被使用，与 AGENTS.md 描述存在漂移。
6. **历史核对**：下表 26 项中 22 项已修复、3 项仍存在、1 项部分修复，另有 4 项本轮未复核（见核对表尾注）。

---

## 二、P0 发现

### P0-1 评分/信号与指标计算存在跨进程竞态：dispatch 即放锁，评分读到"半宇宙"指标

**问题描述**
08:00 `run_indicator_calculation` 解析目标日后，拿到 `daily_pipeline` 锁、`calculate_indicators.delay(...)` 投递 Celery 任务，随后**立即释放锁**（with 块结束）。指标任务自身可运行 4-6 小时（soft 4h / hard 6h），SQL 后端按 chunk 执行并**逐 chunk `db.commit()` 渐进落库**。08:30 `run_score_calculation` 只等待 `daily_pipeline` 锁（此时早已释放），`ScoringService.calculate_daily_scores` 按"每市场最新指标日"取全市场指标行，**没有任何行数/覆盖率校验**。09:00 信号生成同理。

**证据**
- `app/core/scheduler.py:602-623`（dispatch 后 with 块结束即放锁）；`app/core/scheduler.py:1550-1557`（08:00 job）、`app/core/scheduler.py:1574-1581`（08:30 评分 job）
- `app/tasks/indicator.py:42-49`（soft_time_limit=4h、time_limit=6h）
- `app/data/indicators/calculator.py:417`（`updated_count += _batch_calculate_indicators_sql(...)` 逐 chunk）、`calculator.py:461`（循环内 `db.commit()`）、`calculator.py:597-618`（chunk 循环 + UPSERT）
- `app/services/scoring_service.py:186-212`（按 `max(trade_date)` group by market 取数后直接 `.all()` 全量计算，无覆盖率检查）
- 评分一天仅 08:30 一跑（无评分兜底 job；17:00 兜底只补指标，见 `scheduler.py:1558-1573` 注释）

**影响**
指标任务运行超过 30 分钟时（7000+ 标的的常态），08:30 评分把目标日的 `etf_indicator` 当作完整横截面，实际只有部分标的落库 → 百分位排名与 composite_score 系统性失真并**落库对外**；09:00 信号基于同样的不完整指标。当天不会再有评分重跑，错误分数持续一整天（直到次日 08:30）。

**修复建议**
1. 评分/信号入口先等待指标完成信号：复用 `_acquire_indicator_date_lock` 的日期锁（任务结束才释放，`tasks/indicator.py:15-32`）轮询至消失，或查询 `etl_log` 中 `indicator_calculation` 当日 success；
2. 评分前校验覆盖率：目标日 `etf_indicator` 行数 / active universe ≥ 95% 才计算，否则延迟重试（APScheduler `add_job` + `minutes=15` 重排）；
3. 对齐兜底：增加 17:30 评分兜底 job（与 17:00 指标兜底配套），并让 paper_trade_auto 等评分完成信号。

**验证方法**
生产侧：取历史某日，比较 `etl_log` 中 `indicator_calculation` 的 end_time 与 `score_calculation` 的 start_time，统计 overlap 天数；再对比当日 `etf_indicator` 行数与 `etf_score` 计算基数是否一致。本地侧：sqlite 内存库复现"逐 chunk 提交 + 中途评分"断言部分行可见。

---

## 三、P1 发现

### P1-1 stuck-ETL 清理阈值（120 分钟）与合法长任务冲突，会误删活锁

**问题**：`cleanup_stuck_etl_jobs` 每小时 :45 将 `running` 超过 120 分钟的 ETLLog 标为 failed 并删除映射的 Redis 锁。但多个 job 的合法运行时长 ≥ 2h：信号生成锁 TTL 按公式可到 14400s（4h）；`a_share_adj_factor_backfill` 锁 4h；指标 Celery 任务 6h；cninfo 日报锁 2h。`_ETL_JOB_LOCK_MAP` 把 `signal_generation`/`score_calculation` 映射到 `daily_pipeline`，即清理会删掉**仍在被合法持有的** `lock:daily_pipeline`。
**证据**：`app/core/scheduler.py:90`（阈值 120）、`scheduler.py:1366`（`min(14400, ...)` 锁 TTL）、`scheduler.py:140-141`（映射）、`scheduler.py:216-279`（清理逻辑删锁）、`app/tasks/indicator.py:48`（6h）、`scheduler.py:460`（adj_factor 4h 锁）。
**影响**：① etl_log 误报 failed（监控/面板失真，任务结束时又改回 success，中间窗口误导运维）；② 锁被提前删除后，`paper_trade_auto`（09:30 起 wait 3600s，`scheduler.py:1299-1304`）可提前闯入，与仍在运行的信号生成**并发**执行——模拟交易读到不完整信号；③ 多实例场景下其它等锁任务同样可能提前并发。
**建议**：给 `_ETL_JOB_LOCK_MAP` 增加 per-job `max_runtime`（signal/indicator/adj_factor/cninfo 用 4-6h，其余维持 2h），清理按 job 阈值判断；或为 `record_etl` 增加 `heartbeat_at` 列（长任务每 5 分钟续约），清理只回收无心跳行。
**验证**：人为构造 130 分钟的 signal_generation 运行，观察 :45 清理日志、etl_log 状态翻转、paper_trade_auto 是否提前执行。

### P1-2 信号生成 O(策略数 × 全市场标的) 串行，是调度链最大瓶颈

**问题**：`run_signal_generation` 载入**全部** active instrument（A 股 ETF+个股+美股+Crypto，7000+），非横截面策略对每个标的逐一调用 `signal_service.generate_signals`（每次含行情查询+指标计算+持久化），单线程串行。
**证据**：`app/core/scheduler.py:1346-1364`（etfs 全量载入）、`scheduler.py:1422-1436`（逐 ETF 循环）；横截面策略已有批量路径（`scheduler.py:1411-1420`）作对照。
**影响**：耗时随活跃策略数线性放大（可到小时级）；期间持有 `daily_pipeline` 锁 → `paper_trade_auto` 最多等 1h 后放弃（当日模拟交易缺失）；也推迟 17:00 指标兜底取锁。
**建议**：① 策略配置增加适用域过滤（market / instrument_type），ETF 动量策略不必跑 5600 只个股；② 逐标的策略改为分片并行：复用指标任务的 `code_prefix` 分片机制（`app/tasks/indicator.py:56-76`）投 Celery；③ `paper_trade_auto` 改事件驱动（等 `signal_generation` 的 etl_log success，而非等锁）。
**验证**：生产 etl_log 统计 `signal_generation` 的 duration_seconds 分布；改造后对比。

### P1-3 `auto_trade_from_signals` 循环内 N+1 + 每信号一次外部行情 HTTP + 静默吞异常

**问题**：每个账户对当日**全部**信号逐条处理；每条 BUY 都 `get_positions(account_id)`（全量查询）+ `_get_current_price`（provider 实时行情，单标的外部 HTTP）；SELL 逐条查持仓。调度侧循环 `except Exception: continue` **无任何日志**。
**证据**：`app/services/paper_trading_service.py:661-704`（循环）、`paper_trading_service.py:748-759`（单标的行情）；`app/core/scheduler.py:1321-1328`（静默 continue）。
**影响**：数百条 BUY 信号 = 数百次串行 HTTP + 2N 次 SQL，跨账户重复执行；任何失败（配额、超时、下架币）零可观测。
**建议**：账户持仓一次载入并增量维护；价格改批量 quotes（provider 已支持列表入参）；调度循环至少 `logger.exception`。
**验证**：日志中统计单次 `paper_trade_auto` 的行情调用次数；注入异常验证有告警。

### P1-4 cninfo_pdf 与巨潮日报共享 cninfo 队列，重提取会饿死时效任务

**问题**：PDF 文本提取（长 CPU/IO，生产语料 14GB）与 17:00 定期报告日刷同在 `cninfo` 队列（worker 并发 2）。
**证据**：`app/core/celery_app.py:55-60`（路由表）；`app/tasks/cninfo_pdf.py:10`（自述共享队列）、`:46`、`:290`（任务定义）。
**影响**：大批 PDF 回填期间，17:00 `cninfo_reports_daily` 排队延迟，次日早间研报链路（摘要/日报）连锁滞后；反向亦然。
**建议**：拆 `cninfo_pdf` 独立队列 + 独立 worker（或 `worker_concurrency` 隔离）；保持 `task_acks_late`。
**验证**：ECS 上 `celery inspect active_queues` 观察两类任务争抢；拆分后日报刷新耗时不随 PDF 批量波动。

---

## 四、P2 发现

### P2-1 `signal` 表缺 `trade_date` 单列索引
`WHERE trade_date = :d ORDER BY created_at`（`paper_trading_service.py:649-653`，auto-trade 每日高频）只能全扫：现有索引为 `(etf_code, trade_date)` 复合（leading 不匹配）与 `created_at.desc()`；唯一约束 leading 是 `strategy_id`（`app/models/etl.py:187-194`）。signal 表日增万级行。建议 alembic 加 `ix_signal_trade_date (trade_date)`（可含 created_at 第二列）。验证：`EXPLAIN ANALYZE` 前后对比。

### P2-2 全局请求限流缺失；SSE 匿名端点无参数与连接上限
限流仅覆盖 login/change-password（`app/api/v1/auth.py:151,216`），其余 API 无 rate limit（20260701 审计遗留）。`/api/v1/stream/prices`（`app/api/v1/stream.py:320-334`）设计为匿名公开，但 `codes` 数量无上限（一条连接可携带任意多 code → IN 查询放大），连接数无上限，每 3s 一次 DB 查询、300s 生命周期。建议：SSE codes 截断（如 ≤50）+ 全局 slowapi/中间件级限流（至少对匿名端点）。

### P2-3 回测在 HTTP 请求内同步执行引擎
`POST /backtests`（`app/api/v1/backtests.py:27-45`）与 cross_sectional（`:78-100+`）直接在请求线程跑完整引擎（多年历史 × 多标的），分钟级占用 worker 线程 + DB 连接（pool 15/30）。个人平台可接受，但与 pool_timeout=10 的"快速失败"策略相互作用：并发回测易触发排队 504。建议：改 Celery/BackgroundTasks + 轮询结果（digest regenerate 的 202+轮询模式可复用，`app/api/v1/digest.py:176-207` 是现成范本）。

### P2-4 `news.py` 路由 1500 行、24 处直查 ORM：分层债务最大户
news 路由内嵌市场过滤扩展、ILIKE 全文搜索、关联子查询、序列化、健康面板等完整业务逻辑（`app/api/v1/news.py:268-430` 等）。次要：`stats.py` 13 处、`learning.py`/`search_trends.py` 各 6 处（auth/admin_users 的直查属合理例外）。建议：抽 `NewsQueryService`，路由只做参数校验与响应组装；新增端点立规矩"先进 service"。

### P2-5 `etl_status.py` 运维面板每请求 21 次逐 job 查询
`_build_task_summary` 对 21 个 tracked job 逐个 `ORDER BY created_at DESC LIMIT 1`（`app/api/v1/etl_status.py:73-80`），是教科书式 N+1（有 `idx_etl_logs_job` 支撑、量小可忍）。建议：窗口函数 `ROW_NUMBER() OVER (PARTITION BY job_name ORDER BY created_at DESC)` 一次取全。

### P2-6 美股历史回填覆盖策略仍依赖配额轮询
`us_historical_backfill` 每小时跑、每轮 ~15 只（`app/core/scheduler.py:508-529`），569 只美股全量轮转周期以周计；Tiingo 免费层 50 req/h 限制未变（20260718 P1-5 遗留）。日终主链路已改 FMP 主 + Tiingo 兜底（`scheduler.py:483-505` docstring），属部分改善。建议：持久化"缺口标的"清单按需回填，而非匀速轮转。

---

## 五、P3 发现（低危 / 卫生类）

1. **print 与 logging 混用**：非测试代码 232 处 `print(`，`scheduler.py` 全量使用 print（含告警语义的 `⚠️ [SCHEDULER_WARN]`），docker logs 可检索但无级别/无结构化。建议统一 `logging`。
2. **`@cached` 装饰器是死代码且键设计有缺陷**：`app/core/cache.py:88-121` 全仓零使用；且默认键含 `*args`（服务方法即 `self`，`str(self)` 带内存地址 → 永不命中），也未走容错路径。要么删除，要么修键策略（仅用显式 `key_func`）。
3. **`RiskRule` 表仍无消费者**：动态风控规则表只有只读 list 端点（`app/api/v1/live_trading.py:534-541`），`risk_control.py` 全部读 `LiveTradeConfig` 硬编码（20260701 #9 的残留半边）。
4. **`ETFCorporateAction` 孤儿表**：全仓仅模型定义，无 pipeline 写入/读取（复权因子现已走 Tushare `adj_factor` + 周日回填 + yfinance 推导，公司行为表失去存在必要，建议删表或补写入方）。
5. **`redis_lock` token 用 `time.time()`**（`app/core/redis_client.py:57`）：非随机 token，同一微秒双进程可互相删除对方的锁（概率极低）；换 `uuid4().hex` 一行事。
6. **repositories 层名存实亡**：仅 `price_repository.py` 被 5 个 service 使用，AGENTS.md 的"api→services→models/data.repositories"与现实漂移；建议要么明确 repositories 只服务行情读取，要么从文档移除该层。
7. **FRED 手动刷新同步执行**（`app/api/v1/macro.py:152-173`，admin-only，分钟级 HTTP）；对比 digest regenerate 已是线程 + 202 + 轮询的范本。
8. **`ETFService.upsert_holdings` 匹配键与唯一约束不一致**：按 `(etf_code, holding_code, holdings_as_of_date)` 查重（`app/services/etf_service.py:768-777`），而表唯一约束是 `(etf_code, snapshot_date, holding_code)`（`app/models/etf.py:340-346`）——两列由 ETL 保持同步所以现状能跑，但重放/并发下可能撞约束，建议统一走 snapshot_date。

---

## 六、历史问题核对表

对照 `20260701-platform-logic-audit.md`（14 项 P0 + 运维项）、`20260718-platform-indicator-audit-report.md`、`20260718-data-integrity-audit.md` 逐项核实现状（"已修复"均给出本轮证据位置）：

| # | 历史问题 | 现状 | 证据（本轮核实） |
|---|---------|------|-----------------|
| 1 | ETFInfo dataclass 缺 sector/industry/list_date → TypeError | **已修复** | `app/data/providers/base.py:20-23` 字段齐备 |
| 2 | A 股 ETF ETL 未按 instrument_type 过滤 | **已修复** | `app/data/pipelines/a_share.py:45` |
| 3 | Binance change_pct 用 high 计算 | **已修复** | `app/data/providers/binance_provider.py:316-322`（prev-close 基准，含注释） |
| 4 | upsert 丢弃合法零值 | **已修复** | `a_share.py:139-152`（cols_with_data 只剔全 NULL 列，0 值保留） |
| 5 | 回测交易成本模型错误 | **已修复** | `app/services/backtest_engine.py:176-217`（名义金额计费、A股卖出印花税、¥5 最低佣金） |
| 6 | 回测信号用复权价、成交用 raw close | 未逐行复核 | 指标层已统一 qfq（20260718 验证），回测成交价未在本轮范围内核对 |
| 7 | 信号去重 seen_keys 永不命中 | **已修复** | `app/services/signal_service.py:38-44`（key 含 type） |
| 8 | 模拟交易胜率占位 | **已修复** | `paper_trading_service.py:513-546`（FIFO 成本配对） |
| 9 | 真实交易下单/撤单仅需普通登录 | **已修复** | `live_trading.py:359-366 / 461-466 / 519-523`（require_admin）；RiskRule 半边残留见 P3-3 |
| 10 | 风控日盈亏累计全部历史 | **已修复** | `app/services/risk_control.py:189-205`（按今日 updated_at 过滤 + 时区说明） |
| 11 | return_1w 等窗口 off-by-one | **已修复** | `app/data/indicators/risk.py:163`（窗口映射表） |
| 12 | CORS `allow_origins=["*"]` + credentials | **已修复** | `app/main.py:104-120`（env 驱动、wildcard 时禁 credentials） |
| 13 | SECRET_KEY 弱默认值 | **已修复** | `app/config.py:27-52, 302-352`（已知弱值清单 + 非 dev 拒启） |
| 14 | Scheduler 模块导入即启动（多 worker 重复） | **已修复** | `app/main.py:426-485`（startup event + flock + ENABLE_SCHEDULER） |
| 15 | CronTrigger 未指定时区 | **已修复** | `scheduler.py` 全部显式 `timezone="Asia/Shanghai"/"UTC"` |
| 16 | Job 失败仅打印日志、无告警 | **部分修复** | 有 etl_log 面板 + freshness 告警页 + internal watchdog（20260723）；集中通知（如备份失败接 watchdog）仍待接（memory 20260822） |
| 17 | 无请求限流 | **仍存在** | 仅 login/改密限流（auth.py:151,216），见 P2-2 |
| 18 | 无审计日志表 | **已修复** | `audit_log` 模型 + `app/core/audit.py` + admin_users 4 处 `record_audit` |
| 19 | ATR 用 SMA 非 Wilder 平滑 | 未复核 | 本轮未比对 |
| 20 | Crypto seed 列表与 provider 默认不一致 | 未复核 | — |
| 21 | Crypto ETL 时区 bug / 从未写日志 | **已修复** | `crypto_daily_etl` job 在册（scheduler.py:1642-1649），docstring 记录 Binance failover 上下文 |
| 22 | 美股 21 天无成功记录 | **已恢复** | `us_daily_etl` 05:00 在册，FMP 主源 + Tiingo/yfinance 兜底 |
| 23 | ETL stuck 无清理 | **已修复（有新边界）** | 每小时 :45 + 启动清理（scheduler.py:216-279, 2561-2568）；新引入阈值冲突见 P1-1 |
| 24 | 指标目标日期无法发现数据停滞 | **部分修复** | `_resolve_a_share_target_date` 滞后 >2 天仅打 warning（scheduler.py:169-183），未接主动告警 |
| 25 | yfinance batch adj_factor=1.0 | **已修复** | 20260718 报告确认（Adj Close/Close 推导），本轮未重验代码 |
| 26 | 评分风险维度符号 / 按市场取最新日 / rank_category 失效 | **已修复** | 20260718 修复 + 7-19 生产验证（覆盖 86%）；`scoring_service.py:181-221` 现为按市场分组 |
| 27 | 板块轮动 RS 反转 / 信号窗口 | **已修复** | 20260718 Phase 2.11（差值 + 5 交易日） |
| 28 | 资金流默认日期/过滤失效 | **已修复** | 20260718 Phase 1.7 |
| 29 | APScheduler misfire 默认 1s 丢 tick（20260727 P0） | **已修复** | `scheduler.py:79-82`（grace 300s + coalesce + hourly jitter=600） |
| 30 | 首登强制改密（20261024 基线） | **已落地，质量好** | `deps.py:85-135`（403 门禁 + jti 黑名单 + must_change_password 白名单端点）、`auth.py:199-267`（改密轮换全部 refresh token）；作为本轮新代码质量参照 |

> 附注（仍存在但属产品取舍）：港股/日股 discovery/ETL pipeline 至今未建（20260701 §3.2 提及，`app/data/pipelines/` 无 hk/jp 管线）；点-in-time 基本面与无幸存者偏差回测（20260701 P2 战略项）未启动。

---

## 七、值得沉淀为 runbook / 口诀的知识点（只列清单，落库由主会话策展）

1. **"投递 ≠ 完成"**：调度器把 Celery 任务 `.delay()` 出去后 with 块结束即放锁；下游任务要等**完成信号**（etl_log success / 日期锁消失），不能按调度时刻推算顺序。（P0-1 的根因）
2. **"清理阈值必须 ≥ 最长合法运行，且按 job 分级"**：stuck 清理是护栏不是闹钟；上清理机制前先枚举每个 job 的合法时长上限（信号 4h、指标 6h、adj_factor 4h vs 默认 2h）。（P1-1）
3. **"横截面计算前先验 universe 覆盖率"**：排名/百分位类计算对缺失行敏感，读"最新日期"前先比对行数与基数，不足则推迟。（P0-1 的防御性口诀）
4. **"队列即并发预算"**：重提取（PDF）与时效任务（17:00 日报）不共队列；worker 并发数是预算不是默认值。（P1-4）
5. **"router 直查 DB 的面积要有预算"**：新端点先问能否进 service；news.py 是 1500 行演化失控的样本，治理从"不再增长"开始。（P2-4）
6. **"缓存装饰器的键别含 self/ORM 对象"**：`str(self)` 带内存地址 → 永不命中；键必须来自显式 key_func。（P3-2）
7. **"SSE/长连接三件套"**：session 不跨 yield、同步查询丢线程池、请求参数（codes 数）与连接数都要设上限——本项目已做到前两条，缺第三条。（P2-2）
8. **"锁 token 必须随机"**：`redis_lock` 用时间戳做 token 属侥幸正确，uuid4 才是标准姿势。（P3-5）

---

## 八、本轮摸底未覆盖 / 建议下轮补查

- 回测引擎是否全程使用 adj_close 成交（历史 #6 未复核）
- `app/services/news/scheduler_jobs.py`（1921 行）的 170+ 源 job 内部实现质量（本轮只验证了 drain/importance gate/超时配置存在且与 memory 记录一致）
- alembic 迁移与 models 的一致性（`adj_factor_history` 在 models/etf.py:185 与 :231 出现两处 Index 声明样貌，建议下轮核对是否历史遗留重复定义）
- 港股/日股管线取舍的产品决策
- `pytest --collect-only` 收集健康度与 e2e 覆盖（CI 已有 1000+ 用例，本轮未跑）

*本报告为只读摸底产物，未修改任何源代码；md + html 双格式落盘。*
