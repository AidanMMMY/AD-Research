"""Scheduler-wiring tests for the 2026-08-04 AI-chain waves.

The integration registered two batch tables (``ai_cn_batch`` /
``ai_us_batch``) into ``scheduler_jobs.py``, ``app/core/scheduler.py``
and ``app/api/v1/news.py``. This module mirrors
``test_expansion_wave_wiring.py`` for both waves.
"""

from __future__ import annotations

import pytest

from app.services.news.sources.ai_cn_batch import AI_CN_BATCH_JOBS, AI_CN_BATCHES
from app.services.news.sources.ai_us_batch import AI_US_BATCH_JOBS, AI_US_BATCHES


class TestAiCnWiring:
    def test_batch_jobs_materialized(self):
        from app.services.news import scheduler_jobs as sj

        for _job_id, _label, batch in sj.AI_CN_BATCH_JOBS:
            fn = getattr(sj, f"run_ai_cn_{batch}_crawl")
            assert callable(fn)
            assert fn.__name__ == f"run_ai_cn_{batch}_crawl"

    def test_job_table_covers_all_batches(self):
        from app.services.news import scheduler_jobs as sj

        assert {b for _, _, b in sj.AI_CN_BATCH_JOBS} == set(AI_CN_BATCHES)

    @pytest.mark.parametrize("batch", sorted(AI_CN_BATCHES))
    def test_health_meta_exists(self, batch):
        from app.api.v1.news import _WORKER_META

        assert f"news_aicn_{batch}_60m" in _WORKER_META

    def test_health_keyword_covers_job_ids(self):
        from app.api.v1.news import _WORKER_KEYWORDS

        assert any(k in "news_aicn_a_60m" for k in _WORKER_KEYWORDS)


class TestAiUsWiring:
    def test_batch_jobs_materialized(self):
        from app.services.news import scheduler_jobs as sj

        for _job_id, _label, batch in sj.AI_US_BATCH_JOBS:
            fn = getattr(sj, f"run_ai_us_{batch}_crawl")
            assert callable(fn)
            assert fn.__name__ == f"run_ai_us_{batch}_crawl"

    def test_job_table_covers_all_batches(self):
        from app.services.news import scheduler_jobs as sj

        assert {b for _, _, b in sj.AI_US_BATCH_JOBS} == set(AI_US_BATCHES)

    @pytest.mark.parametrize("batch", sorted(AI_US_BATCHES))
    def test_health_meta_exists(self, batch):
        from app.api.v1.news import _WORKER_META

        assert f"news_aius_{batch}_60m" in _WORKER_META

    def test_health_keyword_covers_job_ids(self):
        from app.api.v1.news import _WORKER_KEYWORDS

        assert any(k in "news_aius_a_60m" for k in _WORKER_KEYWORDS)


class TestCrossWaveIntegrity:
    def test_cn_us_no_slug_overlap(self):
        cn_slugs = {row[0] for row in sum(AI_CN_BATCHES.values(), [])}
        us_slugs = {row[0] for row in sum(AI_US_BATCHES.values(), [])}
        assert not (cn_slugs & us_slugs)

    def test_cn_us_no_url_overlap(self):
        cn_urls = {row[2] for row in sum(AI_CN_BATCHES.values(), [])}
        us_urls = {row[2] for row in sum(AI_US_BATCHES.values(), [])}
        assert not (cn_urls & us_urls)

    def test_job_ids_unique_across_waves(self):
        cn_ids = [j for j, _, _ in AI_CN_BATCH_JOBS]
        us_ids = [j for j, _, _ in AI_US_BATCH_JOBS]
        assert len(set(cn_ids + us_ids)) == len(cn_ids) + len(us_ids)
