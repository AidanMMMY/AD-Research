#!/bin/bash
# 2026-07-24: self-hosted GitHub Actions runner health check + self-heal.
#
# 背景：2026-07-23 / 2026-07-24 观察到 aliyun-etf-backend runner 4 次连续
# cascade failure (Deploy #316/#317/#318/#319)，step 5 (update.sh) 跑完
# 后 ~20s runner 整体失联。本脚本试图自动恢复。
#
# 用法：
#   bash /opt/ad-research/scripts/runner_healthcheck.sh            # 单次跑
#   */5 * * * * root bash /opt/ad-research/scripts/runner_healthcheck.sh >> /var/log/runner-health.log 2>&1
#
# 修复策略（按顺序）：
#   1. 磁盘 /data > 90% 或 /var/lib/docker > 95% → docker system prune 清理
#   2. runner daemon inactive/failed → systemctl restart
#   3. 仍有 STEP 5 cascade 痕迹 → 通知 on-call（写到 /tmp/runner-needs-attention）
#
# 设计原则：仅做低风险操作（prune/restart）；不动工作树数据；不动 docker compose up。
set -uo pipefail

LOG_PREFIX="[runner-health $(date -u +%Y-%m-%dT%H:%M:%SZ)]"
NEEDS_ATTENTION=""

log()  { echo "$LOG_PREFIX $*"; }
warn() { echo "$LOG_PREFIX WARN: $*"; }
err()  { echo "$LOG_PREFIX ERROR: $*"; NEEDS_ATTENTION+="$*\n"; }

# ---------------------------------------------------------------------- #
# 1. 磁盘健康
# ---------------------------------------------------------------------- #

DISK_PCT=$(df /data 2>/dev/null | awk 'NR==2 {print $5}' | tr -d '%' || echo "0")
DOCKER_PCT=$(df /var/lib/docker 2>/dev/null | awk 'NR==2 {print $5}' | tr -d '%' || echo "0")

if [[ "$DISK_PCT" -ge 90 ]]; then
  warn "disk /data ${DISK_PCT}% — running docker system prune -f"
  docker system prune -af --filter "until=24h" 2>&1 | tail -3
  err "/data was ${DISK_PCT}% — pruned 24h+ unused images"
fi

if [[ "$DOCKER_PCT" -ge 95 ]]; then
  warn "disk /var/lib/docker ${DOCKER_PCT}% — deep prune"
  docker system prune -af --volumes --filter "until=72h" 2>&1 | tail -3
  err "/var/lib/docker was ${DOCKER_PCT}% — deep pruned 72h+"
fi

# Buildx cache 单独清（容易把 /opt/ad-research 撑爆）
BUILDX_SIZE=$(du -sm /opt/ad-research/.buildx-cache 2>/dev/null | awk '{print $1}' || echo "0")
if [[ "${BUILDX_SIZE:-0}" -gt 20000 ]]; then
  warn ".buildx-cache ${BUILDX_SIZE}MB > 20GB — clearing"
  rm -rf /opt/ad-research/.buildx-cache/cache/* 2>/dev/null
  err ".buildx-cache was ${BUILDX_SIZE}MB — partially cleared"
fi

# ---------------------------------------------------------------------- #
# 2. runner daemon 健康
# ---------------------------------------------------------------------- #

RUNNER_SVC=$(systemctl list-units --type=service --no-legend 2>/dev/null | \
  awk '{print $1}' | grep -E '^actions\.runner' | head -1 || echo "")

if [[ -n "$RUNNER_SVC" ]]; then
  SVC_ACTIVE=$(systemctl is-active "$RUNNER_SVC" 2>/dev/null || echo "unknown")
  if [[ "$SVC_ACTIVE" != "active" ]]; then
    warn "runner daemon $RUNNER_SVC is $SVC_ACTIVE — restarting"
    if systemctl restart "$RUNNER_SVC" 2>&1 | tail -3; then
      sleep 5
      SVC_ACTIVE=$(systemctl is-active "$RUNNER_SVC" 2>/dev/null)
      if [[ "$SVC_ACTIVE" == "active" ]]; then
        log "runner daemon restarted successfully"
      else
        err "runner daemon restart failed: still $SVC_ACTIVE"
      fi
    else
      err "systemctl restart $RUNNER_SVC returned non-zero"
    fi
  fi
else
  err "no actions.runner.* service found on host — install runner first"
fi

# ---------------------------------------------------------------------- #
# 3. 内存压力（OOM kill 后自动清理 stale lock）
# ---------------------------------------------------------------------- #

LOCK="/tmp/ad_research_scheduler.lock"
if [[ -f "$LOCK" ]]; then
  LOCK_AGE_S=$(( $(date +%s) - $(stat -c %Y "$LOCK" 2>/dev/null || echo 0) ))
  if [[ "$LOCK_AGE_S" -gt 1800 ]]; then
    # 锁文件超过 30 分钟（远超正常 scheduler 周期 5min），可能是上次 OOM 留的 stale
    warn "scheduler lock age ${LOCK_AGE_S}s > 1800s — clearing stale lock"
    rm -f "$LOCK"
    err "scheduler lock cleared (was ${LOCK_AGE_S}s old)"
  fi
fi

# ---------------------------------------------------------------------- #
# 4. cascade 痕迹检查 — 上次 workflow 失败 + 间隔短 = cascade
# ---------------------------------------------------------------------- #

CASCADE_MARKER="/tmp/runner-cascade-fingerprint"
if [[ -f "$CASCADE_MARKER" ]]; then
  LAST_CASCADE_AGE=$(( $(date +%s) - $(stat -c %Y "$CASCADE_MARKER" 2>/dev/null || echo 0) ))
  if [[ "$LAST_CASCADE_AGE" -lt 3600 ]]; then
    # 1 小时内再次 cascade — 不只是 daemon restart 能修
    err "cascade-failure recurring within 1h (last: ${LAST_CASCADE_AGE}s ago) — likely host issue (RAM/CPU/disk), needs human investigation"
  fi
fi

# ---------------------------------------------------------------------- #
# 5. 触发 on-call 通知（如果有任何 NEEDS_ATTENTION）
# ---------------------------------------------------------------------- #

if [[ -n "$NEEDS_ATTENTION" ]]; then
  log "needs attention:"
  printf "$NEEDS_ATTENTION"
  # 写 marker 文件供外部 trigger 检查
  date +%s > /tmp/runner-needs-attention
  # 也标记 cascade fingerprint（如果在 cascade window）
  if [[ -f "$CASCADE_MARKER" ]] && [[ "$LAST_CASCADE_AGE" -lt 3600 ]]; then
    date +%s > "$CASCADE_MARKER"
  fi
  exit 1
fi

log "all checks passed; runner host healthy"
exit 0