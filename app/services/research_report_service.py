"""Research-report service.

Layered on top of :class:`EastMoneyResearchProvider`:

* :meth:`fetch_for_stock` / :meth:`fetch_recent_reports` — ingest raw
  rows from Eastmoney and upsert them into ``research_reports``.
* :meth:`summarize_with_deepseek` — call DeepSeek on a single stored
  report to fill in ``summary``, ``key_points``, ``target_price``.
* :meth:`summarize_pending_reports` — batch the LLM call for the
  scheduled catch-up job.
* Listing/facets/get helpers for the API layer.

The LLM call uses :class:`DeepSeekProvider` (configurable). To keep
costs in check, the prompt truncates the upstream ``title + industry +
rating`` to 300 characters and asks for a 200-character summary plus
3-5 bullet key points.  DeepSeek 429s are retried once after 2s; 5s
timeouts skip the row to avoid blocking the batch.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.cache import cache_get, cache_set
from app.data.providers.eastmoney_research_provider import EastMoneyResearchProvider
from app.models.research_report import ResearchReport

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt + parse helpers
# ---------------------------------------------------------------------------

_SUMMARY_SYSTEM = (
    "你是一名严谨的中文卖方研究员。请用中文回答，结论先行。\n"
    "任务：基于研报元数据（标题、行业、评级、机构）生成 200 字以内的摘要、"
    "3-5 条 bullet 要点，以及一个目标价（若可推断，否则 null）。\n"
    "严格按 JSON 输出，不要带任何多余文字、代码块、注释。"
)

_SUMMARY_USER_TEMPLATE = (
    "研报标题: {title}\n"
    "股票: {name} ({ts_code})\n"
    "行业: {industry}\n"
    "评级: {rating}\n"
    "机构: {org_name}\n"
    "发布日期: {publish_date}\n\n"
    "请输出 JSON:\n"
    "{{\"summary\": \"...\", \"key_points\": [\"...\",\"...\"], \"target_price\": 0.0 | null}}"
)

# Defensive cap: prevent pathological titles from blowing the prompt.
_PROMPT_MAX_CHARS = 300


def _truncate(text: str | None, limit: int = _PROMPT_MAX_CHARS) -> str:
    if not text:
        return ""
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _build_prompt(report: ResearchReport) -> tuple[str, str]:
    title = _truncate(report.title)
    name = _truncate(report.name, limit=64)
    industry = _truncate(report.industry, limit=32)
    rating = _truncate(report.rating, limit=16) if report.rating else "未提供"
    org = _truncate(report.org_name, limit=64)
    pub = (
        report.publish_date.isoformat()
        if report.publish_date
        else "未知"
    )
    user = _SUMMARY_USER_TEMPLATE.format(
        title=title or "未提供",
        name=name or "未提供",
        ts_code=report.ts_code or "未提供",
        industry=industry or "未提供",
        rating=rating,
        org_name=org or "未提供",
        publish_date=pub,
    )
    return _SUMMARY_SYSTEM, user


# Extract the first {...} JSON object from the LLM response.  Many
# small models occasionally wrap the JSON in prose; tolerate that.
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_llm_json(content: str) -> dict[str, Any] | None:
    """Best-effort parse of the LLM response into a structured dict.

    Returns ``None`` if no JSON object can be located or if the payload
    is missing the required ``summary`` field.
    """
    if not content:
        return None
    text = content.strip()
    match = _JSON_OBJECT_RE.search(text)
    candidate = match.group(0) if match else text
    # Some models wrap keys in single quotes; normalise.
    candidate = candidate.replace("'", '"')
    try:
        obj = json.loads(candidate)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    if "summary" not in obj:
        return None
    return obj


def _coerce_key_points(value: Any) -> list[str] | None:
    """Best-effort normalisation of the LLM's ``key_points`` field."""
    if value is None:
        return None
    if isinstance(value, list):
        points = [str(v).strip() for v in value if v is not None and str(v).strip()]
        return points[:5] if points else None
    if isinstance(value, str):
        # split on newlines or semicolons or Chinese commas
        parts = re.split(r"[\n;；，,]+", value)
        points = [p.strip() for p in parts if p.strip()]
        return points[:5] if points else None
    return None


def _coerce_target_price(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if isinstance(value, str):
        m = re.search(r"(\d+(?:\.\d+)?)", value)
        if m:
            try:
                v = float(m.group(1))
                return v if v > 0 else None
            except ValueError:
                return None
    return None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ResearchReportService:
    """Service for research reports."""

    def __init__(self, db: Session, provider: EastMoneyResearchProvider | None = None) -> None:
        self.db = db
        self.provider = provider or EastMoneyResearchProvider()

    # ---- Fetch & upsert -------------------------------------------------

    def fetch_for_stock(self, ts_code: str, days: int = 30) -> int:
        """Fetch recent reports for one stock and upsert them.

        ``ts_code`` accepts either the canonical ``600519.SH`` form or
        the plain A-share code ``600519`` (auto-derived by the
        provider).  ``days`` is enforced on the application side as a
        filter on ``publish_date`` after the upsert, since akshare
        returns the full history of a stock at once.
        """
        symbol = self._ts_to_symbol(ts_code)
        raw_rows = self.provider.fetch_for_stock(symbol)
        if not raw_rows:
            return 0
        # Filter to the requested window — keeps a re-run cheap.
        cutoff = date.today() - timedelta(days=max(days, 1))
        kept = [r for r in raw_rows if r["publish_date"] and r["publish_date"] >= cutoff]
        return self._upsert(kept)

    def fetch_recent_reports(self, limit: int = 200) -> int:
        """Fetch a small batch of recent reports for active A-share stocks.

        Rotates through the active A-share ``etf_info`` list based on
        today's day-of-year so each daily run sees a different subset
        — over time this converges on full coverage.  ``limit`` caps
        the total number of upstream stock lookups per call.
        """
        from app.models.etf import ETFInfo  # local import to avoid cycle

        stocks = (
            self.db.query(ETFInfo)
            .filter(ETFInfo.market == "A股")
            .filter(ETFInfo.instrument_type == "STOCK")
            .filter(ETFInfo.status == "active")
            .order_by(ETFInfo.code)
            .all()
        )
        if not stocks:
            return 0

        codes = [s.code for s in stocks]
        # rotate so each run sees a different window
        offset = date.today().timetuple().tm_yday % max(len(codes), 1)
        rotated = codes[offset:] + codes[:offset]
        target_codes = rotated[: max(limit, 1)]

        plain_codes = [self._ts_to_symbol(c) for c in target_codes]
        raw_rows = self.provider.fetch_for_codes(plain_codes)
        if not raw_rows:
            return 0
        return self._upsert(raw_rows)

    def _upsert(self, records: list[dict[str, Any]]) -> int:
        """Upsert a list of normalized provider rows.

        Skips records that are missing any of the unique-constraint
        columns (ts_code / title / publish_date) so the
        ``ON CONFLICT`` clause is always well-formed.
        """
        if not records:
            return 0

        payload: list[dict[str, Any]] = []
        for r in records:
            ts_code = r.get("ts_code")
            title = r.get("title")
            pub = r.get("publish_date")
            if not (ts_code and title and pub):
                continue
            payload.append(
                {
                    "ts_code": ts_code,
                    "name": r.get("name") or "",
                    "title": title,
                    "org_name": r.get("org_name") or "",
                    "industry": r.get("industry"),
                    "publish_date": pub,
                    "rating": r.get("rating"),
                    "pdf_url": r.get("pdf_url"),
                    "source": "eastmoney",
                    "raw_payload": r.get("raw"),
                }
            )

        if not payload:
            return 0

        # PostgreSQL upsert; SQLite ignores index_elements in the same way.
        stmt = insert(ResearchReport).values(payload)
        excluded = insert(ResearchReport).excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=["ts_code", "title", "publish_date"],
            set_={
                "name": excluded.name,
                "org_name": excluded.org_name,
                "industry": excluded.industry,
                "rating": excluded.rating,
                "pdf_url": excluded.pdf_url,
                "source": excluded.source,
                "raw_payload": excluded.raw_payload,
                "fetched_at": func.now(),
            },
        )
        self.db.execute(stmt)
        self.db.commit()
        return len(payload)

    @staticmethod
    def _ts_to_symbol(ts_code: str) -> str:
        if not ts_code:
            return ""
        return ts_code.split(".", 1)[0]

    # ---- LLM summary ----------------------------------------------------

    def summarize_with_deepseek(self, report_id: int) -> str:
        """Call DeepSeek for one report and persist the result.

        Returns the generated ``summary`` text.  The function is
        idempotent: re-running will overwrite a previous summary.
        """
        from app.services.llm import get_llm_provider

        report = self.db.get(ResearchReport, report_id)
        if report is None:
            raise ValueError(f"ResearchReport {report_id} not found")

        system, user = _build_prompt(report)
        provider = get_llm_provider()

        content = self._call_llm_with_retry(provider, system, user)
        if not content:
            return report.summary or ""

        parsed = _parse_llm_json(content)
        if parsed is None:
            logger.warning(
                "ResearchReport %s: could not parse LLM output, leaving summary untouched",
                report_id,
            )
            return report.summary or ""

        report.summary = str(parsed.get("summary") or "")[:1000]
        report.key_points = _coerce_key_points(parsed.get("key_points"))
        tp = _coerce_target_price(parsed.get("target_price"))
        if tp is not None:
            report.target_price = tp
        self.db.commit()
        return report.summary or ""

    def _call_llm_with_retry(self, provider, system: str, user: str) -> str | None:
        """Single DeepSeek call with one 429-retry after 2s.

        Returns ``None`` if no API key is configured (and we got the
        placeholder message back), if the call times out (>5s), or if
        both attempts fail.
        """
        for attempt in range(2):
            try:
                start = time.monotonic()
                content = provider.chat(
                    messages=[{"role": "user", "content": user}],
                    system=system,
                )
                elapsed = time.monotonic() - start
                if elapsed > 5.0:
                    logger.warning(
                        "ResearchReport LLM call took %.2fs (>5s); skipping", elapsed
                    )
                    return None
                if not content:
                    return None
                # The DeepSeek provider returns the NO_KEY placeholder
                # when the key is missing — treat that as a no-op.
                if "AI 功能未配置" in content or "DEEPSEEK_API_KEY" in content:
                    logger.info("ResearchReport LLM: no API key configured, skipping")
                    return None
                return content
            except Exception as exc:
                msg = str(exc).lower()
                is_429 = "429" in msg or "rate" in msg
                if is_429 and attempt == 0:
                    logger.warning("ResearchReport LLM 429; retrying in 2s")
                    time.sleep(2.0)
                    continue
                logger.warning("ResearchReport LLM call failed: %s", exc)
                return None
        return None

    def summarize_pending_reports(
        self, batch_size: int = 20, max_per_run: int = 100
    ) -> int:
        """Summarize a batch of unsummarized reports.

        Returns the number of rows successfully summarized.  Rows that
        fail (timeout / 429 / no key) are left for the next run.
        """
        from app.services.llm import get_llm_provider

        provider = get_llm_provider()
        if not provider.is_available:
            logger.info("summarize_pending_reports: DeepSeek API key not set, skipping")
            return 0

        rows = (
            self.db.query(ResearchReport)
            .filter(ResearchReport.summary.is_(None))
            .order_by(ResearchReport.publish_date.desc(), ResearchReport.id.asc())
            .limit(batch_size)
            .all()
        )
        if not rows:
            return 0

        summarized = 0
        processed = 0
        for report in rows:
            if processed >= max_per_run:
                break
            processed += 1
            try:
                self.summarize_with_deepseek(report.id)
                if report.summary:
                    summarized += 1
            except Exception as exc:  # defensive — keep batch moving
                logger.warning(
                    "summarize_pending_reports: id=%s failed: %s", report.id, exc
                )
                self.db.rollback()
        return summarized

    # ---- API helpers ----------------------------------------------------

    def list_reports(
        self,
        page: int = 1,
        page_size: int = 20,
        ts_code: str | None = None,
        industry: str | None = None,
        org_name: str | None = None,
        rating: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        has_summary: bool | None = None,
        sort_by: str = "publish_date",
        sort_dir: str = "desc",
    ) -> dict[str, Any]:
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 100:
            page_size = 20
        sort_dir_norm = sort_dir.lower() if sort_dir.lower() in ("asc", "desc") else "desc"

        sortable = {"publish_date", "fetched_at", "updated_at"}
        if sort_by not in sortable:
            sort_by = "publish_date"

        stmt = select(ResearchReport)
        count_stmt = select(func.count(ResearchReport.id))

        if ts_code:
            stmt = stmt.where(ResearchReport.ts_code == ts_code)
            count_stmt = count_stmt.where(ResearchReport.ts_code == ts_code)
        if industry:
            stmt = stmt.where(ResearchReport.industry == industry)
            count_stmt = count_stmt.where(ResearchReport.industry == industry)
        if org_name:
            stmt = stmt.where(ResearchReport.org_name == org_name)
            count_stmt = count_stmt.where(ResearchReport.org_name == org_name)
        if rating:
            stmt = stmt.where(ResearchReport.rating == rating)
            count_stmt = count_stmt.where(ResearchReport.rating == rating)
        if start_date:
            stmt = stmt.where(ResearchReport.publish_date >= start_date)
            count_stmt = count_stmt.where(ResearchReport.publish_date >= start_date)
        if end_date:
            stmt = stmt.where(ResearchReport.publish_date <= end_date)
            count_stmt = count_stmt.where(ResearchReport.publish_date <= end_date)
        if has_summary is True:
            stmt = stmt.where(ResearchReport.summary.isnot(None))
            count_stmt = count_stmt.where(ResearchReport.summary.isnot(None))
        elif has_summary is False:
            stmt = stmt.where(ResearchReport.summary.is_(None))
            count_stmt = count_stmt.where(ResearchReport.summary.is_(None))

        sort_col = getattr(ResearchReport, sort_by)
        stmt = stmt.order_by(
            sort_col.desc() if sort_dir_norm == "desc" else sort_col.asc()
        )

        total = self.db.execute(count_stmt).scalar() or 0
        rows = (
            self.db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
            .scalars()
            .all()
        )
        return {
            "items": [_to_out(r) for r in rows],
            "total": int(total),
            "page": page,
            "page_size": page_size,
        }

    def get_report(self, report_id: int) -> dict[str, Any] | None:
        cache_key = f"research_reports:detail:{report_id}"
        cached = cache_get(cache_key)
        if cached is not None:
            return cached
        row = self.db.get(ResearchReport, report_id)
        if row is None:
            cache_set(cache_key, None, ttl=60)
            return None
        detail = _to_detail(row)
        cache_set(cache_key, detail, ttl=300)
        return detail

    def get_facets(self) -> dict[str, list[str]]:
        cache_key = "research_reports:facets"
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        def _distinct(column) -> list[str]:
            stmt = select(distinct(column)).where(column.isnot(None))
            rows = self.db.execute(stmt).scalars().all()
            return sorted({str(v) for v in rows if v})

        facets = {
            "industries": _distinct(ResearchReport.industry),
            "orgs": _distinct(ResearchReport.org_name),
            "ratings": _distinct(ResearchReport.rating),
        }
        cache_set(cache_key, facets, ttl=3600)
        return facets

    def latest_publish_date(self) -> date | None:
        return self.db.execute(select(func.max(ResearchReport.publish_date))).scalar()


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def _to_out(r: ResearchReport) -> dict[str, Any]:
    return {
        "id": r.id,
        "ts_code": r.ts_code,
        "name": r.name,
        "title": r.title,
        "org_name": r.org_name,
        "industry": r.industry,
        "publish_date": r.publish_date.isoformat() if r.publish_date else None,
        "rating": r.rating,
        "pdf_url": r.pdf_url,
        "summary": r.summary,
        "key_points": r.key_points,
        "target_price": float(r.target_price) if r.target_price is not None else None,
        "current_price_at_publish": (
            float(r.current_price_at_publish)
            if r.current_price_at_publish is not None
            else None
        ),
        "source": r.source,
        "fetched_at": _iso(r.fetched_at),
        "updated_at": _iso(r.updated_at),
    }


def _to_detail(r: ResearchReport) -> dict[str, Any]:
    payload = _to_out(r)
    payload["raw_payload"] = r.raw_payload
    payload["created_at"] = _iso(r.created_at)
    return payload


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
