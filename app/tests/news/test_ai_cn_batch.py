"""Module self-consistency tests for the 2026-08-04 AI-chain CN batch.

Covers ``app/services/news/sources/ai_cn_batch.py`` only — scheduler /
health / seed wiring is done by the main session and tested elsewhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.news.sources.ai_cn_batch import (
    AI_CN_BATCH_JOBS,
    AI_CN_BATCHES,
    AI_CN_FEEDS,
)

_EXISTING_SOURCES = Path("/tmp/adresearch-build/existing_sources.txt")


class TestBatchTable:
    def test_batches_cover_all_rows(self):
        covered = [row for rows in AI_CN_BATCHES.values() for row in rows]
        assert covered == AI_CN_FEEDS

    def test_each_batch_at_most_10(self):
        for key, rows in AI_CN_BATCHES.items():
            assert 0 < len(rows) <= 10, f"batch {key} has {len(rows)} rows"

    def test_batch_keys_start_at_a(self):
        assert sorted(AI_CN_BATCHES)[0] == "a"

    def test_batch_jobs_match_batches(self):
        assert {b for _, _, b in AI_CN_BATCH_JOBS} == set(AI_CN_BATCHES)
        assert len(AI_CN_BATCH_JOBS) == len(AI_CN_BATCHES)

    def test_job_id_and_label_format(self):
        for job_id, label, batch in AI_CN_BATCH_JOBS:
            assert job_id == f"news_aicn_{batch}_60m"
            assert label == f"AI链-中文 批次{batch.upper()}"


class TestIntraModuleDedup:
    def test_no_duplicate_slugs(self):
        slugs = [slug for slug, *_ in AI_CN_FEEDS]
        assert len(slugs) == len(set(slugs))

    def test_no_duplicate_urls(self):
        urls = [url for _, _, url, _, _ in AI_CN_FEEDS]
        assert len(urls) == len(set(urls))


class TestNoOverlapWithExistingSources:
    @pytest.mark.skipif(
        not _EXISTING_SOURCES.exists(),
        reason="existing sources snapshot not available",
    )
    def test_zero_overlap_with_existing_slugs(self):
        existing = {
            line.strip()
            for line in _EXISTING_SOURCES.read_text().splitlines()
            if line.strip()
        }
        mine = {slug for slug, *_ in AI_CN_FEEDS}
        assert not (mine & existing), f"overlap: {mine & existing}"


class TestFieldValues:
    def test_market_whitelist(self):
        # news API _GLOBAL_MARKETS = (cn_a, us, crypto); "global" would be
        # invisible in the default view — never allowed here.
        for slug, _, _, market, _ in AI_CN_FEEDS:
            assert market in {"cn_a", "us"}, f"{slug}: market={market}"

    def test_language_whitelist(self):
        for slug, _, _, _, language in AI_CN_FEEDS:
            assert language in {"zh", "en"}, f"{slug}: language={language}"

    def test_urls_are_http(self):
        for slug, _, url, _, _ in AI_CN_FEEDS:
            assert url.startswith(("http://", "https://")), f"{slug}: {url}"
