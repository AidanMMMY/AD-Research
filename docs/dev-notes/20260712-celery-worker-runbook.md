# Celery Worker 运维 Runbook

> 本文档说明 A-share 指标重算、cninfo 定期报告回填等长时后台任务如何通过 Celery Worker 与 backend API 服务分离部署，并提供日常运维命令与故障排查流程。

> 最后核实更新：2026-07-21

## 1. 背景与目标

### 1.1 问题

此前，A 股个股/ETF 指标重算、cninfo 定期报告回填等耗时任务通过 `docker exec` 临时启动在 `alloyresearch-backend` 容器内部。每次 backend 镜像重新构建/部署时，容器被重建，内部所有 `docker exec` 进程全部中断，导致重算和回填任务反复从头开始。

### 1.2 方案

引入 Celery + Redis 任务队列：

- **Broker / Backend**：复用现有 Redis（`redis://redis:6379/0`）。
- **Worker 容器**：按队列拆成两个独立 service —— `celery-worker-indicator`（`-Q indicator`，并发 4）与 `celery-worker-cninfo`（`-Q celery,cninfo,industry`，并发 2），使用与 backend 同一个镜像 `ad-research:latest`，仅启动命令不同。（最初为单一 `celery-worker` service，后拆分以避免大型 cninfo 回填阻塞指标计算。）
- **队列路由**：`app/core/celery_app.py` 中 `task_routes` 把 `app.tasks.indicator.*` 路由到 `indicator` 队列，`app.tasks.cninfo.*` / `app.tasks.cninfo_pdf.*` 路由到 `cninfo` 队列，`app.tasks.sw_industry.*` 路由到 `industry` 队列，其余走默认 `celery` 队列。
- **定时触发层**：保留 `app/core/scheduler.py` 中的 APScheduler，由它将耗时执行委托给 Celery。
- **幂等性**：指标写入依赖 `etf_indicator` 表的 `ON CONFLICT (etf_code, trade_date) DO UPDATE`；cninfo 写入依赖 `cninfo_report` 表的 `ON CONFLICT (announcement_id)`，因此任务可安全重试。

### 1.3 目标

- backend 容器重启后，celery-worker 容器保持运行，队列中未消费的任务继续被处理。
- worker 容器自身重启也能由 `restart: unless-stopped` 自动恢复。
- 提供统一的手动触发脚本与运维命令，减少后续操作差异。

## 2. 服务清单

| 服务 | 容器名 | 职责 | 重启策略 |
|---|---|---|---|
| backend | `alloyresearch-backend` | FastAPI API + APScheduler 定时触发 | unless-stopped |
| celery-worker-indicator | `alloyresearch-celery-worker-indicator` | 消费 `indicator` 队列（指标计算，`-c 4`） | unless-stopped |
| celery-worker-cninfo | `alloyresearch-celery-worker-cninfo` | 消费 `celery,cninfo,industry` 队列（cninfo 回填/PDF、申万行业等，`-c 2`） | unless-stopped |
| redis | `alloyresearch-redis` | Celery broker + result backend + 应用缓存 | unless-stopped |
| postgres | `alloyresearch-postgres` | 持久化数据 | unless-stopped |

## 3. 关键文件

- `app/core/celery_app.py`：Celery 应用单例与配置（含队列路由、`visibility_timeout=43200`、`task_acks_late=True`、`worker_prefetch_multiplier=1`）。
- `app/tasks/indicator.py`：指标计算 Celery 任务（`indicator` 队列）。
- `app/tasks/cninfo.py`：cninfo 全量回填 `backfill_cninfo_reports` 与每日刷新 `refresh_cninfo_reports_daily` Celery 任务（`cninfo` 队列）。
- `app/tasks/cninfo_pdf.py`、`app/tasks/sw_industry.py`：cninfo PDF 下载（`cninfo` 队列）与申万行业指数刷新（`industry` 队列）任务。
- `app/core/scheduler.py`：APScheduler 定时将任务提交到 Celery。
- `scripts/trigger_indicator_calc.py`：手动触发指标计算。
- `scripts/trigger_cninfo_backfill.py`：手动触发 cninfo 回填（自动分片）。
- `docker-compose.yml`：本地开发环境配置。
- `deploy/aliyun-ecs/docker-compose.yml`：生产环境配置。
- `deploy/aliyun-ecs/update.sh`：生产环境更新脚本（已包含 celery-worker 重启）。

## 4. 常用命令

### 4.1 查看 worker 状态

`celery inspect` 通过 broker 查询整个集群，在任意一个 worker 容器里执行即可看到所有 worker：

```bash
# 查看当前活跃任务
docker exec alloyresearch-celery-worker-indicator celery -A app.core.celery_app inspect active

# 查看已注册的 worker 列表
docker exec alloyresearch-celery-worker-indicator celery -A app.core.celery_app inspect registered

# 查看 worker 统计信息
docker exec alloyresearch-celery-worker-indicator celery -A app.core.celery_app inspect stats
```

### 4.2 查看队列堆积

```bash
# 查看已被 worker 预留但未执行完的任务
docker exec alloyresearch-celery-worker-indicator celery -A app.core.celery_app inspect reserved

# 直接查看 Redis 队列长度（需进入 backend 或任一 worker 容器）；
# 注意任务按类型路由到不同队列，只查 celery 会漏掉 indicator/cninfo/industry
docker exec alloyresearch-celery-worker-indicator redis-cli -h redis -n 0 llen indicator
docker exec alloyresearch-celery-worker-cninfo redis-cli -h redis -n 0 llen cninfo
docker exec alloyresearch-celery-worker-cninfo redis-cli -h redis -n 0 llen celery
docker exec alloyresearch-celery-worker-cninfo redis-cli -h redis -n 0 llen industry
```

### 4.3 查看日志

```bash
# 实时跟踪两个 worker 的日志
docker logs -f --tail 100 alloyresearch-celery-worker-indicator
docker logs -f --tail 100 alloyresearch-celery-worker-cninfo

# 查看后端 scheduler 提交日志
docker logs -f --tail 100 alloyresearch-backend
```

### 4.4 手动触发任务

#### 指标计算

```bash
# 进入 backend 容器后执行
python3 scripts/trigger_indicator_calc.py

# 重算全历史 A 股
python3 scripts/trigger_indicator_calc.py --full-history

# 指定日期
python3 scripts/trigger_indicator_calc.py --target-date 2026-07-10

# 美股
python3 scripts/trigger_indicator_calc.py --market US

# 加密货币
python3 scripts/trigger_indicator_calc.py --market CRYPTO
```

#### cninfo 定期报告回填

```bash
# 进入 backend 容器后执行
python3 scripts/trigger_cninfo_backfill.py

# 调整分片大小（每任务股票数）
python3 scripts/trigger_cninfo_backfill.py --shard-size 200

# 只回填最近 1 年
python3 scripts/trigger_cninfo_backfill.py --years 1

# 只拉年报
python3 scripts/trigger_cninfo_backfill.py --type annual

# 试运行，只打印分片不提交
python3 scripts/trigger_cninfo_backfill.py --dry-run

# 手动触发每日刷新任务（B-tier 标的池，最近 7 天窗口）
python3 -c "from app.tasks.cninfo import refresh_cninfo_reports_daily; refresh_cninfo_reports_daily.delay()"
```

### 4.5 重启 worker

```bash
# 开发环境
docker compose restart celery-worker-indicator celery-worker-cninfo

# 生产环境
cd /opt/ad-research/deploy/aliyun-ecs
docker compose restart celery-worker-indicator celery-worker-cninfo
```

### 4.6 清空/撤销任务

> ⚠️ 危险操作，仅在明确需要时使用。`purge` 默认只清 `celery` 队列，
> 指标/cninfo 任务在 `indicator` / `cninfo` 队列里，需用 `-Q` 指定。

```bash
# 清空指定队列中所有未消费任务
docker exec alloyresearch-celery-worker-indicator celery -A app.core.celery_app purge -f -Q indicator
docker exec alloyresearch-celery-worker-cninfo celery -A app.core.celery_app purge -f -Q celery,cninfo,industry

# 撤销指定任务（需 task_id）
docker exec alloyresearch-celery-worker-indicator celery -A app.core.celery_app revoke <task_id>

# 撤销并终止正在执行的任务
docker exec alloyresearch-celery-worker-indicator celery -A app.core.celery_app revoke <task_id> --terminate
```

## 5. 故障排查

### 5.1 worker 不消费任务

1. **检查容器是否在运行**
   ```bash
   docker ps --filter name=celery-worker
   ```

2. **检查 worker 日志是否有启动错误**
   ```bash
   docker logs --tail 100 alloyresearch-celery-worker-indicator
   docker logs --tail 100 alloyresearch-celery-worker-cninfo
   ```
   常见问题：
   - Redis 连接失败：检查 `REDIS_URL` 是否正确，redis 容器是否健康。
   - 任务模块导入失败：检查镜像是否包含最新代码。

3. **检查队列是否有任务**（按路由分别查，见 §4.2）
   ```bash
   docker exec alloyresearch-celery-worker-indicator celery -A app.core.celery_app inspect active
   docker exec alloyresearch-celery-worker-indicator redis-cli -h redis -n 0 llen indicator
   ```

4. **手动提交一个测试任务**
   ```bash
   docker exec alloyresearch-backend python3 scripts/trigger_indicator_calc.py --target-date 2026-07-10
   docker logs -f alloyresearch-celery-worker-indicator
   ```

### 5.2 任务重复执行

- Celery 配置 `task_acks_late=True` + `worker_prefetch_multiplier=1`，长时任务在 worker 异常退出后会重新投递；Redis broker 的 `visibility_timeout` 已调大到 43200s（12h），覆盖指标任务 4-8 小时的最长运行时间，避免运行中被重复投递。
- 指标和 cninfo 任务均基于数据库 UPSERT 实现幂等，重复执行不会导致数据重复，只会浪费资源。
- 如果重复执行频繁，检查 worker 是否因为 OOM 或健康检查失败被频繁重启。

### 5.3 backend 部署后任务丢失

- backend 容器重启不会清空 Redis 队列，已提交但未执行的任务仍保留。
- 两个 celery-worker 容器在 `update.sh` 中会与 backend 一起重启，重启后会继续消费队列。
- 如果 Redis 容器也重启，未持久化的内存数据可能丢失；生产 Redis 已开启 AOF 持久化（`appendonly yes`），风险较低。

### 5.4 worker 日志中出现 `Database locked` 或连接池耗尽

- worker 并发数已限制：indicator worker `-c 4`、cninfo worker `-c 2`，避免同时运行过多长任务拖垮数据库。
- 如果仍出现，可进一步降低并发：修改 `deploy/aliyun-ecs/docker-compose.yml` 中对应 worker 的 command（如 `-c 1`）。

### 5.5 定时任务没有提交到 Celery

- 检查 backend 环境变量 `ENABLE_SCHEDULER=true`。
- 检查 backend 日志中 `[Scheduler] Started` 字样。
- 检查 `app/core/scheduler.py` 中对应任务是否调用 `.delay()`。

## 6. 部署 Checklist

1. 本地修改代码后，运行 `poetry install` 确保 `celery` 已安装。
2. 本地启动 `docker compose up -d backend celery-worker-indicator celery-worker-cninfo redis postgres`，验证 worker 能正常注册并消费任务。
3. 提交代码前运行 `cd web && npm run build`，确保前端 dist 最新（后端改动虽不影响前端，但保持 dist 一致）。
4. 推送到 main 分支。
5. 在生产环境运行 `./update.sh`（或 `FORCE=1 ./update.sh` 强制重编）。
6. 检查两个 worker 容器已启动：
   ```bash
   docker ps --filter name=celery-worker
   ```
7. 手动触发一个测试任务，确认 worker 日志出现消费与完成记录。
8. 检查 backend 的 APScheduler 是否正常将定时任务提交到 Celery。

## 7. 回滚

如果 Celery 方案出现不可预期的问题：

1. 停止两个 celery-worker 容器：
   ```bash
   cd /opt/ad-research/deploy/aliyun-ecs
   docker compose stop celery-worker-indicator celery-worker-cninfo
   ```
2. 恢复使用直接脚本执行（在 backend 容器内）：
   ```bash
   docker exec -it alloyresearch-backend python3 scripts/backfill_cninfo_reports.py --offset 0 --limit 500
   docker exec -it alloyresearch-backend python3 -c "from app.data.indicators.calculator import batch_calculate_indicators; from app.core.database import SessionLocal; db=SessionLocal(); batch_calculate_indicators(db)"
   ```
3. 注意：回滚后将重新面临 backend 重启导致任务中断的问题，仅作为临时兜底。

## 8. 扩展建议

- 后续可将 APScheduler 中的其他定时任务逐步迁移到 Celery，统一后台任务管理。
- 若任务量增长，可水平扩展 worker：`docker compose up -d --scale celery-worker-indicator=3`（需确保数据库连接池足够；postgres 已调到 `max_connections=200`）。
- 如需可视化监控，可考虑引入 Flower，但本期为保持简单暂不使用。

## 9. 相关文档

- [[定时任务恢复操作指南]]：服务端定时任务中断/数据落后时的恢复流程。
- [[数据源已知问题备忘]]：A 股 ETF 数据源异常及处理决策。
- [[美股分类修复与部署约束]]：Function-Optimization 会话中美股 ETF/个股分类进展与部署注意。
