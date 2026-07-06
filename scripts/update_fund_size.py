"""Update ETF fund_size (AUM) from multiple data sources with fallback.

Supports:
  1. A-share ETFs: akshare fund_etf_spot_em (总市值) → Tushare fund_share+fund_daily
  2. US ETFs: yfinance info (total_assets / marketCap) with strict rate limiting

Features:
  - Incremental update (only missing or stale records)
  - Multi-source fallback with per-record reason tracking
  - Marks unrecoverable instruments so they are not retried indefinitely
  - Dry-run mode for safe local testing

Usage:
    python scripts/update_fund_size.py --dry-run
    python scripts/update_fund_size.py --max-age-days 7 --mark-unrecoverable
    python scripts/update_fund_size.py --force-all
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
import warnings
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore")

import akshare as ak
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal
from app.models.etf import ETFInfo


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOG_DIR = PROJECT_ROOT / "logs" / "fund_size"
LOG_DIR.mkdir(parents=True, exist_ok=True)

A_SHARE_EXCHANGES = {"SH", "SZ", "BJ"}
US_EXCHANGES = {"NYSE", "NASDAQ"}

# Funds that are listed but are not exchange-traded funds. Their AUM is not
# available from akshare fund_etf_spot_em and usually not from Tushare fund_daily.
LOF_REIT_KEYWORDS = ("LOF", "REIT")

# Tushare free/basic tier: keep well under 1 QPS to avoid account suspension
TUSHARE_DELAY_SECONDS = 0.4
YFINANCE_DELAY_SECONDS = 2.0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SizeResult:
    """Result of a single size lookup."""

    value: float | None
    source: str
    reason: str = ""


@dataclass
class UpdateSummary:
    """Aggregated update statistics."""

    total_etfs: int = 0
    skipped_fresh: int = 0
    updated: int = 0
    missing: int = 0
    marked_unrecoverable: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    by_reason: dict[str, int] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_etfs": self.total_etfs,
            "skipped_fresh": self.skipped_fresh,
            "updated": self.updated,
            "missing": self.missing,
            "marked_unrecoverable": self.marked_unrecoverable,
            "by_source": self.by_source,
            "by_reason": self.by_reason,
            "errors": self.errors[:50],  # cap log size
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pure_code(code: str) -> str:
    """Strip exchange suffix, e.g. 159915.SZ -> 159915."""
    return code.split(".")[0] if "." in code else code


def _code_with_suffix(code: str, exchange: str) -> str:
    """Ensure Tushare-style suffix."""
    if "." in code:
        return code
    mapping = {"SH": ".SH", "SZ": ".SZ", "BJ": ".BJ"}
    return f"{code}{mapping.get(exchange, '')}"


def _trade_date_str(d: datetime | date) -> str:
    return d.strftime("%Y%m%d") if isinstance(d, date) else d.strftime("%Y%m%d")


def _classify_name(name: str | None) -> str:
    """Classify a listed fund by its name."""
    if not name:
        return "unknown"
    upper = name.upper()
    if "REIT" in upper:
        return "REIT"
    if "LOF" in upper:
        return "LOF"
    return "ETF"


def _missing_reason(record: ETFInfo, fallback_reason: str) -> str:
    """Build a specific reason why an instrument has no fund_size."""
    if record.status == "delisted":
        return "delisted"
    fund_type = _classify_name(record.name)
    if fund_type == "REIT":
        return "REIT not covered by ETF spot sources"
    if fund_type == "LOF":
        return "LOF not covered by ETF spot sources"
    return fallback_reason


def _load_tushare_pro() -> Any:
    token = os.getenv("TUSHARE_TOKEN", "")
    if not token:
        return None
    try:
        import tushare as ts

        return ts.pro_api(token)
    except Exception as exc:
        print(f"[Tushare] failed to initialize: {exc}")
        return None


# ---------------------------------------------------------------------------
# Data source fetchers
# ---------------------------------------------------------------------------


def fetch_akshare_size_map() -> dict[str, float]:
    """Fetch A-share ETF AUM directly from akshare.

    Returns mapping of pure code -> fund size in CNY.
    """
    print("[Akshare] Fetching fund_etf_spot_em ...")
    try:
        df = ak.fund_etf_spot_em()
    except Exception as exc:
        print(f"[Akshare] ERROR: {exc}")
        return {}

    if df.empty or "代码" not in df.columns or "总市值" not in df.columns:
        print("[Akshare] empty or unexpected schema")
        return {}

    size_map: dict[str, float] = {}
    for _, row in df.iterrows():
        code = str(row["代码"]).strip()
        total_mv = row.get("总市值")
        if pd.notna(total_mv) and float(total_mv) > 0:
            size_map[code] = float(total_mv)

    print(f"[Akshare] returned {len(size_map)} ETFs with size")
    return size_map


def fetch_tushare_size_map(pro: Any, target_date: str | None = None, max_lookback: int = 10) -> dict[str, float]:
    """Fetch A-share fund AUM from Tushare fund_share + fund_daily.

    Tries the requested trade_date and walks backwards through up to
    ``max_lookback`` calendar days to find the most recent available data.

    AUM (CNY) = fd_share (万份) * close_price (元) * 10000
    Returns mapping of ts_code (with suffix) -> fund size in CNY.
    """
    if pro is None:
        return {}

    if not target_date:
        target_date = _trade_date_str(datetime.now() - timedelta(days=1))

    share_df: pd.DataFrame | None = None
    daily_df: pd.DataFrame | None = None
    used_date = target_date

    for _ in range(max_lookback):
        print(f"[Tushare] Fetching fund_share for {used_date} ...")
        try:
            share_df = pro.fund_share(trade_date=used_date)
        except Exception as exc:
            print(f"[Tushare] fund_share failed for {used_date}: {exc}")
            share_df = None

        if share_df is not None and not share_df.empty:
            break

        # Walk back one calendar day
        dt = datetime.strptime(used_date, "%Y%m%d") - timedelta(days=1)
        used_date = dt.strftime("%Y%m%d")
        time.sleep(TUSHARE_DELAY_SECONDS)
    else:
        print("[Tushare] fund_share empty for all attempted dates")
        return {}

    # Keep listed funds on SH/SZ/BJ. Do not filter fund_type strictly: many
    # records classified as LOF in our table still have shares traded on exchange.
    share_df = share_df[share_df["market"].isin({"SH", "SZ", "BJ"})]
    if share_df.empty:
        print("[Tushare] no A-share funds in fund_share")
        return {}

    share_df = share_df.drop_duplicates(subset=["ts_code"], keep="first")
    print(f"[Tushare] fund_share returned {len(share_df)} A-share funds for {used_date}")

    print(f"[Tushare] Fetching fund_daily for {used_date} ...")
    time.sleep(TUSHARE_DELAY_SECONDS)
    try:
        daily_df = pro.fund_daily(trade_date=used_date)
    except Exception as exc:
        print(f"[Tushare] fund_daily failed for {used_date}: {exc}")
        return {}

    if daily_df.empty:
        print("[Tushare] fund_daily empty")
        return {}

    daily_df = daily_df.drop_duplicates(subset=["ts_code"], keep="first")
    merged = share_df.merge(daily_df[["ts_code", "close"]], on="ts_code", how="inner")

    size_map: dict[str, float] = {}
    for _, row in merged.iterrows():
        code = str(row["ts_code"]).strip()
        fd_share = row.get("fd_share")
        close = row.get("close")
        if pd.notna(fd_share) and pd.notna(close) and float(close) > 0 and float(fd_share) > 0:
            # fd_share is 万份, close is 元 -> AUM in 元 = fd_share * 10000 * close
            size_map[code] = float(fd_share) * 10000.0 * float(close)

    print(f"[Tushare] computed size for {len(size_map)} A-share funds")
    return size_map


def fetch_yfinance_size_map(codes: list[str]) -> dict[str, SizeResult]:
    """Fetch US ETF AUM from yfinance with strict rate limiting.

    Returns mapping of internal code -> SizeResult.
    """
    results: dict[str, SizeResult] = {}
    if not codes:
        return results

    try:
        import yfinance as yf
    except ImportError:
        print("[yfinance] not installed")
        return {code: SizeResult(None, "yfinance", "yfinance not installed") for code in codes}

    print(f"[yfinance] Fetching size for {len(codes)} US ETFs (slow, ~{YFINANCE_DELAY_SECONDS}s each) ...")
    for code in codes:
        symbol = code.replace(".US", "")
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info or {}
            # Prefer total_assets (AUM) then marketCap
            size = info.get("totalAssets") or info.get("marketCap")
            if size and float(size) > 0:
                results[code] = SizeResult(float(size), "yfinance", "")
            else:
                results[code] = SizeResult(None, "yfinance", "no AUM field in yfinance info")
        except Exception as exc:
            results[code] = SizeResult(None, "yfinance", f"yfinance error: {exc}")
        time.sleep(YFINANCE_DELAY_SECONDS)

    successes = sum(1 for r in results.values() if r.value is not None)
    print(f"[yfinance] returned size for {successes}/{len(codes)} US ETFs")
    return results


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def ensure_fund_size_source_column(db: Session) -> None:
    """Add fund_size_source column if it does not exist (idempotent)."""
    try:
        db.execute(
            text(
                "ALTER TABLE etf_info ADD COLUMN IF NOT EXISTS fund_size_source VARCHAR(100)"
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"[DB] warning: could not ensure fund_size_source column: {exc}")


def is_fresh(record: ETFInfo, max_age_days: int, now: datetime, unrecoverable_cooldown_days: int = 30) -> bool:
    """Return True if record does not need updating.

    A record with a non-NULL fund_size is fresh if updated recently.
    A record marked unrecoverable (fund_size is NULL and fund_size_source
    starts with 'unrecoverable:') is fresh for a longer cooldown so we do not
    hammer external APIs for instruments that are permanently unavailable.
    """
    updated_at = record.updated_at
    if updated_at is None:
        return False
    if updated_at.tzinfo is not None:
        now = now.astimezone(updated_at.tzinfo)
    age_days = (now - updated_at).days

    if record.fund_size is None and record.fund_size_source and record.fund_size_source.startswith("unrecoverable:"):
        return age_days < unrecoverable_cooldown_days

    if record.fund_size is None:
        return False

    return age_days < max_age_days


# ---------------------------------------------------------------------------
# Main update logic
# ---------------------------------------------------------------------------


def update_fund_size(
    dry_run: bool = False,
    max_age_days: int = 7,
    force_all: bool = False,
    mark_unrecoverable: bool = False,
    enable_yfinance: bool = False,
    batch_size: int = 500,
    unrecoverable_cooldown_days: int = 30,
) -> UpdateSummary:
    """Run the multi-source fund_size update pipeline."""
    summary = UpdateSummary()
    now = datetime.now()

    db = SessionLocal()
    try:
        ensure_fund_size_source_column(db)

        # Only instrument_type='ETF' needs fund_size; stocks use market_cap
        query = db.query(ETFInfo).filter(ETFInfo.instrument_type == "ETF")
        etfs = query.all()
        summary.total_etfs = len(etfs)
        print(f"\nTotal ETF records: {summary.total_etfs}")

        # Split by market
        a_share_etfs: list[ETFInfo] = []
        us_etfs: list[ETFInfo] = []
        others: list[ETFInfo] = []
        for etf in etfs:
            if etf.exchange in A_SHARE_EXCHANGES:
                a_share_etfs.append(etf)
            elif etf.exchange in US_EXCHANGES:
                us_etfs.append(etf)
            else:
                others.append(etf)

        print(f"  A-share ETFs: {len(a_share_etfs)}")
        print(f"  US ETFs: {len(us_etfs)}")
        print(f"  Other/unknown: {len(others)}")

        # Determine which records actually need updating
        to_update_a_share = [e for e in a_share_etfs if force_all or not is_fresh(e, max_age_days, now, unrecoverable_cooldown_days)]
        to_update_us = [e for e in us_etfs if force_all or not is_fresh(e, max_age_days, now, unrecoverable_cooldown_days)]
        summary.skipped_fresh = summary.total_etfs - len(to_update_a_share) - len(to_update_us) - len(others)
        print(f"\nSkipping fresh records (within {max_age_days} days): {summary.skipped_fresh}")
        print(f"To update A-share: {len(to_update_a_share)}")
        print(f"To update US: {len(to_update_us)}")

        # ------------------------------------------------------------------
        # A-share: akshare -> Tushare
        # ------------------------------------------------------------------
        akshare_map: dict[str, float] = {}
        tushare_map: dict[str, float] = {}
        if to_update_a_share:
            akshare_map = fetch_akshare_size_map()
            missing_from_akshare = {e for e in to_update_a_share if _pure_code(e.code) not in akshare_map}
            if missing_from_akshare:
                pro = _load_tushare_pro()
                tushare_map = fetch_tushare_size_map(pro)
            else:
                tushare_map = {}

        # Build code -> size for A-share
        a_share_updates: list[tuple[str, float, str]] = []
        a_share_missing: list[tuple[str, str]] = []
        for etf in to_update_a_share:
            pure = _pure_code(etf.code)
            ts_code = _code_with_suffix(etf.code, etf.exchange)

            if pure in akshare_map:
                a_share_updates.append((etf.code, akshare_map[pure], "akshare"))
            elif ts_code in tushare_map:
                a_share_updates.append((etf.code, tushare_map[ts_code], "tushare"))
            else:
                reason = _missing_reason(etf, "not covered by akshare or tushare batch")
                a_share_missing.append((etf.code, reason))

        # ------------------------------------------------------------------
        # US: yfinance (optional, slow)
        # ------------------------------------------------------------------
        us_updates: list[tuple[str, float, str]] = []
        us_missing: list[tuple[str, str]] = []
        if to_update_us:
            if enable_yfinance:
                yf_results = fetch_yfinance_size_map([e.code for e in to_update_us])
                for etf in to_update_us:
                    res = yf_results.get(etf.code)
                    if res and res.value is not None:
                        us_updates.append((etf.code, res.value, res.source))
                    else:
                        us_missing.append((etf.code, _missing_reason(etf, res.reason if res else "yfinance disabled")))
            else:
                for etf in to_update_us:
                    us_missing.append((etf.code, _missing_reason(etf, "US ETFs require --enable-yfinance (rate limited)")))

        # ------------------------------------------------------------------
        # Apply updates
        # ------------------------------------------------------------------
        all_updates = a_share_updates + us_updates
        all_missing = a_share_missing + us_missing + [(e.code, _missing_reason(e, "unknown exchange/market")) for e in others if force_all or e.fund_size is None]

        for code, size, source in all_updates:
            if not dry_run:
                db.query(ETFInfo).filter(ETFInfo.code == code).update(
                    {
                        "fund_size": size,
                        "fund_size_source": source,
                        "updated_at": now,
                    }
                )
            summary.updated += 1
            summary.by_source[source] = summary.by_source.get(source, 0) + 1

        # Mark unrecoverable missing ones (only if currently NULL to avoid overwriting valid data)
        unrecoverable_codes = {code for code, _ in all_missing if db.query(ETFInfo).filter(ETFInfo.code == code, ETFInfo.fund_size.is_(None)).first() is not None}
        for code, reason in all_missing:
            if mark_unrecoverable and code in unrecoverable_codes:
                if not dry_run:
                    db.query(ETFInfo).filter(ETFInfo.code == code).update(
                        {
                            "fund_size": None,
                            "fund_size_source": f"unrecoverable: {reason}",
                            "updated_at": now,
                        }
                    )
                summary.marked_unrecoverable += 1
            summary.missing += 1
            summary.by_reason[reason] = summary.by_reason.get(reason, 0) + 1

        if not dry_run:
            db.commit()

        # ------------------------------------------------------------------
        # Final summary from DB
        # ------------------------------------------------------------------
        with_size = db.query(ETFInfo).filter(ETFInfo.fund_size.isnot(None)).count()
        total = db.query(ETFInfo).count()
        etf_with_size = (
            db.query(ETFInfo)
            .filter(ETFInfo.instrument_type == "ETF", ETFInfo.fund_size.isnot(None))
            .count()
        )
        etf_total = db.query(ETFInfo).filter(ETFInfo.instrument_type == "ETF").count()

        print(f"\n{'DRY-RUN ' if dry_run else ''}Summary:")
        print(f"  ETF records updated this run: {summary.updated}")
        print(f"  Missing/unrecoverable this run: {summary.missing}")
        print(f"  Marked unrecoverable: {summary.marked_unrecoverable}")
        print(f"  By source: {summary.by_source}")
        print(f"  All records with fund_size: {with_size}/{total}")
        print(f"  ETF records with fund_size: {etf_with_size}/{etf_total}")

    except Exception as exc:
        db.rollback()
        summary.errors.append({"error": str(exc), "trace": traceback.format_exc()})
        raise
    finally:
        db.close()

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Update ETF fund_size from multiple sources")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to DB")
    parser.add_argument("--max-age-days", type=int, default=7, help="Skip records updated within N days")
    parser.add_argument("--force-all", action="store_true", help="Ignore freshness and update all")
    parser.add_argument("--mark-unrecoverable", action="store_true", help="Set fund_size=NULL for instruments that cannot be sourced")
    parser.add_argument("--enable-yfinance", action="store_true", help="Enable yfinance fallback for US ETFs (slow)")
    parser.add_argument("--batch-size", type=int, default=500, help="Unused, kept for CLI compatibility")
    parser.add_argument("--unrecoverable-cooldown-days", type=int, default=30, help="Days before retrying instruments marked unrecoverable")
    args = parser.parse_args()

    summary = update_fund_size(
        dry_run=args.dry_run,
        max_age_days=args.max_age_days,
        force_all=args.force_all,
        mark_unrecoverable=args.mark_unrecoverable,
        enable_yfinance=args.enable_yfinance,
        batch_size=args.batch_size,
        unrecoverable_cooldown_days=args.unrecoverable_cooldown_days,
    )

    # Persist log
    log_path = LOG_DIR / f"update_fund_size_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "args": vars(args),
        "summary": summary.to_dict(),
    }
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    print(f"\nLog written to: {log_path}")


if __name__ == "__main__":
    main()
