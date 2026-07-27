# wechat2rss 二批（batch2）集成补丁说明

> 日期：2026-07-28
> 新模块：`app/services/news/sources/wechat2rss_batch2.py`（103 源，10 批次 `w2a`–`w2j`）
> 本文档给出主会话需要**串行**应用到 3 个共享文件的精确补丁。子 agent 未改动这些文件。
> 应用后 `app/tests/news/test_wechat2rss_batch2.py` 中 13 个 xfail 会自动转为通过（共 27 项全绿）。

---

## 1. `app/services/news/scheduler_jobs.py`

在第一批 wechat2rss 段落（`WECHAT2RSS_BATCH_JOBS` 的 `globals()` 循环，约 445 行）之后、
`# ── Global multi-language RSS batches` 段落之前，插入以下完整代码块：

```python
# ── wechat2rss second-wave batches (added 2026-07-28) ──
#
# 103 more WeChat accounts — macro / strategy / industry / tech /
# business — served by TWO public wechat2rss mirrors (bestblogs.dev
# self-hosted instance + the original xlab.app free list). Table and
# selection rule live in
# app/services/news/sources/wechat2rss_batch2.py; evidence table in
# docs/dev-notes/20260728-wechat-batch2.md. Same batching rationale
# as the first wave (10 jobs for 103 feeds, keys w2a-w2j). The
# marketing filter stays on: this wave includes portal-media and
# review accounts where soft-ad posts do appear.


def _wechat2b_batch_job(job_id: str, batch_key: str):
    """Build a ``run_*`` function crawling one second-wave wechat2rss batch."""

    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        from app.services.news.filters import WechatMarketingFilter
        from app.services.news.sources.wechat2rss_batch2 import (
            Wechat2RssBatch2Crawler,
        )

        async def _go():
            crawler = Wechat2RssBatch2Crawler(batch_key)
            return await crawler.fetch_recent()

        try:
            articles = _run_async(_go())
        except Exception as exc:
            logger.exception("wechat2rss batch2 %s crawl failed: %s", batch_key, exc)
            return {
                "fetched": 0,
                "written": 0,
                "skipped": True,
                "skip_reason": f"crawl_error: {exc}",
            }

        if not articles:
            return {"fetched": 0, "written": 0, "skipped": True, "skip_reason": "no_articles"}

        try:
            marketing_filter = WechatMarketingFilter()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("wechat marketing filter init failed, passing through: %s", exc)
            marketing_filter = None

        filtered, rejected = _apply_marketing_filter(articles, marketing_filter)
        written = _write_to_db(filtered)
        return {
            "fetched": len(articles),
            "written": written,
            "rejected_marketing": rejected,
        }

    _run.__name__ = f"run_wechat2b_{batch_key}_crawl"
    return _run


WECHAT2B_BATCH_JOBS: list[tuple[str, str, str]] = [
    # (job_id, label, batch_key) — all run every 60 minutes.
    ("news_wechat2b_w2a_60m", "公众号二批 A 组", "w2a"),
    ("news_wechat2b_w2b_60m", "公众号二批 B 组", "w2b"),
    ("news_wechat2b_w2c_60m", "公众号二批 C 组", "w2c"),
    ("news_wechat2b_w2d_60m", "公众号二批 D 组", "w2d"),
    ("news_wechat2b_w2e_60m", "公众号二批 E 组", "w2e"),
    ("news_wechat2b_w2f_60m", "公众号二批 F 组", "w2f"),
    ("news_wechat2b_w2g_60m", "公众号二批 G 组", "w2g"),
    ("news_wechat2b_w2h_60m", "公众号二批 H 组", "w2h"),
    ("news_wechat2b_w2i_60m", "公众号二批 I 组", "w2i"),
    ("news_wechat2b_w2j_60m", "公众号二批 J 组", "w2j"),
]
for _job_id, _label, _batch in WECHAT2B_BATCH_JOBS:
    globals()[f"run_wechat2b_{_batch}_crawl"] = _wechat2b_batch_job(_job_id, _batch)
```

注意点：
- 复用了同文件内已有的 `_record_etl` / `_run_async` / `_apply_marketing_filter` / `_write_to_db`，无需新增 import。
- 与第一批共享 `WechatMarketingFilter`（LLM 判定结果有 24h 缓存，成本可控）。
- 函数名/批次键命名空间为 `wechat2b_*` / `w2[a-j]`，与第一批 `wechat2rss_*` / `a-i`、独立源 `independent_*` / `a-n`、全球 RSS `global_rss_*` / `a-l` 均不冲突。

## 2. `app/core/scheduler.py`

在 `for job_id, label, batch in _news_jobs.WECHAT2RSS_BATCH_JOBS:` 注册循环（约 2058-2068 行）之后插入：

```python
        # wechat2rss second-wave batches (2026-07-28) — generated in
        # ``scheduler_jobs.WECHAT2B_BATCH_JOBS``, all hourly.
        for job_id, label, batch in _news_jobs.WECHAT2B_BATCH_JOBS:
            fn = getattr(_news_jobs, f"run_wechat2b_{batch}_crawl")
            scheduler.add_job(
                fn,
                trigger=IntervalTrigger(minutes=60),
                id=job_id,
                name=label,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
```

位置必须在 `try:` 块内（与第一批同级的缩进），`except ImportError` 之前。

## 3. `app/api/v1/news.py`

### 3a. `_WORKER_KEYWORDS`（约 598 行，`"wechat2rss",` 之后）

```python
    "wechat2rss",
    "wechat2b",
```

### 3b. `_WORKER_META`（约 652 行，第一批 9 个 `news_wechat2rss_*` 条目之后）

```python
    # wechat2rss second-wave batches (2026-07-28, 103 accounts)
    "news_wechat2b_w2a_60m": {"label": "公众号二批 A 组 (11 号)", "schedule": "每 60 分钟"},
    "news_wechat2b_w2b_60m": {"label": "公众号二批 B 组 (11 号)", "schedule": "每 60 分钟"},
    "news_wechat2b_w2c_60m": {"label": "公众号二批 C 组 (11 号)", "schedule": "每 60 分钟"},
    "news_wechat2b_w2d_60m": {"label": "公众号二批 D 组 (11 号)", "schedule": "每 60 分钟"},
    "news_wechat2b_w2e_60m": {"label": "公众号二批 E 组 (11 号)", "schedule": "每 60 分钟"},
    "news_wechat2b_w2f_60m": {"label": "公众号二批 F 组 (11 号)", "schedule": "每 60 分钟"},
    "news_wechat2b_w2g_60m": {"label": "公众号二批 G 组 (11 号)", "schedule": "每 60 分钟"},
    "news_wechat2b_w2h_60m": {"label": "公众号二批 H 组 (11 号)", "schedule": "每 60 分钟"},
    "news_wechat2b_w2i_60m": {"label": "公众号二批 I 组 (11 号)", "schedule": "每 60 分钟"},
    "news_wechat2b_w2j_60m": {"label": "公众号二批 J 组 (4 号)", "schedule": "每 60 分钟"},
```

### 3c. `_WORKER_JOB_TO_SOURCE`

**不需要改动**。批次 job 写多个 source（每源 `wechat_{slug}`），与第一批批次 job 一样不在该映射内
（该映射只服务单源 job 的 articles_24h 统计；批次 job 在健康面板按 etl_log 展示）。

## 4. 应用后验证清单

```bash
# 1. 单测全绿（27 项：14 通过 + 13 个原 xfail 转为通过）
poetry run pytest app/tests/news/test_wechat2rss_batch2.py -q

# 2. 批次 job 函数已生成
poetry run python -c "
from app.services.news import scheduler_jobs as sj
fns = [n for n in dir(sj) if n.startswith('run_wechat2b_')]
print(len(fns), sorted(fns))
assert len(fns) == 10
"

# 3. 本地冒烟一个批次（真镜像，~25s）
poetry run python -c "
import asyncio
from app.services.news.sources.wechat2rss_batch2 import Wechat2RssBatch2Crawler
arts = asyncio.run(Wechat2RssBatch2Crawler('w2j', delay_seconds=0.5).fetch_recent())
print(len(arts), 'articles'); print(arts[0].source, arts[0].title[:30] if arts else '-')
"

# 4. 部署后：健康面板应出现 10 个 "公众号二批 X 组" 卡片；
#    etl_log 中 news_wechat2b_w2a_60m 每小时一条 success。
```

## 5. 部署注意

- 无需新增环境变量、无需迁移、无需改动 wewe-rss。
- bestblogs 镜像（`wechat2rss.bestblogs.dev`）是 BestBlogs 项目的自建公共实例：免费公共品，
  可用性不受我们控制。爬虫已带 2s inter-feed 礼貌延迟；若其失效，etl_log 会出现连续 failed，
  届时按 runbook §5 处理（下掉对应批次或替换镜像域名）。
- `news_article.source_id` 已在迁移 `s5t7u9v1w3x5` 加宽到 500，镜像长 mp 链接不会再触发
  2026-07-27 的截断 P0。
