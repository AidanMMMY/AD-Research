"""Shared helpers for writing scheduler-job rows to ``etl_log``.

The pipeline-flavoured jobs (ETF / stock / search-trends / futures / ...)
all inherit from :class:`app.data.pipelines.base.ETLPipeline` whose
``_create_log`` / ``_update_log`` already persist a row to
``etl_log`` per run.  A handful of scheduler jobs do **not** go through
``ETLPipeline`` — they live in service modules (FRED refresh, China
macro refresh, global indices refresh, news crawlers, ...) and until
recently only relied on ``logging`` for observability.  Without an
``etl_log`` row the freshness-alert page cannot tell whether a job is
running cleanly, slow, or entirely broken — the table just keeps the
last successful row from days ago.

This module factors the "write one row per run" pattern into a small
decorator and two helpers, so any scheduler function can mark itself
``@record_etl("job_id")`` and get free observability.

Behaviour::

    @record_etl("china_macro_daily", source="akshare")
    def run_china_macro_refresh() -> dict:
        ...

    # the wrapper inserts {status='running', start_time=now()},
    # runs the function, then UPDATEs the same row with
    # {status, end_time, records_count, error_msg, extra_data}.

* Exception path → ``status='failed'`` with ``error_msg`` truncated to
  1000 chars; the exception is re-raised so the scheduler can keep its
  existing handling.
* Dict return path →
  ``status='skipped'`` when ``result['skipped']`` is true,
  ``status='partial'`` when ``result['failed']`` is a non-empty list,
  ``status='success'`` otherwise.  ``records_count`` is taken from
  ``written`` first, falling back to ``fetched``, then ``0``.
* Non-dict return → ``status='success'``, records_count=0.  Use the
  helper for non-pipeline jobs whose output is just a status string.
* ``extra_data.duration_seconds`` is recorded on every successful /
  skipped / partial row so the admin dashboards can graph p95 runtime.
* All DB exceptions while writing the log row are swallowed — they
  must never block the actual job.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable

from app.models.etl import ETLLog

logger = logging.getLogger(__name__)


def start_log(job_id: str, source: str | None = None) -> tuple[Any, Any]:
    """Insert an ``etl_log`` row with ``status='running'``.

    Returns ``(db_session, log_row)``.  The caller is responsible for
    committing/closing the session and for calling :func:`finish_log`
    on the returned ``log_row``.  Used by tests and one-shot scripts
    that want the same observability row but do not want to go through
    the ``@record_etl`` decorator.

    DB failures are swallowed — observability must never block the
    actual job.  In that case ``(db_session, None)`` is returned and
    ``finish_log`` becomes a no-op.
    """
    from app.core.database import SessionLocal

    db = SessionLocal()
    log_row: ETLLog | None = None
    try:
        log_row = ETLLog(
            job_name=job_id,
            source=source,
            status="running",
            start_time=datetime.now(timezone.utc),
        )
        db.add(log_row)
        db.commit()
        db.refresh(log_row)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("etl_log start insert failed for %s: %s", job_id, exc)
        log_row = None
    return db, log_row


def finish_log(
    db: Any,
    log_row: ETLLog | None,
    *,
    status: str,
    records_count: int = 0,
    error_msg: str | None = None,
    extra: dict[str, Any] | None = None,
    duration_seconds: float | None = None,
) -> None:
    """Update the ``ETLLog`` row opened by :func:`start_log`.

    Safe to call with ``log_row=None`` (no row was created) — the
    function returns without touching the DB.
    """
    if log_row is None:
        try:
            db.close()
        except Exception:  # pragma: no cover - defensive
            pass
        return
    try:
        log_row.status = status
        log_row.end_time = datetime.now(timezone.utc)
        log_row.records_count = records_count
        if error_msg:
            log_row.error_msg = error_msg[:1000]
        if extra is not None or duration_seconds is not None:
            merged: dict[str, Any] = dict(extra or {})
            if duration_seconds is not None:
                merged.setdefault(
                    "duration_seconds", round(duration_seconds, 3)
                )
            log_row.extra_data = merged
        db.commit()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("etl_log finish update failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        try:
            db.close()
        except Exception:  # pragma: no cover - defensive
            pass


def _resolve_records(result: Any) -> int:
    """Pick the most informative record count from a result dict."""
    if not isinstance(result, dict):
        return 0
    written = result.get("written")
    if isinstance(written, int) and written >= 0:
        return written
    fetched = result.get("fetched")
    if isinstance(fetched, int) and fetched >= 0:
        return fetched
    return 0


def _resolve_status(result: Any) -> str:
    """Infer final ``status`` from a function return value.

    * ``result['skipped']`` truthy → ``'skipped'``
    * ``result['failed']`` is a non-empty list, or a non-zero error
      counter (e.g. FRED's ``"failed": -1``) → ``'partial'`` /
      ``'failed'`` (a non-list signal we treat as ``failed``)
    * otherwise → ``'success'``
    """
    if not isinstance(result, dict):
        return "success"
    if result.get("skipped"):
        return "skipped"
    failed = result.get("failed")
    if isinstance(failed, list):
        # The macro refreshers use ``['__job__']`` as a sentinel for
        # "the whole batch crashed" (typically via the outermost
        # ``except`` guard). Treat that as a hard failure rather than
        # a partial success.
        if failed == ["__job__"]:
            return "failed"
        return "partial" if failed else "success"
    if isinstance(failed, int) and failed != 0:
        # Macro-job convention: -1 means "the whole job crashed" while
        # a positive int means "N series failed but the job survived".
        return "failed" if failed < 0 else "partial"
    if result.get("error") is not None:
        return "failed"
    return "success"


def record_etl(
    job_id: str, source: str | None = None
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: persist one ``etl_log`` row covering ``fn``'s run.

    ``job_id`` should match the APScheduler ``id`` registered in
    ``app.core.scheduler`` (e.g. ``"china_macro_daily"``).  ``source``
    is stored on the ``ETLLog.source`` column for ad-hoc filtering
    (e.g. ``WHERE source='fred'``); leave ``None`` when the job spans
    multiple providers and one label is misleading.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            db, log_row = start_log(job_id, source=source)
            started = time.monotonic()
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                finish_log(
                    db,
                    log_row,
                    status="failed",
                    records_count=0,
                    error_msg=str(exc),
                    duration_seconds=time.monotonic() - started,
                )
                raise

            status = _resolve_status(result)
            records = _resolve_records(result)
            extra: dict[str, Any] = {}
            # Carry across per-source / per-series summaries so the
            # admin dashboards can drill down without re-fetching.
            if isinstance(result, dict):
                for key in ("per_source", "per_series", "skip_reason",
                            "failed", "error"):
                    if result.get(key) is not None:
                        extra[key] = result[key]
            finish_log(
                db,
                log_row,
                status=status,
                records_count=records,
                error_msg=result.get("error") if isinstance(result, dict) else None,
                extra=extra,
                duration_seconds=time.monotonic() - started,
            )
            return result

        return wrapper

    return decorator
