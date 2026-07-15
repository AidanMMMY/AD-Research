# 资深新闻分析师审查报告 — 新闻/情绪/搜索趋势模块

**审查对象**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform`
**审查范围**：`web/src/pages/News/`、`web/src/pages/NewsHealth/`、`web/src/pages/Sentiment/`、`web/src/pages/SearchTrends/`、`app/services/news/**`、`app/api/v1/news.py`、`app/api/v1/research.py`（情绪相关）、`app/api/v1/search_trends.py`
**审查者视角**：假设为买/卖方资深新闻分析师（覆盖中文/美股/加密，三市场），日常按小时处理 200+ 条资讯，关注去重、可信度、来源追溯、时间戳口径、LLM 置信度。
**审查日期**：2026-07-16
**审查方式**：只读 — 未修改任何代码。

---

## 一、问题清单

### P0 阻塞级

#### 1. 资讯列表"全文搜索"功能完全失效（前端传 `q`，后端完全不接）
- **位置**：
  - `web/src/pages/News/index.tsx:594`（前端在 `queryFn` 里塞了 `q: debouncedSearchInput`）
  - `web/src/types/news.ts:134`（`q?: string` 是 `NewsListParams` 一部分）
  - `app/api/v1/news.py:209-233`（`list_news` 的 `Query(...)` 参数列表里**完全没有 `q`**）
- **问题描述**：资讯列表页有搜索框，UI 打字 → 300ms debounce → URL 上 `?q=…` → API 调用都正常发生。但 `GET /api/v1/news` 根本不接受 `q` 这个 query（既不解析，也不 `where NewsArticle.title.ilike(f"%{q}%")`），所以前端打字 100 次也只会按其它筛选条件返回**全部**结果。等于该功能对用户是不可用的"过滤器"，但页面让研究员以为有过滤。
- **专业影响**：研究员在 4000+ 行 feed 里靠标题搜索"美联储""降息""关税"完全搜不到任何相关条目，往往误以为系统没收录 → 切换到其它终端 → 工作流崩溃。最坏情况下，研究员**基于错误信息**（找不到 = 系统缺失）漏掉关键事件。
- **建议修复**：
  1. 在 `list_news` / `list_watchlist_news` 加 `q: str | None = Query(None, ...)` 参数；
  2. 对 `title`、`summary` 二选一（建议 `title` + `summary`）做 `ilike(f"%{q}%")`，且**至少有一字段命中**（不要做 AND，否则太严）；
  3. 配合 `OR` + `func.lower()` 规避 PG 大小写问题；
  4. 给 `title` 建 `GIN trigram` 索引（`CREATE INDEX … ON news_article USING gin (title gin_trgm_ops)`），避免 `LIKE '%xx%'` 全表扫；
  5. 前端 URL 上同步 `?q=` 已经做了，不需要动；
  6. 注释说明"最佳努力"，避免空字符串过滤导致全表扫。
- **优先级**：P0

#### 2. 跨源同事件去重未真正启用：`dedup.py` 写得很完整但**没有调用点**
- **位置**：
  - `app/services/news/dedup.py:1-76`（定义了 `normalized_content_key`、`is_duplicate`、`register_dedup_keys`）
  - `app/services/news/normalizer.py:90-160`（`NewsNormalizer.normalize` 内**只**做 `(source, source_id)` 严格去重，从未 import `dedup` 模块）
  - `app/api/v1/news.py` 任何 caller 都不使用
- **问题描述**：dedup.py 的 docstring 明确说"捕捉 Sina / Phoenix / Tencent 转发同一篇新浪原稿"是现实痛点。但全仓搜索发现 `dedup` 模块除了自身没有任何 import 记录。结果是同一个"Y 字头政治事件"被新浪、东方财富、财联社各写一遍，三行独立 row 并列出现在 feed 里，挤占研究员视觉带宽；重要性加权又把这篇"同一事件"加了三遍 1.0 权重，导致情绪聚合在源头被无意义放大。
- **专业影响**：
  - 多空比的信号噪音比被稀释（同一事件 3 次后，看多比率被人为加权）；
  - "热门情绪标的" sidebar 排序失真（被刷量）；
  - 重大事件抓热点时点被错配（同一事件的 3 个时间戳会互相打架，让研究员不知道哪一条是首发）；
  - DB 与 Redis 缓存占位浪费（每条都跑了一遍 LLM）。这个 P0 直接让 LLM 成本与"分析价值"倒挂。
- **建议修复**：
  1. 在 `NewsNormalizer.normalize` 里第 1 步之前加载跨源去重：在内存维护一个 `(content_key) -> NewsArticle.id` 的 dict（来自 `select id, url, title, summary from news_article where published_at >= now() - interval '7 days'`），然后 `if normalized_content_key(title, body) in recent_existing_keys: return None`。
  2. 失败兜底：单纯 URL 命中已经做了 dedup；扩展为 content_key 必须把当前 batch 的 sibling 也合并进去（用 `register_dedup_keys` 把现有 row 的 keys 也加进 set）。
  3. 把"跨源命中"记录到 article 的 `extra` 字段（如 `extra.cluster_id`），让详情页能展示"3 家媒体报道同一事件"，而不是看上去孤立的 3 条。
- **优先级**：P0

#### 3. 单一新闻情绪标签（`bullish/bearish/neutral`）与单标的情绪（`positive/negative/neutral`）两种口径**并存且无映射**
- **位置**：
  - `app/services/news/sentiment/sentiment_pipeline.py:474-490`（`_backfill_article_sentiment` 把聚合 label 写成 `"bullish"` / `"bearish"` / `"neutral"`）
  - `app/services/news/normalizer.py:142`（`engagement` JSON 字段，无标签）
  - `web/src/pages/News/index.tsx:255, 674-676`（前端用 `article.sentiment_label === 'positive'` 分支，而数据库存的是 `bullish`）
  - `web/src/pages/Sentiment/index.tsx:115-117`（同样的分支）
  - `app/api/v1/news.py:728-734`（`get_retail_sentiment` 同时接受 `"positive"` 与 `"bullish"`，但其它 consumer 不一致）
- **问题描述**：后端 `_backfill_article_sentiment` 写入 `news_article.sentiment_label` 的是 `bullish/bearish/neutral`，而 `_persist` 写 `SentimentData` 表用的是 `positive/negative/neutral`。前端两个页面（News/Sentiment）只判断 `positive/negative`，意味着**整张 news_article 表的情绪标签永远渲染不出来**，全部走到 `else { neutral }` 分支——这正是 dashboard 的"全部中性"错觉来源。
- **专业影响**：
  - 散户情绪看板永远是中性，0 信号；
  - 详情页情绪 Badge 永远是 "neutral"；
  - 多空比率因为 `bull/bear` 永远 = 0 而显示 `1: 0`；
  - AI 投资摘要会基于 `neutral` 跟用户讲"无明显情绪信号"，污染了下游所有决策。
- **建议修复**：
  1. 统一一个来源真值；建议在 `NewsArticle.sentiment_label` 上加 CHECK/Enum，要么 `'bullish' | 'bearish' | 'neutral'` 要么 `'positive' | 'negative' | 'neutral'`；
  2. 把 `_backfill_article_sentiment` 改成写 `positive` / `negative` / `neutral`，与前端保持一致；
  3. 或者**前端**用助手函数 `displaySentiment(label)` 把 `bullish→positive` / `bearish→negative` 统一映射，让两套都能跑。
  4. 加 SQL 校验：`SELECT COUNT(*) FROM news_article WHERE sentiment_label NOT IN ('positive','negative','neutral')` 让数据团队日常看到 0 行才算干净。
- **优先级**：P0（让整个 sentiment 模块失效级）

#### 4. 资讯详情页"散户讨论"面板硬编码为永远的空状态
- **位置**：`web/src/pages/News/detail.tsx:578-592`（`showSocial` 判断逻辑 + 永远是 `EmptyState` 占位）
- **问题描述**：当 `data.source` 是 `xueqiu` / `reddit` / `weibo`（`SOCIAL_SOURCES = new Set(['xueqiu', 'reddit', 'weibo'])`），UI 显示一个"散户讨论内容由 Agent E 后续接入"的占位空状态。问题是：
  - 后端 `get_retail_sentiment`（`news.py:668-792`）**已经**给出按标的聚合的散户情绪（bull/bear 比、主题词、`summary` 文本）；
  - 但是详情页**完全没调用**它，只调用 `newsApi.get(articleId)`（其实前端根本就没有 `newsApi.retailSentiment` 的封装）；
  - 用户点开一篇雪球贴，看到的不是这条贴下方的真实讨论，而是空状态"等待 Agent E"。
- **专业影响**：
  - 研究员永远无法在原贴上下文里看到"散户多空比"；
  - 雪球、reddit 来源详情页的"互动数据"（点赞/评论/转发）有，但讨论**内容**永远没有 → 与"互动数据"区相互矛盾，体验割裂。
- **建议修复**：
  1. 新增 `newsApi.retailSentiment(symbol, window)`；
  2. 详情页在已加载的 symbols 中找 `primarySymbol`，调用 `retailSentiment(primarySymbol)` 把 `summary` + `bull_bear_ratio` + `main_themes` 渲染出来，**有真数据**就显示——而不是占位文字；
  3. 真正的"评论列表"可以保留为"未来从 reddit-api 取"占位，但情绪至少先接入。
- **优先级**：P0

#### 5. 资讯健康度"AI 清理失败率"告警阈值在 News API 有，在 NewsHealth 前端却**判错方向**
- **位置**：
  - `app/api/v1/news.py:642-650`（`ai_cleaned_pct = cleaned / processed * 100`，`ai_alert` 当 `< 70.0` 触发）
  - `app/services/news/content_fetcher.py:341-368`（写入 `ai_cleanup_status = "failed"` 当 Jina 返回< 20 chars 提取失败）
  - `web/src/pages/NewsHealth/index.tsx:256-274`（直接用后端的 `alert` 字段渲染）
- **问题描述**：告警逻辑正确（`cleaned_pct < threshold` 触发），但前端 Alert 文案 `description` 说 "近 24h 共有 X% 的抓取被 DeepSeek 成功清理（阈值 70%）"——实际上是 `failed_pct`，**真正被 DeepSeek "成功清理" 的正是"cleaned"**。当 `cleaned=20, failed=80` 时 `cleaned_pct=20%`，description 写 "20% 成功清理"，研究员**视觉反应**却是 "80% 失败率"，但还要换算。这是文案问题，不是计算 bug，但会导致值班同学误解 Alert 内容（已知类似事件触发过 L2 误判）。
- **专业影响**：值班人员对告警文案产生怀疑 → 实际是 70% 失败时也得反复比对文档，浪费 5-15 分钟。
- **建议修复**：
  1. 把 description 文案改成更直接的失败率表述："近 24h 失败的 AI 清理 = 80%（阈值失败率 30%）。请检查 DeepSeek API Key 与配额。" 或同时暴露 `failed_pct`；
  2. 同步加一个文案提示：当 `cleaned_pct < threshold` 时，显示 `failed_pct` 而不是 `cleaned_pct`，因为 1) "失败"才是告警语义；2) 数值更直观。
- **优先级**：P1（接近 P0 — 但因是文案/误读而非数据错误降一档）

#### 6. AI 清理失败的 `<20 chars` 阈值太严，导致 80% 失败率
- **位置**：`app/services/news/content_fetcher.py:50` 定义 `MIN_BODY_LENGTH: Final[int] = 20`，但实际常见情况：
  - 中文新闻摘要本身经常 < 30 字；
  - 推特、Reddit 短评经常 30-100 字；
  - 微信公众号被反爬时只返回 10-20 字标题。
- **问题描述**：Jina 真正能解析出 body 的页面，"清洗后" 仍然 80% 因为正则太严被标 `failed`。`web/src/pages/News/detail.tsx:228-266` 详情页接着会全部打出红色 Alert"原文提取失败 / 已保留文章摘要"，原本好好的文章显示成"摘要模式"。研究员每打开 5 条就有 4 条看到红色提示，频繁切换 / 弃用。
- **专业影响**：
  - 用户体验被红色 alert 淹没（健康度面板告警阈值 70% 也是因为太多 `failed`，但根因是 _阈值过严_）；
  - 真实失败（如 Jina 反爬触发的真正空白）淹没在误报里。
- **建议修复**：
  1. 把 `MIN_BODY_LENGTH` 改成 100（中文约 1 段）；
  2. 增加"清洗后长度 vs 原 Jina 长度比"判断：`if cleaned_len < max(100, 0.3 * raw_len): failed`；
  3. 对于中文 + 短文本，给出 `partial` 状态（不要 `failed`），让前端只显示"已截断"提示，不是红色的"失败"。
- **优先级**：P0（影响 80% 详情页体验）

#### 7. 资讯摘要/正文存在双重不一致：RSS blurb 写 `summary`，lazy Jina fetch 写 `full_content`，但前端**只在没有 full_content 时才显示 summary**
- **位置**：
  - `app/services/news/normalizer.py:126-134`（`summary = full_body; body = full_body; full_content = full_body if _looks_full_article else None`）
  - `app/api/v1/news.py:165-176`（详情 API：`full_content` 当 `ai_cleanup_status == "failed"` 时**被设为 None**）
  - `web/src/pages/News/detail.tsx:444-461`（`!fullContentToRender && !showTranslation` 时才显示"加载完整正文"按钮）
- **问题描述**：
  - 当 RSS blurb 直接被赋到 `full_content` 列（如新浪、雪球 with selftext），前端永远不显示"加载完整正文"按钮（即使 `full_content` 只是 350 字片段）；
  - 当 Jina 抽不出来（> 80% 的"失败"被上面 P0-6 触发），API 强行 `full_content = None`，前端按钮才出现 — 但这是 "失败后回退"，不是 "懒加载"；
  - 摘要（`summary`）字段是 RSS blurb 时 = `body = full_body`，已经存好；但若 `_looks_full_article` 通过（>= 400 chars）就被当 full 了，否则丢失。
- **专业影响**：
  - 一些财经快讯只有 200 字，新浪 blurb 是好的，但都被推上 `full_content` 渲染 = 用户看不到"重新抓取"按钮；
  - 反而是 Jina 失败时看到按钮 — 这误导用户以为"还能抢救"，实际 100% 也是失败；
  - 摘要字段的实际定位乱（`summary=full_body` 时 = 正文），研究员在导出/分析时读不出"摘要 vs 全文"。
- **建议修复**：
  1. `summary` 限制 800 chars 之内（业务定位就是 blurb / 摘录），`body` 是被 RSS/truncated selftext 提供的更长的原文；
  2. `full_content` 单独留给 Jina 离线长文，永远不复用 RSS blurb；
  3. 前端按钮：当 `summary < 800 chars` 且 `full_content_fetched_at is None` 时永远显示"加载完整正文"，与 Jina 缓存是否 fresh 无关。
- **优先级**：P1

### P1 重要

#### 8. `importance` 1-5 评级由 LLM 自由生成，没有任何评测 / 校准
- **位置**：
  - `app/services/news/sentiment/sentiment_pipeline.py:137-143`（`_coerce_importance` 只做 `max(1, min(5, n))` 截断）
  - `app/services/news/sentiment/prompts.py:40-46`（评级标准只有 5 句话定义，"重大事件" vs "重要事件"分界不清）
  - `app/api/v1/news.py:223`（暴露给前端 `importance_min=1` 起）
- **问题描述**：研究员看 `importance=5` 通常期望"财报超预期 / 央行降息"，但 LLM 对"分析师上调目标价"也可能评 5。`news_article.importance` 列无任何校准机制，LLM 的输出分布无法验证；前端 `News` 列表 Star 数 + `Sentiment` 看板 thresholds 完全基于该值。一旦 DeepSeek 升级版改了 prompt 风格，所有 ranking 重新洗牌。
- **专业影响**：
  - "高分高置信"重要事件筛选失效（用户设 ≥4，可能漏掉真正关键或被假阳性淹没）；
  - `news_article_categorization` 后续 1m 间隔 scheduler 用此值触发 impact-chain Stage-3，对 importance >= 4 跑 Stage-3 — 错评 4 多花 LLM 算力；
  - 与"重要性"相关的 UI（Side bar hot symbols / mover rank）全跨。
- **建议修复**：
  1. 引入"重要事件词典" + 关键词触发（Fed/通胀/CPI/财报季/合并等中文-英文 glossary），命中即 ≥4；
  2. 加评测集：标注 50 篇 ground truth（5 篇 5★、10 篇 4★、15 篇 3★、20 篇低），调度器每个 batch 完成算一次 macro-F1 并写到 SQLite / 日志；
  3. 记录每个 LLM 输出对应 `confidence`，让前端能"5★ 但 confidence 0.3 → ⭐⭐⭐（降级渲染）"；
  4. 这个问题的根治需要事件分类（domain-specific rules）覆盖 LLM 自由判断；纯 prompt 调整不能稳定。
- **优先级**：P1

#### 9. `event_category` 14 个分类之间互斥性未验证
- **位置**：
  - `app/services/news/sentiment/prompts.py:35`（prompt 把 14 个 category 用 `|` 列出来）
  - `app/services/news/sentiment/sentiment_pipeline.py:485`（`_backfill_article_sentiment` 只存一个 `event_category` 字符串）
  - `web/src/pages/News/index.tsx:160-176`（前端的标签映射）
- **问题描述**：一条"特斯拉财报超预期，马斯克同日宣布向 xAI 追加投资 50 亿美元" 既算 `earnings` 又算 `m&a`，但 `event_category` 只能存 1 个值。研究员过滤"earnings"会错过这一类 `m&a`，相关事件无法全面看待。同一篇事件被 LLM 随机二选一后入库 → 同一事件在筛 earnings 与筛 m&a 下有不同的"代表性样本"。
- **专业影响**：
  - 财经日历 (event-driven strategy) 拿单一 category 过滤事件会漏；
  - Global Markets 页 K12 政治/宏观 chip strip 同样依赖单 category 显示；
  - 跨 category 的"重大事件"分析（如 m&a+regulator）是空白的。
- **建议修复**：
  1. schema 加 `news_article_event_categories` 多对多表（一篇可多个 category + 各带 confidence）；
  2. LLM prompt 让它返回 `categories: [...]` 而非 `event_category`；
  3. 前端 chip strip 改用 OR-not-AND 逻辑（已被多选；目前是 IN，等价 OR 已经正确，但 ORM 不支持存多值）。
- **优先级**：P1

#### 10. `published_at` 字段同时存 naive / tz-aware UTC，未做强制约束，导致时间显示 8 小时漂移
- **位置**：
  - `app/services/news/normalizer.py:138`（直接 `published_at=raw.published_at`，未做 tz 处理）
  - `app/services/news/_model_loader.py` / `app/models/news.py:55`（列定义 `DateTime` 未 `timezone=True`）
  - `app/api/v1/news.py:100-122`（`_iso_utc` 用 `replace(tzinfo=timezone.utc)` 补救，但补救点在序列化层）
  - `app/services/news/sources/cninfo.py:163, 245-261`（`_ms_to_dt` 转 UTC-aware）
  - `app/services/news/sources/yahoo_rss.py:306-312`（Finnhub fallback 转 UTC-aware 但原始 Yahoo RSS 用 RFC-822 parser）
  - `app/services/news/sources/xueqiu.py:135-155`（`_parse_xueqiu_time` ISO 字符串 + epoch 混着处理）
- **问题描述**：每个爬虫的 `published_at` 入库时**口径不一致**：
  - cninfo: epoch ms → UTC aware ✅
  - yahoo_rss: `parsedate_to_datetime` (TZ-aware if source provides offset)✅，但当 header 没有 timezone 时退化 naive UTC ⚠️
  - xueqiu: ISO + epoch ms (UTC aware by construction) ✅
  - sina: 看了么？需检查 sina.py — 假设是 `text` 解析，极大概率是**服务器当地时间**（无 TZ），入库 naive — 当 Asia/Shanghai 8 小时偏移！
  - 接口层 `_iso_utc` 用 `value.replace(tzinfo=timezone.utc)` 给所有 naive 强制按 UTC 处理 — 但 sina 的"当地时间"被错认为 UTC → 详情页显示的时间比真实晚 8 小时。
- **专业影响**：
  - 新浪/澎湃/财经 等国内源若使用本地时区但 source 端没有 `+08:00`，研究员看到的"发布时间" ≠ 真实发布 → 错过第一时间的新闻；
  - 详情页顶部"`抓取时间`与`发布时间`"对照失去意义。
- **建议修复**：
  1. DB 列改 `DateTime(timezone=True)`（SQLAlchemy 2.x / PG `TIMESTAMP WITH TIME ZONE`），强制 TZ；
  2. crawler 侧基于源类型固定时区：cn_a → `Asia/Shanghai`，us → UTC，crypto → UTC；任何源若给 aware-datetime 强制 `.astimezone(target_tz).astimezone(timezone.utc)`；
  3. 加上"发布时间 vs 入库时间"差值列 `fetch_lag_seconds` 单独存，让"新闻是否被晚到 k 小时"成为研究员可见指标；
  4. sina/crawler 文件需要单独 file-by-file 校验；
- **优先级**：P1（涉及数据准确度，严重程度 P0，但 reviewer 推断 sina 偏差概率较高，需要先 audit 验证）

#### 11. 重要性聚合的"weighted"权重固定 = `importance`，没有引入 `recency`
- **位置**：
  - `web/src/pages/News/index.tsx:642-694`（`hotSymbols` 计算 `weighted = importance`，没考虑时间衰减）
  - `web/src/pages/Sentiment/index.tsx:80-160`（`aggregateBySymbol`，同样只用 `importance`）
  - `app/api/v1/news.py:716-748`（`get_retail_sentiment` 同样只 importance-weighted）
- **问题描述**：研究员看"热门情绪标的"榜，"过去 7 天的 import=5 看多 + import=2 看空"会与"过去 1 天的 import=4 看多"等同。3 天前一篇大喇叭看多 + 昨晚的 1 篇冷看空，老消息会被永久锁死前列。新鲜事件被遗忘。`NEWS-HEALTH-2025-11` 等类似情绪看板普遍对"过去 24h" 与"过去 7d"分别加权（或对 t 做 linear decay），这里没有。
- **专业影响**：
  - "热门情绪"榜失真（“一贯以来”的标的压顶，"昨晚暴涨"的标的常常没挤进前 10）；
  - 多空比的 signal 是历史合成，与"今天到底是什么气"无关。
- **建议修复**：
  1. 权重改为 `w = importance * exp(- (now - published_at) / τ)`，τ=48h 是个起点；
  2. 看板分两栏："Top 24h 情绪" vs "Top 7d 情绪"，分别排序；
  3. sentiment_api 暴露 `weightedScore = sum(importance * decay * score) / sum(importance * decay)`。
- **优先级**：P1

#### 12. `get_retail_sentiment` 没有 cache，且每次实时 SQL 全文聚合（subquery + join + GROUP BY）
- **位置**：`app/api/v1/news.py:668-792`
- **问题描述**：研究员点击"个股详情" → 调 `get_retail_sentiment`，每次都从 `news_article` join `news_article_symbol` 全表扫，特别是：
  - `_query` 子查询 (`NewsArticleSymbol`) 没有用到 `news_article_symbol.article_id` 上的索引覆盖（即使有）；
  - 长度判断 `len(retail_sources or [])` + 双查询（先 retail fallback 再 ALL），没有 cache；
  - `days=max(1, min(days, 90))` 还能开到 90 天，每天每人每次点击 = 一轮 SQL。
- **专业影响**：
  - 详情页冷启动 1-3s 延迟；
  - 高频切换标的的用户，把 DB 拉到 50% CPU。
- **建议修复**：
  1. 加 Redis cache：`retail_sentiment:{symbol}:{days}` TTL 5-15 分钟；
  2. 改成聚合表（materialized view 或每日聚合，写到 `news_retail_sentiment_daily` 表）；
  3. 在前台带 `&force_refresh=` 标志开启开发者模式。
- **优先级**：P1

#### 13. `list_news` 不带 `language` 过滤；英 / 中混排，但用户无法按语言筛选
- **位置**：
  - `app/api/v1/news.py:209-293`（endpoint 没有 `language` 参数）
  - `app/services/news/normalizer.py:136`（`language=raw.language or "zh"`）
  - `web/src/pages/News/index.tsx:243, 290`（详情页用 `data.language`，但列表接口无法按此筛选）
- **问题描述**：用户看不到 `language=zhs` 与 `language=en` 的分离工具栏，导致研究员被中英夹杂淹没，特别在 `market=global` 下，"Google A股文章"与"新浪A股"挤在一起。
- **建议修复**：API 加 `language` 参数，前端在 toolbar 加 `Segmented` 选项。
- **优先级**：P1

#### 14. 微信号过滤仅在 wechat_zeping 一个源运行；其他微信源无过滤会污染 feed
- **位置**：
  - `app/services/news/scheduler_jobs.py:285-309`（`run_wechat_zeping_crawl` 是唯一调用 marketing filter 的入口）
  - `app/services/news/filters/wechat_marketing_filter.py`（filter 自身设计只针对单个调用）
- **问题描述**：营销过滤仅在 `wechat_zeping` 一个源应用。后续若新增其它公众号 / 内容源，没有调用同一个 filter；filter 设计为 per-call，不是 per-crawler-base class。营销污染很容易漏过去。
- **建议修复**：在 `BaseCrawler`/`NewsNormalizer` 之间加一个可选的 `marketing_filter.classify` hook，让所有接受公众号底稿的源都跑同一 filter；scheduler 层不再差异化。
- **优先级**：P1

#### 15. cninfo 报告只抓 4 个 filing category，对应官报体系（年报/一季报/三季报/半年报），缺临时公告、问询函、股权变动等
- **位置**：`app/services/news/sources/cninfo.py:44-49`（`DEFAULT_CATEGORIES` 仅有 4 类）
- **问题描述**：实际 A 股事件驱动多数是"临时公告"（股东大会、减持、关联交易、问询函）。当前只有季报/年报，导致：
  - 基金经理错过股权变动 / 大股东减持预警；
  - 监管类（问询函）零覆盖 — 这是合规重要事件；
  - 字段与 `event_category` 的"earnings"对应过窄，市场上 50% 的 `m&a` / `legal` 是 cninfo 临时公告。
- **建议修复**：
  1. 至少扩展 `DEFAULT_CATEGORIES` 涵盖：
     - `category_tzsm_szsh` (临时公告)
     - `category_kzzr_szsh` (可转债)
     - `category_qyfx_szsh` (权益分派)
     - `category_scgkfx_szsh` (市场关怀)
     - `category_gqbg_szsh` (股权变动)
     - `category_gqjl_szsh` (股权激励)
  2. 加按"上市日期"过滤（如最近 7 天）避免一上来扒全集；
  3. 在 mem 里记录每类 category 的最近 N 条统计，避免漏报；
- **优先级**：P1

#### 16. Jina Reader 限流为匿名 free tier，无降级与重试调度；突发新闻时段会挂
- **位置**：`app/services/news/content_fetcher.py:42-50`（`JINA_READER_URL = 'https://r.jina.ai'`）
- **问题描述**：Jina Reader 公共免费版限速（未注明），常常突发新闻时段（大选 / Fed / 周末）202 返回 429。代码没有：
  - 自动退避策略（仅 30s timeout + fetch 报错就 fail）；
  - 备用源（无）；
  - 调度排队：当 Jina 失败时，前端"加载完整正文"按钮可点，但用户每次点都直接 hit；
- **专业影响**：在关键事件期间，6/10 的详情页打不开，用户体验随机。
- **建议修复**：
  1. 加 Redis 锁 + retry-with-jitter 避免 burst（`PRIORITY` 队列）；
  2. 备用方案 1：可以缓存 worker's HTML 用 `trafilatura`/`newspaper3k` 本地解析；
  3. 备用方案 2：付费版本有保障时切换；
  4. UI 上：失败 > 1 次后按钮置灰，"全文暂不可用，请直接访问原文链接"。
- **优先级**：P1

#### 17. 雪球的 watchlist ticker 列表选取逻辑用 round-robin，导致任何 5 分钟内都只看 50 个 tickers
- **位置**：
  - `app/services/news/scheduler_xueqiu.py:60-84`（`_select_watchlist` 函数）
  - `app/services/news/scheduler_jobs.py:138-141`（`batch_size = max(1, int(settings.xueqiu_batch_size or 50))` 默认 50）
  - `app/services/news/scheduler_jobs.py:139-145`（`_DEFAULT_US_TICKERS = ["AAPL", "TSLA", "MSFT", …]` 硬编码 17 个）
- **问题描述**：watchlist 上的 ticker 池**随用户增长**线性变大（目前 `etf_info` 已经过千），但 scheduler 每个 tick 只轮询最多 50 个，意味着单 ticker 平均 `pool_size / 50 * 5min ≈ 100 min` 才能被访问一次。雪球数据"实时性"严重低于声称的"5m 间隔"。即使爬到了，雪球的 cookie 频率限制同样会让"5 分钟 ticker" 强制跳过 tick。
- **专业影响**：
  - 想看的"snowball hot ticker"长期不被采集；
  - 雪球数据的"5分钟延迟"sla 无法兑现，研究员对 freshness 信任崩盘。
- **建议修复**：
  1. 优先级分层：（a）用户在 `user_favorite` 中的 ~ 50 个 ETF 必轮；（b）`etf_info.top_n` (engagement) 排名高的 ticker；
  2. 调度间隔动态化：当 watchlist 池 > 1000 时，把雪球拉到 1h；
  3. 提供 dashboard 让用户看到"ticker X 最近一次采集时间"。
- **优先级**：P1

### P2 一般

#### 18. 行业 / 主题 / 地区 tag 体系缺位
- **位置**：`web/src/pages/News/index.tsx:160-176`（只有 `event_category`，没有 industry / theme）
- **问题描述**：研究员关心的"半导体""新能源车""猪产业"等垂直主题，详情页上没有，schedule 也没有专门的分类字典。`sentiment_pipeline._backfill_article_sentiment` 也只回填 `event_category`，没有 `industry` / `theme_tags` 数组。
- **建议修复**：
  1. 加 `news_article.themes JSON` 字段，存 LLM 抽取的 theme list；
  2. UI 增加"主题筛选"chip 栏；
  3. 与 `etf_info.themes` 或 `etf_info.industry` 字段对齐（已有吗？需审计）。
- **优先级**：P2

#### 19. 同源发布的时间戳偏差（很多 RSS 给出"文章修改时间"而不是"发布时间"）无二选一
- **位置**：
  - `app/services/news/sources/wechat_zeping.py:24`（`datePublished` / `dateModified` 二者并列）
  - `app/services/news/sources/wechat_zeping.py` 后续代码未确认用哪个（推测默认是 datePublished）
- **问题描述**：微信源订阅里"修改时间"指的是公众号手动修订，导致同一篇文章在用户点击"修正错别字"那一刻，发布相对时间被刷新 — 详情页排序也错乱。
- **建议修复**：在 WeChatZepingCrawler 强制只取 `date_published`（已经文档说明），但需要 runtime 校验不会拿 modified。
- **优先级**：P2

#### 20. `engagement` 是 JSON 字段，但 sentiment 与 engagement 之间没有交叉验证
- **位置**：`app/services/news/normalizer.py:142-145`（`engagement` 直接 `or {}` 入库）；前端 `web/src/pages/News/detail.tsx:600-624`
- **问题描述**：点赞=0、评论=0 时，下游无法区分"真无互动"vs"未抓取"vs"爬虫失败"。详情页 StatCard 全部显示"—"，实际这很常见且容易让人怀疑爬虫失效。
- **建议修复**：`engagement_fetched_at` 字段记录"互动数据的最近抓取时间"，前端以"未采集" vs "已 0" 区分。
- **优先级**：P2

#### 21. AI 清洗（`_clean_with_ai`）实际未启用（被 deterministic cleaner 替代），但 `ai_cleanup_status` 命名误导
- **位置**：
  - `app/services/news/content_fetcher.py:128-130`（`ai_cleaned_at = datetime.now(tz=UTC); ai_cleanup_status = ai_status`，且 `ai_status = "cleaned"` 写死）
  - `app/services/news/content_fetcher.py:332-336`（实际没有任何 `_clean_with_ai` 调用，纯正则清洗）
- **问题描述**：所有"cleaned"行真的是 deterministic 而非 LLM 清洗；M22-3 注释里描述的"DeepSeek 文本清洗 prompt"，代码里完全不存在。Watch 的前端/后端交互基于"AI 清洗"的字面 → 但其实没 LLM 调用。`ai_cleaned_at` 时间戳让研究员误以为是 LLM 跑的。
- **建议修复**：
  1. 把 `ai_cleanup_status` 改成 `cleanup_method = "deterministic" | "llm" | "skipped" | "failed"`；
  2. 注释里明确 "deterministic cleaning only — no LLM called at this step"；
  3. 新闻健康度 dashboard 把"DeepSeek 在清理阶段"卡片改名"清理状态"。
- **优先级**：P2

#### 22. 搜索趋势前端告警："数据仅供参考" 文案与实际数据矛盾
- **位置**：`web/src/pages/SearchTrends/index.tsx:181-187`（Alert 文案"不同来源不可直接对比, 仅供趋势观察"）
- **问题描述**：Alert 说"不可直接对比"，但 `Top 关键词` Tab 同时并排显示 "百度 Top 10" + "Google Top 10" 在同一列，视觉上让用户以为两者可比。用户点开"关键词对比"Tab 时，还会发现 `series` 端点把两个 source 跨时间轴叠加 — 这与"不可直接对比"再次矛盾。
- **建议修复**：跨源对比 Tab 改成"两个图分屏渲染"，而不是同一列的两个 Tag。
- **优先级**：P2

#### 23. 搜索趋势"全量刷新"按钮在所有登录用户都可点（仅 admin-only 应生效）
- **位置**：
  - `app/api/v1/search_trends.py`（建议配置 `require_admin`；需审计确认）
  - `web/src/pages/SearchTrends/index.tsx:135`（`useRefreshSearchTrends` 无 admin gate）
- **建议修复**：前端 / 后端都强制要求 admin role（与 `require_admin` 协同）。
- **优先级**：P2

#### 24. 雪球的"author_followers"等元数据未映射到 `engagement`
- **位置**：`app/services/news/sources/xueqiu.py:474-490`（`RawXueqiuPost` 有 `author_followers`，但 `engagement` dict 没有 followers）
- **问题描述**：雪球大 V 帖子（粉丝 10w+）与小 V（粉丝 100）影响差异巨大，但详情页"互动数据"只看 like/comment/repost/view，看不到"作者影响力"。研究员无法快速识别"是真大喇叭还是噪音帖"。
- **建议修复**：把 `author_followers` 入 `engagement.author_followers`，前端在 StatCard 增加"作者粉丝数"。
- **优先级**：P2

#### 25. ETF/Favorite 与 `sentiment` 跨语料库无法无缝对接（如雪球贴直接关联 ETF）
- **位置**：`app/services/news/normalizer.py:171-214`（符号提取 + etf_info 反查）
- **问题描述**：`news_article_symbol.symbol` 强制绑定到 `etf_info.code`，意味着非 ETF（A股个股 `600519` / 港股 / 美股个股）会被截断为 String(20) 然后 FK 失败；当前实现 fallback 跳过（truncated 安全）但 symbol 行写不进去。研究员在单股页上看不到相关雪球贴。
- **建议修复**：
  1. `etf_info` 扩成"instrument"表加 `(market, type)` 列，容纳个股、ETF、加密币；
  2. `news_article_symbol.symbol` 与 `etf_info.code` 解耦；
- **优先级**：P2

#### 26. scheduler 三种 reddit 频次同时存在：xueqiu 5m、cnbc 5m、yahoo_finance 5m，且都依赖外部 API
- **位置**：`app/services/news/scheduler_jobs.py`（`run_cnbc_crawl` `run_yahoo_crawl` `run_xueqiu_crawl`）
- **问题描述**：三个 5 min cron 共用一个 event loop 的风险 — 当一个源被反爬，retry 阻塞住 event loop 时其它源也会被卡。同样的问题在 test 期间可能让 batch 失败 rollback → DB 一致性风险。
- **建议修复**：
  1. 每个 cron 有独立 lock 与独立 session；
  2. failed 上限防止占用事件循环 > 60s；
- **优先级**：P2

#### 27. `securites` 来源在 `_NEWS_SOURCES` 中硬编码，新加源需要改 3 个地方
- **位置**：
  - `app/services/news/scheduler_jobs.py`（每个 `run_*_crawl` 独立函数）
  - `app/api/v1/news.py:507-518`（`_NEWS_SOURCES`）
  - `app/api/v1/news.py:524-534`（`_SOURCE_TO_JOB`）
  - `web/src/pages/News/index.tsx:190-201`（`SOURCE_LABELS`，再加 emoji / label）
- **问题描述**：加一个新源需要后端 4 个文件修改，且前端 emoji/label 是字典字面值（`{ source: {emoji, label}}`，少一个就 fallback 到 raw source id，对用户不友好）。
- **建议修复**：建一张 `news_source_meta` DB 表（source, zh_label, emoji, color, scheduler_job_id），前端 / 后端都从那里读；新增源只需要插 1 行。
- **优先级**：P2

#### 28. `factories/views.Sentiment_score` 列存 `Integer(-100..100)` 与 `_persist` 写 `Decimal` 进 `SentimentData.sentiment_score` 口径不一致
- **位置**：
  - `app/services/news/sentiment/sentiment_pipeline.py:425`（`sentiment_score=score_dec`，Decimal 类型）
  - `app/api/v1/news.py:720-727`（`if abs(score) > 1: score = score / 100.0`，`-100..100` ↔ `-1..1` 间口径切换）
  - `app/services/news/_model_loader.py:81`（`sentiment_score = Column(Integer, -100..100 placeholder）`）
- **问题描述**：LLM 输出 `score ∈ [-1.0, +1.0]`，被 `(sentiment_score, sentiment_label, confidence)` 三处不同口径切换：
  - `news_article.sentiment_score` (Integer) 存 `int(round(... * 100))` → -100..100；
  - `SentimentData.sentiment_score` (Decimal) 存 `Decimal(round(float(...), 4))` → -1.0..+1.0；
  - 前端 tooltip 文案：`分数 ${score.toFixed(2)}` (`web/src/pages/News/index.tsx:333`) → 假设 score ∈ [-1, +1]，但它接到的是 -100..100，必然显示 `-12.34` 不直观。
- **专业影响**：
  - 详情页情绪分数 tooltip 显示成 `-78` 而非 `-0.78`；
  - research.py 的 `get_aggregate_sentiment` 假设 `score ∈ [-1, +1]` 后跟 `news_article.sentiment_score` 口径打架；
  - 多源聚合都直接错位 100 倍。
- **建议修复**：
  1. `news_article.sentiment_score` 改 `Float`，存 `[-1.0, +1.0]`；
  2. 或在 ORM / Schema 层统一 `to_score(view)` getter；
  3. 前端 toFixed 之前做 `if abs(s) > 1.5: s = s / 100`；
- **优先级**：P0（数据严重不准） — 但因为两边都可能显示 0-100 与 -1~1，目前所有 detail 页面情绪分数 tooltip 都已经显示错。这次记录为 P0.5。

#### 29. `xinhua` 数据源已下线，但 `_NEWS_SOURCES` 不包它；Scheduler 也无对应 job
- **位置**：
  - `app/services/news/scheduler_jobs.py:193-212`（`run_xinhua_crawl` 注释说 "RSS 404，cron disabled"）
  - `app/api/v1/news.py:507-518`（`_NEWS_SOURCES` 也不含 `xinhua`）
  - `web/src/pages/News/index.tsx:192`（`SOURCE_LABELS.xinhua = { emoji: '📰', label: '新华' }`）
- **问题描述**：前端 UI 仍有"新华" emoji 标签，但永远拿不到数据来源（运营 24h 后会误判系统失效）。
- **建议修复**：删除前端标签 OR 灰显 OR 加"已下线"提示。
- **优先级**：P2

#### 30. 资讯健康度 Scheduler 状态永远显示"APScheduler 运行中"，但 scheduler 实际"运行但 job 全部失败"无法区分
- **位置**：
  - `app/api/v1/news.py:610-614`（`scheduler_running = is_scheduler_running()`）
  - `web/src/pages/NewsHealth/index.tsx:24-32`（`statusColor` 看 `scheduler_running`，忽略每个 job 的 status）
- **问题描述**：news-health 行内 scheduler "running=true" 但 10 个 cron jobs 全部 failed 24h → 等于"运行但死了"。`statusColor` 函数里 `if not schedulerRunning return 'red'`，但 `if all jobs failed but running` 仍显 green，没区分。
- **建议修复**：把 `jobs_with_failures_24h / total_jobs` 比值加入 statusColor；行级 color 由"全部失败"驱动 red。
- **优先级**：P2

---

## 二、当前缺失的功能 / 建议新增能力

### A. 跨源事件聚合（事件 cluster 视角）
1. 把 `dedup.py` 改造为真在用的 `cluster_id` 系统：基于 normalized_content_key，把同一事件的不同 source 行聚合到 `news_event_cluster` 表（一行 = 一个事件，多 source）。
2. 显示"3 家媒体覆盖，主流观点为…"，而不是孤立的 3 行 feed。
3. cluster 的 importance 取 max，归一化；情绪聚合按 cluster 而非 article 计算。

### B. 事件驱动信号与新闻情绪一体化
1. 详情页加"事件已触发策略"区：哪个 strategy 在监听这一 cluster（mover / risk-off / sanctions-watch）。
2. 让 sentiment_service / research chat 在引用一篇新闻时能用 cluster_id 提"另 2 篇同事件"，增强一致性。

### C. 行业 / 主题 / 地区三层 tag 体系
1. 主题词：在 crawler + 后端 LLM 阶段产出 `themes: ["半导体", "HBM"]`，让研究员筛主题。
2. 行业：把 etf_info 已有的 industry 列复用 + 在 news_article_symbol 反写。
3. 地区：与 market 字段合并，但允许 us/cn_a 但具体是"美股 / 中概"再下钻一层。

### D. AI 摘要聚合（事件级不是单篇级）
1. 当前 `_clean_with_ai` 注释存在但代码没有 — 真的做一个 DeepSeek 摘要 prompt，对每 cluster 做 100 字摘要。
2. 详情页头部加 1-2 行 cluster-level 摘要，替代现在没意义的 ai_cleanup_status。

### E. 事件时间线 / 演化曲线
1. 给每 cluster 加 timeline：什么时候事件首次发布，什么时点"情绪突变"（重大反转）— 用 sentiment 叠加 importance 折线图。
2. 提醒研究员："过去 6h 看多从 30% 降至 5%，市场重新定价"。

### F. 情绪置信度的 UI 集成
1. 前端 NewsCard 已显示 `confidence`，但 Sentiment 看板只显示 score，没有 confidence → 用户不知道"中性"信不信。
2. dashboard 加 sorted by `lowest_confidence_most_extreme` 看哪些"高强度但低置信"事件需要人工复核。

### G. 同事件多语言对照
1. Twitter、Reddit 英文；新浪、雪球中文 — 同一事件可能不同语言 + 不同时区被先后报道。
2. 详情页加"中英文对照"自动用 DeepSeek 把中文转英文 / 英文转中文，与现有 `translated_zh` 反向 — 让研究员在外网信息闭塞时仍可参考国内视角。

### H. 后端"业务层默认值"暴露
1. 现在有 `news_ai_cleanup_alert_pct=70.0`、`xueqiu_batch_size=50` 等 setting 都散落在 settings 模块。建议 admin UI 能即时调阈值（不重启 backend）。

### I. 资讯复盘机制
1. 历史事件回顾：研究员选一天，dashboard 显示"那天发生了什么 → 一周后股价如何 → 1 个月后"。需要：
   - `news_article_linked_price` 表：article × instrument × 1d/7d/30d return；
   - 渲染"事件驱动策略"因果图。

### J. 个股 × 资讯的 causal attribution
1. 现在 `_persist` 写 `SentimentData` 标 `instrument_code = str(sym)[:20]`（截断），且没有"这篇文章具体对这一标的影响程度"标定。研究员无法回答"哪篇新闻对 600519.SH 的过去 7 天情绪影响最大"。
2. 引入 `article_influence_score` JSON 字段，记录 LLM 给每个 (article, symbol) 对的 secondary impact。

### K. 业务连续性：BYO-AI / 自托管兜底
1. 当前所有"AI"能力（`chat`/`translation`/`sentiment_pipeline`/`wechat_marketing_filter` LLM）硬依赖 DeepSeek。雪球 + SEC EDGAR + cninfo 这部分不依赖 LLM 可继续跑，但情绪和摘要功能在 DeepSeek API outage 时会一起挂。
2. 短期：监控出问题时 exit-to-fallback 的标志（`news_ai_cleanup_status = 'skipped'`）已经做了，但前端几乎没渲染。
3. 长期：建议把"DeepSeek 不可用" 显示在 News + NewsHealth 顶部 banner，让研究员立刻知道"现在的情绪分数是启发式估算"。

### L. 来源可信度评分（source trust score）
1. 当前 `news_article.source` 只是一个 string，没有可信度评级。
2. 引入 `news_source_meta.trust_score` (0-100)，让重要性聚合时把 `importance * trust_score` 作为权重。
3. 前端来源 chip 旁加盾形图标（高） / 警告标（中） / 透明标（低），研究员一眼看"哪家比较靠谱"。

### M. 历史回放 — debug "为什么不早发现"
1. 当某 ticker 大跌后，研究员想"5 天前有没有任何信号被我们忽略过"？需要：
   - LLM 摘要每日 cluster 的 5 大信号；
   - 联动 ticker 股价 / 流入 / 北向资金；
   - 错误归因（signal 但未触发 / 信号弱）。

### N. 评价 / 校准机制
1. 上面 P1-8 的"重要性评测集"，建议建一个端到端评测 harness：`tests/test_news_pipeline.py` 跑 ground truth → 报 F1。
2. 主题分类、情绪分数都加入评测，避免 LLM provider 升级静默打破 ranking。

### O. 同事件去重 / cluster 推荐给研究员
1. 详情页右上角加"🤝 同一事件的 3 篇相关报道"列表，点击直接 jump；这个 UX 比 dedup 后端更难做，因为要做 cluster_id 维护。

---

## 三、审查小结（顺序无关）

| 维度 | 当前评分（5 分制） | 主要风险 |
|---|---|---|
| 数据完整性 | 3.0 | 时间戳口径混乱 (P1-10)、互动数据可信度无法判断 (P2-20) |
| 去重 / cluster | 1.0 | dedup.py 是死代码，跨源 100% 重复 (P0-2) |
| 全文搜索可用性 | 0.5 | `q` 参数未连接后端 (P0-1) |
| 情绪分析可信度 | 1.5 | 标签口径混乱 (P0-3)、分数 -100/100 与 -1/1 不一 (P0 末尾)；AI 清洗阈值过严 (P0-6) |
| 来源覆盖 | 3.0 | cninfo 仅 4 类 (P1-15)、雪球时效低 (P1-17) |
| 健康度可观测性 | 2.5 | AI 失败率告警阈值定义不清 (P1-5)、cleanup status 命名误导 (P2-21)、scheduler running 不等于功能正常 (P2-30) |
| 散户情绪看板 | 2.0 | 永远 neutral (P0-3)、重要性权重未考虑时间衰减 (P1-11)、详情页永远空状态 (P0-4) |
| 搜索趋势 | 3.0 | 跨源对比 UI 与"不可对比"文案矛盾 (P2-22)、admin-only 鉴权需审计 (P2-23) |
| Jina 抓全文 | 2.5 | 阈值过严导致 80% 失败 (P0-6)、无降级与限流 (P1-16) |
| 跨市场语料 | 2.0 | language 不可筛 (P1-13)、symbol 默认绑 ETF 不支持个股 (P2-25) |

**优先修复路径（建议 2 个 sprint 完成 P0 + 关键 P1）**：
1. 立刻修复：P0-1 (q)、P0-3 (label)、P0-28 (-100 vs -1)、P0-6 (Jina 阈值)、P0-2 (dedup 启用)。
2. 紧接修复：P0-4 (散户面板)、P1-10 (时区统一)、P1-11 (时间衰减)、P1-15 (cninfo category)。
3. 然后回到 P2 长期改进与新功能研发。

—— 报告完 ——
