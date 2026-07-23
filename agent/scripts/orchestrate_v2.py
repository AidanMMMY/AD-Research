#!/usr/bin/env python3
"""
orchestrate_v2.py — AD-Research multi-source data aggregator.

Runs the configured news/sentiment workers with staggered starts, per-worker
timeouts, and failure isolation, then emits a single aggregate.json that
summarises per-worker results + totals.

CLI examples
------------
    # Hourly quick sweep (no login required)
    python3 scripts/orchestrate_v2.py --schedule quick \
        --output-dir /data/ad-research/aggregate.json

    # All 8 workers with explicit output
    python3 scripts/orchestrate_v2.py --schedule all \
        --output-dir /data/ad-research/aggregate.json

    # Pick specific workers
    python3 scripts/orchestrate_v2.py \
        --workers xueqiu,cls,eastmoney_news \
        --output-dir /data/ad-research/aggregate.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Configuration                                                               #
# --------------------------------------------------------------------------- #

AGENT_ROOT = Path("/root/ad-research/agent")
WORKER_DIR = AGENT_ROOT / "workers"
RUN_WORKER = AGENT_ROOT / "scripts" / "run_worker.sh"  # type: ignore[assignment]
LOG_DIR = Path("/root/ad-research/logs")
DATA_ROOT = Path("/data/ad-research")

WORKERS: dict[str, dict[str, Any]] = {
    "eastmoney_news":    {"args": ["--hours", "24"], "category": "quick",     "timeout": 300},
    "gov_china":         {"args": ["--hours", "24"], "category": "quick",     "timeout": 300},
    "fed_intl":          {"args": ["--hours", "24"], "category": "quick",     "timeout": 300},
    "stocktwits":        {"args": ["--hours", "24"], "category": "quick",     "timeout": 300},
    "cls":               {"args": ["--hours", "24"], "category": "quick",     "timeout": 300},
    "xueqiu_playwright": {"args": ["--hours", "24"], "category": "logged_in", "timeout": 600},
    "x":                 {"args": ["--hours", "24"], "category": "logged_in", "timeout": 600},
    "reddit_curl_cffi":  {"args": ["--hours", "24"], "category": "logged_in", "timeout": 600},
}

QUICK_WORKERS = [n for n, c in WORKERS.items() if c["category"] == "quick"]
LOGGED_IN_WORKERS = [n for n, c in WORKERS.items() if c["category"] == "logged_in"]
ALL_WORKERS = list(WORKERS.keys())

DEFAULT_STAGGER_RANGE = (5.0, 10.0)  # seconds between worker launches


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="orchestrate_v2",
        description="AD-Research multi-source aggregator.",
    )
    p.add_argument(
        "--schedule",
        choices=["all", "quick", "logged_in"],
        help="Preset worker group. Mutually exclusive with --workers.",
    )
    p.add_argument(
        "--workers",
        help="Comma-separated explicit worker list (e.g. xueqiu,cls,eastmoney_news).",
    )
    p.add_argument(
        "--output-dir",
        required=True,
        help="Path where the aggregate JSON will be written.",
    )
    p.add_argument(
        "--data-root",
        default=str(DATA_ROOT),
        help="Root directory where per-worker output JSON files live.",
    )
    p.add_argument(
        "--agent-root",
        default=str(AGENT_ROOT),
        help="Path to the AD-Research agent checkout (contains workers/ + scripts/).",
    )
    p.add_argument(
        "--log-dir",
        default=str(LOG_DIR),
        help="Directory where the run log will be written.",
    )
    p.add_argument(
        "--stagger-min",
        type=float,
        default=DEFAULT_STAGGER_RANGE[0],
        help="Min seconds between worker launches (default: 5).",
    )
    p.add_argument(
        "--stagger-max",
        type=float,
        default=DEFAULT_STAGGER_RANGE[1],
        help="Max seconds between worker launches (default: 10).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned worker sequence + exit without running.",
    )
    # 2026-07-23: silent-failure watchdog hook. If the failed-worker count
    # is >= this threshold we POST an aggregate to the backend so it shows
    # up in NotificationLog + /admin/etl-status. See:
    #   docs/dev-notes/20260720-ecs-ops-audit-and-fixes.md (P1 "采集故障无告警通道")
    # Default 2 — any single-worker outage isn't worth alerting on, but
    # 2+ in the same tick is the canary we've been missing for 16h+ incidents.
    p.add_argument(
        "--alert-threshold",
        type=int,
        default=2,
        help="Min number of failed workers in a single run that triggers the watchdog alert (default: 2).",
    )
    p.add_argument(
        "--alert-backend-url",
        default=os.getenv("ORCHESTRATE_ALERT_URL", "http://alloyresearch-backend:8000/api/v1/internal/orchestrate-alert"),
        help="Backend endpoint the watchdog posts to. Default reads ORCHESTRATE_ALERT_URL.",
    )
    p.add_argument(
        "--alert-token",
        default=os.getenv("ORCHESTRATE_ALERT_TOKEN", "") or os.getenv("INTERNAL_API_TOKEN", ""),
        help="Bearer token for the watchdog endpoint. Reads ORCHESTRATE_ALERT_TOKEN first, then INTERNAL_API_TOKEN.",
    )
    p.add_argument(
        "--alert-disable",
        action="store_true",
        help="Skip the watchdog POST even if the threshold is exceeded (useful for local debugging).",
    )
    args = p.parse_args()

    if args.schedule and args.workers:
        p.error("--schedule and --workers are mutually exclusive.")
    if args.stagger_min < 0 or args.stagger_max < args.stagger_min:
        p.error("--stagger-min must be >= 0 and --stagger-max must be >= --stagger-min.")
    if args.alert_threshold < 1:
        p.error("--alert-threshold must be >= 1.")

    return args


def resolve_workers(args: argparse.Namespace) -> list[str]:
    if args.schedule == "all":
        return list(ALL_WORKERS)
    if args.schedule == "quick":
        return list(QUICK_WORKERS)
    if args.schedule == "logged_in":
        return list(LOGGED_IN_WORKERS)
    if args.workers:
        chosen = [w.strip() for w in args.workers.split(",") if w.strip()]
        unknown = [w for w in chosen if w not in WORKERS]
        if unknown:
            raise SystemExit(f"Unknown worker(s): {unknown}. Known: {sorted(WORKERS)}")
        return chosen
    # Default: all (matches hourly cron intent)
    return list(ALL_WORKERS)


# --------------------------------------------------------------------------- #
# Logging                                                                     #
# --------------------------------------------------------------------------- #


def configure_logging(log_dir: Path) -> tuple[logging.Logger, Path]:
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    log_path = log_dir / f"orchestrate-{stamp}.log"

    logger = logging.getLogger("orchestrate_v2")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_h = logging.FileHandler(log_path, encoding="utf-8")
    file_h.setFormatter(fmt)
    logger.addHandler(file_h)

    stream_h = logging.StreamHandler(sys.stdout)
    stream_h.setFormatter(fmt)
    logger.addHandler(stream_h)

    return logger, log_path


# --------------------------------------------------------------------------- #
# Worker runner                                                               #
# --------------------------------------------------------------------------- #


def worker_output_path(data_root: Path, worker_name: str) -> Path:
    """Return the canonical output path for a worker."""
    return data_root / worker_name / "today.json"


def run_worker(
    name: str,
    cfg: dict[str, Any],
    data_root: Path,
    agent_root: Path,
    logger: logging.Logger,
) -> dict[str, Any]:
    """Run a single worker; never raises."""
    out_path = worker_output_path(data_root, name)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    run_sh = agent_root / "scripts" / "run_worker.sh"
    cmd = [str(run_sh), name, str(out_path), *cfg.get("args", [])]
    timeout = int(cfg.get("timeout", 600))

    started = time.monotonic()
    logger.info("▶ %s start  cmd=%s  timeout=%ss  out=%s",
                name, shlex.join(cmd), timeout, out_path)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        rc = proc.returncode
        timed_out = False
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate(timeout=10)
        rc = -1
        timed_out = True
        logger.warning("⏱ %s killed after %ss timeout", name, timeout)

    duration = round(time.monotonic() - started, 2)

    items = 0
    size_bytes = 0
    preview: list[Any] = []
    err: str | None = None

    if out_path.exists():
        size_bytes = out_path.stat().st_size
        try:
            with out_path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if isinstance(payload, dict):
                items = (
                    payload.get("items")
                    or payload.get("count")
                    or payload.get("total")
                    or 0
                )
                if "items" in payload and isinstance(payload["items"], list):
                    items = len(payload["items"])
                    preview = payload["items"][:3]
                elif "data" in payload and isinstance(payload["data"], list):
                    items = len(payload["data"])
                    preview = payload["data"][:3]
            elif isinstance(payload, list):
                items = len(payload)
                preview = payload[:3]
        except (json.JSONDecodeError, OSError) as exc:
            err = f"output_parse_error: {exc}"

    if timed_out:
        err = f"timeout after {timeout}s"
    elif rc != 0 and err is None:
        stderr_tail = (stderr or "").strip().splitlines()[-3:]
        err = f"exit {rc}: {' | '.join(stderr_tail)[:300]}"

    result: dict[str, Any] = {
        "exit_code": rc,
        "items": items,
        "duration": duration,
        "size_bytes": size_bytes,
    }
    if err:
        result["error"] = err
    if preview:
        result["preview"] = preview

    logger.info(
        "✔ %s done  rc=%s  items=%s  duration=%ss  size=%sB%s",
        name, rc, items, duration, size_bytes,
        f"  err={err}" if err else "",
    )
    return result


# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #


def main() -> int:
    args = parse_args()
    log_dir = Path(args.log_dir)
    data_root = Path(args.data_root)
    agent_root = Path(args.agent_root)

    logger, log_path = configure_logging(log_dir)
    logger.info("=== orchestrate_v2 run ===")
    logger.info("log_path=%s", log_path)

    plan = resolve_workers(args)
    logger.info("schedule=%s  workers=%s", args.schedule or "(explicit)", plan)

    if args.dry_run:
        logger.info("DRY-RUN — would launch:")
        for n in plan:
            logger.info("  • %s  timeout=%ss  args=%s",
                        n, WORKERS[n]["timeout"], WORKERS[n]["args"])
        return 0

    overall_start = time.monotonic()
    results: dict[str, dict[str, Any]] = {}
    for idx, name in enumerate(plan):
        if idx > 0:
            sleep_s = random.uniform(args.stagger_min, args.stagger_max)
            logger.info("…sleeping %.1fs before %s", sleep_s, name)
            time.sleep(sleep_s)
        try:
            results[name] = run_worker(
                name=name,
                cfg=WORKERS[name],
                data_root=data_root,
                agent_root=agent_root,
                logger=logger,
            )
        except Exception as exc:  # noqa: BLE001 — failure isolation
            logger.exception("worker %s crashed: %s", name, exc)
            results[name] = {
                "exit_code": -2,
                "items": 0,
                "duration": 0.0,
                "size_bytes": 0,
                "error": f"orchestrator_error: {exc}",
            }

    duration_total = round(time.monotonic() - overall_start, 2)
    totals_items = sum(r.get("items", 0) for r in results.values())
    exit_codes: dict[str, int] = {}
    for r in results.values():
        key = str(r.get("exit_code", -99))
        exit_codes[key] = exit_codes.get(key, 0) + 1

    aggregate = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": duration_total,
        "schedule": args.schedule or "explicit",
        "results": results,
        "totals": {
            "items": totals_items,
            "exit_codes": exit_codes,
        },
    }

    out_path = Path(args.output_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(aggregate, fh, ensure_ascii=False, indent=2)
    logger.info("=== aggregate written to %s ===", out_path)
    logger.info("totals.items=%s  totals.exit_codes=%s  duration=%ss",
                totals_items, exit_codes, duration_total)

    # ---------------------------------------------------------------- #
    # 2026-07-23: silent-failure watchdog (P1 from 20260720 ECS audit).
    # ---------------------------------------------------------------- #
    failed_workers = _failed_workers(results)
    if failed_workers:
        logger.warning(
            "watchdog: %d workers failed (threshold=%d) — considering alert",
            len(failed_workers), args.alert_threshold,
        )
    if not args.alert_disable:
        try:
            _post_watchdog_alert(
                logger=logger,
                url=args.alert_backend_url,
                token=args.alert_token,
                threshold=args.alert_threshold,
                schedule=args.schedule or "explicit",
                duration_seconds=duration_total,
                failed=failed_workers,
            )
        except Exception as exc:  # noqa: BLE001 — watchdog must never break the cron
            logger.error("watchdog POST failed (cron continues): %s", exc)
    else:
        logger.info("watchdog: disabled by --alert-disable")

    return 0


def _failed_workers(results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Return worker result dicts whose exit was non-zero or contained an error."""
    out: list[dict[str, Any]] = []
    for name, r in results.items():
        if not isinstance(r, dict):
            continue
        rc = int(r.get("exit_code", 0))
        if rc != 0 or r.get("error"):
            out.append({
                "name": name,
                "exit_code": rc,
                "items": int(r.get("items", 0) or 0),
                "duration": float(r.get("duration", 0.0) or 0.0),
                "error": str(r.get("error") or "")[:300] or None,
            })
    return out


def _post_watchdog_alert(
    logger: logging.Logger,
    url: str,
    token: str,
    threshold: int,
    schedule: str,
    duration_seconds: float,
    failed: list[dict[str, Any]],
) -> None:
    """POST aggregate to backend; never raises."""
    import socket
    payload: dict[str, Any] = {
        "failed_workers": failed,
        "schedule": schedule,
        "total_duration_seconds": duration_seconds,
        "host": socket.gethostname(),
        "threshold": threshold,
    }
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        # Without a token we'd either fail with 403 (saving nothing) or
        # skip entirely (silent). Skip with a clear log line.
        logger.warning(
            "watchdog: INTERNAL_API_TOKEN unset — skipping backend POST. "
            "Set the env var on the cron host to enable alerts."
        )
        return
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
    except requests.RequestException as exc:
        logger.error("watchdog: transport error to %s: %s", url, exc)
        return
    if 200 <= resp.status_code < 300:
        logger.info(
            "watchdog: alert accepted  status=%s  failed=%d  body=%s",
            resp.status_code, len(failed), resp.text[:200],
        )
        return
    logger.error(
        "watchdog: alert rejected  status=%s  body=%s", resp.status_code, resp.text[:300]
    )


if __name__ == "__main__":
    sys.exit(main())