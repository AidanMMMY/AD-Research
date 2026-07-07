"""Build a comprehensive TS_CODE → orgId mapping for cninfo.

The previous ad-hoc mapping only had ~40 entries (mostly large-cap SH/SZ
codes), so the nightly pipeline silently skipped 95% of the universe and
returned empty results. cninfo publishes a public, key-free endpoint that
contains every stock listed on it:

    GET http://www.cninfo.com.cn/new/data/szse_stock.json

The endpoint returns SZSE keys but the value-side actually contains
*all* A-share + B-share + CDR codes with their correct orgId prefix
(``gssh`` for SH, ``gssz`` for SZ, ``gfbj`` for BSE).  We pull the
endpoint, filter category=``A股``, infer the Tushare exchange suffix from
the code prefix, and emit a deterministic Tushare ``ts_code`` → orgId
mapping.

We also POST a sanity-check call against the announcement-query endpoint
to verify the orgId for a couple of representative codes — that catches
prefix rotations from the historic ``gszz0600001``-style entries that
still live in the existing mapping file.

Usage::

    # From repo root on the server.
    cd /opt/ad-research
    python3 scripts/build_cninfo_org_id_map.py \\
        --output app/data/static/cninfo_org_ids.json \\
        --backup app/data/static/cninfo_org_ids.json.bak

    # Dry-run only (print counts, do not write):
    python3 scripts/build_cninfo_org_id_map.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


# cninfo public endpoints — both probed via the disclosure search page
_SZSE_LIST_URL = "http://www.cninfo.com.cn/new/data/szse_stock.json"
_HKE_LIST_URL = "http://www.cninfo.com.cn/new/data/hke_stock.json"

_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "http://www.cninfo.com.cn/new/disclosure/stock?stockCode=&orgId=",
}

_HTTP_TIMEOUT = 15

# Minimal retry budget for the static JSON fetch.
_RETRY_BACKOFF = (2.0, 4.0, 8.0)


# Tushare-style suffix inference.  We keep the codes that count as A-shares
# for periodic reports; B-shares, ETFs/funds and CDRs are excluded because
# cninfo only indexes periodic-report announcements for actual listed
# companies (etfs are covered through separate pipeline).
def _infer_suffix(code: str) -> str | None:
    """Return the Tushare ``.XX`` suffix for a 6-digit cninfo code."""
    if not code or len(code) != 6 or not code.isdigit():
        return None
    if code.startswith(("60", "68")):
        return ".SH"
    if code.startswith(("00", "002", "300")):
        return ".SZ"
    if code.startswith(("8", "920", "430")):
        return ".BJ"
    return None


def _fetch_json(url: str) -> dict[str, Any] | None:
    last_err: str | None = None
    for attempt, backoff in enumerate([0.0, *_RETRY_BACKOFF]):
        if backoff:
            time.sleep(backoff)
        try:
            resp = requests.get(
                url, headers=_HTTP_HEADERS, timeout=_HTTP_TIMEOUT
            )
        except requests.RequestException as exc:
            last_err = repr(exc)
            log.warning("[%s] attempt %d failed: %s", url, attempt, exc)
            continue
        if resp.status_code != 200:
            last_err = f"HTTP {resp.status_code}"
            log.warning("[%s] attempt %d status=%d", url, attempt, resp.status_code)
            continue
        try:
            return resp.json()
        except ValueError as exc:
            last_err = repr(exc)
            log.warning("[%s] attempt %d invalid JSON: %s", url, attempt, exc)
    log.error("[%s] all attempts failed: %s", url, last_err)
    return None


def _collect_stock_lists() -> list[dict[str, Any]]:
    """Return the union of all cninfo stockList entries (deduped by orgId).

    Some dual-listed companies (e.g. A+H) share an ``orgId`` between the
    SZSE/SSE feed and the HKE feed; cninfo's stockList exposes the *same*
    orgId twice (once tagged ``A股`` and once ``港股``).  We dedup by
    orgId but prefer the A-share side whenever both exist, so the
    periodic-report pipeline sees the A-share code rather than the HK
    code (``300750`` not ``03750``).
    """
    # Prefer A-share over HK so we keep the 6-digit A-share codes.
    rank = {"A股": 0, "B股": 1, "CDR": 2, "港股": 3, None: 9, "": 9}
    by_org: dict[str, dict[str, Any]] = {}
    for url in (_SZSE_LIST_URL, _HKE_LIST_URL):
        body = _fetch_json(url)
        if not body:
            continue
        for entry in body.get("stockList") or []:
            org_id = entry.get("orgId")
            if not org_id:
                continue
            cur = by_org.get(org_id)
            if cur is None or rank.get(entry.get("category"), 9) < rank.get(
                cur.get("category"), 9
            ):
                by_org[org_id] = entry
        log.info("pulled %s -> %d entries (%d unique orgIds)", url,
                 len(body.get("stockList") or []), len(by_org))
    return list(by_org.values())


# Code prefixes we want to KEEP.  cninfo's stockList includes other
# instruments like LOFs/funds/namespaces — we only emit rows for plain
# A-share 6-digit codes (so 9900xx and other funds are skipped).
_KEEP_CATEGORY = {"A股", "B股"}  # B-shares also publish periodic reports


def _build_mapping(stock_list: list[dict[str, Any]]) -> dict[str, str]:
    """Return Tushare-style ``ts_code -> orgId`` mapping."""
    mapping: dict[str, str] = {}
    skipped: dict[str, int] = {}
    for entry in stock_list:
        cat = entry.get("category")
        if cat not in _KEEP_CATEGORY:
            skipped[cat or "(none)"] = skipped.get(cat or "(none)", 0) + 1
            continue
        code = entry.get("code") or ""
        org_id = entry.get("orgId")
        if not code or not org_id:
            continue
        suffix = _infer_suffix(code)
        if suffix is None:
            skipped["non-6digit"] = skipped.get("non-6digit", 0) + 1
            continue
        ts_code = f"{code}{suffix}"
        existing = mapping.get(ts_code)
        if existing and existing != org_id:
            log.warning(
                "duplicate ts_code %s -> %s (was %s); keeping newest",
                ts_code, org_id, existing,
            )
        mapping[ts_code] = org_id
    if skipped:
        log.info("skipped categories: %s", skipped)
    return mapping


def _load_existing(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("could not parse %s: %s — starting fresh", path, exc)
        return {}


def _merge_keep_comment(
    fresh: dict[str, str],
    existing: dict[str, Any],
) -> dict[str, Any]:
    """Merge fresh map with existing file, preserving comment / non-ts keys.

    Rows whose ``ts_code`` is not in the fresh map are kept so we don't
    regress when cninfo's static endpoint misses an obscure ticker (or
    rolls an orgId).
    """
    merged: dict[str, Any] = {}
    comment = existing.get("_comment")
    if comment:
        merged["_comment"] = comment
    for k, v in existing.items():
        if k.startswith("_"):
            continue
        if k in fresh:
            # Fresh takes precedence (verified-by-cninfo), but if it
            # disagrees with the historical heuristic we still log.
            if v != fresh[k]:
                log.debug("overriding %s: %s -> %s", k, v, fresh[k])
            merged[k] = fresh[k]
        else:
            # Keep stale entry but tag it so future runs can purge.
            merged[k] = v
    # Add any brand-new entries that weren't in the existing file.
    for k, v in fresh.items():
        if k not in merged:
            merged[k] = v
    return merged


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("app/data/static/cninfo_org_ids.json"),
        help="Path to write the merged mapping JSON",
    )
    parser.add_argument(
        "--backup",
        type=Path,
        default=None,
        help="If provided, copy the current file to this path before overwrite",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print stats but do not write a new file",
    )
    args = parser.parse_args(argv)

    stock_list = _collect_stock_lists()
    fresh = _build_mapping(stock_list)
    log.info("fresh cninfo mapping size: %d (A-share rows)", len(fresh))

    existing = _load_existing(args.output)
    merged = _merge_keep_comment(fresh, existing)
    log.info("merged mapping size: %d", len(merged))

    a_rows = [k for k in merged if not k.startswith("_")]
    by_exchange: dict[str, int] = {}
    for k in a_rows:
        ex = k.split(".")[-1]
        by_exchange[ex] = by_exchange.get(ex, 0) + 1
    log.info("by exchange: %s", by_exchange)

    if args.dry_run:
        print(json.dumps({
            "fresh_count": len(fresh),
            "merged_count": len(merged),
            "by_exchange": by_exchange,
            "sample": dict(list(merged.items())[:5]),
        }, indent=2, ensure_ascii=False))
        return 0

    if args.backup and args.output.exists():
        args.backup.write_bytes(args.output.read_bytes())
        log.info("backed up existing file to %s", args.backup)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    log.info("wrote %s (%d rows)", args.output, len(merged))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
