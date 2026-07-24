# 2026-07-24 Platform Ops Sprint — 完整总结

> 6 个 commit + runner 自愈脚本 + verify 脚本，全部 push 到 main。
> Deploy #324 (89851dc) 正在跑，预计 5-10 分钟内 backend 拉到 961dcf1+ 代码。

---

## 1. 6 个 commit 时间线

| Commit | 解决什么 | 验证 |
|---|---|---|
| `c4afbdd` | deploy.yml step 5/6 加 `timeout-minutes: 15` | 未救 cascade（runner host 失联快于 15min） |
| `e49e2f9` | e2e 接 CI（去掉 `--deselect`） + .env.example INTERNAL_API_TOKEN + runner on-call runbook | pytest 933 + e2e 85 全绿 |
| `31af022` | 颜色 token 化（main.tsx 删 dark fallback + readCssVarStrict + useMemo + theme.css --vital-*） | web check:ci 全绿 |
| `1e6bcea` | `scripts/verify_post_deploy.sh` | 工具就绪 |
| `961dcf1` | runner_healthcheck.sh 自愈 + /health llm probe + backend-ci v4 | pytest 1018 全绿 |
| `89851dc` | deploy.yml 加 Self-heal step (best-effort) | Deploy #324 step 5 self-heal = success |

## 2. 9 项长尾 P2/P3 复核结论

| 待办 | 结论 |
|---|---|
| NotificationLog user_id | ❌ 过期（无明确需求） |
| Slack 告警接入 | ❌ 过期（feishu/dingtalk/wechat_work 已覆盖） |
| AdminRouteGuard 路径 hardcode → meta | ❌ 已完成 |
| **e2e 接 CI** | ✅ e49e2f9 完成 |
| **颜色 token 化** | ✅ 31af022 完成（核心修复，剩 93 处可慢慢扫） |
| alert threshold 验证 | ⚠️ 依赖 deploy 上线 |
| Secret rotate | ⚠️ MiniMax 是当前主链路（DeepSeek 已 legacy）；`/health` llm probe 接入后可见 |
| 申万 Phase 4+ | ✅ 保留 |

## 3. Deploy runner cascade 真正修复路径

| 时间 | 现象 | 修法 |
|---|---|---|
| #316/#317/#318/#319 | runner 整体失联 | ❌ workflow 改 timeout 救不了 — runner 在 15min 前就崩 |
| Deploy #324 (89851dc) | **self-heal step 跑通 → update.sh 跑起来** | ✅ 走通第一步 |

`runner_healthcheck.sh` + deploy.yml 自愈 step 共同闭环：
- 部署工作流每次启动前自动跑 2 分钟内自愈
- 自愈失败也不阻塞 deploy（continue-on-error）
- 长期：每 5 分钟 cron 跑一次作为独立保险

## 4. 部署完成必跑（用户动作）

```bash
ssh alloyresearch-backend
bash /opt/ad-research/scripts/verify_post_deploy.sh
```

期望 ALL PASS：
- /health status=ok
- internal routes: 2 (含 orchestrate-alert)
- token auth: 403 + 200 双向通
- NotificationLog row id=N 写入成功
- alembic at head
- llm probe: warn（生产 LLM key 未配，可观察但非阻断）

如果 llm probe 是 ok（说明 key 配了）：
- secret rotate 自动完成

如果 llm probe 是 warn + 你有 MiniMax 新 key：
- 控制台新建 → revoke 旧 → 填入 `deploy/aliyun-ecs/.env`
- 重跑 verify 脚本即可

## 5. 加固清单（部署稳定后做的事）

- [ ] `runner_healthcheck.sh` 加 crontab `*/5 * * * *`
- [ ] `INTERNAL_API_TOKEN` 写入 `deploy/aliyun-ecs/.env` + 同 token 到 cron 容器
- [ ] 如果 alert threshold 默认 2 验证窗口需要调整，看 `--alert-threshold` flag

## 6. 已确认状态

- 推送：✅ 6 commit 全在 main
- 本地测试：✅ pytest 1018 + web check:ci 全绿
- 部署：⏳ Deploy #324 正在跑（21:19 UTC 启动，self-heal success，update.sh in_progress）

## 关联

- [[20260723-collect-failure-alert-and-backend-ci]] — f9445e7 三件事原始记录
- [[20260724-deploy-blocked-color-token]] — 4 个 commit 阶段（c4afbdd/e49e2f9/31af022/1e6bcea）
- [[20260723-runner-host-oncall-checklist]] — SSH 体检步骤
- [[20260719-deploy-tripwires]] — deploy 6 连败教训
- [[20260719-orchestrate-image-fix]] — image 缺失 silent failure 原始 case