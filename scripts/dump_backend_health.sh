#!/bin/bash
# 2026-07-24: deploy 失败时快速 dump backend 健康状态。
# 单独成文件因为 deploy.yml `run: |` 块不支持 heredoc。
set -u

CONTAINER="${BACKEND_CONTAINER:-alloyresearch-backend}"

# 1. 容器状态
echo "=== docker ps ${CONTAINER} ==="
docker ps --filter "name=${CONTAINER}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>&1 || true

# 2. /health body（容器内）
echo ""
echo "=== /health body (in container) ==="
docker exec "${CONTAINER}" python - <<'PY' 2>&1 || true
import json
import urllib.request
try:
    resp = urllib.request.urlopen('http://localhost:8000/health', timeout=5)
    body = resp.read().decode()
    print(f'status_code: {resp.status}')
    parsed = json.loads(body)
    print(f'top-level status: {parsed.get("status")}')
    print(f'ready: {parsed.get("ready")}')
    print('components:')
    for name, c in parsed.get('components', {}).items():
        print(f'  {name}: status={c.get("status")} detail={c.get("detail", "")[:120]}')
except Exception as exc:
    print(f'error: {exc.__class__.__name__}: {exc}')
PY

# 3. alembic current + head
echo ""
echo "=== alembic current ==="
docker exec "${CONTAINER}" alembic current 2>&1 | tail -10 || true
echo ""
echo "=== alembic heads ==="
docker exec "${CONTAINER}" alembic heads 2>&1 | tail -10 || true

# 4. container logs tail
echo ""
echo "=== docker logs ${CONTAINER} (tail 50) ==="
docker logs "${CONTAINER}" --tail 50 2>&1 || true