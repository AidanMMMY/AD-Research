# 20260729 中文播客批次 (zhx_) — 集成补丁说明

> 本文件由子任务 agent 产出。**主会话请按以下三处补丁串行集成**；
> 子任务按纪律未改动任何现有文件。新文件
> `app/services/news/sources/zh_multi_batch.py`（40 个 ECS 实测存活
> 中文播客源，批次 a–d，每批 10 个）与
> `app/tests/news/test_zh_multi_batch.py` 已就绪，
> `poetry run pytest app/tests/news/test_zh_multi_batch.py -q` 已绿
> （14 passed + 7 skipped，跳过项即下方集成后才能启用的接线测试）。

集成共三步，全部为**追加**，不删改任何现有行。

---

## 1. `app/services/news/scheduler_jobs.py`

追加到 `GLOBAL_INDIE_BATCH_JOBS` 物化循环
（`globals()[f"run_global_indie_{_batch}_crawl"] = ...`）之后、
"New Chinese news sources" 段之前：

```python
# ── Chinese podcast batches (added 2026-07-29) ──
#
# 40 live-verified Chinese-language podcasts (investing / macro /
# business analysis / industry depth / tech commentary) on 小宇宙 /
# 喜马拉雅 / SoundOn / Firstory / Fireside / Acast / SoundCloud /
# self-hosted feeds. Table and selection rule live in
# app/services/news/sources/zh_multi_batch.py; batch keys a-d sit in
# their own job namespace (news_zhx_*), so they do not collide with
# the a-n (independent) / o-x (global indie) key ranges. Same no-LLM
# rationale as the independent batches (curated editorial voices) —
# no marketing filter.

def _zhx_batch_job(job_id: str, batch_key: str):
    """Build a ``run_*`` function crawling one Chinese podcast batch."""

    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        from app.services.news.sources.zh_multi_batch import (
            ZhMultiBatchCrawler,
        )

        async def _go():
            crawler = ZhMultiBatchCrawler(batch_key)
            return await crawler.fetch_recent()

        try:
            articles = _run_async(_go())
        except Exception as exc:
            logger.exception("zh podcast batch %s crawl failed: %s", batch_key, exc)
            return {
                "fetched": 0,
                "written": 0,
                "skipped": True,
                "skip_reason": f"crawl_error: {exc}",
            }

        if not articles:
            return {"fetched": 0, "written": 0, "skipped": True, "skip_reason": "no_articles"}

        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}

    _run.__name__ = f"run_zh_multi_{batch_key}_crawl"
    return _run


from app.services.news.sources.zh_multi_batch import (  # noqa: E402
    ZH_MULTI_BATCH_JOBS,
)

for _job_id, _label, _batch in ZH_MULTI_BATCH_JOBS:
    globals()[f"run_zh_multi_{_batch}_crawl"] = _zhx_batch_job(_job_id, _batch)
```

## 2. `app/core/scheduler.py`

追加到 `GLOBAL_INDIE_BATCH_JOBS` 注册循环（约 2096–2108 行）之后：

```python
        # Chinese podcast batches (2026-07-29) — 40 verified Chinese
        # podcasts, batches a-d, generated in
        # ``scheduler_jobs.ZH_MULTI_BATCH_JOBS``, all hourly.
        for job_id, label, batch in _news_jobs.ZH_MULTI_BATCH_JOBS:
            fn = getattr(_news_jobs, f"run_zh_multi_{batch}_crawl")
            scheduler.add_job(
                fn,
                trigger=IntervalTrigger(minutes=60, jitter=600),
                id=job_id,
                name=label,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
```

## 3. `app/api/v1/news.py`

**3a.** `_WORKER_KEYWORDS` 元组 — 在 `"gind_",` 之后追加一行：

```python
    "zhx_",
```

**3b.** `_WORKER_META` — 在 `news_gind_x_60m` 条目之后追加 4 条：

```python
    # Chinese podcast batches (2026-07-29, 40 sources)
    "news_zhx_a_60m": {"label": "中文播客 A 组 (10 源)", "schedule": "每 60 分钟"},
    "news_zhx_b_60m": {"label": "中文播客 B 组 (10 源)", "schedule": "每 60 分钟"},
    "news_zhx_c_60m": {"label": "中文播客 C 组 (10 源)", "schedule": "每 60 分钟"},
    "news_zhx_d_60m": {"label": "中文播客 D 组 (10 源)", "schedule": "每 60 分钟"},
```

## 4. 集成后启用接线测试

集成完成后，编辑 `app/tests/news/test_zh_multi_batch.py`，把
`TestSchedulerWiring` 类上的 `@pytest.mark.skip(...)` 装饰器删掉，
然后跑：

```bash
poetry run pytest app/tests/news/test_zh_multi_batch.py -q
```

预期 18 passed 0 skipped。

## 5. 验证 checklist

1. `poetry run pytest app/tests/news -q` 全绿。
2. ECS 部署后 `curl /health`（或前端健康格）出现 `news_zhx_a_60m` … `news_zhx_d_60m`。
3. 首轮跑完后查库确认落库：

```sql
SELECT source, COUNT(*) FROM news_article
WHERE source LIKE 'zhx_%' GROUP BY source ORDER BY 2 DESC LIMIT 20;
```

最后：全部为 `language='zh'`，翻译管线仅处理英文，不会对这些文章产生
额外 LLM 成本；摘要管线（如有中文摘要开关）按现有逻辑自动拾取。
