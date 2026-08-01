# 2026-08-01 全球指数详情页 + 资讯三修复 综合 runbook

涉及提交：`5999f5e`（后端）/ `04a09ef`（前端）/ `4e034e6`（news 双根治）/ `f413835`（段距），全部已部署（生产 git_sha `f413835`），Backend CI / Web CI / Deploy 全绿。

## 1. 全球速览 28 个宏观代码详情页

### 架构

- **新表 `global_index_daily_bar`**（迁移 `v3w5x7y9z1a3`）：复合 PK `(code, trade_date, source)`，O/H/L 可空、close 非空、volume 可空。不带 region/name——元数据从 `macro_indicator` 取，避免双写不一致
- **双写管线**：`run_global_indices_refresh`（每工作日 17:00）原有三段 `macro_indicator` upsert 不动，末尾追加 OHLC 旁路段（yfinance 3mo 增量 + akshare 40 天），per_source 摘要新增 `yfinance_ohlcv`/`akshare_ohlcv` 计数；旁路段整体 try/except 不阻断主流程
- **聚合端点** `GET /api/v1/macro/indicators/{code}/detail`：返回 `has_ohlc` 驱动前端选蜡烛/折线；`latest`/`stats`（52 周高低）在 OHLC 分支由 bars 计算，折线分支来自 `get_series` 窗口
- **前端** `/global/:code`（GlobalIndexDetail）：KPI strip 5 列 + 时间范围 Radio + KLineChart（has_ohlc=true）/ MacroLineChart（AreaSeries，新组件）；速览页 CategoryTable 行点击跳转

### 关键陷阱（下次别再踩）

1. **EUR=X 类 `invert_value=True` 源**：存 OHLC 时四个价格全取倒数**且 high/low 互换**（new_high=1/low, new_low=1/high），否则 K 线实体颠倒
2. **覆盖率漂移**：`global_sp500`/`global_dow` 被 FRED+yfinance 双覆盖、`global_ndx` 在 registry 但不在速览——前后端都不硬编码清单，`has_ohlc` 由数据驱动
3. **yfinance RATES registry（^TNX/^TYX）不抓 OHLC**——利率走折线，与 FRED 8 个 line 代码保持一致

### 运维记录

- 迁移随部署自动执行（deploy 跑 alembic upgrade head）
- **10 年回填已完成**：`docker cp scripts/backfill_global_index_ohlcv.py <backend>:/tmp/ && docker exec <backend> bash -c "PYTHONPATH=/app python3 /tmp/backfill_global_index_ohlcv.py --period 10y"` → **71,009 行 / 22 个代码**（yfinance 10y + akshare A股全历史，上证综指 8,694 行最深）
- 生产验证：global_hsi 蜡烛+52周高低 ✅、us_dgs10 折线 ✅、usd_eur 反转值 ~1.15 且 high>low ✅、bad_code 404 ✅

## 2. FRED_API_KEY 生产缺失（待用户提供 key）

- **发现过程**：详情页 us_dgs2/t10y2y/t10y3m/vix 折线数据停在 2026-07-21；admin `POST /macro/refresh?lookback_days=3650` 37 系列全部瞬间失败
- **根因**：生产 `.env` `FRED_API_KEY=` 为空。us_dgs2 等 4 个 FRED-only 系列 fetched_at 显示 07-05→07-22 每天有 key 在工作，之后 key 丢失（疑似 7-22 前后某次 .env 重写丢行）；`/root/.env.bak-20260801` 里已为空，无法找回
- **为什么速览页看不出**：us_dgs10/us_dgs30/global_dxy/sp500/nasdaq/dow 有 yfinance 后备源（^TNX/^TYX/DX-Y.NYB 等）每天 17:00 照常更新，掩盖了 FRED 链路断裂
- **修复**：用户提供 FRED key（免费申请 https://fred.stlouisfed.org/docs/api/api_key.html）→ 写入 ECS `.env` → recreate backend → `POST /api/v1/macro/refresh?lookback_days=3650` 回填 10 年

## 3. 资讯时区错位根治（"未来时间"文章）

- **根因①**：`global_nocutnews`（韩国）RSS 的 `<dc:date>` 是 KST 墙钟却标注 `GMT` → 入库比真实 UTC 快 9h，前端 +8 后变成"明天"
- **根因②（连带发现）**：`rss_common._parse_date` 内部把 naive 时间强转 UTC，导致 `_extract_pub_date` 的 `default_tz` 参数成死代码——`zhb_ithometw`（naive 台湾时间）和 `stats_gov` 受害
- **修复**：`_parse_date` 不再内部强转；新增 `GLOBAL_RSS_TZ_OVERRIDE = {"nocutnews": "Asia/Seoul"}`（feed 时区标注错误时按发行方本地时区重解释）；zh 批次源加 `default_tz=Asia/Shanghai`；入库汇合点 `published_at > now+15min` 钳到 `now`
- **存量已修（生产已执行）**：nocutnews 256 行 -9h、ithometw 60 行 -8h、stats_gov 55 行 -8h；剩余未来行 0
- **新增坏 feed 怎么办**：curl 该 feed 对比 `<dc:date>` 墙钟与真实时区，确认误标后往 `GLOBAL_RSS_TZ_OVERRIDE` 加条目

## 4. 正文提取：打平守卫 + Jina 断路器 + 段落保留

- **huxiu 段落粘连根因**：`rss_common._strip_html` / `normalizer._strip_html_to_text` 把 `<p>` 等块级标签替换成空格再 `\s+` 折叠 → 全文一段。修复：块级边界（`</p>|</div>|</li>|</h1-6>|</blockquote>|</tr>|</section>|</article>` → `\n\n`，`<br>` → `\n`）先转换行再剥标签
- **打平缓存守卫**（content_fetcher）："≥400 字且零换行"的缓存视为结构丢失，自动从原页面重抓重建段落
- **Jina 断路器**：402/429/403 拉闸（冷却 1h/5min/10min）fail-fast，消除 drain 每轮白打必败请求；402 错误信息明示 "recharge the Jina account"
- **段距修复**（前端）：`--reading-para-gap` 页面级覆写 1em→0.75em + 渲染层 3+ 连换行折叠
- **huxiu 存量重抓**：387 篇打平行，首批 255 篇 tier-1 成功修复；~132 篇中部分是源站已 404 的失效文章（直连 404 → 落 Jina → 402），**等 Jina 充值后重跑 `/tmp/refetch_huxiu.py`（幂等，脚本在 backend 容器 /tmp，源码见下）**

```python
# /tmp/refetch_huxiu.py（PYTHONPATH=/app python3 运行）
from sqlalchemy import select
from app.core.database import SessionLocal
from app.services.news._model_loader import NewsArticle
from app.services.news.content_fetcher import ContentFetcher
db = SessionLocal()
ids = db.execute(select(NewsArticle.id).where(
    NewsArticle.source == "huxiu", NewsArticle.full_content.isnot(None))).scalars().all()
flat = [i for i in ids if "\n" not in (db.get(NewsArticle, i).full_content or "")]
print("flattened:", len(flat), flush=True)
f = ContentFetcher(db)
for i in flat:
    f.fetch(i, force=True)
db.close()
```

## 5. Jina 余额耗尽（P0，待用户充值）

- 生产 `JINA_API_KEY` 在，但 r.jina.ai 返回 **402 InsufficientBalanceError**（7-30 起）
- 影响：marketwatch/investing/ft/ouestfrance/ndtv_profit/businesstoday_my 等 10+ 英文源全文提取全灭（7-30 以来 failed 累计 2000+）
- 充值后无需任何代码操作：断路器 1h 冷却自动恢复探测，drain 自动重试 failed 行；huxiu 剩余 ~110 篇重跑一次上面的脚本即可
