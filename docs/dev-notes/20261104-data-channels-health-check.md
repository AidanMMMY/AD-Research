# 2026-11-04 数据通道健康巡检报告

> 巡检时间：2026-11-04 00:22–00:55（北京时间，周三凌晨）
> 巡检方式：只读（SSH `ad-research` + 容器内 psql / Redis / API），未改动任何代码与配置
> 日历说明：11-04 实为**周三**（巡检任务描述中"周二"有误）；11-03（周二）为 A 股交易日
> 巡检期间事件：00:36 左右发生一次**同版本容器 recreate**（docker events 见 `tag ad-research:latest`，git_sha 前后均为 74493db），非本次巡检引起，四容器 recreate 后均 healthy

## 结论速览

| 等级 | 数量 | 概览 |
|---|---|---|
| 🔴 P0 正在坏 | **2** | MiniMax 配额滚动耗尽致 LLM 链单点全灭（digest 连续 14 天全章节占位）；A 股个股/板块/大盘资金流停摆 6–14 天 |
| 🟡 P1 三天内坏过/部分坏 | **5** | 巨潮定期报告停摆 6 周+；期货日线缺口；美股 ETL 周末 6 连败 + Tiingo 回填每小时空跑；news/health 端点超时 |
| 🟠 P2 陈旧/死源/结构性 | **5** | 死源 204+（yahoo_finance、wewe-rss 公众号批次、cninfo）；A 股评分结构性滞后一个交易日；DeepSeek 不在 failover 链等 |
| 🟢 正常 | 行情主链、调度器、指标、宏观、SEC、申万等 | 详见下表 |

**一句话**：行情数据主链（A 股/美股/Crypto 的 bars→指标→信号）全部新鲜正常；坏的是 **LLM 依赖链**（digest/情绪/摘要）和**免费资金流接口**，另有巨潮公告停摆 6 周。

## 分维度明细

### 1. 调度与管线

- 调度器运行中，`/api/v1/etl/scheduler/jobs` 共 **217 个 job**，全部有 next_run（无暂停）；heartbeat 新鲜
- 状态分布：success 183 / None 25（重启后新进程内存态，非异常）/ skipped 2 / failed 3 / partial 3 / running 1
- etl_log 近 7 天非 success 记录（按 job 聚合）：

| job | 状态 | 次数 | 首次 | 最近 | 错误摘要 |
|---|---|---|---|---|---|
| us_historical_backfill | failed | 336 | 10-27 | 11-03 16:00 UTC | `TIINGO_API_KEY ... not set`（每小时空跑失败） |
| daily_digest | partial | 7/7 天 | 10-27 | 11-02 22:30 UTC | 六章节全部 failed（`overnight_news/macro_policy/market_recap/sector_rotation/watchlist_lens/outlook_risks`），时长恒定 ~73s |
| market_fund_flow_daily | partial | 6 | 10-28 | 11-03 10:35 UTC | `fetch_market_fund_flow returned empty; nothing to upsert` |
| fund_flow_daily | partial 4 + failed 1 | 5 | 10-28 | 11-03 09:30 UTC | `empty sub-tasks: individual, sector`；failed 一次为重启打断 |
| us_daily_etl | failed | 6 | 10-31 21:00 | 11-01 21:25 UTC | 周末连续失败，11-02 21:00 UTC 已恢复 success |
| cninfo_reports_daily | failed 2 | 2 | 11-03 11:55 | 11-03 12:05 UTC | `[scheduler-cleanup] process terminated or lease expired`（周二晚部署重启打断）；更早均为 success 但 **records=0** |
| futures_daily_etl | failed | 1 | 11-03 08:30 UTC | 同左 | 同上（重启打断） |
| etf_holdings / news_* 各组 | failed | 各 1–2 | 10-28~11-02 | — | 资讯分组零星失败（jiemian/aicn/edu 等），非持续性 |

- 关键管线最近一次运行：a_share_daily_etl ✅ 11-03 15:30（1643 行）、a_stock_daily_etl ✅ 16:00（5571 行）、indicator_calculation ✅、score_calculation ✅、signal_generation ✅、crypto/us ETL ✅

### 2. 市场数据新鲜度（max trade_date 实测）

期望基线（周三 00:30 北京）：A 股=11-02（**D 日 15:30 落 D-1 数据的 T-1 语义**，经代码 docstring 与行数对账证实：周二两笔 ETL 1643+5571=7214 行恰好等于 11-02 全部行数）；美股=11-02（周二盘今晨 05:00 拉）；Crypto=11-02（UTC 日）。

| 表 | A股 | US | CRYPTO | 结论 |
|---|---|---|---|---|
| instrument_daily_bar | **11-02**（7214 行） | 11-02（550） | 11-02（22） | ✅ 三市场均符合 T-1 预期 |
| etf_indicator | 11-02（7214/7214 覆盖 100%，17:00 兜底生效） | 11-02 | 11-02 | ✅ |
| etf_score | 10-30（11-02 待今晨 08:30 补，见 P2-2） | 11-02（1650 行） | 11-01 | ⚠️ A 股滞后一个周期但**不漏日期** |
| signal | 11-03（日更正常） | — | — | ✅ |
| flow_signal | 11-03 | — | — | ✅ |
| individual_fund_flow | **10-29**（停 6 天） | | | 🔴 P0-2 |
| sector_fund_flow | **10-21**（停 14 天） | | | 🔴 P0-2 |
| market_fund_flow | **10-29** | | | 🔴 P0-2 |
| etf_fund_flow（推断口径） | 11-03 ✅ | | | 正常 |

### 3. 资讯源存活

- 日摄入量（published_at）：11-03=8,523 / 11-02=11,498 / 11-01=5,607 / 10-31=5,577 / 10-30=11,635 —— 管线整体活着
- news_source_meta 共 **293 源**：3 天内活跃 **152** / 3–7 天 47 / 7–30 天 36 / **>30 天无产出 48** / 从未产出 10
- 全库历史（news_article 出现过 **1137 个 source**）：近 3 天零产出 465 个，其中 **>30 天无产出 204 个**（156 个不在 meta 表，属历史遗留）
- 重点死源（证据=最后发文时间）：

| 源 | 最后发文 | 说明 |
|---|---|---|
| yahoo_finance | 2026-07-26 | 累计 10,004 篇的头部源，死了 3 个多月 |
| cninfo | 2026-09-18 | 与 P1-1 巨潮停摆同源 |
| wechat_latepost / zhigu / lixunlei / congming / canghai / fupeng 等 | 2026-07-25~29 批量停止 | wewe-rss 批次整体死亡（与 7 月 wewe-rss token 过期记录吻合） |
| global_financial_post | 2026-10-31 | 累计 7,419 篇，3 天断流（此前周产 ~350） |
| 微信镜像 2020–2025 停更号约 40 个 | 各年份 | wechat2rss 镜像自然退役 |

- `GET /api/v1/news/health`：**超时（>60s 无响应）**——端点自身性能问题（P1-5）；`/api/v1/news/stats/sources` 正常返回

### 4. 辅助数据

| 数据 | 最新 | 结论 |
|---|---|---|
| daily_digest | report_date 11-03，但 content_md 仅 278 字符（六章节全为"本节因数据/模型原因暂缺"占位）；近 14 天全部 partial | 🔴 并入 P0-1 |
| macro_indicator | us/global=11-03、cn/eu=11-02 | ✅ |
| sec_filings | 10-30（SEC EDGAR 周更，周六跑，下次 11-07） | ✅ |
| cninfo_reports | **2026-09-18**（近 8 天 0 条入库；job 每天跑但 records=0） | 🟡 P1-1 |
| sw_industry_index_return | 11-03 | ✅ |
| futures_daily_bars | 11-02 仅 **42/57** 根（周二任务被重启打断），11-03 待今日 16:30 补 | 🟡 P1-3 |

### 5. /health 全量输出（00:39 实测，部署 recreate 后）

```json
{
 "status": "ok", "ready": true, "version": "0.1.0", "git_sha": "74493db",
 "db": "ok", "redis": "ok",
 "components": {
   "db": {"status": "ok"},
   "redis": {"status": "ok"},
   "scheduler": {"status": "ok", "running": true},
   "data": {"status": "ok", "stale_markets": [],
            "markets": {"overall": {"status": "ok", "age_days": 2, "latest_date": "2026-11-02"}}},
   "llm": {"status": "ok", "minimax_configured": true, "deepseek_configured": true,
           "chain_order": ["minimax", "glm", "kimi"], "active_chain": ["minimax"],
           "cooling_down": ["minimax"], "last_used_provider": null}
 }
}
```

注：`llm.status=ok` 但 `cooling_down=[minimax]` 且链上无可用备用——health 对 LLM 的判定偏乐观，与实际 digest/情绪全灭矛盾（建议把 provider 全冷却时降级为 degraded）。

### 6. Redis 状态

- `llm:provider_down:minimax = 1`（TTL ~45min，6h 冷却窗口内）——与日志互相印证
- `quota exhausted (2056)` 日志：**11-02 00:00 UTC 以来 273,617 条**（约 13.7 万/天，重试风暴；来源 sentiment_pipeline / news summary / digest）
- `sentiment:article:*` **9,971 键**待处理积压（LLM 饥饿的直接后果）
- MiniMax 日调用量：10-31=955 / 11-01=408 / 11-02=276 / 11-03=565（冷却恢复后仍可用，配额为滚动耗尽而非永久耗尽）
- celery unacked 各 1 条，无拥堵；`ad_research:scheduler:heartbeat` 新鲜
- 容器内存均低（backend 245MB/3GB）；磁盘 / 46%、/data 72%

## 异常清单（分级）

### 🔴 P0（正在坏）

1. **MiniMax 配额滚动耗尽 + failover 链无备用 → LLM 依赖功能全灭窗口**
   - 证据：27.3 万条 `quota exhausted (2056): all LLM providers in cooldown: ['minimax']`；`llm:provider_down:minimax` 存在；GLM_API_KEY/KIMI_API_KEY/ZHIPU_API_KEY 均未配（容器 env 实测 EMPTY）；daily_digest 连续 14 天 partial、最新一期六章节全占位（278 字符）；sentiment 积压 9,971 键
   - 影响面：每日 AI 综合研报（四渠道推送的是空壳）、资讯 AI 摘要/情绪、翻译质量链路
   - 处置建议：① 给 MiniMax 充值/提额（每日早间 06:30 digest 窗口稳定撞冷却）；② **配置 GLM 或 KIMI key** 激活既有 failover 链（链路代码已就绪，memory 记录 7 月即部署）；③ LLM 恢复后 sentiment 积压可自消化，无需手动 reset
2. **A 股个股/板块/大盘资金流停摆**
   - 证据：individual max=10-29、sector max=10-21、market max=10-29；fund_flow_daily 连续 4 天 partial（`empty sub-tasks: individual, sector`）+ 1 failed；market_fund_flow_daily 连续 6 天 partial（`returned empty`）；etf_fund_flow（推断口径）正常=11-03
   - 处置建议：排查 Tushare moneyflow 系接口（疑似积分门槛/接口下线），可临时切 akshare 同类接口；flow_signal 当前靠推断口径撑着（11-03 有数），但口径已与 individual/sector 断层

### 🟡 P1（3 天内坏过）

1. **巨潮定期报告停摆 6 周+**：cninfo_reports 最新公告 2026-09-18；job 每天执行且报 success 但 records=0（"成功空转"），11-03 两次 failed 为部署重启打断。对照 20260707 修复记录排查接口翻页/日期参数（secid/orgId）。资讯源 `cninfo` 同步死（9-18 后 0 文）
2. **期货日线缺口**：futures_daily_etl 周二 16:30 被部署重启打断（lease expired）；11-02 仅 42/57 根。今日 16:30 自动跑 11-03，11-02 缺口需手动触发一次回补（run-now 或 re-run）
3. **美股 ETL 周末 6 连败**：10-31 21:00 ~ 11-01 21:25 UTC 失败 6 次，11-02 已自愈；us_daily=11-02 正常。观察下个周末是否复现（周一为美股非交易日，失败或与空数据日处理有关）
4. **us_historical_backfill 每小时空跑失败 336 次/7天**：TIINGO_API_KEY 未配（长期已知）。建议：配 key 或在 config 层禁用该 job，停止无效重试噪音
5. **news/health 端点超时**（>60s）：stats/sources 正常，说明是 health 端点自身聚合过重，需加缓存或瘦身

### 🟠 P2（陈旧/死源/结构性）

1. **死源清单**（建议在 news_source_meta 加 is_active 标记并策展退役）：meta 内 48 源 >30 天无产出 + 10 源从未产出；重点：yahoo_finance（7-26 起）、wewe-rss 公众号批次（latepost/zhigu/lixunlei/congming/canghai 等，7 月底齐死，10,000+ 篇级别的头部源）、global_financial_post（10-31 断流）；另有 156 个不在 meta 的历史遗留源
2. **A 股评分结构性滞后一个交易日**：ETL 为 T-1 语义（D 日 15:30 落 D-1 数据）而评分在 D+1 日 08:30 → A 股 score 永远基于 T-2 收盘（当前 10-30；11-02 将于今晨 08:30 自动补上，**不漏日期**）。美股链（05:00 拉隔夜盘→05:30 指标）无此问题。改进方向：评分挪到 17:30（指标兜底 17:00 之后）或 ETL 改当日 15:30 语义
3. **DeepSeek key 已配但不在 failover 链**：chain_order=[minimax, glm, kimi]，DeepSeek 402 余额问题后已移出；若 DeepSeek 已充值可考虑重新入链作为第二备用
4. **/health llm 判定偏乐观**：provider 全冷却时仍报 ok（见第 5 节注）
5. **部署时点保护缺失**：周二晚 20:22 与本次 00:36 两次容器 recreate 均打断在跑任务（futures/cninfo lease expired 即此因）；建议部署脚本前置检查 in-flight ETL 或改在 01:00 后低峰窗口

## 今日（11-04 周三）应自动发生的事项（验证点）

- 05:00 us_daily_etl 拉美股周二盘 → US bars 应变 11-03
- 08:00/08:30/09:00 指标/评分/信号 → A 股 etf_score 应补出 11-02（指标门控已满足：7214/7214）
- 08:05/08:30 crypto ETL/指标 → CRYPTO 应变 11-03
- 15:30/16:00 A 股 ETL → bars 应变 11-03
- 06:30 daily_digest → **若 MiniMax 配额窗口未恢复，将产出第 15 天占位研报**（P0-1 验证点）

---

*报告生成：数据通道健康巡检 agent（只读巡检）；证据均为 2026-11-04 00:22–00:55 北京时间实测。*
