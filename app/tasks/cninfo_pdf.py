"""Celery tasks for cninfo PDF download + text extraction.

Separate from ``app.tasks.cninfo`` (metadata backfill) so the two can run
at different cadences and have independent retry/timeout semantics:

* ``backfill_cninfo_reports`` (cninfo.py) — writes metadata only.
* ``download_cninfo_pdfs`` (this module) — reads metadata, downloads
  PDFs, then extracts text into ``extracted_text``.

Both share the same ``cninfo`` queue so they balance against a single
``-c 2`` worker pool; the PDF task is rate-limited per-file to stay
under cninfo's ~30 req/min budget.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime
from pathlib import Path

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.data.providers.exchange_provider import ExchangeProvider
from app.services.cninfo_report_service import (
    CninfoReportService,
    _DEFAULT_PDF_DIR,
)
from app.tasks.cninfo import _load_ts_codes

log = logging.getLogger("celery.cninfo_pdf")

# Public alias so other code can import the canonical path without
# poking at the private ``_DEFAULT_PDF_DIR`` module attribute.
PDF_DIR = _DEFAULT_PDF_DIR

# Sleep between consecutive PDF downloads.  cninfo tolerates ~30 req/min
# in practice; 0.5s gives us ~120 req/min * 2 workers ≈ 240 req/min which
# is plenty of headroom and matches the metadata backfill pacing.
_DOWNLOAD_SLEEP = 0.5

# Print progress every N PDFs so the operator can see ETA.
_ETA_INTERVAL = 50


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30, acks_late=True, queue="cninfo")
def download_cninfo_pdfs(
    self,
    offset: int,
    limit: int,
    start_date: str = "2026-01-01",
    report_type: str = "all",  # annual / semi / q1 / q3 / all
    download: bool = True,
    extract_text: bool = True,
) -> dict:
    """Download + extract PDF text for a shard of A-share stocks.

    Args:
        offset: Start index into the sorted ``cninfo_org_ids.json`` list.
        limit: How many stocks this shard covers.
        start_date: ISO date; only announcements on/after this are processed.
        report_type: ``annual`` / ``semi`` / ``q1`` / ``q3`` / ``all``.
        download: Whether to actually fetch the PDF (else only extract
            from existing ``file_path`` rows — useful for retrying
            extraction after a pdfplumber upgrade).
        extract_text: Whether to run text extraction after download.

    Returns:
        Dict with counters: ``scanned`` / ``downloaded`` / ``skipped`` /
        ``extracted`` / ``failed`` / ``bytes`` /
        ``fallback_used`` (count of downloads salvaged by the exchange
        fallback when cninfo was down).
    """
    all_codes = _load_ts_codes()
    shard = all_codes[offset : offset + limit]
    if not shard:
        log.warning("download_cninfo_pdfs: empty shard offset=%d limit=%d", offset, limit)
        return {
            "scanned": 0,
            "downloaded": 0,
            "skipped": 0,
            "extracted": 0,
            "failed": 0,
            "bytes": 0,
            "fallback_used": 0,
        }

    try:
        cutoff = datetime.fromisoformat(start_date).date()
    except ValueError as exc:
        log.error("invalid start_date %r: %s", start_date, exc)
        return {
            "scanned": 0,
            "downloaded": 0,
            "skipped": 0,
            "extracted": 0,
            "failed": 1,
            "bytes": 0,
            "fallback_used": 0,
        }

    db = SessionLocal()
    try:
        service = CninfoReportService(db)
        # One session-scoped ExchangeProvider so we reuse TCP connections
        # across many resolutions inside the shard.
        exchange_provider = ExchangeProvider()
    
        scanned = 0
        downloaded = 0
        extracted = 0
        skipped = 0
        failed = 0
        total_bytes = 0
        fallback_used = 0
        t0 = time.time()
    
        log.info(
            "download_cninfo_pdfs START shard=[%d:%d] start_date=%s type=%s "
            "download=%s extract=%s pdf_dir=%s",
            offset,
            offset + limit,
            cutoff.isoformat(),
            report_type,
            download,
            extract_text,
            PDF_DIR,
        )
    
        for idx, ts_code in enumerate(shard):
            try:
                # Step 1: ensure metadata exists.  fetch_for_stock is a no-op
                # when there is no orgId in the lookup table, so this only
                # hits cninfo for stocks we *can* actually resolve.
                try:
                    service.fetch_for_stock(
                        ts_code,
                        start_date=cutoff,
                        end_date=date.today(),
                    )
                except Exception as exc:
                    # Don't blow up the whole shard on a single fetch hiccup.
                    log.warning("metadata fetch failed for %s: %s", ts_code, exc)
    
                # Step 2: list pending reports.
                try:
                    reports = service.list_reports_for_download(
                        ts_code=ts_code,
                        start_date=cutoff,
                        report_type=report_type,
                        only_pending=True,
                    )
                except Exception as exc:
                    log.warning("DB query failed for %s: %s", ts_code, exc)
                    failed += 1
                    continue
    
                if not reports:
                    skipped += 1
                    scanned += 1
                    continue
    
                for report in reports:
                    scanned += 1
                    rid = report.id
    
                    # Step 3: download (with exchange fallback).
                    if download and not report.file_path:
                        try:
                            result = service.download_with_fallback(
                                rid, exchange_provider=exchange_provider
                            )
                        except Exception as exc:
                            log.warning(
                                "download raised for %s id=%s: %s",
                                ts_code,
                                rid,
                                exc,
                            )
                            failed += 1
                            continue
    
                        path = result.get("path")
                        source = result.get("source") or "?"
                        if path is None:
                            # download_with_fallback already logged the
                            # underlying cause (no URL / HTTP != 200 /
                            # OSError / no exchange match).  Treat as a
                            # permanent skip so we don't tight-loop on it.
                            failed += 1
                            continue
    
                        downloaded += 1
                        if result.get("fallback_used"):
                            fallback_used += 1
                            log.info(
                                "fallback hit: %s id=%s source=%s",
                                ts_code,
                                rid,
                                source,
                            )
                        try:
                            total_bytes += path.stat().st_size
                        except OSError:  # pragma: no cover - defensive
                            pass
    
                        # Polite pacing between consecutive downloads — the
                        # metadata backfill uses ~2s but the static.cninfo
                        # CDN tolerates more.
                        time.sleep(_DOWNLOAD_SLEEP)
    
                    # Step 4: extract text.
                    if extract_text:
                        try:
                            ok = service.extract_text_for_report(rid)
                        except Exception as exc:
                            log.warning(
                                "extraction raised for %s id=%s: %s",
                                ts_code,
                                rid,
                                exc,
                            )
                            failed += 1
                            continue
                        if ok:
                            extracted += 1
                        # If ok is False the service has already marked the
                        # row ``failed``; don't double-count.
    
                if (idx + 1) % _ETA_INTERVAL == 0:
                    done = idx + 1
                    avg = (time.time() - t0) / max(done, 1)
                    eta_min = (len(shard) - done) * avg / 60
                    log.info(
                        "[%d/%d] progress — scanned=%d downloaded=%d "
                        "extracted=%d skipped=%d failed=%d fallback=%d "
                        "bytes=%.1fMB avg=%.1fs/stock eta=%.0fmin",
                        done,
                        len(shard),
                        scanned,
                        downloaded,
                        extracted,
                        skipped,
                        failed,
                        fallback_used,
                        total_bytes / (1024 * 1024),
                        avg,
                        eta_min,
                    )
    
            except Exception as exc:
                # Last-resort guard: never let one bad stock kill the shard.
                log.exception("unhandled error on %s: %s", ts_code, exc)
                failed += 1
                try:
                    db.rollback()
                except Exception:  # pragma: no cover - defensive
                    pass
                continue

    finally:
        db.close()

    total_time = time.time() - t0
    log.info(
        "download_cninfo_pdfs DONE shard=[%d:%d] — scanned=%d downloaded=%d "
        "extracted=%d skipped=%d failed=%d fallback=%d bytes=%.1fMB %.0fs",
        offset,
        offset + limit,
        scanned,
        downloaded,
        extracted,
        skipped,
        failed,
        fallback_used,
        total_bytes / (1024 * 1024),
        total_time,
    )
    return {
        "scanned": scanned,
        "downloaded": downloaded,
        "extracted": extracted,
        "skipped": skipped,
        "failed": failed,
        "bytes": total_bytes,
        "fallback_used": fallback_used,
    }


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30, acks_late=True, queue="cninfo")
def reextract_cninfo_md(
    self,
    offset: int,
    limit: int,
    batch_sleep: float = 0,
) -> dict:
    """全量重提：把已下载 PDF 的提取产物升级为 markdown（B2，2026-08-03）。

    选取 ``file_path NOT NULL AND (extracted_format IS NULL OR
    extracted_format='text')`` 的行（按 id 排序分片，offset/limit 控制
    单任务处理量，防止单任务超长）。本地 CPU 任务，默认不 sleep；
    ``batch_sleep`` 仅用于想限速时。

    Returns:
        Dict with counters: ``scanned`` / ``extracted`` / ``skipped`` /
        ``failed`` / ``bytes_md``（本次写出的 md 字符数）。
    """
    from sqlalchemy import or_, select

    from app.models.cninfo_report import CninfoReport

    db = SessionLocal()
    try:
        service = CninfoReportService(db)

        stmt = (
            select(CninfoReport)
            .where(
                CninfoReport.file_path.isnot(None),
                or_(
                    CninfoReport.extracted_format.is_(None),
                    CninfoReport.extracted_format == "text",
                ),
            )
            .order_by(CninfoReport.id)
            .offset(offset)
            .limit(limit)
        )
        rows = list(db.execute(stmt).scalars().all())
        if not rows:
            log.info("reextract_cninfo_md: empty shard offset=%d limit=%d", offset, limit)
            return {
                "scanned": 0,
                "extracted": 0,
                "skipped": 0,
                "failed": 0,
                "bytes_md": 0,
            }

        scanned = 0
        extracted = 0
        skipped = 0
        failed = 0
        bytes_md = 0
        t0 = time.time()

        log.info(
            "reextract_cninfo_md START shard=[%d:%d] rows=%d",
            offset,
            offset + limit,
            len(rows),
        )

        for idx, row in enumerate(rows):
            scanned += 1
            try:
                # 防御：文件已不在盘上（例如删除脚本已清）则跳过。
                if not row.file_path or not Path(row.file_path).exists():
                    skipped += 1
                    continue
                ok = service.extract_text_for_report(row.id, fmt="md")
                if ok:
                    extracted += 1
                    bytes_md += len(row.extracted_text or "")
                else:
                    # service 已把行标记 failed，这里只计数。
                    failed += 1
            except Exception as exc:
                # 最后一道防线：绝不让单行错误杀掉整个分片。
                log.warning("reextract raised for id=%s: %s", row.id, exc)
                failed += 1
                try:
                    db.rollback()
                except Exception:  # pragma: no cover - defensive
                    pass

            if batch_sleep:
                time.sleep(batch_sleep)

            if (idx + 1) % _ETA_INTERVAL == 0:
                done = idx + 1
                avg = (time.time() - t0) / max(done, 1)
                eta_min = (len(rows) - done) * avg / 60
                log.info(
                    "[%d/%d] progress — extracted=%d skipped=%d failed=%d "
                    "bytes_md=%.1fMB avg=%.2fs/report eta=%.0fmin",
                    done,
                    len(rows),
                    extracted,
                    skipped,
                    failed,
                    bytes_md / (1024 * 1024),
                    avg,
                    eta_min,
                )

        total_time = time.time() - t0
        log.info(
            "reextract_cninfo_md DONE shard=[%d:%d] — scanned=%d extracted=%d "
            "skipped=%d failed=%d bytes_md=%.1fMB %.0fs",
            offset,
            offset + limit,
            scanned,
            extracted,
            skipped,
            failed,
            bytes_md / (1024 * 1024),
            total_time,
        )
        return {
            "scanned": scanned,
            "extracted": extracted,
            "skipped": skipped,
            "failed": failed,
            "bytes_md": bytes_md,
        }
    finally:
        db.close()
