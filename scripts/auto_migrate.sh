#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/auto_migrate.sh
#
# Idempotent Alembic migration runner for the backend container.
#
# Compares `alembic current` against `alembic heads --resolve` and runs
# `alembic upgrade head` only when there's drift. Always prints the schema
# diff (`alembic history --verbose -r current:head`) so the operator can see
# what is (or isn't) about to apply.
#
# Usage:
#   ./auto_migrate.sh [compose-file]
#
# Arguments:
#   compose-file  Path to the docker-compose file that defines the backend
#                 service. Defaults to ./deploy/aliyun-ecs/docker-compose.yml
#                 (the canonical production stack).
#
# Exit codes:
#   0   Database is already at head OR migrations applied successfully
#   1   Alembic reported an error (current == head mismatch after upgrade)
#   2   Bad invocation / missing dependencies
#
# Notes:
#   This script assumes the backend image has `alembic` installed and that
#   DATABASE_URL is reachable from the running container (handled by the
#   compose service definition).
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail

# ── Args ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${1:-${PROJECT_ROOT}/deploy/aliyun-ecs/docker-compose.yml}"

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "[FATAL] compose file not found: ${COMPOSE_FILE}" >&2
    exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "[FATAL] docker CLI is required" >&2
    exit 2
fi

COMPOSE_DIR="$(cd "$(dirname "$COMPOSE_FILE")" && pwd)"

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
CYAN=$'\033[0;36m'
NC=$'\033[0m'

log_info()  { echo "${CYAN}[INFO]${NC}  $1"; }
log_warn()  { echo "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo "${RED}[ERROR]${NC} $1"; }
log_ok()    { echo "${GREEN}[ OK ]${NC}  $1"; }
log_step()  { echo ""; echo "${GREEN}━━━ $1 ━━━${NC}"; }

# ── Helpers ──
# Run `alembic …` inside the backend service defined by the compose file.
# Returns the command's exit code; output goes to stdout so the caller can
# tee / capture it.
run_alembic() {
    docker compose \
        --project-directory "$COMPOSE_DIR" \
        -f "$COMPOSE_FILE" \
        exec -T backend \
        alembic "$@"
}

# Extract the head revision short id from `alembic heads --resolve` output.
# The output looks like:
#   "<sha> (head)"      for a single head
#   "<sha1> (head), <sha2> (head)"  for multiple heads (rare)
parse_head() {
    # First line that ends with "(head)" — strip everything after the SHA.
    awk '/\(head\)/ { print $1; exit }' <<< "$1"
}

# Extract the current revision from `alembic current` output.
# Output is typically "<sha> (head)" or "<sha> (some_branch)".
parse_current() {
    awk 'NF { print $1; exit }' <<< "$1"
}

# ── Start ──
echo "════════════════════════════════════════════════════════════════════"
echo " Auto-migrate — compose: ${COMPOSE_FILE}"
echo " $(date -u +'%Y-%m-%d %H:%M:%S UTC')"
echo "════════════════════════════════════════════════════════════════════"

# Make sure the backend container is running. If not, bring the stack up
# first (postgres + redis are required dependencies).
log_step "1/5 Ensure backend service is running"
if ! docker compose \
        --project-directory "$COMPOSE_DIR" \
        -f "$COMPOSE_FILE" \
        ps --services --status running 2>/dev/null \
        | grep -qx "backend"; then
    log_info "backend is not running — starting dependent services first"
    docker compose \
        --project-directory "$COMPOSE_DIR" \
        -f "$COMPOSE_FILE" \
        up -d postgres redis >/dev/null
    docker compose \
        --project-directory "$COMPOSE_DIR" \
        -f "$COMPOSE_FILE" \
        up -d backend >/dev/null
    log_info "Waiting 10s for backend to finish initial boot…"
    sleep 10
fi
log_ok "backend is up"

# ── 2. Current revision ──
log_step "2/5 Read current Alembic revision"
CURRENT_RAW=$(run_alembic current 2>&1) || {
    log_error "Failed to read alembic current — output above"
    exit 1
}
log_info "current: ${CURRENT_RAW}"

CURRENT_REV=$(parse_current "$CURRENT_RAW")
# `alembic current` returns nothing when no revisions have been applied
# (fresh DB). Treat as "<empty>".
if [ -z "$CURRENT_REV" ]; then
    log_warn "No current revision (empty DB or first migration)"
    CURRENT_REV="<empty>"
fi

# ── 3. Head revision ──
log_step "3/5 Read head revision"
HEADS_RAW=$(run_alembic heads --resolve 2>&1) || {
    log_error "Failed to read alembic heads — output above"
    exit 1
}
log_info "heads (resolved): ${HEADS_RAW}"

HEAD_REV=$(parse_head "$HEADS_RAW")
if [ -z "$HEAD_REV" ]; then
    log_error "Could not parse head revision from: ${HEADS_RAW}"
    exit 1
fi
log_info "head: ${HEAD_REV}"

# ── 4. Compare & decide ──
log_step "4/5 Drift check + (conditional) upgrade"
if [ "$CURRENT_REV" = "$HEAD_REV" ]; then
    log_ok "No drift — DB already at head (${HEAD_REV})"
else
    log_warn "Drift detected — current=${CURRENT_REV}  head=${HEAD_REV}"
    log_info "Schema diff (current → head):"
    echo "------------------------------------------------------------------"
    # `alembic history --verbose -r current:head` raises if current is empty,
    # so guard with a no-op upgrade that won't move the revision pointer.
    run_alembic history --verbose -r "current:head" 2>&1 \
        || log_warn "history dump failed (likely fresh DB — will show all migrations instead)"
    echo "------------------------------------------------------------------"

    log_info "Running: alembic upgrade head"
    if ! run_alembic upgrade head 2>&1; then
        log_error "alembic upgrade head FAILED — DB may be in partial state"
        exit 1
    fi
    log_ok "alembic upgrade head completed"
fi

# ── 5. Verify ──
log_step "5/5 Post-upgrade verification"
POST_CURRENT_RAW=$(run_alembic current 2>&1) || {
    log_error "Post-upgrade alembic current failed"
    exit 1
}
POST_CURRENT_REV=$(parse_current "$POST_CURRENT_RAW")
log_info "post-upgrade current: ${POST_CURRENT_REV}"

if [ "$POST_CURRENT_REV" != "$HEAD_REV" ]; then
    log_error "Verification failed — expected ${HEAD_REV}, got ${POST_CURRENT_REV}"
    exit 1
fi

log_ok "DB is now at head (${HEAD_REV})"
echo "════════════════════════════════════════════════════════════════════"
exit 0