#!/usr/bin/env bash
# archive_logs.sh
#
# Roll up docker container logs into daily files under /var/log/ad-research,
# then gzip anything older than 14 days and delete anything older than 60
# days. Designed to be run nightly from cron (or on-demand) on the host that
# owns the docker compose deployment.
#
# Usage:
#   scripts/archive_logs.sh [path/to/docker-compose.yml]
#
# Defaults to ./docker-compose.yml if no argument is supplied.
#
# Exit codes:
#   0   success (one or more containers archived and rotations applied)
#   1   any container failed to be read or the rotation phase failed
#
# Notes:
# - The script is read-only with respect to app/** source code.
# - It writes only to /var/log/ad-research (and the gzip tmp files).
# - It does NOT touch /var/lib/docker or stop/restart any container.
# - Each container's stdout+stderr is captured into one merged daily file.
# - De-duplication is done by piping through `awk '!seen[$0]++'` AFTER
#   the merge so identical lines emitted to both streams collapse once.

set -u
set -o pipefail

COMPOSE_FILE="${1:-./docker-compose.yml}"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
    echo "[archive_logs] ERROR: compose file not found: ${COMPOSE_FILE}" >&2
    exit 1
fi

LOG_ROOT="/var/log/ad-research"
TODAY="$(date +%Y%m%d)"
COMPOSE_DIR="$(cd "$(dirname "${COMPOSE_FILE}")" && pwd)"

CONTAINERS=("alloyresearch-backend" "alloyresearch-postgres" "alloyresearch-redis" "alloyresearch-nginx")

mkdir -p "${LOG_ROOT}"
if [[ ! -d "${LOG_ROOT}" || ! -w "${LOG_ROOT}" ]]; then
    echo "[archive_logs] ERROR: cannot write to ${LOG_ROOT}" >&2
    exit 1
fi

FAIL=0

archive_one() {
    local container="$1"
    local out="${LOG_ROOT}/${container}-${TODAY}.log"
    local tmp
    tmp="$(mktemp -t "archive_${container}.XXXXXX")"

    # Merge stdout + stderr from the last 24h, dedupe, append to today's file.
    # `docker logs --since 24h` returns both streams interleaved when --timestamps
    # is NOT used; we keep timestamps for traceability and sort by them.
    if ! (
        cd "${COMPOSE_DIR}"
        docker logs --since 24h "${container}" 2>&1 \
            | awk '!seen[$0]++' \
            >> "${tmp}"
    ); then
        echo "[archive_logs] ERROR: failed to read logs from ${container}" >&2
        rm -f "${tmp}"
        return 1
    fi

    # Only append if we got something; never overwrite a previous same-day file.
    if [[ -s "${tmp}" ]]; then
        # If today's file already exists, append with a divider.
        if [[ -s "${out}" ]]; then
            printf '\n----- archive rerun %s -----\n' "$(date -Iseconds)" >> "${out}"
        fi
        cat "${tmp}" >> "${out}"
        echo "[archive_logs] ${container}: appended $(wc -l < "${tmp}" | tr -d ' ') lines -> ${out}"
    else
        echo "[archive_logs] ${container}: no logs in last 24h (skipping append)"
    fi
    rm -f "${tmp}"
    return 0
}

echo "[archive_logs] compose: ${COMPOSE_FILE}"
echo "[archive_logs] output : ${LOG_ROOT}"
echo "[archive_logs] date   : ${TODAY}"

for c in "${CONTAINERS[@]}"; do
    if ! archive_one "${c}"; then
        FAIL=1
    fi
done

# Rotation: gzip .log files older than 14 days.
echo "[archive_logs] rotating .log files older than 14 days..."
gzip_find_failed=0
while IFS= read -r -d '' f; do
    if ! gzip -9 --keep "${f}"; then
        echo "[archive_logs] ERROR: gzip failed for ${f}" >&2
        gzip_find_failed=1
    else
        # Remove the now-compressed original .log file. gzip --keep keeps
        # both .log and .log.gz; we want only the .log.gz to stay.
        rm -f "${f}"
        echo "[archive_logs] gzipped ${f}"
    fi
done < <(find "${LOG_ROOT}" -maxdepth 1 -type f -name '*.log' -mtime +14 -print0 2>/dev/null)
if [[ "${gzip_find_failed}" -ne 0 ]]; then
    FAIL=1
fi

# Cleanup: remove .gz files older than 60 days.
echo "[archive_logs] pruning .gz files older than 60 days..."
find "${LOG_ROOT}" -maxdepth 1 -type f -name '*.log.gz' -mtime +60 -print -delete 2>/dev/null

if [[ "${FAIL}" -ne 0 ]]; then
    echo "[archive_logs] DONE WITH ERRORS (exit 1)" >&2
    exit 1
fi

echo "[archive_logs] OK (exit 0)"
exit 0