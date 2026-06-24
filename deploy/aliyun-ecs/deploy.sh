#!/usr/bin/env bash
set -euo pipefail

# 阿里云 ECS 一键部署脚本
# 用法：
#   1. 将项目代码上传到服务器（如 /opt/ad-research）
#   2. cd /opt/ad-research/deploy/aliyun-ecs
#   3. chmod +x deploy.sh
#   4. ./deploy.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检测 Linux 发行版
# 输出格式：ID|VERSION_CODENAME，例如 ubuntu|plucky
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "${ID}|${VERSION_CODENAME:-}"
    else
        echo "unknown|"
    fi
}

# 安装基础工具（git、curl、gnupg、ca-certificates 等）
install_base_tools() {
    local os_id
    os_id=$(detect_os | cut -d'|' -f1)

    log_info "安装基础工具..."
    case "$os_id" in
        ubuntu|debian)
            apt-get update
            apt-get install -y git curl gnupg ca-certificates openssl
            ;;
        centos|rhel|almalinux|rocky|alinux)
            yum install -y git curl gnupg ca-certificates openssl
            ;;
        *)
            log_warn "未知发行版，跳过基础工具安装"
            ;;
    esac
}

# 安装 Docker
install_docker() {
    if command -v docker > /dev/null 2>&1; then
        log_info "Docker 已安装：$(docker --version)"
        return
    fi

    local os_info os_id os_codename
    os_info=$(detect_os)
    os_id=$(echo "$os_info" | cut -d'|' -f1)
    os_codename=$(echo "$os_info" | cut -d'|' -f2)

    log_info "正在安装 Docker（发行版：$os_id，代号：$os_codename）..."

    case "$os_id" in
        ubuntu|debian)
            apt-get update
            apt-get install -y ca-certificates curl gnupg
            install -m 0755 -d /etc/apt/keyrings
            curl -fsSL "https://download.docker.com/linux/$os_id/gpg" | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
            chmod a+r /etc/apt/keyrings/docker.gpg

            # Docker 官方可能暂未提供 Ubuntu 26.04 (plucky) 的仓库，
            # 临时回退到上一个 LTS (noble / 24.04) 的仓库，兼容性良好
            local docker_codename="$os_codename"
            if [ "$os_id" = "ubuntu" ] && [ "$os_codename" = "plucky" ]; then
                docker_codename="noble"
                log_warn "Ubuntu 26.04 (plucky) 暂无官方 Docker 仓库，临时使用 Ubuntu 24.04 (noble) 仓库"
            fi

            echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$os_id $docker_codename stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
            apt-get update
            apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
            ;;
        centos|rhel|almalinux|rocky|alinux)
            yum install -y yum-utils
            yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
            yum install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
            ;;
        *)
            log_error "不支持的发行版：$os_id，请手动安装 Docker"
            exit 1
            ;;
    esac

    # 启动 Docker 并设置开机自启
    systemctl start docker || true
    systemctl enable docker || true
}

# 确保 docker compose 可用
ensure_docker_compose() {
    if docker compose version > /dev/null 2>&1; then
        log_info "Docker Compose 插件已安装"
    else
        log_error "未检测到 docker compose 插件，请检查 Docker 安装"
        exit 1
    fi
}

# 初始化 .env 文件
init_env_file() {
    if [ -f "$ENV_FILE" ]; then
        log_info ".env 文件已存在，跳过初始化"
        return
    fi

    log_warn ".env 文件不存在，正在从 .env.example 创建..."
    cp "${SCRIPT_DIR}/.env.example" "$ENV_FILE"

    # 自动生成强密码
    local random_db_password random_secret random_admin_password
    random_db_password=$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-24)
    random_secret=$(openssl rand -hex 32)
    random_admin_password=$(openssl rand -base64 24 | tr -d '=+/' | cut -c1-16)

    sed -i "s|POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${random_db_password}|" "$ENV_FILE"
    sed -i "s|AUTH_SECRET_KEY=.*|AUTH_SECRET_KEY=${random_secret}|" "$ENV_FILE"
    sed -i "s|AUTH_ADMIN_PASSWORD=.*|AUTH_ADMIN_PASSWORD=${random_admin_password}|" "$ENV_FILE"

    log_warn "请编辑 ${ENV_FILE} 文件，确认 TUSHARE_TOKEN 等配置是否正确"
    log_warn "首次生成的管理员密码：${random_admin_password}"
    log_warn "建议立即记录该密码，然后按回车继续..."
    read -r
}

# 主部署流程
main() {
    log_info "开始部署 AD-Research 到阿里云 ECS..."
    log_info "项目目录：${PROJECT_ROOT}"

    install_base_tools
    install_docker
    ensure_docker_compose

    # 将当前用户加入 docker 组（避免每次使用 sudo）
    if [ "$EUID" -eq 0 ] && [ -n "${SUDO_USER:-}" ]; then
        usermod -aG docker "$SUDO_USER" || true
        log_warn "已将 $SUDO_USER 加入 docker 组，重新登录后生效"
    fi

    init_env_file

    cd "$SCRIPT_DIR"

    log_info "拉取基础镜像（PostgreSQL / Redis）..."
    docker compose pull postgres redis || true

    log_info "构建 AD-Research 后端镜像..."
    docker compose build --no-cache

    log_info "启动 PostgreSQL 和 Redis..."
    docker compose up -d postgres redis

    log_info "等待数据库就绪..."
    sleep 5

    log_info "执行数据库迁移..."
    docker compose run --rm backend alembic upgrade head

    log_info "初始化管理员账号..."
    docker compose run --rm backend python scripts/seed_users.py

    log_info "启动后端服务..."
    docker compose up -d backend

    log_info "等待服务启动..."
    sleep 3

    # 健康检查
    local public_ip
    public_ip=$(curl -s http://100.100.100.200/latest/meta-data/eipv4 || curl -s http://100.100.100.200/latest/meta-data/public-ipv4 || echo "YOUR_SERVER_IP")

    if curl -sf "http://localhost:8000/health" > /dev/null 2>&1; then
        echo ""
        log_info "✅ 部署成功！"
        log_info "访问地址：http://${public_ip}:8000"
        log_info "API 文档：http://${public_ip}:8000/docs"
        log_info "健康检查：http://${public_ip}:8000/health"
        echo ""
        log_info "常用命令："
        log_info "  查看日志：docker compose -f ${SCRIPT_DIR}/docker-compose.yml logs -f backend"
        log_info "  重启服务：docker compose -f ${SCRIPT_DIR}/docker-compose.yml restart"
        log_info "  停止服务：docker compose -f ${SCRIPT_DIR}/docker-compose.yml down"
    else
        log_error "服务健康检查失败，请查看日志："
        log_error "  docker compose -f ${SCRIPT_DIR}/docker-compose.yml logs backend"
        exit 1
    fi
}

main "$@"
