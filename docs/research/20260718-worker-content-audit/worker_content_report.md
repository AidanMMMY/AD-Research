# Worker 内容巡检报告

**生成时间:** 2026-07-18 09:27:13 UTC (UTC)

**巡检范围:** ECS 生产环境 (host `ad-research`) 上的 8 支资讯/情绪 Worker（Celery、APScheduler、新闻爬虫、LLM 情绪流水线）

**数据来源:** 仅读 backend 容器内 PostgreSQL（`news_article`、`sentiment_data`、`etl_log`），未写入或删除任何生产数据。

## 一、执行摘要

### ECS 容器状态

| 容器名 | 状态 | 备注 |
|---|---|---|
| alloyresearch-backend | Up 2h (healthy) | 主 API / APScheduler |
| alloyresearch-celery-worker | Up 2h | Celery 4 并发 worker |
| alloyresearch-postgres | Up 40h (healthy) | PostgreSQL 5432 |
| alloyresearch-redis | Up 41h (healthy) | Redis 6379 |
| alloyresearch-nginx | Up 2h | 80/443/8000 |
| alloyresearch-overnight-research | Up 2h | 8000/tcp |
| alloyresearch-hermes | Up 6d | 8000/8080/9090 |

> 主机负载：`6.10, 5.75, 5.52`（22 天 uptime，负载正常偏高，与正在运行的 A 股指标重算一致）。

### Celery Worker 状态

| 项目 | 值 |
|---|---|
| 启动命令 | `celery -A app.core.celery_app worker -l info -c 4 -Q celery,indicator,cninfo` |
| 并发模型 | prefork |
| 最大并发数 | 4 |
| 当前活跃任务 | 4（cninfo_pdf × 2、indicator_calculate × 1、cninfo_backfill × 1） |
| 在线节点 | 1 |

### APScheduler 调度器状态

- 调度器心跳存在（Redis `ad_research:scheduler:heartbeat` 存在），Leader 存活。
- 从 Redis 快照读取到全部 53 个调度任务，其中 8 个资讯/情绪任务见下表。

### 数据总量概览

| 表 | 近 7 天记录数 | 本次采样数 |
|---|---|---|
| news_article | 6215 | 500 |
| sentiment_data | 174 | 174 |

- **24h 新增新闻来源分布**：[{'source': 'yahoo_finance', 'count': 602}, {'source': 'sina_finance', 'count': 121}, {'source': 'cointelegraph', 'count': 17}, {'source': 'coindesk', 'count': 11}, {'source': 'cninfo', 'count': 9}, {'source': 'cnbc', 'count': 1}, {'source': 'sec_edgar', 'count': 1}]。
- **7d 新增新闻来源分布**：[{'source': 'yahoo_finance', 'count': 3570}, {'source': 'sina_finance', 'count': 2357}, {'source': 'cointelegraph', 'count': 121}, {'source': 'coindesk', 'count': 113}, {'source': 'cnbc', 'count': 34}, {'source': 'cninfo', 'count': 15}, {'source': 'sec_edgar', 'count': 5}]。

### 8 Worker 健康总览

| ID | 名称 | 调度周期 | 近 24h 运行 | 24h 成功 | 24h 失败 | 24h 记录 | 最近状态 | 健康评估 |
|---|---|---|---|---:|---:|---:|---|---|
| news_reddit_5m | Reddit 散户讨论 | 每 5 分钟 | 89 | 0 | 0 | 0 | skipped | ⏸️ 被跳过/未配置 |
| news_coindesk_5m | CoinDesk RSS | 每 5 分钟 | 89 | 89 | 0 | 11 | success | ✅ 正常 |
| news_cointelegraph_5m | Cointelegraph RSS | 每 5 分钟 | 86 | 86 | 0 | 17 | success | ✅ 正常 |
| news_xueqiu_5m | 雪球 散户讨论 | 每 5 分钟 | 78 | 78 | 0 | 0 | success | ✅ 正常 |
| news_article_categorization_1m | 新闻事件分类 | 每 1 分钟 | 0 | 0 | 0 | 0 | 无日志 | ❓ 无 ETL 日志（可能未启用或日志未写入） |
| sentiment_retail_agg_30m | 散户讨论聚合 | 每 30 分钟 | 0 | 0 | 0 | 0 | 无日志 | ❓ 无 ETL 日志（可能未启用或日志未写入） |
| sentiment_batch_30s | 情绪批量处理 | 每 30 秒 | 0 | 0 | 0 | 0 | 无日志 | ❓ 无 ETL 日志（可能未启用或日志未写入） |
| sentiment_low_latency_5m | 情绪低延迟处理 | 每 5 分钟 | 0 | 0 | 0 | 0 | 无日志 | ❓ 无 ETL 日志（可能未启用或日志未写入） |

## 二、8 Worker 详细状态

### Reddit 散户讨论（`news_reddit_5m`）

- **调度周期:** 每 5 分钟
- **数据去向:** Reddit
- **任务说明:** 抓取 Reddit 指定 subreddit 的散户讨论帖，经过去重、营销过滤后写入 news_article。
- **近 24h 运行:** 89 次，成功 0 次，失败 0 次，跳过 88 次
- **近 24h 抓取/处理记录:** 0 条
- **最近运行:** 2026-07-18 09:26:44 UTC
- **最近状态:** skipped
- **最近记录数:** 0
- **额外元数据:** `{"reason": "missing_credentials", "duration_seconds": 0.023}`

### CoinDesk RSS（`news_coindesk_5m`）

- **调度周期:** 每 5 分钟
- **数据去向:** CoinDesk
- **任务说明:** 拉取 CoinDesk RSS 获取加密货币市场新闻。
- **近 24h 运行:** 89 次，成功 89 次，失败 0 次，跳过 0 次
- **近 24h 抓取/处理记录:** 11 条
- **最近运行:** 2026-07-18 09:26:44 UTC
- **最近状态:** success
- **最近记录数:** 0
- **额外元数据:** `{"duration_seconds": 0.452}`

### Cointelegraph RSS（`news_cointelegraph_5m`）

- **调度周期:** 每 5 分钟
- **数据去向:** Cointelegraph
- **任务说明:** 拉取 Cointelegraph RSS 获取加密货币行业资讯。
- **近 24h 运行:** 86 次，成功 86 次，失败 0 次，跳过 0 次
- **近 24h 抓取/处理记录:** 17 条
- **最近运行:** 2026-07-18 09:26:44 UTC
- **最近状态:** success
- **最近记录数:** 0
- **额外元数据:** `{"duration_seconds": 0.474}`

### 雪球 散户讨论（`news_xueqiu_5m`）

- **调度周期:** 每 5 分钟
- **数据去向:** Xueqiu
- **任务说明:** 通过 Xueqiu 关注/交易排行榜抓取 A 股散户讨论帖并归一化为 news_article。
- **近 24h 运行:** 78 次，成功 78 次，失败 0 次，跳过 0 次
- **近 24h 抓取/处理记录:** 0 条
- **最近运行:** 2026-07-18 09:26:44 UTC
- **最近状态:** success
- **最近记录数:** 0
- **额外元数据:** `{"duration_seconds": 0.032, "symbols_total": 0, "symbols_ok": 0, "symbols_failed": 0, "auth_ok": 0, "users_refreshed": 0}`

### 新闻事件分类（`news_article_categorization_1m`）

- **调度周期:** 每 1 分钟
- **数据去向:** news_article
- **任务说明:** 对近 30 条未分类的 news_article 调用 LLM 情绪流水线，填充 event_category 等字段。
- **近 24h 运行:** 0 次，成功 0 次，失败 0 次，跳过 0 次
- **近 24h 抓取/处理记录:** 0 条
- **最近运行:** 近 24h 无 ETL 日志

### 散户讨论聚合（`sentiment_retail_agg_30m`）

- **调度周期:** 每 30 分钟
- **数据去向:** sentiment_data
- **任务说明:** 基于最近 24h 的 sentiment_data 聚合热门标的，并刷新 Redis 热股 zset。
- **近 24h 运行:** 0 次，成功 0 次，失败 0 次，跳过 0 次
- **近 24h 抓取/处理记录:** 0 条
- **最近运行:** 近 24h 无 ETL 日志

### 情绪批量处理（`sentiment_batch_30s`）

- **调度周期:** 每 30 秒
- **数据去向:** sentiment_data
- **任务说明:** 批量处理最多 100 条未处理文章，通过 LLM 情绪流水线生成 sentiment_label/score/drivers。
- **近 24h 运行:** 0 次，成功 0 次，失败 0 次，跳过 0 次
- **近 24h 抓取/处理记录:** 0 条
- **最近运行:** 近 24h 无 ETL 日志

### 情绪低延迟处理（`sentiment_low_latency_5m`）

- **调度周期:** 每 5 分钟
- **数据去向:** sentiment_data
- **任务说明:** 对最近 5 分钟入库的文章进行低延迟 LLM 情绪分析，优先保证热点时效。
- **近 24h 运行:** 0 次，成功 0 次，失败 0 次，跳过 0 次
- **近 24h 抓取/处理记录:** 0 条
- **最近运行:** 近 24h 无 ETL 日志

## 三、近 7 天资讯内容汇总

本章节从 `news_article` 表中抽取最近 7 天（或最新 500 条，取更少）的 500 条记录，按来源归类展示。

### 3.1 来源分布

| 来源 | 24h 数量 | 7d 数量 | 类型 |
|---|---:|---:|---|
| yahoo_finance | 602 | 3570 | 美股新闻 |
| sina_finance | 121 | 2357 | A 股新闻 |
| cointelegraph | 17 | 121 | 加密货币 |
| coindesk | 11 | 113 | 加密货币 |
| cnbc | 1 | 34 | 美股新闻 |
| cninfo | 9 | 15 | A 股公告 |
| sec_edgar | 1 | 5 | SEC 公告 |

### 3.2 代表性内容

#### yahoo_finance（409 条 / 样本）

- **2026-07-18 04:37:37 ** — [JPMorgan Chase: In Hyper-CapEx Supercycle](https://finnhub.io/api/news?id=98b884381cbdc68c2330a85e74da019273c14176ab7416072f5b61203fec50db)
  - 摘要：JPMorgan's strategic shift reallocates capital from buybacks to financing global infrastructure, AI, and defense. See why JPM stock is upgraded to a buy.
  - 相关标的：CAPEX.US, CHASE.US, HYPER.US, JPM.US, SEE.US, SHIFT.US
- **2026-07-18 08:30:37 ** — [Netflix (NASDAQ:NFLX): A Top Affordable Growth Stock With Strong Momentum](https://finnhub.io/api/news?id=51adbbd19a3b491411b624a0df7dab6368589899f8c0107d1f0f25e1a2ac922b)
  - 摘要：Netflix stock analysis reveals strong growth with 32.9% EPS growth, reasonable P/E of 26, and top profitability ratings, making it a prime candidate for the affordable growth investment strategy.
  - 相关标的：NFLX.US, PRIME.US, TOP.US
- **2026-07-18 04:36:34 ** — [Amazon: A Scaled-Up AWS Rinse And Repeat Is All It Needs](https://finnhub.io/api/news?id=921c7b79c1698d55f263f4ccfd91611cea3e916e8b66d99c427260c39226f510)
  - 摘要：Amazon outlook: Q2 2026 revenue +16.8%, AWS & generative AI CapEx nearing $200B, bullish 40â45% AWS growth thesis. Click here to read more in detail.
  - 相关标的：AMZN.US, AWS.US, CAPEX.US, CLICK.US, HERE.US, NEEDS.US, READ.US, RINSE.US
- **2026-07-18 06:08:52 ** — [American Express (AXP) Joins X402 And Raises Platinum Card Fee To $895](https://finnhub.io/api/news?id=941eba9c5522ae71683d4b4d0e1077c545b61394ea608544a92b0981fa3a3861)
  - 摘要：American Express (NYSE:AXP) has joined Visa, Mastercard, and Stripe in backing the x402 Foundation, an AI driven, open source payment protocol initiative. The company has also raised the annual fee on
  - 相关标的：AXP.US, CARD.US, FEE.US, FIRST.US, JOINS.US, LINKS.US, MOVES.US, NYSE.US, OPEN.US, SINCE.US, THESE.US, VISA.US
- **2026-07-18 07:20:00 ** — [I Know That a Bear Market Is Coming Eventually. This Is Warren Buffett's Single Best Piece of Advice for Investors.](https://finnhub.io/api/news?id=bd7647c4077bbd58c6eaceca297e4cccfd5bddac451d0cf76ddbcc708c99783b)
  - 摘要：Not surprisingly, Warren Buffett looks on the bright side of market crashes.
  - 相关标的：KNOW.US, LOOKS.US, PIECE.US, SIDE.US

#### sina_finance（71 条 / 样本）

- **2026-07-18 08:21:02 ** — [养老FOF清盘小高峰，全年近40只发起式清盘，“定制局”何解？](https://finance.sina.com.cn/roll/2026-07-18/doc-iniifhty3916711.shtml)
  - 摘要：来源：财联社 财联社7月18日讯（记者 封其娟）2026年刚过半，养老FOF迎来清盘潮，年内清盘数量已超过去4年任意单年清盘峰值。 截至7月17日，据Choice统计...
- **2026-07-18 08:21:23 ** — [国投期货周小燕：纯碱漫漫寻底路](https://finance.sina.com.cn/money/future/fmnews/2026-07-18/doc-iniifhuc8385437.shtml)
  - 摘要：作者 ：国投期货 周小燕 投资咨询号：Z0016691 近期纯碱加速下跌，本周五08合约跌破1000元/吨，09主力合约逼近1000元/吨，市场情绪悲观。
- **2026-07-18 08:09:05 ** — [世界杯决赛或受加拿大山火影响，特朗普威胁加关税](https://finance.sina.com.cn/roll/2026-07-18/doc-iniifhty3906310.shtml)
  - 摘要：伴随着19日世界杯决赛日的临近，位于新泽西州的决赛场馆却笼罩在烟霾之下。 据央视新闻微信公众号，当地时间17日，加拿大山火导致的大量烟霾继续在美国中部及东北部扩散蔓...
- **2026-07-18 08:04:00 ** — [飞天茅台价格大涨，原箱批价突破1700元/瓶](https://finance.sina.com.cn/wm/2026-07-18/doc-iniifhty3903943.shtml)
  - 摘要：7月18日，第三方平台“今日酒价”数据显示，26、25年飞天茅台全线上涨，2026年飞天茅台原箱报1700元/瓶，较前一日涨50元，2025年飞天茅台原箱报1760元/瓶，较前一日涨55元。
  - 事件分类：`product`
  - 情绪标签：`positive` / 分数：`70`
- **2026-07-18 07:38:13 ** — [加拿大野火烟雾蔓延至美国，特朗普痛批并称要加税](https://finance.sina.com.cn/stock/usstock/c/2026-07-18/doc-iniifhua1569091.shtml)
  - 摘要：美国总统特朗普周五猛烈抨击加拿大，称其野火产生的烟雾笼罩了美国大片地区，并表示他将把污染造成的损失计入现有关税。

#### cointelegraph（17 条 / 样本）

- **2026-07-17 21:40:18 ** — [FTX to distribute $900M to creditors in fifth payment round](https://cointelegraph.com/news/ftx-distribute-millions-creditors-fifth-payment-round?utm_source=rss_feed&utm_medium=rss&utm_campaign=rss_partner_inbound)
  - 摘要：The FTX Recovery Trust and company have distributed about $10 billion since the exchange filed for bankruptcy in November 2022, leaving users cut off from their funds.
  - 相关标的：ABOUT.US, FIFTH.US, FILED.US, FTX.US, FUNDS.US, OFF.US, ROUND.US, SINCE.US, THEIR.US, TRUST.US, USERS.US
- **2026-07-17 20:03:32 ** — [Galaxy lands 15-year Texas Tech stadium naming rights deal](https://cointelegraph.com/news/galaxy-lands-15-year-texas-tech-stadium-naming-rights-deal?utm_source=rss_feed&utm_medium=rss&utm_campaign=rss_partner_inbound)
  - 摘要：Galaxy Digital will rename Texas Tech’s football stadium under a 15-year agreement, expanding its West Texas presence as the state attracts growing crypto investment.
  - 相关标的：DEAL.US, LANDS.US, STATE.US, TECH.US, TEXAS.US, UNDER.US, WEST.US
- **2026-07-17 19:33:58 ** — [Consensys unknowingly outsourced developer work to North Korean](https://cointelegraph.com/news/consensys-north-korean-hacker-software-developer?utm_source=rss_feed&utm_medium=rss&utm_campaign=rss_partner_inbound)
  - 摘要：Through an introduction with a “reputable third-party service provider,“ the company took on a developer who, as part of an investigation, was revealed to be tied to North Korea.
  - 相关标的：KOREA.US, NORTH.US, PART.US, PARTY.US, THIRD.US, TIED.US, TOOK.US
- **2026-07-17 19:23:53 ** — [Crypto Biz: When dollars disappear, stablecoins step in](https://cointelegraph.com/news/crypto-biz-when-dollars-disappear-stablecoins-step-in?utm_source=rss_feed&utm_medium=rss&utm_campaign=rss_partner_inbound)
  - 摘要：Bolivia moves to recognize USDT amid a dollar shortage, while Bitcoin miners’ AI ambitions face fresh investor scrutiny.
  - 相关标的：AMID.US, BIZ.US, FACE.US, FRESH.US, MOVES.US, STEP.US, USDT.US, WHILE.US
- **2026-07-17 14:37:39 ** — [Bitcoin price sags under $62.5K as Iran strikes add to US stocks pressure](https://cointelegraph.com/markets/bitcoin-price-sags-under-625k-as-iran-strikes-add-to-us-stocks-pressure?utm_source=rss_feed&utm_medium=rss&utm_campaign=rss_partner_inbound)
  - 摘要：Bitcoin saw a key rejection at local highs before reversing lower, moving with stocks for a second day as US-Iran war downside took its toll.
  - 相关标的：ADD.US, HIGHS.US, IRAN.US, KEY.US, LOCAL.US, LOWER.US, SAGS.US, SAW.US, TOLL.US, TOOK.US, UNDER.US, WAR.US

#### coindesk（2 条 / 样本）

- **2026-07-17 18:00:11 ** — [Polymarket traders cut Clarity Act passage odds to record low as Senate delay drags on](https://www.coindesk.com/markets/2026/07/17/polymarket-traders-cut-clarity-act-passage-odds-to-record-low-as-senate-delay-drags-on)
  - 摘要：Polymarket bettors have cut the odds of the CLARITY Act passing this year to a record low as Senate negotiations over ethics provisions remain unresolved.
  - 相关标的：ACT.US, DELAY.US, DRAGS.US, LOW.US, ODDS.US
- **2026-07-17 17:23:01 ** — [Stripe and Swift race to control the next generation of global payments infrastructure](https://www.coindesk.com/business/2026/07/17/stripe-and-swift-race-to-control-the-next-generation-of-global-payments-infrastructure)
  - 摘要：Crypto and blockchain experts say this week's moves show the two established finance companies are increasingly competing for control of the infrastructure behind digital payments.
  - 相关标的：MOVES.US, NEXT.US, RACE.US, SHOW.US, SWIFT.US

#### sec_edgar（1 条 / 样本）

- **2026-07-17 00:00:00 ** — [10-Q — NFLX (10-Q)](https://www.sec.gov/Archives/edgar/data/1065280/000106528026000212/nflx-20260630.htm)
  - 摘要：10-Q \| Filed: 2026-07-17 \| Period: 2026-06-30
  - 相关标的：FILED.US, NFLX.US

### 3.3 情绪数据 (sentiment_data) 概览

- **7d 总量:** 174 条
- **来源:** 全部为 `llm_pipeline`（LLM 情绪流水线产出）
- **情绪分布（样本）:** {'positive': 46, 'neutral': 13, 'negative': 115}

| 时间 | 标的 | 标题 | 情绪 | 分数 | 置信度 |
|---|---|---|---|---:|---:|
| 2026-07-18 08:12:50  | 600519.SH | 飞天茅台价格大涨，原箱批价突破1700元/瓶 | positive | 0.7 | 0.85 |
| 2026-07-17 17:07:23  | 688146.SH | 中船特气2026年半年度报告_摘要 | neutral | — | 0.5 |
| 2026-07-17 17:07:17  | 688146.SH | 中船特气2026年半年度报告 | neutral | — | 0.3 |
| 2026-07-17 05:21:41  | 301358.SZ | 旺季来临！湖南裕能发布磷酸铁锂涨价函 多家企业已启动调价沟通 | positive | 0.7 | 0.8 |
| 2026-07-17 03:24:24  | 600236.SH | 华银电力等多股封板，华宝基金电力ETF（159146）逆市涨超2.5%！厄尔尼诺持续演绎，重视板块量价双升机会 | positive | 0.9 | 0.85 |
| 2026-07-17 03:24:24  | 159146.SZ | 华银电力等多股封板，华宝基金电力ETF（159146）逆市涨超2.5%！厄尔尼诺持续演绎，重视板块量价双升机会 | positive | 0.85 | 0.85 |
| 2026-07-17 03:24:24  | 600744.SH | 华银电力等多股封板，华宝基金电力ETF（159146）逆市涨超2.5%！厄尔尼诺持续演绎，重视板块量价双升机会 | positive | 0.9 | 0.85 |
| 2026-07-17 03:24:24  | 001258.SZ | 华银电力等多股封板，华宝基金电力ETF（159146）逆市涨超2.5%！厄尔尼诺持续演绎，重视板块量价双升机会 | positive | 0.9 | 0.85 |
| 2026-07-17 03:24:24  | 000899.SZ | 华银电力等多股封板，华宝基金电力ETF（159146）逆市涨超2.5%！厄尔尼诺持续演绎，重视板块量价双升机会 | positive | 0.9 | 0.85 |
| 2026-07-17 03:24:24  | 600644.SH | 华银电力等多股封板，华宝基金电力ETF（159146）逆市涨超2.5%！厄尔尼诺持续演绎，重视板块量价双升机会 | positive | 0.9 | 0.85 |

## 四、数据表结构与字段说明

### 4.1 `news_article`（统一资讯表）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | int | 自增主键 |
| source | varchar(50) | 来源，如 `yahoo_finance`、`sina_finance`、`coindesk`、`cointelegraph`、`cninfo`、`sec_edgar` |
| source_id | varchar(200) | 来源原生 ID |
| url | varchar(1000) | 原文链接 |
| url_hash | varchar(32) | MD5(url) 去重 |
| title | varchar(1000) | 标题 |
| summary | text | 摘要/RSS 摘要 |
| body | text | 正文 |
| full_content | text | Jina Reader 抓取的完整正文 |
| author | varchar(200) | 作者 |
| author_followers | int | 粉丝数（散户来源） |
| language | varchar(10) | 语言 |
| market | varchar(20) | US / HK / CN / CRYPTO / GLOBAL |
| published_at | datetime | 原文发布时间 |
| fetched_at | datetime | 入库时间 |
| category | varchar(100) | 可选类别标签 |
| event_category | varchar(50) | 事件分类：earnings、m&a、product、macro、regulation、guidance、analyst、legal、rumor、geopolitics、central_bank、election、trade_war、sanction、other |
| sentiment_score | int | -100..100 情绪分 |
| sentiment_label | varchar(20) | bullish / bearish / neutral |
| sentiment_confidence | float | 0..1 |
| sentiment_drivers | jsonb | 情绪驱动关键词 |
| importance | smallint | 1..5 重要性 |
| engagement | jsonb | 来源相关指标（upvotes、comments、score 等） |
| ai_cleanup_status | varchar(16) | AI 清洗状态 |

### 4.2 `news_article_symbol`（多对多标的关系）

| 字段 | 说明 |
|---|---|
| article_id | 外键到 news_article |
| symbol | 内部代码，如 `AAPL.US` |
| match_type | title / body / cashtag / subreddit |
| confidence | 提取置信度 |
| name / name_zh | 标的显示名称 |

### 4.3 `sentiment_data`（LLM 情绪产出）

| 字段 | 说明 |
|---|---|
| id | 自增主键 |
| instrument_code | 标的代码（可为 NULL 表示市场级） |
| source | 来源，当前全部为 `llm_pipeline` |
| title | 文章标题 |
| content | 正文 |
| url | 链接 |
| sentiment_score | -1.0..1.0 |
| sentiment_label | positive / negative / neutral |
| confidence | 0..1 |
| published_at | 原文发布时间 |
| ingested_at | 入库时间 |

### 4.4 `etl_log`（任务执行日志）

| 字段 | 说明 |
|---|---|
| job_name | 任务 ID，如 `news_reddit_5m` |
| status | running / success / failed / skipped |
| start_time / end_time | 起止时间 |
| records_count | 处理记录数 |
| error_msg | 错误信息 |
| extra_data | JSON 元数据 |

## 五、前端结合建议

### 5.1 资讯流（News Feed）

- 直接消费 `news_article` 表，按 `published_at` 倒序展示。
- 按 `source` 和 `market` 过滤：A 股（sina/cninfo/xueqiu）、美股（yahoo/cnbc/sec）、加密货币（coindesk/cointelegraph）。
- 已爬取的 `full_content` 可支持内展开，减少跳转到外部。

### 5.2 AI 聊天 RAG

- 将 `news_article` 的 `title` + `summary` / `body` + `full_content` 切片向量化，作为 RAG 上下文。
- `sentiment_data` 和 `event_category` 可作为检索过滤器，回答“最近市场对 NVDA 的情绪如何？”这类问题。
- 建议按 `instrument_code` 和 `event_category` 建立索引，加速多轮对话召回。

### 5.3 情绪仪表盘

- 利用 `sentiment_data` 的 `sentiment_score` / `sentiment_label` 生成时序图和情绪热力图。
- 结合 `news_article_symbol` 做标的维度聚合，展示 Top10 看涨/看跌标的。
- 当前 7 天仅有 174 条 LLM 情绪产出，样本量偏小，建议确认 sentiment jobs 是否真正运行或处理队列是否阻塞。

### 5.4 事件驱动信号

- `event_category` 当前覆盖率低（500 条样本中仅 1 条 `product`），需优先修复新闻事件分类 job 的落地（如补充 ETLLog 确认运行、检查 LLM 调用是否成功）。
- 事件分类稳定后，可在策略模块订阅 `earnings`、`m&a`、`central_bank`、`trade_war` 等事件，生成事件驱动信号。

### 5.5 散户讨论（Reddit / 雪球）

- Reddit 当前因 `missing_credentials` 被跳过，需配置 `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` 才能产出内容。
- 雪球运行成功但 24h 记录为 0，可能 cookies 失效或抓取目标无更新，建议检查 `XUEQIU_COOKIE` 和 `news_xueqiu_5m` 的 symbol 配置。
- 散户讨论聚合 job 当前无 ETLLog，建议添加日志以便观察其是否真正刷新 Redis 热股 zset。

### 5.6 可观测性改进

- 4 个情绪/分类 job（batch、low_latency、retail_agg、news_article_categorization）未写入 `etl_log`，导致无法从 ETL 日志判断运行状态。建议统一使用 `_record_etl` 装饰器包装。
- 在健康检查 `/health` 或后台页面中暴露 `etl_log` 的最近运行状态，便于运营监控。

---

*报告结束。数据由 ECS 生产数据库只读生成，未做任何写入或删除操作。*
