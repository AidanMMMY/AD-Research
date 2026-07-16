#!/usr/bin/env bash
# ============================================================
# 统一部署健康检查脚本
# 用法：./scripts/deploy_health_check.sh [选项]
#
# 选项：
#   --from-host          通过 nginx（http://localhost:8000/health）探测
#   --container NAME     指定 backend 容器名（默认 alloyresearch-backend）
#   --timeout SECONDS    单次探测超时（默认 5）
#   --retries N          重试次数（默认 30）
#   --interval SECONDS   重试间隔（默认 2）
#   --require-status-ok  要求响应 body 中 status 字段为 "ok"（默认只检查 HTTP 200）
#
# 退出码：
#   0  健康检查通过
#   1  健康检查失败
# ============================================================

set -euo pipefail

CONTAINER="alloyresearch-backend"
FROM_HOST=false
TIMEOUT=5
RETRIES=30
INTERVAL=2
REQUIRE_STATUS_OK=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --from-host)
            FROM_HOST=true
            shift
            ;;
        --container)
            CONTAINER="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --retries)
            RETRIES="$2"
            shift 2
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        --require-status-ok)
            REQUIRE_STATUS_OK=true
            shift
            ;;
        -h|--help)
            echo "用法: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --from-host          通过 nginx（localhost:8000）探测"
            echo "  --container NAME     backend 容器名（默认 alloyresearch-backend）"
            echo "  --timeout SECONDS    单次探测超时（默认 5）"
            echo "  --retries N          重试次数（默认 30）"
            echo "  --interval SECONDS   重试间隔（默认 2）"
            echo "  --require-status-ok  要求 /health body status=ok"
            echo ""
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

_probe_container() {
    docker exec "$CONTAINER" python -c "
import urllib.request, json, sys
try:
    resp = urllib.request.urlopen('http://localhost:8000/health', timeout=${TIMEOUT})
    body = json.loads(resp.read().decode())
    if ${REQUIRE_STATUS_OK}:
        sys.exit(0 if body.get('status') == 'ok' else 1)
    else:
        sys.exit(0 if resp.status == 200 else 1)
except Exception:
    sys.exit(1)
" 2>/dev/null
}

_probe_host() {
    python -c "
import urllib.request, json, sys
try:
    resp = urllib.request.urlopen('http://localhost:8000/health', timeout=${TIMEOUT})
    body = json.loads(resp.read().decode())
    if ${REQUIRE_STATUS_OK}:
        sys.exit(0 if body.get('status') == 'ok' else 1)
    else:
        sys.exit(0 if resp.status == 200 else 1)
except Exception:
    sys.exit(1)
" 2>/dev/null
}

MODE="容器内 ${CONTAINER}"
if [ "$FROM_HOST" = true ]; then
    MODE="host localhost:8000"
fi

echo "[INFO] 健康检查模式: ${MODE}, timeout=${TIMEOUT}s, retries=${RETRIES}, interval=${INTERVAL}s"

for i in $(seq 1 "$RETRIES"); do
    if [ "$FROM_HOST" = true ]; then
        if _probe_host; then
            echo "[OK] /health 通过（第 ${i} 次）"
            exit 0
        fi
    else
        if _probe_container; then
            echo "[OK] /health 通过（第 ${i} 次）"
            exit 0
        fi
    fi
    echo "[WAIT] 第 ${i}/${RETRIES} 次探测失败，${INTERVAL}s 后重试..."
    sleep "$INTERVAL"
done

echo "::error::健康检查失败：${RETRIES} 次探测后 /health 仍未通过"
exit 1
