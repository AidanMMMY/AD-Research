# 2026-07-19 部署连环失败 runbook — 4 个隐藏 tripwire

> 2026-07-18~19 连续 #275/#276/#277/#278/#279/#280 共 6 次 deploy 失败，
> 每个失败原因都不同，但都"看似无关"。本文按时间线汇总 4 个隐藏 tripwire，
> 每个的触发条件、根因、复现、和修复方案——下次踩到任何一个都能秒查。

---

## 时间线速览

| Run | Commit | 失败点 | 真因 |
|---|---|---|---|
| #275 | a539451 | step 2 sync | 工作树脏（overnight_* 未 gitignore） |
| #276 | fbf3537 | step 2 sync | 同上 |
| #277 | 9c5e097 | step 3 build | poetry.lock 与 pyproject 不一致 |
| #278 | 9c5e097 | step 3 build | 同 #277（SIGINT 后 retry 仍失败） |
| #279 | 9c5e097 | step 3 update.sh | update.sh 引用不存在的 service celery-worker |
| #280 | 57e25c0 | step 3 container | alembic 阻塞 + healthcheck 太严 + orphan 持锁 |

#275/#276 修复 commit：9c5e097（.gitignore）
#277/#278 修复 commit：a39b9be（poetry lock）
#279 修复 commit：57e25c0（update.sh celery name）
#280 修复 commit：7c4deae（orphan 清理 + 等就绪 300s）

---

## Tripwire #1：ECS 工作树被 overnight_* 污染

### 触发条件
- deploy.yml step 2 检测 `git status --porcelain` 非空 → exit 1
- 实际 untracked 目录：overnight_*/ (worker 跑出来的输出，落在 /opt/ad-research 根目录)

### 根因
- overnight-research worker 写入到 `/data/ad-research/overnight_*/`（持久化），但 ECS 上
  `/opt/ad-research` 是工作树目录，被 git status 看见
- 仓库 .gitignore 没排除 overnight_*/

### 修复（commit 9c5e097）
```gitignore
overnight_*/
overnight_test*/
agent/overnight_hermes.env
```

### 防御
- 任何 worker / agent 在 `/opt/ad-research` 写入临时产物，**必须先 gitignore**
- ECS 上 `/opt/ad-research` 是工作树，写持久化产物应走 `/data/ad-research/` 挂载点
- 如再次发生：ssh ECS 跑 `git clean -fd`（gitignore 已覆盖，safe）

---

## Tripwire #2：pyproject.toml 改了但 poetry.lock 没 commit

### 触发条件
- Docker build step 6 跑 `poetry install` 时报：
  ```
  pyproject.toml changed significantly since poetry.lock was last generated.
  Run `poetry lock` to fix the lock file.
  ```

### 根因
- 任何在 pyproject.toml 新增/升级依赖的 commit，**必须**同步 commit poetry.lock
- 之前 5 个 commit 改了 pyproject（celery/playwright/readability-lxml/simhash...）但 lock 没动
- poetry install 在 strict 模式下会拒装

### 修复（commit a39b9be）
```bash
cd /Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform
poetry lock          # poetry 2.x 没有 --no-update，但 lock 不会升版本
git add poetry.lock
git commit -m "fix(deploy): poetry lock 同步 ..."
git push
```

### 防御
- **PR / commit 模板**：任何修改 `pyproject.toml` 的 commit message 末尾必须带
  `poetry-lock: regenerated`（用 commitlint 之类强制）
- CI 加一步 `poetry check` 在 build 之前拦截（最低成本）
- ECS 端 backup 旧 lock，万一 lock 退化可以快速回退

---

## Tripwire #3：update.sh 引用了不存在的 service 名

### 触发条件
- update.sh 跑 `docker compose stop backend nginx celery-worker` 时报：
  ```
  no such service: celery-worker
  ```
- `set -euo pipefail` 直接 exit 1，deploy 失败

### 根因
- docker-compose.yml 里 celery 拆成两个独立 worker：
  ```
  celery-worker-indicator  (queue=indicator, concurrency=4)
  celery-worker-cninfo     (queue=celery,cninfo, concurrency=2)
  ```
- 但 update.sh 三处仍引用 `celery-worker`（错的 service 名）——历史 bug

### 修复（commit 57e25c0）
```bash
# deploy/aliyun-ecs/update.sh 三处全部替换
docker compose stop backend nginx celery-worker-indicator celery-worker-cninfo
docker compose rm -f -s backend celery-worker-indicator celery-worker-cninfo nginx
docker compose up -d --force-recreate backend celery-worker-indicator celery-worker-cninfo
```

### 防御
- update.sh 里 service 名应**只用变量**（如 `${BACKEND_SVC}`）而非硬编码
- 加 CI grep 检查：`grep -n 'celery-worker\b' deploy/aliyun-ecs/update.sh` 应该 0 个匹配
  （`celery-worker` 单数是历史拼写）

---

## Tripwire #4：alembic 大列 ALTER 撞 orphan INSERT 持锁

### 触发条件
- alembic 跑 `ALTER TABLE etf_indicator ALTER COLUMN return_X TYPE NUMERIC(18,6)`
- 等锁超过 100s 仍未拿到 AccessExclusiveLock
- update.sh 等 120s 超时 → exit 1
- docker compose 直接杀所有容器（healthcheck 一直 unhealthy）
- 一旦 alembic 退出，列定义仍为旧值，下次 deploy 重新走一遍同样过程

### 根因（两层）
1. **大列 ALTER 需要物理 rewrite**：numeric(8,4) → numeric(18,6) 在 PG 实际
   跑了 5-6 分钟（6 列 × ~1min）—— 不是 catalog-only 操作
2. **orphan 容器持锁**：历史的 `alloyresearch-celery-worker` /
   `alloyresearch-temp-indicator-worker` 在持续向 `etf_indicator` 表 INSERT，
   占着 ShareLock 排队等 AccessExclusiveLock；docker compose 不识别这些
   旧容器名（它们在 compose 改名之前已存在），所以不会 stop 它们

### 修复（commit 7c4deae）
```bash
# deploy/aliyun-ecs/update.sh step 2.5 加 orphan 清理
docker ps -a --filter "label=com.docker.compose.project=alloyresearch" \
    --format '{{.ID}} {{.Names}}' \
  | awk '$2 !~ /^(alloyresearch-backend|...)$/ {print $1}' \
  | xargs -r docker rm -f >/dev/null 2>&1

# step 3 等就绪窗口从 120s 提到 300s
log_info "等待 backend 就绪 (最多 300s，需 /health status=ok)..."
for i in $(seq 1 150); do  # 150 * 2s = 300s
```

### 防御（建议但未实施）
- docker-compose.yml backend healthcheck `start_period: 30s` 提到 `180s`
  （让 docker compose 的 healthcheck 别在 alembic 期间误判 unhealthy）
- 大列迁移在 PR review 时**必须**手动估算耗时；超 1min 必须拆批或用
  pg_repack / 在线 schema 工具

---

## 验证清单（下次 deploy 完成后核对）

- [ ] `docker exec alloyresearch-backend curl http://localhost:8000/health` body 含 `git_sha=<新 commit>`
- [ ] `docker compose ps` 所有服务 `running` / `healthy`，无 `Created`
- [ ] `docker ps -a` 无 orphan 容器（name 不在 compose 里）
- [ ] `/var/log/ad-research/deploy-latest.log` 含 `alembic current 已等于 head`
- [ ] `curl https://<domain>/health` 返回 200 + `status=ok`

---

## 应急逃生口

如果 deploy 整体崩溃，可以手动 SSH 介入：

```bash
# 1. 杀掉 orphan 容器（持锁元凶）
docker kill alloyresearch-celery-worker alloyresearch-temp-indicator-worker

# 2. 在 backend 容器内手动等 alembic 完成（不要 SIGINT，让它跑完）
docker exec alloyresearch-backend cat /proc/1/cmdline
# 应该是 docker-entrypoint.sh uvicorn ... 但 uvicorn 还没起 → alembic 还在

# 3. 等 alembic 自然完成后，强制启动 celery workers
cd /opt/ad-research/deploy/aliyun-ecs
docker compose up -d celery-worker-indicator celery-worker-cninfo nginx

# 4. 校验
docker ps --filter "name=alloyresearch" --format "{{.Names}} {{.Status}}"
curl http://localhost/health
```