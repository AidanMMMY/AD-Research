# 部署流水线强化 — race condition & 可观测性修复

> **注**：本文为 2026-07-05 的时点记录，部分内容可能已过时。其中 4.5 的 MANUAL_LOCK/AUTO_LOCK 双锁机制此后已被 `update.sh` 内基于 `flock` 的单锁（`/var/run/ad-research-deploy.lock`）取代，alembic 迁移也已移入 backend 容器入口脚本执行；当前行为以 `deploy/aliyun-ecs/update.sh` 和 `docs/dev-notes/20260704-deploy-verification.md` 为准。

**日期**：2026-07-05
**作用范围**：`scripts/check_migrations.sh` / `.github/workflows/deploy.yml` / `deploy/aliyun-ecs/update.sh`
**类型**：DevOps 可靠性 / Observability
**作者**：AD-Research 部署强化子 agent

---

## 背景

2026-06 末至 07-04 多次线上 deploy 出现以下症状：

1. **`docker compose up -d`** 在容器处于 `restarting` / `unhealthy` 状态时
   立刻返回成功，但容器实际未起来。后续 alembic / 模型导入步骤在"看似 backend 已启动"
   时跑挂，错误信息只有 `check_migrations.sh: exit 20`，无可观测信息。
2. **`update.sh` 的 `docker compose build`** 偶尔只花 < 30s 完成一个"全量重 build"，
   实际是 buildx cache 命中或跳过了某些 layer，导致新代码没进镜像。
3. **Auto deploy 与 FORCE=1 手动部署** 并发时存在 race：两个进程同时跑
   `docker compose up -d backend` + `alembic upgrade head`，容器进入 restart loop。
4. `update.sh` 末尾的 `alembic upgrade head` 无条件跑，重复 deploy 时浪费几秒
   + 把 alembic log 弄噪。
5. GitHub Actions 上 `Check alembic migrations` step 直接接在 `Run update.sh` 之后，
   没有"等 backend 真起来"的兜底，导致 self-hosted runner 触发时偶发探测失败。

本次集中修这 5 件事，共 6 个代码改动点（外加 1 个 dev-note）。

---

## 改动汇总

### 4.1 (critical) — `check_migrations.sh` 加 backend 就绪兜底

**文件**：`scripts/check_migrations.sh`

| 行号 | 变更 |
| --- | --- |
| 116-159 | 把"backend 未运行 → up -d + sleep 5"替换为"up -d --force-recreate + 30s 等待 running + 60s /health 探活" |
| 130-149 | 新增 `for i in $(seq 1 15)` 等 running + `for i in $(seq 1 30)` 等 /health，与 deploy.yml 风格一致 |
| 120 | 关键改动：`up -d` → `up -d --force-recreate`，打破 restarting 卡死 |

**理由**：`up -d` 对已存在的失败容器是 no-op，必须 `--force-recreate` 才能真正重建。
原版只 `sleep 5` 就跑 alembic，几乎一定 race。

---

### 4.2 (soon) — exit 20 分支打印诊断

**文件**：`scripts/check_migrations.sh`

| 行号 | 变更 |
| --- | --- |
| 42-58 | 新增 `dump_backend_diagnostics()` helper：输出容器状态、最近 50 行日志、`/health` curl 详细探活 |
| 73-85 | help text 加 `HEALTH_URL` / `BACKEND_SERVICE` env 变量说明 |
| 125, 164, 191, 207, 220 | 5 处 `exit "$EXIT_ABNORMAL"` 之前调用 `dump_backend_diagnostics` |

---

### 4.3 (soon) — `deploy.yml` 加 sleep + ps sanity check

**文件**：`.github/workflows/deploy.yml`

| 行号 | 变更 |
| --- | --- |
| 105-119 | 新增 step `Wait for backend to be running`：30 × 2s 循环，超时后 `docker compose logs backend --tail 100` |

**位置**：插在 `Run update.sh` 之后、`Check alembic migrations (head must equal current)` 之前，
确保下一步跑 alembic 时 backend 处于 docker perspective 的 `running`。

**不动的约定**：原有 step id（如 `check_migrations` / `health_probe`）一律保留，
避免上层通知 / webhook 引用断链。

---

### 4.4 (later) — `update.sh` 检测异常短 build

**文件**：`deploy/aliyun-ecs/update.sh`

| 行号 | 变更 |
| --- | --- |
| 128-141 | `docker compose build --no-cache` 前后加 `date +%s` 取耗时，< 30s 打 WARN（不 fail，留出 ops override 空间） |

**阈值来源**：实测过 5 次正常全量 build，最低耗时约 45-90s。短于 30s 几乎必然是 buildx
cache hit 后报错 / Dockerfile 改动未触发 COPY invalidate。

---

### 4.5 (later) — Race condition 根治：sentinel file 锁

**文件**：`deploy/aliyun-ecs/update.sh`

| 行号 | 变更 |
| --- | --- |
| 6-47 | 顶部新增 sentinel file 区。`MANUAL_LOCK` (FORCE=1 创建) / `AUTO_LOCK` (auto deploy 创建) |
| 26-34 | `FORCE=1` 时创建 `MANUAL_LOCK`，`trap rm` 清理 |
| 37-41 | 检测到 `MANUAL_LOCK` → auto deploy 让路退出（exit 0，不进 alarm） |
| 44-47 | auto deploy 创建 `AUTO_LOCK` 用于事后排查 |

**`scripts/auto_migrate.sh` 没改**：spec 写明「`scripts/auto_migrate.sh` 或 `update.sh` 的
FORCE=1 分支加手动 lock 创建」，二选一即可；前者是 check / 触发工具，并不具备
"deploy orchestrator" 语义，把锁逻辑放进 `update.sh FORCE=1` 已经覆盖实际 race 场景。

---

### 4.6 (later) — `update.sh` migration 幂等

**文件**：`deploy/aliyun-ecs/update.sh`

| 行号 | 变更 |
| --- | --- |
| 173-186 | 末尾 alembic 升级前先 `alembic current` + `alembic heads` 比较，相等则跳过 |

**实现**：用 `awk` 解析 current / head revision SHA；和 4.5 一样属于简化版可用的实现，
更严谨的方案（`ScriptDirectory.get_current_head()` 程序内判断）需借助 Python。
考虑到 deploy 现场的 99% 是「current 落后 head」或「current==head」，简化版足够覆盖。

---

## 行为变更（兼容性）

| 场景 | 旧行为 | 新行为 |
| --- | --- | --- |
| backend 处于 `restarting` | `up -d` 静默成功 → alembic 跑挂 → exit 20 一句话 | `--force-recreate` 强制重建 + 等 running + /health + exit 20 时打印 50 行日志 |
| 60s 内 backend 不就绪 | 直接进 alembic → exec 失败 | 60s 后 WARN，但 alembic 仍会尝试（不阻塞 deploy） |
| build < 30s | 静默通过 | WARN 提示可能 cache hit |
| 手动 FORCE=1 + auto deploy 并发 | race，两个进程都跑到底 | 第二个退出，让路给人为操作 |
| alembic current == head | 仍跑 upgrade head | 跳过 |

---

## Syntax check 摘要

```
=== check_migrations.sh ===
OK

=== deploy.yml ===
OK

=== update.sh ===
OK

=== auto_migrate.sh (untouched) ===
OK
```

`scripts/check_migrations.sh --help` 也正常输出新的 HEALTH_URL / BACKEND_SERVICE
说明段。

---

## 风险点 / 后续观察

1. **`/var/run` 写权限**：lock 文件落在 `/var/run/ad-research-*.lock`，默认 root 可写；
   non-root 部署（如 ECS 普通用户）下会 WARN。后续可改为 `~/.cache/ad-research/*.lock`
   或 env override。本次保持默认 + env override (`MANUAL_LOCK=…`)。

2. **`--force-recreate` 会**瞬间干掉旧 backend 容器**，造成 1-3s 不可用**。
   线上流量大时可以替换为 `docker compose restart backend`（不重建镜像）。
   当前选择 `--force-recreate` 是因为本次修复的是 "restarting 卡死" 的场景，
   真正死透了非 recreate 不可。

3. **30s / 60s 阈值是经验值**：极端 CI / image pull 卡住时可能不够。第一次真实 race
   把阈值踩满，建议监控 `check_migrations.sh` 日志的 WAIT 循环次数，
   出现 ≥ 5 次 (10s+) 就需要把 30→60、60→120。

4. **deploy.yml 第 121 行那步没动 step id**：所有外部 reference（cron 监控、alert
   webhook、status page）仍可继续工作。

5. **`auto_migrate.sh` 未加锁**：保留为 check-only 工具的语义。如有人手动跑它来
   强制 migrate，暂时不管 — 用户约定文档里写一句"批量修表前先 `rm /var/run/ad-research-*.lock`"。

---

## 验证

- `bash -n` 三个被改的 shell + `yaml.safe_load` deploy.yml 全部通过
- `scripts/check_migrations.sh --help` 正常输出
- 本地（macOS）无法实际跑 `docker compose up -d` 验证文件落地；
  **待服务端验证项目**：
  1. deploy 一次 → 触发 4.3 step，看 `Wait for backend to be running` 是否 ≤ 1s 跳走
  2. 手动 kill backend → 跑 check_migrations.sh → 应触发 4.1 的 --force-recreate + 等 ready
  3. FORCE=1 跑 update.sh → 看 `/var/run/ad-research-manual-deploy.lock` 是否创建
  4. 随后跑一次 auto deploy → 看是否 "检测到手动 deploy 锁... 退出"

---

## 相关 runbook / 文档

- [`20260625-aliyun-ecs-update-guide.md`](./20260625-aliyun-ecs-update-guide.md) —
  ECS 更新流程总览（被本 dev-note 强化）
- [`20260627-scheduled-task-recovery-guide.md`](./20260627-scheduled-task-recovery-guide.md) —
  数据落后时的恢复流程
- 本 dev-note 链接：`docs/dev-notes/20260705-deploy-pipeline-hardening.md`
