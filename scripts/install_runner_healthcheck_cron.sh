#!/bin/bash
# 2026-07-24: 安装 runner_healthcheck.sh cron — 每 5 分钟跑一次。
# 解决 Deploy cascade failure（runner host 在 step 6 完成后 ~20s 失联）。
#
# 用法：
#   sudo bash /opt/ad-research/scripts/install_runner_healthcheck_cron.sh
#
# 副作用：
#   - 写入 /etc/cron.d/ad-research-runner-health（root 调度）
#   - 不动其他 cron
set -euo pipefail

SCRIPT_PATH="/opt/ad-research/scripts/runner_healthcheck.sh"
LOG_FILE="/var/log/runner-health.log"
CRON_FILE="/etc/cron.d/ad-research-runner-health"

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "[FATAL] $SCRIPT_PATH 不存在 — deploy 还没把 runner_healthcheck.sh 推到 runner host"
  exit 1
fi

if [[ ! -x "$SCRIPT_PATH" ]]; then
  echo "[INFO] $SCRIPT_PATH 不可执行，加 +x"
  chmod +x "$SCRIPT_PATH"
fi

cat > "$CRON_FILE" <<EOF
# 2026-07-24: self-hosted runner host 自愈 cron
# Deploy cascade failure 时 5 min 间隔自愈磁盘 / daemon / stale lock。
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

*/5 * * * * root bash ${SCRIPT_PATH} >> ${LOG_FILE} 2>&1
EOF
chmod 644 "$CRON_FILE"

# logrotate-friendly: 限制单文件大小（如果不希望无限增长）
# 不做复杂 logrotate，5min 频率下 7 天约 2016 行，~100KB
echo "[OK] 安装 cron: $CRON_FILE"
echo "[OK] 日志: $LOG_FILE (每 5min 一行，7 天约 100KB)"
echo ""
echo "下次 deploy 跑完后 (scripts/runner_healthcheck.sh 已落地)，"
echo "本 cron 立即生效，无需重启。"