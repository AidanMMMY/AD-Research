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

# CATEGORY 显式列出 overnight_v2 — main() 显式注入该 source，单独走
# read_overnight_v2() 而非 read_source()，因此不出现在 KNOWN_SOURCES 里。
CATEGORY = {
    "eastmoney_news": "quick",
    "gov_china": "quick",
    "fed_intl": "quick",
    "stocktwits": "quick",
    "cls": "quick",
    "xueqiu_playwright": "logged_in",
    "x": "logged_in",
    "reddit_curl_cffi": "logged_in",
    "overnight_v2": "overnight",
}

DEFAULT_DATA_ROOT = "/data/ad-research"


# --------------------------------------------------------------------------- #
# Staleness thresholds (used to flag warning / critical in the rendered      #
# status report and the process exit code).                                   #
# --------------------------------------------------------------------------- #
# - ``quick`` sources (8 个) are scheduled hourly by orchestrate_v2.          #
#   6h warn / 12h critical = 错过 1 次 / 2 次调度就该告警。                   #
# - ``logged_in`` sources (x / xueqiu / reddit) use cookies that decay;       #
#   24h warn / 48h critical = 1 天 / 2 天没刷。                               #
# - ``overnight`` v2 worker runs once per day (manual kick-off). 36h          #
#   warn / 60h critical = 跨日 / 跨 2 日没产出。                              #
THRESHOLD_HOURS = {
    "quick": (6, 12),
    "logged_in": (24, 48),
    "overnight": (36, 60),
}


def _parse_iso(s: str | None) -> datetime | None:
    """Best-effort ISO 8601 → tz-aware datetime."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def _staleness_level(
    source: str,
    fetched_at: datetime | None,
    mtime_fallback: datetime | None,
    now: datetime,
) -> tuple[str, float | None]:
    """Return (level, hours_since).

    level: "ok" | "warn" | "critical" | "missing"
    """
    # overnight 走 mtime_fallback；其他 source 优先 fetched_at
    if source == "overnight_v2":
        ref = mtime_fallback
        category = "overnight"
    else:
        ref = fetched_at
        category = CATEGORY.get(source, "quick")
    if ref is None:
        return ("missing" if source != "overnight_v2" else "critical", None)
    hours = (now - ref).total_seconds() / 3600.0
    warn_h, crit_h = THRESHOLD_HOURS.get(category, THRESHOLD_HOURS["quick"])
    if hours >= crit_h:
        return ("critical", hours)
    if hours >= warn_h:
        return ("warn", hours)
    return ("ok", hours)


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
        "_fetched_iso": str(fetched_at) if fetched_at else None,
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
        except (json.JSONDecodeError, OSError):
            continue
        # capture file mtime BEFORE summarize so list-payload paths can
        # fall back to it (some sources dump a bare JSON list with no
        # fetched_at key).
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        result = summarize(source, payload)
        if not result.get("_fetched_iso"):
            result["_fetched_iso"] = mtime.isoformat()
        result["_mtime"] = mtime
        return result
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
        "| source | category | staleness | items | last fetched | login_state | note |"
    )
    lines.append("|---|---|---|---:|---|---|---|")
    for row in rows:
        cat = CATEGORY.get(row["source"], "—")
        staleness = row.get("staleness", "?")
        staleness_cell = {
            "ok": "✅ ok",
            "warn": "⚠️ warn",
            "critical": "🔴 critical",
            "missing": "❓ missing",
        }.get(staleness, staleness)
        lines.append(
            "| `{name}` | {cat} | {stale} | {items} | {fetched} | {login} | {note} |".format(
                name=row["source"],
                cat=cat,
                stale=staleness_cell,
                items=row["items"],
                fetched=row["fetched_at"],
                login=row["login_state"],
                note=(row["note"] or "—").replace("|", "\\|"),
            )
        )
    lines.append("")
    levels = {r.get("staleness") for r in rows}
    if "critical" in levels or "missing" in levels:
        lines.append("**🔴 OVERALL: critical** (exit 2)")
    elif "warn" in levels:
        lines.append("**⚠️ OVERALL: warn** (exit 1)")
    else:
        lines.append("**✅ OVERALL: ok** (exit 0)")
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


# --------------------------------------------------------------------------- #
# Overnight v2 (special: db + log mtime, not a JSON today file)              #
# --------------------------------------------------------------------------- #

def read_overnight_v2(data_root: Path) -> dict[str, Any] | None:
    """Find the latest overnight_v2 run dir, return summary or None.

    Strategy: pick the most recently modified directory matching
    ``overnight_*_v2`` (excluding test dirs) under ``data_root`` and report
    its ``overnight_research_v2.db`` mtime as the freshness signal.
    """
    candidates: list[Path] = []
    for path in data_root.glob("overnight_*_v2"):
        if not path.is_dir():
            continue
        if "test" in path.name:
            continue
        candidates.append(path)
    if not candidates:
        return None
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    db_path = latest / "overnight_research_v2.db"
    log_path = latest / "overnight_research_v2.log"
    if not db_path.exists():
        return None
    db_mtime = datetime.fromtimestamp(db_path.stat().st_mtime, tz=timezone.utc)
    log_mtime = (
        datetime.fromtimestamp(log_path.stat().st_mtime, tz=timezone.utc)
        if log_path.exists() else None
    )
    # crude item count: best-effort via db size proxy; the real count
    # requires a sqlite3 read which we deliberately avoid here.
    db_size_kb = db_path.stat().st_size // 1024
    return {
        "source": "overnight_v2",
        "items": db_size_kb,  # KB proxy; UI shows under items column
        "fetched_at": _fmt_ts(db_mtime.isoformat()),
        "login_state": "n/a",
        "note": f"run={latest.name} log_mtime={_fmt_ts(log_mtime.isoformat()) if log_mtime else '—'}",
        "_fetched_iso": db_mtime.isoformat(),
        "_mtime": db_mtime,
    }


def annotate_staleness(rows: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    """Tag each row with staleness level + hours_since. Mutates in place + returns."""
    for row in rows:
        level, hours = _staleness_level(
            source=row["source"],
            fetched_at=_parse_iso(row.get("_fetched_iso")),
            mtime_fallback=row.get("_mtime"),
            now=now,
        )
        row["staleness"] = level
        row["staleness_hours"] = (
            round(hours, 1) if hours is not None else None
        )
        # append to note for visibility in markdown table
        if level in ("warn", "critical", "missing"):
            tag = {
                "warn": "⚠️",
                "critical": "🔴",
                "missing": "❓",
            }[level]
            hours_str = (
                f" ({row['staleness_hours']:.1f}h 旧)"
                if row["staleness_hours"] is not None
                else ""
            )
            row["note"] = (
                f"{tag} {level}{hours_str} | "
                + (row.get("note") or "")
            )
    return rows


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    p.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    p.add_argument("--source", help="show only one source")
    p.add_argument(
        "--no-exit-code",
        action="store_true",
        help="always exit 0 (use when piping the report into chat)",
    )
    args = p.parse_args()

    data_root = Path(args.data_root)
    sources = list(KNOWN_SOURCES)
    if args.source:
        sources = [args.source]

    now = datetime.now(timezone.utc)
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
                "_fetched_iso": None,
            }
        rows.append(summary)

    # overnight_v2 总是 include (除非 --source 显式过滤)
    if not args.source:
        ov = read_overnight_v2(data_root)
        if ov is not None:
            rows.append(ov)

    annotate_staleness(rows, now)

    if args.json:
        # 输出时去掉 _mtime / _fetched_iso 内部字段
        clean = [
            {k: v for k, v in r.items() if not k.startswith("_")}
            for r in rows
        ]
        print(render_json(clean))
    else:
        print(render_markdown(rows, data_root))

    if args.no_exit_code:
        return 0
    # 退出码: 0 = all ok, 1 = warn, 2 = critical
    levels = {r.get("staleness") for r in rows}
    if "critical" in levels or "missing" in levels:
        return 2
    if "warn" in levels:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())