"""全量回填 A 股定期报告（多 worker 并行友好）。

从 cninfo_org_ids.json 读取全量 A 股代码，按 ``--offset`` / ``--limit``
分片，每个 shard 独立拉取指定时间窗口的定期报告并 upsert 入库。

依赖 PostgreSQL ``ON CONFLICT (announcement_id)`` 保证幂等 ——
多个 worker 同时写同一条记录也不会产生重复。

Usage::

    # 单 worker: stocks 0-499, 5 年回填
    python3 scripts/backfill_cninfo_reports.py --offset 0 --limit 500

    # 多 worker 并行（在各终端分别启动）
    for i in 0 500 1000 1500 2000; do
      nohup python3 scripts/backfill_cninfo_reports.py \
        --offset $i --limit 500 \
        > /tmp/cninfo_backfill_${i}.log 2>&1 &
    done

    # 仅回填最近 1 年（更快）
    python3 scripts/backfill_cninfo_reports.py --offset 0 --limit 500 --years 1

    # 仅拉年报（跳过 Q1/Q3/半年，速度 4x）
    python3 scripts/backfill_cninfo_reports.py --offset 0 --limit 500 --type annual

    # 试运行（只打印会处理哪些股票，不实际拉取）
    python3 scripts/backfill_cninfo_reports.py --offset 0 --limit 10 --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

# Ensure the project root is on sys.path so `app` is importable.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from app.core.database import SessionLocal
from app.services.cninfo_report_service import CninfoReportService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("backfill_cninfo")

# ── constants ──────────────────────────────────────────
_ORG_IDS_PATH = _PROJECT_ROOT / "app" / "data" / "static" / "cninfo_org_ids.json"

_ALL_TYPES = ("annual", "semi", "q1", "q3")

# ETA logging interval (every N stocks).
_ETA_INTERVAL = 50


def load_ts_codes() -> list[str]:
    """Read cninfo_org_ids.json and return sorted list of ts_codes."""
    if not _ORG_IDS_PATH.exists():
        log.error("org_id mapping not found at %s — run build_cninfo_org_id_map.py first", _ORG_IDS_PATH)
        sys.exit(1)
    data = json.loads(_ORG_IDS_PATH.read_text(encoding="utf-8"))
    codes = sorted(k for k in data if not k.startswith("_"))
    log.info("loaded %d ts_codes from %s", len(codes), _ORG_IDS_PATH)
    return codes


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offset", type=int, required=True)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--years", type=int, default=5, help="how many years back from today")
    parser.add_argument(
        "--type",
        choices=("annual", "semi", "q1", "q3", "all"),
        default="all",
        help="only fetch this report type (default: all)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    all_codes = load_ts_codes()
    shard = all_codes[args.offset : args.offset + args.limit]
    if not shard:
        log.warning("empty shard (offset=%d limit=%d total=%d)", args.offset, args.limit, len(all_codes))
        return 0

    end_date = date.today()
    start_date = end_date - timedelta(days=args.years * 365)

    log.info(
        "shard [%d:%d] — %d stocks, window %s..%s, types=%s",
        args.offset, args.offset + args.limit,
        len(shard), start_date, end_date,
        "all" if args.type == "all" else args.type,
    )

    if args.dry_run:
        log.info("DRY-RUN — first 20: %s", shard[:20])
        return 0

    db = SessionLocal()
    service = CninfoReportService(db)
    total_written = 0
    total_skipped = 0
    t0 = time.time()

    for idx, ts_code in enumerate(shard):
        iter_start = time.time()
        try:
            if args.type == "all":
                written = service.fetch_for_stock(ts_code, start_date, end_date)
            else:
                # Fetch a single report type only (faster).
                from app.data.providers.cninfo_provider import CninfoProvider
                provider = service.provider
                org_id = provider.get_org_id(ts_code)
                if not org_id:
                    total_skipped += 1
                    continue
                raw = provider.fetch_announcements(
                    org_id=org_id,
                    start_date=start_date,
                    end_date=end_date,
                    period_type=args.type,
                )
                written = 0
                stock_code = ts_code.split(".")[0]
                for rec in raw:
                    try:
                        written += service._upsert(rec, ts_code, stock_code, org_id)
                    except Exception:
                        pass
            if written > 0:
                total_written += written
        except Exception as exc:
            log.warning("[%d/%d] %s FAILED: %s", idx + 1, len(shard), ts_code, exc)
            continue

        elapsed = time.time() - iter_start
        if (idx + 1) % _ETA_INTERVAL == 0:
            done = idx + 1
            avg = (time.time() - t0) / done
            eta_min = (len(shard) - done) * avg / 60
            log.info(
                "[%d/%d] progress — written=%d skipped=%d avg=%.1fs/stock eta=%.0fmin",
                done, len(shard), total_written, total_skipped, avg, eta_min,
            )

    db.close()

    total_time = time.time() - t0
    log.info(
        "DONE shard [%d:%d] — %d stocks, written %d rows, skipped %d (no org_id), %.0fs (%.1fs/stock)",
        args.offset, args.offset + args.limit,
        len(shard), total_written, total_skipped, total_time,
        total_time / len(shard) if shard else 0,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
