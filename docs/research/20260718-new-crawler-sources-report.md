# 新增财经资讯源研究报告

> **研究时间**：2026-07-18  
> **目标**：在当前 ECS 平台 8 个资讯/情绪 worker 之外，寻找更多“当前可用、反爬较弱、可持续抓取”的财经/投资研究资讯源，并新增 worker 将数据沉淀到现有 `news_article` / `news_article_symbol` / `sentiment_data` 等表，用于后续大数据与 AI 投研分析。  
> **约束**：未 push 到 GitHub；未中断 A 股指标重算进程；所有爬虫遵守 robots.txt 检查、限流、重试、日志。

---

## 1. 研究过程（三轮迭代）

### 第 1 轮：盘点现有源与失效情况

先梳理现有 `app/services/news/sources/` 与 `app/core/scheduler.py` 中已注册的 worker：

| 已有源 | 抓取方式 | 当前状态 |
|--------|----------|----------|
| 巨潮资讯（cninfo） | JSON API | 正常，已注册 |
| 新浪财经（sina） | JSON roll | 正常，已注册 |
| 微信公众号（wewe-rss） | JSON | 需自建 wewe-rss，未配置则跳过 |
| 雪球 | JSON + Cookie | 需 `XUEQIU_COOKIE`，否则跳过 |
| Reddit | OAuth2 API | 需 `REDDIT_CLIENT_ID/SECRET`，否则跳过 |
| Yahoo Finance RSS | RSS + Finnhub fallback | 非浏览器 UA 常被 429，fallback 至 Finnhub |
| CNBC RSS | RSS | 正常 |
| SEC EDGAR | JSON | 正常，需真实 User-Agent |
| CoinDesk / Cointelegraph | RSS | 正常 |
| 新华社（xinhua） | RSS | 已失效 404，未注册调度 |

**结论**：现有源偏海外/加密货币，中文财经/宏观/政策源覆盖不足，且多个依赖登录或自建服务。本轮明确需要补充“无需登录、反爬弱”的中文源。

### 第 2 轮：候选源扩展

通过 Exa 搜索、GitHub RSS 合集（`awesome-rss-feeds`、`top-rss-list`、`RssFeedLib`）、RSSHub 文档，以及公开 API 文档，枚举出以下候选：

- **实时快讯**：华尔街见闻 7x24 API、36kr 快讯 RSS、虎嗅 RSS、界面新闻 RSS、财联社、第一财经、证券时报。
- **深度/媒体**：财新、经济观察网、21 世纪经济报道、每日经济新闻、中国新闻网财经。
- **宏观/政策**：国家统计局 RSS（最新发布 / 数据解读）、中国人民银行、国家发改委官网。
- **海外英文**：MarketWatch、CNBC（已存在）、Reuters、Seeking Alpha、Benzinga、Investing.com。

### 第 3 轮：可用性验证（重点：无需登录、可访问、反爬弱）

从 ECS 主机（阿里云，中国内网）与本地同时探测，结果如下：

| 候选源 | 探测 URL | 结果 | 备注 |
|--------|----------|------|------|
| 华尔街见闻 7x24 | `https://api-one.wallstcn.com/apiv1/content/lives?channel=global-channel&limit=20` | 200 JSON | 公开 API，无登录 |
| 36kr 快讯 RSS | `https://36kr.com/feed-newsflash` | 200 RSS | 官方 RSS |
| 虎嗅 RSS | `https://rss.huxiu.com/` | 200 RSS | 官方 RSS（`https://www.huxiu.com/rss/0.xml` 已失效/超时） |
| 界面新闻 RSS | `https://a.jiemian.com/index.php?m=article&a=rss` | 200 RSS | 官方 RSS |
| 财新最新文章 | `https://gateway.caixin.com/api/dataplatform/scroll/index` | 200 JSON | 公开 API，无登录 |
| 中国新闻网财经 | `https://www.chinanews.com.cn/rss/finance.xml` | 200 RSS | 官方 RSS |
| 国家统计局最新发布 | `https://www.stats.gov.cn/sj/zxfb/rss.xml` | 200 RSS（约 4.5 MB） | 官方宏观数据，无登录 |
| 国家统计局数据解读 | `https://www.stats.gov.cn/sj/sjjd/rss.xml` | 200 RSS | 官方 |
| 第一财经 RSS | `https://www.yicai.com/rss/` | 404 | 无官方开放 RSS |
| 财新 RSS | `https://www.caixin.com/rss/` | 404 | 官方 RSS 已关闭；仅 API 可用 |
| 经济观察网 RSS | `http://www.eeo.com.cn/finance/rss.xml` | 200 RSS | **但内容停滞在 2011 年，已失效** |
| 证券时报 RSS | `http://app.stcn.com/rss.php?catid=1` | 超时 | 无法稳定访问 |
| 21 世纪经济报道 RSS | `https://m.21jingji.com/rss/` | 403 | 反爬 |
| 每日经济新闻 RSS | `https://www.nbd.com.cn/rss/` | 404 | 无 RSS |
| MarketWatch RSS | `https://www.marketwatch.com/rss/` | 403 | 反爬 |
| Investing.com RSS | `https://cn.investing.com/rss/` | 403 | 反爬 |
| Reuters RSS | 多个路径 | 404 | 官方 RSS 路径变更/关闭 |
| Seeking Alpha | `https://seekingalpha.com/feed.xml` | 200 RSS | 可用，但本次优先中文源 |
| Benzinga | `https://www.benzinga.com/feed` | 200 RSS | 可用，但本次优先中文源 |

**最终入选 7 个源**：华尔街见闻、36kr、虎嗅、界面新闻、财新、中国新闻网财经、国家统计局最新发布。全部满足：无需登录、可访问、反爬弱、内容聚焦财经/宏观/投资研究。

---

## 2. 新增 Worker 清单

| 源名称 | 模块文件 | 抓取方式 | 调度周期 | 单批次条数 | 首次写入条数 | 反爬/限流措施 |
|--------|----------|----------|----------|------------|--------------|---------------|
| 华尔街见闻 | `app/services/news/sources/wallstreetcn.py` | JSON API | 5 分钟 | 50 | 46 | 60 req/min，UA 轮换，随机抖动，指数退避重试，robots.txt 检查 |
| 36kr 快讯 | `app/services/news/sources/kr36.py` | RSS | 10 分钟 | 50 | 20 | 20 req/min，UA 轮换，随机抖动，指数退避重试，robots.txt 检查 |
| 虎嗅 | `app/services/news/sources/huxiu.py` | RSS | 10 分钟 | 50 | 50 | 同上 |
| 界面新闻 | `app/services/news/sources/jiemian.py` | RSS | 10 分钟 | 50 | 30 | 同上 |
| 财新 | `app/services/news/sources/caixin.py` | JSON API | 10 分钟 | 20 | 20 | 30 req/min，UA 轮换，随机抖动，指数退避重试，robots.txt 检查 |
| 中国新闻网财经 | `app/services/news/sources/chinanews_finance.py` | RSS | 15 分钟 | 50 | 30 | 20 req/min，同上 |
| 国家统计局 | `app/services/news/sources/stats_gov.py` | RSS | 30 分钟 | 50 | 50 | 10 req/min，同上 |

**通用实现细节**：
- 复用 `BaseCrawler`（`app/services/news/crawler/base.py`）提供的 UA 池、令牌桶限流、重试与抖动。
- 新增 `app/services/news/crawler/robots.py`，每个 worker 启动时检查目标 URL 的 `robots.txt` 并记录结果。
- 新增 `app/services/news/sources/rss_common.py` 通用 RSS/Atom 解析器，支持 `pubDate` / `pubTime` / `dc:date` / ISO 8601 / 36kr 特殊格式等。
- 新增 `app/services/news/scheduler_jobs.py` 调度包装函数，均用 `@_record_etl(...)` 写入 `etl_log`。
- 在 `app/core/scheduler.py` 中注册对应 APScheduler 任务。

---

## 3. 数据沉淀验证（ECS backend 容器内手动跑通）

在 ECS `alloyresearch-backend` 容器内运行 7 个新 worker 的调度函数，结果全部成功写入 DB，并生成 `etl_log` 成功记录：

```
run_wallstreetcn_crawl:      {'fetched': 46, 'written': 46}
run_kr36_crawl:              {'fetched': 20, 'written': 20}
run_huxiu_crawl:             {'fetched': 50, 'written': 50}
run_jiemian_crawl:           {'fetched': 30, 'written': 30}
run_caixin_crawl:            {'fetched': 20, 'written': 20}
run_chinanews_finance_crawl: {'fetched': 30, 'written': 30}
run_stats_gov_crawl:         {'fetched': 50, 'written': 50}
```

**ETL 日志验证**：

| job_name | status | records_count | end_time (UTC) |
|----------|--------|---------------|----------------|
| news_wallstreetcn_5m | success | 46 | 2026-07-18 10:12:03 |
| news_36kr_10m | success | 20 | 2026-07-18 10:12:08 |
| news_huxiu_10m | success | 50 | 2026-07-18 10:12:15 |
| news_jiemian_10m | success | 30 | 2026-07-18 10:12:18 |
| news_caixin_10m | success | 20 | 2026-07-18 10:12:22 |
| news_chinanews_finance_15m | success | 30 | 2026-07-18 10:12:27 |
| news_stats_gov_30m | success | 50 | 2026-07-18 10:12:33 |

**news_article 表按源统计（首次写入后）**：

| source | 条数 |
|--------|------|
| wallstreetcn | 46 |
| 36kr | 20 |
| huxiu | 50 |
| jiemian | 30 |
| caixin | 20 |
| chinanews_finance | 30 |
| stats_gov | 50 |
| **合计** | **246** |

---

## 4. 已抓取数据样例（脱敏：标题/来源/时间/URL）

| 来源 | 标题 | 发布时间（UTC） | URL |
|------|------|-----------------|-----|
| wallstreetcn | 伊朗称打击位于科威特、巴林、约旦的美军目标 | 2026-07-18 09:47:13 | https://wallstreetcn.com/livenews/3135999 |
| 36kr | 腾讯升级发布具身智能全栈方案，ADP 4.0 海外版正式上线 | 2026-07-18 09:30:23 | https://36kr.com/newsflashes/3900908700436103 |
| huxiu | 世界人工智能合作组织在上海成立，全球求解 AI 治理的“人机边界” | 2026-07-18 09:51:35 | https://www.huxiu.com/article/4876358.html |
| jiemian | 科威特石油公司称一设施遭伊朗袭击致多人伤亡 | 2026-07-18 10:11:38 | https://www.jiemian.com/article/14788976.html |
| caixin | 国际组织呼吁 AI 成果普惠 各方积极参与多边治理机制 | 2026-07-18 10:11:19 | https://china.caixin.com/2026-07-18/102465722.html |
| chinanews_finance | 业内人士：中欧汽车产业应加强合作 科技创新最终是改善生活 | 2026-07-18 09:52:15 | https://www.chinanews.com.cn/cj/2026/07-18/10662082.shtml |
| stats_gov | 2026 年二季度和上半年国内生产总值初步核算结果 | 2026-07-16 01:30:00 | https://www.stats.gov.cn/sj/zxfb/202607/t20260716_1964142.html |

---

## 5. 后续可扩展方向

1. **更多官方 RSS/宏观源**：国家统计局数据解读、财新 Morning Call 播客、中国政府网政策文件、央行/发改委公告页。
2. **英文源**：当平台需要全球资产覆盖时，可接入 Benzinga、Seeking Alpha、Financial Times 公开 RSS（需评估反爬）。
3. **向量化与语义检索**：将 `news_article.body` 或 `full_content` 写入向量库，供 RAG 搜索与事件关联。
4. **情绪与事件抽取**：复用现有 `sentiment_pipeline.py`，对新源自动打 sentiment_score / event_category / importance。
5. **去重增强**：目前基于 `(source, source_id)` 去重；对跨源同事件可考虑 title+published_at 的 simhash 去重。
6. **RSSHub 自建实例**：对于第一财经、证券时报、21 世纪经济报道等无官方 RSS 的源，可部署私有 RSSHub 节点作为中转，降低对公共 rsshub.app 的依赖。
7. **按频道细分**：华尔街见闻 API 支持 `global-channel` / `a-stock-channel` / `us-stock-channel` 等；可按需拆分为多个 worker 或按 channel 打标签。

---

## 6. 风险与合规提示

- **robots.txt**：新增 worker 已调用 `is_robots_allowed()` 检查并记录结果；若目标站后续修改 robots.txt 禁止抓取，worker 会自动返回空列表。
- **限流**：所有源自设限速 ≤ 1 req/s（最严 10 req/min），并复用 BaseCrawler 的指数退避重试，避免触发目标站反爬。
- **User-Agent**：使用 BaseCrawler 的 15 个桌面浏览器 UA 池，避免被识别为爬虫。
- **数据版权**：抓取内容仅供内部投研分析，不对外发布；全文内容通过 `full_content` 懒加载，降低对源站的直接流量占用。
- **登录依赖**：本次 7 个源均无需登录/Cookie；若未来接入需要登录的源，必须单独配置并在文档中标注。
- **稳定性**：stats.gov.cn RSS 体积较大（4.5 MB），已限制只保留最近 50 条；后续可加入“仅保留最近 N 天”的过滤。
- **A 股指标重算**：本次验证全程通过 `docker exec` 在 backend 容器内运行独立进程，未重启、未中断 PID 4143479 的指标重算任务。

---

## 7. 结论

本次研究通过三轮迭代，从数十个候选源中筛选出 **7 个当前可用、无需登录、反爬较弱**的中文财经/宏观资讯源，并新增了对应的 crawler worker、scheduler job 与 ETL 日志。所有新源已在 ECS backend 容器内手动跑通小批量，成功写入 `news_article` 表，首次共沉淀 **246 条**记录，为后续大数据与 AI 投研分析提供了更丰富的中文资讯输入。
