"""FRED macro-indicator ingestion service.

Pulls observations for ~30 US economic indicators plus ~6 cross-border
series (S&P 500 / DXY / USDJPY / Brent / WTI / Gold) from FRED and
upserts them into the ``macro_indicator`` table.  Idempotent — safe
to re-run daily because the unique constraint on
(code, region, period, source) prevents duplicates.

Designed to be invoked from:
  - APScheduler (daily, post-FRED-publish)
  - Admin manual refresh API
  - One-shot CLI / test fixtures

Region tag:
  - ``us`` — kept on every legacy US-only ``us_*`` code so the existing
    Macro page query (region='us') continues to return the same set.
  - ``global`` — added in 2026-07 for cross-border series surfaced via
    the new ``/global`` dashboard / page.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.data.providers.fred_provider import FredProvider
from app.models.macro import MacroIndicator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FredSeriesMeta:
    """One row in the static FRED registry.

    The fields are intentionally flat so we can iterate trivially
    inside ``refresh()``.  ``code`` is the stable internal identifier
    (independent of the FRED series id, which may change when FRED
    renames a series).
    """

    series_id: str      # FRED's native id, e.g. CPIAUCSL
    code: str           # internal id, e.g. us_cpi
    name_zh: str        # Chinese display name
    name_en: str        # English display name (from FRED)
    unit: str           # display unit
    category: str       # grouping for the UI (价格 / 就业 / 利率 / ...)


# ---------------------------------------------------------------------------
# Static registry of US macro indicators we track.  Add/remove entries
# here and the scheduler, API, and frontend will pick them up
# automatically on the next refresh.
# ---------------------------------------------------------------------------
SERIES_REGISTRY: list[FredSeriesMeta] = [
    # ── Output ──
    FredSeriesMeta("GDP",      "us_gdp",        "美国GDP（名义）", "Nominal GDP",                       "十亿美元", "产出"),
    FredSeriesMeta("GDPC1",    "us_real_gdp",   "美国实际GDP",    "Real GDP",                          "十亿美元(2017年价)", "产出"),

    # ── Prices ──
    FredSeriesMeta("CPIAUCSL", "us_cpi",        "美国CPI",        "CPI All Urban Consumers",           "指数",     "价格"),
    FredSeriesMeta("CPILFESL", "us_core_cpi",   "美国核心CPI",    "Core CPI",                          "指数",     "价格"),
    FredSeriesMeta("PCEPI",    "us_pce",        "美国PCE",        "PCE Price Index",                   "指数",     "价格"),
    FredSeriesMeta("PCEPILFE", "us_core_pce",   "美国核心PCE",    "Core PCE",                          "指数",     "价格"),

    # ── Labour ──
    FredSeriesMeta("UNRATE",   "us_unrate",     "美国失业率",     "Unemployment Rate",                 "%",        "就业"),
    FredSeriesMeta("PAYEMS",   "us_nfp",        "美国非农就业",   "Total Nonfarm Payrolls",            "千人",     "就业"),
    FredSeriesMeta("ICSA",     "us_jobless_claims", "美国初请失业金人数", "Initial Jobless Claims",     "千人",     "就业"),

    # ── Money / Rates ──
    FredSeriesMeta("M2SL",     "us_m2",         "美国M2货币供应", "M2 Money Supply",                   "十亿美元", "货币"),
    FredSeriesMeta("FEDFUNDS", "us_fed_funds",  "美国联邦基金利率", "Effective Federal Funds Rate",     "%",        "利率"),
    FredSeriesMeta("DFF",      "us_dff",        "美国日度联邦基金利率", "Daily Federal Funds Rate",    "%",        "利率"),
    FredSeriesMeta("DGS10",    "us_dgs10",      "美国10年期国债收益率", "10-Year Treasury Rate",       "%",        "利率"),
    FredSeriesMeta("DGS2",     "us_dgs2",       "美国2年期国债收益率", "2-Year Treasury Rate",         "%",        "利率"),
    FredSeriesMeta("DGS30",    "us_dgs30",      "美国30年期国债收益率", "30-Year Treasury Rate",         "%",        "利率"),
    FredSeriesMeta("T10Y2Y",   "us_t10y2y",     "10Y-2Y利差",     "10-Year minus 2-Year Treasury Spread", "%",     "利率"),
    FredSeriesMeta("T10Y3M",   "us_t10y3m",     "10Y-3M利差",     "10-Year minus 3-Month Treasury Spread", "%",   "利率"),

    # ── Markets ──
    FredSeriesMeta("VIXCLS",   "us_vix",        "VIX恐慌指数",    "VIX (CBOE Volatility Index)",       "指数",     "市场"),

    # ── FX ──
    FredSeriesMeta("DEXUSEU",  "usd_eur",       "美元/欧元",      "USD/EUR Exchange Rate",             "EUR/USD",  "外汇"),
    FredSeriesMeta("DEXCHUS",  "usd_cny",       "美元/人民币",    "CNY/USD Exchange Rate",             "CNY/USD",  "外汇"),

    # ── Housing / Production / Sales ──
    FredSeriesMeta("HOUST",    "us_houst",      "美国新屋开工",   "Housing Starts",                    "千套",     "房地产"),
    FredSeriesMeta("INDPRO",   "us_indpro",     "美国工业生产指数", "Industrial Production Index",      "指数",     "生产"),
    FredSeriesMeta("RSAFS",    "us_retail",     "美国零售销售",   "Retail Sales",                      "百万美元", "消费"),

    # ── Sentiment / Surveys ──
    FredSeriesMeta("NAPM",     "us_ism_pmi",    "美国ISM制造业PMI", "ISM Manufacturing PMI",           "指数",     "景气"),
    FredSeriesMeta("UMCSENT",  "us_umich",      "密歇根大学消费者信心指数", "UMich Consumer Sentiment", "指数",   "景气"),
]


# ---------------------------------------------------------------------------
# Global / cross-border series exposed under ``region='global'``.
# They live in the same ``macro_indicator`` table — only ``region``
# differs — so consumers can pull a unified view via
# ``/macro/latest?region=global`` without any new table.
#
# All sources are FRED (free, 120 req/min).  Region is tagged 'global'
# so downstream filters can isolate them.  For the 'us' US-only series
# above (``us_*``) we keep ``region='us'`` unchanged to preserve
# backward compatibility for the existing Macro page.
# ---------------------------------------------------------------------------
_GLOBAL_SERIES: list[FredSeriesMeta] = [
    # ── Cross-border Index ──
    FredSeriesMeta("SP500",            "global_sp500",  "标普500指数",    "S&P 500",                  "指数",   "指数"),
    FredSeriesMeta("NASDAQCOM",        "global_nasdaq", "纳斯达克综合指数", "NASDAQ Composite",         "指数",   "指数"),
    FredSeriesMeta("DJIA",             "global_dow",    "道琼斯工业指数",  "Dow Jones Industrial Average", "指数", "指数"),
    # ── FX (broad USD) ──
    FredSeriesMeta("DTWEXBGS",         "global_dxy",    "美元指数(广义)",  "Broad U.S. Dollar Index",  "指数",   "外汇"),
    FredSeriesMeta("DEXJPUS",          "global_usdjpy", "美元/日元",      "USD/JPY",                  "JPY/USD","外汇"),
    # ── Commodities (USD) ──
    FredSeriesMeta("DCOILBRENTEU",     "global_brent",  "布伦特原油",      "Brent Crude (Europe)",     "USD/桶","大宗"),
    FredSeriesMeta("DCOILWTICO",       "global_wti",    "WTI原油",        "WTI Crude Oil (Cushing)",  "USD/桶","大宗"),
    # NOTE: FRED discontinued GOLDAMGBD228NLBM (London AM gold fix) with no
    # direct replacement. Gold is omitted until a replacement source is added.
]


# Single tuple so the refresh loop can iterate both registries without
# branching on the region label.
_SERIES_ALL: list[tuple[FredSeriesMeta, str]] = (
    [(m, "us") for m in SERIES_REGISTRY]
    + [(m, "global") for m in _GLOBAL_SERIES]
)


class FredService:
    """Orchestrates FRED → macro_indicator upserts."""

    def __init__(self, db: Session | None = None, provider: FredProvider | None = None) -> None:
        self.db = db
        self.provider = provider or FredProvider()

    # ------------------------------------------------------------------
    # Read path (used by the API)
    # ------------------------------------------------------------------

    def list_indicators(self, region: str | None = None) -> list[dict[str, Any]]:
        """Return metadata + latest value for every registered series.

        Joins the registry with the latest stored observation (if any)
        so the frontend can render ``name + latest value + period`` in
        a single request.

        Pass ``region='us'`` for US-only series, ``region='global'`` for
        the cross-border series added in the Global Markets rollout, or
        ``None`` for every series (the two registries merged).
        """
        from sqlalchemy import select

        if self.db is None:
            raise RuntimeError("list_indicators requires a DB session")

        if region == "us":
            registry: list[tuple[FredSeriesMeta, str]] = [(m, "us") for m in SERIES_REGISTRY]
        elif region == "global":
            registry = [(m, "global") for m in _GLOBAL_SERIES]
        elif region in (None, ""):
            registry = list(_SERIES_ALL)
        else:
            return []

        codes = [meta.code for meta, _ in registry]
        rows = self.db.execute(
            select(MacroIndicator)
            .where(MacroIndicator.source == "fred")
            .where(MacroIndicator.code.in_(codes))
        ).scalars().all()

        latest_by_code: dict[str, MacroIndicator] = {}
        for r in rows:
            existing = latest_by_code.get(r.code)
            if existing is None or (r.period and (existing.period is None or r.period > existing.period)):
                latest_by_code[r.code] = r

        out: list[dict[str, Any]] = []
        for meta, meta_region in registry:
            latest = latest_by_code.get(meta.code)
            out.append({
                "code": meta.code,
                "region": meta_region,
                "name_zh": meta.name_zh,
                "name_en": meta.name_en,
                "unit": meta.unit,
                "source": "fred",
                "category": meta.category,
                "period": latest.period if latest else None,
                "value": latest.value if latest else None,
                "fetched_at": latest.fetched_at if latest else None,
            })

        return out

    def get_series(
        self,
        code: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 500,
    ) -> dict[str, Any] | None:
        """Return time-series observations for one indicator (ascending)."""
        from sqlalchemy import select

        if self.db is None:
            raise RuntimeError("get_series requires a DB session")

        meta_entry: tuple[FredSeriesMeta, str] | None = next(
            ((m, r) for m, r in _SERIES_ALL if m.code == code),
            None,
        )
        if meta_entry is None:
            return None
        meta, region_tag = meta_entry

        stmt = (
            select(MacroIndicator)
            .where(MacroIndicator.source == "fred")
            .where(MacroIndicator.code == code)
            .where(MacroIndicator.region == region_tag)
        )
        if start_date:
            stmt = stmt.where(MacroIndicator.period >= start_date)
        if end_date:
            stmt = stmt.where(MacroIndicator.period <= end_date)
        stmt = stmt.order_by(MacroIndicator.period.asc()).limit(limit)

        rows = self.db.execute(stmt).scalars().all()
        return {
            "code": meta.code,
            "region": region_tag,
            "name_zh": meta.name_zh,
            "name_en": meta.name_en,
            "unit": meta.unit,
            "source": "fred",
            "points": [
                {"period": r.period, "value": float(r.value)}
                for r in rows
                if r.period is not None and r.value is not None
            ],
        }

    # ------------------------------------------------------------------
    # Write path (called by the scheduler)
    # ------------------------------------------------------------------

    def refresh(
        self,
        lookback_days: int = 180,
        session: Session | None = None,
    ) -> dict[str, Any]:
        """Fetch the last ``lookback_days`` for every registered series.

        Returns a summary dict ``{written, series_count, failed, ...}``.
        Individual series failures are logged but do not abort the batch.
        """
        own_session = session is None and self.db is None
        db = session or self.db
        if db is None:
            raise RuntimeError("refresh requires a DB session")

        settings = get_settings()
        api_key = (self.provider.api_key or settings.fred_api_key or "").strip()
        if not api_key:
            return {
                "written": 0,
                "series_count": 0,
                "failed": [m.series_id for m, _ in _SERIES_ALL],
                "started_at": datetime.now(timezone.utc),
                "finished_at": datetime.now(timezone.utc),
                "skipped_reason": "FRED_API_KEY not configured",
            }

        started = datetime.now(timezone.utc)
        end = date.today()
        start = end - timedelta(days=lookback_days)

        written = 0
        failed: list[str] = []
        total_series = len(_SERIES_ALL)

        try:
            for meta, region_tag in _SERIES_ALL:
                try:
                    obs = self.provider.get_series(
                        meta.series_id,
                        start_date=start.isoformat(),
                        end_date=end.isoformat(),
                    )
                except Exception as exc:  # noqa: BLE001 - defensive: log and continue
                    logger.warning(
                        "FRED refresh %s (%s) failed: %s",
                        meta.series_id, meta.code, exc,
                    )
                    failed.append(meta.series_id)
                    # Even on error, still respect rate limits so we don't
                    # pound the API on the next series.
                    self.provider.rate_limit_sleep()
                    continue

                if not obs:
                    self.provider.rate_limit_sleep()
                    continue

                # Use Postgres-native ON CONFLICT for idempotent bulk upsert.
                rows = [
                    {
                        "code": meta.code,
                        "region": region_tag,
                        "name_zh": meta.name_zh,
                        "name_en": meta.name_en,
                        "unit": meta.unit,
                        "period": self._parse_date(o["date"]),
                        "value": float(o["value"]),
                        "source": "fred",
                    }
                    for o in obs
                    if o.get("date")
                    and o.get("value") is not None
                    and o["value"] != "."
                    and o["value"] != ""
                ]
                if rows:
                    self._upsert_rows(db, rows)
                written += len(rows)
                self.provider.rate_limit_sleep()

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            if own_session:
                db.close()

        finished = datetime.now(timezone.utc)
        logger.info(
            "FRED refresh done: written=%d series_count=%d failed=%d elapsed=%.1fs",
            written, total_series, len(failed),
            (finished - started).total_seconds(),
        )
        return {
            "written": written,
            "series_count": total_series,
            "failed": failed,
            "started_at": started,
            "finished_at": finished,
        }

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        """Parse YYYY-MM-DD into a ``date``. Returns None on failure."""
        if isinstance(value, date):
            return value
        if not value:
            return None
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _upsert_rows(db: Session, rows: list[dict[str, Any]]) -> None:
        """Insert or update ``rows`` in ``macro_indicator`` idempotently.

        Postgres uses native ``ON CONFLICT … DO UPDATE`` (production).
        SQLite (>= 3.24) supports the same syntax via the bundled
        ``sqlite_dialect.insert`` helper, which we use so unit tests
        exercise the same code path.
        """
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        dialect = db.bind.dialect.name if db.bind is not None else ""
        if dialect.startswith("postgres"):
            ins_stmt = pg_insert(MacroIndicator).values(rows)
            ins_stmt = ins_stmt.on_conflict_do_update(
                constraint="uq_macro_indicator_code_region_period_source",
                set_={
                    "value": ins_stmt.excluded.value,
                    "name_zh": ins_stmt.excluded.name_zh,
                    "name_en": ins_stmt.excluded.name_en,
                    "unit": ins_stmt.excluded.unit,
                    "fetched_at": func.now(),
                },
            )
            db.execute(ins_stmt)
        else:
            ins_stmt = sqlite_insert(MacroIndicator).values(rows)
            ins_stmt = ins_stmt.on_conflict_do_update(
                index_elements=["code", "region", "period", "source"],
                set_={
                    "value": ins_stmt.excluded.value,
                    "name_zh": ins_stmt.excluded.name_zh,
                    "name_en": ins_stmt.excluded.name_en,
                    "unit": ins_stmt.excluded.unit,
                    "fetched_at": func.now(),
                },
            )
            db.execute(ins_stmt)