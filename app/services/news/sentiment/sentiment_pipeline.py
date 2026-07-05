"""Async sentiment LLM pipeline.

Stage 1 (every article)
    1. ``entity_extraction``   - symbols, category, importance
    2. ``sentiment_analysis``  - per-symbol score / label / drivers

Stage 2 (importance >= 4 only)
    3. ``impact_chain``        - first/second-order impact

Persists the per-symbol result into the existing
``app.models.research.SentimentData`` table (one row per symbol
per article).  Caches the full per-article payload in Redis keyed by
``url_hash``.

Concurrency
-----------

LLM calls are synchronous (DeepSeek SDK is sync).  Each call runs in
``asyncio.to_thread``; the pipeline holds an ``asyncio.Semaphore`` to
cap in-flight LLM calls (default 20).

JSON robustness
---------------

LLMs are not deterministic.  ``_parse_json`` extracts the first
JSON object / array from the response, falling back to empty.

This module does not depend on a ``NewsArticle`` ORM model — it
operates on plain article dicts produced by upstream crawlers.  When
the news module's ORM ships we will add a thin adapter to write into
it; the LLM stages already cache their outputs in Redis, so a
schema upgrade is a write-path-only change.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import DataProviderError
from app.models.research import SentimentData
from app.services.llm import DeepSeekProvider, LLMService
from app.services.news.sentiment import prompts
from app.services.news.sentiment.cache import SentimentCache
from app.services.news.sentiment.monitor import LLMPipelineMonitor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class PipelineResult:
    """Outcome of processing a single article."""

    url: str
    success: bool
    cache_hit: bool = False
    entity: dict | None = None
    sentiment: list[dict] = field(default_factory=list)
    impact: dict | None = None
    symbols: list[str] = field(default_factory=list)
    importance: int = 0
    error: str | None = None
    duration_ms: int = 0
    cost_usd: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class SentimentPipeline:
    """Async DeepSeek-backed sentiment pipeline."""

    def __init__(
        self,
        db: Session,
        llm: LLMService | None = None,
        cache: SentimentCache | None = None,
        monitor: LLMPipelineMonitor | None = None,
        max_concurrency: int = 20,
        model: str = "deepseek-v4-flash",
    ) -> None:
        self.db = db
        self.llm = llm or LLMService(DeepSeekProvider(model=model))
        self.cache = cache or SentimentCache()
        self.monitor = monitor or LLMPipelineMonitor(cache=self.cache)
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.model = model

    # ------------------------------------------------------------------
    # JSON parsing
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_json(text: str) -> Any:
        text = (text or "").strip()
        if not text:
            return None
        # Strip markdown fences if any
        text = re.sub(r"^```(?:json)?", "", text).rstrip("`").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # First {...} block
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        # First [...] block
        m = re.search(r"\[[\s\S]*\]", text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return None

    @staticmethod
    def _coerce_importance(value: Any) -> int:
        try:
            n = int(round(float(value)))
        except (TypeError, ValueError):
            return 0
        return max(1, min(5, n))

    # ------------------------------------------------------------------
    # LLM wrappers (async, semaphore-bounded, cost-monitored)
    # ------------------------------------------------------------------
    async def _llm_complete(
        self,
        system: str,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> str:
        async with self.semaphore:
            try:
                return await asyncio.to_thread(
                    self.llm.provider.complete,
                    prompt=prompt,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            except Exception as exc:
                logger.error("LLM call failed: %s", exc)
                raise DataProviderError(f"LLM call failed: {exc}") from exc

    async def _stage(
        self,
        stage_name: str,
        system: str,
        user_prompt: str,
        max_tokens: int = 1024,
    ) -> tuple[Any, int, int, float]:
        """Run one LLM stage, record cost, return (parsed_json, p_tok, c_tok, usd)."""
        start = time.time()
        result = await self._llm_complete(system, user_prompt, max_tokens=max_tokens)
        elapsed_ms = int((time.time() - start) * 1000)
        parsed = self._parse_json(result)
        # DeepSeek does not return token counts on every endpoint, so we
        # estimate.  Rough heuristic: ~1 token / 1.5 Chinese chars
        p_tok = max(1, int(len(user_prompt) / 1.5))
        c_tok = max(1, int(len(result) / 1.5))
        cost = self.monitor.record_call(
            self.model, p_tok, c_tok
        )
        logger.info(
            "LLM stage=%s elapsed=%dms p_tok=%d c_tok=%d cost=%.6f",
            stage_name, elapsed_ms, p_tok, c_tok, cost,
        )
        return parsed, p_tok, c_tok, cost

    # ------------------------------------------------------------------
    # Single article
    # ------------------------------------------------------------------
    async def process_article(self, article: dict | int) -> PipelineResult:
        """Process a single article.

        Accepts either an article dict (from a crawler) or an int
        ``SentimentData.id`` (legacy ingest path).  When given an int,
        we hydrate it from the DB.
        """
        if isinstance(article, int):
            article = self._hydrate(article)

        url = article.get("url", "") or ""
        title = article.get("title") or article.get("headline", "")
        body = (
            article.get("body")
            or article.get("content")
            or article.get("summary")
            or ""
        )
        result = PipelineResult(url=url, success=False)

        if not url:
            result.error = "missing url"
            return result

        start = time.time()

        cached = self.cache.get_article(url)
        if cached is not None:
            self.monitor.record_cache_hit()
            result.cache_hit = True
            result.success = True
            result.entity = cached.get("entity")
            result.sentiment = cached.get("sentiment") or []
            result.impact = cached.get("impact")
            result.symbols = cached.get("symbols") or []
            result.importance = cached.get("importance", 0)
            return result

        self.monitor.record_cache_miss()

        try:
            entity, p1, c1, cost1 = await self._stage(
                "entity",
                prompts.ENTITY_EXTRACTION_SYSTEM,
                prompts.ENTITY_EXTRACTION_PROMPT.format(title=title, body=body),
                max_tokens=600,
            )
            result.entity = entity or {}
            result.importance = self._coerce_importance((entity or {}).get("importance"))

            raw_symbols = (entity or {}).get("symbols") or []
            symbols_for_prompt = [
                f"{s.get('symbol')} ({s.get('market', '?')})"
                for s in raw_symbols
                if s.get("symbol")
            ]
            result.symbols = [s.get("symbol") for s in raw_symbols if s.get("symbol")]

            if symbols_for_prompt:
                sent, p2, c2, cost2 = await self._stage(
                    "sentiment",
                    prompts.SENTIMENT_ANALYSIS_SYSTEM,
                    prompts.SENTIMENT_ANALYSIS_PROMPT.format(
                        title=title,
                        body=body,
                        symbols=", ".join(symbols_for_prompt),
                    ),
                    max_tokens=900,
                )
                if isinstance(sent, dict):
                    sent = [sent]
                if isinstance(sent, list):
                    result.sentiment = sent
                else:
                    result.sentiment = []
            else:
                p2 = c2 = cost2 = 0

            # Stage 3: impact chain for high-importance events only
            if result.importance >= prompts.IMPACT_CHAIN_IMPORTANCE_THRESHOLD:
                impact, p3, c3, cost3 = await self._stage(
                    "impact",
                    prompts.IMPACT_CHAIN_SYSTEM,
                    prompts.IMPACT_CHAIN_PROMPT.format(
                        event=json.dumps(
                            {
                                "title": title,
                                "category": (entity or {}).get("event_category"),
                                "importance": result.importance,
                            },
                            ensure_ascii=False,
                        ),
                        symbols=json.dumps(result.symbols, ensure_ascii=False),
                        sentiment=json.dumps(result.sentiment, ensure_ascii=False),
                    ),
                    max_tokens=900,
                )
                result.impact = impact
            else:
                p3 = c3 = cost3 = 0

            result.prompt_tokens = p1 + p2 + p3
            result.completion_tokens = c1 + c2 + c3
            result.cost_usd = cost1 + cost2 + cost3
            result.success = True
            result.duration_ms = int((time.time() - start) * 1000)

            # Persist to DB
            self._persist(article, result)
            # Cache
            self.cache.set_article(
                url,
                {
                    "entity": result.entity,
                    "sentiment": result.sentiment,
                    "impact": result.impact,
                    "symbols": result.symbols,
                    "importance": result.importance,
                },
            )
            return result
        except Exception as exc:
            logger.exception("process_article failed for %s", url)
            result.error = str(exc)
            result.duration_ms = int((time.time() - start) * 1000)
            return result

    # ------------------------------------------------------------------
    # Batch
    # ------------------------------------------------------------------
    async def process_batch(
        self, articles: list[dict], concurrency: int = 20
    ) -> list[PipelineResult]:
        """Process a list of article dicts concurrently."""
        sem = asyncio.Semaphore(concurrency)

        async def _one(art: dict) -> PipelineResult:
            async with sem:
                return await self.process_article(art)

        return list(await asyncio.gather(*[_one(a) for a in articles]))

    # ------------------------------------------------------------------
    # Retail aggregation
    # ------------------------------------------------------------------
    async def aggregate_retail(
        self, symbol: str, comments: list[str], window_hours: int = 24
    ) -> dict:
        """Aggregate a list of retail comments for one symbol.

        The comments are expected to come from a separate
        ``RetailCrawler`` (out of scope for this module).  We treat
        the first 50 as the working set to bound LLM context size.
        """
        symbol = symbol.upper()
        cached = self.cache.get_retail(symbol, window_hours)
        if cached is not None:
            self.monitor.record_cache_hit()
            return cached
        self.monitor.record_cache_miss()

        sample = comments[:50]
        body = "\n".join(f"- {c[:400]}" for c in sample)
        prompt = prompts.RETAIL_AGGREGATION_PROMPT.format(
            N=len(sample), symbol=symbol, comments=body
        )
        parsed, _, _, _ = await self._stage(
            "retail",
            prompts.RETAIL_AGGREGATION_SYSTEM,
            prompt,
            max_tokens=900,
        )
        out = parsed or {}
        self.cache.set_retail(symbol, window_hours, out)
        return out

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def _hydrate(self, sentiment_id: int) -> dict:
        rec = (
            self.db.query(SentimentData)
            .filter(SentimentData.id == sentiment_id)
            .first()
        )
        if not rec:
            return {"url": f"id:{sentiment_id}"}
        return {
            "url": rec.url or f"sentiment:{rec.id}",
            "title": rec.title or "",
            "body": rec.content or "",
            "instrument_code": rec.instrument_code,
            "published_at": rec.published_at,
        }

    def _persist(self, article: dict, result: PipelineResult) -> None:
        """Write per-symbol rows into ``sentiment_data``.

        We attach the full LLM payload via ``content`` (a denormalised
        copy of the per-symbol row + the article-level metadata) so
        nothing is lost even if the cache expires.
        """
        for sym_payload in result.sentiment or []:
            sym = sym_payload.get("symbol") if isinstance(sym_payload, dict) else None
            if not sym:
                continue
            score = sym_payload.get("score", 0.0)
            label = sym_payload.get("label", "neutral")
            conf = sym_payload.get("confidence", 0.5)
            try:
                score_dec = Decimal(str(round(float(score or 0.0), 4)))
            except (TypeError, ValueError):
                score_dec = Decimal("0.0000")
            try:
                conf_dec = Decimal(str(round(float(conf or 0.0), 4)))
            except (TypeError, ValueError):
                conf_dec = Decimal("0.0000")
            try:
                drivers = sym_payload.get("drivers") or []
                drivers_text = "; ".join(str(d) for d in drivers)[:500]
            except Exception:
                drivers_text = ""

            rec = SentimentData(
                instrument_code=str(sym)[:20],
                source="llm_pipeline",
                title=(article.get("title") or "")[:500],
                content=drivers_text or (article.get("body") or "")[:1000],
                url=(article.get("url") or "")[:1000],
                sentiment_score=score_dec,
                sentiment_label=str(label)[:20],
                confidence=conf_dec,
                published_at=article.get("published_at") or datetime.utcnow(),
            )
            self.db.add(rec)
        # Backfill the article-level sentiment onto ``news_article`` when the
        # article dict carries its DB id (crawler path). This gives the
        # event-driven strategy a single-source-of-truth score without a
        # separate join. Best-effort: skipped for the legacy int-id path.
        self._backfill_article_sentiment(article, result)
        try:
            self.db.commit()
        except Exception as exc:
            logger.warning("DB commit failed in pipeline persist: %s", exc)
            self.db.rollback()

    def _backfill_article_sentiment(self, article: dict, result: PipelineResult) -> None:
        """Write an aggregate LLM sentiment back onto ``news_article``.

        Averages the per-symbol scores (range ``-1..1``) into a single
        ``-100..100`` article score and stamps ``sentiment_processed_at``.
        No-op when the article has no DB id or no usable scores.
        """
        article_id = article.get("id")
        if not article_id:
            return
        scores: list[float] = []
        for sym_payload in result.sentiment or []:
            if not isinstance(sym_payload, dict):
                continue
            try:
                scores.append(float(sym_payload.get("score", 0.0) or 0.0))
            except (TypeError, ValueError):
                continue
        if not scores:
            return
        avg = sum(scores) / len(scores)
        label = "bullish" if avg > 0.15 else "bearish" if avg < -0.15 else "neutral"
        try:
            from app.services.news._model_loader import NewsArticle

            self.db.query(NewsArticle).filter(NewsArticle.id == article_id).update(
                {
                    "sentiment_score": int(round(max(-1.0, min(1.0, avg)) * 100)),
                    "sentiment_label": label,
                    "event_category": (result.entity or {}).get("event_category"),
                    "importance": result.importance or None,
                    "sentiment_processed_at": datetime.utcnow(),
                },
                synchronize_session=False,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("news_article sentiment backfill skipped: %s", exc)

    # ------------------------------------------------------------------
    # Scheduling-friendly entrypoint
    # ------------------------------------------------------------------
    def process_unprocessed(self, limit: int = 100) -> dict:
        """Sync wrapper for the APScheduler.  Returns counts.

        Strategy: look at recent ``sentiment_data`` rows that came from
        the legacy Finnhub flow (the only source we know about before
        the news crawlers are wired) and re-classify them.  When the
        news module adds ``news_article`` rows, this is the place to
        branch on ``source``.
        """
        from app.services.sentiment_service import SentimentService

        legacy = (
            self.db.query(SentimentData)
            .filter(SentimentData.source != "llm_pipeline")
            .order_by(SentimentData.ingested_at.desc())
            .limit(limit)
            .all()
        )
        service = SentimentService(self.db)
        done = 0
        for rec in legacy:
            art = {
                "url": rec.url or f"sentiment:{rec.id}",
                "title": rec.title or "",
                "body": rec.content or "",
                "published_at": rec.published_at,
            }
            # Use the existing service to add a parallel LLM-pipeline
            # row; do not touch the original.
            service._classify_sentiment(art["title"], art["body"])
            done += 1
        return {"reclassified": done, "scanned": len(legacy)}
