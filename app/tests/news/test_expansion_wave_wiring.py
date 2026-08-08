"""Scheduler-wiring tests for the 2026-08-02 expansion waves.

The main-session integration registered three batch tables
(``en_fin_batch`` / ``official_batch`` / ``zh_media_batch``) into
``scheduler_jobs.py``, ``app/core/scheduler.py`` and
``app/api/v1/news.py``. The official wave carries its own wiring
tests in ``test_official_batch.py``; this module covers the English
finance (``enf_*``) and Chinese media / Asia / crypto (``zhm_*``)
waves the same way.
"""

from __future__ import annotations

import pytest

from app.services.news.sources.en_fin_batch import EN_FIN_BATCH_JOBS, EN_FIN_BATCHES
from app.services.news.sources.zh_media_batch import ZH_MEDIA_BATCH_JOBS, ZH_MEDIA_BATCHES


class TestEnFinWiring:
    def test_batch_jobs_materialized(self):
        from app.services.news import scheduler_jobs as sj

        for _job_id, _label, batch in sj.EN_FIN_BATCH_JOBS:
            fn = getattr(sj, f"run_en_fin_{batch}_crawl")
            assert callable(fn)
            assert fn.__name__ == f"run_en_fin_{batch}_crawl"

    def test_job_table_covers_all_batches(self):
        from app.services.news import scheduler_jobs as sj

        assert {b for _, _, b in sj.EN_FIN_BATCH_JOBS} == set(EN_FIN_BATCHES)

    @pytest.mark.parametrize("batch", sorted(EN_FIN_BATCHES))
    def test_health_meta_exists(self, batch):
        from app.api.v1.news import _WORKER_META

        assert f"news_enf_{batch}_60m" in _WORKER_META

    def test_health_keyword_covers_job_ids(self):
        from app.api.v1.news import _WORKER_KEYWORDS

        assert any(k in "news_enf_a_60m" for k in _WORKER_KEYWORDS)

    def test_no_overlap_with_official_wave(self):
        """The parallel waves initially collected 6 identical feeds."""
        from app.services.news.sources.official_batch import OFFICIAL_FEEDS

        enf_urls = {url for _, _, url, _, _ in sum(EN_FIN_BATCHES.values(), [])}
        ofc_urls = {url for _, _, url, _, _ in OFFICIAL_FEEDS}
        assert not (enf_urls & ofc_urls)


class TestZhMediaWiring:
    def test_batch_jobs_materialized(self):
        from app.services.news import scheduler_jobs as sj

        for _job_id, _label, batch in sj.ZH_MEDIA_BATCH_JOBS:
            fn = getattr(sj, f"run_zh_media_{batch}_crawl")
            assert callable(fn)
            assert fn.__name__ == f"run_zh_media_{batch}_crawl"

    def test_job_table_covers_all_batches(self):
        from app.services.news import scheduler_jobs as sj

        assert {b for _, _, b in sj.ZH_MEDIA_BATCH_JOBS} == set(ZH_MEDIA_BATCHES)

    @pytest.mark.parametrize("batch", sorted(ZH_MEDIA_BATCHES))
    def test_health_meta_exists(self, batch):
        from app.api.v1.news import _WORKER_META

        assert f"news_zhm_{batch}_60m" in _WORKER_META

    def test_health_keyword_covers_job_ids(self):
        from app.api.v1.news import _WORKER_KEYWORDS

        assert any(k in "news_zhm_a_60m" for k in _WORKER_KEYWORDS)


def test_job_id_namespaces_are_unique():
    """enf/ofc/zhm job ids must not collide with each other."""
    enf_ids = {j for j, _, _ in EN_FIN_BATCH_JOBS}
    zhm_ids = {j for j, _, _ in ZH_MEDIA_BATCH_JOBS}
    assert not (enf_ids & zhm_ids)
    assert all(j.startswith("news_enf_") for j in enf_ids)
    assert all(j.startswith("news_zhm_") for j in zhm_ids)


class TestEduWiring:
    """Education wave (edu_*) scheduler/health wiring (added 2026-08-02)."""

    def test_batch_jobs_materialized(self):
        from app.services.news import scheduler_jobs as sj
        from app.services.news.sources.edu_batch import EDU_BATCHES

        for _job_id, _label, batch in sj.EDU_BATCH_JOBS:
            fn = getattr(sj, f"run_edu_{batch}_crawl")
            assert callable(fn)
            assert fn.__name__ == f"run_edu_{batch}_crawl"
        assert {b for _, _, b in sj.EDU_BATCH_JOBS} == set(EDU_BATCHES)

    @pytest.mark.parametrize("batch", ["a", "b"])
    def test_health_meta_exists(self, batch):
        from app.api.v1.news import _WORKER_META

        assert f"news_edu_{batch}_60m" in _WORKER_META

    def test_health_keyword_covers_job_ids(self):
        from app.api.v1.news import _WORKER_KEYWORDS

        assert any(k in "news_edu_a_60m" for k in _WORKER_KEYWORDS)

    def test_edu_sources_tagged_in_learning_seed(self):
        """All 17 edu feeds must appear in the learning-center seed."""
        from app.services.news.source_meta_seed import SOURCE_META_SEED
        from app.services.news.sources.edu_batch import EDU_FEEDS

        tagged = {row["source"] for row in SOURCE_META_SEED}
        missing = {f"edu_{slug}" for slug, *_ in EDU_FEEDS} - tagged
        assert not missing, f"edu feeds missing from learning seed: {missing}"
