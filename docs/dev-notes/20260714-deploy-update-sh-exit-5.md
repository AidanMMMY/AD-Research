# deploy update.sh Exit 5 容器残留清理 Runbook

## 1. 问题

`deploy/aliyun-ecs/update.sh` 在 GitHub Actions 部署时偶发 `exit=5`，导致容器被 step 3.5 删除但 step 4 未启动 → 服务挂掉。

最近几次发生时间：
- 2026-07-12 run #234（commit 2b167bd）
- 2026-07-14 多次本地 FORCE=1 部署

## 2. 根因

`update.sh` step 3.5 加了「清理残留容器」逻辑：

```bash
docker compose rm -f -s backend celery-worker nginx 2>/dev/null || true
PROJECT_NAME=$(docker compose ls --format json 2>/dev/null | jq -r '.Name // empty' | head -1)
if [ -n "$PROJECT_NAME" ]; then
  docker container prune -f --filter "label=com.docker.compose.project=${PROJECT_NAME}" 2>/dev/null || true
fi
```

`set -euo pipefail` + `pipefail` + `docker compose rm` 返回 5（无容器可删 / 状态不对）→ 整个脚本在 `|| true` 后仍因为 pipefail 中断。

`docker compose ls --format json` 在某些 docker compose v2 版本返回格式不稳定，配合 `jq` 在 pipe 中失败时 exit code 通过管道传播。

## 3. 临时恢复（已用过）

```bash
# 当 deploy 失败、容器不在运行时
ssh -i ~/.ssh/claude_aliyun root@47.239.13.111 '
  cd /opt/ad-research/deploy/aliyun-ecs
  docker compose up -d --force-recreate backend celery-worker
  sleep 8
  docker compose up -d nginx
  sleep 12
  curl -sf http://localhost:8000/health
'
```

预期输出：`{"status":"ok",...}`

## 4. 永久修复（已应用，2026-07-15）

修复 `update.sh` step 3.5：

```bash
log_step "3.5/5 清理残留容器"
# 用子 shell + set +e 显式关闭 errexit/pipefail，避免 `docker compose rm` 返回 5
# 或 `docker compose ls | jq` 管道失败时让整段脚本中断（set -euo pipefail 会）。
# 只清理本 compose project 的容器，绝不影响其他项目或手动容器。
(
    set +e
    docker compose rm -f -s backend celery-worker nginx >/dev/null 2>&1
    docker compose ls --format json 2>/dev/null \
        | jq -r '.Name // empty' 2>/dev/null \
        | head -1 \
        | xargs -r -I{} docker container prune -f --filter "label=com.docker.compose.project={}" >/dev/null 2>&1
    true
)
```

关键改动：
1. `set +e` 关闭 errexit 在清理块内
2. `>/dev/null 2>&1` 完全抑制 stderr
3. 块尾 `true` 显式返回 0
4. 用 `xargs` 替代 `if [...]` 避免 `docker compose ls` 失败时中断

应用记录：
- 文件：`deploy/aliyun-ecs/update.sh`
- 时间：2026-07-15
- 触发：GitHub Actions run #242（commit docs: add runbooks for fund-flow, indicator completeness, deploy exit-5）再次触发 exit 5 告警后本地排查
- 结果：已本地修改，尚未 push（等待用户确认）

## 5. 临时跳过 step 3.5 的应急方案

如果 update.sh 持续失败，可以临时注释掉 step 3.5：

```bash
# 在 update.sh 找到 "3.5/5 清理残留容器" 行，注释掉整个块
```

但**不推荐**长期这么做，因为 step 3.5 的目的正是防止「上次 deploy 失败留下的同名容器导致新容器无法创建」。

## 6. 监控

部署后**必须**确认：

```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
# 期望：4 个容器都在跑（backend / celery-worker / nginx / postgres / redis）
curl -sf http://localhost:8000/health
# 期望：{"status":"ok","db":"ok","redis":"ok"}
```

如果只看到 redis / postgres / hermes 三个，backend / celery-worker / nginx 全没了 → deploy 失败，立刻按第 3 节手动恢复。

## 7. 关联

- 之前的「update.sh 容器清理」修复 commit：`9ef26d7`
- 完整方案见后续 sprint 整改（本 runbook 仅记录现状 + 应急恢复）