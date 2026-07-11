"""批量下载 PDF 并提取文本（后台长运行队列）。

从 ``cninfo_reports`` 表中读取 ``extraction_status = 'pending'`` 的记录，
批量下载 PDF 到本地存储，然后用 pdfplumber/pypdf 提取文本。

设计为单进程长运行任务（PDF 下载不限速，文本提取受单核 CPU 限制）。
可并行多进程（每条记录有数据库行锁保护，不会重复处理）。

Usage::

    # 单进程（默认 batch=200, 处理后自动退出）
    python3 scripts/batch_download_extract.py

    # 持续运行模式（处理完所有 pending 后退 60s 再检查）
    python3 scripts/batch_download_extract.py --daemon

    # 更大 batch
    python3 scripts/batch_download_extract.py --batch-size 500

    # 仅下载（不提取文本）
    python3 scripts/batch_download_extract.py --skip-extract

    # 仅提取已有 PDF 但尚未提取文本的
    python3 scripts/batch_download_extract.py --skip-download
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.cninfo_report import CninfoReport
from app.services.cninfo_report_service import CninfoReportService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("batch_download_extract")


def _pick_batch(db, service: CninfoReportService, batch_size: int,
                skip_download: bool, skip_extract: bool) -> int:
    """Process one batch. Returns number processed."""
    if skip_download:
        # Only process rows that have a file_path but no extracted_text
        stmt = (
            select(CninfoReport)
            .where(
                CninfoReport.extraction_status == "downloaded",
                CninfoReport.file_path.isnot(None),
            )
            .limit(batch_size)
        )
    else:
        stmt = (
            select(CninfoReport)
            .where(CninfoReport.extraction_status == "pending")
            .limit(batch_size)
        )

    rows = db.execute(stmt).scalars().all()
    if not rows:
        return 0

    downloaded = 0
    extracted = 0
    failed = 0

    for row in rows:
        try:
            if not skip_download and row.extraction_status == "pending":
                path = service.download_pdf(row.id)
                if path:
                    downloaded += 1
                    db.refresh(row)
                else:
                    failed += 1
                    continue

            if not skip_extract:
                ok = service.extract_text_for_report(row.id)
                if ok:
                    extracted += 1
                else:
                    failed += 1
        except Exception as exc:
            log.warning("row %d (%s) failed: %s", row.id, row.ts_code, exc)
            failed += 1

    log.info("batch: downloaded=%d extracted=%d failed=%d", downloaded, extracted, failed)
    return len(rows)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-extract", action="store_true")
    parser.add_argument("--sleep", type=int, default=60, help="sleep seconds between batches in daemon mode")
    args = parser.parse_args(argv)

    db = SessionLocal()
    service = CninfoReportService(db)

    # Count pending
    pending = db.execute(
        select(CninfoReport).where(CninfoReport.extraction_status == "pending")
    ).scalars().all()
    log.info("pending downloads: %d rows", len(pending))

    round_num = 0
    while True:
        round_num += 1
        processed = _pick_batch(
            db, service, args.batch_size, args.skip_download, args.skip_extract,
        )
        if processed == 0:
            log.info("no more rows to process")
            if not args.daemon:
                break
            log.info("sleeping %ds before next check...", args.sleep)
            time.sleep(args.sleep)
        else:
            if not args.daemon and round_num >= 10:
                # Non-daemon mode caps at 10 batches to avoid runaway
                log.info("non-daemon cap reached (10 batches) — exiting")
                break

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
