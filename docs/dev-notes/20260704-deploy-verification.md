# 20260704 — 部署后健康校验手册

> 目标:把"升级后一定健康"做成流水线自动断言,而不是肉眼看一眼就当成功。

> 最后核实更新：2026-07-21

## 1. 标准发布流水线

实际流水线由 `.github/workflows/deploy.yml` 定义（self-hosted runner 跑在 ECS 上），
顺序如下，**任一步骤非零退出即终止**，失败时自动回滚到部署前 HEAD：

```
git push  →  sync code (reset --hard)  →  baseline /health  →  update.sh (失败自动重试 1 次)
          →  backend smoke check  →  check_migrations.sh  →  health probe  →  (失败) rollback.sh
```

| 步骤 | 入口 | 作用 | 失败信号 |
| ---- | ---- | ---- | -------- |
| ① git push | 本地 `git push origin main` | 把 commit 推到 GitHub | 推送拒绝 / pre-commit hook 红 |
| ② sync code | deploy.yml step 2 | 备份 previous_head → `git reset --hard origin/main`；工作树脏直接 exit 1 | 工作树有未提交变更 |
| ③ baseline check | deploy.yml step 2.5 | 部署前记录一次 `/health` 状态码 | 仅记录，不拦截 |
| ④ `update.sh` | `deploy/aliyun-ecs/update.sh` | 构建镜像 → 停旧容器/清 orphan → 重建 backend+celery → 等 `/health`（150×2s=300s）→ nginx → 迁移只读校验 | 300s 内 `/health` body status 不是 `ok`；alembic current ≠ head |
| ⑤ smoke check | deploy.yml step 3.5 | 容器内 `import app.main` + `alembic current` + 探测 `/health`、`/openapi.json` | 导入失败 / 探针非 200 / status≠ok |
| ⑥ `check_migrations.sh` | `scripts/check_migrations.sh` | 只读比对 alembic current / head（exit 0/10/20） | current ≠ head 或模型导入失败 |
| ⑦ health probe | deploy.yml step 5 | 容器内 30×2s 轮询 `/health` 要求 `status=ok` | 60s 不通过 → 触发回滚 |
| ⑧ rollback | `scripts/rollback.sh`（failure 时） | 回滚到 previous_head 并复检 `/health` | 回滚失败需人工介入 |

辅助脚本（不挂在 deploy.yml 里，可手动用）：

- `scripts/auto_migrate.sh [compose-file]` — 幂等迁移执行器，current ≠ head 时才 `upgrade head`
- `scripts/post_deploy_check.sh <url>` — 从外部对 `/health`、`/docs` 等做冒烟断言

## 2. 健康检查标准

`GET /health` **始终返回 HTTP 200**（即使依赖故障），真实结论在 body 里——
这是 2026-07 起的行为（ops P1-13），调用方必须解析 body 的 `status` 字段，不能只看状态码。

| 字段 | 类型 | 取值 | 含义 |
| ---- | ---- | ---- | ---- |
| `status` | string | `"ok"` 或 `"degraded"` | 整体健康状态；仅 db/redis 两个关键组件决定 |
| `ready` | bool | — | 与 `status=="ok"` 等价 |
| `version` | string | `app.__version__`，例如 `"0.1.0"` | 业务发版号 |
| `git_sha` | string | 7 位 git 短 SHA,或 `"unknown"` | 构建对应的 commit |
| `db` | string | `"ok"` 或 `"error: <异常类名>"` | `SELECT 1` 往返结果（顶层冗余字段，兼容旧脚本） |
| `redis` | string | `"ok"` 或 `"error: <异常类名>"` | `PING` 结果（同上） |
| `components` | object | `db` / `redis` / `scheduler` / `data` 各自的状态 | 分组件明细；scheduler/data 异常只是 warn，不会翻转整体状态 |
| `pool` | object | size/checked_in/checked_out/overflow | SQLAlchemy 连接池计数（只在 `readiness_check()` 原始报告里） |
| `checked_at` | string | ISO 时间戳 | 探测时间（结果缓存 5s） |

### 示例响应(健康)

```json
{
  "status": "ok",
  "ready": true,
  "version": "0.1.0",
  "git_sha": "a5384a4",
  "db": "ok",
  "redis": "ok",
  "checked_at": "2026-07-21T08:00:00+00:00",
  "components": {"db": {"status": "ok"}, "redis": {"status": "ok"}, "...": "..."}
}
```

### 示例响应(DB 故障，HTTP 仍为 200)

```json
{
  "status": "degraded",
  "ready": false,
  "version": "0.1.0",
  "git_sha": "a5384a4",
  "db": "error: OperationalError",
  "redis": "ok"
}
```

### 版本号注入

- 业务发版号: `app.main.__version__` 常量,每次发版手动 bump。
- Git SHA: 启动时按以下优先级解析,首次解析后整个进程复用:
  1. 环境变量 `GIT_SHA`(由 CI / Dockerfile `ARG GIT_SHA` 注入)
  2. `git rev-parse --short HEAD` 子进程调用(本地开发)
  3. 兜底 `"unknown"`(容器里既无 env 也无 git 二进制)

## 3. 失败处置

### 3.1 容器起不来

**症状**: `update.sh` 等就绪 300s（150 次 × 2s）后超时 exit 1,或 `docker compose ps` 显示 backend `Exit 1`。

排查清单:
1. `docker compose logs backend --tail 100` 看启动堆栈。
2. `docker compose ps` 确认 postgres / redis 都是 `healthy` —— backend
   `depends_on: condition: service_healthy`,如果依赖项没起来会一直重启。
3. `docker compose exec backend env | grep -E 'DATABASE_URL|REDIS_URL'` 确认环境变量注入正确。
4. `docker compose exec backend alembic current` —— 如果迁移失败,
   backend 容器在入口脚本（`scripts/docker-entrypoint.sh`）的 alembic 步骤就会退出。
   大列 `ALTER COLUMN ... TYPE` 可能物理 rewrite 数分钟，属正常等待（healthcheck
   `start_period` 已放宽到 240s）。
5. 容器在跑但 `/health` body `status=degraded`：直接
   `docker exec alloyresearch-backend python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"`,
   看 `components` 里哪个组件报错（backend 不映射宿主机端口，需在容器内探测）。

### 3.2 Alembic 落后

**症状**: `auto_migrate.sh` 退出码非零,日志包含 `current != head` 或
`Drift detected`。

排查清单:
1. `docker compose exec backend alembic current` 看真实 current。
2. `docker compose exec backend alembic heads --resolve` 看真实 head(注意
   多分支时 `--resolve` 会给出合并后的 head)。
3. `docker compose exec backend alembic history --verbose -r current:head`
   看 pending 迁移的 SQL 大致内容。
4. `docker compose exec backend alembic upgrade head` 手跑一次,看错误堆栈。
5. 常见原因:
   - `alembic merge` 没产生 resolved head → 本地分支没合并就 push
   - 迁移脚本里 DROP COLUMN 命中 NOT NULL 列的现有行 → 需要 backfill
   - 迁移文件顺序错位(数字前缀冲突)→ 检查 `alembic/versions/` 命名

### 3.3 API 5xx

**症状**: `post_deploy_check.sh` 任意探针非 200,或线上反馈接口报错。

排查清单:
1. **快速回滚**: `git revert <bad_sha>` → push → runner 重跑流水线,
   `update.sh` 会自动重新构建并部署上一个好版本。
2. **看响应体**: `post_deploy_check.sh` 输出里附带了 body 前 200 字节,
   通常能直接看到 traceback。
3. **日志**: `docker compose logs -f backend --tail 200`。
4. **路由级 500**: 用 `curl -i` 命中问题路径,贴响应头和 body 到 issue。
5. **数据库问题**: 检查 `docker compose exec backend alembic current` 和
   `psql -U etf -d ad_research -c '\dt'`,看表是否存在。
6. **缓存问题**: Redis 挂了 `/health` body 会报 `status=degraded`（HTTP 仍是 200），
   但只读路由一般还能用 —— 优先重启 redis 容器 `docker compose restart redis`,然后再
   `post_deploy_check.sh` 复测。

## 4. 相关文件

- `/health` endpoint: `app/main.py` (line ~120-161)，探测逻辑在 `app/core/health.py`
- `__version__` / `GIT_SHA` 注入: `app/main.py` (line ~69-93)
- 发布脚本: `deploy/aliyun-ecs/update.sh`
- CI 流水线: `.github/workflows/deploy.yml`
- 迁移校验: `scripts/check_migrations.sh`；迁移执行: `scripts/auto_migrate.sh`（手动）
- 探针脚本: `scripts/post_deploy_check.sh`（手动）
- 回滚脚本: `scripts/rollback.sh`