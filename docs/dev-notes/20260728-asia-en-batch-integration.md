# 亚洲英文 RSS 批次（asia_en）集成说明

日期：2026-07-28
交付：`app/services/news/sources/asia_en_batch.py`（176 源，16 批 a–p）+ `app/tests/news/test_asia_en_batch.py`
Runbook：`docs/dev-notes/20260728-asia-en-batch.md`（含 .html）

本文件给出主会话统一集成时需在 **三个现有文件** 中新增的完整代码块。直接按块粘贴即可；行号基于集成时的文件状态，位置注释已标明参照物。

> 注意：本批次与并行交付的 `global_indie_batch`（批次 o–x，`gind_` 前缀）、`wechat2rss_batch2` 无 slug / URL / job_id 冲突（已逐一比对）。`ASIA_EN_BATCH_JOBS` 由源模块导出，`scheduler_jobs` 直接 import，避免两处维护批次几何。

---

## 1. `app/services/news/scheduler_jobs.py`

在 `_global_rss_batch_job` 注册循环（`for _job_id, _label, _batch in GLOBAL_RSS_BATCH_JOBS:` 那一段）之后追加：

```python
# ── Asia-focused English RSS batches (added 2026-07-28) ──
#
# 176 live-verified English feeds — Asian English financial media
# (India/SEA/South Asia/Gulf/Central Asia/China-EN/AU-NZ),
# international media section feeds beyond the front page, industry
# verticals (semiconductors, new energy, biopharma, automotive,
# shipping & logistics, commodities & mining, aerospace/defense/
# fintech trades) and self-hosted investor blogs — split into 16
# batch jobs (11 feeds each) so the scheduler gains 16 jobs instead
# of 176. See app/services/news/sources/asia_en_batch.py for the
# selection rule and docs/dev-notes/20260728-asia-en-batch.md for the
# two-round ECS verification evidence.

from app.services.news.sources.asia_en_batch import (  # noqa: E402
    ASIA_EN_BATCH_JOBS,
)


def _asia_en_batch_job(job_id: str, batch_key: str):
    """Build a ``run_*`` function crawling one Asia-EN batch."""

    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        from app.services.news.sources.asia_en_batch import (
            AsiaEnBatchCrawler,
        )

        async def _go():
            crawler = AsiaEnBatchCrawler(batch_key)
            return await crawler.fetch_recent()

        try:
            articles = _run_async(_go())
        except Exception as exc:
            logger.exception("asia-en batch %s crawl failed: %s", batch_key, exc)
            return {
                "fetched": 0,
                "written": 0,
                "skipped": True,
                "skip_reason": f"crawl_error: {exc}",
            }

        if not articles:
            return {"fetched": 0, "written": 0, "skipped": True, "skip_reason": "no_articles"}

        # No marketing filter: professional publications and curated
        # blogs, same precedent as ``_global_rss_batch_job``.
        written = _write_to_db(articles)
        return {"fetched": len(articles), "written": written}

    _run.__name__ = f"run_asia_en_{batch_key}_crawl"
    return _run


for _job_id, _label, _batch in ASIA_EN_BATCH_JOBS:
    globals()[f"run_asia_en_{_batch}_crawl"] = _asia_en_batch_job(_job_id, _batch)
```

## 2. `app/core/scheduler.py`

在 GLOBAL_RSS 注册循环（`for job_id, label, batch in _news_jobs.GLOBAL_RSS_BATCH_JOBS:` 那段 `scheduler.add_job(...)` 块）之后、`except ImportError:` 之前追加：

```python
        # Asia-focused English RSS batches (2026-07-28) — Asian
        # English financial media + international section feeds +
        # industry verticals + investor blogs, generated in
        # ``scheduler_jobs.ASIA_EN_BATCH_JOBS`` (re-exported from
        # ``sources/asia_en_batch.py``), all hourly.
        for job_id, label, batch in _news_jobs.ASIA_EN_BATCH_JOBS:
            fn = getattr(_news_jobs, f"run_asia_en_{batch}_crawl")
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

### 3a. `_WORKER_KEYWORDS` 元组追加两个关键字

在 `"global_rss",` 之后追加（保持元组语法）：

```python
    "global_rss",
    "asia_en",
    "asen_",
```

### 3b. `_WORKER_META` 追加 16 条

在 `"news_global_rss_l_60m": {...}` 之后追加：

```python
    "news_asia_en_a_60m": {"label": "亚洲英文财经 RSS A 组 (11 源)", "schedule": "每 60 分钟"},
    "news_asia_en_b_60m": {"label": "亚洲英文财经 RSS B 组 (11 源)", "schedule": "每 60 分钟"},
    "news_asia_en_c_60m": {"label": "亚洲英文财经 RSS C 组 (11 源)", "schedule": "每 60 分钟"},
    "news_asia_en_d_60m": {"label": "亚洲英文财经 RSS D 组 (11 源)", "schedule": "每 60 分钟"},
    "news_asia_en_e_60m": {"label": "亚洲英文财经 RSS E 组 (11 源)", "schedule": "每 60 分钟"},
    "news_asia_en_f_60m": {"label": "亚洲英文财经 RSS F 组 (11 源)", "schedule": "每 60 分钟"},
    "news_asia_en_g_60m": {"label": "亚洲英文财经 RSS G 组 (11 源)", "schedule": "每 60 分钟"},
    "news_asia_en_h_60m": {"label": "亚洲英文财经 RSS H 组 (11 源)", "schedule": "每 60 分钟"},
    "news_asia_en_i_60m": {"label": "亚洲英文财经 RSS I 组 (11 源)", "schedule": "每 60 分钟"},
    "news_asia_en_j_60m": {"label": "亚洲英文财经 RSS J 组 (11 源)", "schedule": "每 60 分钟"},
    "news_asia_en_k_60m": {"label": "亚洲英文财经 RSS K 组 (11 源)", "schedule": "每 60 分钟"},
    "news_asia_en_l_60m": {"label": "亚洲英文财经 RSS L 组 (11 源)", "schedule": "每 60 分钟"},
    "news_asia_en_m_60m": {"label": "亚洲英文财经 RSS M 组 (11 源)", "schedule": "每 60 分钟"},
    "news_asia_en_n_60m": {"label": "亚洲英文财经 RSS N 组 (11 源)", "schedule": "每 60 分钟"},
    "news_asia_en_o_60m": {"label": "亚洲英文财经 RSS O 组 (11 源)", "schedule": "每 60 分钟"},
    "news_asia_en_p_60m": {"label": "亚洲英文财经 RSS P 组 (11 源)", "schedule": "每 60 分钟"},
```

> 生成方式（批次几何变化时可重跑）：
> ```python
> from app.services.news.sources.asia_en_batch import ASIA_EN_BATCH_JOBS, ASIA_EN_BATCHES
> for job_id, _label, batch in ASIA_EN_BATCH_JOBS:
>     n = len(ASIA_EN_BATCHES[batch])
>     print(f'    "{job_id}": {{"label": "亚洲英文财经 RSS {batch.upper()} 组 ({n} 源)", "schedule": "每 60 分钟"}},')
> ```

---

## 集成后验证清单

1. `poetry run pytest app/tests/news/test_asia_en_batch.py -q` — 10 项全绿（当前已是）。
2. 集成后补跑 `poetry run pytest app/tests/news -q` 确认无回归。
3. 建议在 `test_asia_en_batch.py` 的 `TestSchedulerWiring` 风格下补三个集成测试（仿照 `test_global_rss_batch.py::TestSchedulerWiring`）：`ASIA_EN_BATCH_JOBS` 函数物化、`_WORKER_META` 覆盖 16 个 job、`_WORKER_KEYWORDS` 命中。
4. ECS 部署后首个整点观察 health grid：`news_asia_en_a_60m` … `news_asia_en_p_60m` 的 `fetched/written`；`source LIKE 'asen_%'` 应出现新文章，`language='en'` 的文章会由 `news_translate_10m` 自动翻译。
5. 前端默认 "global" 筛选可见：`market` 只写 `us` / `cn_a`（本模块已保证），不踩 `global_rss_batch` 写 `global` 导致默认视图不可见的老坑。
