# 20260728 全球英文独立源批次 (gind_) — 集成补丁说明

> 本文件由子任务 agent 产出。**主会话请按以下三处补丁串行集成**；
> 子任务按纪律未改动任何现有文件。新文件
> `app/services/news/sources/global_indie_batch.py`（104 个 ECS 实测
> 存活源，批次 o–x；另有 6 个实测合格的亚洲源按主会话裁决移交并行
> `asia_en_batch` 波次）与 `app/tests/news/test_global_indie_batch.py`
> 已就绪，`pytest app/tests/news/test_global_indie_batch.py -q` 已绿
> （13 passed + 13 skipped，跳过项即下方集成后才能启用的接线测试）。

集成共三步，全部为**追加**，不删改任何现有行。

---

## 1. `app/services/news/scheduler_jobs.py`

追加到 `INDEPENDENT_BATCH_JOBS` 物化循环（`globals()[f"run_independent_{_batch}_crawl"] = ...`）之后、"New Chinese news sources" 段之前：

```python
# ── Global English indie batches (added 2026-07-28) ──
#
# 104 live-verified English independent blogs / newsletters / research
# outlets (custom-domain Substacks, Ghost, dev.to/Hashnode authors,
# nonprofit newsrooms). Table and selection rule live in
# app/services/news/sources/global_indie_batch.py; batch keys o-x keep
# clear of the a-n keys owned by INDEPENDENT_BATCH_JOBS. Same no-LLM
# rationale as the independent batches (curated editorial voices).

def _global_indie_batch_job(job_id: str, batch_key: str):
    """Build a ``run_*`` function crawling one global-indie batch."""

    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        from app.services.news.sources.global_indie_batch import (
            GlobalIndieBatchCrawler,
        )

        async def _go():
            crawler = GlobalIndieBatchCrawler(batch_key)
            return await crawler.fetch_recent()

        try:
            articles = _run_async(_go())
        except Exception as exc:
            logger.exception("global indie batch %s crawl failed: %s", batch_key, exc)
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

    _run.__name__ = f"run_global_indie_{batch_key}_crawl"
    return _run


from app.services.news.sources.global_indie_batch import (  # noqa: E402
    GLOBAL_INDIE_BATCH_JOBS,
)

for _job_id, _label, _batch in GLOBAL_INDIE_BATCH_JOBS:
    globals()[f"run_global_indie_{_batch}_crawl"] = _global_indie_batch_job(_job_id, _batch)
```

## 2. `app/core/scheduler.py`

追加到 `GLOBAL_RSS_BATCH_JOBS` 注册循环（约 2089–2099 行）之后：

```python
        # Global English indie batches (2026-07-28) — 104 independent
        # English blogs / newsletters / research outlets, batches o-x,
        # generated in ``scheduler_jobs.GLOBAL_INDIE_BATCH_JOBS``, all hourly.
        for job_id, label, batch in _news_jobs.GLOBAL_INDIE_BATCH_JOBS:
            fn = getattr(_news_jobs, f"run_global_indie_{batch}_crawl")
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

## 3. `app/api/v1/news.py`

**3a.** `_WORKER_KEYWORDS` 元组 — 在 `"global_rss",` 之后追加一行：

```python
    "gind_",
```

**3b.** `_WORKER_META` — 在 `news_global_rss_l_60m` 条目之后追加 10 条：

```python
    # Global English indie batches (2026-07-28, 104 sources)
    "news_gind_o_60m": {"label": "全球独立源 O 组 (11 源)", "schedule": "每 60 分钟"},
    "news_gind_p_60m": {"label": "全球独立源 P 组 (11 源)", "schedule": "每 60 分钟"},
    "news_gind_q_60m": {"label": "全球独立源 Q 组 (11 源)", "schedule": "每 60 分钟"},
    "news_gind_r_60m": {"label": "全球独立源 R 组 (11 源)", "schedule": "每 60 分钟"},
    "news_gind_s_60m": {"label": "全球独立源 S 组 (11 源)", "schedule": "每 60 分钟"},
    "news_gind_t_60m": {"label": "全球独立源 T 组 (11 源)", "schedule": "每 60 分钟"},
    "news_gind_u_60m": {"label": "全球独立源 U 组 (11 源)", "schedule": "每 60 分钟"},
    "news_gind_v_60m": {"label": "全球独立源 V 组 (11 源)", "schedule": "每 60 分钟"},
    "news_gind_w_60m": {"label": "全球独立源 W 组 (11 源)", "schedule": "每 60 分钟"},
    "news_gind_x_60m": {"label": "全球独立源 X 组 (5 源)", "schedule": "每 60 分钟"},
```

## 4. 集成后启用接线测试

集成完成后，编辑 `app/tests/news/test_global_indie_batch.py`，把
`TestSchedulerWiring` 里 4 个 `@pytest.mark.skip(...)` 装饰器删掉，
然后跑：

```bash
poetry run pytest app/tests/news/test_global_indie_batch.py -q
```

预期 17 passed 0 skipped。

## 5. 验证 checklist

1. `poetry run pytest app/tests/news -q` 全绿。
2. ECS 部署后 `curl /health`（或前端健康格）出现 `news_gind_o_60m` … `news_gind_x_60m`。
3. 首轮跑完后查库确认落库：

```sql
SELECT source, COUNT(*) FROM news_article
WHERE source LIKE 'gind_%' GROUP BY source ORDER BY 2 DESC LIMIT 20;
```

最后：翻译管线应自动拾取（全部为 `language='en'`，`translation_service` 仅排除中文）。
