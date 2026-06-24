#!/usr/bin/env bash
set -euo pipefail

# 数据库迁移脚本：从 etf_research 迁移到 ad_research
# 支持本地 Docker Compose 环境和阿里云 ECS 环境
#
# 用法：
#   本地开发：./scripts/migrate_database.sh
#   阿里云 ECS：./scripts/migrate_database.sh deploy/aliyun-ecs/docker-compose.yml
#
# 迁移前会自动备份旧库数据到 /tmp/etf_research_backup_*.sql

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 默认使用本地 docker-compose.yml
COMPOSE_FILE="${1:-${PROJECT_ROOT}/docker-compose.yml}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# 检测 compose 文件是否存在
if [ ! -f "$COMPOSE_FILE" ]; then
    log_error "未找到 docker-compose 文件：$COMPOSE_FILE"
    log_info "用法：$0 [path/to/docker-compose.yml]"
    exit 1
fi

COMPOSE_DIR="$(cd "$(dirname "$COMPOSE_FILE")" && pwd)"
COMPOSE_BASENAME="$(basename "$COMPOSE_FILE")"

# 构建 docker compose 命令
docker_compose_cmd() {
    docker compose -f "$COMPOSE_FILE" "$@"
}

# 在 postgres 容器内执行 psql
psql_exec() {
    local db="${1:-postgres}"
    shift || true
    docker_compose_cmd exec -T postgres psql -U etf -d "$db" "$@"
}

# 检查服务是否运行
check_services() {
    log_step "检查 PostgreSQL 服务是否运行..."
    if ! docker_compose_cmd ps | grep -q "postgres"; then
        log_warn "PostgreSQL 容器未运行，尝试启动..."
        docker_compose_cmd up -d postgres
        sleep 5
    fi

    # 等待数据库就绪
    local retries=0
    while [ $retries -lt 30 ]; do
        if docker_compose_cmd exec -T postgres pg_isready -U etf > /dev/null 2>&1; then
            log_info "PostgreSQL 已就绪"
            return 0
        fi
        retries=$((retries + 1))
        echo "等待 PostgreSQL 就绪... ($retries/30)"
        sleep 2
    done

    log_error "PostgreSQL 无法就绪，请检查服务状态"
    exit 1
}

# 主流程
main() {
    log_info "开始数据库迁移：etf_research → ad_research"
    log_info "使用的 compose 文件：$COMPOSE_FILE"

    check_services

    # 检查源数据库是否存在
    log_step "检查源数据库 etf_research..."
    if ! psql_exec postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'etf_research'" | grep -q 1; then
        log_error "源数据库 etf_research 不存在，无需迁移"
        exit 1
    fi
    log_info "源数据库 etf_research 存在"

    # 检查目标数据库是否存在
    log_step "检查目标数据库 ad_research..."
    if psql_exec postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'ad_research'" | grep -q 1; then
        log_warn "目标数据库 ad_research 已存在"
        read -p "是否删除并重新迁移？(y/N): " confirm
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            log_warn "正在删除目标数据库 ad_research..."
            psql_exec postgres -c "DROP DATABASE ad_research;"
        else
            log_info "取消迁移"
            exit 0
        fi
    fi

    # 检查目标数据库是否存在
    log_step "检查目标数据库 ad_research..."
    if psql_exec postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'ad_research'" | grep -q 1; then
        log_warn "目标数据库 ad_research 已存在"
        read -p "是否删除并重新迁移？(y/N): " confirm
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            log_warn "正在删除目标数据库 ad_research..."
            psql_exec postgres -c "DROP DATABASE ad_research;"
        else
            log_info "取消迁移"
            exit 0
        fi
    fi

    # 方式一：如果源库没有其他连接，使用 TEMPLATE 方式最快
    log_step "尝试使用 TEMPLATE 方式快速复制数据库..."
    if psql_exec postgres -c "CREATE DATABASE ad_research WITH TEMPLATE etf_research OWNER etf;" 2> /tmp/migrate_template_error.log; then
        log_info "✅ TEMPLATE 方式复制成功"
    else
        log_warn "TEMPLATE 方式失败（可能源库有活动连接），切换到 pg_dump/psql 方式..."
        cat /tmp/migrate_template_error.log

        # 创建目标数据库
        psql_exec postgres -c "CREATE DATABASE ad_research OWNER etf;"

        # 备份源数据库
        BACKUP_FILE="/tmp/etf_research_backup_$(date +%Y%m%d_%H%M%S).sql"
        log_step "备份源数据库到 $BACKUP_FILE..."
        docker_compose_cmd exec -T postgres pg_dump -U etf -d etf_research --no-owner --no-privileges > "$BACKUP_FILE"
        log_info "备份完成：$(ls -lh "$BACKUP_FILE" | awk '{print $5}')"

        # 恢复到目标数据库
        log_step "恢复数据到 ad_research..."
        docker_compose_cmd exec -T postgres psql -U etf -d ad_research < "$BACKUP_FILE"
        log_info "✅ pg_dump/psql 方式迁移成功"
    fi

    # 验证迁移结果
    log_step "验证迁移结果..."
    local source_count target_count
    source_count=$(psql_exec etf_research -tc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" | xargs)
    target_count=$(psql_exec ad_research -tc "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" | xargs)

    log_info "源库表数量：$source_count"
    log_info "目标库表数量：$target_count"

    if [ "$source_count" -eq "$target_count" ]; then
        log_info "✅ 迁移验证通过"
        echo ""
        log_info "迁移完成！现在可以："
        log_info "  1. 更新你的 .env 文件，确保 DATABASE_URL 使用 ad_research"
        log_info "  2. 重启后端服务：docker compose -f $COMPOSE_FILE restart backend"
        log_info "  3. （可选）确认无误后删除旧库：docker compose exec postgres dropdb -U etf etf_research"
    else
        log_error "❌ 迁移验证失败：表数量不一致"
        exit 1
    fi
}

main "$@"
