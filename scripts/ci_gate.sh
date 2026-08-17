#!/usr/bin/env bash
# ci_gate.sh <owner/repo> <sha> <github_token>
#
# Deploy 前置 CI 门禁（2026-08-18 重写，替代 deploy.yml 里 YAML 语法破损的
# 内联版本——Codex 8/6 加入的多行 python3 -c 未缩进导致整个 deploy.yml
# 无法解析，8/6 起所有 push 部署全部 workflow-level failure，8/18 才发现）。
#
# 语义：
#   - 该 SHA 除 deploy 自身外没有任何 check run（docs-only 推送）→ 放行
#   - 任一 check run conclusion 为 failure/cancelled/timed_out 等 → 中止部署
#   - 全部 completed 且无失败 → 放行
#   - 其余（pending/in_progress/queued）→ 等待，15 分钟超时中止
#
# 注意：必须用 /check-runs 端点——GitHub Actions 产生的是 check run，
# /status（combined status）端点只看老式 commit status，永远为空。
set -euo pipefail

REPO="$1"
SHA="$2"
TOKEN="$3"
SELF_NAME="${4:-deploy}"   # 排除 deploy 工作流自身的 check run

for i in $(seq 1 90); do
  BODY="$(curl -sS -H "Authorization: Bearer ${TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${REPO}/commits/${SHA}/check-runs?per_page=100" || echo '{}')"
  STATE="$(printf '%s' "${BODY}" | python3 \
    "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/ci_gate_parse.py" "${SELF_NAME}")"
  echo "[ci_gate] attempt=${i}/90 state=${STATE}"
  case "${STATE}" in
    success) echo "[ci_gate] CI 全绿（或无 check），放行部署"; exit 0 ;;
    failure) echo "::error::CI 存在失败 check run，中止部署以避免坏代码上线"; exit 1 ;;
    *) sleep 10 ;;
  esac
done
echo "::error::[ci_gate] 等待 CI 超时（15 分钟），为安全起见中止部署"
exit 1
