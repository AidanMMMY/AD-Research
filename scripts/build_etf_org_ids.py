#!/usr/bin/env python3
"""Build / refresh the cninfo orgId table for active A-share ETFs.

The default ``app/data/static/cninfo_org_ids.json`` only carries the
~40 names manually curated for periodic-report scraping.  This script
extends it with the **~600 on-exchange ETFs** that cninfo actually
indexes, by walking every row of Eastmoney's
``fund_etf_spot_em`` feed and resolving each code through cninfo's
``topSearch/query`` endpoint.

Output: writes the table back to ``app/data/static/cninfo_org_ids.json``
in the richer shape ``{ts_code: {orgId, name}}`` (downstream
``CninfoETFHoldingsProvider`` accepts both the old ``{ts_code: orgId}``
shape and the new one).

Run from the repo root, ideally from inside the backend container so
akshare is importable::

    docker exec alloyresearch-backend python3 scripts/build_etf_org_ids.py

The script is **idempotent** — re-running it patches the table in place
without dropping manually-curated entries.  Expect ~10 minutes for the
~1,500 ETFs at cninfo's ~2 req/s politeness budget.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import requests


_REPO_ROOT = Path(__file__).resolve().parents[1]
_TABLE_PATH = _REPO_ROOT / "app" / "data" / "static" / "cninfo_org_ids.json"
_TOPSEARCH_URL = "http://www.cninfo.com.cn/new/information/topSearch/query"
_AKSHARE_TIMEOUT = 60
_HTTP_TIMEOUT = 10
_MIN_INTERVAL = 0.6  # seconds between cninfo calls

logger = logging.getLogger("build_etf_org_ids")


def _load_existing_table() -> dict:
    if not _TABLE_PATH.exists():
        return {}
    try:
        return json.loads(_TABLE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _normalise_entry(value) -> dict:
    """Coerce the on-disk entry into the new ``{orgId, name}`` shape."""
    if isinstance(value, dict):
        return {
            "orgId": value.get("orgId") or value.get("org_id"),
            "name": value.get("name") or value.get("zwjc"),
        }
    if isinstance(value, str):
        return {"orgId": value, "name": None}
    return {"orgId": None, "name": None}


def fetch_etf_universe() -> list[dict]:
    """Return ``[{code, name, market}, ...]`` for active A-share ETFs."""
    try:
        import akshare as ak
    except ImportError as exc:  # pragma: no cover - container check
        raise SystemExit(
            "akshare is required to enumerate the ETF universe; run from "
            "the backend container (docker exec alloyresearch-backend ...)"
        ) from exc

    df = ak.fund_etf_spot_em()
    if df is None or df.empty:
        return []
    out = []
    for _, row in df.iterrows():
        code = str(row.get("代码") or "").strip()
        name = str(row.get("名称") or "").strip()
        if not code:
            continue
        # Heuristic: SH ETFs start with 5 or 6; SZ ETFs start with 1.
        if code.startswith("5") or code.startswith("6"):
            market = "SH"
        elif code.startswith("1"):
            market = "SZ"
        else:
            market = "SH"
        out.append({"code": code, "name": name, "market": market})
    return out


def resolve_org_id(name: str, session: requests.Session) -> str | None:
    """Query cninfo's topSearch and return the first ETF match's orgId."""
    payload = {"keyWord": name, "maxSecNum": 10, "maxListNum": 10}
    try:
        r = session.post(
            _TOPSEARCH_URL,
            data=payload,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
                ),
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            timeout=_HTTP_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.debug("topSearch %s: %s", name, exc)
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    for entry in data or []:
        if entry.get("category") == "ETF" and entry.get("zwjc") == name:
            return entry.get("orgId")
    # Fallback: first ETF-shaped entry, even if name differs slightly.
    for entry in data or []:
        if entry.get("category") == "ETF":
            return entry.get("orgId")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Cap the number of ETFs to process (0 = no cap, default).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the proposed table without writing it back to disk.",
    )
    parser.add_argument(
        "--log",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=args.log,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    logging.info("Loading existing table from %s", _TABLE_PATH)
    existing = _load_existing_table()
    # Strip the _comment key from the existing blob (it's metadata, not data).
    existing.pop("_comment", None)

    universe = fetch_etf_universe()
    if not universe:
        logging.error("ETF universe from akshare is empty — aborting")
        return 1
    if args.limit:
        universe = universe[: args.limit]
    logging.info("ETF universe: %d entries", len(universe))

    session = requests.Session()
    table: dict = {}
    matched = 0
    unchanged = 0
    missing = 0
    for i, etf in enumerate(universe, 1):
        code = etf["code"]
        name = etf["name"]
        ts_code = f"{code}.{etf['market']}"
        # Skip if we already have a non-null orgId for this ts_code.
        prior = _normalise_entry(existing.get(ts_code) or existing.get(code))
        if prior.get("orgId"):
            table[ts_code] = {"orgId": prior["orgId"], "name": prior.get("name") or name}
            unchanged += 1
            continue
        org_id = resolve_org_id(name, session)
        if org_id:
            table[ts_code] = {"orgId": org_id, "name": name}
            matched += 1
        else:
            table[ts_code] = {"orgId": None, "name": name}
            missing += 1
        if i % 50 == 0:
            logging.info(
                "  [%d/%d] matched=%d unchanged=%d missing=%d last=%s %s -> %s",
                i, len(universe), matched, unchanged, missing, ts_code, name, org_id,
            )
        time.sleep(_MIN_INTERVAL)

    # Also preserve any existing entries not in the live universe (delisted
    # codes that the table still references).
    for ts_code, raw in existing.items():
        if ts_code not in table:
            table[ts_code] = _normalise_entry(raw)

    summary = {
        "_comment": (
            "Auto-generated by scripts/build_etf_org_ids.py.  Each entry is "
            "{orgId, name} (cninfo orgId + canonical ETF name).  Downstream "
            "CninfoETFHoldingsProvider reads `orgId`/`name` from this table; "
            "missing orgId entries are simply skipped at fetch time."
        ),
        **table,
    }
    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False, indent=2)[:2000])
        return 0

    _TABLE_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logging.info(
        "Wrote %d entries to %s (matched=%d, unchanged=%d, missing=%d)",
        len(table), _TABLE_PATH, matched, unchanged, missing,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
