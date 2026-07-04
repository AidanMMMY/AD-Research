"""Unit tests for the sentiment LLM pipeline.

All LLM calls are mocked.  Redis is replaced with a small in-memory
shim (see :mod:`app.tests.news.conftest`).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from decimal import Decimal

import pytest

from app.services.news.sentiment import (
    LLMPipelineMonitor,
    SentimentCache,
    SentimentPipeline,
    prompts,
)
from app.services.news.sentiment.sentiment_pipeline import PipelineResult


# ---------------------------------------------------------------------------
# Stub LLM service
# ---------------------------------------------------------------------------


class StubProvider:
    """Fake ``LLMProvider`` that returns canned responses per stage."""

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[dict] = []
        self.is_available = True

    def complete(self, prompt, system=None, max_tokens=1024, temperature=0.7):
        self.calls.append(
            {"prompt": prompt, "system": system, "max_tokens": max_tokens}
        )
        if "实体" in prompt or "extract" in prompt.lower() or "提取关键信息" in prompt:
            return self.responses.get(
                "entity",
                json.dumps(
                    {
                        "symbols": [
                            {"symbol": "AAPL", "market": "us", "confidence": 0.95}
                        ],
                        "event_category": "earnings",
                        "importance": 5,
                        "reasoning": "earnings beat",
                    },
                    ensure_ascii=False,
                ),
            )
        if "影响链" in prompt or "impact" in prompt.lower():
            return self.responses.get(
                "impact",
                json.dumps(
                    {
                        "first_order": [
                            {"target": "AAPL", "impact": "正面", "reason": "beat"}
                        ],
                        "second_order": [],
                        "time_dimension": {
                            "intraday": "+3%",
                            "1_week": "+5%",
                            "1_month": "neutral",
                            "1_year": "+10%",
                        },
                        "counter_argument": "guidance cautious",
                        "uncertainty": "macro",
                    },
                    ensure_ascii=False,
                ),
            )
        if "散户" in prompt or "retail" in prompt.lower():
            return self.responses.get(
                "retail",
                json.dumps(
                    {
                        "overall_sentiment": 0.4,
                        "bull_bear_ratio": {"bull": 65, "bear": 35},
                        "main_themes": [],
                        "controversy_level": 0.3,
                        "manipulation_signals": {
                            "coordinated_accounts": False,
                            "sudden_consensus": False,
                            "evidence": "",
                        },
                        "vs_smart_money": "aligned",
                        "summary": "mildly bullish",
                    },
                    ensure_ascii=False,
                ),
            )
        # Default: sentiment
        return self.responses.get(
            "sentiment",
            json.dumps(
                [
                    {
                        "symbol": "AAPL",
                        "score": 0.7,
                        "label": "positive",
                        "confidence": 0.9,
                        "drivers": ["beat", "guidance"],
                        "time_horizon": "short_term",
                        "reasoning": "strong quarter",
                    }
                ],
                ensure_ascii=False,
            ),
        )

    def chat(self, messages, system=None, max_tokens=1024, temperature=0.7):
        return self.complete(messages[-1]["content"], system, max_tokens, temperature)

    def check_health(self) -> bool:
        return True


def _make_pipeline(db_session, fake_redis, responses=None, model="deepseek-v4-flash"):
    """Build a pipeline wired to a stub provider."""
    from app.services.llm import LLMService

    provider = StubProvider(responses=responses)
    llm = LLMService(provider)  # type: ignore[arg-type]
    cache = SentimentCache(redis_client=fake_redis)
    monitor = LLMPipelineMonitor(cache=cache)
    return SentimentPipeline(
        db=db_session,
        llm=llm,
        cache=cache,
        monitor=monitor,
        model=model,
        max_concurrency=4,
    )


# ---------------------------------------------------------------------------
# 1. Prompt templates
# ---------------------------------------------------------------------------


def test_entity_extraction_prompt_substitutes_title_and_body():
    out = prompts.ENTITY_EXTRACTION_PROMPT.format(
        title="My title", body="My body content"
    )
    assert "My title" in out
    assert "My body content" in out
    assert "importance" in out


def test_sentiment_prompt_includes_symbols():
    out = prompts.SENTIMENT_ANALYSIS_PROMPT.format(
        title="t", body="b", symbols="AAPL (us), 600519.SH (cn_a)"
    )
    assert "AAPL" in out
    assert "600519.SH" in out


def test_impact_prompt_substitutes_event_symbols_sentiment():
    out = prompts.IMPACT_CHAIN_PROMPT.format(
        event='{"title":"x"}', symbols='["AAPL"]', sentiment='[{"score":0.5}]'
    )
    assert "first_order" in out
    assert "AAPL" in out


def test_retail_aggregation_prompt_handles_many_comments():
    out = prompts.RETAIL_AGGREGATION_PROMPT.format(
        N=3, symbol="AAPL", comments="- one\n- two\n- three"
    )
    assert "AAPL" in out
    assert "one" in out and "two" in out


# ---------------------------------------------------------------------------
# 2. JSON parsing
# ---------------------------------------------------------------------------


def test_parse_json_handles_fenced_block():
    text = "```json\n{\"a\": 1}\n```"
    assert SentimentPipeline._parse_json(text) == {"a": 1}


def test_parse_json_handles_embedded_object():
    text = "Here you go: {\"x\": 2} - hope that helps"
    assert SentimentPipeline._parse_json(text) == {"x": 2}


def test_parse_json_handles_array():
    text = '[{"a": 1}, {"b": 2}]'
    parsed = SentimentPipeline._parse_json(text)
    assert isinstance(parsed, list) and len(parsed) == 2


def test_parse_json_returns_none_on_garbage():
    assert SentimentPipeline._parse_json("not json at all") is None


def test_coerce_importance_clamps():
    assert SentimentPipeline._coerce_importance(0) == 1
    assert SentimentPipeline._coerce_importance(7) == 5
    assert SentimentPipeline._coerce_importance(3.4) == 3
    assert SentimentPipeline._coerce_importance("bad") == 0


# ---------------------------------------------------------------------------
# 3. End-to-end pipeline (mocked LLM)
# ---------------------------------------------------------------------------


def _article(url: str = "https://example.com/a", title: str = "AAPL beats Q3") -> dict:
    return {
        "url": url,
        "title": title,
        "body": "AAPL reported strong Q3 earnings, beating expectations by 5%.",
        "published_at": datetime(2026, 7, 1, 10, 0),
    }


def test_process_article_happy_path_writes_db_and_cache(db_session, fake_redis):
    pipe = _make_pipeline(db_session, fake_redis)
    res = asyncio.run(pipe.process_article(_article()))

    assert isinstance(res, PipelineResult)
    assert res.success is True
    assert res.cache_hit is False
    assert res.importance == 5
    assert res.symbols == ["AAPL"]
    assert res.impact is not None  # importance >= 4 -> impact run
    assert res.cost_usd > 0

    # DB row inserted
    from app.models.research import SentimentData

    rows = db_session.query(SentimentData).filter_by(source="llm_pipeline").all()
    assert len(rows) == 1
    assert rows[0].sentiment_label == "positive"

    # Cache populated
    cached = pipe.cache.get_article("https://example.com/a")
    assert cached is not None
    assert cached["importance"] == 5


def test_process_article_cache_hit_skips_llm(db_session, fake_redis):
    pipe = _make_pipeline(db_session, fake_redis)
    a = _article()

    res1 = asyncio.run(pipe.process_article(a))
    calls_after_first = len(pipe.llm.provider.calls)

    res2 = asyncio.run(pipe.process_article(a))
    assert res2.cache_hit is True
    assert res2.success is True
    # No new LLM calls on the second run
    assert len(pipe.llm.provider.calls) == calls_after_first
    # Cache hit recorded
    assert pipe.cache.daily_summary()["cache_hits"] >= 1


def test_process_article_low_importance_skips_impact_chain(db_session, fake_redis):
    pipe = _make_pipeline(
        db_session,
        fake_redis,
        responses={
            "entity": json.dumps(
                {
                    "symbols": [{"symbol": "TSLA", "market": "us", "confidence": 0.6}],
                    "event_category": "rumor",
                    "importance": 2,
                    "reasoning": "speculation",
                },
                ensure_ascii=False,
            )
        },
    )
    res = asyncio.run(pipe.process_article(_article(url="https://x.com/2")))
    assert res.importance == 2
    assert res.impact is None  # never invoked


def test_process_article_handles_missing_url(db_session, fake_redis):
    pipe = _make_pipeline(db_session, fake_redis)
    res = asyncio.run(pipe.process_article({"url": "", "title": "x", "body": "y"}))
    assert res.success is False
    assert res.error == "missing url"


def test_process_batch_runs_concurrently(db_session, fake_redis):
    pipe = _make_pipeline(db_session, fake_redis)
    articles = [
        _article(url=f"https://x.com/{i}", title=f"item {i}") for i in range(5)
    ]
    results = asyncio.run(pipe.process_batch(articles, concurrency=3))
    assert len(results) == 5
    assert sum(1 for r in results if r.success) >= 4


# ---------------------------------------------------------------------------
# 4. Retail aggregation
# ---------------------------------------------------------------------------


def test_aggregate_retail_uses_cache(db_session, fake_redis):
    pipe = _make_pipeline(db_session, fake_redis)
    comments = ["bullish", "bearish", "sideways"]
    out1 = asyncio.run(pipe.aggregate_retail("AAPL", comments))
    assert out1["overall_sentiment"] == 0.4

    # Second call -> cache hit, no new LLM invocations
    calls_before = len(pipe.llm.provider.calls)
    out2 = asyncio.run(pipe.aggregate_retail("AAPL", comments))
    assert out2 == out1
    assert len(pipe.llm.provider.calls) == calls_before


# ---------------------------------------------------------------------------
# 5. Monitor / cost
# ---------------------------------------------------------------------------


def test_monitor_records_calls_and_cost(fake_redis):
    cache = SentimentCache(redis_client=fake_redis)
    mon = LLMPipelineMonitor(cache=cache)
    from datetime import date

    today = date(2026, 7, 1)
    usd = mon.record_call("deepseek-v4-flash", prompt_tokens=1000, completion_tokens=500, day=today)
    # (1000/1000)*0.00007 + (500/1000)*0.00028 = 0.00007 + 0.00014 = 0.00021
    assert round(usd, 6) == 0.00021

    mon.record_cache_hit(today)
    mon.record_cache_miss(today)
    snap = mon.daily_summary(today)
    assert snap["total_calls"] == 1
    assert snap["by_model"]["deepseek-v4-flash"]["prompt_tokens"] == 1000
    assert snap["by_model"]["deepseek-v4-flash"]["completion_tokens"] == 500
    assert snap["cache_hits"] == 1
    assert snap["cache_misses"] == 1
    assert snap["cache_hit_rate"] == 0.5


def test_monitor_flush_to_db_creates_table(db_session, fake_redis, monkeypatch):
    # Override SessionLocal to use our in-memory session
    from app.core import database as db_mod

    monkeypatch.setattr(db_mod, "SessionLocal", lambda: db_session)

    cache = SentimentCache(redis_client=fake_redis)
    mon = LLMPipelineMonitor(cache=cache)
    from datetime import date

    today = date(2026, 7, 1)
    mon.record_call("deepseek-v4-flash", 200, 100, day=today)
    snap = mon.flush_to_db(day=today)
    assert snap["total_calls"] == 1
    # table should exist now (portable DDL was applied)
    rows = db_session.execute(
        __import__("sqlalchemy").text("SELECT day, total_calls FROM llm_usage_daily")
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][1] == 1
    assert rows[0][0] == "2026-07-01"


# ---------------------------------------------------------------------------
# 6. Scheduler-side bridging (no actual scheduler tick)
# ---------------------------------------------------------------------------


def test_process_unprocessed_counts_legacy_rows(db_session, fake_redis):
    from app.models.research import SentimentData

    db_session.add(
        SentimentData(
            instrument_code="AAPL",
            source="finnhub_news",
            title="x",
            content="y",
            url="https://x.com/legacy1",
        )
    )
    db_session.commit()

    pipe = _make_pipeline(db_session, fake_redis)
    out = pipe.process_unprocessed(limit=10)
    assert out["scanned"] == 1
    assert out["reclassified"] == 1
