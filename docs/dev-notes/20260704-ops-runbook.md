# AD-Research 运维 Runbook

> 创建日期：2026-07-04
> 适用范围：阿里云 ECS 生产环境（`/opt/ad-research`）+ 本地 Docker Compose
> 关联脚本：`deploy/aliyun-ecs/*.sh`、`scripts/*.sh`、`.github/workflows/deploy.yml`

---

## 0. 资产总览

### 0.1 部署/更新脚本（`deploy/aliyun-ecs/`）

| 文件 | 用途 | 调用时机 |
| --- | --- | --- |
| `deploy.sh` | 首次一键部署（装 Docker + 初始化 .env + 构建 + 迁移 + 启动） | 新服务器首装 |
| `update.sh` | 日常更新（git pull → 重构后端 → 健康检查 → 可选 alembic upgrade） | 每次 push 后 / 手动 |
| `docker-compose.yml` | 生产 compose（postgres / redis / backend / nginx） | 由 deploy / update / rollback 隐式调用 |
| `nginx.conf` | 反向代理 + 静态资源服务 | 容器启动时挂载 |
| `.env` / `.env.example` | 运行时配置（数据库密码、API key 等） | 必填 |
| `ssl/` | TLS 证书目录 | 容器启动时挂载 |
| `README.md` | 部署说明（与本 runbook 互补） | 文档 |

### 0.2 通用脚本（`scripts/`）

| 文件 | 用途 | 调用时机 |
| --- | --- | --- |
| `restart_backend.sh` | 在 server 上裸重启 backend 容器（旧式入口） | 紧急时手动 |
| `migrate_database.sh` | 把 etf_research 数据库迁移到 ad_research（旧库迁移） | 一次性历史迁移 |
| `rollback.sh` | **一键安全回滚**（指定 git commit 回退） | 出问题需快速回滚 |
| `check_migrations.sh` | **部署前后 alembic 迁移完整性校验** | CI/CD 或部署前后 |
| `*.py`（数据/种子/检查） | 数据回填、初始化、smoke test 等 | 按需 |

### 0.3 GitHub Actions（`.github/workflows/deploy.yml`）

- 触发：`push` to `main` + `workflow_dispatch`
- 流程：备份 head → `git reset --hard origin/main` → 调 `update.sh` → `check_migrations.sh` → health probe
- 失败：写 `/var/log/ad-research/deploy-failures.log`（webhook 待接入）

---

## 1. 日常更新（标准流程）

**首选：`deploy/aliyun-ecs/update.sh`**

```bash
ssh ad-research
cd /opt/ad-research/deploy/aliyun-ecs
./update.sh                     # 完整更新（拉代码 + 重建 + 健康检查 + alembic upgrade）
./update.sh --frontend-only     # 仅前端热更（30s 内完成）
./update.sh --no-db             # 跳过迁移（默认 update.sh 会自动 alembic upgrade head）
FORCE=1 ./update.sh             # 即使没新 commit 也强制重编
```

**update.sh 内部步骤**：
1. 校验 `.env`、记录 `before` / `after` git hash
2. `docker compose build backend`
3. `docker compose stop backend nginx` → `docker compose up -d backend`
4. 60s `/health` 探测循环
5. `docker compose exec backend alembic upgrade head`（默认开启）
6. 输出 release notes（`git log before..after`）

> **不要直接 `docker compose restart`** —— 那会丢失代码更新。

---

## 2. 紧急回滚（出问题了）

**首选：`scripts/rollback.sh`**

```bash
ssh ad-research
cd /opt/ad-research

# 找上一个稳定 commit
git log --oneline -10

# 回滚到指定 commit（短 / 长 hash 都可）
bash scripts/rollback.sh a5384a4
```

**rollback.sh 内部步骤**：
1. 校验 `<target>` commit 存在（`git rev-parse --verify`）
2. 备份当前 HEAD → `/var/log/ad-research/rollback-latest.log`
3. `git reset --hard <target>`
4. `docker compose up -d --build backend`
5. 60s `/health` 探测循环
6. 输出 release notes（`git log PREV..TARGET`）

**失败兜底**：
- 任意阶段出错 → 打印「回滚失败」并提示跑 `update.sh` 重新同步到 main
- 备份日志路径：`/var/log/ad-research/rollback-latest.log`

**手动回滚（rollback.sh 也不灵时）**：
```bash
ssh ad-research
cd /opt/ad-research
git reset --hard <known-good-commit>
cd deploy/aliyun-ecs
docker compose up -d --build backend
# 等待 /health 通过
```

---

## 3. 数据库迁移

### 3.1 部署前校验（CI / 手动）

**首选：`scripts/check_migrations.sh`**

```bash
# 本地
bash scripts/check_migrations.sh

# 阿里云 ECS
bash scripts/check_migrations.sh deploy/aliyun-ecs/docker-compose.yml
```

**退出码**：
- `0` —— current == head，模型可导入，一切 OK
- `10` —— 需要迁移（current != head）
- `20` —— 异常（容器没起、alembic 失败、模型导入失败）

**CI 行为**（`.github/workflows/deploy.yml`）：退出 10 时自动跑 `alembic upgrade head` 并再次校验；其他情况报错并置 `rollback=true`。

### 3.2 升级（update.sh 内置）

`update.sh` 默认会执行 `docker compose exec backend alembic upgrade head`。如果迁移失败：
```bash
cd /opt/ad-research/deploy/aliyun-ecs
docker compose exec backend alembic upgrade head
# 查看 alembic 版本
docker compose exec backend alembic current
docker compose exec backend alembic history
```

### 3.3 旧库迁移（一次性）

历史遗留：原项目使用 `etf_research` 数据库，现统一为 `ad_research`。

```bash
bash scripts/migrate_database.sh deploy/aliyun-ecs/docker-compose.yml
```

**仅当**服务器上同时存在 `etf_research` 时才需要运行；新部署不需要。

---

## 4. Health 探针

| 端点 | 地址 | 说明 |
| --- | --- | --- |
| `/health` | `http://<server>:8000/health` | FastAPI 健康检查（返回 200 = OK） |

**手动探测**：
```bash
curl -sf http://localhost:8000/health && echo OK || echo FAIL
```

**容器内探测**（推荐用于 CI）：
```bash
cd /opt/ad-research/deploy/aliyun-ecs
docker compose exec -T backend python -c \
  "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"
```

---

## 5. 日常检查

### 5.1 容器状态

```bash
ssh ad-research
cd /opt/ad-research/deploy/aliyun-ecs

# 概览
docker ps

# 仅看我们的服务
docker ps --filter name=alloyresearch

# 资源占用
docker stats --no-stream
```

### 5.2 滚动日志

```bash
# 最近 200 行（默认三个服务）
docker compose logs --tail 200

# 仅 backend，实时跟随
docker compose logs -f backend

# 某段时间内
docker compose logs --since 30m backend
```

### 5.3 数据库

```bash
# 进入 postgres 容器
docker compose exec postgres psql -U etf -d ad_research

# 表数量
docker compose exec -T postgres psql -U etf -d ad_research -c \
  "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';"

# alembic 版本
docker compose exec backend alembic current
```

### 5.4 磁盘

```bash
df -h
docker system df
# 清理 dangling 镜像（慎用）
docker image prune -f
```

---

## 6. 紧急止血

**场景**：backend 起不来，但 nginx 仍要保持 80/443 可达（哪怕只返回静态错误页）。

```bash
ssh ad-research
cd /opt/ad-research/deploy/aliyun-ecs

# 停 backend（nginx + postgres + redis 不动）
docker compose stop backend

# 此时 nginx 仍可达，可能返回 502/504，但不会 500
curl -I http://localhost
```

**恢复**：
```bash
docker compose up -d backend
# 等待 /health 通过
```

**更进一步（如果 docker daemon 异常）**：
```bash
sudo systemctl restart docker
cd /opt/ad-research/deploy/aliyun-ecs
docker compose up -d
```

---

## 7. 常见故障

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| `/health` 502 | backend 容器未启动 / 端口冲突 | `docker compose logs backend --tail 100` |
| `/health` 504 | backend 启动慢 / 数据库未就绪 | 等待 30s 重试；查 postgres healthcheck |
| 前端 404 | `web_dist` 卷未挂载 / `--frontend-only` 后未刷缓存 | `docker compose restart nginx` |
| alembic 失败 | 模型与 migration 不一致 | 看日志；必要时 `alembic downgrade -1` |
| push 触发 workflow 失败 | runner 未连接 / 磁盘满 | `deploy-failures.log` 在 `/var/log/ad-research/` |

---

## 8. 联系 & 升级窗口

- 紧急变更：直接 ssh 到服务器，按本 runbook 操作
- 计划变更：合并 PR → push main → GitHub Actions 自动部署
- 重要操作后：在团队群同步 HEAD hash（`git rev-parse --short HEAD`）

---

## 附：自托管 Runner 前置

GitHub Actions 使用 self-hosted runner，必须满足：
- 已 `git clone https://github.com/<org>/ad-research.git /opt/ad-research`
- runner 工作目录能访问 `/opt/ad-research`
- runner 用户在 `docker` 组内（或 sudo 可用）
- `/var/log/ad-research/` 可写（否则日志降级到 `/tmp`）

> 本 runbook 涉及的脚本均不引入第三方依赖；`shellcheck` 未安装时可跳过静态检查，但建议 CI 容器内固定装一份。