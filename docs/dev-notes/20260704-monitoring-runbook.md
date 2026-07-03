# ETF Research Platform — 监控 / 报警 Runbook

> 本文档为「监控 + 报警 runbook」，用于在缺少正式 APM / Prometheus / 钉钉
> 通道的情况下，给出可立即执行的本地探测命令与指标汇总方法。
> 与 `20260627-scheduled-task-recovery-guide.md` 互补：
> 那篇是「数据已经落后了怎么办」；本篇是「在数据落后之前怎么发现」。

最后更新：2026-07-04

---

## 〇、当前现状（无外接报警通道）

| 项目                 | 状态                                       |
|----------------------|--------------------------------------------|
| 钉钉 / 飞书 / Slack webhook | 未接入                                  |
| Prometheus / Grafana | 未部署                                     |
| Sentry / OpenTelemetry | 未接入                                  |
| 主机 cron            | 假设已挂载（本 runbook 不强制）            |
| docker-compose 日志  | JSON file driver，backend 100m × 5 / 其余 50m × 3 |

> **建议**：先按本 runbook 用本地 cron 巡检，把数据落到 `/var/log/ad-research/`，
> 再用 Prometheus 抓 `node_exporter` + `cadvisor` 输出到 Grafana；报警通道
> 接入钉钉 webhook（参见 §六）。

---

## 一、必须监控项（按优先级排序）

### 1.1 `/health` 状态 + 响应耗时

```bash
# 必须 200 且耗时 < 1.5s
time curl -fsS -o /dev/null -w 'http=%{http_code} time=%{time_total}s\n' \
  http://localhost:8000/api/v1/health
```

判定阈值：

| 指标           | 阈值                | 触发动作                                            |
|----------------|---------------------|-----------------------------------------------------|
| http_code      | == 200              | 一切非 200 视为异常                                 |
| time_total     | < 1.5s              | 持续 > 3s 触发 backend 日志查 OOM / DB 慢查询      |
| 连接拒绝       | 任何                 | 立即 `docker ps \| grep alloyresearch-backend`      |

---

### 1.2 后端进程活跃

```bash
docker ps --filter "name=alloyresearch-backend" \
          --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

期望输出至少包含一行 `alloyresearch-backend ... Up ... hours`。

若返回空：

```bash
docker ps -a --filter "name=alloyresearch-backend" \
           --format 'table {{.Names}}\t{{.Status}}\t{{.ExitCode}}'
# 看 ExitCode，非 0 时按 §四 救援流程处理。
```

---

### 1.3 Postgres 占用

```bash
docker exec alloyresearch-postgres \
  psql -U etf -d ad_research -c "SELECT pg_size_pretty(pg_database_size('ad_research'));"
```

阈值建议：

- < 30 GB：正常
- 30–80 GB：开始关注；查 `pg_stat_user_tables.n_live_tup`
- > 80 GB：考虑 vacuum full / 冷数据归档

附加诊断（看活动连接数）：

```bash
docker exec alloyresearch-postgres psql -U etf -d ad_research -c \
  "SELECT count(*) AS active, count(*) FILTER (WHERE state='active') AS running
     FROM pg_stat_activity;"
```

---

### 1.4 alembic head 是否对齐

```bash
bash scripts/migrate_database.sh --check-only
# 若该 flag 未实现，使用以下等价命令：
docker exec alloyresearch-backend alembic current
docker exec alloyresearch-backend alembic heads
# 两边的 revision 必须一致；不一致表示有未应用的迁移。
```

补充：在 backend 容器里看最近一次迁移时间。

```bash
docker exec alloyresearch-postgres psql -U etf -d ad_research -c \
  "SELECT version_num, date_modified FROM alembic_version JOIN
     (SELECT now() AS now) t ON true;"
```

---

### 1.5 调度任务偏移（DRIFT）

```bash
bash scripts/check_scheduler_drift.sh 5
```

期望：所有 job 出现 `OK` 状态；`WARN` 出现但 exit code = 0 时由调用方决策。

退出码语义：

| Exit | 含义                                                  |
|------|-------------------------------------------------------|
| 0    | OK 或带 WARN（由 cron / 调用方决定是否告警）          |
| 10   | 探测本身失败（容器未起 / scheduler 未 running）        |

---

## 二、推荐的巡检脚本（一次性收集所有指标）

```bash
#!/usr/bin/env bash
# 在主机 cron 中每 5 分钟跑一次：*/5 * * * * /opt/ad-research/cron_healthcheck.sh
set -u

BASE_URL="${BASE_URL:-http://localhost:8000}"
COMPOSE="${COMPOSE:-./docker-compose.yml}"
TS="$(date -Iseconds)"
OUT="/var/log/ad-research/health-${TS}.json"
mkdir -p "$(dirname "${OUT}")"

echo "{ \"ts\": \"${TS}\"" > "${OUT}"

# 1.1 /health
H="$(curl -fsS -o /dev/null -w '%{http_code}|%{time_total}' \
      "${BASE_URL}/api/v1/health" 2>/dev/null || echo '000|0')"
echo ", \"health\": \"${H}\"" >> "${OUT}"

# 1.2 backend container state
B="$(docker ps -a --filter 'name=alloyresearch-backend' \
     --format '{{.Status}}|{{.ExitCode}}' 2>/dev/null || echo 'unknown|-1')"
echo ", \"backend\": \"${B}\"" >> "${OUT}"

# 1.3 pg size
PG="$(docker exec alloyresearch-postgres \
       psql -U etf -d ad_research -tA -c \
       "SELECT pg_size_pretty(pg_database_size('ad_research'));" \
       2>/dev/null || echo 'unknown')"
echo ", \"pg_size\": \"${PG}\"" >> "${OUT}"

# 1.4 alembic
A="$(docker exec alloyresearch-backend alembic current 2>/dev/null | head -1 || echo 'unknown')"
echo ", \"alembic_current\": \"${A}\"" >> "${OUT}"

# 1.5 scheduler drift (just exit code + last 6 lines)
D_LOG="$(bash scripts/check_scheduler_drift.sh 5 2>&1 || true)"
D_CODE="$?"
echo ", \"drift_code\": ${D_CODE}" >> "${OUT}"
D_TAIL="$(printf '%s' "${D_LOG}" | tail -n 6 | python -c \
  'import sys,json;print(json.dumps(sys.stdin.read()))')"
echo ", \"drift_tail\": ${D_TAIL}}" >> "${OUT}"
```

输出格式是「单行 JSON」，便于后续接入 Loki / Filebeat 之类。

---

## 三、常见故障判定

### 3.1 `db=down`

症状：

- `/health` 返回 500 或 `time_total` 持续 > 5s
- `pg_isready` / `psql` 失败
- backend 日志中频繁出现 `OperationalError` / `could not translate host name "postgres"`

救援流程：

```bash
# 1. 看 postgres 健康
docker ps --filter name=alloyresearch-postgres --format '{{.Status}}'
docker logs --since 10m alloyresearch-postgres | tail -50

# 2. 重启 backend（让依赖重新解析）
docker compose -f docker-compose.yml restart backend
sleep 30

# 3. 再次 health
curl -fsS http://localhost:8000/api/v1/health

# 4. 若仍失败，回看 backend 日志
docker logs --since 5m alloyresearch-backend | tail -100
```

### 3.2 `scheduler=stopped`

症状：

- `scripts/check_scheduler_drift.sh` 退出码 10
- `is_scheduler_running()` 返回 False
- 心跳 redis key `ad_research:scheduler:heartbeat` 不存在

```bash
docker exec alloyresearch-backend redis-cli -h redis GET ad_research:scheduler:heartbeat
# 返回 (nil) 即心跳丢失

# 救援：重启 backend 即可，scheduler 在 main.py 启动时由 init_scheduler() 装配
docker compose -f docker-compose.yml restart backend
```

### 3.3 日志被 GC

症状：`docker logs` 只能拿到最近几分钟的内容（受 JSON file driver 的 max-size 限制）。

参考 `scripts/archive_logs.sh` 的部署方式：把脚本挂到主机 cron（每天 03:30），把
`/var/log/ad-research/*.log` 滚动归档。

---

## 四、推荐的部署拓扑

```text
[主机 cron] -- 5min --> /var/log/ad-research/health-*.json
                         │
                         ├── filebeat / promtail --> Loki（日志检索）
                         │
                         └── node_exporter + cadvisor --> Prometheus --> Grafana
                                                                  │
                                                                  └─ alertmanager --> 钉钉 webhook
```

最低成本的告警通道（无 Grafana）：

```bash
# 在 healthcheck 脚本末尾追加：
if [[ "${H%%|*}" != "200" || "${B%%|*}" != "Up" ]]; then
  curl -X POST "${DINGTALK_WEBHOOK:-https://oapi.dingtalk.com/robot/send?access_token=__PLACEHOLDER__}" \
       -H 'Content-Type: application/json' \
       -d "{\"msgtype\":\"text\",\"text\":{\"content\":\"ad-research alert: ${TS} health=${H} backend=${B}\"}}"
fi
```

---

## 五、相关脚本清单

| 脚本                                                | 用途                              |
|-----------------------------------------------------|-----------------------------------|
| `scripts/archive_logs.sh`                           | 日志滚动归档 + 旧日志压缩 / 清理 |
| `scripts/check_scheduler_drift.sh`                  | 调度任务 next_run_time 偏移巡检   |
| `scripts/check_scheduler.py`                        | HTTP 端点版的 scheduler 状态查看  |
| `scripts/data_completeness_check.py`                | 数据完整性（与定时任务恢复指南配套）|
| `scripts/db_consistency_check.py`                   | DB 结构与 ORM 对齐检查            |

---

## 六、后续 TODO（不阻塞本 runbook）

1. 接入 `prometheus_fastapi_instrumentator` 到 backend，开放 `/metrics`。
2. 部署 `node_exporter` + `cadvisor` + `postgres_exporter`。
3. 钉钉 webhook 通道（已在 §四 给出示例）。
4. 把 `health-*.json` 落盘路径改到 Loki 卷。