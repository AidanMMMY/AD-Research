#!/usr/bin/env python3
"""
Production-ready batched ETF holdings ETL.

Improvements over v3 (/tmp/etf_holdings_batched.py):

* No hard `signal.alarm(10800)` timeout — APScheduler owns liveness.
  SIGTERM sets a cooperative shutdown flag; the main loop drains the
  current ETF and exits cleanly.
* Explicit exit codes:
      0  all target ETFs processed (with or without holdings)
      1  partial failure (>=1 ETF errored, but loop ran to completion
         or hit the shutdown flag)
      2  fatal / startup error (db connection lost, missing deps, etc.)
* Structured JSON-line logging via stdlib `logging` — easy to ship to
  Loki/CloudWatch.
* Heartbeat thread (default 60s) writes
      {"event": "heartbeat", "done": N, "total": M, ...}
  so an external health check can prove the process is alive.
* PID + status files:
      $ETF_HOLDINGS_PID_FILE   default /var/run/etf-holdings.pid
      $ETF_HOLDINGS_STATUS_FILE default /var/run/etf-holdings.status
  Both paths are overridable so non-root callers (e.g. local dev) can
  drop them in /tmp.
* On exit, prints a single `===SUMMARY=== {json}` line and writes the
  same JSON to the status file, then removes the PID file.
* `--dry-run` lists target ETFs and exits 0 without hitting the
  network. `--limit N` caps the work for smoke tests.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import os
import signal
import sys
import threading
import time
import traceback
from typing import Any

# Allow running from repo root or from /app on the ECS container.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _candidate in ("/app", _REPO_ROOT):
    if os.path.isdir(_candidate) and _candidate not in sys.path:
        sys.path.insert(0, _candidate)

# ---- Configurable paths / tunables (env-overridable) ----------------------
PID_FILE = os.environ.get(
    "ETF_HOLDINGS_PID_FILE", "/var/run/etf-holdings.pid"
)
STATUS_FILE = os.environ.get(
    "ETF_HOLDINGS_STATUS_FILE", "/var/run/etf-holdings.status"
)
PROGRESS_FILE = os.environ.get(
    "ETF_HOLDINGS_PROGRESS_FILE", "/tmp/etf_holdings_progress.json"
)

DEFAULT_BATCH_SIZE = int(os.environ.get("ETF_HOLDINGS_BATCH_SIZE", "50"))
DEFAULT_BATCH_SLEEP = int(os.environ.get("ETF_HOLDINGS_BATCH_SLEEP", "30"))
DEFAULT_ETF_SLEEP = float(os.environ.get("ETF_HOLDINGS_ETF_SLEEP", "0.5"))
DEFAULT_RETRIES = int(os.environ.get("ETF_HOLDINGS_RETRIES", "3"))
DEFAULT_HEARTBEAT = int(os.environ.get("ETF_HOLDINGS_HEARTBEAT", "60"))

# ---- Exit codes -----------------------------------------------------------
EXIT_OK = 0          # all target ETFs processed
EXIT_PARTIAL = 1     # some ETFs failed but loop finished cleanly
EXIT_FATAL = 2       # startup / fatal error (db, signal abort, etc.)

# ---- Module-level shutdown flag (SIGTERM sets it) ------------------------
_shutdown = threading.Event()
_shutdown_reason: str = ""


# ---- Structured logging ---------------------------------------------------
class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line, ISO timestamp, easy to ingest."""

    _RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname",
        "filename", "module", "exc_info", "exc_text", "stack_info",
        "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "message",
        "asctime", "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": _dt.datetime.utcfromtimestamp(record.created).isoformat(
                timespec="milliseconds"
            )
            + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for k, v in record.__dict__.items():
            if k in self._RESERVED or k.startswith("_"):
                continue
            try:
                json.dumps(v)
                payload[k] = v
            except (TypeError, ValueError):
                payload[k] = repr(v)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _build_logger() -> logging.Logger:
    lg = logging.getLogger("etf_holdings")
    lg.setLevel(logging.INFO)
    lg.propagate = False
    if not lg.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(_JsonFormatter())
        lg.addHandler(h)
    return lg


log = _build_logger()


# ---- Helpers --------------------------------------------------------------
def _is_rate_limit_err(err: str) -> bool:
    e = err.lower()
    return (
        "频次" in err
        or "limit" in e
        or "rate" in e
        or "too many" in e
        or "throttle" in e
    )


def _write_atomic(path: str, content: str) -> None:
    """Write ``content`` to ``path`` atomically (tmp + replace)."""
    tmp = f"{path}.tmp.{os.getpid()}"
    try:
        with open(tmp, "w") as f:
            f.write(content)
        os.replace(tmp, path)
    except OSError as exc:
        # /var/run may be unwritable in local dev — degrade silently.
        log.warning(
            "status_write_failed", extra={"path": path, "error": str(exc)}
        )


def _write_pid(path: str) -> bool:
    try:
        _write_atomic(path, str(os.getpid()))
        log.info("pid_written", extra={"path": path, "pid": os.getpid()})
        return True
    except OSError:
        log.warning("pid_file_unavailable", extra={"path": path})
        return False


def _remove_pid(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
            log.info("pid_removed", extra={"path": path})
    except OSError as exc:
        log.warning("pid_remove_failed", extra={"path": path, "error": str(exc)})


# ---- Heartbeat ------------------------------------------------------------
class Heartbeat:
    """Background thread that emits a heartbeat every ``interval`` seconds."""

    def __init__(self, interval: int, state: dict[str, Any]):
        self.interval = max(5, int(interval))
        self.state = state
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="etf-heartbeat", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            snap = dict(self.state)
            done = snap.get("done", 0)
            total = snap.get("total", 0) or 0
            pct = round(done / total * 100, 1) if total else 0.0
            log.info(
                "heartbeat",
                extra={
                    "event": "heartbeat",
                    "done": done,
                    "total": total,
                    "pct": pct,
                    "inserted": snap.get("inserted", 0),
                    "failed": snap.get("failed", 0),
                    "elapsed_sec": round(time.time() - snap.get("t0", time.time()), 1),
                },
            )


# ---- Signal handling ------------------------------------------------------
def _on_sigterm(signum, frame):  # noqa: ARG001
    global _shutdown_reason
    _shutdown_reason = f"signal:{signum}"
    log.warning("shutdown_requested", extra={"signal": signum})
    _shutdown.set()


def _on_sigint(signum, frame):  # noqa: ARG001
    global _shutdown_reason
    _shutdown_reason = f"signal:{signum}"
    log.warning("shutdown_requested", extra={"signal": signum, "hint": "Ctrl-C"})
    _shutdown.set()


# ---- Progress persistence -------------------------------------------------
def _load_progress(path: str) -> set[str]:
    if not os.path.exists(path):
        return set()
    try:
        with open(path) as f:
            return set(json.load(f))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("progress_unreadable", extra={"path": path, "error": str(exc)})
        return set()


def _save_progress(path: str, done: set[str]) -> None:
    try:
        _write_atomic(path, json.dumps(sorted(done), ensure_ascii=False))
    except OSError as exc:
        log.warning(
            "progress_write_failed", extra={"path": path, "error": str(exc)}
        )


# ---- Main ETL -------------------------------------------------------------
def _run_with_backoff(p, etf, tushare_provider, retries: int) -> tuple[Any, str | None]:
    """Try Tushare then Akshare for one ETF with exponential backoff.

    Returns (df, source). df is None if both providers failed.
    """
    df = None
    source = None

    if tushare_provider is not None:
        for attempt in range(retries):
            try:
                df = tushare_provider.fetch_etf_holdings(ts_code=etf.code)
                source = "tushare"
                return df, source
            except Exception as exc:
                err = str(exc)
                log.warning(
                    "tushare_attempt_failed",
                    extra={
                        "code": etf.code,
                        "attempt": attempt + 1,
                        "err": err[:200],
                    },
                )
                if _is_rate_limit_err(err):
                    log.info("rate_limit_sleep", extra={"code": etf.code, "sec": 60})
                    time.sleep(60)
                else:
                    time.sleep(2 ** attempt)

    if df is None or (hasattr(df, "empty") and df.empty):
        for attempt in range(retries):
            try:
                df = p.provider.fetch_etf_holdings(etf.code)
                source = "akshare"
                return df, source
            except Exception as exc:
                err = str(exc)
                log.warning(
                    "akshare_attempt_failed",
                    extra={
                        "code": etf.code,
                        "attempt": attempt + 1,
                        "err": err[:200],
                    },
                )
                time.sleep(2 ** attempt)

    return None, None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batched ETF holdings ETL (production)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List target ETFs and exit 0 without fetching.",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Cap the number of ETFs to process (0 = no cap).",
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
    )
    parser.add_argument(
        "--batch-sleep", type=int, default=DEFAULT_BATCH_SLEEP,
    )
    parser.add_argument(
        "--etf-sleep", type=float, default=DEFAULT_ETF_SLEEP,
    )
    parser.add_argument(
        "--retries", type=int, default=DEFAULT_RETRIES,
    )
    parser.add_argument(
        "--heartbeat-sec", type=int, default=DEFAULT_HEARTBEAT,
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore the progress file; reprocess everything.",
    )
    args = parser.parse_args()

    t0 = time.time()
    log.info(
        "etf_holdings_start",
        extra={
            "event": "start",
            "pid": os.getpid(),
            "argv": sys.argv,
            "dry_run": args.dry_run,
        },
    )

    # ---- PID file ----
    pid_written = _write_pid(PID_FILE)

    # ---- Signal handlers (cooperative shutdown) ----
    signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        signal.signal(signal.SIGINT, _on_sigint)
    except ValueError:
        # SIGINT not settable from non-main thread; ignore.
        pass

    # ---- Heartbeat ----
    state: dict[str, Any] = {"t0": t0, "done": 0, "total": 0, "inserted": 0, "failed": 0}
    heartbeat = Heartbeat(args.heartbeat_sec, state)
    if not args.dry_run:
        heartbeat.start()

    summary: dict[str, Any] = {
        "ok": [],
        "no_holdings": [],
        "failed": [],
        "inserted": 0,
        "started_at": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "finished_at": None,
        "duration_sec": 0.0,
        "exit_code": EXIT_OK,
        "reason": "",
    }

    exit_code = EXIT_OK
    fatal_error: str | None = None

    try:
        # ---- Imports happen inside main() so the script can be
        # ---- collected for `--help` / `--dry-run` even if the
        # ---- app package is missing.
        try:
            from app.data.pipelines.etf_holdings import ETFHoldingsPipeline
            from app.models.etf import ETFInfo
            from app.api.deps import get_db  # type: ignore
        except Exception as exc:
            fatal_error = f"import_failed: {exc}"
            log.error("import_failed", extra={"error": str(exc)})
            return EXIT_FATAL

        try:
            db = next(get_db())
        except Exception as exc:
            fatal_error = f"db_connect_failed: {exc}"
            log.error("db_connect_failed", extra={"error": str(exc)})
            return EXIT_FATAL

        try:
            p = ETFHoldingsPipeline(db=db)
        except Exception as exc:
            fatal_error = f"pipeline_init_failed: {exc}"
            log.error("pipeline_init_failed", extra={"error": str(exc)})
            return EXIT_FATAL

        try:
            etfs = (
                db.query(ETFInfo)
                .filter(
                    ETFInfo.market == "A股",
                    ETFInfo.instrument_type == "ETF",
                    ETFInfo.status == "active",
                )
                .order_by(ETFInfo.code)
                .all()
            )
        except Exception as exc:
            fatal_error = f"query_failed: {exc}"
            log.error("query_failed", extra={"error": str(exc)})
            return EXIT_FATAL

        log.info("etfs_loaded", extra={"event": "loaded", "count": len(etfs)})

        if args.dry_run:
            sample = [e.code for e in etfs[:10]]
            log.info(
                "dry_run",
                extra={
                    "event": "dry_run",
                    "would_process": len(etfs),
                    "sample": sample,
                    "limit": args.limit,
                },
            )
            summary["reason"] = "dry_run"
            # Don't dump the entire ETF universe into the summary;
            # keep only the first few so the status file stays small.
            summary["ok"] = sample
            summary["total_etfs"] = len(etfs)
            return EXIT_OK

        # ---- Resume state ----
        done: set[str] = set() if args.no_resume else _load_progress(PROGRESS_FILE)
        if done:
            log.info("resumed", extra={"event": "resumed", "already_done": len(done)})

        pending = [e for e in etfs if e.code not in done]
        if args.limit > 0:
            pending = pending[: args.limit]
        log.info(
            "pending",
            extra={
                "event": "pending",
                "pending": len(pending),
                "skipped_done": len(etfs) - len(pending),
            },
        )
        state["total"] = len(pending)

        # ---- Providers ----
        tushare_provider = None
        try:
            from app.data.providers.tushare_provider import TushareProvider

            tushare_provider = TushareProvider()
            log.info("tushare_ready", extra={"event": "tushare_ready"})
        except Exception as exc:
            log.warning(
                "tushare_init_failed",
                extra={"event": "tushare_init_failed", "error": str(exc)},
            )

        batch_inserted = 0
        t_batch_start = time.time()

        for i, etf in enumerate(pending):
            if _shutdown.is_set():
                log.warning(
                    "shutdown_break",
                    extra={
                        "event": "shutdown_break",
                        "processed": i,
                        "remaining": len(pending) - i,
                        "reason": _shutdown_reason,
                    },
                )
                # Treat forced shutdown as a partial run if we got
                # through anything; otherwise it's a fatal abort.
                exit_code = EXIT_PARTIAL if i > 0 else EXIT_FATAL
                summary["reason"] = f"shutdown:{_shutdown_reason}"
                break

            code = etf.code
            df = None
            source = None
            try:
                df, source = _run_with_backoff(
                    p, etf, tushare_provider, args.retries
                )
            except Exception as exc:
                log.error(
                    "etf_unexpected",
                    extra={"code": code, "err": str(exc), "trace": traceback.format_exc(limit=3)},
                )
                summary["failed"].append(code)
                state["failed"] += 1
                done.add(code)
                _save_progress(PROGRESS_FILE, done)
                time.sleep(args.etf_sleep)
                continue

            if df is None:
                log.info("etf_no_holdings", extra={"code": code})
                summary["no_holdings"].append(code)
                done.add(code)
                _save_progress(PROGRESS_FILE, done)
                time.sleep(args.etf_sleep)
                continue

            try:
                # Mirror snapshot_date from holdings_as_of_date.
                if "snapshot_date" not in df.columns:
                    df["snapshot_date"] = df.get("holdings_as_of_date")
                df["snapshot_date"] = df["snapshot_date"].fillna(_dt.date.today())
                count = p.load(df)
                summary["inserted"] += count
                batch_inserted += count
                log.info(
                    "etf_loaded",
                    extra={
                        "code": code,
                        "source": source,
                        "rows": count,
                        "batch_total": batch_inserted,
                        "grand_total": summary["inserted"],
                    },
                )
            except Exception as exc:
                log.error(
                    "etf_load_failed",
                    extra={"code": code, "err": str(exc), "trace": traceback.format_exc(limit=3)},
                )
                summary["failed"].append(code)
                state["failed"] += 1
                # Don't mark as done — we want a retry next run.
                time.sleep(args.etf_sleep)
                continue

            summary["ok"].append(code)
            done.add(code)
            _save_progress(PROGRESS_FILE, done)
            state["done"] += 1
            time.sleep(args.etf_sleep)

            if (i + 1) % args.batch_size == 0:
                elapsed = time.time() - t_batch_start
                rate = (i + 1) / elapsed * 60 if elapsed > 0 else 0
                log.info(
                    "batch_done",
                    extra={
                        "event": "batch_done",
                        "index": i + 1,
                        "pending": len(pending),
                        "elapsed_sec": round(elapsed, 1),
                        "rate_per_min": round(rate, 1),
                        "sleep_sec": args.batch_sleep,
                    },
                )
                batch_inserted = 0
                t_batch_start = time.time()
                time.sleep(args.batch_sleep)

        # ---- Loop completed naturally ----
        if exit_code == EXIT_OK:
            if summary["failed"]:
                exit_code = EXIT_PARTIAL
                summary["reason"] = "partial_failure"
            else:
                summary["reason"] = "success"

    except Exception as exc:
        fatal_error = f"unhandled: {exc}"
        log.error(
            "fatal",
            extra={"err": str(exc), "trace": traceback.format_exc(limit=5)},
        )
        exit_code = EXIT_FATAL
    finally:
        heartbeat.stop()
        if pid_written:
            _remove_pid(PID_FILE)
        summary["finished_at"] = (
            _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
        )
        summary["duration_sec"] = round(time.time() - t0, 2)
        summary["exit_code"] = exit_code
        if fatal_error:
            summary["reason"] = fatal_error
        # Single-line JSON summary to stdout, also to status file.
        print("===SUMMARY===" + json.dumps(summary, ensure_ascii=False))
        try:
            _write_atomic(STATUS_FILE, json.dumps(summary, ensure_ascii=False, indent=2))
        except OSError:
            pass
        log.info(
            "etf_holdings_end",
            extra={
                "event": "end",
                "exit_code": exit_code,
                "ok": len(summary["ok"]),
                "no_holdings": len(summary["no_holdings"]),
                "failed": len(summary["failed"]),
                "inserted": summary["inserted"],
                "duration_sec": summary["duration_sec"],
                "reason": summary["reason"],
            },
        )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
