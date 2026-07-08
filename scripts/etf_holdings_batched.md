# `etf_holdings_batched.py` — production ETF holdings ETL

Batched, resumable, rate-limit-aware ETL that backfills A-share ETF
holdings from Tushare (primary) with an Akshare fallback. Designed to
be driven by APScheduler on the ECS backend container; safe to run
multiple times in the same calendar day (idempotent upsert keyed on
`etf_code + holding_code + snapshot_date`).

This is the production version of the v3 prototype that previously
lived at `/tmp/etf_holdings_batched.py`. The prototype had a `tmux` +
`read -n 1` wrapper that hung the wrapper process and made exit codes
ambiguous. The production version is self-contained.

---

## TL;DR

```bash
# On the ECS backend container (run by APScheduler)
python3 /app/scripts/etf_holdings_batched.py

# Local dev — dry-run to confirm plumbing without hitting the network
python3 scripts/etf_holdings_batched.py --dry-run --limit 5

# Local dev — process 5 ETFs for real (writes progress + status files)
ETF_HOLDINGS_PID_FILE=/tmp/etf-holdings.pid \
ETF_HOLDINGS_STATUS_FILE=/tmp/etf-holdings.status \
python3 scripts/etf_holdings_batched.py --limit 5
```

---

## Exit codes

| Code | Meaning                                                                  |
| ---- | ------------------------------------------------------------------------ |
| `0`  | All target ETFs processed successfully (or no work to do / dry-run)      |
| `1`  | Partial failure — at least one ETF errored, but the loop ran to natural completion **or** exited via SIGTERM after processing ≥1 ETF |
| `2`  | Fatal — DB connection lost, package import failed, or SIGTERM received before the first ETF finished |

These are stable; APScheduler / wrapper scripts should branch on them.

---

## Logging

Every line is a single JSON object on stdout (no plain-text prefix).
Key fields:

```json
{"ts": "2026-07-08T14:48:40.818Z", "level": "INFO", "logger": "etf_holdings",
 "msg": "etf_holdings_start", "event": "start", "pid": 17671, "argv": [...], "dry_run": false}
```

The `event` field is the stable identifier; `msg` is the human label.
`extra={...}` fields are merged into the JSON. Stack traces appear as
`exc` (truncated to 3-5 frames).

The last line of stdout is a summary you can grep for in a wrapper:

```
===SUMMARY==={"ok": ["159001.SZ", ...], "no_holdings": [], "failed": [],
 "inserted": 1234, "started_at": "...", "finished_at": "...",
 "duration_sec": 123.4, "exit_code": 0, "reason": "success"}
```

`reason` is one of:

* `success` — clean run, no failures
* `partial_failure` — loop ran to completion but ≥1 ETF errored
* `shutdown:signal:15` — SIGTERM (or other signal) interrupted
* `dry_run` — `--dry-run` path
* `<error string>` — fatal startup error (db/import/pipeline init)

---

## Heartbeat

A daemon thread emits one `event: "heartbeat"` line every
`--heartbeat-sec` seconds (default **60**). It's the proof of life for
external health checks:

```json
{"event": "heartbeat", "done": 50, "total": 2133, "pct": 2.3,
 "inserted": 412, "failed": 1, "elapsed_sec": 92.4}
```

The heartbeat is suppressed in `--dry-run` (no work is happening).

---

## PID + status files

| File                                          | Default                                | Overridable via                              |
| --------------------------------------------- | -------------------------------------- | -------------------------------------------- |
| PID                                           | `/var/run/etf-holdings.pid`            | `ETF_HOLDINGS_PID_FILE`                      |
| Status (JSON, written on every exit)          | `/var/run/etf-holdings.status`         | `ETF_HOLDINGS_STATUS_FILE`                   |
| Progress (resume marker, list of done codes)  | `/tmp/etf_holdings_progress.json`      | `ETF_HOLDINGS_PROGRESS_FILE`                 |

* The PID file is written on startup and **removed on every exit path**
  (clean, exception, SIGTERM, dry-run, fatal). If a stale PID is left
  behind after a `kill -9`, delete it manually before restarting.
* The status file holds the same JSON that goes to stdout, indented for
  human inspection. Always reflects the **last** run.
* The progress file lets you restart mid-batch: codes already in the
  list are skipped. Use `--no-resume` to reprocess everything.

If `/var/run/` is not writable (e.g. local dev as a non-root user),
the script falls back to logging a `pid_file_unavailable` warning and
continues. Always set the env var explicitly in local dev to put the
files somewhere you can read them.

---

## Signal handling

| Signal          | Behavior                                                                                       |
| --------------- | ---------------------------------------------------------------------------------------------- |
| `SIGTERM` (15)  | Sets a cooperative shutdown flag. The main loop finishes the current ETF, then breaks with `exit_code=1` (partial) or `exit_code=2` (fatal, if before first ETF). |
| `SIGINT`  (2)   | Same as SIGTERM (Ctrl-C works in interactive runs).                                            |

There is **no hard `signal.alarm` timeout** — APScheduler owns the
restart cadence. If the process truly wedges (e.g. a hung Tushare
socket), the outer scheduler can SIGTERM it cleanly and the partial
results in the status file tell you exactly where to resume.

---

## CLI reference

```
python3 etf_holdings_batched.py [options]

  --dry-run              List target ETFs and exit 0. No network calls.
  --limit N              Cap the number of ETFs to process (0 = no cap).
  --batch-size N         Pause every N ETFs (default 50, env ETF_HOLDINGS_BATCH_SIZE).
  --batch-sleep SEC      Sleep between batches (default 30).
  --etf-sleep SEC        Sleep between individual ETFs (default 0.5).
  --retries N            Per-ETF retry count, each provider (default 3).
  --heartbeat-sec N      Heartbeat interval (default 60; min 5).
  --no-resume            Ignore the progress file; reprocess everything.
```

All tunables are also env-overridable (`ETF_HOLDINGS_BATCH_SIZE`,
`ETF_HOLDINGS_BATCH_SLEEP`, `ETF_HOLDINGS_ETF_SLEEP`,
`ETF_HOLDINGS_RETRIES`, `ETF_HOLDINGS_HEARTBEAT`).

---

## APScheduler wiring (suggested)

The job should run on a low-traffic window (Tushare rate-limits are
tightest during market hours). One sensible schedule:

```python
# in app/services/scheduler.py
from apscheduler.triggers.cron import CronTrigger

scheduler.add_job(
    "scripts.etf_holdings_batched:main",  # or a thin wrapper
    CronTrigger.from_crontab("30 18 * * 1-5"),  # weekdays 18:30 CST
    id="etf_holdings",
    max_instances=1,
    coalesce=True,
    misfire_grace_time=3600,
)
```

`max_instances=1` + `coalesce=True` prevents overlapping runs from
clobbering the same `etf_holdings` rows; the script's own
`ETF_HOLDINGS_PID_FILE` is a second line of defense in case APScheduler
ever spawns a duplicate.

---

## Verifying it works

Smoke test from your local checkout:

```bash
# 1. Help renders, no DB needed
python3 scripts/etf_holdings_batched.py --help

# 2. Dry-run: lists target universe, exits 0
python3 scripts/etf_holdings_batched.py --dry-run --limit 5

# 3. Real run, 3 ETFs, override paths
ETF_HOLDINGS_PID_FILE=/tmp/etf-holdings.pid \
ETF_HOLDINGS_STATUS_FILE=/tmp/etf-holdings.status \
ETF_HOLDINGS_PROGRESS_FILE=/tmp/etf-holdings-test.json \
python3 scripts/etf_holdings_batched.py --limit 3 --etf-sleep 0.1 \
  --heartbeat-sec 5 --batch-size 2 --batch-sleep 1 --no-resume

# Check artifacts
cat /tmp/etf-holdings.status
cat /tmp/etf-holdings-test.json

# 4. SIGTERM mid-run: should exit 1 with reason=shutdown:signal:15
python3 scripts/etf_holdings_batched.py --limit 10 --etf-sleep 4 \
  --heartbeat-sec 3 --no-resume &
PID=$!
sleep 2 && kill -TERM $PID
wait $PID; echo "exit=$?"   # expect 1
```

---

## Differences from v3 (`/tmp/etf_holdings_batched.py`)

* No `signal.alarm(10800)` — APScheduler is the liveness owner
* No `read -n 1` / tmux wrapper — process self-terminates with a clear code
* Structured JSON logging (one object per line) — Loki/CloudWatch friendly
* Heartbeat thread (60s) — external health checks have a signal
* PID + status files — health checks and post-mortems are trivial
* `===SUMMARY===` last line — easy to grep and parse in wrappers
* `--dry-run` and `--limit` flags — smoke tests without touching the network
* `ETF_HOLDINGS_*` env vars — paths/tunables are 12-factor configurable
* Failed ETFs are **not** added to the progress file (v3 marked them
  done); a retry next run will pick them up
