#!/usr/bin/env bash
# ============================================================
# AD-Research 一键安全回滚脚本
# 用法：./scripts/rollback.sh <git-rev-before>
#
#   <git-rev-before>   要回退到的 commit hash（短 / 长均可）
#
# 行为：
#   1. 备份当前 HEAD 到 /var/log/ad-research/rollback-latest.log
#   2. git reset --hard 到目标 commit
#   3. 切换 docker 镜像 tag：ad-research:${TARGET_SHA} → ad-research:latest
#   4. 重新启动 backend / celery-worker / nginx
#   5. 容器内健康检查 60s，要求 /health status=ok
#   6. 输出变更摘要
#
# 失败处理：
#   任何阶段出错即退出，明确给出「回滚失败」提示，
#   并指引管理员跑 update.sh 重新拉取 main。
# ============================================================

set -euo pipefail

# ── 参数与环境 ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-/opt/ad-research}"
COMPOSE_DIR="${PROJECT_ROOT}/deploy/aliyun-ecs"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"
ROLLBACK_LOG_DIR="/var/log/ad-research"
ROLLBACK_LOG="${ROLLBACK_LOG_DIR}/rollback-latest.log"
BACKEND_CONTAINER="alloyresearch-backend"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "\n${GREEN}━━━ $1 ━━━${NC}"; }

# ── Help ──
if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ] || [ "$#" -lt 1 ]; then
    echo "用法: $0 <git-rev-before>"
    echo ""
    echo "  <git-rev-before>   要回退到的 commit hash（短 / 长均可）"
    echo ""
    echo "环境变量:"
    echo "  PROJECT_ROOT       项目根目录（默认 /opt/ad-research）"
    echo ""
    echo "示例:"
    echo "  $0 a5384a4"
    echo "  $0 a5384a4f3c1d9b8e7a2c4f6d8e9f0a1b2c3d4e5f"
    echo ""
    exit 0
fi

TARGET="$1"

# ── 前置检查 ──
log_step "回滚前置检查"

if [ ! -d "$PROJECT_ROOT" ]; then
    log_error "项目目录不存在：$PROJECT_ROOT（可用 PROJECT_ROOT=... 覆盖）"
    exit 1
fi

if [ ! -d "$PROJECT_ROOT/.git" ]; then
    log_error "未检测到 git 仓库：$PROJECT_ROOT/.git"
    exit 1
fi

if ! command -v git > /dev/null 2>&1; then
    log_error "未检测到 git 命令"
    exit 1
fi

if ! command -v docker > /dev/null 2>&1; then
    log_error "未检测到 docker 命令"
    exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
    log_error "compose 文件不存在：$COMPOSE_FILE"
    exit 1
fi

# 校验目标 commit 是否存在
if ! git -C "$PROJECT_ROOT" rev-parse --verify "$TARGET" > /dev/null 2>&1; then
    log_error "目标 commit 不存在或无法解析：$TARGET"
    log_info "提示：先在服务器上 git fetch origin main，确保目标 hash 已知"
    exit 1
fi

PREV=$(git -C "$PROJECT_ROOT" rev-parse HEAD)
TARGET_FULL=$(git -C "$PROJECT_ROOT" rev-parse "$TARGET")
TARGET_SHA="${TARGET_FULL:0:7}"

if [ "$PREV" = "$TARGET_FULL" ]; then
    log_warn "当前 HEAD 已是目标 commit，无需回滚：${TARGET_SHA}"
    exit 0
fi

log_info "当前 HEAD: ${PREV:0:7}"
log_info "目标 commit: ${TARGET_SHA}"

# ── 1. 备份当前 HEAD ──
log_step "1/5 备份当前 HEAD"

mkdir -p "$ROLLBACK_LOG_DIR" 2>/dev/null || {
    log_warn "无法创建 ${ROLLBACK_LOG_DIR}，回滚日志将写入 /tmp"
    ROLLBACK_LOG="/tmp/ad-research-rollback-latest.log"
}

{
    echo "============================================"
    echo "rollback timestamp: $(date -Iseconds 2>/dev/null || date)"
    echo "rollback target:    ${TARGET_FULL}"
    echo "rollback previous:  ${PREV}"
    echo "rollback operator:  ${USER:-unknown}"
    echo "============================================"
    echo ""
    echo "[git status before rollback]"
    git -C "$PROJECT_ROOT" status --short || true
    echo ""
    echo "[git log PREV..TARGET]"
    git -C "$PROJECT_ROOT" log --oneline "${PREV}..${TARGET_FULL}" || true
} >> "$ROLLBACK_LOG" 2>&1

log_info "回滚日志写入：$ROLLBACK_LOG"

# ── 2. git reset --hard ──
log_step "2/5 git reset --hard 到目标 commit"

if ! git -C "$PROJECT_ROOT" reset --hard "$TARGET_FULL" 2>&1 | tee -a "$ROLLBACK_LOG"; then
    log_error "git reset --hard 失败，仓库可能处于不一致状态"
    log_error "请人工检查：cd $PROJECT_ROOT && git status"
    log_error "或重新跑 update.sh 拉回 main"
    exit 1
fi

# ── 3. 切换镜像 tag 并重启服务 ──
log_step "3/5 切换镜像并重启服务"

# 优先复用已存在的版本 tag；如果不存在则回退到构建。
if docker image inspect "ad-research:${TARGET_SHA}" >/dev/null 2>&1; then
    log_info "复用现有镜像 tag: ad-research:${TARGET_SHA}"
    docker tag "ad-research:${TARGET_SHA}" ad-research:latest
else
    log_warn "未找到 ad-research:${TARGET_SHA}，将基于目标 commit 重新构建"
fi

export GIT_SHA="${TARGET_SHA}"

if ! (cd "$COMPOSE_DIR" && docker compose stop backend celery-worker nginx && \
      docker compose rm -f backend celery-worker nginx && \
      docker compose up -d --force-recreate backend celery-worker nginx) 2>&1 | tee -a "$ROLLBACK_LOG"; then
    log_error "docker compose 重启失败"
    log_error "回滚失败：请人工检查后跑 update.sh 重新同步到 main"
    exit 1
fi

# ── 4. 健康检查 60s ──
log_step "4/5 健康检查（最多 60s）"

HEALTH_OK=false
for i in $(seq 1 30); do
    _status=$(docker exec "${BACKEND_CONTAINER}" python -c "
import urllib.request, json
try:
    r = json.loads(urllib.request.urlopen('http://localhost:8000/health', timeout=5).read())
    print(r.get('status', 'unknown'))
except Exception:
    print('err')
" 2>/dev/null || echo "err")
    if [ "${_status}" = "ok" ]; then
        log_info "Backend /health status=ok ✓（第 ${i} 次探测）"
        HEALTH_OK=true
        break
    fi
    sleep 2
done

if [ "$HEALTH_OK" = false ]; then
    log_error "Backend 健康检查超时（60s）"
    log_error "回滚失败：容器起来了但 /health 未就绪"
    log_error "请查看：docker compose -f ${COMPOSE_FILE} logs backend --tail 100"
    log_error "可手动跑：bash ${PROJECT_ROOT}/deploy/aliyun-ecs/update.sh"
    exit 1
fi

# ── 5. 输出 release notes ──
log_step "5/5 回滚完成 — 变更摘要"

{
    echo ""
    echo "[release notes]"
    echo "PREV:  ${PREV}"
    echo "TARGET: ${TARGET_FULL}"
    echo ""
    git -C "$PROJECT_ROOT" log --oneline "${PREV}..${TARGET_FULL}" || echo "(无法生成 release notes)"
} | tee -a "$ROLLBACK_LOG"

NEW_HEAD=$(git -C "$PROJECT_ROOT" rev-parse HEAD)
log_info "当前 HEAD 已变为：${NEW_HEAD:0:7}"

echo ""
echo "  ✅ 回滚完成"
echo "  📋 日志位置：$ROLLBACK_LOG"
echo "  🔍 容器状态：docker ps | grep ${BACKEND_CONTAINER}"
echo ""
echo "  如需重新拉回 main:"
echo "    bash ${PROJECT_ROOT}/deploy/aliyun-ecs/update.sh"
echo ""
