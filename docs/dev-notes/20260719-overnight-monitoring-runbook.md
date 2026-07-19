# Overnight Worker 监控告警 Runbook

**日期**：2026-07-19
**触发**：所有 news/social/IR 抓取源 7-11 后再没刷新过；overnight v2
的报告也没自动跑过。需要可观测性 + 自动告警。
**作者**：总管 Agent

## 背景

- `orchestrate_v2` 每小时 :47 跑 8 个 source (quick + logged_in)；
  **目前没有 monitor**，抓取挂了我们只能看 docker logs 后知后觉。
- `overnight_research_v2` 是单次任务（手动 kick），不靠 cron。
  SIGTERM 修好后（commit `b010311`）能正常 wind-down 出报告，但
  缺勤告警。
- `agent/scripts/status_report.py` 已经能渲染每个 source 的
  `fetched_at / items / login_state` 表，但**无 staleness 计算，
  无退出码**。

## 修复

### 1. `status_report.py` 加 staleness + 退出码

- **新阈值** (`THRESHOLD_HOURS`):
  - `quick`: 6h warn / 12h critical
  - `logged_in`: 24h warn / 48h critical
  - `overnight`: 36h warn / 60h critical
- **`summarize()`**: 输出多保留 `_fetched_iso` 给 staleness 计算用。
- **`read_source()`**: 当 payload 是 list（无顶层 fetched_at）时，
  用文件 mtime 兜底，避免某些 source 永远 stale=missing。
- **`read_overnight_v2()`** 新函数：扫 `/data/ad-research/overnight_*_v2/`
  目录，mtime 最新的取 `overnight_research_v2.db` 的修改时间作为
  freshness 信号。items 列显示 db 大小（KB）作为 proxy。
- **`annotate_staleness()`**: 给每行打 level (`ok/warn/critical/missing`)
  + hours_since。
- **退出码**:
  - 0 = all ok
  - 1 = 有 warn 但无 critical
  - 2 = 有 critical 或 missing
  - `--no-exit-code` 强制 0，方便 cron + 报告展示

### 2. `setup_cron.sh` 加 status_report 调度

- 新 cron tag: `ad-research-status-report`
- 每整点 :15（错开 orchestrate :47）
- 写 `/root/ad-research/logs/cron-status-report.log`
- 使用 `--no-exit-code` 避免 cron 把告警当任务失败发邮件噪声
- `do_install` / `do_uninstall` 同步处理

### 3. 验证（2026-07-19 10:24 UTC 实测）

| source | category | staleness | last fetched | hours |
|---|---|---|---|---|
| eastmoney_news | quick | 🔴 critical | (file mtime 7-11) | 191.6h |
| gov_china | quick | 🔴 critical | 2026-07-11 10:50 UTC | 191.6h |
| fed_intl | quick | 🔴 critical | 2026-07-11 10:51 UTC | 191.5h |
| stocktwits | quick | 🔴 critical | 2026-07-11 10:51 UTC | 191.5h |
| cls | quick | 🔴 critical | 2026-07-11 10:51 UTC | 191.5h |
| xueqiu_playwright | logged_in | 🔴 critical | 2026-07-11 10:52 UTC | 191.5h |
| x | logged_in | 🔴 critical | 2026-07-11 10:53 UTC | 191.5h |
| reddit_curl_cffi | logged_in | 🔴 critical | (file mtime 7-11) | 191.5h |
| overnight_v2 | overnight | ✅ ok | 2026-07-19 04:19 UTC | 6.1h |

**OVERALL: critical (exit 2)** — 8 个 source 全部 7-11 之后没刷，
**确认 orchestrate_v2 自 7-11 起没跑过**（与 `cron-orchestrate.log`
应一并检查）。

## 部署步骤

```bash
# 1. push 后 ECS 上拉最新代码
cd /opt/ad-research/agent    # 或 /root/ad-research/agent，看实际路径
git pull

# 2. 装新的 status_report cron（保留现有 orchestrate）
bash scripts/setup_cron.sh install

# 3. 验证：手动跑一次
python3 scripts/status_report.py --no-exit-code
echo "exit=$?"  # 期望 0（用了 --no-exit-code）

# 4. 不加 --no-exit-code 看真实退出码
python3 scripts/status_report.py >/dev/null
echo "exit=$?"  # 期望 2（critical）

# 5. 看 cron 日志
tail -f /root/ad-research/logs/cron-status-report.log
```

## 后续

1. **orchestrate_v2 7-11 后没跑过** — 单独排查（与本 runbook 无关）
   - `tail /root/ad-research/logs/cron-orchestrate.log`
   - `systemctl status cron` / `crontab -l`
   - 可能 docker container 挂 / ad-research 仓库 dirty 触发
     deploy-tripwire（见 20260719-deploy-tripwires.md）
2. **未来接入 Pushgateway / Slack**：
   - status_report.py 已支持 `--json`，cron 里再加一步
     `python3 -c "import json,sys,urllib.request; ..."` 即可
   - 推荐先接 Slack `#ad-research-ops` 频道
3. **回退**：`bash scripts/setup_cron.sh uninstall` 一次性清两条 cron

## 关联

- 监控脚本：`agent/scripts/status_report.py`
- 调度脚本：`agent/scripts/setup_cron.sh`
- 数据根：`/data/ad-research/`（与 `/opt/ad-research/` 软链）
- 抓取源：`agent/scripts/orchestrate_v2.py` (`WORKERS`)
- overnight 任务：`agent/workers/overnight_research_v2.py`