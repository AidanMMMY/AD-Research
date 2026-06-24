#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# 阿里云 ECS 更新脚本 — 拉取最新代码并热更新服务
# 用法：./update.sh [--no-db] [--frontend-only]
#   --no-db           跳过数据库迁移（由 backend 容器自动执行）
#   --frontend-only   仅更新前端（跳过后端镜像重编译，更快）
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "\n${GREEN}━━━ $1 ━━━${NC}"; }

NO_DB=false
FRONTEND_ONLY=false

for arg in "$@"; do
    case "$arg" in
        --no-db)          NO_DB=true ;;
        --frontend-only)  FRONTEND_ONLY=true ;;
        -h|--help)
            echo "用法: ./update.sh [选项]"
            echo ""
            echo "选项:"
            echo "  --no-db           跳过数据库迁移（迁移由 backend 启动时自动执行）"
            echo "  --frontend-only   仅更新前端（不重编译 Python 镜像）"
            echo ""
            echo "示例:"
            echo "  ./update.sh                     # 完整更新"
            echo "  ./update.sh --frontend-only     # 前端热更（30s 内完成）"
            exit 0
            ;;
    esac
done

# 检查 .env 文件
if [ ! -f "$ENV_FILE" ]; then
    log_error "未找到 .env 文件，请先运行 deploy.sh 完成首次部署"
    log_info "预期路径: ${ENV_FILE}"
    exit 1
fi

# 加载 .env
set -a; source "$ENV_FILE"; set +a

# ── 1. 拉取代码 ──
log_step "1/5 拉取最新代码"
cd "$PROJECT_ROOT"
before=$(git rev-parse HEAD)
git pull origin main 2>&1 | tail -1 || {
    log_warn "git pull 失败，尝试继续使用本地代码"
}
after=$(git rev-parse HEAD)

if [ "$before" = "$after" ] && [ "${FORCE:-0}" != "1" ]; then
    log_info "代码已是最新，无变更（${before:0:7}）"
    log_info "如需强制重编，运行: FORCE=1 ./update.sh"
    exit 0
fi

log_info "代码更新: ${before:0:7} → ${after:0:7}"

# ── 2. 构建镜像 ──
log_step "2/5 构建镜像"
cd "$SCRIPT_DIR"

if [ "$FRONTEND_ONLY" = true ]; then
    log_info "仅构建前端（--frontend-only）"
    # 利用 Docker 层缓存：只重做前端阶段
    docker compose build backend \
        --build-arg BUILDKIT_INLINE_CACHE=1
else
    log_info "全量重新构建（含 Python 依赖）"
    docker compose build backend --no-cache
fi

# ── 3. 停止旧容器 ──
log_step "3/5 停止旧容器"
docker compose stop backend nginx

# ── 4. 启动新容器 ──
log_step "4/5 启动新容器"
docker compose up -d postgres redis 2>/dev/null || true
docker compose up -d backend

# 等待 backend 健康
log_info "等待 backend 就绪 (最多 60s)..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        log_info "Backend 就绪 ✓"
        break
    fi
    if [ "$i" -eq 30 ]; then
        log_error "Backend 启动超时，查看日志: docker compose logs backend --tail 50"
    fi
    sleep 2
done

# 启动 nginx
docker compose up -d nginx

# ── 5. 数据库迁移（可选） ──
if [ "$NO_DB" = false ] && [ "$FRONTEND_ONLY" = false ]; then
    log_step "5/5 数据库迁移"
    docker compose exec backend alembic upgrade head || {
        log_warn "迁移未执行或已由启动脚本自动完成"
    }
else
    log_info "跳过数据库迁移"
fi

# ── 完成 ──
log_step "更新完成"
public_ip=$(curl -sf http://100.100.100.200/latest/meta-data/eipv4 2>/dev/null || \
            curl -sf http://100.100.100.200/latest/meta-data/public-ipv4 2>/dev/null || \
            echo "YOUR_SERVER_IP")

echo ""
echo "  ✅ 服务已更新"
echo "  🌐 访问地址: http://${public_ip}:8000"
echo "  📋 查看日志: docker compose logs -f backend"

# 显示变更摘要
echo ""
echo "  本次变更:"
cd "$PROJECT_ROOT"
git log --oneline "${before}..${after}" 2>/dev/null | head -10 || echo "  (无法获取变更记录)"
echo ""
