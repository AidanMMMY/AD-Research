# gitleaks 误报阻断部署与生产 E2E 验收（2026-10-25）

> 事件：`ee22869`（首登强制改密）等 6 个 commit push 后部署被 secrets-scan 误报阻断并自动回滚；修复后重新部署成功，并在生产完成改密功能全链路验收。
> 关联：[Tripwire #6](20260719-deploy-tripwires.md)、[首登强制改密与统一密码策略](20261024-first-login-password-policy.md)、[模型切换交接](20261025-model-switch-handoff.md)

## 1. 事件时间线（全部有实证）

| 时间 (+08) | 事件 | 证据 |
|---|---|---|
| 10-25 02:36:06 | `c0a8ce1` 提交并 push（6 commit 一次推） | 本地 git；ECS origin/main 引用 |
| 02:36:26 | deploy run 40121472239 启动 | runner `_diag/Worker_20261024-183626-utc.log` |
| 02:36:28 | Sync 成功，/opt 已 reset 到 c0a8ce1 | Worker 日志 Step result: Succeeded；deploy-failures.log 记 current_head=c0a8ce1 |
| 02:36:39 | CI Gate 中止（仅 ~11s，非等待超时） | Worker 日志 Step result: Failed |
| 02:36:39–02:37:02 | 自动回滚：reset 回 `a89a03e`，旧镜像重建 4 容器 | rollback-20261025-023639.log；容器 StartedAt |
| 02:37:25 | job Failed 结束 | deploy-failures.log 末条 |

## 2. 根因

- secrets-scan 的 gitleaks 以 `generic-api-key` 规则标记 `app/tests/test_user_password_scripts.py:19` 的夹具常量 `NEW_PASSWORD`（15 字符形如 `N3w-…123` 的高熵串，原文见 commit `ee22869`）。本地 gitleaks 8.30.1 复扫同范围（`a89a03e..c0a8ce1`）确认 6 commit 中**唯一命中就是这一行**。
- [ci_gate.sh](../../scripts/ci_gate.sh) 语义「任一 failure check run → 中止部署」，与 secrets-scan 联动构成硬阻断；gitleaks 出结论快（<30s），门禁首轮查询即翻红。
- 排除项（当时的取证结论）：非脏工作树（Sync 已成功）、非 update.sh（deploy-latest.log 未更新，说明根本没跑到）、非迁移问题。
- 其余 CI（Web lint/build、a11y、Backend pytest、Ruff）在 c0a8ce1 上全绿——独立佐证上会话本地验证记录。

## 3. 修复（commit `212a9ec`，2026-10-25 push 并部署成功）

| 文件 | 改动 |
|---|---|
| `app/tests/test_user_password_scripts.py:19` | 行尾加 `# gitleaks:allow` 内联豁免（gitleaks 官方机制，夹具值不动） |
| `scripts/reset_user_password.py:11` | docstring 示例 `'N3w-passw0rd123'` → `'<NEW_PASSWORD>'`（同款字符串除患） |

验证：pytest 该文件 4 passed；ruff 通过；`gitleaks detect --log-opts="c0a8ce1..212a9ec"` = no leaks found。03:08 deploy **success**（gitleaks/Ruff/Backend pytest 全绿）。

## 4. 部署落地验证（03:09，SSH 只读核查）

- `/opt/ad-research` HEAD 与 backend 容器 `GIT_SHA` 均为 `212a9ec`
- `/health` status=ok（db/redis/scheduler/data 全 ok）
- alembic `current` = `b3c5d7e9f1a2`（head），迁移已应用
- `users.must_change_password` boolean NOT NULL default false 已建列

## 5. 生产 E2E 验收（公网 https://www.alloyresearch.net 实测，6/6 通过）

| # | 步骤 | 期望 | 实测 |
|---|---|---|---|
| 1 | 容器内按模型建测试用户（`must_change_password=True`）→ 登录 | 200，`user.must_change_password=true`，返回双令牌 | ✅ |
| 2 | `GET /auth/me`（access） | 200 且 flag=true | ✅ |
| 3 | `GET /pools`、`GET /stocks`（access，待改密） | **403**（不是 401，防 axios 误判过期触发 refresh） | ✅ 均为 403 |
| 4 | `POST /auth/change-password`（旧密码+新密码） | 200 且返回新 access/refresh | ✅ |
| 5 | 新 access 访问 `/pools`、`/auth/me` | 200；flag=false | ✅ |
| 6 | 旧 refresh token 再刷新 | 401（已吊销） | ✅ |

验收后测试用户与其 refresh token 已从生产库删除（DELETE 2 + DELETE 1，复核 remaining=0），本地令牌/密码临时文件已清理。

## 6. 沉淀口诀

- **deploy 秒败（<1 分钟）且日志出现 Rollback** → 先看 `/var/log/ad-research/deploy-failures.log` + runner `_diag/Worker_*.log` 的 Step result 时间戳，再查 GitHub check-runs（仓库公开，未 gh auth 也能 curl）。
- **写密码/密钥类测试夹具**：要么低熵形态，要么当场 `# gitleaks:allow`；提交前 `gitleaks detect --log-opts="<上次push>..HEAD"` 本地复扫。
- **取证优先级**：deploy-failures.log（previous/current head）→ rollback-*.log → Worker 日志（步骤级成败+秒级时间）→ check-runs API。四步内必达根因。
- gitleaks 已本地安装（brew，8.30.1）。
