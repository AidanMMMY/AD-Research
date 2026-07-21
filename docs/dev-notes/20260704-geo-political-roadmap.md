# 2026-07-04 全球政治 / 地缘事件覆盖路线图

> 最后核实更新：2026-07-21。P0 已落地（原文 §3），P1 两项（Global Markets
> 事件小卡 + AI Help 上下文）也已落地，事件窗口 2026-07-12 起由 24h 扩为
> 最近 7 天；P2（新增政治类 RSS 源、行业影响地图）仍未做。详见 §2/§4 内标注。

> 调研背景：AD-Research 已启动「全球资本市场」板块（K11），但目前仅覆盖
> 可量化指标（指数、收益率、商品、汇率）。影响 A 股开盘、外资流向、行业
> 轮动的另一类关键软变量 —— **全球政治 / 地缘事件** —— 仍未成体系。本
> 文档记录调研结论、补齐方案与已落地的 P0 改动。

## 1. 调研结论（read-only）

### 1.1 现有资讯抓取能力（`app/services/news/sources/`）

已注册的 `source`（来自 `app/api/v1/news.py` 的 `_NEWS_SOURCES` 与
`sources/__init__.py`）：

| source id      | 类型                       | 是否覆盖地缘/政治     |
|----------------|----------------------------|-----------------------|
| `cninfo`       | A 股公告 (深交所/上交所)   | 否（公司披露）         |
| `sina_finance` | 新浪财经 RSS               | 间接（标题层）         |
| `wechat_zeping`| 泽平宏观公众号              | **是**（宏观/政策评论）|
| `yahoo_finance`| Yahoo Finance RSS          | 间接（标题层）         |
| `cnbc`         | CNBC RSS                   | **是**（美股 + 美宏观）|
| `sec_edgar`    | SEC 备案                   | 否（公司事件）         |
| `reddit`       | Reddit ticker sub          | 否（散户）             |
| `xueqiu`       | 雪球帖                     | 否（散户）             |
| `coindesk`     | CoinDesk RSS               | 否（加密）             |
| `cointelegraph`| Cointelegraph RSS          | 否（加密）             |
| `xinhua`       | 新华社 RSS                 | **是**（CN 官方动态） |

**缺口**：缺 Reuters、Bloomberg、Politico、Foreign Policy、白宫官网、
各国央行公告。泽平公众号 + CNBC + 新华社只覆盖了"中、美宏观"一条窄路径，
**没有专门的政治 / 地缘事件源**。

### 1.2 现有 `event_category` 枚举

- 列定义：`app/models/news.py:85` —
  `Column(String(50), comment="earnings|m&a|product|macro|regulation|guidance|analyst|legal|rumor|other")`。
  是 `String(50)`，无 DB 级枚举约束。
- LLM prompt：`app/services/news/sentiment/prompts.py:35` —
  `"earnings|m&a|product|macro|regulation|guidance|analyst|legal|rumor|other"`。
- 前端展示：`web/src/pages/News/index.tsx:155` 与
  `web/src/pages/News/detail.tsx:282` —— 只做裸字符串 Tag 渲染。

**缺口**：
- 没有 `geopolitics` / `central_bank` / `election` / `trade_war` /
  `sanction` 这些关键类别。
- `GET /news` 与 `GET /news/watchlist` 都不支持按 `event_category`
  过滤；只能通过搜索框模糊命中。

### 1.3 现有情绪处理

- `app/services/news/sentiment/sentiment_pipeline.py` 对所有
  `event_category` 一视同仁，按 `importance` 加权后聚合。
- 没有为地缘类设置更高权重 / 不同的影响链模板。

### 1.4 现有 AI 教学助手上下文

- `web/src/components/AIHelpProvider.tsx:32-35` 中
  `buildHelpMessage(pageType, contextData, question)` 将
  `contextData` 字符串直接拼到 LLM prompt。`contextData` 是页面
  自由构造的 Markdown 文本，**没有事件流维度**。
- 没有页面把「最近 5 条地缘事件」塞进 context，所以用户问
  "特朗普关税对 A 股有什么影响"时模型只能泛泛而谈。

### 1.5 现有 Global Markets 页面

- `web/src/pages/Macro/` 只有一个宏观指标页（FRED / akshare）。
- 真正的 Global Markets 页面尚未落地（K11）。
- 暂无事件流小卡。

## 2. 优先级建议

### P0（已落地，见 §3）

1. **prompt + UI 同步扩展 `event_category`**：加入
   `geopolitics | central_bank | election | trade_war | sanction`。
   由于 DB 列是 `String(50)`，无需 Alembic 迁移。
2. **`/news` 增加 `event_category` 查询参数 + 前端 chip 筛选**。
3. **News 详情 + 列表把新类别显示成彩色 tag**，并加
   `POLITICAL_CATEGORY` 视觉强调（地缘/央行/选举/贸易战/制裁）。

> AI Help 上下文补"最近 5 条地缘事件"作为单独增量任务，预留接口
> `newsApi.recentPoliticalEvents()` + `buildNewsContext()` 辅助函数，
> 留给后续 K11 + AI Help 联调时使用，避免在本会话修改 AI Help 的
> 默认行为。

### P1（留给后续 K11 / 全局联动）

- **K11 Global Markets 顶部"最近 24h 重大事件"小卡**：
  `event_category IN (geopolitics, central_bank, election, trade_war,
  sanction)` + `importance >= 4` + `published_at >= now-24h`，每条点
  击跳 `/news/{id}`。
  - ✅ **已落地**（2026-07-21 核实）：`web/src/pages/GlobalMarkets/index.tsx`
    的 `RecentWeekEvents` 面板即按此实现；2026-07-12 起窗口由 24h 扩为
    **最近 7 天**（`importance >= 4`，每页 4 条），标题为「最近一周重大
    政治 / 地缘事件」。
- **未来 7 天日历小卡**：G7/G20/OPEC+/Fed/ECB/BOJ/CNPC 等静态 +
  可选 RSS（投资日历 wiki）。
  - ❌ 仍未做（2026-07-21 核实：无 `macro_calendar` 表或日历端点）。

### P2（长期）

- 增加 Reuters / Bloomberg / Politico / Foreign Policy / 白宫官网 /
  各国央行公告翻译源。
- 行业影响地图：点事件 → 看哪些 A 股行业 / ETF 关联最强（基于
  `news_article_symbol` 的频率 + 共现）。

## 3. P0 已落地

### 3.1 后端：扩展 prompt 与 API 过滤

- `app/services/news/sentiment/prompts.py`：
  把 `event_category` 枚举改为
  `earnings|m&a|product|macro|regulation|guidance|analyst|legal|rumor|geopolitics|central_bank|election|trade_war|sanction|other`。
- `app/api/v1/news.py`：`GET /news` 与 `GET /news/watchlist`
  新增 `event_category` 查询参数（可重复），后端走
  `NewsArticle.event_category.in_(...)`。

### 3.2 前端：News 页面筛选 + tag 着色

- `web/src/types/news.ts`：在 `NewsListParams` 与
  `NewsWatchlistParams` 中加入 `event_category?: string[]`。
- `web/src/api/news.ts`：把 `event_category` 透传给 query。
- `web/src/pages/News/index.tsx`：
  - 顶层加入 `POLITICAL_CATEGORIES` 列表。
  - 在 `FilterToolbar` 中渲染 chip（multi-select），与现有
    "我的自选 / 市场 / 来源 / 日期"并存。
  - 列表卡片 `event_category` tag 按政治类目显示彩色，普通类目
    保持灰色。
- `web/src/pages/News/detail.tsx`：把政治类目显示为彩色 Tag。

### 3.3 已验证

- `npx tsc --noEmit`：✅ 通过。
- `pytest app/tests/news/test_news.py` 中 `event_category` 用例
  仍通过（已有 `test_retail_sentiment_returns_aggregate` 等用例
  使用 `event_category="earnings"`，枚举扩展不影响既有值）。

## 4. 后续指南（P1/P2）

### P1：Global Markets "最近 24h 重大事件"小卡

> ✅ 已落地（见 §2 标注；窗口现为 7 天，`useRecentPoliticalEvents()`）。

1. K11 在 `web/src/pages/GlobalMarkets/index.tsx` 顶部加一个
   `<Panel>`，调用 `newsApi.list({ event_category:
   POLITICAL_CATEGORIES, importance_min: 4, from_date: now-24h,
   page_size: 10 })`。
2. 每行展示：标题、来源、`event_category` 中文标签、相对时间。
3. 点击 `navigate('/news/{id}')`。
4. 增加空态文案 "暂无 24h 内重大政治事件"。

### P1：AI Help 上下文接入"最近 5 条地缘事件"

> ✅ 已落地（2026-07-21 核实）：GlobalMarkets 页的 AI Help 按钮通过
> `buildGlobalMarketsContext(flatRows, recentEvents)` 把同一批政治事件
> （复用 `useRecentPoliticalEvents` 缓存）注入 `contextData`。

1. `web/src/pages/GlobalMarkets/index.tsx`（或 News 详情）调
   `newsApi.list({ event_category: POLITICAL_CATEGORIES,
   page_size: 5 })`，把标题 + 来源 + 时间拼成 markdown 字符串。
2. 把字符串塞进 `useAIHelp().open({ contextData: ... })` 的
   contextData，让 AI 在回答时引用真实事件。

### P2：政治事件 RSS 抓取

1. 新增 `app/services/news/sources/reuters_rss.py`、
   `bloomberg_rss.py`、`whitehouse_rss.py`、`ecb_rss.py` 等。
2. 在 `crawler` 注册时映射 `source` 到 `_SOURCE_TO_JOB`。
3. 在 `app/services/news/sources/__init__.py` 暴露。
4. 在 `app/api/v1/news.py:_NEWS_SOURCES` 中追加 id。
5. 在 `web/src/pages/News/index.tsx` 的 `SOURCE_LABELS` 中加
   emoji + 中文标签。

### P2：行业影响地图

1. 后端 `GET /news/impacts?category=geopolitics&symbol=XXX`：基于
   `news_article_symbol` 计算"最近 30 天地缘类目下与 XXX 同现次数
   最高的行业 ETF"。
2. 前端 Global Markets 详情面板渲染网络图。