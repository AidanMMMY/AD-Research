# 2026-07-29 资讯正文提取问题修复 Runbook

> 触发：2026-07-27 用户截图报告两类正文问题 —— (1) 正文提取成导航/推荐链接垃圾；
> (2) 正文完全为空。本文记录摸底数据、根因、修复内容、验证证据与运维后续。
> 代码修复全部在本地完成（未 commit），ECS 只做只读排查。

---

## 1. 现状摸底（ECS 只读，2026-07-29，最近 7 天 news_article）

### 1.1 body 与 full_content 均缺失（<100 字符）的 Top 源

| source | 7天总量 | 完全无内容 | 根因分类 |
|---|---|---|---|
| cls | 1630 | 665 (41%) | 快讯本身短（API 即全文），ingestion 未 seed full_content |
| investing | 624 | **624 (100%)** | feed 无 description + 直连 403 + Jina 匿名封域 |
| jiemian | 1791 | 339 | 快讯被误判 failed + 部分提取失败 |
| wallstreetcn | 1323 | 298（误报） | 7-27 后已修，短快讯即全文，非问题 |
| sina_finance | 2343 | 184 | trafilatura 抽到侧栏垃圾阻断 Jina 兜底 |
| 36kr | 772 | 88 | SPA 页面，提取不稳定 |
| wechat_canghai 等 8 个 wewe-rss 源 | 各 30 | **各 30 (100%)** | wewe-rss 会话过期，feed 本身 content_html 为空 |
| huxiu / chinanews_finance / marketwatch / caixin | — | 11–23 | 同 sina 类提取失败 |

注：`cls`/`wallstreetcn` 快讯 30–160 字符是**完整内容**，不是 bug；
真正的问题是 ingestion 没把 API 全文 seed 进 full_content，导致反复回源抓取。

### 1.2 正文含导航垃圾的 Top 源（特征词命中）

| source | 命中数 | 典型 |
|---|---|---|
| asen_ndtv_profit | 159 | Jina 输出整页导航（`* [Live TV](url)` 等）穿透清洗器 |
| jiemian | 142 | 多为误命中（正文提及 read more）；少量快讯 nav 残留 |
| yahoo_finance | 103 | 多为正文内合法提及，少量推广行残留 |
| global_ithome_cn / wechat_* / asen_* | 各 10–40 | 同类 Jina nav 泄漏 |

典型样本（id=5241959, asen_ndtv_profit）：存储的 full_content 10000 字符中
前 ~5000 字符是网站导航（链接占比 0.59），正文从第 5000 字符才开始。

---

## 2. 根因定位（实跑验证）

### 2.1 investing.com —— 三重死路（100% 空正文）

1. **Feed 本身无 `<description>`**：`https://www.investing.com/rss/news_25.rss`
   只有 title/pubDate/author/link/enclosure，解析器无正文可提取（ECS 实拉确认）。
2. **直连反爬 403**：文章页 UA 伪装直连仍 403（3 字节响应体）。
3. **Jina Reader 匿名封域**：`r.jina.ai` 返回
   `AbuseAlleviationError: Anonymous access to domain www.investing.com blocked ...
   DDoS attack suspected` —— 匿名层整个域被封，带 API key 可解。

→ 三层全挂时旧代码**什么都不写**（full_content_fetched_at/ai_cleanup_status 全 NULL），
624 条文章每 10 分钟被 drain job 不可见地重试。

### 2.2 asen_ndtv_profit —— 清洗器漏 link-only 行

Jina 对 NDTV Profit 返回整页 markdown（含完整导航）。
旧 `_strip_boilerplate_lines` 只删"单行单链接"，漏掉了：

- `*   [Live TV](https://... "Live TV")` ——  bullet + 链接
- `[facebook](x)[twitter](y)[instagram](z)` —— 一行多链接
- `[](url)` —— 空锚文本链接
- `[![Image](img)](url)` —— 图片链接
- `*   #### [标题 ![Image](img)](url)` —— 相关推荐卡片（链接文本里嵌图片）
- `Advertisement` / `Scan to Download` / `Read Time: 2 mins` —— 英文 boilerplate

### 2.3 sina_finance —— trafilatura 垃圾阻断 Jina 兜底

新浪财经文章页 trafilatura（favor_precision）抽中的是**侧栏推广块**
（VIP课程推荐/APP专享/热门推荐/公众号二维码，~200 字符），非 None，
旧逻辑 `if md: method = "trafilatura"` 直接接受 → 清洗后 <80 字符 → 标记 failed，
**Jina 兜底从未被调用**。实测同 URL Jina 可返回 36KB 完整正文。

### 2.4 jiemian 快讯 —— 真快讯被误判 failed

界面快讯全文就是一句话（如 "7月29日下午，长鑫科技成交额达300亿元，现涨6.6%。"，29 字符）。
trafilatura 正确抽出 29 字符 < MIN_BODY_LENGTH(80) → 标记 failed →
详情页红色失败 Alert，且 full_content 永远为 NULL。是真快讯，不是提取失败。

### 2.5 wewe-rss 8 个公众号源 —— 数据源会话过期（运维项，非代码）

zhigu/yuanchuan/canghai/fupeng/lixunlei/congming/beiwei/latepost
8 个 wewe-rss feed **items 全部 content_html 为空**（ECS 容器内实查）。
wewe-rss 的微信读书会话过期，需重新扫码登录（AuthCode 默认 123567）。
mp.weixin.qq.com 直连与 Jina 均返回"环境异常"验证码页，回填无解。
**代码层无法修，需运维重新登录 wewe-rss。**

### 2.6 cls —— API 即全文但 ingestion 不 seed

财联社电报 API 的 `content` 字段就是完整快讯；cls.cn 详情页是 Next.js SPA。
旧 `_looks_full_article(min=400)` 把快讯判为摘要 → full_content=NULL →
每 10 分钟回源 SPA 页做无用功。与 7-26 wallstreetcn 完全同构。

---

## 3. 修复内容（本地代码，未 commit）

### 3.1 `app/services/news/content_fetcher.py`

1. **link-only 行清洗**：新增 `_is_link_only_line()` —— 剥掉行内所有 markdown
   链接原子（含嵌套图片、`javascript:void(0)` 嵌套括号、空锚文本）后，
   残余仅为 bullet/分隔符/井号即整行删除。覆盖 2.2 全部六种漏网形态。
2. **英文 boilerplate**：新增 `_EN_BOILERPLATE_LINE_RE`（Advertisement /
   Scan to Download / Read Time / Published On / Sign up / Trending /
   Also Read / Download the App / author: / photo credit / 英文裸日期行），
   仅对 ≤120 字符的独立行 **fullmatch**，且同时匹配"去链接后的残余"
   （`*   Author: [Name](url)` 也算 byline），正文句子不误伤。
3. **面包屑+标题行去重**：`_remove_duplicate_title` 新增第二模式，
   删除 `[home](x)[Markets](y)标题原文` 这类面包屑标题行。
4. **tier-1 垃圾闸**：`_extraction_is_junk()` —— 对清洗后的候选判空/判薄(<80)/
   判 nav 行占比(>50%)。trafilatura 抽中垃圾时**fall through 到 Jina**（修 2.3）。
   注意：刻意**不用链接字符占比**做闸 —— 新浪正文每家公司名都是超链接
   （实测合法正文链接字符占比 0.83），会误杀；用行级特征才对。
5. **快讯确认**：`_is_confirmed_flash()` —— 清洗结果 20–80 字符且与
   RSS/API body（≤300 字符）归一化后互相包含或 difflib 相似度 ≥0.6，
   判定为真快讯：存 full_content 并标 cleaned（修 2.4）。
6. **失败留痕**：三层全挂时写入 `ai_cleanup_status='failed'` +
   `ai_cleaned_at`（不动 full_content/fetched_at，drain 继续重试），
   让"从未尝试"与"永久失败"可区分（修 2.1 的观测盲区）。
7. **Jina API key**：`_call_jina` 在 `settings.jina_api_key` 非空时加
   `Authorization: Bearer` 头 —— 解 investing.com 匿名封域的钥匙（2.1）。

### 3.2 `app/services/news/normalizer.py`

- `_SOURCES_WITH_API_FULL_CONTENT` 增加 `"cls"`：电报 API content 即全文，
  ingestion 直接 seed full_content，不再回源 SPA 页（修 2.6）。

### 3.3 `app/config.py`

- 新增 `jina_api_key: str = ""`（env `JINA_API_KEY`，无前缀，自动映射）。

### 3.4 测试 `app/tests/news/test_content_fetcher.py`（+12 个）

link-only 六形态、英文 boilerplate 保留正文句、junk 闸三态、
sina 垃圾→Jina 兜底、jiemian 快讯确认、不匹配短文仍 failed、
全挂留痕、nav-only Jina 不缓存、API key 头、cls seed、sina 不 seed 回归。

---

## 4. 验证

### 4.1 pytest

- `app/tests/news/` + `test_news_dedup.py`：**502 passed**
- `app/tests` 其余：**706 passed**（合计 1208 全绿）

### 4.2 真实数据前后对比

| 案例 | 修复前 | 修复后 |
|---|---|---|
| NDTV id=5241959（真实库存内容重跑清洗器） | 10000 字符，链接占比 0.59，前 5000 字符全是导航 | 2963 字符纯正文，导航全灭，junk=False |
| sina id=5242354（真实 HTML+真实 Jina 输出模拟） | tier-1 抽侧栏 → 清洗后 15 字符 → failed，full_content NULL | 闸拒绝 tier-1 → Jina → 8385 字符完整正文，junk=False |
| jiemian id=5242854（真实 Jina 输出模拟） | 29 字符 < 80 → failed 红 Alert | flash_confirmed=True → 存全文标 cleaned |
| investing | 624 条全 NULL 且无留痕 | 三层全挂写 failed 可观测；配 `JINA_API_KEY` 后 Jina 层可通 |

### 4.3 部署后回填 SQL（参考）

```sql
-- 清掉被导航垃圾污染的 full_content，让 drain job 用新清洗器重抓
UPDATE news_article
SET full_content = NULL, full_content_fetched_at = NULL, ai_cleanup_status = NULL
WHERE fetched_at >= now() - interval '14 days'
  AND full_content ~* '(Live TV|Scan to Download|Get App|Read Time:|Sign up for)'
  AND length(full_content) > 2000;
```

---

## 5. 运维后续（代码外）

1. **wewe-rss 重新登录**（2.5）：8 个公众号 feed content_html 全空，
   需在 wewe-rss Web 端重新扫码（AuthCode 123567），恢复后新文章自动带全文；
   存量 240 条空 body 文章在 feed 恢复后无法自动回补（feed 只推新），
   如需要可删除让 crawler 重拉。
2. **配置 JINA_API_KEY**（2.1）：申请 jina.ai key 后写入 ECS `.env`，
   investing.com 全文即可恢复；不配则 investing 保持"纯标题源"，
   建议在产品上接受（其内容多为 Reuters 通稿，其它源有覆盖）。
3. **seekingalpha**（摘要 feed + 付费墙）与 **investing** 同属"源层面无解"，
   保持现状即可，失败留痕后监控可见。
4. **scheduler 补丁说明**：本修复未动 scheduler_jobs.py / scheduler.py /
   news.py（纪律要求）。若后续要给 drain job 加"按源熔断"
   （如 investing 连续失败 N 次暂停重试），改 `run_fetch_full_content`
   的 SELECT 加 `AND ai_cleanup_status IS DISTINCT FROM 'failed'`
   或加 per-source cooldown —— 留待下一轮。

---

## 6. 文件清单

- `app/services/news/content_fetcher.py` — 清洗器/闸/快讯/留痕/Jina key
- `app/services/news/normalizer.py` — cls 加入 API 全文源白名单
- `app/config.py` — `jina_api_key` 设置项
- `app/tests/news/test_content_fetcher.py` — +12 测试
