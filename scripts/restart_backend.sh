#!/bin/bash
# Restart the backend container on the correct Docker network.
# Usage: ssh ad-research "bash /opt/ad-research/scripts/restart_backend.sh"
set -e

cd /opt/ad-research

# Ensure .env exists with required vars
if [ ! -f .env ]; then
  echo "ERROR: .env file not found at /opt/ad-research/.env"
  echo "Create one with DATABASE_URL and REDIS_URL set."
  exit 1
fi

docker rm -f adresearch-backend 2>/dev/null || true

docker run -d \
  --name adresearch-backend \
  --network aliyun-ecs_adresearch-network \
  -p 8000:8000 \
  --restart unless-stopped \
  --env-file /opt/ad-research/.env \
  -e TZ=Asia/Shanghai \
  -v /opt/ad-research:/app \
  ad-research-backend:latest \
  sh -c 'mkdir -p /app/web/dist && cp -r /dist-image/* /app/web/dist/ && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2'

echo "Waiting for backend to start..."
for i in $(seq 1 15); do
  if docker logs adresearch-backend 2>&1 | grep -q "Application startup complete"; then
    echo "Backend started successfully"
    break
  fi
  sleep 2
done

docker ps --filter name=adresearch
