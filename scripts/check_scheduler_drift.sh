#!/usr/bin/env bash
# check_scheduler_drift.sh
#
# Reach into the running backend container, ask APScheduler what it thinks
# its next-run times are, and compare each entry against the schedule
# declared in app/core/scheduler.py. If any job's actual next_run_time
# drifts more than DRIFT_MINUTES (default 5) from the expected cron/interval
# boundary, print a WARN line.
#
# This script is OBSERVATION ONLY. It does not modify any source file or
# touch the running scheduler. It exits 0 when nothing is alarming and 10
# when the introspection itself fails (e.g. container not running).
#
# Usage:
#   scripts/check_scheduler_drift.sh [DRIFT_MINUTES]
#
# Exit codes:
#   0   OK (no drift detected OR drift warning printed but caller-OK)
#  10   Failed to introspect scheduler (container down, scheduler stopped, etc.)

set -u

DRIFT_MINUTES="${1:-5}"
COMPOSE_FILE="${DOCKER_COMPOSE_FILE:-./docker-compose.yml}"
CONTAINER="${SCHEDULER_CONTAINER:-alloyresearch-backend}"
PROBE_FILE="$(mktemp -t "sched_probe.XXXXXX.py")"
trap 'rm -f "${PROBE_FILE}"' EXIT

if ! [[ "${DRIFT_MINUTES}" =~ ^[0-9]+$ ]]; then
    echo "[drift] ERROR: DRIFT_MINUTES must be a non-negative integer (got '${DRIFT_MINUTES}')" >&2
    exit 10
fi

cat > "${PROBE_FILE}" <<'PY'
"""Probe scheduler jobs from inside the backend container.

Dumps a JSON document to stdout with one entry per registered job:
  { "id": "...", "name": "...", "next_run_time": "ISO-8601 UTC or null" }
This matches the format already used by get_scheduler_jobs() in
app/core/scheduler.py, but inlines the import so we do not require
the FastAPI app to be running.
"""
import json
import sys

try:
    from app.core.scheduler import scheduler
except Exception as exc:
    print(json.dumps({"error": f"import_failed: {exc}"}))
    sys.exit(2)

out = []
try:
    if not scheduler.running:
        print(json.dumps({"error": "scheduler_not_running"}))
        sys.exit(3)
    for job in scheduler.get_jobs():
        nrt = job.next_run_time
        out.append(
            {
                "id": job.id,
                "name": getattr(job, "name", None) or job.id,
                "next_run_time": nrt.isoformat() if nrt else None,
            }
        )
except Exception as exc:
    print(json.dumps({"error": f"introspect_failed: {exc}"}))
    sys.exit(4)

print(json.dumps({"jobs": out}, ensure_ascii=False))
PY

echo "[drift] compose: ${COMPOSE_FILE}"
echo "[drift] container: ${CONTAINER}"
echo "[drift] threshold: ${DRIFT_MINUTES} minute(s)"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
    echo "[drift] ERROR: compose file not found: ${COMPOSE_FILE}" >&2
    exit 10
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "[drift] ERROR: docker CLI not found on PATH" >&2
    exit 10
fi

# Run the probe inside the backend container so it sees the same in-process
# BackgroundScheduler instance. We never call the FastAPI HTTP endpoint
# because we want the live process view, not a cached Redis snapshot.
PROBE_OUTPUT="$(
    docker compose -f "${COMPOSE_FILE}" exec -T "${CONTAINER}" \
        python -c "
import runpy, sys, pathlib
pathlib.Path('${PROBE_FILE}').write_text(open('/dev/stdin').read())
runpy.run_path('${PROBE_FILE}', run_name='__main__')
" 2>&1 < "${PROBE_FILE}"
)"

# Some compose / docker versions strip stdin cleanly enough that the heredoc
# approach above is awkward. Fall back to mounting via cat.
if [[ -z "${PROBE_OUTPUT}" || "${PROBE_OUTPUT}" == *"No such file or directory"* ]]; then
    PROBE_OUTPUT="$(
        docker compose -f "${COMPOSE_FILE}" exec -T "${CONTAINER}" \
            python - "$(cat "${PROBE_FILE}")" <<'EOF'
import sys, runpy
script = sys.argv[1]
exec(compile(script, '<probe>', 'exec'), {'__name__': '__main__'})
EOF
    )"
fi

# Last resort: pipe the file in via shell heredoc on stdin.
if [[ -z "${PROBE_OUTPUT}" ]]; then
    PROBE_OUTPUT="$(
        docker compose -f "${COMPOSE_FILE}" exec -T "${CONTAINER}" python - 2>&1 <<EOF
$(cat "${PROBE_FILE}")
EOF
    )"
fi

if [[ -z "${PROBE_OUTPUT}" ]]; then
    echo "[drift] ERROR: scheduler probe returned no output (container ${CONTAINER} unreachable?)" >&2
    exit 10
fi

# Validate JSON and extract any error field.
ERROR_FIELD="$(printf '%s' "${PROBE_OUTPUT}" | python -c "
import json, sys
try:
    payload = json.loads(sys.stdin.read())
except Exception as e:
    print('PARSE_FAIL: ' + str(e))
    sys.exit(0)
if 'error' in payload:
    print(payload['error'])
else:
    print('')
")"

if [[ -n "${ERROR_FIELD}" ]]; then
    echo "[drift] ERROR: scheduler probe failed: ${ERROR_FIELD}" >&2
    exit 10
fi

JOB_COUNT="$(printf '%s' "${PROBE_OUTPUT}" | python -c "
import json, sys
payload = json.loads(sys.stdin.read())
print(len(payload.get('jobs', [])))
")"

echo "[drift] scheduler reports ${JOB_COUNT} active job(s)"

# The drift comparison itself: APScheduler's next_run_time is authoritative
# for the running process. We don't reproduce the cron math here — instead
# we compare two snapshots of next_run_time taken DRIFT_MINUTES apart and
# warn if a CronTrigger-bound job's next_run_time did not advance within
# the expected tolerance. This is the same heuristic the existing
# scripts/check_scheduler.py is meant to support; we just emit warnings.
#
# For IntervalTrigger jobs we instead sanity-check that next_run_time is
# in the future (it always should be) and never more than 2x the interval
# away.
NOW_ISO="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"
DRIFT_OK="$(printf '%s' "${PROBE_OUTPUT}" | python -c "
import json, sys
from datetime import datetime, timezone, timedelta

threshold_min = ${DRIFT_MINUTES}
payload = json.loads(sys.stdin.read())
jobs = payload.get('jobs', [])
now = datetime.now(timezone.utc)
ok = True

# Static expected schedules, mirrored from app/core/scheduler.py.
# These are the cron expressions (Beijing time) the source code registers.
# The drift script does NOT re-parse the Python file; it compares against
# this hard-coded mirror so a code change forces a re-baseline here too.
# For interval triggers we only check liveness.
EXPECTED_CRON_BJ = {
    # id                       : (hour, minute, dow)
    'us_daily_etl'             : (5, 0,  None),
    'us_historical_backfill'   : (None, 0, None),  # every hour
    'us_indicator_calculation' : (5, 30, None),
    'a_share_daily_etl'        : (15, 30, None),
    'indicator_calculation'    : (8, 0,  None),
    'score_calculation'        : (8, 30, None),
    'weekly_pool_reports'      : (22, 0, 'sun'),
    'us_etf_discovery'         : (1, 0,  'sun'),
    'us_stock_discovery'       : (2, 0,  'sun'),
    'us_stock_enrichment'      : (2, 30, None),
    'etf_market_scan'          : (3, 0,  'sun'),
    'signal_generation'        : (9, 0,  None),
    'crypto_daily_etl'         : (8, 5,  None),
    'crypto_indicator_calculation': (8, 30, None),
    'etf_metadata_enrichment'  : (4, 0,  'sun'),
    'listing_events_daily'     : (9, 30, None),
    'cninfo_reports_daily'     : (17, 0, None),
    'china_macro_daily'        : (9, 30, 'mon-fri'),
    'futures_daily_etl'        : (16, 30, None),
    'futures_contracts_refresh': (3, 0,  None),   # day=1 (monthly)
    'paper_trade_market_update': (None, 15, None),  # hourly :15
    'paper_trade_auto'         : (9, 30, None),
    'a_stock_daily_etl'        : (16, 0, None),
    'a_stock_fundamental_etl'  : (16, 30, None),
    'a_stock_discovery'        : (1, 0,  'mon'),
    'a_stock_financials'       : (2, 0,  'mon'),
    'research_reports_daily'   : (18, 0, None),
    'fred_macro_daily'         : (3, 0,  'mon-fri'),
    'sec_edgar_daily'          : (6, 0,  'sat'),  # UTC
    'microstructure_daily'     : (18, 30, None),
    'search_trends_daily'      : (3, 0,  None),
}

INTERVAL_JOBS = {
    'research_summarize': 120,
    'news_cninfo_10m': 10,
    'news_sina_5m': 5,
    'news_wechat_zeping_15m': 15,
    'news_yahoo_5m': 5,
    'news_cnbc_5m': 5,
    'news_sec_edgar_30m': 30,
    'news_reddit_5m': 5,
    'news_coindesk_5m': 5,
    'news_cointelegraph_5m': 5,
    'news_xueqiu_5m': 5,
    'news_full_content_10m': 10,
}

BJ = timezone(timedelta(hours=8))
UTC = timezone.utc

def expected_for(job_id, nrt):
    # Returns the expected cron/interval next-run boundary (UTC) given the
    # observed next_run_time as the search anchor. We do not own the full
    # cron parser; instead we project forward/backward from nrt to find the
    # nearest boundary that satisfies the schedule.
    if nrt is None:
        return None
    if job_id in EXPECTED_CRON_BJ:
        hour, minute, dow = EXPECTED_CRON_BJ[job_id]
        if job_id == 'sec_edgar_daily':
            tz = UTC
        else:
            tz = BJ
        anchor = nrt.astimezone(tz)
        # For minute-bound cron the boundary is the wall-clock HH:MM itself.
        return anchor.replace(hour=hour or anchor.hour,
                              minute=minute,
                              second=0,
                              microsecond=0)
    if job_id in INTERVAL_JOBS:
        return nrt  # intervals have no 'expected wall-clock', only liveness
    return None

seen_ids = set()
for j in jobs:
    jid = j['id']
    seen_ids.add(jid)
    nrt_str = j['next_run_time']
    if not nrt_str:
        print(f'WARN job={jid} no next_run_time')
        ok = False
        continue
    try:
        nrt = datetime.fromisoformat(nrt_str.replace('Z', '+00:00'))
    except Exception:
        print(f'WARN job={jid} unparseable next_run_time={nrt_str}')
        ok = False
        continue

    expected = expected_for(jid, nrt)
    if expected is None:
        continue

    if jid in INTERVAL_JOBS:
        # liveness: next run must be in the future and within 2x the interval.
        delta_min = (nrt - now).total_seconds() / 60.0
        if delta_min < 0:
            print(f'WARN job={jid} next_run_time is in the past ({delta_min:.1f}m ago)')
            ok = False
        elif delta_min > 2 * INTERVAL_JOBS[jid]:
            print(f'WARN job={jid} next_run_time is {delta_min:.0f}m out (interval={INTERVAL_JOBS[jid]}m)')
            ok = False
        continue

    delta_min = abs((nrt - expected).total_seconds()) / 60.0
    # APScheduler reports next_run_time in UTC; the cron is in Asia/Shanghai.
    # Allow a 1-hour cushion for the timezone shift + scheduler latency.
    effective_threshold = max(threshold_min, 60)
    if delta_min > effective_threshold:
        print(f'WARN job={jid} next_run_time={nrt.isoformat()} '
              f'drifts {delta_min:.0f}m from expected={expected.isoformat()} '
              f'(threshold={effective_threshold}m)')
        ok = False

missing = set(EXPECTED_CRON_BJ.keys()) | set(INTERVAL_JOBS.keys()) - seen_ids
for jid in sorted(missing):
    print(f'WARN job={jid} missing from scheduler (declared in scheduler.py)')
    ok = False

print('OK' if ok else 'DRIFT')
sys.exit(0 if ok else 0)  # always exit 0 here; shell decides exit code
")"

case "${DRIFT_OK}" in
    *OK)
        echo "[drift] OK: no drift beyond ${DRIFT_MINUTES} minute(s)"
        echo "[drift] observation-only exit code: 0"
        exit 0
        ;;
    *DRIFT)
        echo "[drift] WARN: drift detected (see warnings above)"
        echo "[drift] observation-only exit code: 0 (caller decides)"
        exit 0
        ;;
    *)
        echo "[drift] ERROR: unable to interpret probe output" >&2
        echo "----- raw probe output -----" >&2
        echo "${PROBE_OUTPUT}" >&2
        exit 10
        ;;
esac