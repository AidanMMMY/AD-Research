#!/bin/bash
set -e
cd /opt/ad-research/deploy/aliyun-ecs

echo "=== Rebuilding nginx (SSE config update) ==="
docker compose up -d --build --no-deps nginx

echo "=== Rebuilding backend (new env vars) ==="
docker compose up -d --build --no-deps backend

sleep 5
echo "=== Status ==="
docker ps --format '{{.Names}} {{.Status}}'
