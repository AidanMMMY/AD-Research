"""Search-index (百度 + Google Trends) ingestion service.

Pulls daily search-index observations for a curated set of A-share-related
keywords (indices, stocks, macro topics) and persists them into the
``search_trends`` table.

Two upstreams are supported:

* **百度指数** (Baidu) via ``akshare.stock_hot_search_baidu`` — returns
  the live A-share hot-search ranking; we map it to a search-index proxy
  (rank → score = 10000 - rank).
* **Google Trends** via ``pytrends`` (the unofficial `pytrends`
  package).  pytrends rate-limits aggressively, so each call sleeps
  60 seconds before the next request; failures are caught + logged so
  a single bad keyword never aborts the batch.

If a source is unavailable (akshare/pytrends not installed, network
blocked, etc.) the helpers degrade gracefully and return empty lists
— the daily refresh must remain best-effort.
"""

import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Keyword registry
# ---------------------------------------------------------------------------

_STATIC_DIR = Path(__file__).resolve().parent.parent / "data" / "static"
_KEYWORDS_PATH = _STATIC_DIR / "search_keywords.json"


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
    """Flatten ``registry[source]`` into ``[(keyword, category, source), ...]``."""
    out: list[tuple[str, str, str]] = []
    section = registry.get(source) or {}
    for category in ("indices", "stocks", "macro"):
        for kw in section.get(category) or []:
            if isinstance(kw, str) and kw.strip():
                out.append((kw.strip(), category, source))
    return out


# ---------------------------------------------------------------------------
# Baidu (akshare)
# ---------------------------------------------------------------------------


def fetch_baidu_index(
    keyword: str,
    days: int = 30,
    *,
    region: str = "CN",
) -> list[dict[str, Any]]:
    """Return ``[{trade_date, value, is_partial}]`` for ``keyword``.

    Implementation: akshare does not expose a per-keyword historical
    Baidu 指数 endpoint, so we use the **Baidu hot-search ranking**
    (``stock_hot_search_baidu``) as a *proxy* for daily search
    intensity.  Each entry's rank is mapped to a synthetic index
    ``value = max(0, 10000 - rank)`` so higher rank = higher value.

    The proxy is intentionally approximate — the UI surfaces a
    "数据仅供参考，非精确值" disclaimer.
    """
    if days < 1 or days > 365:
        days = 30
    try:
        import akshare as ak  # type: ignore
    except ImportError:
        logger.warning("akshare not installed; fetch_baidu_index returns empty")
        return []

    # Best-effort: pull the live ranking.  We cannot map a single
    # keyword to a date window here, so the trade_date is "today" and
    # is_partial=True unless ``days`` resolves to a single observation.
    try:
        df = ak.stock_hot_search_baidu()  # type: ignore[attr-defined]
    except Exception as exc:
        logger.warning("ak.stock_hot_search_baidu failed for %s: %s", keyword, exc)
        return []

    if df is None or getattr(df, "empty", True):
        return []

    # The function returns a global ranking.  We filter rows whose
    # name / keyword column contains the target substring (case-insensitive).
    try:
        records = df.replace({float("nan"): None}).to_dict("records")
    except Exception as exc:
        logger.warning("baidu_index: dataframe → records failed: %s", exc)
        return []

    today = date.today()
    is_partial = True  # always mid-day unless proven otherwise
    out: list[dict[str, Any]] = []

    # Build a normalised text-search column once.
    def _matches(row: dict[str, Any]) -> bool:
        for col in ("名称", "name", "keyword", "word", "热搜词"):
            v = row.get(col)
            if isinstance(v, str) and keyword in v:
                return True
        return False

    for row in records:
        if not _matches(row):
            continue
        rank = row.get("排名") or row.get("rank") or row.get("排序")
        try:
            rank_int = int(rank) if rank is not None else None
        except (TypeError, ValueError):
            rank_int = None
        if rank_int is None:
            continue
        value = max(0, 10000 - rank_int)
        out.append(
            {
                "trade_date": today,
                "value": int(value),
                "is_partial": is_partial,
                "rank": rank_int,
                "region": region,
            }
        )
        break  # one observation per keyword per day

    if not out:
        # Keyword not in today's hot ranking → still record a 0 so
        # the daily refresh has a continuous series.
        out.append(
            {
                "trade_date": today,
                "value": 0,
                "is_partial": is_partial,
                "rank": None,
                "region": region,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Google Trends (pytrends)
# ---------------------------------------------------------------------------


def fetch_google_trends(
    keyword: str,
    days: int = 30,
    *,
    region: str = "GLOBAL",
) -> list[dict[str, Any]]:
    """Return ``[{trade_date, value}]`` for ``keyword`` from Google Trends.

    Uses ``pytrends.request.TrendReq`` to query the daily interest-over-time
    series for the past ``days`` days.  Sleeps 60 seconds before and after
    each call to stay below Google's rate limits.

    Failures (network / rate-limit / pytrends not installed) return
    ``[]`` — callers must treat Google as best-effort.
    """
    if days < 1 or days > 365:
        days = 30

    try:
        from pytrends.request import TrendReq  # type: ignore
    except ImportError:
        logger.warning("pytrends not installed; fetch_google_trends returns empty")
        return []

    timeframe = f"today {min(days, 90)}-d"  # Google caps at 90 days
    sleep_seconds = 60.0  # required cadence between pytrends calls

    try:
        time.sleep(sleep_seconds)
        pt = TrendReq(hl="en-US", tz=0, retries=2, backoff_factor=1.5)
        pt.build_payload([keyword], cat=0, timeframe=timeframe, geo="", gprop="")
        df = pt.interest_over_time()
    except Exception as exc:
        logger.warning("pytrends.fetch_google_trends(%s) failed: %s", keyword, exc)
        return []

    out: list[dict[str, Any]] = []
    if df is None or getattr(df, "empty", True):
        # pytrends returned no data — emit a single zero observation so
        # the daily refresh keeps a continuous series.
        out.append(
            {
                "trade_date": date.today(),
                "value": 0,
                "is_partial": False,
                "region": region,
            }
        )
        time.sleep(sleep_seconds)
        return out

    try:
        for idx, row in df.iterrows():
            try:
                d = idx.date() if hasattr(idx, "date") else idx
            except Exception:
                d = date.today()
            try:
                value = int(float(row.get(keyword, 0)))
            except (TypeError, ValueError):
                value = 0
            out.append(
                {
                    "trade_date": d,
                    "value": value,
                    "is_partial": False,
                    "region": region,
                }
            )
    except Exception as exc:
        logger.warning("pytrends.fetch_google_trends(%s) parse failed: %s", keyword, exc)
        return []

    time.sleep(sleep_seconds)
    return out


# ---------------------------------------------------------------------------
# Combined refresh helper
# ---------------------------------------------------------------------------


def refresh_all(
    *,
    daily_limit_per_source: int = 8,
    days: int = 30,
) -> dict[str, Any]:
    """Fetch one observation per keyword for every configured source.

    Caps each source at ``daily_limit_per_source`` keywords per call so
    the daily ETL doesn't blow the pytrends 60s cadence.  Callers are
    expected to rotate through the registry across days.
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
    """Return the day's slice of keywords per source (rotates by day-of-year).

    Returned dict is ``{source: [keyword, ...]}`` so the pipeline can
    decide which sources are still active without consulting the full
    registry every run.
    """
    slice_size = 8
    out: dict[str, list[str]] = {}
    today_index = date.today().toordinal() % max(1, slice_size)
    for source in ("baidu", "google"):
        flat = [kw for (kw, _cat, _src) in flatten_keywords(registry, source)]
        if not flat:
            continue
        n = len(flat)
        # Rotate the start pointer by day-of-year so coverage cycles daily.
        start = today_index % n if n else 0
        rotated = flat[start:] + flat[:start]
        out[source] = rotated[:slice_size]
    return out