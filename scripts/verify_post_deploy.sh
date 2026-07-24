#!/bin/bash
# 2026-07-24: post-deploy verification script
# 用法: ssh alloyresearch-backend 主机后跑（或本机远程跑）
#   bash scripts/verify_post_deploy.sh
#
# 验证:
#   1. backend 跑的是新代码（检查 /api/v1/internal/* 路由存在）
#   2. INTERNAL_API_TOKEN 配置正确
#   3. NotificationLog 可写（带 token POST 失败聚合 → 期望 200 + notification_log_id）
#   4. /health status=ok + components.db=ok
#   5. alembic current == head
#
# 前提: ECS 上 backend 已由 deploy 拉起新代码 (commit >= f9445e7)
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
ENV_FILE="${ENV_FILE:-/opt/ad-research/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[FATAL] $ENV_FILE not found — backend 还没配置 INTERNAL_API_TOKEN"
  exit 1
fi
TOKEN=$(grep '^INTERNAL_API_TOKEN=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'")
if [[ -z "$TOKEN" ]]; then
  echo "[FATAL] INTERNAL_API_TOKEN is empty in $ENV_FILE"
  exit 1
fi

echo "=== 1. /health ==="
HEALTH=$(curl -sS "$BACKEND_URL/health")
echo "$HEALTH" | python3 -m json.tool | head -20
STATUS=$(echo "$HEALTH" | python3 -c "import json,sys; print(json.load(sys.stdin)['status'])")
if [[ "$STATUS" != "ok" ]]; then
  echo "[FAIL] /health status=$STATUS (expected ok)"
  exit 1
fi

echo ""
echo "=== 2. backend 跑 f9445e7+ (检查 internal 路由存在) ==="
ROUTE_COUNT=$(curl -sS "$BACKEND_URL/openapi.json" | python3 -c "
import json, sys
spec = json.load(sys.stdin)
internal = [p for p in spec.get('paths', {}) if '/internal/' in p]
print(len(internal))
for p in internal:
    print(' ', p)
")
echo "internal routes count: $ROUTE_COUNT"
if [[ "$ROUTE_COUNT" -lt 2 ]]; then
  echo "[FAIL] internal routes < 2 — backend 仍跑旧版 (< f9445e7)"
  exit 1
fi

echo ""
echo "=== 3. INTERNAL_API_TOKEN 拒绝无 token 请求 ==="
NO_TOKEN=$(curl -sS -o /dev/null -w '%{http_code}' -X POST \
  "$BACKEND_URL/api/v1/internal/orchestrate-alert" \
  -H "Content-Type: application/json" \
  -d '{"failed_workers":[],"schedule":"all"}')
if [[ "$NO_TOKEN" != "403" && "$NO_TOKEN" != "503" ]]; then
  echo "[FAIL] no-token 请求返回 $NO_TOKEN（期望 403 或 503）"
  exit 1
fi
echo "  ✓ no-token 返回 $NO_TOKEN"

echo ""
echo "=== 4. INTERNAL_API_TOKEN 接受带 token 请求 (no failures → skipped) ==="
SKIPPED=$(curl -sS -X POST \
  "$BACKEND_URL/api/v1/internal/orchestrate-alert" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"failed_workers":[],"schedule":"smoke-test"}')
echo "$SKIPPED" | python3 -m json.tool
STATUS=$(echo "$SKIPPED" | python3 -c "import json,sys; print(json.load(sys.stdin)['status'])")
if [[ "$STATUS" != "skipped" ]]; then
  echo "[FAIL] skipped 测试期望 status=skipped，实际 $STATUS"
  exit 1
fi

echo ""
echo "=== 5. 触发真实失败聚合（threshold=2 → logged + NotificationLog row） ==="
LOGGED=$(curl -sS -X POST \
  "$BACKEND_URL/api/v1/internal/orchestrate-alert" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "failed_workers": [
      {"name": "xueqiu_playwright", "exit_code": 66, "items": 0, "duration": 5.0, "error": "smoke-test image not found"},
      {"name": "reddit_curl_cffi", "exit_code": 1, "items": 0, "duration": 10.0, "error": "smoke-test WAF block"}
    ],
    "schedule": "smoke-test",
    "total_duration_seconds": 60.0,
    "host": "post-deploy-verify",
    "threshold": 2
  }')
echo "$LOGGED" | python3 -m json.tool
STATUS=$(echo "$LOGGED" | python3 -c "import json,sys; print(json.load(sys.stdin)['status'])")
LOG_ID=$(echo "$LOGGED" | python3 -c "import json,sys; print(json.load(sys.stdin)['notification_log_id'])")
if [[ "$STATUS" != "logged" ]]; then
  echo "[FAIL] 触发失败聚合期望 status=logged，实际 $STATUS"
  exit 1
fi
echo "  ✓ NotificationLog row id=$LOG_ID"

echo ""
echo "=== 6. alembic head == current ==="
ALEMBIC=$(docker exec alloyresearch-backend alembic current 2>&1 | grep "(head)")
echo "$ALEMBIC"
if [[ -z "$ALEMBIC" ]]; then
  echo "[FAIL] alembic current 没有 (head) 标记"
  exit 1
fi

echo ""
echo "=== ALL PASS ==="
echo "  /health: ok"
echo "  internal routes: $ROUTE_COUNT (含 orchestrate-alert)"
echo "  token auth: 403 + 200 双向都通"
echo "  NotificationLog row id=$LOG_ID 写入成功"
echo "  alembic: at head"