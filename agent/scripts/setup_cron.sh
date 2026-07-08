#!/bin/bash
# setup_cron.sh — install / uninstall / status for the AD-Research hourly
# orchestration cron.
#
# Usage:
#   bash scripts/setup_cron.sh install
#   bash scripts/setup_cron.sh uninstall
#   bash scripts/setup_cron.sh status
#
# Notes
# -----
# - Hourly run at minute :47 (chosen to avoid colliding with the existing
#   quarter-hour jobs in /etc/cron.d/ on the prod box).
# - Logs go to /root/ad-research/logs/cron-orchestrate.log (tee'd so the
#   caller's stdout still sees the run output).
# - install prefers /etc/cron.d/ad-research-orchestrate (system-wide, no
#   user crontab editing); falls back to per-user crontab if /etc/cron.d
#   isn't writable.

set -euo pipefail

ACTION="${1:-status}"

AGENT_ROOT="${AGENT_ROOT:-/root/ad-research/agent}"
SCRIPT="${AGENT_ROOT}/scripts/orchestrate_v2.py"
LOG_DIR="/root/ad-research/logs"
CRON_LOG="${LOG_DIR}/cron-orchestrate.log"
AGGREGATE="/data/ad-research/aggregate.json"
SCHEDULE_TAG="ad-research-orchestrate"
CRON_MINUTE="47"

# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

build_command() {
    cat <<EOF
PYTHONUNBUFFERED=1 flock -n /var/lock/ad-research-orchestrate.lock \
    /usr/bin/env python3 ${SCRIPT} --schedule all \
    --output-dir ${AGGREGATE} \
    >> ${CRON_LOG} 2>&1
EOF
}

ensure_paths() {
    if [[ ! -f "${SCRIPT}" ]]; then
        echo "ERROR: orchestrate_v2.py not found at ${SCRIPT}" >&2
        echo "       Set AGENT_ROOT=/path/to/ad-research/agent" >&2
        exit 1
    fi
    mkdir -p "${LOG_DIR}" "/data/ad-research"
}

# --------------------------------------------------------------------------- #
# Sub-commands                                                                #
# --------------------------------------------------------------------------- #

do_install() {
    ensure_paths
    local cmd
    cmd="$(build_command)"

    # Try /etc/cron.d first (system-wide, preferred)
    local cron_file="/etc/cron.d/${SCHEDULE_TAG}"
    local cron_body
    cron_body=$(cat <<EOF
# AD-Research hourly aggregate — installed $(date '+%Y-%m-%d %H:%M:%S')
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
${CRON_MINUTE} * * * * root ${cmd}
EOF
)

    if [[ -w /etc/cron.d ]] || sudo -n true 2>/dev/null; then
        if echo "${cron_body}" | sudo tee "${cron_file}" >/dev/null; then
            sudo chmod 0644 "${cron_file}"
            log "installed system cron at ${cron_file} (minute=${CRON_MINUTE})"
            log "aggregate: ${AGGREGATE}"
            log "log:       ${CRON_LOG}"
            return 0
        fi
        echo "WARN: failed to write ${cron_file}, falling back to user crontab" >&2
    fi

    # Fallback: user crontab
    (
        crontab -l 2>/dev/null | grep -v -F "# ad-research-orchestrate" | \
            grep -v -F "${SCRIPT}" || true
        echo "# ad-research-orchestrate — auto-managed by setup_cron.sh"
        echo "${CRON_MINUTE} * * * * ${cmd}"
    ) | crontab -
    log "installed user crontab entry (minute=${CRON_MINUTE})"
    log "aggregate: ${AGGREGATE}"
    log "log:       ${CRON_LOG}"
}

do_uninstall() {
    local removed=0
    local cron_file="/etc/cron.d/${SCHEDULE_TAG}"
    if [[ -f "${cron_file}" ]]; then
        if sudo -n true 2>/dev/null; then
            sudo rm -f "${cron_file}"
            log "removed ${cron_file}"
        else
            sudo rm -f "${cron_file}" || rm -f "${cron_file}" || true
            log "removed ${cron_file}"
        fi
        removed=1
    fi

    if crontab -l 2>/dev/null | grep -q -F "${SCRIPT}"; then
        crontab -l 2>/dev/null \
            | grep -v -F "# ad-research-orchestrate" \
            | grep -v -F "${SCRIPT}" \
            | crontab -
        log "removed crontab entries for ${SCRIPT}"
        removed=1
    fi

    if [[ ${removed} -eq 0 ]]; then
        log "no cron entries found — nothing to uninstall"
    fi
}

do_status() {
    echo "=== AD-Research orchestration cron ==="
    echo "agent_root : ${AGENT_ROOT}"
    echo "script     : ${SCRIPT}  $( [[ -f "${SCRIPT}" ]] && echo '[OK]' || echo '[MISSING]' )"
    echo "aggregate  : ${AGGREGATE}"
    echo "cron log   : ${CRON_LOG}"
    echo "minute     : :${CRON_MINUTE} (hourly)"
    echo
    echo "--- /etc/cron.d/${SCHEDULE_TAG} ---"
    if [[ -f "/etc/cron.d/${SCHEDULE_TAG}" ]]; then
        cat "/etc/cron.d/${SCHEDULE_TAG}"
    else
        echo "(not installed)"
    fi
    echo
    echo "--- user crontab matches ---"
    if crontab -l 2>/dev/null | grep -F "${SCRIPT}"; then
        :
    else
        echo "(no user crontab entry for ${SCRIPT})"
    fi
    echo
    echo "--- recent cron log tail ---"
    if [[ -f "${CRON_LOG}" ]]; then
        tail -n 20 "${CRON_LOG}"
    else
        echo "(no log yet)"
    fi
}

# --------------------------------------------------------------------------- #
# Dispatch                                                                    #
# --------------------------------------------------------------------------- #

case "${ACTION}" in
    install)   do_install ;;
    uninstall) do_uninstall ;;
    status)    do_status ;;
    *)
        echo "Usage: $0 [install|uninstall|status]" >&2
        exit 2
        ;;
esac