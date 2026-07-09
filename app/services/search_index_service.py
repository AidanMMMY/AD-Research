"""Search-index ingestion service.

Pulls daily search-index observations for a curated list of A-share-related
keywords (indices, stocks, macro topics) and persists them into the
``search_trends`` table.

Both the **baidu** and **google** slots are now sourced from Xueqiu's
public hot-rank endpoints (the real Baidu/Google upstreams are
unreachable from the ECS IP — Baidu blocks our datacenter ASN, and
Google Trends returns 429 after the first request):

* **baidu slot** → ``akshare.stock_hot_follow_xq`` (雪球关注排行榜)
  — 5,000+ A-share hot-follow ranked stocks.
* **google slot** → ``akshare.stock_hot_deal_xq`` (雪球分享交易排行榜)
  — 5,000+ A-share hot-deal ranked stocks.

Each row's rank is mapped to a search-index proxy
``value = max(0, 10000 - rank)`` so rank #1 → 9999 and a rank outside
the top 10,000 → 0. The keyword registry in
``app/data/static/search_keywords.json`` is matched against the
``股票简称`` (stock short name) column with case-sensitive substring
matching, which works for the curated A-share names.

The keyword registry exposes ``baidu_index`` and ``google_trends`` keys
but the pipeline historically referred to ``baidu`` / ``google`` — the
``_SOURCE_ALIASES`` map accepts both spellings so old callers (and the
one-off backfill script) continue to work.

Both Xueqiu fetchers share an in-process cache (one HTTP call per slot
per pipeline run) and retry 3x with exponential backoff so a transient
flake never blanks out the daily refresh.
"""

import json
import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Keyword registry
# ---------------------------------------------------------------------------

_STATIC_DIR = Path(__file__).resolve().parent.parent / "data" / "static"
_KEYWORDS_PATH = _STATIC_DIR / "search_keywords.json"

# Map the short slot name used by the pipeline ("baidu"/"google") to the
# registry keys it should consult.  ``baidu_index`` and ``google_trends``
# are the canonical keys in ``search_keywords.json``; the short aliases
# exist for backwards compatibility with older callers.
_SOURCE_ALIASES: dict[str, tuple[str, ...]] = {
    "baidu": ("baidu", "baidu_index"),
    "google": ("google", "google_trends"),
    "baidu_index": ("baidu_index",),
    "google_trends": ("google_trends",),
}


def load_keyword_registry() -> dict[str, dict[str, list[str]]]:
    """Return the keyword registry from disk.

    Returns an empty dict when the file is missing or malformed — the
    pipeline should treat an empty registry as a no-op rather than an
    error.
    """
    if not _KEYWORDS_PATH.exists():
        logger.warning("search_keywords.json missing at %s", _KEYWORDS_PATH)
        return {}
    try:
        with _KEYWORDS_PATH.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("search_keywords.json read failed: %s", exc)
        return {}


def flatten_keywords(
    registry: dict[str, dict[str, list[str]]],
    source: str,
) -> list[tuple[str, str, str]]:
    """Flatten registry entries for ``source`` into ``[(keyword, category, source), ...]``.

    Accepts both short (``baidu`` / ``google``) and canonical
    (``baidu_index`` / ``google_trends``) registry keys so old
    callers keep working.
    """
    aliases = _SOURCE_ALIASES.get(source, (source,))
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for alias in aliases:
        section = registry.get(alias) or {}
        for category in ("indices", "stocks", "macro"):
            for kw in section.get(category) or []:
                if isinstance(kw, str) and kw.strip() and kw not in seen:
                    seen.add(kw)
                    out.append((kw.strip(), category, source))
    return out


# ---------------------------------------------------------------------------
# Xueqiu in-process cache
# ---------------------------------------------------------------------------


# Module-level cache so the Xueqiu API is hit once per pipeline run, not
# once per keyword.  ``follow`` and ``deal`` slots each have their own
# slot.  ``ts`` is the unix-time of the last successful fetch; we
# re-fetch after ``_CACHE_TTL_SECONDS`` to keep the daily snapshot fresh
# across long-lived workers.
_XQ_FOLLOW_CACHE: dict[str, Any] = {"data": None, "ts": 0.0}
_XQ_DEAL_CACHE: dict[str, Any] = {"data": None, "ts": 0.0}
_CACHE_TTL_SECONDS = 6 * 3600

# Retry policy: 3 attempts with exponential backoff.  Xueqiu is generally
# fast (~1-2s) so the cumulative cap is ~8s; we never want a single
# transient flake to blank out the daily refresh.
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF = (1.5, 3.0, 6.0)


def _fetch_xueqiu_df(slot: str) -> Any:
    """Fetch a Xueqiu hot-rank DataFrame once per pipeline run per slot.

    ``slot`` is either ``"follow"`` (``ak.stock_hot_follow_xq``) or
    ``"deal"`` (``ak.stock_hot_deal_xq``).  Returns ``None`` if
    akshare is missing or every retry fails — callers degrade to a
    zero-valued row.
    """
    if slot not in ("follow", "deal"):
        raise ValueError(f"unknown xueqiu slot: {slot!r}")

    cache = _XQ_FOLLOW_CACHE if slot == "follow" else _XQ_DEAL_CACHE
    now = time.time()
    if cache["data"] is not None and (now - cache["ts"]) < _CACHE_TTL_SECONDS:
        return cache["data"]

    try:
        import akshare as ak  # type: ignore
    except ImportError:
        logger.warning("akshare not installed; _fetch_xueqiu_df(%s) returns None", slot)
        return None

    fn = ak.stock_hot_follow_xq if slot == "follow" else ak.stock_hot_deal_xq

    last_exc: Exception | None = None
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            df = fn(symbol="最热门")
            if df is None or getattr(df, "empty", True):
                raise RuntimeError(f"xq slot={slot} returned empty dataframe")
            cache["data"] = df
            cache["ts"] = now
            return df
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "xq slot=%s attempt %d failed: %s", slot, attempt, exc
            )
            if attempt < _RETRY_ATTEMPTS:
                time.sleep(_RETRY_BACKOFF[attempt - 1])

    logger.warning("xq slot=%s exhausted retries; last error: %s", slot, last_exc)
    return None


def _match_keyword(df: Any, keyword: str) -> dict[str, Any] | None:
    """Find the first row in ``df`` whose name contains ``keyword``.

    Returns ``{rank, code, name, follow}`` (1-based rank) or ``None``
    if the keyword isn't in the top-N ranking.  Match is a case-sensitive
    substring search on the ``股票简称`` (stock short name) column,
    which is exactly the format used in ``search_keywords.json``.
    """
    if df is None or getattr(df, "empty", True):
        return None

    # Normalise column names — akshare exposes Chinese keys but downstream
    # callers sometimes rename to ascii, so check both.
    name_col = "股票简称" if "股票简称" in df.columns else (
        "name" if "name" in df.columns else None
    )
    code_col = "股票代码" if "股票代码" in df.columns else (
        "code" if "code" in df.columns else None
    )
    follow_col = "关注" if "关注" in df.columns else (
        "follow" if "follow" in df.columns else None
    )
    if name_col is None:
        return None

    try:
        records = df.replace({float("nan"): None}).to_dict("records")
    except Exception as exc:
        logger.warning("xq match: dataframe → records failed: %s", exc)
        return None

    for idx, row in enumerate(records, start=1):
        name = row.get(name_col)
        if not isinstance(name, str) or keyword not in name:
            continue
        follow_val = row.get(follow_col) if follow_col else None
        try:
            follow_int = int(float(follow_val)) if follow_val is not None else None
        except (TypeError, ValueError):
            follow_int = None
        code_val = row.get(code_col) if code_col else None
        return {
            "rank": idx,
            "code": code_val,
            "name": name,
            "follow": follow_int,
        }
    return None


# ---------------------------------------------------------------------------
# Baidu slot → Xueqiu hot-follow
# ---------------------------------------------------------------------------


def fetch_baidu_index(
    keyword: str,
    days: int = 30,
    *,
    region: str = "CN",
) -> list[dict[str, Any]]:
    """Return ``[{trade_date, value, is_partial, ...}]`` for ``keyword``.

    Backed by ``ak.stock_hot_follow_xq`` (雪球关注排行榜) since the real
    Baidu 指数 upstream is blocked from the ECS IP.  The hot-follow
    rank is mapped to a search-index proxy
    ``value = max(0, 10000 - rank)`` so the top-ranked stock scores
    9999 and anything below rank 10,000 scores 0.

    The ``days`` argument is preserved for backwards compatibility
    (other callers pass it) but ignored — Xueqiu only exposes the
    current snapshot, so the pipeline records a single observation per
    keyword per day.  When the keyword isn't in today's ranking we
    still emit a zero-valued row so the daily series stays continuous.
    """
    if days < 1 or days > 365:
        days = 30

    df = _fetch_xueqiu_df("follow")
    today = date.today()
    is_partial = True  # intraday snapshot

    matched = _match_keyword(df, keyword)
    if matched is None:
        out: list[dict[str, Any]] = [
            {
                "trade_date": today,
                "value": 0,
                "is_partial": is_partial,
                "rank": None,
                "follow_count": None,
                "region": region,
            }
        ]
        return out

    value = max(0, 10000 - int(matched["rank"]))
    out = [
        {
            "trade_date": today,
            "value": int(value),
            "is_partial": is_partial,
            "rank": int(matched["rank"]),
            "follow_count": matched.get("follow"),
            "region": region,
        }
    ]
    return out


# ---------------------------------------------------------------------------
# Google slot → Xueqiu hot-deal
# ---------------------------------------------------------------------------


def fetch_google_trends(
    keyword: str,
    days: int = 30,
    *,
    region: str = "GLOBAL",
) -> list[dict[str, Any]]:
    """Return ``[{trade_date, value, is_partial, ...}]`` for ``keyword``.

    Backed by ``ak.stock_hot_deal_xq`` (雪球分享交易排行榜) since the
    real Google Trends / pytrends upstream returns 429 from the ECS IP.
    Rank is mapped to ``value = max(0, 10000 - rank)`` to keep the
    scale consistent with the baidu slot.

    The ``days`` argument is preserved for backwards compatibility but
    ignored — Xueqiu only exposes the current snapshot, so a single
    observation per keyword per day is recorded.
    """
    if days < 1 or days > 365:
        days = 30

    df = _fetch_xueqiu_df("deal")
    today = date.today()
    is_partial = True

    matched = _match_keyword(df, keyword)
    if matched is None:
        out: list[dict[str, Any]] = [
            {
                "trade_date": today,
                "value": 0,
                "is_partial": is_partial,
                "rank": None,
                "follow_count": None,
                "region": region,
            }
        ]
        return out

    value = max(0, 10000 - int(matched["rank"]))
    out = [
        {
            "trade_date": today,
            "value": int(value),
            "is_partial": is_partial,
            "rank": int(matched["rank"]),
            "follow_count": matched.get("follow"),
            "region": region,
        }
    ]
    return out


# ---------------------------------------------------------------------------
# Combined refresh helper
# ---------------------------------------------------------------------------


def refresh_all(
    *,
    daily_limit_per_source: int = 50,
    days: int = 30,
) -> dict[str, Any]:
    """Fetch one observation per keyword for every configured source.

    Xueqiu is fast (~1-2s per slot) so we can comfortably cover the
    full registry in a single run.  ``daily_limit_per_source`` is kept
    as a cap so a runaway registry can't blow out memory.
    """
    registry = load_keyword_registry()
    started = datetime.now(timezone.utc)

    rows_by_source: dict[str, list[dict[str, Any]]] = {"baidu": [], "google": []}

    for source in ("baidu", "google"):
        keywords = flatten_keywords(registry, source)
        if not keywords:
            continue
        keywords = keywords[: max(1, int(daily_limit_per_source))]

        for kw, category, src in keywords:
            try:
                if src == "baidu":
                    fetched = fetch_baidu_index(kw, days=days)
                    region = "CN"
                else:
                    fetched = fetch_google_trends(kw, days=days)
                    region = "GLOBAL"
            except Exception as exc:
                logger.warning("refresh_all %s %s failed: %s", src, kw, exc)
                continue

            for entry in fetched:
                rows_by_source[src].append(
                    {
                        "keyword": kw,
                        "category": category,
                        "region": region,
                        "source": src,
                        "trade_date": entry.get("trade_date") or date.today(),
                        "value": int(entry.get("value") or 0),
                        "is_partial": bool(entry.get("is_partial", False)),
                    }
                )

    finished = datetime.now(timezone.utc)
    return {
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "baidu_rows": len(rows_by_source["baidu"]),
        "google_rows": len(rows_by_source["google"]),
        "rows": rows_by_source,
    }


def today_partial_keywords(registry: dict[str, dict[str, list[str]]]) -> dict[str, list[str]]:
    """Return the day's slice of keywords per source.

    Sized at 50 (effectively "all keywords" given the registry's
    footprint of ~10 baidu + ~14 google entries) so the daily refresh
    covers the full registry in a single run — Xueqiu is cheap enough
    that we don't need to rotate across days.

    Returned dict is ``{source: [keyword, ...]}`` so the pipeline can
    decide which sources are still active without consulting the full
    registry every run.
    """
    slice_size = 50
    out: dict[str, list[str]] = {}
    today_index = date.today().toordinal() % max(1, slice_size)
    for source in ("baidu", "google"):
        flat = [kw for (kw, _cat, _src) in flatten_keywords(registry, source)]
        if not flat:
            continue
        n = len(flat)
        start = today_index % n if n else 0
        rotated = flat[start:] + flat[:start]
        out[source] = rotated[:slice_size]
    return out