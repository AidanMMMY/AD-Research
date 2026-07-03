#!/bin/bash
set -e
cd /opt/ad-research/deploy/aliyun-ecs
docker compose up -d --build --no-deps backend
echo "Done. Checking container:"
docker ps --filter name=alloyresearch-backend --format '{{.Names}} {{.Status}}'
