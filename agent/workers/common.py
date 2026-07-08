"""
common.py - shared utilities for AD-Research data-source workers.

Used by: cls, eastmoney_news, xueqiu_hot, reddit_finance, stocktwits, gov_china, fed_intl.

Provides:
- Logging setup (console + optional file handler)
- Argparse helper for --hours N / --symbol / --out / --limit
- Standardized JSON output to /data/ad-research/<source>/<timestamp>.json
- Time/date helpers (cutoff window based on --hours)
- HTTP session with sane defaults (UA, timeout, retries via urllib3)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------- Constants ----------
DEFAULT_DATA_ROOT = "/data/ad-research"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

CST = timezone(timedelta(hours=8))  # China Standard Time
UTC = timezone.utc


# ---------- Logging ----------
def setup_logger(name: str, level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    logger.propagate = False
    return logger


# ---------- HTTP session ----------
def make_session(
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: int = 20,
    retries: int = 3,
    backoff: float = 0.5,
) -> requests.Session:
    """Create a requests.Session with retry/backoff and browser-like defaults."""
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": user_agent,
            "Accept": "application/json, text/html, application/xml, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
    )
    retry = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.request_timeout = timeout  # type: ignore[attr-defined]
    return s


def http_get(
    session: requests.Session,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: int = 20,
) -> requests.Response | None:
    """GET with exception swallowing; returns None on hard failure."""
    try:
        resp = session.get(
            url,
            params=params,
            headers=headers,
            timeout=timeout,
        )
        return resp
    except requests.RequestException as exc:
        logging.getLogger("common").warning("GET %s failed: %s", url, exc)
        return None


# ---------- Argparse ----------
def base_parser(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Filter items newer than N hours (default: 24). Use 0 to disable.",
    )
    p.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON path. Default: /data/ad-research/<source>/<utcnow>.json",
    )
    p.add_argument(
        "--data-root",
        type=str,
        default=os.environ.get("AD_RESEARCH_DATA_ROOT", DEFAULT_DATA_ROOT),
        help=f"Root output directory (default: {DEFAULT_DATA_ROOT})",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Max number of items to keep (default: 500).",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    return p


# ---------- Time helpers ----------
def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def parse_dt(value: Any) -> datetime | None:
    """Best-effort parse ISO-8601 / RFC-822 / epoch into tz-aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # feedparser-style: "Mon, 05 Jul 2026 12:34:56 +0000"
        from email.utils import parsedate_to_datetime

        try:
            dt = parsedate_to_datetime(s)
            if dt is not None:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt.astimezone(UTC)
        except (TypeError, ValueError):
            pass
        # ISO-8601 fallback
        try:
            s2 = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s2)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except ValueError:
            return None
    return None


def within_hours(dt: datetime | None, hours: int) -> bool:
    """True if dt is within the last `hours` hours. hours<=0 disables the filter."""
    if hours <= 0 or dt is None:
        return True
    return (utcnow() - dt) <= timedelta(hours=hours)


# ---------- Output ----------
def write_json(
    items: Iterable[dict],
    *,
    source: str,
    out_path: str | None,
    data_root: str,
    limit: int,
    logger: logging.Logger | None = None,
) -> dict:
    """Write `items` to disk, return a small summary dict (also printed to stdout).

    Output schema (always):
      {
        "source": "stocktwits",
        "fetched_at": "2026-07-07T08:00:00Z",
        "count": 42,
        "items": [...]
      }
    """
    log = logger or logging.getLogger("common")
    items_list = list(items)[: max(0, limit)] if limit > 0 else list(items)
    payload = {
        "source": source,
        "fetched_at": utcnow().isoformat().replace("+00:00", "Z"),
        "count": len(items_list),
        "items": items_list,
    }

    if out_path:
        path = Path(out_path)
    else:
        ts = utcnow().strftime("%Y%m%dT%H%M%SZ")
        path = Path(data_root) / source / f"{ts}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("wrote %d items to %s", payload["count"], path)
    # also print the summary to stdout for the orchestrator to parse
    print(json.dumps({"source": source, "count": payload["count"], "path": str(path)}))
    return payload


# ---------- Misc helpers ----------
def safe_get(d: dict, *keys: str, default: Any = None) -> Any:
    """dict.get(d, *keys) chained - first key that exists wins."""
    cur: Any = d
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur


def first_nonempty(*vals: Any) -> Any:
    for v in vals:
        if v not in (None, "", [], {}):
            return v
    return None

# ---------------------------------------------------------------------------
# Legacy compatibility shim
# ---------------------------------------------------------------------------
# Some older workers (xueqiu_hot, eastmoney_news, cls, reddit_finance) were
# written against an earlier version of common.py. Re-export the old names.
# ---------------------------------------------------------------------------
import logging as _logging
import time as _time
import json as _json
import datetime as _datetime
from typing import Any as _Any, Callable as _Callable
import os as _os
import sys as _sys

LOG = _logging.getLogger("ad-research.worker")


def configure_logging(verbose: bool = False) -> None:
    _logging.basicConfig(
        level=_logging.DEBUG if verbose else _logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def add_common_args(p) -> None:
    g = p.add_argument_group("common")
    g.add_argument("--hours", type=int, default=24)
    g.add_argument("--output", type=str, default=None)
    g.add_argument("--data-root", type=str, default="/data/ad-research")
    g.add_argument("--limit", type=int, default=100, dest="max_items")
    g.add_argument("--max-pages", type=int, default=3)
    g.add_argument("--rate", type=float, default=0.5)
    g.add_argument("--timeout", type=int, default=15)
    g.add_argument("--max-retries", type=int, default=3)
    g.add_argument("--verbose", action="store_true")


def fetch_with_retry(fn, max_retry: int = 3, rate: float = 0.5):
    for attempt in range(1, max_retry + 1):
        try:
            r = fn()
            if r is not None and getattr(r, "status_code", 200) < 500:
                return r.json() if hasattr(r, "json") else r
        except Exception as exc:
            LOG.warning("attempt %d/%d failed: %s", attempt, max_retry, exc)
        if attempt < max_retry:
            _time.sleep(rate * attempt)
    return None


def to_iso_utc(dt):
    if dt is None:
        return None
    try:
        if isinstance(dt, (int, float)):
            ts = float(dt) / 1000.0 if dt > 1e11 else float(dt)
            return _datetime.datetime.fromtimestamp(ts, tz=_datetime.timezone.utc).isoformat()
        if isinstance(dt, str):
            try:
                ms = int(dt)
                return _datetime.datetime.fromtimestamp(ms / 1000.0, tz=_datetime.timezone.utc).isoformat()
            except ValueError:
                pass
            return dt
        if isinstance(dt, _datetime.date) and not isinstance(dt, _datetime.datetime):
            return dt.isoformat()
        if isinstance(dt, _datetime.datetime):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_datetime.timezone.utc)
            return dt.isoformat()
    except Exception:
        return None
    return str(dt)


def truncate(s: str, n: int) -> str:
    if not isinstance(s, str):
        s = str(s)
    return s if len(s) <= n else s[:n] + "..."


def write_output(path, items, *, source: str) -> None:
    if not items:
        items = []
    out_path = path or f"/data/ad-research/{source}/today.json"
    _os.makedirs(_os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        _json.dump({"source": source, "count": len(items), "items": items}, f, ensure_ascii=False, indent=2)
    LOG.info("wrote %d items to %s", len(items), out_path)
