# 20260704 — 部署后健康校验手册

> 目标:把"升级后一定健康"做成流水线自动断言,而不是肉眼看一眼就当成功。

## 1. 标准发布流水线

从代码推送到线上对外可用的完整路径,顺序如下,**任一步骤非零退出即终止**,
排查完才能继续推。

```
git push  →  self-host runner checkout  →  update.sh  →  auto_migrate.sh  →  post_deploy_check.sh
```

| 步骤 | 入口 | 作用 | 失败信号 |
| ---- | ---- | ---- | -------- |
| ① git push | 本地 `git push origin main` | 把 commit 推到 GitHub | 推送拒绝 / pre-commit hook 红 |
| ② self-host runner | GitHub Actions self-hosted runner | 在 ECS 上拉代码 | runner offline / checkout 失败 |
| ③ `update.sh` | `deploy/aliyun-ecs/update.sh` | git pull → docker compose build → 重启 backend | 30 次轮询 `/health` 仍超时 |
| ④ `auto_migrate.sh` | `scripts/auto_migrate.sh` | 比对 alembic current / head,必要时 `upgrade head` | 迁移后 current ≠ head |
| ⑤ `post_deploy_check.sh` | `scripts/post_deploy_check.sh <url>` | 探针 /health、/docs、/openapi.json,严格 JSON 字段断言 | 任何 JSON 字段缺失或 HTTP != 200 |

### GitHub Actions 模板(参考)

```yaml
- name: Checkout
  uses: actions/checkout@v4
  with:
    fetch-depth: 0   # 需要完整历史给 update.sh 比对

- name: Deploy via update.sh
  run: ./deploy/aliyun-ecs/update.sh

- name: Auto-migrate
  run: ./scripts/auto_migrate.sh ./deploy/aliyun-ecs/docker-compose.yml

- name: Post-deploy health check
  run: ./scripts/post_deploy_check.sh "${{ secrets.PUBLIC_URL }}"
```

## 2. 健康检查标准

`GET /health` 必须满足以下契约,任何一条不达标都返回 HTTP 503:

| 字段 | 类型 | 取值 | 含义 |
| ---- | ---- | ---- | ---- |
| `status` | string | `"ok"` 或 `"degraded"` | 整体健康状态,503 时一定是 `"degraded"` |
| `version` | string | `app.__version__`,例如 `"0.1.0"` | 业务发版号 |
| `git_sha` | string | 7 位 git 短 SHA,或 `"unknown"` | 构建对应的 commit |
| `db` | string | `"ok"` 或 `"error: <异常类名>"` | `SELECT 1` 往返结果 |
| `redis` | string | `"ok"` 或 `"error: <异常类名>"` | `PING` 结果 |

### 示例响应(健康)

```json
{
  "status": "ok",
  "version": "0.1.0",
  "git_sha": "a5384a4",
  "db": "ok",
  "redis": "ok"
}
```

### 示例响应(DB 故障)

```json
{
  "status": "degraded",
  "version": "0.1.0",
  "git_sha": "a5384a4",
  "db": "error: OperationalError",
  "redis": "ok"
}
```

HTTP 状态码: 200 (健康) / 503 (任一子检查失败)。

### 版本号注入

- 业务发版号: `app.main.__version__` 常量,每次发版手动 bump。
- Git SHA: 启动时按以下优先级解析,首次解析后整个进程复用:
  1. 环境变量 `GIT_SHA`(由 CI / Dockerfile `ARG GIT_SHA` 注入)
  2. `git rev-parse --short HEAD` 子进程调用(本地开发)
  3. 兜底 `"unknown"`(容器里既无 env 也无 git 二进制)

## 3. 失败处置

### 3.1 容器起不来

**症状**: `update.sh` 30 次轮询 /health 全部失败,或 `docker compose ps` 显示 backend `Exit 1`。

排查清单:
1. `docker compose logs backend --tail 100` 看启动堆栈。
2. `docker compose ps` 确认 postgres / redis 都是 `healthy` —— backend
   `depends_on: condition: service_healthy`,如果依赖项没起来会一直重启。
3. `docker compose exec backend env | grep -E 'DATABASE_URL|REDIS_URL'` 确认环境变量注入正确。
4. `docker compose exec backend alembic current` —— 如果迁移失败,
   backend 容器在 `command:` 的 alembic 步骤就会退出。
5. 健康检查 503 但容器在跑:直接 `curl http://localhost:8000/health`,
   看 `db` / `redis` 字段哪个报错。

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
6. **缓存问题**: Redis 挂了 `/health` 会 503,但只读路由一般还能用
   —— 优先重启 redis 容器 `docker compose restart redis`,然后再
   `post_deploy_check.sh` 复测。

## 4. 相关文件

- `/health` endpoint: `app/main.py` (line ~117-160)
- `__version__` / `GIT_SHA` 注入: `app/main.py` (line ~64-89)
- 发布脚本: `deploy/aliyun-ecs/update.sh`
- 迁移脚本: `scripts/auto_migrate.sh`
- 探针脚本: `scripts/post_deploy_check.sh`