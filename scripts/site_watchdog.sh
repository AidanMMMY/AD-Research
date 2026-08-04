#!/bin/bash
# 2026-08-04: 站点拨测 + nginx 自愈 + admin 渠道告警。
#
# 背景：2026-08-04 nginx 容器在磁盘 94% 触发的激进 prune 循环中被整体
# 删除，站点断访 ~20h 无人知晓（详见
# docs/dev-notes/20260804-site-outage-nginx-pruned.md）。
# runner_healthcheck 只管 runner 主机健康，没人盯「站点本身是否可达」。
#
# 行为（每 5 分钟 cron）：
#   1. 外部视角探 https://www.alloyresearch.net/health（走公网域名，覆盖
#      DNS/证书/nginx/后端全链路）
#   2. 失败 → 查 nginx 容器状态，非 running 一律 `docker compose up -d nginx`
#      （容器被 prune 删掉也能重建），复探
#   3. 自愈失败/恢复 → 通过 backend 容器走 NotificationService.send_etl_alert
#      通知全部 active admin 渠道（邮件/企微等，复用存量配置，不引入新凭据）
#
# 用法：
#   bash /root/site_watchdog.sh
#   */5 * * * * root bash /root/site_watchdog.sh >> /var/log/site-watchdog.log 2>&1
set -uo pipefail

URL="${SITE_URL:-https://www.alloyresearch.net/health}"
COMPOSE_DIR="/opt/ad-research/deploy/aliyun-ecs"
BACKEND_CONTAINER="alloyresearch-backend"
STATE_FILE="/tmp/site-watchdog-consecutive-failures"
ALERT_STATE="/tmp/site-watchdog-last-alert"

LOG_PREFIX="[site-watchdog $(date -u +%Y-%m-%dT%H:%M:%SZ)]"
log()  { echo "$LOG_PREFIX $*"; }
warn() { echo "$LOG_PREFIX WARN: $*"; }

probe() { curl -sk -o /dev/null -w '%{http_code}' --max-time 10 "$URL" 2>/dev/null || echo "000"; }

# 告警：经 backend 容器复用 NotificationService（全部 active admin 渠道）。
# backend 也挂了就只能写日志——那是另一个量级的事故，由 runner_healthcheck
# 的 cascade 分支兜底。
alert() {
  local msg="$1"
  docker exec "$BACKEND_CONTAINER" python -c "
from app.core.database import SessionLocal
from app.services.notification_service import NotificationService
db = SessionLocal()
try:
    n = NotificationService(db).send_etl_alert('site_watchdog', '''${msg}''')
    print(f'alert sent to {n} channel(s)')
finally:
    db.close()
" 2>&1 | tail -2
}

# 告警节流：同一轮故障 30 分钟最多一次
alert_throttled() {
  local msg="$1"
  local now last
  now=$(date +%s)
  last=$(cat "$ALERT_STATE" 2>/dev/null || echo 0)
  if (( now - last >= 1800 )); then
    alert "$msg"
    echo "$now" > "$ALERT_STATE"
  fi
}

code=$(probe)
if [[ "$code" == "200" ]]; then
  fails=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
  if [[ "$fails" -gt 0 ]]; then
    log "recovered (HTTP 200, was failing x${fails})"
    alert_throttled "站点已恢复：${URL} 返回 200（此前连续失败 ${fails} 次，自愈已生效）"
  fi
  echo 0 > "$STATE_FILE"
  log "healthy (HTTP 200)"
  exit 0
fi

fails=$(( $(cat "$STATE_FILE" 2>/dev/null || echo 0) + 1 ))
echo "$fails" > "$STATE_FILE"
warn "probe failed: HTTP ${code} (consecutive=${fails})"

# 首次失败可能只是网络抖动，第二次起才动刀
if [[ "$fails" -lt 2 ]]; then
  exit 1
fi

status=$(docker inspect -f '{{.State.Status}}' alloyresearch-nginx 2>/dev/null || echo "missing")
if [[ "$status" != "running" ]]; then
  warn "nginx container status=${status} — attempting compose up -d nginx"
  (cd "$COMPOSE_DIR" && docker compose up -d nginx) 2>&1 | tail -2
  sleep 8
  code=$(probe)
  if [[ "$code" == "200" ]]; then
    log "self-heal succeeded (nginx ${status} -> running, HTTP 200)"
    alert_throttled "站点故障已自愈：nginx 容器曾处于 ${status}，已重新拉起，${URL} 恢复 200"
    echo 0 > "$STATE_FILE"
    exit 0
  fi
  warn "self-heal failed: still HTTP ${code}"
fi

alert_throttled "站点不可达：${URL} 返回 HTTP ${code}（连续 ${fails} 次），nginx 状态=${status}，自愈未生效，需人工介入"
exit 1
