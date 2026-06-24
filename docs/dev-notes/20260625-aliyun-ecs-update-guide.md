# 阿里云 ECS 更新部署指南

> 2026-06-25 | 基于 `deploy/aliyun-ecs/` 部署套件

## 部署架构

```
Browser → Nginx(:8000) → /api/* → Backend(:8000)
                       → /*     → 前端静态文件 (web_dist volume)
                                    ↑
                              Backend 启动时 cp dist-image → web_dist
```

| 服务 | 镜像 | 端口 | 职责 |
|---|---|---|---|
| postgres | `postgres:16-alpine` | 内部 | 数据库 |
| redis | `redis:7-alpine` | 内部 | 缓存 |
| backend | `ad-research:latest` (自构建) | expose 8000 | API + 前端文件复制 |
| nginx | `nginx:alpine` | 8000 | 反向代理 + 静态文件 |

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

```bash
cd /opt/ad-research
git pull origin main
cd deploy/aliyun-ecs

# 重新构建镜像（--no-cache 确保重新编译前端）
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
| `--no-db` | 跳过手动数据库迁移（backend 启动时自动执行） |
| `FORCE=1` | 强制重编，即使代码无变更 |

## 关键机制

### 前端自动更新
Dockerfile 采用多阶段构建：
1. 阶段 1（node:20-alpine）：`npm run build` → `/app/web/dist`
2. 阶段 2（python:3.11-slim）：从阶段 1 复制产物到 `/app/web/dist-image`
3. backend 容器启动命令：`cp -r /app/web/dist-image/* /app/web/dist/`
4. `web_dist` 是 backend 和 nginx 共享的 Docker Volume
5. nginx 从 `/usr/share/nginx/html`（= `web_dist`）提供静态文件

### 数据库迁移
backend 启动命令中已包含 `alembic upgrade head`，容器启动时自动执行。

### Nginx 缓存策略
- `/index.html` — 禁止缓存（每次刷新拿到最新 SPA 入口）
- `/assets/` — 长期缓存 1 年（Vite 打包文件名带 hash，内容变更自动失效）
- `/api/` — 反向代理到 backend

## 常用运维命令

| 场景 | 命令 |
|---|---|
| 查看所有容器状态 | `docker compose ps` |
| 查看后端日志 | `docker compose logs -f backend --tail 100` |
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
