#!/bin/bash
# Weekly cleanup of old Docker images and build cache on ECS
set -e
LOG=/var/log/docker-cleanup.log
echo "$(date -Iseconds) Starting cleanup" >> "$LOG"
df -h /data >> "$LOG"
# Remove dangling images
docker image prune -f >> "$LOG" 2>&1 || true
# Prune build cache (aggressive but safe)
docker builder prune -f >> "$LOG" 2>&1 || true
# Remove unused images older than 7 days (keep tagged current)
docker image prune -a --filter "until=168h" -f >> "$LOG" 2>&1 || true
df -h /data >> "$LOG"
echo "$(date -Iseconds) Cleanup done" >> "$LOG"
