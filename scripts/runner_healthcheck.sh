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
#   1. 磁盘 /data > 95% → 受控 prune（见下方注释，绝不裸 -af）
#   2. runner daemon inactive/failed → systemctl restart
#   3. 仍有 STEP 5 cascade 痕迹 → 通知 on-call（写到 /tmp/runner-needs-attention）
#
# 设计原则：仅做低风险操作（prune/restart）；不动工作树数据；不动 docker compose up。
#
# 2026-08-04 事故教训（站点断访 20h）：
#   旧逻辑 /data ≥90% 就每 5min `docker system prune -af`。
#   当 nginx 处于崩溃-重启循环时，容器一旦被 prune 删掉 → 网站直接黑掉，
#   且 web_dist 命名卷在容器消失后变成 unreferenced，若叠加 --volumes
#   深 prune 连前端构建产物都会被删。因此：
#   - 阈值 90% → 95%（120G 盘的 90% 还剩 12G，够人工介入窗口）
#   - 停止容器只清 72h+ 且不带 compose 项目标签的（栈内容器留尸排查）
#   - 镜像只清悬空层；未引用镜像要 168h+ 才清（崩溃循环中的容器镜像受保护）
#   - 永不带 --volumes（命名卷 = pg 数据/前端产物，命名卷必须人工删）
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

# 受控 prune：只动「与运行栈无关」的资源。compose 项目标签保护栈内容器/卷。
# （label!= 过滤对 container/volume prune 有效；compose v2 自动打
#   com.docker.compose.project=aliyun-ecs 标签）
COMPOSE_PROJECT="aliyun-ecs"

if [[ "$DISK_PCT" -ge 95 ]]; then
  warn "disk /data ${DISK_PCT}% — running GUARDED prune (no -a, no --volumes, compose stack protected)"
  docker container prune -f --filter "until=72h" \
    --filter "label!=com.docker.compose.project=${COMPOSE_PROJECT}" 2>&1 | tail -2
  docker image prune -f 2>&1 | tail -2
  docker image prune -af --filter "until=168h" 2>&1 | tail -2
  err "/data was ${DISK_PCT}% — guarded prune done (stack containers/volumes untouched)"
fi

if [[ "$DOCKER_PCT" -ge 97 ]]; then
  warn "disk /var/lib/docker ${DOCKER_PCT}% — deep prune (still no named volumes)"
  docker container prune -f --filter "until=72h" \
    --filter "label!=com.docker.compose.project=${COMPOSE_PROJECT}" 2>&1 | tail -2
  docker image prune -af --filter "until=72h" 2>&1 | tail -2
  docker volume prune -f \
    --filter "label!=com.docker.compose.project=${COMPOSE_PROJECT}" 2>&1 | tail -2
  err "/var/lib/docker was ${DOCKER_PCT}% — deep pruned (named stack volumes protected)"
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
  awk '{print $1}' | grep -iE '(runner|actions)' | head -1 || echo "")

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
  err "no runner/github-runner service found on host — install runner first"
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