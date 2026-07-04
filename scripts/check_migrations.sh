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

# ── 4.2 dump_backend_diagnostics ──
# 在 exit 20 之前调用：打印容器状态 + 最近 50 行日志，
# 避免线上 race condition 出现时只有 "RC=20" 一句话没法排查。
dump_backend_diagnostics() {
    local compose_file="${1:-}"
    local backend_svc="${2:-backend}"
    local health_url="${3:-http://localhost:8000/health}"

    echo "=== backend container 状态 ===" >&2
    docker ps -a --filter "name=${backend_svc}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" >&2 || true

    echo "=== backend 最近 50 行日志 ===" >&2
    if [ -n "$compose_file" ] && [ -f "$compose_file" ]; then
        docker compose -f "$compose_file" logs --tail 50 "${backend_svc}" >&2 || true
    else
        docker logs --tail 50 "${backend_svc}" >&2 || true
    fi

    if [ -n "$health_url" ]; then
        echo "=== ${health_url} 探活 ===" >&2
        curl -sSv -o /dev/null --max-time 5 "${health_url}" >&2 || true
    fi
}

# ── Help ──
if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    echo "用法: $0 [compose-file]"
    echo ""
    echo "  compose-file   docker-compose 文件路径（默认 ./docker-compose.yml）"
    echo ""
    echo "环境变量:"
    echo "  HEALTH_URL     backend 健康检查地址（默认 http://localhost:8000/health）"
    echo "  BACKEND_SERVICE backend 服务名（默认 backend；自动探测 alloyresearch-backend）"
    echo ""
    echo "退出码:"
    echo "  0   一切正常（current == head 且模型可导入）"
    echo "  10  需要迁移（current != head）"
    echo "  20  异常（模型导入失败 / 容器未运行 / alembic 命令失败）"
    echo ""
    echo "示例:"
    echo "  $0                                           # 本地"
    echo "  $0 deploy/aliyun-ecs/docker-compose.yml      # 阿里云 ECS"
    echo "  HEALTH_URL=http://10.0.0.5:8000/health $0   # 自定义健康检查地址"
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
# ── 注意：旧逻辑在容器处于 restarting/unhealthy 时只跑 `up -d`，docker compose
#     不会重启已存在容器，立刻返回成功但容器实际没起来，引发 race condition。
#     现改为：先用 --force-recreate 强制重建，再用循环等 running，最后做 /health 探活。
if ! docker compose -f "$COMPOSE_FILE" ps --services --filter "status=running" 2>/dev/null | grep -q "^${BACKEND_SERVICE}$"; then
    log_warn "backend 容器未运行或处于异常状态，尝试强制重建..."
    docker compose -f "$COMPOSE_FILE" up -d --force-recreate "$BACKEND_SERVICE" > /dev/null 2>&1 || {
        log_error "无法启动 backend 容器"
        dump_backend_diagnostics "$COMPOSE_FILE" "$BACKEND_SERVICE" "$HEALTH_URL"
        exit "$EXIT_ABNORMAL"
    }
fi

# ── 4.1 等 backend 至少一次进入 running 状态（最多 30s） ──
log_info "等待 backend 进入 running 状态（最多 30s）..."
for i in $(seq 1 15); do
    if docker compose -f "$COMPOSE_FILE" ps --services --filter "status=running" 2>/dev/null | grep -q "^${BACKEND_SERVICE:-backend}$"; then
        log_info "backend 已进入 running 状态"
        sleep 3  # 等 entrypoint 完全初始化
        break
    fi
    sleep 2
done

# ── 4.1 再做 /health 探活（最多 60s） ──
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/health}"
log_info "等待 backend /health 通过（最多 60s）..."
HEALTH_OK=false
for i in $(seq 1 30); do
    if curl -sf "${HEALTH_URL}" >/dev/null 2>&1; then
        log_info "backend /health 已就绪 ✓"
        HEALTH_OK=true
        break
    fi
    sleep 2
done

if [ "$HEALTH_OK" != "true" ]; then
    log_warn "backend /health 60s 内未通过，但继续后续校验（alembic 可能在容器内仍可执行）"
fi

# ── 1. alembic current ──
log_step "1/3 读取 alembic current"

CURRENT_RAW=$(docker compose -f "$COMPOSE_FILE" exec -T "$BACKEND_SERVICE" alembic current 2>&1) || {
    log_error "alembic current 执行失败"
    echo "$CURRENT_RAW"
    dump_backend_diagnostics "$COMPOSE_FILE" "$BACKEND_SERVICE" "$HEALTH_URL"
    exit "$EXIT_ABNORMAL"
}

# Extract current revision: prefer line tagged with (head), else first non-INFO hex/string ID
CURRENT=$(echo "$CURRENT_RAW" | grep -E "^[0-9a-f]{6,}.*\(head\)|^[A-Za-z0-9_]+.*\(head\)" | head -1 | awk '{print $1}' || true)
if [ -z "$CURRENT" ]; then
    CURRENT=$(echo "$CURRENT_RAW" | grep -E "^[0-9a-f]{6,}\b|^[A-Za-z0-9_]+\b" | grep -vE "^INFO" | head -1 | awk '{print $1}' || true)
fi

if [ -z "$CURRENT" ]; then
    # alembic 在空数据库上输出空内容 → 视为需要 migrate
    log_warn "alembic current 输出为空（数据库可能尚未初始化）"
    CURRENT="(empty)"
fi

log_info "alembic current: $CURRENT"

# ── 2. alembic heads 找 head ──
# 用 `alembic heads` 而不是 `alembic history`：heads 命令输出的是所有
# 当前 head revision（每行一个），不会被 history 的 "->" 行格式干扰。
# 这能正确处理 2026_07_04 起的字符串 ID migration（hex 正则匹配不到）。
log_step "2/3 读取 alembic heads"

HEADS_RAW=$(docker compose -f "$COMPOSE_FILE" exec -T "$BACKEND_SERVICE" alembic heads 2>&1) || {
    log_error "alembic heads 执行失败"
    echo "$HEADS_RAW"
    dump_backend_diagnostics "$COMPOSE_FILE" "$BACKEND_SERVICE" "$HEALTH_URL"
    exit "$EXIT_ABNORMAL"
}

# 取第一个 head revision（脚本只支持单一 head；多 head 由合并 migration 处理）
HEAD=$(echo "$HEADS_RAW" | grep -E "^[0-9a-f]{6,}\b|^[A-Za-z0-9_]+\b" | head -1 | awk '{print $1}' || true)

if [ -z "$HEAD" ]; then
    # 退化：从 history 末行解析
    # history 输出每行 "<a> -> <b> (head), msg"，head 行第三个 token 才是真正的 head
    HEAD_RAW=$(docker compose -f "$COMPOSE_FILE" exec -T "$BACKEND_SERVICE" alembic history 2>&1) || true
    HEAD=$(echo "$HEAD_RAW" | grep -E "^[0-9a-f]{6,}.*\(head\)|^[A-Za-z0-9_]+.*\(head\)" | head -1 | awk '{print $3}' || true)
fi

if [ -z "$HEAD" ]; then
    log_error "无法从 alembic history 中解析 head revision"
    dump_backend_diagnostics "$COMPOSE_FILE" "$BACKEND_SERVICE" "$HEALTH_URL"
    exit "$EXIT_ABNORMAL"
fi

log_info "alembic head:    $HEAD"

# ── 3. 校验模型导入 ──
log_step "3/3 校验模型可导入"

IMPORT_RAW=$(docker compose -f "$COMPOSE_FILE" exec -T "$BACKEND_SERVICE" \
    python -c "from app.models import *  # noqa: F401,F403" 2>&1) || {
    log_error "模型导入失败（app.models 异常）"
    echo "$IMPORT_RAW"
    dump_backend_diagnostics "$COMPOSE_FILE" "$BACKEND_SERVICE" "$HEALTH_URL"
    exit "$EXIT_ABNORMAL"
}

log_info "模型导入 ✓"

# ── 决策 ──
log_step "校验结论"

if [ "$CURRENT" = "$HEAD" ] && [ "$CURRENT" != "(empty)" ]; then
    log_info "✅ current == head（${CURRENT}），迁移完整"
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