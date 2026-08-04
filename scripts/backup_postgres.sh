#!/usr/bin/env bash
# ============================================================
# PostgreSQL 每日备份脚本
# 用法：./scripts/backup_postgres.sh
#
# 环境变量：
#   BACKUP_DIR        备份目录（默认 /data/backups/postgres）
#   RETENTION_DAYS    保留天数（默认 7）
#   POSTGRES_DB       数据库名（默认 ad_research）
#   POSTGRES_USER     用户名（默认 etf）
#   POSTGRES_HOST     主机（默认 localhost）
#   POSTGRES_PORT     端口（默认 5432）
#   COMPOSE_FILE      docker-compose 文件路径（可选，优先用容器内 pg_dump）
#
# 行为：
#   1. 使用 pg_dump 导出指定数据库
#   2. gzip 压缩并按时间命名
#   3. 删除超过 RETENTION_DAYS 的旧备份
#   4. 输出结果与备份路径
# ============================================================

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/data/backups/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
POSTGRES_DB="${POSTGRES_DB:-ad_research}"
POSTGRES_USER="${POSTGRES_USER:-etf}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
COMPOSE_FILE="${COMPOSE_FILE:-}"
BACKEND_CONTAINER="alloyresearch-backend"

log_info()  { echo "[INFO]  $1"; }
log_warn()  { echo "[WARN]  $1"; }
log_error() { echo "[ERROR] $1"; }

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/${POSTGRES_DB}_${TIMESTAMP}.sql.gz"

log_info "开始备份 ${POSTGRES_DB} → ${BACKUP_FILE}"

# 优先通过 backend 容器内的 pg_dump 执行，确保版本一致。
# 2026-08-04 事故修复（两处）：
#   a) 探针从「完整跑一次 pg_dump > /dev/null」改为 `pg_dump --version`
#      —— 旧探针每凌晨白跑 1-2 次全库导出（数分钟/3.3G IO），且在容器
#      重启窗口内探针失败会直接跌进本地 pg_dump 分支。
#   b) 产物加 MIN_BACKUP_BYTES 底线校验：pipefail 下 pg_dump 失败只留
#      20B 空 gzip，旧 `-s` 判据把它当成功；且失败残留文件必须删除，
#      否则占用 retention 槽位让人误以为当天有备份。
MIN_BACKUP_BYTES="${MIN_BACKUP_BYTES:-104857600}"  # 100MB；当前全量 ~3.2G

dump_ok=1
if [ -n "$COMPOSE_FILE" ] && [ -f "$COMPOSE_FILE" ]; then
    docker compose -f "$COMPOSE_FILE" exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip > "$BACKUP_FILE" || dump_ok=0
elif docker exec "$BACKEND_CONTAINER" pg_dump --version >/dev/null 2>&1; then
    docker exec "$BACKEND_CONTAINER" pg_dump -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip > "$BACKUP_FILE" || dump_ok=0
elif docker exec alloyresearch-postgres pg_dump --version >/dev/null 2>&1; then
    docker exec alloyresearch-postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip > "$BACKUP_FILE" || dump_ok=0
elif command -v pg_dump >/dev/null 2>&1; then
    log_warn "容器内 pg_dump 均不可用，回退本地 pg_dump"
    pg_dump -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip > "$BACKUP_FILE" || dump_ok=0
else
    log_error "所有 pg_dump 通道均不可用（backend/postgres 容器无 pg_dump，本地未安装）"
    dump_ok=0
fi

ACTUAL_BYTES=$(stat -c %s "$BACKUP_FILE" 2>/dev/null || echo 0)
if [ "$dump_ok" -eq 1 ] && [ "$ACTUAL_BYTES" -ge "$MIN_BACKUP_BYTES" ]; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log_info "备份完成: ${BACKUP_FILE} (${SIZE})"
else
    log_error "备份失败（导出中断或大小 ${ACTUAL_BYTES}B < 底线 ${MIN_BACKUP_BYTES}B）— 已删除残缺文件"
    rm -f "$BACKUP_FILE"
    exit 1
fi

# 清理旧备份
DELETED=$(find "$BACKUP_DIR" -maxdepth 1 -type f -name "${POSTGRES_DB}_*.sql.gz" -mtime "+${RETENTION_DAYS}" -print | wc -l)
if [ "$DELETED" -gt 0 ]; then
    find "$BACKUP_DIR" -maxdepth 1 -type f -name "${POSTGRES_DB}_*.sql.gz" -mtime "+${RETENTION_DAYS}" -delete
    log_info "已删除 ${DELETED} 个超过 ${RETENTION_DAYS} 天的旧备份"
else
    log_info "没有超过 ${RETENTION_DAYS} 天的旧备份需要清理"
fi

log_info "当前备份列表:"
ls -lh "${BACKUP_DIR}"/*.sql.gz 2>/dev/null || true
