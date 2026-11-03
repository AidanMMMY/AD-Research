# 数据覆盖现状评估与渐进补齐方案（2026-11-04）

> 评估 agent 一次性报告：生产库实测（ECS `alloyresearch-postgres`，2026-11-04 采样）+ 代码侧取数限制考古 + 分阶段补数方案。
> 本文只做评估与方案，未改任何代码、未触发任何回填。

---

## 1. 现状表（范围 × 周期 × 行数）

### 1.1 行情主链路：etf_info / instrument_daily_bar / etf_indicator / etf_score

| 市场 | 宇宙（etf_info） | 有 bar 标的 | bar 最早 | bar 最新 | 中位行数/标的 | bar 总行数 | 指标行数 | 评分行数 |
|---|---|---|---|---|---|---|---|---|
| A股 | **7,889**（STOCK 5,593 + ETF 2,296） | 7,261 | 2010-01-04 | 2026-11-02 | 1,619 | 14,448,707 | 14,330,713 | 2,134,642 |
| US | **579**（S&P500 510 + 精选 ETF 69） | 570 | 2010-01-04 | 2026-11-02 | 4,227 | 2,253,143 | 2,241,653 | 341,933 |
| CRYPTO | **25**（人工精选清单） | 22 | **2026-07-12** | 2026-11-02 | 114 | 2,508 | 2,290 | 6,738 |

A股首批数据分布：2,100 只早于 2012（≈上市日起全史）、2015-2017 首行 1,015 只、2018-2020 754 只、2021-2023 1,094 只、≥2024 2,012 只——后半段与 IPO 波次吻合，但混入了「历史缺口」标的（见第 2 节）。

美股深度反而是三市场里最好的：493/570 只有 2012 年以前数据（中位 4,227 行 ≈ 16.8 年），真正的短板是**宇宙规模**——只有标普 500 成分股 + 69 只精选 ETF，NASDAQ 其余 ~3,000 只、罗素成分、小盘股全部缺席。

CRYPTO 是覆盖最薄的：25 个 curated 币种（`binance_provider.py:33-59`），只有约 4 个月日线，且 Binance klines 本身有 2017 年起的免费全史。

### 1.2 其他资产域覆盖面与深度

| 表 | 行数 | 标的/序列数 | 最早 | 最新 | 评价 |
|---|---|---|---|---|---|
| stock_fundamental（PE/PB/市值） | 1,079,364 | 5,593 股 | **2026-01-05** | 2026-11-02 | ⚠️ 仅 11 个月，估值史缺口最大的表 |
| adj_factor_history | 496,682 | — | **2025-12-04** | 2026-11-02 | ⚠️ 仅 11 个月（周任务按股拉全史，但表内数据从平台上线起） |
| futures_daily_bars | 212,974 | 85 合约 | 2005-01-04 | 2026-11-02 | ✅ 深度好（21 年） |
| global_index_daily_bar | 72,493 | — | 1990-12-19 | 2026-11-03 | ✅ 深度好 |
| macro_indicator | 72,296 | 65 序列（cn 15 / us 24 / global 22 / eu 4） | cn 1996-02 / 其余 2016 | 2026-11-03 | ✅ 深度可用 |
| sw_industry_index_return | — | 31 行业 | **2024-11-21** | 2026-11-03 | ⚠️ 仅 1 年 |
| cninfo_reports | 121,653 | — | 2021-07-13 | **2026-09-19** | 🔴 已停更 ~6 周（job 近期 failed，见 4.4） |
| etf_fund_flow | 109,008 | — | 2026-07-15 | 2026-11-03 | ⚠️ 仅 4 个月 |
| sec_filings | 1,477 | 49 公司 | — | — | 浅（EDGAR 全量本身免费，属可选扩面） |
| etf_holding / individual_fund_flow / market_fund_flow | — | — | — | — | 均为平台上线后增量，无深史 |

存储现状：整库 24 GB；最大表 news_article 6.5 GB、etf_indicator 5.6 GB、instrument_daily_bar 5.1 GB、cninfo_reports 2.5 GB。ECS 数据盘 /data 118 GB 用 82 GB（**余 32 GB**）。

---

## 2. 缺口量化（核心数字）

### 2.1 A股「上市日起早于首根 bar」的历史洞

以 `list_date + 30 天 < 首根 bar 日` 判定（etf_info.list_date 覆盖率 7,768/7,889）：

| 类型 | 缺口标的 | 缺口规模（日历天合计） | **估算缺失行数** |
|---|---|---|---|
| STOCK | **1,507** | 5,184,219 | **≈ 348 万** |
| ETF | **989** | 1,398,693 | **≈ 94 万** |
| 合计 | 2,496 | — | **≈ 442 万行**（按 245 交易日/年折算） |

个股缺口分布：>10 年 762 只、6-10 年 311 只、3-6 年 170 只、1-3 年 196 只、≤1 年 68 只——**762 只老股票缺十年以上**，是主力缺口。

另有：**618 只退市 A股零数据**（仅 24 只退市股有 bar）；10 只 active 无 bar。

### 2.2 其他缺口

- **估值（stock_fundamental）**：只有 2026-01-05 起。补到 2015 年 ≈ 2,800 个交易日 × 全市场（daily_basic 同样支持 1 次/日全市场 bulk）。
- **CRYPTO**：25 币全部只从 2026-07-12 起；BTC 等主流币可回补至 2017-18 年，全量 ≈ 80-100 次 Binance 分页调用，零配额。
- **US 深史**：570 只中 8 只只有 2024+ 数据、9 只零数据；受 Tiingo 500 symbols/月 + yfinance 云 IP 限制。
- **申万行业指数**：2024-11-21 起，可回补 2021（SW2021 口径发布）→ 2024。
- **ETF 资金流**：2026-07-15 起（东财接口免费，理论可回补更早，优先级低）。

---

## 3. 取数限制清单（代码考古，file:line）

### Tushare（A股市主源）
- `app/data/providers/tushare_provider.py:8-15`：免费档注释——200 req/min、**5,000 积分/天**；stock_basic 一次性、daily ≈ 2 积分/股、daily_basic ≈ 0.2 积分/股。
- `:36-41`：`_API_DELAY=0.5s`、`_BATCH_DELAY=3.0s`、`_MAX_WORKERS=5`、`_RETRIES=2`。
- `:704-714`：`fetch_daily_all_market(trade_date)` **1 次调用取全市场当日**；注释自估「~5000 行 × 2 分 ≈ 10,000 分（免费档 5,000/天）→ bulk backfill 需摊到多天」——⚠️ 该估算与生产实际（日终每天 1 次全市场调用成功）矛盾，说明现用 token 档位更高，**真实积分单价必须探针实测**（见 Phase 1）。
- `:429-447`：`new_share` 需更高积分，已有降级 fallback；`:347+` index_member 需 elevated 积分。
- `app/data/pipelines/a_share_stock_daily.py:70-77`：日终增量只从「库内最新日+1」续抓；`a_share.py:74` ETF 日终窗口仅 7 天——**历史洞永远不会被日终 ETL 自动补上**。

### Tiingo（美股主力）
- `app/data/providers/tiingo_provider.py:3-6`：免费档 **1,000 req/天、50 req/时、500 symbols/月、1 GB 带宽/月**；`:26` `_FREE_TIER_SAFE_DELAY=1.5s`；`:32` 连续 3 次 429 中止本轮。
- `app/data/pipelines/us_etf.py:34`：日更只给 Tiingo 轮转 **50 只/天**，其余靠 yfinance/Sina 兜底。
- `app/data/pipelines/us_backfill.py:44-50`：慢速回填 **每轮 15 只、每轮只拉 90 天窗**（`_HISTORY_DAYS=90`），2 小时一跑；Redis 轮转偏移 + 连续 3 次失败进 7 天冷却。
- 🔴 **生产现状：容器内 `TIINGO_API_KEY` 为空值** → `us_historical_backfill` 近 3 天失败 144 次（每小时 2 跑全挂），`us_daily_etl` 近 3 天 6 败 1 成，全靠 yfinance 从云 IP 间歇成功。整条美股链路处于带病单点运行。

### yfinance
- `app/data/providers/yfinance_provider.py:6`：非官方 ~2,000 req/时；`:24` `_SAFE_DELAY=2.0s`；`:26` `_MAX_BATCH_SIZE=20`；`us_backfill.py:25-26` 注明**云服务器 IP 被重点限流**（ECS 上不可靠，本地跑才稳）。

### FMP / Finnhub（美股宇宙发现）
- `app/data/pipelines/us_stock_discovery.py:23-24`：宇宙=**FMP 标普 500 成分**，`_MAX_COMPANIES=500`，受 FMP 免费档 250 req/天约束。
- `us_etf_discovery.py`：69 只 ETF 来自 FinnhubProvider **硬编码清单**（无 API 调用）。

### Binance / akshare（免费无鉴权）
- `binance_provider.py:33-59`：25 币 curated 清单；klines 公开端点无鉴权、1,000 根/页。
- akshare（A股市 ETF 日线、期货、申万、资金流）无配额，但无 SLA、接口随上游改版漂移（历史事故多次）。

### 既有回填基建（可直接复用）
| 工具 | 位置 | 能力 |
|---|---|---|
| `backfill_a_stock_2026.py` | `app/scripts/` | **bars / fundamental / financials 三模式**；bars 与 fundamental 均为 1 API 调用/日，专为积分档设计，支持 dry-run 与日期区间 |
| `backfill_a_share_adj_factor.py` | `app/scripts/` | 按股拉 Tushare 全史复权因子 → adj_factor_history + 镜像 daily_bar；**已挂周调度，Redis 锁 4h**（`scheduler.py:107,115,556`） |
| `backfill_us_deep_history.py` | `app/scripts/` | 美股深史 Plan C（2020→今）：core 33 走 Tiingo、非 core 走 yfinance 批 5，Redis offset 可续跑 |
| `chunked_recalc_a_share_indicators.py` | `scripts/` | A股指标分块重算，**磁盘 checkpoint 可断点续跑**（防 OOM） |
| `backfill_indicators_full_history.py` | `scripts/` | 全历史指标补算（full_history 模式一次性） |
| `recalculate_scores.py` | `scripts/` | 按日期重算评分（支持 --date / --dry-run） |
| `backfill_futures_history.py` / `backfill_global_index_ohlcv.py` / `backfill_market_fund_flow.py` | `scripts/` | 期货（调度默认 30 天，脚本可 1 万天）/ 全球指数 10y / 大盘资金流 |
| `update_daily_data.py` | `scripts/` | 增量追平 daily_bar→indicator→score→signal→backtest 全链 |
| `backfill_us_priority.py` | `scripts/` | 生成美股优先级回填清单 CSV（不动生产轮转逻辑） |

---

## 4. 分阶段补数方案

总原则：**闲暇驱动、限速保日终、免费源优先、探针先行**。全部回填动作在 backend 容器内 `docker exec` 跑脚本（与调度共用 DB），避开 15:30-21:00 CST 日终高峰，首选 23:00-06:00 CST 窗口与周末白天。

### Phase 0 · 快赢与止血（本周闲暇，≈ 半天）

| 项 | 目标 | 方法 | 预算 | 风险 | 验收 |
|---|---|---|---|---|---|
| 0.1 配置 TIINGO_API_KEY | 美股链路去单点 | tiingo.com 免费注册 → 填入 ECS `.env`（注意 compose 用 `deploy/aliyun-ecs/.env`）→ 重建 backend 容器 | 0 元、10 分钟 | 无（免费档 1,000 req/天远超日更需求） | `us_historical_backfill` 恢复 success；`us_daily_etl` 连续 3 日 success |
| 0.2 修复 cninfo_reports_daily | 巨潮公告停更 6 周（max 2026-09-19，近 3 天 2 次 failed） | 按 `news_cninfo_10m` 同期故障一起排障（先查 etl_log.error_msg） | 0 | 上游接口改版 | 表 max 日期追平至 T-1 |
| 0.3 CRYPTO 全史一次性回填 | 25 币补到各自上线日（BTC≈2017-08） | 新增小脚本：Binance klines 按 startTime 分页 1,000 根/页 → upsert instrument_daily_bar；随后跑 chunked 指标补算 | ≈80-100 次调用、0 元、<1 小时 | 无（公网无鉴权） | 每币 min(trade_date) ≤ 上线后 7 天；指标/评分自动跟进 |

### Phase 1 · A股补深（第 1-2 个月，周末+夜间窗口）

**目标**：442 万行 bar 缺口清零 + 估值补到 2015 + 复权因子全史对齐 + 指标/评分联动重算。

1. **ETF（989 只，≈94 万行）——零配额，先做**
   - 方法：akshare `fund_etf_hist_em` 按股全史（`a_share.py` 管线 / `update_daily_data.py` 模式），2296 只 × ~1.5s ≈ **1 小时跑完**，一个周末上午完事。
   - 风险：akshare 接口漂移（历史多次）；失败清单化重跑即可。
2. **STOCK（1,507 只，≈348 万行）——Tushare，探针定速**
   - 第一步（探针）：`backfill_a_stock_2026.py --mode bars --start/--end` 取 10 个历史交易日 dry-run → 真跑 → 到 Tushare 控制台看**积分流水单价**。
   - 路线 A（积分便宜）：按日 bulk，缺失日期全集 ≈ 7822 个日历日中的 ~4,000 个交易日，纯调用时长 4,000 × 0.5s ≈ 35 分钟——按每晚 200 日期限速，**≈ 1 个月夜窗跑完**。
   - 路线 B（积分贵）：按股全史 `fetch_daily_bars`（1,507 次调用；周度 adj_factor 任务已证明该模式可用），每轮限 100 只，≈ 2-3 周夜窗。
   - 顺序注意：先老后新（762 只 >10y 缺口优先，对长周期指标/回测价值最大）。
3. **估值（stock_fundamental）**：`--mode fundamental` 同为 1 调用/日；建议先补 2023→今（≈900 日），再视需求延伸 2015→2022。行数估算：2015→今 ≈ 1,200 万行 × 227 B ≈ **2.7 GB**；2023→今 ≈ 1 GB。
4. **复权因子对齐**：bar 补完后必跑一次 `backfill_a_share_adj_factor.py`（周任务会自动收敛，但主动跑一次更快），否则旧段 qfq_close 口径错。
5. **指标重算**：`chunked_recalc_a_share_indicators.py --batch-size 100` 断点续跑，348 万新行建议拆 **2-3 个周末夜窗**（OOM 已有 batch 防护）。
6. **评分重算**：`recalculate_scores.py` 只重算**最近 2 年**（评分对「当日全市场横截面」敏感，远古评分业务价值低）。

预算：Tushare 每晚新增调用 ≤ 200 次（探针后按实测积分调）；磁盘新增 ≈ bars 442 万 × 323 B + 指标 × 334 B ≈ **2.9 GB** + 估值 1-2.7 GB，合计 < 6 GB，32 GB 余量可承受。
风险与对策：积分耗尽影响日终 ETL → 夜窗限速 + 失败即停（provider 已识别权限/积分错误）；磁盘 → 跑前后 `df -h` 对账，保留 news 增长余量。
验收：`首根bar ≤ list_date+30` 的 A股标的数 ≈ 0；etf_indicator 行数增幅与 bar 同步；抽样 3 只老股（如 600xxx 1994 年上市）首行 = 上市周。

### Phase 2 · 美股扩宇宙（第 2-4 个月，月度配额节奏）

**目标**：宇宙 579 → 900+（+NASDAQ-100 与核心宽基补充），新标的深史到位。

1. 宇宙扩容：NASDAQ-100 清单（维基静态页或 FMP）复用 `us_stock_discovery.py` 的 upsert 路径注册；FMP 免费档 250 req/天足够。
2. 深史来源分层（依赖 Phase 0.1 的 Tiingo key）：
   - Tiingo 500 symbols/月 → 每月净增 ≤ 400 新标的（留 100 给日更轮转），**+NASDAQ-100 一个季度内消化**；
   - `backfill_us_deep_history.py` 扩 tier 定义后跑非 core（yfinance 批 5、Redis offset 续跑）；
   - 可选加速：本地 Mac 跑 yfinance（家宽 IP 不受限）拉 CSV → 经 API/脚本入库，绕开云 IP 限制。
3. 9 只零数据 + 8 只 2024+ 标的：确认冷却机制（7 天冷却）后手工触发一轮。

预算：0 元；Tiingo symbols/月为唯一硬约束。风险：Tiingo 免费档无 SLA、yfinance 改版；NASDAQ-100 成分季度调整需发现任务跟进。
验收：etf_info US ≥ 680；新标的 min(bar) ≤ 2020-01-04；us_daily_etl 连续周 success 率 ≥ 95%。

### Phase 3 · 深度与广度延伸（长期低优先）

- 申万行业指数回填 2021→2024-11（akshare 免费）；
- ETF 资金流更早历史（东财免费，优先级低）；
- sec_filings 扩公司覆盖（EDGAR 全量免费）；
- A股退市股 618 只历史（Tushare stock_basic 含退市，daily 按日 bulk 天然带回退市段数据——Phase 1 路线 A 顺带覆盖大部分；刻意补齐可再评估）；
- 美股再扩（罗素 1000 / 全 NASDAQ）——受 Tiingo 月配额约束，按 400/月节奏排队。

---

## 5. 三个最关键结论

1. **「一定范围、一定周期」的真身**：A股市主体其实已有上市日起的深史（7,261 只、中位 1,619 行），真缺口是 **2,496 只的早期历史洞 ≈ 442 万行**（762 只缺 >10 年）+ 估值表只有 11 个月；美股是「深度好、范围窄」（中位 16.8 年，但宇宙仅 S&P500+69 ETF）；CRYPTO 只有 4 个月。
2. **美股链路正在带病运行，且修复只要 10 分钟**：`TIINGO_API_KEY` 为空 → 慢速回填任务近 3 天失败 144 次、日更 ETL 6 败 1 成全靠 yfinance 间歇续命。这是所有美股补数动作的前置条件（Phase 0.1）。
3. **补齐可行且大部分免费**：A股市 ETF/期货/行业、CRYPTO 全史走 akshare/Binance 零配额（ETF 全史 1 小时、CRYPTO 半小时）；A股市个股/估值有现成的 1 调用/日基建（`backfill_a_stock_2026.py`），唯一硬约束是 Tushare 积分/天——**先跑 10 日期探针实测单价再定每晚批量**；磁盘总增量 < 7 GB，在 32 GB 余量内。
