#!/usr/bin/env bash
# ============================================================
# 部署前后 Alembic 迁移完整性校验
# 用法：./scripts/check_migrations.sh [compose-file]
#
# 默认 compose-file：./docker-compose.yml
# 阿里云 ECS：./scripts/check_migrations.sh deploy/aliyun-ecs/docker-compose.yml
#
# 行为：
#   1. 进入 backend 容器执行 `alembic current` 拿当前版本
#   2. 进入 backend 容器执行 `alembic history` 拿最新版本
#   3. 若 current != head  → 退出码 10（需 migrate）
#   4. 尝试 `python -c "from app.models import *"` 验证模型可导入
#   5. 若模型导入失败 → 退出码 20（异常）
#   6. 一切正常 → 退出码 0
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 默认 compose 文件：本地
COMPOSE_FILE="${1:-${PROJECT_ROOT}/docker-compose.yml}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }

# 退出码常量
EXIT_OK=0
EXIT_NEED_MIGRATE=10
EXIT_ABNORMAL=20

# ── Help ──
if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    echo "用法: $0 [compose-file]"
    echo ""
    echo "  compose-file   docker-compose 文件路径（默认 ./docker-compose.yml）"
    echo ""
    echo "退出码:"
    echo "  0   一切正常（current == head 且模型可导入）"
    echo "  10  需要迁移（current != head）"
    echo "  20  异常（模型导入失败 / 容器未运行 / alembic 命令失败）"
    echo ""
    echo "示例:"
    echo "  $0                                           # 本地"
    echo "  $0 deploy/aliyun-ecs/docker-compose.yml      # 阿里云 ECS"
    exit 0
fi

# ── 前置检查 ──
log_step "校验 alembic 迁移完整性"
log_info "compose file: $COMPOSE_FILE"

if [ ! -f "$COMPOSE_FILE" ]; then
    log_error "compose 文件不存在：$COMPOSE_FILE"
    exit "$EXIT_ABNORMAL"
fi

if ! command -v docker > /dev/null 2>&1; then
    log_error "未检测到 docker 命令"
    exit "$EXIT_ABNORMAL"
fi

COMPOSE_DIR="$(cd "$(dirname "$COMPOSE_FILE")" && pwd)"
COMPOSE_BASENAME="$(basename "$COMPOSE_FILE")"

# 选择 backend 服务名（兼容本地与 aliyun-ecs）
BACKEND_SERVICE="backend"
if docker compose -f "$COMPOSE_FILE" config --services 2>/dev/null | grep -q "^backend$"; then
    BACKEND_SERVICE="backend"
elif docker compose -f "$COMPOSE_FILE" config --services 2>/dev/null | grep -q "^alloyresearch-backend$"; then
    BACKEND_SERVICE="alloyresearch-backend"
else
    log_warn "compose 文件中未找到 backend 服务，尝试默认 'backend'"
fi

log_info "backend service: $BACKEND_SERVICE"

# 检查 backend 容器是否在运行
if ! docker compose -f "$COMPOSE_FILE" ps --services --filter "status=running" 2>/dev/null | grep -q "^${BACKEND_SERVICE}$"; then
    log_warn "backend 容器未运行，先启动..."
    docker compose -f "$COMPOSE_FILE" up -d "$BACKEND_SERVICE" > /dev/null 2>&1 || {
        log_error "无法启动 backend 容器"
        exit "$EXIT_ABNORMAL"
    }
    sleep 5
fi

# ── 1. alembic current ──
log_step "1/3 读取 alembic current"

CURRENT_RAW=$(docker compose -f "$COMPOSE_FILE" exec -T "$BACKEND_SERVICE" alembic current 2>&1) || {
    log_error "alembic current 执行失败"
    echo "$CURRENT_RAW"
    exit "$EXIT_ABNORMAL"
}

CURRENT=$(echo "$CURRENT_RAW" | grep -E "^[0-9a-f]{6,}" | head -1 | awk '{print $1}' || true)

if [ -z "$CURRENT" ]; then
    # alembic 在空数据库上输出空内容 → 视为需要 migrate
    log_warn "alembic current 输出为空（数据库可能尚未初始化）"
    CURRENT="(empty)"
fi

log_info "alembic current: $CURRENT"

# ── 2. alembic history 找 head ──
log_step "2/3 读取 alembic history head"

HEAD_RAW=$(docker compose -f "$COMPOSE_FILE" exec -T "$BACKEND_SERVICE" alembic history 2>&1) || {
    log_error "alembic history 执行失败"
    echo "$HEAD_RAW"
    exit "$EXIT_ABNORMAL"
}

# head 通常是历史列表的最后一条，带 (head) 标记
HEAD=$(echo "$HEAD_RAW" | grep -E "^[0-9a-f]{6,}.*\(head\)" | head -1 | awk '{print $1}' || true)

if [ -z "$HEAD" ]; then
    # 退化：取最后一条 revision
    HEAD=$(echo "$HEAD_RAW" | grep -E "^[0-9a-f]{6,}" | tail -1 | awk '{print $1}' || true)
fi

if [ -z "$HEAD" ]; then
    log_error "无法从 alembic history 中解析 head revision"
    exit "$EXIT_ABNORMAL"
fi

log_info "alembic head:    $HEAD"

# ── 3. 校验模型导入 ──
log_step "3/3 校验模型可导入"

IMPORT_RAW=$(docker compose -f "$COMPOSE_FILE" exec -T "$BACKEND_SERVICE" \
    python -c "from app.models import *  # noqa: F401,F403" 2>&1) || {
    log_error "模型导入失败（app.models 异常）"
    echo "$IMPORT_RAW"
    exit "$EXIT_ABNORMAL"
}

log_info "模型导入 ✓"

# ── 决策 ──
log_step "校验结论"

if [ "$CURRENT" = "$HEAD" ] && [ "$CURRENT" != "(empty)" ]; then
    log_info "✅ current == head（${CURRENT:0:7}），迁移完整"
    exit "$EXIT_OK"
fi

if [ "$CURRENT" = "(empty)" ] || [ "$CURRENT" != "$HEAD" ]; then
    log_warn "⚠️  需要数据库迁移"
    log_warn "   current: $CURRENT"
    log_warn "   head:    $HEAD"
    log_warn "   修复:    bash deploy/aliyun-ecs/update.sh   （会自动 alembic upgrade head）"
    exit "$EXIT_NEED_MIGRATE"
fi

log_error "未预期的状态：current=$CURRENT head=$HEAD"
exit "$EXIT_ABNORMAL"