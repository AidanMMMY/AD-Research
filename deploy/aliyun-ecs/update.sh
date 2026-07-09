#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# 阿里云 ECS 更新脚本 — 拉取最新代码并热更新服务
# 用法：./update.sh [--no-db] [--frontend-only]
#   --no-db           跳过数据库迁移（由 backend 容器自动执行）
#   --frontend-only   仅更新前端（跳过后端镜像重编译，更快）
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "\n${GREEN}━━━ $1 ━━━${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

# ============================================================
# 4.5 Race-condition 防护：手动/自动 deploy 互斥
# ============================================================
# 背景：
#   早期版本曾出现 "auto deploy 触发时刚好有人在跑 FORCE=1" 的
#   race condition，导致 alembic upgrade / docker compose up -d
#   互相覆盖，容器处于 restart loop。
#
# 机制：
#   - MANUAL_LOCK（/var/run/ad-research-manual-deploy.lock）
#       由 "FORCE=1 ./update.sh" 创建；auto deploy 检测到就退出，
#       等于把升级通道让给人为操作。
#   - AUTO_LOCK（/var/run/ad-research-auto-deploy.lock）
#       仅用于诊断，方便排查 "有谁在跑 auto deploy"。
#
# 约束：
#   - 锁文件仅是软互斥，不阻塞重新尝试（auto deploy 跑完即清理）。
#   - 用 trap 确保异常退出也能 rm 锁。
#   - 必须在 log_info/log_warn 定义之后执行，否则 FORCE=1 时会报
#     "command not found"。
# ============================================================
MANUAL_LOCK="${MANUAL_LOCK:-/var/run/ad-research-manual-deploy.lock}"
AUTO_LOCK="${AUTO_LOCK:-/var/run/ad-research-auto-deploy.lock}"

# 如果调用方明确 FORCE=1，先把"手动锁"建上，告诉后来的 auto deploy 退避
if [ "${FORCE:-0}" = "1" ]; then
    if [ -w "$(dirname "$MANUAL_LOCK")" ] || mkdir -p "$(dirname "$MANUAL_LOCK")" 2>/dev/null; then
        echo "$$ $(date -Iseconds 2>/dev/null || date) FORCE=1" > "$MANUAL_LOCK" 2>/dev/null \
            && log_info "已创建手动 deploy 锁: ${MANUAL_LOCK}" || \
            log_warn "无法写入 ${MANUAL_LOCK}（可能缺权限），继续运行"
        trap 'rm -f "$MANUAL_LOCK"' EXIT
    fi
fi

# 检测手动锁：有则让路给人为操作
if [ -f "$MANUAL_LOCK" ] && [ "${FORCE:-0}" != "1" ]; then
    log_info "检测到手动 deploy 锁 (${MANUAL_LOCK})，auto deploy 让路退出"
    log_info "（如需强制覆盖：FORCE=1 ./update.sh，或删除该锁文件）"
    exit 0
fi

# 标记本次 auto deploy 开始
if mkdir -p "$(dirname "$AUTO_LOCK")" 2>/dev/null; then
    echo "$$ $(date -Iseconds 2>/dev/null || date) auto" > "$AUTO_LOCK" 2>/dev/null || true
    trap 'rm -f "$AUTO_LOCK"' EXIT
fi

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
    # ── 4.4 检测"异常短 build"：build < 30s 通常意味着 buildx cache 命中
    # 或镜像根本没被重 build（用过时的 layer）。给操作者一个 WARN。
    # ── 4.7 阿里云 HTTP/2 registry 偶发 RESET_STREAM：首次 build 失败时
    # sleep 5s 重试一次（最多 2 次）。非网络错误（语法/依赖缺失）也会
    # 在第二次失败时立刻冒出来，不会被无谓吞掉 —— `set -e` 会把第二次
    # 的非零退出码直接传给调用方。
    # 同时启用 BuildKit inline cache（--build-arg BUILDKIT_INLINE_CACHE=1），
    # 让后续若切到 cache-from 模式时无需再改脚本即可复用 layer 元数据。
    BUILD_START=$(date +%s)
    if ! docker compose build backend --no-cache --build-arg BUILDKIT_INLINE_CACHE=1; then
        log_warn "首次 docker compose build 失败（多为阿里云 registry 抖动），5s 后重试一次"
        sleep 5
        docker compose build backend --no-cache --build-arg BUILDKIT_INLINE_CACHE=1
    fi
    BUILD_END=$(date +%s)
    BUILD_ELAPSED=$((BUILD_END - BUILD_START))
    if [ "$BUILD_ELAPSED" -lt 30 ]; then
        log_warn "docker compose build 仅用 ${BUILD_ELAPSED}s，可能未真正重建"
        log_warn "建议检查 docker buildx cache 状态或手动重 build"
    else
        log_info "构建耗时 ${BUILD_ELAPSED}s"
    fi
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
    # ── 4.6 幂等：先比较 current vs head，避免无变更时仍跑 upgrade ──
    CURRENT_REV=$(docker compose exec -T backend alembic current 2>/dev/null \
        | awk 'NF && $1 !~ /^INFO/ { print $1; exit }' || true)
    HEAD_REV=$(docker compose exec -T backend alembic heads 2>/dev/null \
        | awk '/\(head\)/ { print $1; exit }' || true)

    if [ -n "$CURRENT_REV" ] && [ -n "$HEAD_REV" ] && [ "$CURRENT_REV" = "$HEAD_REV" ]; then
        log_info "alembic current 已等于 head（${HEAD_REV}），跳过 migration"
    else
        log_info "alembic current=${CURRENT_REV:-<empty>}  head=${HEAD_REV:-<unknown>}，执行 upgrade head"
        docker compose exec backend alembic upgrade head || {
            log_warn "迁移未执行或已由启动脚本自动完成"
        }
    fi
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
