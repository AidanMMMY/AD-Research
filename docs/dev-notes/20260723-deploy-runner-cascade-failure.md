# 2026-07-23 Deploy Runner Cascade-Failure Runbook

> 症状：self-hosted `aliyun-etf-backend` runner 在 push 后第 5 个 step（`update.sh`
> attempt 1/2）完成后 ~20s 整体失联，所有后续 step 标 cancelled/skipped，
> job conclusion = failure。本文件记录根因 + 排查 + 已落地的修复。

---

## 1. 现象

最近 3 次 deploy 连续同样失败：

| Run | SHA | 耗时 | step 5 | step 6 | job |
|---|---|---|---|---|---|
| #315 | c238900 | 11m38s | success | (没跑) | ✅ success |
| #316 | e181574 | 23m34s | success 14m28s | skipped | ❌ failure |
| #317 | 75abf8c | 22m43s | success > 20m | skipped | ❌ failure |
| #318 | f9445e7 | 6m17s | success 3m40s | **cancelled** | ❌ failure |

**模式**：step 1-4 全 success → step 5 success → step 6 cancelled + step 7+ skipped → job conclusion = failure（runner cascade 失联触发的 GitHub 内部判定）。

---

## 2. 根因（双因素）

### 2.1 deploy.yml step 5 缺 timeout-minutes

`step 5` 没有 `timeout-minutes`，仅依赖 job-level `timeout-minutes: 45`。
`step 5` 在 `docker compose build backend --no-cache` 跑全量 rebuild 时很容易 > 15min。
GitHub 的 step-level 没有 timeout 时，单 step 会跑到底不会主动取消，
最后由 job-level 切 job。**这个设计只对正常 step 友好，对"挂在后台不动"的
step 是灾难** —— runner host 在跑 docker build 时 CPU/IO 满载，
期间任何 heartbeat / GC / OOM 都会被延迟触发，进而整 runner 失联。

### 2.2 `continue-on-error: true` 把 step 5 真失败标 success

```yaml
- name: Run update.sh (unified entrypoint) [attempt 1/2]
  id: update_sh
  continue-on-error: true   # ← 这里
```

`continue-on-error: true` 让 `bash update.sh` 退出非 0 时，
这个 step 的 `conclusion` 被 GitHub 重写为 success。
但 `outcome` 字段还是 `failure`（这正是 step 6 用 `if: steps.update_sh.outcome == 'failure'` 来判断重试的原因）。

**问题**：当 step 5 实际失败（比如 runner host 失效前最后一次 heartbeat 没收到）
而 `bash update.sh` 当时也在异常退出时，runner 失联**先于** step 6 启动，
把后续 step 全部 skipped，把 job 标 failure。
step 6 永远进不去 attempt 2，因为 runner 已经死了。

---

## 3. 落地修复（同一 commit）

### 3.1 step 5 + step 6 都加 `timeout-minutes: 15`

```yaml
- name: Run update.sh (unified entrypoint) [attempt 1/2]
  timeout-minutes: 15    # ← 新增
  continue-on-error: true
  ...
- name: Retry Run update.sh (unified entrypoint) [attempt 2/2]
  timeout-minutes: 15    # ← 新增
  continue-on-error: false
  ...
```

效果：step 超过 15 min 立即被 GitHub 主动取消 → runner host 不会被
单 step 拖到失联 → job 能干净地进 step 6 retry。
预期下次 deploy 即使 host 不健康也会在 15 min 后强制进入 attempt 2 → 失败 → 执行 rollback。

### 3.2 Backend CI 的 Setup Python 0s 失败

`actions/setup-python@v5` + `cache: 'poetry'` 但没 `cache-dependency-path`
时，setup-python 内部会 fast-fail 抛错（#1 in current main, conclusion=failure
started_at=14:47:18 completed_at=14:47:18, 0s 完成)。

修复：显式给 `cache-dependency-path: poetry.lock`。
（参考 actions/setup-python 文档：当 `cache` 是 poetry/pipenv/uv 时，
必须配 `cache-dependency-path` 才会真正启用缓存。）

---

## 4. ECS Runner Host 健康排查（on-call）

如果改完 workflow 后 deploy 仍然失败，需要 SSH 上 runner host 检查。
**常见原因**（按概率排序）：

### 4.1 磁盘满

```
ssh runner-host
df -h                    # /data, /var/lib/docker
docker system df
docker system prune -af  # 紧急清理（会清掉所有未在用的 image）
```

7-17 /data 满事件后续可能再次复发。`update.sh` 会 build 新镜像、写临时 layer 到
/var/lib/docker/tmp。`buildx` 缓存路径 `${PROJECT_ROOT}/.buildx-cache` 也要查。

### 4.2 runner daemon 异常

```bash
systemctl status actions.runner.*  # 找具体的 service 名
journalctl -u actions.runner.* -n 200 --no-pager
```

如果 daemon 失联但 host 还在，做：
```bash
sudo systemctl restart actions.runner.*
```

### 4.3 内存 / OOM

```bash
free -h
dmesg | tail -100 | grep -i "killed\|oom"
```

docker build 期间 RSS 可能达 4-6GB。如果只有 8GB 物理内存会触发 OOM killer，
把 runner daemon 一起杀掉。

### 4.4 网络抖动

阿里云 HTTP/2 registry 偶发 RESET_STREAM。update.sh 内部已有 5s sleep +
retry，但**大 layer pull (>500MB) 的失败概率更高**。

### 4.5 runner 注册 token 过期

GitHub self-hosted runner 注册 token 默认 1h 过期（如果走 gh api register）。
长期 runner 不会过期，但 transient 模式下需要定期重新注册。

---

## 5. 当前部署状态（2026-07-23 14:53 UTC）

| Workflow | Run | status | 备注 |
|---|---|---|---|
| Backend CI | #1 | ❌ failure | Setup Python 0s 失败，已修 |
| Web CI | #20 | ✅ success | |
| Deploy to Aliyun | #318 | ❌ failure | runner cascade，已修 deploy.yml |

**生产 backend 仍跑 75abf8c**，f9445e7 的 `app/api/v1/internal.py` + orchestrate watchdog **未上线**。

**下一步**：
1. 把 timeout + cache-dependency-path 修复 push 上去
2. GitHub Actions 重新触发 deploy workflow_dispatch
3. 用户在 ECS runner host 上 **先 df -h** 确认不是磁盘满

---

## 6. 已落地

- [x] `.github/workflows/deploy.yml` step 5 + step 6 加 `timeout-minutes: 15`
- [x] `.github/workflows/backend-ci.yml` Setup Python 加 `cache-dependency-path: poetry.lock`
- [ ] push + 触发 deploy（需用户批准；workflow 改了强制）
- [ ] SSH runner host 做基础健康检查（需用户执行）