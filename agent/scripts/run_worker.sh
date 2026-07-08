#!/usr/bin/env bash
# run_worker.sh - AD-Research agent worker launcher.
#
# Launches a one-off worker container on the isolated alloyresearch-agent-network
# (NOT on alloyresearch-network, which is for the platform backend/postgres/redis).
#
# Usage:
#   run_worker.sh <worker_name> <output_path> [extra args...]
#
# Examples:
#   run_worker.sh cls /data/ad-research/cls/today.json
#   run_worker.sh xueqiu_hot /data/xueqiu/hot.json --hours 48
#   run_worker.sh reddit_finance /tmp/r.json --sort new --top-time hour --verbose
#
# Env overrides:
#   AD_AGENT_IMAGE       image tag to use (default: alloyresearch-agent:latest)
#   AD_AGENT_NETWORK     network name (default: alloyresearch-agent-network)
#   AD_AGENT_PROFILE     Playwright profile bind mount (default: /root/.playwright-profile)
#   AD_AGENT_DATA        data output bind mount (default: /data/ad-research)
#   AD_AGENT_WORKERS     workers dir bind mount (default: /root/ad-research/agent/workers)
#   AD_AGENT_MEMORY      container memory limit (default: 1g)
#   AD_AGENT_CPUS        container CPU limit (default: 1.5)
#   AD_AGENT_TIMEOUT     auto-kill timeout seconds (default: 600)
#   AD_AGENT_ENV_FILE    optional env file to pass into the container (-e)
set -euo pipefail

# ---- resolve inputs ----
if [[ $# -lt 2 ]]; then
  echo "usage: $0 <worker_name> <output_path> [extra args...]" >&2
  echo "       workers: cls eastmoney_news xueqiu_hot reddit_finance" >&2
  exit 64
fi

WORKER="$1"
shift
OUTPUT_HOST="$1"
shift
EXTRA_ARGS=("$@")

AD_AGENT_IMAGE="${AD_AGENT_IMAGE:-alloyresearch-agent:latest}"
AD_AGENT_NETWORK="${AD_AGENT_NETWORK:-alloyresearch-agent-network}"
AD_AGENT_PROFILE="${AD_AGENT_PROFILE:-/root/.playwright-profile}"
AD_AGENT_DATA="${AD_AGENT_DATA:-/data/ad-research}"
AD_AGENT_WORKERS="${AD_AGENT_WORKERS:-/root/ad-research/agent/workers}"
AD_AGENT_MEMORY="${AD_AGENT_MEMORY:-1g}"
AD_AGENT_CPUS="${AD_AGENT_CPUS:-1.5}"
AD_AGENT_TIMEOUT="${AD_AGENT_TIMEOUT:-600}"
AD_AGENT_ENV_FILE="${AD_AGENT_ENV_FILE:-}"

# ---- pre-flight checks ----
if [[ ! -d "$AD_AGENT_PROFILE" ]]; then
  echo "[run_worker] WARN: profile dir $AD_AGENT_PROFILE missing, creating" >&2
  mkdir -p "$AD_AGENT_PROFILE"
  chmod 700 "$AD_AGENT_PROFILE"
fi
if [[ ! -d "$AD_AGENT_WORKERS" ]]; then
  echo "[run_worker] ERROR: workers dir $AD_AGENT_WORKERS not found" >&2
  exit 65
fi
if ! docker image inspect "$AD_AGENT_IMAGE" >/dev/null 2>&1; then
  echo "[run_worker] ERROR: image $AD_AGENT_IMAGE not found locally" >&2
  exit 66
fi
if ! docker network inspect "$AD_AGENT_NETWORK" >/dev/null 2>&1; then
  echo "[run_worker] ERROR: network $AD_AGENT_NETWORK not found" >&2
  echo "[run_worker] hint:   docker network create $AD_AGENT_NETWORK" >&2
  exit 67
fi
if [[ ! -f "$AD_AGENT_WORKERS/$WORKER.py" ]]; then
  echo "[run_worker] ERROR: worker script $WORKER.py not in $AD_AGENT_WORKERS" >&2
  exit 68
fi

# ---- map host output path to container path ----
# We mount $AD_AGENT_DATA -> /data, so any host output under AD_AGENT_DATA becomes
# /data/<rel>. If the caller passes a path outside that tree, fall back to /data.
case "$OUTPUT_HOST" in
  "$AD_AGENT_DATA"/*)
    OUTPUT_CONT="/data/${OUTPUT_HOST#$AD_AGENT_DATA/}"
    ;;
  *)
    echo "[run_worker] WARN: output $OUTPUT_HOST is outside $AD_AGENT_DATA," >&2
    echo "[run_worker]        writing to /data/$(basename "$OUTPUT_HOST") instead." >&2
    OUTPUT_CONT="/data/$(basename "$OUTPUT_HOST")"
    ;;
esac

CONTAINER_NAME="alloyresearch-agent-worker-$(date +%s)-$$"
TS="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="${LOG_DIR:-/root/ad-research/logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/${WORKER}-${TS}.log"

echo "[run_worker] worker=$WORKER image=$AD_AGENT_IMAGE net=$AD_AGENT_NETWORK" | tee -a "$LOG_FILE"
echo "[run_worker] host_out=$OUTPUT_HOST cont_out=$OUTPUT_CONT" | tee -a "$LOG_FILE"
echo "[run_worker] log=$LOG_FILE" | tee -a "$LOG_FILE"

ENV_FILE_ARGS=()
if [[ -n "$AD_AGENT_ENV_FILE" && -f "$AD_AGENT_ENV_FILE" ]]; then
  ENV_FILE_ARGS=(--env-file "$AD_AGENT_ENV_FILE")
fi

# ---- launch worker ----
set +e
docker run --rm \
  --name "$CONTAINER_NAME" \
  --network "$AD_AGENT_NETWORK" \
  --memory "$AD_AGENT_MEMORY" \
  --cpus "$AD_AGENT_CPUS" \
  --pids-limit 256 \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=256m \
  -v "$AD_AGENT_PROFILE:/profile:rw" \
  -v "$AD_AGENT_WORKERS:/workspace/workers:ro" \
  -v "$AD_AGENT_DATA:/data:rw" \
  -e PYTHONUNBUFFERED=1 \
  -e TZ=Asia/Shanghai \
  -e PLAYWRIGHT_USER_DATA_DIR=/profile \
  -e PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
  "${ENV_FILE_ARGS[@]}" \
  "$AD_AGENT_IMAGE" \
  timeout "${AD_AGENT_TIMEOUT}s" \
    python "/workspace/workers/$WORKER.py" \
      --output "$OUTPUT_CONT" \
      "${EXTRA_ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"
rc=${PIPESTATUS[0]}
set -e

echo "[run_worker] exit=$rc log=$LOG_FILE" | tee -a "$LOG_FILE"

# Verify output file landed where the caller asked (only if it's under AD_AGENT_DATA).
if [[ "$OUTPUT_HOST" == "$AD_AGENT_DATA"/* ]]; then
  if [[ -s "$OUTPUT_HOST" ]]; then
    bytes=$(stat -c%s "$OUTPUT_HOST")
    echo "[run_worker] OK output=$OUTPUT_HOST bytes=$bytes" | tee -a "$LOG_FILE"
  else
    echo "[run_worker] FAIL output missing or empty: $OUTPUT_HOST" | tee -a "$LOG_FILE"
    rc=69
  fi
fi

exit $rc