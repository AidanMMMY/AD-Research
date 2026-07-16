# 2026-07-17 Deploy / Health / Celery 修复跟进

> 决策日志：记录 2026-07-16 ~ 2026-07-17 连续 deploy 失败 (#255-#258) 的根因、修复过程与后续加固措施。
> 相关 runbook：[[20260712-celery-worker-runbook]]、[[20260714-deploy-update-sh-exit-5-fix]]、[[20260707-cninfo-reports-fix]]。

## 1. 事件摘要

| 项目 | 内容 |
|---|---|
| 时间 | 2026-07-16 ~ 2026-07-17 |
| 现象 | GitHub Actions deploy #255-#258 连续失败，网站一度不可访问 |
| 根因 | ① backend 仅 `expose:8000`，host 侧 `curl localhost:8000/health` 探测失败；② `/health` 数据新鲜度查询扫描 ~16M 行耗时 14s，并发探针放大后耗尽 QueuePool；③ `update.sh` 在 backend 未就绪时继续启动 nginx；④ entrypoint 脚本未 `chmod +x`；⑤ ECS `/data` 磁盘 97% 满 / build OOM |
| 恢复 | 已清理磁盘、重建镜像、重启 backend/celery-worker/nginx，`https://www.alloyresearch.net/health` 返回 200 且 `status=ok` |

## 2. 已应用的修复

### 2.1 部署流程（deploy.yml / update.sh / rollback.sh）

| 修复点 | 文件 | 说明 |
|---|---|---|
| workflow retry 判断 `outcome` 而非 `conclusion` | `.github/workflows/deploy.yml:122` | `continue-on-error` 会把 `conclusion` 重写为 `success`，必须用 `outcome` 判断真实失败，否则重试永不触发 |
| smoke check 移除 `/auth/me` | `.github/workflows/deploy.yml:151` | `/auth/me` 不存在且受保护，会 401 导致 smoke check 失败 |
| 镜像 tag 方向修正 | `deploy/aliyun-ecs/update.sh:148` | 旧逻辑会把新构建的 `${GIT_SHA}` 覆盖回旧的 `latest`；改为 `ad-research:${GIT_SHA} -> latest` |
| 回滚时镜像缺失自动 build | `scripts/rollback.sh:149-154` | 若目标版本镜像不存在，基于目标 commit 重新构建，避免 `pull_policy: never` 导致回滚失败 |
| backend build 传入 `GIT_SHA` | `deploy/aliyun-ecs/docker-compose.yml:99-102` | `/health` 能显示准确 commit |
| backend healthcheck 解析 `status=ok` | `deploy/aliyun-ecs/docker-compose.yml:109-114` | 避免 DB 未就绪时 nginx/celery-worker 提前启动 |

### 2.2 健康检查与数据库连接池

| 修复点 | 文件 | 说明 |
|---|---|---|
| `/health` 使用独立 NullPool 引擎 | `app/core/health.py:56-66` | 不再与业务请求竞争主 QueuePool；设置连接级 `statement_timeout=3000ms` |
| 简化新鲜度查询 | `app/core/health.py:163-166` | 从 per-market join 改为全局 `max(trade_date)` |
| 新增 `trade_date` 单列索引 | `alembic/versions/2026_07_17_add_instrument_daily_bar_trade_date_index.py` | 保证 `max(trade_date)` 走 Index Only Scan；保留原 `(etf_code, trade_date DESC)` 复合索引 |
| Postgres 提高 `max_connections` | `deploy/aliyun-ecs/docker-compose.yml:40` | 默认 100 太紧张，改为 200 |
| 限制 APScheduler 并发线程 | `app/core/scheduler.py:52-56` | 默认 20 线程会放大连接池占用，改为 5 |

### 2.3 Celery 改造收尾

| 修复点 | 文件 | 说明 |
|---|---|---|
| 新增日刷 Celery 任务 | `app/tasks/cninfo.py:132-164` | `refresh_cninfo_reports_daily` 在 worker 中执行 `CninfoReportsPipeline` |
| scheduler 改为提交 Celery | `app/core/scheduler.py:1009-1019` | `run_cninfo_reports_daily` 调用 `.delay()`，backend 重启不中断 |

## 3. 验证结果

- `python -m py_compile app/core/health.py app/core/scheduler.py app/tasks/cninfo.py alembic/versions/2026_07_17_add_instrument_daily_bar_trade_date_index.py` 通过
- ECS 容器状态：backend/celery-worker/nginx/postgres/redis 全部 running/healthy
- 外部 `https://www.alloyresearch.net/health`：`status=ok`、`db=ok`、`redis=ok`、`data=ok`（latest_date=2026-07-15，age_days=2）

## 4. 仍存在的风险与后续 TODO

| 优先级 | 事项 | 说明 |
|---|---|---|
| P1 | 真 secret rotate | DeepSeek/雪球/Tushare 真 key 已识别，需下一轮 sprint 执行，仓库历史里 `.env` 未抹（见 [[20260704-secret-rotate-runbook]]、[[20260705-secret-rotate-3-providers]]） |
| P1 | UI Sprint 遗留 4 项 | 见 [[20260701-p0-and-ui-sprint-results]] |
| P2 | scheduler 长会话优化 | 当前多个 scheduler 函数把 `SessionLocal()` 持有到 pipeline 结束，应把 session 生命周期控制在真正 DB 事务范围内 |
| P2 | 独立 scheduler 容器 | 避免 scheduler 与 API worker 共享连接池 |
| P3 | `cninfo_pdf.py` 冗余 `db.close()` | `try` 块内和 `finally` 块中各一次，可清理 |
| P3 | 回滚/失败日志保留多份 | 当前 `previous_head` 与 `rollback-latest.log` 只保留最新一份，不利于多次失败审计 |

## 5. 操作命令速查

```bash
# 生产环境检查所有服务
cd /opt/ad-research/deploy/aliyun-ecs
docker compose ps

# 容器内 /health
docker exec alloyresearch-backend python -c "import urllib.request,json; print(json.loads(urllib.request.urlopen('http://localhost:8000/health',timeout=5).read()))"

# 手动触发 cninfo 日刷
docker exec alloyresearch-backend python -c "from app.tasks.cninfo import refresh_cninfo_reports_daily; refresh_cninfo_reports_daily.delay()"

# 查看 celery worker 活跃任务
docker exec alloyresearch-celery-worker celery -A app.core.celery_app inspect active

# 手动回滚到某个 commit
bash scripts/rollback.sh <COMMIT_SHA>
```

## 6. 决策与回滚

- **决策**：本次修改同时涉及部署脚本、Docker 配置、健康检查、数据库索引、Celery 任务，属于跨多文件重构，已同步更新本决策日志、代码注释与 MEMORY 指针。
- **回滚方式**：若新代码导致问题，可执行 `bash scripts/rollback.sh <previous_commit_sha>`；ECS 当前已恢复，回滚目标镜像 `ad-research:0ba98c2` 仍存在。
