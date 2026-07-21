# 阿里云 ECS 更新部署指南

> 2026-06-25 | 基于 `deploy/aliyun-ecs/` 部署套件
> 最后核实更新：2026-07-21

## 部署架构

```
Browser → Nginx(:8000 / :443) → /api/* → Backend(:8000)
                              → /*     → 前端静态文件 (web_dist volume)
                                           ↑
                                     Backend 启动时 rsync dist-image → web_dist
```

| 服务 | 镜像 | 端口 | 职责 |
|---|---|---|---|
| postgres | `postgres:16-alpine` | 内部 | 数据库 |
| redis | `redis:7-alpine` | 内部 | 缓存 |
| backend | `ad-research:<git_sha>` (自构建) | expose 8000 | API + 前端文件复制 + alembic 迁移（入口脚本） |
| celery-worker-indicator | `ad-research:latest` | 内部 | Celery 队列 `indicator`（指标计算，concurrency=4） |
| celery-worker-cninfo | `ad-research:latest` | 内部 | Celery 队列 `celery,cninfo,industry`（巨潮公告等，concurrency=2） |
| nginx | `nginx:alpine` | 8000 / 80 / 443 | 反向代理 + 静态文件 + HTTPS |

## 快速更新（推荐）

```bash
# 1. SSH 登录 ECS
ssh root@<服务器IP>

# 2. 进入部署目录
cd /opt/ad-research/deploy/aliyun-ecs

# 3. 一键更新
./update.sh
```

## 手动更新步骤

### 完整更新（代码 + 前端 + 后端）

日常更新一律走 `update.sh`（与 CI 同一入口）。以下为手动等价步骤，仅供排查时使用：

```bash
cd /opt/ad-research
git pull origin main
cd deploy/aliyun-ecs

# 重新构建镜像（update.sh 默认 --no-cache，确保重新编译前端）
docker compose build backend --no-cache

# 重启服务
docker compose up -d

# 查看日志
docker compose logs -f backend --tail 50
```

### 仅更新前端（无后端代码变更）

```bash
cd /opt/ad-research
git pull
cd deploy/aliyun-ecs
docker compose build backend     # 前端在 Dockerfile 阶段1编译
docker compose restart backend nginx
```

## update.sh 选项

| 选项 | 说明 |
|---|---|
| `--frontend-only` | 仅更新前端 UI，约 30 秒 |
| `--no-db` | 跳过迁移状态只读校验（backend 入口仍会执行 `alembic upgrade head`） |

其他机制：

- **互斥锁**：脚本启动时用 `flock` 抢 `/var/run/ad-research-deploy.lock` 排他锁，已有其他 deploy 在跑时立即退出让路（`LOCK_FILE` 环境变量可覆盖路径）。
- **等就绪窗口**：backend 重建后最多等 300 秒（150 次 × 2s），要求容器内 `/health` body 的 `status=ok`，超时则 exit 1（2026-07-19 起，覆盖 alembic 大列 ALTER 的耗时）。
- **短 build 告警**：全量 build 耗时 < 30s 会打 WARN（可能 buildx cache 命中、镜像未真正重建）。
- **失败重试**：首次 `docker compose build` 失败会 sleep 5s 自动重试一次（应对阿里云 registry 抖动）。
- **残留容器清理**：启动前会 `rm -f -s` 本项目旧容器，并清理 compose 不识别的 orphan 容器（防止旧 worker 持表锁阻塞迁移）。
- `FORCE=1` 不再控制行为，仅作为元数据写入锁文件，供排查谁触发了部署。

## 关键机制

### 前端自动更新
Dockerfile 采用多阶段构建：
1. 阶段 1（node:20-alpine）：`npm run build` → `/app/web/dist`
2. 阶段 2（python:3.11-slim）：从阶段 1 复制产物到 `/app/web/dist-image`
3. backend 容器入口脚本（`scripts/docker-entrypoint.sh`）：`rsync -a --delete /app/web/dist-image/ /app/web/dist/`
4. `web_dist` 是 backend 和 nginx 共享的 Docker Volume
5. nginx 从 `/usr/share/nginx/html`（= `web_dist`）提供静态文件

### 数据库迁移
backend 容器入口脚本在启动 uvicorn 前执行 `alembic upgrade head`，是**唯一**的迁移执行点。`update.sh` 在部署末尾只做 `current == head` 的只读校验，不一致则 exit 1。

### Nginx 缓存策略
- `/index.html` — 禁止缓存（每次刷新拿到最新 SPA 入口）
- `/assets/` — 长期缓存 1 年（Vite 打包文件名带 hash，内容变更自动失效）
- `/api/` — 反向代理到 backend（限流 50r/s，SSE 端点 `*/stream` 长超时单独放行）
- 80 端口与裸域 443 — 301 重定向到 `https://www.alloyresearch.net`（证书在 `deploy/aliyun-ecs/ssl/`）

## 常用运维命令

| 场景 | 命令 |
|---|---|
| 查看所有容器状态 | `docker compose ps` |
| 查看后端日志 | `docker compose logs -f backend --tail 100` |
| 查看 Celery worker 日志 | `docker compose logs -f celery-worker-indicator celery-worker-cninfo` |
| 查看 nginx 日志 | `docker compose logs -f nginx` |
| 数据库迁移（手动） | `docker compose exec backend alembic upgrade head` |
| 重启单个服务 | `docker compose restart backend` |
| 全部停止 | `docker compose down` |
| 全部重启 | `docker compose up -d` |
| 进入后端容器 | `docker compose exec backend bash` |

## 首次部署

首次部署使用 `deploy.sh`（一键脚本），自动完成：
1. 安装 Docker 及依赖
2. 生成强密码（DB、AUTH_SECRET_KEY、管理员密码）
3. 构建镜像并启动所有服务
4. 执行数据库初始化和种子用户创建

详见 `deploy/aliyun-ecs/README.md`。

## ECS 推荐配置

| 配置项 | 推荐值 |
|---|---|
| 实例规格 | `ecs.c7.large`（2核4G） |
| 操作系统 | Ubuntu 24.04 LTS |
| 系统盘 | 40GB ESSD |
| 安全组端口 | 8000（平台）+ 22（SSH） |
| 部署路径 | `/opt/ad-research/` |
