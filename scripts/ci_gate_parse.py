"""ci_gate 的 check-runs 响应解析器（从 ci_gate.sh 拆出，避免 heredoc 与管道
stdin 冲突：``python3 - <<EOF`` 会让程序与管道数据争用同一个 stdin）。

用法：printf '%s' "$BODY" | python3 ci_gate_parse.py <self_job_name>
输出（stdout 单行）：
  success —— 除 deploy 自身外无 check run（docs-only 推送放行），或全部 completed 且无失败
  failure —— 任一 check run conclusion 为失败类
  pending —— 还有 check run 在跑
  retry   —— 响应无法解析（API 抖动），调用方继续轮询
"""

import json
import sys

self_name = sys.argv[1].lower() if len(sys.argv) > 1 else "deploy"
try:
    d = json.load(sys.stdin)
    runs = [
        r
        for r in d.get("check_runs", [])
        if self_name not in r.get("name", "").lower()
    ]
except Exception:
    print("retry")
    sys.exit(0)

BAD = ("failure", "cancelled", "timed_out", "action_required", "startup_failure")
if not runs:
    print("success")
elif any(r.get("conclusion") in BAD for r in runs):
    print("failure")
elif all(r.get("status") == "completed" for r in runs):
    print("success")
else:
    print("pending")
