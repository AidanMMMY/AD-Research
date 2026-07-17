#!/usr/bin/env bash
# ============================================================
# 日志/快照文件轮换辅助脚本
#
# 用法：
#   rotate-log.sh <dir> <prefix> <ext> <latest_symlink> <keep_count>
#
# 参数：
#   dir          存储目录
#   prefix       文件名前缀（如 rollback）
#   ext          文件扩展名（如 log）
#   latest_name  指向最新文件的符号链接名称（如 rollback-latest.log）
#   keep_count   保留最近 N 份（含本次新建），建议 >= 1
#
# 行为：
#   1. 创建 <dir>/<prefix>-YYYYMMDD-HHMMSS.<ext>
#   2. 创建/更新 <dir>/<latest_name> 指向该文件
#   3. 删除旧文件，只保留最近 keep_count 份
#
# 输出：
#   新文件绝对路径（stdout）
# ============================================================

set -euo pipefail

DIR="${1:-}"
PREFIX="${2:-}"
EXT="${3:-}"
LATEST_NAME="${4:-}"
KEEP_COUNT="${5:-10}"

if [ -z "$DIR" ] || [ -z "$PREFIX" ] || [ -z "$EXT" ] || [ -z "$LATEST_NAME" ] || [ -z "$KEEP_COUNT" ]; then
    echo "Usage: $0 <dir> <prefix> <ext> <latest_name> <keep_count>" >&2
    exit 1
fi

if ! [[ "$KEEP_COUNT" =~ ^[0-9]+$ ]] || [ "$KEEP_COUNT" -lt 1 ]; then
    echo "keep_count must be a positive integer, got: $KEEP_COUNT" >&2
    exit 1
fi

if ! mkdir -p "$DIR" 2>/dev/null; then
    echo "Cannot create directory: $DIR" >&2
    exit 1
fi

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
FILENAME="${PREFIX}-${TIMESTAMP}.${EXT}"
ENTRY_PATH="${DIR}/${FILENAME}"

# 如果目录存在同名文件，使用 touch 确保 mtime 更新（保留旧内容），不覆盖
if [ -f "$ENTRY_PATH" ]; then
    touch "$ENTRY_PATH"
else
    # 创建空文件，方便调用方直接写入
    : > "$ENTRY_PATH"
fi

LATEST_PATH="${DIR}/${LATEST_NAME}"
# 迁移旧版单文件：如果 latest_name 是常规文件，先将其保留为本次时间戳的历史快照
if [ -f "$LATEST_PATH" ] && [ ! -L "$LATEST_PATH" ]; then
    mv "$LATEST_PATH" "${ENTRY_PATH}.legacy"
fi

if [ -L "$LATEST_PATH" ]; then
    rm -f "$LATEST_PATH"
fi
ln -s "$FILENAME" "$LATEST_PATH" 2>/dev/null || true

# 轮换旧文件：按 mtime 排序，保留最近 keep_count 份，删除其余
# 匹配模式同时覆盖 *.ext 和 *.ext.legacy 等历史快照
ls -t "${DIR}/${PREFIX}"-*".${EXT}"* 2>/dev/null \
    | tail -n +$((KEEP_COUNT + 1)) \
    | while IFS= read -r old_file; do
        [ -f "$old_file" ] && rm -f "$old_file"
    done

# 输出绝对路径
cd "$DIR" && echo "$(pwd)/${FILENAME}"
