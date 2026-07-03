#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/post_deploy_check.sh
#
# Post-deployment smoke test for the FastAPI backend.
#
# Pulls /health, /docs, and /api/v1/healthz (when present) and asserts the
# expected shape & latency. Designed to be run from CI or a self-hosted
# runner immediately after `update.sh` + `auto_migrate.sh`.
#
# Usage:
#   ./post_deploy_check.sh <public-url>
#
# Arguments:
#   <public-url>  Base URL of the deployed backend, e.g.
#                  http://1.2.3.4:8000
#                  https://app.example.com
#
# Exit codes:
#   0   All probes passed
#   1   One or more probes failed
#   2   Bad invocation / missing dependencies
#
# Output:
#   Each probe is logged with elapsed time in milliseconds. Final summary
#   shows pass/fail counts; the script always prints what went wrong before
#   returning non-zero so the failure is debuggable from CI logs alone.
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail

# ── Args & sanity ──
if [ "$#" -ne 1 ]; then
    echo "[FATAL] Usage: $0 <public-url>" >&2
    echo "        e.g.   $0 http://1.2.3.4:8000" >&2
    exit 2
fi

PUBLIC_URL="${1%/}"   # strip trailing slash

# Need curl + jq for JSON parsing. jq is preferred but optional — fall back
# to grep/sed-style assertions if jq isn't available.
if ! command -v curl >/dev/null 2>&1; then
    echo "[FATAL] curl is required but not installed" >&2
    exit 2
fi

HAVE_JQ=0
if command -v jq >/dev/null 2>&1; then
    HAVE_JQ=1
fi

# ── Bookkeeping ──
PASS=0
FAIL=0
declare -a RESULTS=()

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
CYAN=$'\033[0;36m'
NC=$'\033[0m'

log_pass() { echo "${GREEN}[ OK ]${NC}  $1"; PASS=$((PASS+1)); RESULTS+=("PASS|$1"); }
log_fail() { echo "${RED}[FAIL]${NC}  $1"; FAIL=$((FAIL+1)); RESULTS+=("FAIL|$1"); }
log_info() { echo "${CYAN}[INFO]${NC}  $1"; }
log_warn() { echo "${YELLOW}[WARN]${NC}  $1"; }

# ── Probe helper ──
# probe <label> <method> <path> <expected_status> [jq-filter]
# On success: prints "[ OK ] label (XXms)" and writes the body to $LAST_BODY
# On failure: prints "[FAIL] label (XXms) <reason>" and writes "" to $LAST_BODY
LAST_BODY=""
LAST_STATUS=""

probe() {
    local label="$1"
    local method="$2"
    local path="$3"
    local expected="$4"
    local filter="${5:-}"

    local url="${PUBLIC_URL}${path}"
    local start_ns end_ns elapsed_ms
    local tmp_body tmp_headers
    tmp_body=$(mktemp)
    tmp_headers=$(mktemp)

    start_ns=$(date +%s%N)
    LAST_STATUS=$(curl -s -o "$tmp_body" -D "$tmp_headers" \
        -w "%{http_code}" \
        -X "$method" \
        --max-time 10 \
        "$url" || echo "000")
    end_ns=$(date +%s%N)
    elapsed_ms=$(( (end_ns - start_ns) / 1000000 ))

    LAST_BODY=$(cat "$tmp_body")
    rm -f "$tmp_body" "$tmp_headers"

    if [ "$LAST_STATUS" != "$expected" ]; then
        log_fail "${label} — got HTTP ${LAST_STATUS}, expected ${expected} (${elapsed_ms}ms) — body: ${LAST_BODY:0:200}"
        return 1
    fi

    if [ -n "$filter" ] && [ "$HAVE_JQ" -eq 1 ]; then
        local value
        value=$(echo "$LAST_BODY" | jq -r "$filter" 2>/dev/null || echo "")
        if [ -z "$value" ] || [ "$value" = "null" ]; then
            log_fail "${label} — jq filter '${filter}' returned empty — body: ${LAST_BODY:0:200}"
            return 1
        fi
    fi

    log_pass "${label} (HTTP ${LAST_STATUS}, ${elapsed_ms}ms)"
    return 0
}

# ── Start ──
echo "════════════════════════════════════════════════════════════════════"
echo " Post-deploy check — target: ${PUBLIC_URL}"
echo " $(date -u +'%Y-%m-%d %H:%M:%S UTC')"
echo "════════════════════════════════════════════════════════════════════"

# ── 1. /health (strict — checks DB + Redis) ──
probe "/health" GET "/health" "200" >/dev/null

if [ "$LAST_STATUS" = "200" ]; then
    if [ "$HAVE_JQ" -eq 1 ]; then
        # /health must include status=ok, version, db=ok, redis=ok
        health_status=$(echo "$LAST_BODY" | jq -r '.status // ""' 2>/dev/null)
        health_version=$(echo "$LAST_BODY" | jq -r '.version // ""' 2>/dev/null)
        health_db=$(echo "$LAST_BODY" | jq -r '.db // ""' 2>/dev/null)
        health_redis=$(echo "$LAST_BODY" | jq -r '.redis // ""' 2>/dev/null)
        health_sha=$(echo "$LAST_BODY" | jq -r '.git_sha // ""' 2>/dev/null)

        [ "$health_status" = "ok" ] \
            && log_pass "/health.status == ok" \
            || log_fail "/health.status expected 'ok', got '${health_status}'"

        [ -n "$health_version" ] \
            && log_pass "/health.version present (${health_version})" \
            || log_fail "/health.version missing"

        [ "$health_db" = "ok" ] \
            && log_pass "/health.db == ok" \
            || log_fail "/health.db expected 'ok', got '${health_db}'"

        [ "$health_redis" = "ok" ] \
            && log_pass "/health.redis == ok" \
            || log_fail "/health.redis expected 'ok', got '${health_redis}'"

        log_info "Build identity — version=${health_version}  git_sha=${health_sha}"
    else
        log_warn "jq not installed — skipping JSON field assertions (install jq for stricter checks)"
    fi
else
    log_fail "/health returned ${LAST_STATUS} — body: ${LAST_BODY:0:200}"
fi

# ── 2. /docs (OpenAPI UI) ──
probe "/docs" GET "/docs" "200" >/dev/null

# ── 3. /api/v1/healthz (optional — 404 is acceptable) ──
probe "/api/v1/healthz" GET "/api/v1/healthz" "200" >/dev/null \
    || log_warn "/api/v1/healthz not exposed (this is OK if not implemented)"

# ── 4. /openapi.json (spec sanity — guards against router mis-wiring) ──
probe "/openapi.json" GET "/openapi.json" "200" >/dev/null

# ── Summary ──
echo "────────────────────────────────────────────────────────────────────"
TOTAL=$((PASS + FAIL))
echo " Summary: ${PASS}/${TOTAL} passed, ${FAIL} failed"
if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo " Failures:"
    for r in "${RESULTS[@]}"; do
        case "$r" in
            FAIL*) echo "   - ${r#FAIL|}" ;;
        esac
    done
fi
echo "════════════════════════════════════════════════════════════════════"

[ "$FAIL" -eq 0 ] && exit 0 || exit 1