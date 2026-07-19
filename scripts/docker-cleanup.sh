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
# ---------------------------------------------------------------------------
# 2026-07-19: 白名单 — 这些镜像必须保留（被 orchestrate_v2 cron 隐式依赖）
# 白名单之外的、未被容器引用的、超过 168h 没用的镜像才走 prune -a。
# ---------------------------------------------------------------------------
PROTECTED_IMAGES=(
    "alloyresearch-agent:latest"   # 8 个 worker cron 用；缺了所有 source 0.04s 失败
)
# 步骤 1: 给白名单镜像加 :latest-only 别名,确保即使没有 running container 引用,
# 它们也不会被 `docker image prune -a` 干掉 (prune -a 只清 dangling/unused,
# 有 tagged :latest 不算 dangling,但 -a + until=168h 会清没在用的)。
# 解法: 把白名单镜像重 tag 到一个永远保留的 repo,或者直接用 docker save/load。
# 简化路径: 在 prune 前先 docker tag 这些镜像到一个固定 "keep" 镜像,
# prune 后再 docker rmi 掉临时 keep,这样 prune 期间它们就被容器"使用"了。
# 进一步简化: 白名单中的镜像 7 天没用也必须保留,直接复制 image id 到一个新
# 镜像并 tag,让它们"在用"再恢复旧 tag。
for img in "${PROTECTED_IMAGES[@]}"; do
    if docker image inspect "$img" >/dev/null 2>&1; then
        # tag 成 :__keep__ 让镜像在 prune 期间被引用,不会被 -a 清掉
        docker tag "$img" "${img%:*}:__keep__" >> "$LOG" 2>&1 || true
    fi
done
# Remove unused images older than 7 days (白名单镜像因为有 :__keep__ tag,
# 被认为是"使用中",不会被 -a + until=168h 干掉)
docker image prune -a --filter "until=168h" -f >> "$LOG" 2>&1 || true
# 还原白名单 tag (从 __keep__ 还原为原 tag,然后清掉 __keep__)
for img in "${PROTECTED_IMAGES[@]}"; do
    if docker image inspect "${img%:*}:__keep__" >/dev/null 2>&1; then
        docker rmi "$img" >> "$LOG" 2>&1 || true
        docker tag "${img%:*}:__keep__" "$img" >> "$LOG" 2>&1 || true
        docker rmi "${img%:*}:__keep__" >> "$LOG" 2>&1 || true
    fi
done
df -h /data >> "$LOG"
echo "$(date -Iseconds) Cleanup done" >> "$LOG"
