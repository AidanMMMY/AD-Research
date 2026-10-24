# commit→push→CI→ci_gate→部署→落地验证 全链路审计（2026-10-25）

> 审计 agent 一次性产物。范围：本地提交前规则、push 触发、GitHub CI 门禁、
> ci_gate 语义、ECS 部署链参数、落地验证层、环境参数完备性、知识库覆盖。
> 关联：[gitleaks 阻断事故](20261025-gitleaks-deploy-block-and-e2e.md)、[deploy-tripwires](20260719-deploy-tripwires.md)
>
> 审计基线：HEAD 6047e04。注意：审计开始时快照为「本地领先 origin/main 若干
> commit 待 push」，审计过程中 origin/main 已同步到 6047e04（`git rev-parse
> origin/main` == HEAD，本审计未做任何 push）。

## 0. 全链路一图流（现状）

```
本地（无 pre-commit 钩子，全靠成文习惯）
  └─ git commit ──→ git push origin main
       ├─ secrets-scan.yml  gitleaks 全历史扫描（PR + push main，无 paths 过滤）
       ├─ backend-ci.yml    pytest(≈1064,15min) + ruff（paths: app/alembic/scripts/pyproject/poetry.lock/self）
       ├─ web-ci.yml        lint+tsc+build + a11y（paths: web/**）
       └─ deploy.yml        self-hosted runner，/opt/ad-research：
            1 Sync       rotate-log 备份 previous_head(留10) → fetch --all --prune
                        → porcelain 脏树即败 → reset --hard origin/main
            2 ci_gate    check-runs 轮询 90×10s≈15min；无 check=放行/有失败=中止/否则等待
            2.5 baseline /health 记录基线
            2.7 runner_healthcheck.sh 自愈（best-effort, 2min）
            3 update.sh  flock 互斥 → docker build --no-cache(GIT_SHA 打标, tag
                        ad-research:<sha>+latest) → <30s build 警告 → 停旧容器+孤儿清理
                        → up -d(force-recreate) → 容器内 /health body status=ok
                        等待 300s(150×2s) → alembic current==head 只读校验 →
                        旧镜像清理(只留 sha+latest, cache 72h+)   [外层 retry ×2, 15min/次]
            3.5 smoke    容器内 import app + alembic current + /health body + openapi.json
            4 迁移校验    check_migrations.sh（0=OK /10=需迁移 /20=异常）
            5 health     30×2s 容器内探测
            6 失败回滚    rollback.sh previous_head（镜像 tag 复用或重建 + 60s 健康）
            7 成功摘要    previous..current git log
       失败/成功 → webhook + /var/log/ad-research/deploy-failures.log
落地验证（人工）：/opt HEAD vs 容器 GIT_SHA vs /health vs alembic；
  verify_post_deploy.sh（internal 路由 + INTERNAL_API_TOKEN 双向 + llm probe）
```

## 1. 环节表

### 1.1 本地提交前

| 规则/参数 | 现状 | 证据 | 评估 |
|---|---|---|---|
| black line-length 100 | 成文 | pyproject.toml:57-58 | ✅ |
| ruff 0.8.x，rule 集 E,F,W,I,N,UP,B,C4,SIM，忽略 E501 + per-file-ignores | 成文 | pyproject.toml:61-90 | ✅（CI ruff==0.8.6 与本地对齐，backend-ci.yml:180） |
| 提 PR 前本地 pytest + tsc + vite build | 成文（AGENTS.md §6） | AGENTS.md | ⚠️ 仅约束直推 main 之外的 PR；本仓库常态是直推 main |
| gitleaks 预扫 `detect --log-opts="<上次push>..HEAD"` | 成文口诀（tripwire#6 防御段） | 20260719-deploy-tripwires.md:231-233；gitleaks 8.30.1 已 brew 本地 | ⚠️ 是习惯非强制，漏跑的代价=push 后 11 秒中止+自动回滚（10-25 实测） |
| staged diff 独立审查 | 纯习惯，未成文 | — | ⚠️ 无任何文档提及 |
| pre-commit 钩子（任何形式） | **不存在** | 无 .pre-commit-config.yaml、无 .husky（实测 ls） | ❌ ruff/black/gitleaks/pytest 全部只在 CI 或人工触发；secrets 的第一道防线后置到 push 后 |

**建议**：① 引入 pre-commit 框架 + gitleaks hook（`--staged` 秒级，是性价比最高的一道）；② 至少先把「提交前 gitleaks 复扫 + staged diff 自查」写进 AGENTS.md §6 成文清单；③ black/ruff 可留给 CI（已有硬门禁），不强求本地钩子。

### 1.2 push 触发（逐 workflow）

| workflow | on 触发 | paths | 证据 | 评估 |
|---|---|---|---|---|
| secrets-scan | PR(全) + push main | **无过滤** | secrets-scan.yml:7-10 | ✅ 合理：secret 可经任意路径进来，且 PR 全历史扫描（fetch-depth:0）；缺点：无 timeout-minutes（默认 360min），P3 |
| backend-ci | PR + push main | app/**, alembic/**, scripts/**, pyproject.toml, poetry.lock, self | backend-ci.yml:22-39 | ❌ 漏了 `agent/**`、`research/**`（ruff 明明 lint 这两个目录，backend-ci.yml:183，但只改它们不触发任何 CI）、`Dockerfile`、`deploy/**`——Dockerfile/compose 改动零门禁直上生产 |
| web-ci | PR + push main | web/** | web-ci.yml:4-10 | ✅（前端只依赖 web/**；npm ci 以 web/package-lock.json 为准） |
| deploy | push main + workflow_dispatch(ref/skip_migrations/dry_run) | **无过滤** | deploy.yml:6-22 | ⚠️ docs-only push 也全量 no-cache 重建+重建 4 容器（分钟级中断）。但**不建议**简单加 paths-ignore：c0c5e8d 事件证明 GitHub 事件本身会丢，过滤越多越难发现"该跑没跑"；且每次 push 同步 /opt 是兜底价值。若要优化，应做成"docs-only 只 Sync 不 rebuild"的 dry_run 分支 |
| 事件丢失防御（c0c5e8d push 零触发） | **无任何检测/防御** | 10-25 实录：c0c5e8d push 后 deploy/secrets-scan（均无 paths 过滤、本应必触发）零 run | ❌ P2 | 建议：push 后 2min 人工/脚本核对 check-runs 非空；或加每 30min 的 watchdog workflow：比较 origin/main HEAD 与最近一次 deploy run 的 head_sha，漂移+无进行中 run 即告警。兜底判断：SSH 看 /opt 是否已 Sync 到该 SHA，或再推一次空 commit |

### 1.3 CI 门禁（ci_gate）

| 参数 | 值/语义 | 证据 | 评估 |
|---|---|---|---|
| 轮询 | 90 次 × 10s ≈ 15min 超时中止 | ci_gate.sh:23-36 | ✅ 语义正确：无非 deploy check=放行（docs-only）；任一 failure/cancelled/timed_out/action_required/startup_failure=中止；否则等待 |
| 端点 | `/commits/{sha}/check-runs`（不是 /statuses） | ci_gate.sh:14-15 注释 | ✅ 正确（Actions 产生 check run，combined status 永远为空——8/21 已踩过） |
| SELF_NAME 过滤 | 名字含 "deploy" 的 check run 排除 | ci_gate.sh:21, ci_gate_parse.py:20-22 | ⚠️ 子串匹配：将来任何 job 名含 "deploy" 的 check（如 deploy-check）失败会被静默豁免。P3 |
| API 错误处理 | curl 不带 -f；错误响应 JSON（401/403/404）无 check_runs 键 → `d.get("check_runs",[])` → runs=[] → **"success" 放行** | ci_gate_parse.py:18-29 | ❌ P2：token 失效/repo 改名/SHA 不存在时门禁静默打开。建议校验 `total_count` 字段存在或 HTTP 状态 |
| 零 check 立即放行 | 首轮查询若事件尚未注册 check run（GitHub 延迟）→ 秒判 success | 同上 | ⚠️ P3：与"事件丢失"叠加时等于未验证先部署。可要求前 N 轮连续非空或最小等待 60s |
| GITHUB_TOKEN | secrets.GITHUB_TOKEN（self-hosted） | deploy.yml:104-105 | ✅ 同仓库读权限足够 |
| timeout 层级 | job 45min（deploy.yml:35）；ci_gate 步骤无显式 timeout（自身≈15.5min 封顶）；update ×2 各 15min（deploy.yml:143,173）；smoke 5min | deploy.yml | ❌ P2：最坏路径 gate 15.5 + self-heal 2 + update1 15 + 30s + update2 15 ≈ **48min > 45min**——job 被 timeout 取消时 `if: failure()` 的 Rollback 步骤**不会执行**（取消≠failure）。建议重排预算（如 update 两次共享 15min 窗）或 job timeout 提到 60min |

### 1.4 部署链参数

| 环节 | 参数 | 证据 | 评估 |
|---|---|---|---|
| concurrency | group=aliyun-deploy, cancel-in-progress=false | deploy.yml:32-34 | ✅ 部署严格串行 |
| Sync 三步 | rotate-log 备份 previous_head（留 10 份）→ fetch --all --prune → TARGET_REF 校验 → porcelain 脏树 loud bail → reset --hard | deploy.yml:48-89 | ✅ 完备（tripwire#5 语义保留，Action-253 未提交变更不再被静默 clean） |
| 镜像打标 | GIT_SHA build-arg → `ad-research:${GIT_SHA}` + retag latest | update.sh:131-133,161-168；Dockerfile:52-53；compose:113-115 | ✅ /health 可报精确 commit |
| build 异常检测 | <30s 警告"可能未真正重建" | update.sh:169-176 | ✅（配合 --no-cache 每次全量重建，语义自洽） |
| 互斥 | flock /var/run/ad-research-deploy.lock 非阻塞 | update.sh:75-96 | ✅ |
| 健康窗 | 300s（150×2s）容器内 /health body `status=ok`（不再只看 HTTP 200） | update.sh:221-256；compose:128-139（start_period 240s） | ✅ 覆盖 alembic 大列 ALTER 实测 ~5min |
| 迁移校验 | entrypoint 是唯一 upgrade 执行点；update.sh 与 deploy.yml 双层只读校验 current==head | update.sh:261-279；check_migrations.sh:42-44,186-197；deploy.yml:242-272 | ✅ 分层冗余合理（退出码 0/10/20 语义清晰） |
| 孤儿容器清理 | `--filter label=com.docker.compose.project=alloyresearch` | update.sh:196-205 | ❌ **P1：标签疑似不匹配**。compose 无顶层 `name:`，项目名默认取目录名 `aliyun-ecs`（runner_healthcheck.sh:47 也用 aliyun-ecs 并注释 v2 自动打 aliyun-ecs 标签）→ update.sh 这条过滤很可能匹配 0 个容器，tripwire#4 的孤儿清理防御**静默 no-op**。需 ECS 上 `docker inspect alloyresearch-backend --format '{{index .Config.Labels "com.docker.compose.project"}}'` 实证后修正 |
| 旧镜像清理 | 每次成功后只留 `${GIT_SHA}`+latest，其余 ad-research:* 全删；builder cache 只清 72h+ | update.sh:281-293 | ✅ 磁盘事故后加固到位。⚠️ 副作用：**previous_head 的镜像必然已被删**，自动回滚走"重建旧 commit"慢路径（分钟级）而非秒级换 tag——可接受的取舍，但排障时要有预期（P3 记录） |
| rollback | previous_head 读取（rotate-log 符号链接）→ tag 复用或重建 → 重启 backend+indicator+cninfo+nginx → 60s 健康 | rollback.sh:157-180,183-209；deploy.yml:303-330 | ✅（worker 名已修过一次，现在对） |
| retry | update.sh 外层 attempt 2/2，间隔 30s（阿里云 HTTP/2 registry 抖动） | deploy.yml:130-187 | ✅ 针对性强；见 1.3 超时预算问题 |
| 落地验证 | smoke（import+alembic+/health body+openapi）+ verify_post_deploy.sh（internal 路由/token 双向/llm probe）+ tripwires 尾部验证清单 | deploy.yml:190-215；scripts/verify_post_deploy.sh | ✅ 分层充分；verify_post_deploy 是手动脚本，未挂进 deploy.yml（可选 P3） |

### 1.5 环境参数完备性

| 项 | 现状 | 证据 | 评估 |
|---|---|---|---|
| AUTH_REGISTRATION_ENABLED / FRONTEND_BASE_URL | 根 .env.example 已登记（106-112）；config 默认关/localhost:5173 | .env.example:106-112；app/config.py:271,330 | ❌ **P1 三处缺二**：① deploy/aliyun-ecs/.env.example 无这两个键；② **deploy compose `x-backend-env` anchor 根本不透传**（docker-compose.yml:4-40 无此二键）——即使生产 .env 配了，容器也看不到。后果：注册功能在生产打开需要改 compose；魔法链接若在 anchor 修好前误开会指向 http://localhost:5173 |
| LLM 切换链（LLM_PROVIDER_CHAIN/GLM_*/KIMI_*/COOLDOWN） | 根 .env.example 齐全（54-78） | deploy/.env.example:54-65（只有 minimax/deepseek 旧文案）；compose anchor 无 GLM/KIMI/CHAIN 键 | ❌ P2：2026-09-28 上线的切换链没接进生产 compose/example——"GLM/KIMI key 至今未配"的根因之一就是生产侧根本没有落点。单点 MiniMax 风险仍在 |
| BLS_API_KEY | compose 透传（:27），生产 .env 在用；**两个 .env.example 都没有** | docker-compose.yml:27 | ❌ 登记漏 |
| CORS_ORIGINS / ENABLE_SCHEDULER / GITHUB_TOKEN / GITHUB_REPO / JINA_API_KEY | 根 example 有（部分）；deploy example 全缺（生产 .env 实配 CORS/ENABLE_SCHEDULER/XUEQIU 等） | deploy/.env.example vs deploy/.env 键名清单 | ❌ deploy example 长期滞后，违反「env key 双登记」口诀（20260729 教训） |
| INTERNAL_API_TOKEN | 两 example + compose anchor 三处齐全 | .env.example:174-183；deploy/.env.example:68-76；compose:35 | ✅ 事故教训已闭环 |
| 镜像内容物 | 只 COPY app/ + alembic/ + alembic.ini + scripts/docker-entrypoint.sh + scripts/seed_users.py | Dockerfile:85-93 | ❌ P2：**scripts/ 其余全不进镜像**——create_user.py / reset_user_password.py / recalculate_scores.py 等容器内不存在（10-25 E2E 只能"按模型建测试用户"绕过）。建议整体 COPY scripts/（体积可忽略，ruff 已有门禁）或文档化「docker cp 进容器再跑」 |
| .env.example GITHUB_REPO 示例 | 写的 `AidanMMMY/ad-research` | .env.example:121-122 | ⚠️ 实际是 `AidanMMMY/AD-Research`，nit |
| TLS 私钥仍在 git | `deploy/aliyun-ecs/ssl/www.alloyresearch.net.key` 被 track | git ls-files | ❌ 既有 CRITICAL（20260817 已识别，重签+filter-repo 待执行），此处挂账不展开 |

### 1.6 知识库（vault）覆盖

| 项 | 审计前状态 | 动作 |
|---|---|---|
| 30-Architecture pipeline 全链路图 | **目录为空** | 已补《commit→push→CI→deploy 全链路图》（含参数速查表） |
| 20-Runbooks/_index.md 今日新文档 | gitleaks 复盘、tripwires#6、model-switch-handoff 均已索引 ✅ | 只追加本次审计报告条目 |
| 50-Reviews/_index.md 今日文档 | 缺 self-registration-design / backend-health-survey / frontend-health-survey / redundant-modules-workload-review | 已追加 4 条 + 本次审计 |
| 60-Lessons「密码夹具二次案例」口诀 | **已有**（部署.md 第 22 行，含"文档引用字面量二次触发"） | 无需补 |
| 60-Lessons push 零触发判断法 | 缺 | 已补 |
| 60-Lessons 镜像只含 app/ | 缺 | 已补 |
| 60-Lessons env 三处同步 | 缺（只有"双登记"半句） | 已补 |

## 2. 缺口分级清单

### P1（建议主会话尽快处理）

1. **compose anchor 不透传新 env + deploy/.env.example 缺键**：`FRONTEND_BASE_URL`、`AUTH_REGISTRATION_ENABLED`（docker-compose.yml x-backend-env），顺带补 GLM/KIMI/CHAIN、BLS_API_KEY、CORS_ORIGINS、ENABLE_SCHEDULER、GITHUB_TOKEN/REPO、JINA_API_KEY 到 deploy/.env.example。否则邮箱注册功能（0e161d4）生产不可用/魔法链接指向 localhost。
2. **update.sh 孤儿清理 compose project 标签不匹配**（alloyresearch vs aliyun-ecs，update.sh:201）——先 ECS 实证标签值再修；这层是 tripwire#4 的防御，静默失效比没有更危险。
3. **TLS 私钥仍在 git**（既有挂账，借本次审计重申优先级）。

### P2

4. **ci_gate API 错误被当"无 check"放行**（ci_gate_parse.py:18-29）——校验 `total_count`/HTTP 码，防 token 失效/repo 改名时门禁洞开。
5. **push 事件丢失无检测**（c0c5e8d 零触发）——watchdog workflow 或 push 后 check-runs 核对习惯（口诀已入 vault）。
6. **deploy 超时预算 48min > job 45min**，双 update 失败的边界会跳过自动回滚（deploy.yml:35,143,173）。
7. **镜像缺 scripts/**（Dockerfile:85-93）——COPY scripts/ 或文档化替代。
8. **backend-ci paths 漏 agent/**、research/**、Dockerfile、deploy/**（backend-ci.yml:22-39）——ruff lint 的目录与触发目录不一致。

### P3

9. 引入 pre-commit（gitleaks hook 优先）；AGENTS.md §6 成文化提交前清单（gitleaks 复扫 + staged diff 自查）。
10. ci_gate SELF_NAME 子串匹配收严为全等；首轮零 check 立即放行的竞态（最小等待窗）。
11. secrets-scan 加 timeout-minutes；verify_post_deploy.sh 挂进 deploy.yml 成功路径（可选）。
12. 回滚走重建慢路径的预期管理（旧镜像保留策略的已知副作用，写进 runbook 即可）。
13. .env.example GITHUB_REPO 示例改成 AD-Research（大小写）。

## 3. repo 侧待主会话处理的建议清单（本审计不改代码）

- [ ] deploy/aliyun-ecs/docker-compose.yml：x-backend-env 补 FRONTEND_BASE_URL / AUTH_REGISTRATION_ENABLED / LLM_PROVIDER_CHAIN / LLM_PROVIDER_COOLDOWN_SEC / GLM_API_KEY / GLM_BASE_URL / GLM_MODEL / KIMI_API_KEY / KIMI_BASE_URL / KIMI_MODEL
- [ ] deploy/aliyun-ecs/.env.example：按根 .env.example 补齐上述 + BLS_API_KEY / CORS_ORIGINS / ENABLE_SCHEDULER / GITHUB_TOKEN / GITHUB_REPO / JINA_API_KEY（保持「双登记」纪律）
- [ ] scripts/ci_gate_parse.py：非 2xx 或缺 total_count → retry/abort 而非 success
- [ ] deploy/aliyun-ecs/update.sh:201：compose project 标签修正（先实证：docker inspect … compose.project）
- [ ] .github/workflows/deploy.yml：重排超时预算（update×2 共享窗口或 job 60min）
- [ ] .github/workflows/backend-ci.yml：paths 补 agent/**, research/**, Dockerfile, deploy/aliyun-ecs/**, .github/workflows/backend-ci.yml（self 已有）
- [ ] Dockerfile：COPY scripts/ ./scripts/（或至少 create_user.py / reset_user_password.py）
- [ ] AGENTS.md：§4 补「新 Settings env 键三处同步（根 example + deploy example + compose anchor）」；§6 补提交前 gitleaks 复扫与镜像内容物说明
- [ ] （既有挂账）TLS 私钥 filter-repo 清历史

## 4. vault 补漏（本次已写入）

| 路径 | 内容 |
|---|---|
| `30-Architecture/commit-push-ci-deploy-pipeline.md` | 全链路图 + 每环节参数速查表 + 失败定位入口 |
| `20-Runbooks/_index.md`（追加） | 本次审计报告索引（部署与发布节） |
| `50-Reviews/_index.md`（追加） | self-registration-design / backend+frontend health survey / redundant-modules review / 本次审计 |
| `60-Lessons/部署.md`（追加 3 条） | push 零 check-runs=事件丢失判断法；镜像只含 app/（scripts 不进镜像）；新 env 键三处同步 |
