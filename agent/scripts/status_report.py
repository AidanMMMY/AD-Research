#!/usr/bin/env python3
"""
status_report.py — emit a markdown dashboard of AD-Research worker health.

Reads /data/ad-research/<source>/today.json (or similar) for each known
source, then prints a markdown table to stdout suitable for inclusion in
the investment-research platform dashboard or a Slack message.

Usage
-----
    python3 scripts/status_report.py                # markdown table
    python3 scripts/status_report.py --json         # JSON instead
    python3 scripts/status_report.py --data-root /custom/root
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Keep in sync with orchestrate_v2.WORKERS
KNOWN_SOURCES = [
    "eastmoney_news",
    "gov_china",
    "fed_intl",
    "stocktwits",
    "cls",
    "xueqiu_playwright",
    "x",
    "reddit_curl_cffi",
]

CATEGORY = {
    "eastmoney_news": "quick",
    "gov_china": "quick",
    "fed_intl": "quick",
    "stocktwits": "quick",
    "cls": "quick",
    "xueqiu_playwright": "logged_in",
    "x": "logged_in",
    "reddit_curl_cffi": "logged_in",
}

DEFAULT_DATA_ROOT = "/data/ad-research"


# --------------------------------------------------------------------------- #
# Discovery                                                                   #
# --------------------------------------------------------------------------- #


def candidate_files(data_root: Path, source: str) -> list[Path]:
    """Return candidate per-source files, newest first if multiple."""
    src_dir = data_root / source
    if not src_dir.is_dir():
        return []
    candidates = [
        src_dir / "today.json",
        src_dir / "latest.json",
        src_dir / "out.json",
    ]
    # also pick the newest dated file as a fallback
    dated = sorted(
        [p for p in src_dir.glob("*.json") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    # de-dup, preserve order
    seen: set[Path] = set()
    ordered: list[Path] = []
    for p in candidates + dated:
        if p.exists() and p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered


# --------------------------------------------------------------------------- #
# Extraction                                                                  #
# --------------------------------------------------------------------------- #


def _first(*keys: str, payload: dict[str, Any]) -> Any:
    for k in keys:
        if k in payload and payload[k] is not None:
            return payload[k]
    return None


def summarize(source: str, payload: Any) -> dict[str, Any]:
    items = 0
    fetched_at: str | None = None
    login_state: str | None = None
    note: str | None = None

    if isinstance(payload, dict):
        items = _first("items", "count", "total", payload=payload) or 0
        if isinstance(items, list):
            items = len(items)
        elif not isinstance(items, int):
            items = 0

        fetched_at = _first(
            "fetched_at", "crawled_at", "generated_at", "timestamp",
            "as_of", "scraped_at", payload=payload,
        )
        login_state = _first(
            "login_state", "auth", "session", payload=payload,
        )
        meta = payload.get("meta") or payload.get("metadata") or {}
        if isinstance(meta, dict):
            fetched_at = fetched_at or _first(
                "fetched_at", "generated_at", "timestamp", payload=meta,
            )
            login_state = login_state or _first("login_state", payload=meta)
        note = payload.get("note") or payload.get("error")
    elif isinstance(payload, list):
        items = len(payload)

    return {
        "source": source,
        "items": int(items or 0),
        "fetched_at": _fmt_ts(fetched_at),
        "login_state": str(login_state) if login_state else ("n/a" if CATEGORY.get(source) != "logged_in" else "unknown"),
        "note": str(note)[:80] if note else "",
    }


def _fmt_ts(value: Any) -> str:
    if value is None:
        return "—"
    s = str(value)
    # Try to normalise a few common ISO formats to a compact form
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return s[:19]


def read_source(data_root: Path, source: str) -> dict[str, Any] | None:
    for path in candidate_files(data_root, source):
        try:
            with path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
            return summarize(source, payload)
        except (json.JSONDecodeError, OSError):
            continue
    return None


# --------------------------------------------------------------------------- #
# Rendering                                                                   #
# --------------------------------------------------------------------------- #


def render_markdown(rows: list[dict[str, Any]], data_root: Path) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []
    lines.append(f"### AD-Research worker status — {now}")
    lines.append("")
    lines.append(
        "| source | category | items | last fetched | login_state | note |"
    )
    lines.append("|---|---|---:|---|---|---|")
    for row in rows:
        cat = CATEGORY.get(row["source"], "—")
        lines.append(
            "| `{name}` | {cat} | {items} | {fetched} | {login} | {note} |".format(
                name=row["source"],
                cat=cat,
                items=row["items"],
                fetched=row["fetched_at"],
                login=row["login_state"],
                note=row["note"].replace("|", "\\|") or "—",
            )
        )
    lines.append("")
    lines.append(f"_data root: `{data_root}`_")
    return "\n".join(lines)


def render_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(
        {"generated_at": datetime.now(timezone.utc).isoformat(), "sources": rows},
        ensure_ascii=False,
        indent=2,
    )


# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    p.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    p.add_argument("--source", help="show only one source")
    args = p.parse_args()

    data_root = Path(args.data_root)
    sources = [args.source] if args.source else KNOWN_SOURCES

    rows: list[dict[str, Any]] = []
    for src in sources:
        summary = read_source(data_root, src)
        if summary is None:
            summary = {
                "source": src,
                "items": 0,
                "fetched_at": "—",
                "login_state": "missing",
                "note": "no output file",
            }
        rows.append(summary)

    if args.json:
        print(render_json(rows))
    else:
        print(render_markdown(rows, data_root))
    return 0


if __name__ == "__main__":
    sys.exit(main())