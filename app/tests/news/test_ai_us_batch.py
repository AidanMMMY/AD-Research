"""Module-self tests for the 2026-08-04 English AI-chain batch wave.

Covers ``app/services/news/sources/ai_us_batch.py`` only — scheduler /
health-API / source-meta wiring is done by the coordinating session and
tested elsewhere. Mirrors the structure of
``test_expansion_wave_wiring.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.news.sources.ai_us_batch import (
    AI_US_BATCH_JOBS,
    AI_US_BATCHES,
    AI_US_FEEDS,
)

_EXISTING_SOURCES = Path("/tmp/adresearch-build/existing_sources.txt")


class TestBatchTable:
    def test_all_feeds_appear_in_exactly_one_batch(self):
        batched = [row for rows in AI_US_BATCHES.values() for row in rows]
        assert batched == AI_US_FEEDS

    def test_batches_within_size_limit(self):
        assert AI_US_BATCHES, "no batches materialized"
        for key, rows in AI_US_BATCHES.items():
            assert 0 < len(rows) <= 10, f"batch {key} has {len(rows)} feeds"

    def test_batch_keys_restart_at_a_and_are_contiguous(self):
        assert sorted(AI_US_BATCHES) == list(AI_US_BATCHES)
        assert list(AI_US_BATCHES)[0] == "a"

    def test_job_table_covers_all_batches(self):
        assert {b for _, _, b in AI_US_BATCH_JOBS} == set(AI_US_BATCHES)
        assert len(AI_US_BATCH_JOBS) == len(AI_US_BATCHES)

    def test_job_id_and_label_format(self):
        for job_id, label, batch in AI_US_BATCH_JOBS:
            assert job_id == f"news_aius_{batch}_60m"
            assert label == f"AI链-英文 批次{batch.upper()}"


class TestUniqueness:
    def test_no_duplicate_slugs(self):
        slugs = [slug for slug, *_ in AI_US_FEEDS]
        assert len(slugs) == len(set(slugs))

    def test_no_duplicate_urls(self):
        urls = [url for _, _, url, *_ in AI_US_FEEDS]
        assert len(urls) == len(set(urls))

    def test_no_duplicate_display_names(self):
        names = [name for _, name, *_ in AI_US_FEEDS]
        assert len(names) == len(set(names))

    @pytest.mark.skipif(
        not _EXISTING_SOURCES.exists(),
        reason="existing-source slug snapshot not available on this machine",
    )
    def test_zero_overlap_with_existing_sources(self):
        existing = {
            line.strip()
            for line in _EXISTING_SOURCES.read_text().splitlines()
            if line.strip()
        }
        ours = {slug for slug, *_ in AI_US_FEEDS}
        overlap = ours & existing
        assert not overlap, f"slugs already in the library: {sorted(overlap)}"


class TestMarketAndLanguage:
    def test_market_is_always_us_never_global(self):
        """news API _GLOBAL_MARKETS whitelist is cn_a/us/crypto only —
        market="global" rows would be invisible in the default view."""
        bad = {slug for slug, _, _, market, _ in AI_US_FEEDS if market != "us"}
        assert not bad, f"non-us market rows: {sorted(bad)}"

    def test_language_is_always_en(self):
        bad = {slug for slug, *_, lang in AI_US_FEEDS if lang != "en"}
        assert not bad, f"non-en rows: {sorted(bad)}"


class TestUrls:
    @pytest.mark.parametrize(
        "slug,url",
        [(slug, url) for slug, _, url, *_ in AI_US_FEEDS],
        ids=[slug for slug, *_ in AI_US_FEEDS],
    )
    def test_url_is_http(self, slug, url):
        assert url.startswith(("http://", "https://")), f"{slug}: {url}"


def test_expected_feed_count():
    """38 self-media (9 newsletter + 3 official + 15 podcast + 11 YT)
    + 24 us-models uniques + 37 upstream uniques = 99."""
    assert len(AI_US_FEEDS) == 99
