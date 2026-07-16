#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# 阿里云 ECS 更新脚本 — 热更新服务
# 用法：./update.sh [--no-db] [--frontend-only]
#   --no-db           跳过数据库迁移校验（backend 入口仍会执行迁移）
#   --frontend-only   仅更新前端（跳过后端镜像重编译，更快）
#
# 注意：
#   代码同步由调用方（如 GitHub Actions deploy.yml）负责。本脚本只读取
#   当前 HEAD 并构建镜像。backend 容器入口是唯一的 alembic 升级执行点。
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
# ── 4.5 Race-condition 防护：自动/手动 deploy 互斥 ──
# 背景：
#   旧实现用两个独立锁文件 + 两个 trap，第二个 trap 会覆盖第一个，
#   导致 FORCE=1 的自动 deploy 遗留永久手动锁；且逻辑上把"手动锁"
#   与"FORCE=1"混用，auto/manual 互斥形同虚设。
#
# 机制：
#   使用 flock 做真正的跨进程互斥锁。无论手动还是自动 deploy，
#   启动时尝试获取 /var/run/ad-research-deploy.lock 的非阻塞排他锁；
#   获取失败说明已有其他 deploy 在运行，立即退出让路。
#   trap 确保本进程退出时释放锁并删除锁文件。
LOCK_FILE="${LOCK_FILE:-/var/run/ad-research-deploy.lock}"

_cleanup_deploy_lock() {
    rm -f "$LOCK_FILE"
}
trap _cleanup_deploy_lock EXIT

# 确保锁文件存在（flock 需要一个已存在的文件描述符目标）
mkdir -p "$(dirname "$LOCK_FILE")" 2>/dev/null || true
: > "$LOCK_FILE" 2>/dev/null || {
    log_warn "无法写入锁文件 ${LOCK_FILE}（可能缺权限），继续运行但互斥失效"
}

# 尝试获取非阻塞排他锁
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    log_info "检测到另一个 deploy 进程正在运行，本次让路退出"
    log_info "（如需强制覆盖：先确认无其他 update.sh 在跑，或删除 ${LOCK_FILE}）"
    exit 0
fi
echo "$$ $(date -Iseconds 2>/dev/null || date) $0 FORCE=${FORCE:-0} HOST=$(hostname)" >&200
log_info "已获取 deploy 互斥锁: ${LOCK_FILE}"

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

# 读取当前代码版本（由调用方负责同步）
GIT_SHA=$(git rev-parse --short HEAD)
log_info "当前部署版本: ${GIT_SHA}"
export GIT_SHA

# ── 1. 构建镜像 ──
log_step "1/4 构建镜像"
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
    _BUILD_ARGS="--no-cache --build-arg BUILDKIT_INLINE_CACHE=1 --build-arg GIT_SHA=${GIT_SHA}"
    if ! docker compose build backend ${_BUILD_ARGS}; then
        log_warn "首次 docker compose build 失败（多为阿里云 registry 抖动），5s 后重试一次"
        sleep 5
        docker compose build backend ${_BUILD_ARGS}
    fi
    # 给镜像打 latest tag，便于 compose 默认引用；版本 tag 已由 compose 构建时生成
    docker tag "ad-research:${GIT_SHA}" ad-research:latest || log_warn "latest tag 打标失败"
    BUILD_END=$(date +%s)
    BUILD_ELAPSED=$((BUILD_END - BUILD_START))
    if [ "$BUILD_ELAPSED" -lt 30 ]; then
        log_warn "docker compose build 仅用 ${BUILD_ELAPSED}s，可能未真正重建"
        log_warn "建议检查 docker buildx cache 状态或手动重 build"
    else
        log_info "构建耗时 ${BUILD_ELAPSED}s"
    fi
fi

# ── 2. 停止旧容器 ──
log_step "2/4 停止旧容器"
docker compose stop backend nginx celery-worker

# ── 2.5 清理可能残留的孤儿容器（防止上一次 deploy 失败留下同名容器导致 Conflict）
log_step "2.5/4 清理残留容器"
# 用子 shell + set +e 显式关闭 errexit/pipefail，避免 `docker compose rm` 返回 5
# 或 `docker compose ls | jq` 管道失败时让整段脚本中断（set -euo pipefail 会）。
# 只清理本 compose project 的容器，绝不影响其他项目或手动容器。
(
    set +e
    docker compose rm -f -s backend celery-worker nginx >/dev/null 2>&1
    true
)

# ── 3. 启动新容器 ──
log_step "3/4 启动新容器"
docker compose up -d postgres redis 2>/dev/null || true
docker compose up -d --force-recreate backend celery-worker

# 等待 backend 健康
# ── ops P1-13 ──
# /health 现在始终返回 200，并在 body 里按组件报告状态（db/redis/scheduler/data）。
# 因此不能再只看 HTTP 状态码，必须解析 body 的 "status" 字段：
#   - status == "ok"        → 关键依赖(DB/Redis)就绪，放行
#   - status == "degraded"  → 进程活着但依赖未就绪，继续等待（多见于 DB 尚在迁移/预热）
# 等待窗口从 60s 提升到 120s（60 次 × 2s），给冷启动 + 迁移预热留足时间。
BACKEND_CONTAINER="${BACKEND_CONTAINER:-alloyresearch-backend}"
log_info "等待 backend 就绪 (最多 120s，需 /health status=ok)..."
_backend_ready=false
for i in $(seq 1 60); do
    # backend service 只 expose 8000 给容器网络，没有映射到 host，
    # 因此不能从 host curl localhost:8000/health。在容器内探测。
    # 使用单行的 python -c，避免某些 Docker/shell 环境下 heredoc 无输出。
    _body=$(docker exec "${BACKEND_CONTAINER}" python -c "
import urllib.request
try:
    print(urllib.request.urlopen('http://localhost:8000/health', timeout=5).read().decode())
except Exception:
    pass
" 2>/dev/null || true)
    if [ -n "$_body" ]; then
        # grep 兼容无 jq 环境：匹配 "status":"ok"（容忍空格）。
        if printf '%s' "$_body" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"'; then
            log_info "Backend 就绪 ✓ (/health status=ok)"
            _backend_ready=true
            break
        fi
        # 进程已响应但依赖降级——打印一次组件明细，便于定位。
        if [ "$((i % 10))" -eq 0 ]; then
            log_warn "backend 已响应但 /health 未就绪 (第 ${i} 次): ${_body}"
        fi
    fi
    sleep 2
done

if [ "$_backend_ready" = false ]; then
    log_error "Backend 启动超时或依赖未就绪，查看日志: docker compose logs backend --tail 50; 健康详情: docker exec ${BACKEND_CONTAINER} python -c \"import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health', timeout=5).read().decode())\""
    # Action-253 root-cause: previously exited 0 even when /health
    # never came up, masking real failures (pool exhaustion, missing
    # migrations, import errors). Refuse to continue to nginx so the
    # deploy workflow's "Backend smoke check" can flag the run.
    exit 1
fi

# 启动 nginx
docker compose up -d nginx

# ── 4. 数据库迁移状态校验 ──
# backend 容器入口是唯一的 alembic upgrade head 执行点。这里只做只读校验，
# 如果 current != head 说明入口迁移失败或未执行，必须退出让调用方处理。
if [ "$NO_DB" = false ] && [ "$FRONTEND_ONLY" = false ]; then
    log_step "4/4 数据库迁移状态校验"
    CURRENT_REV=$(docker compose exec -T backend alembic current 2>/dev/null \
        | awk 'NF && $1 !~ /^INFO/ { print $1; exit }' || true)
    HEAD_REV=$(docker compose exec -T backend alembic heads 2>/dev/null \
        | awk '/\(head\)/ { print $1; exit }' || true)

    if [ -n "$CURRENT_REV" ] && [ -n "$HEAD_REV" ] && [ "$CURRENT_REV" = "$HEAD_REV" ]; then
        log_info "alembic current 已等于 head（${HEAD_REV}）"
    else
        log_error "alembic current=${CURRENT_REV:-<empty>} 与 head=${HEAD_REV:-<unknown>} 不一致，backend 入口迁移可能失败"
        exit 1
    fi
else
    log_info "跳过数据库迁移状态校验"
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
echo "  🔖 当前版本: ${GIT_SHA}"
echo ""
