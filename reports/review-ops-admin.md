# 资深运营管理员审查报告

> 角色视角：资深平台运营 / 运维管理员
> 审查范围：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform`
> 审查方式：只读 — 绝无任何代码改动
> 审查时间：2026-07-16

---

## 一、问题清单

### P0 阻塞级

#### 1. 管理员写操作 0 审计日志（合规 / 取证盲区）

- **位置**：
  - `app/api/v1/admin_users.py:35-110`（create_user / update_user / reset_password / delete_user）
  - `app/api/v1/notifications.py:28-78`（create_config / update_config / delete_config）
  - `app/api/v1/deployments.py:106-114`（`api_trigger_deploy`）
  - `app/api/v1/auth.py:109-138`（login 失败/成功落库均不写）
- **问题描述**：平台目前**不存在任何 `audit_log` / `operation_log` 表**（`grep -r "audit" app/models/` 仅在文档注释中出现 5 次，无模型）。任何 admin 改他人角色、改密码、删除账号、修改推送 webhook、触发生产部署，均不留 actor / before / after / ip 记录。GDPR / 内部审计 / 离职合规审查场景下无法定位「谁在什么时候改了什么」。
- **专业影响**：合规风险（无 trail → SOX / 内部审计 0 容忍）+ 运营风险（误操作无法回滚 / 无法追责）。
- **建议修复**：
  1. 新增 `audit_log` 表（`alembic/versions/` 新 migration）：`id / actor_id / action / resource_type / resource_id / before_json / after_json / ip / user_agent / created_at`
  2. 在 admin_* 路由和 `trigger_workflow_dispatch` 加 `@audit_action` 装饰器
  3. 前端 `AdminUsers` / `NotificationConfig` 加「操作历史」tab
- **优先级**：P0

---

#### 2. 没有「超级管理员」 / 最后一名 admin 自我保护

- **位置**：
  - `app/models/user.py:8-28`（User 模型 — 无 `is_super_admin` 字段）
  - `app/api/v1/admin_users.py:58-77`（`update_user` 可任意把 admin 改成 user）
  - `app/api/v1/admin_users.py:97-110`（`delete_user` 可任意删除 admin）
- **问题描述**：
  - `User.role` 只有 `admin|user` 两类，没有「最后一名 admin」锁。
  - `update_user` 可把唯一 admin 改成 `user` → 系统无 admin → 必须 ssh 进容器改库。
  - `delete_user` 可删除自己的账号（前端 `web/src/pages/AdminUsers/index.tsx:54` 仅判断 `username === currentUser?.username` 阻止当前会话，前端绕过 / 旧 token 仍可调 API）。
  - `UserCreateRequest` 没限制「第一个 admin 必须是初始化 admin」— 任何人可以邀请任意 admin。
- **专业影响**：运营风险 — 单点 admin 误操作即可让平台无人能管理。
- **建议修复**：
  1. 加 `User.is_super_admin: bool` 字段 + 不能 unset / 不能 delete
  2. `update_user` 后置钩子：「若被改用户是 admin 且新 role 为 user，禁止 if 系统中 admin 数 = 1」
  3. `delete_user` 同样的 last-admin 保护
  4. 前端同步 disable 操作按钮（前端目前只禁用 `isSelf`，是 username 字符串比较，username 改名即可绕过 — 见 `web/src/pages/AdminUsers/index.tsx:54`）
- **优先级**：P0

---

#### 3. 推送 webhook / SMTP 密码明文落 DB（待确认）

- **位置**：
  - `app/services/notification_service.py:65-71`（`_protect_config_json`）声称加密 `smtp_password` / `webhook_secret`
  - `app/models/notification.py:21`（`config_json = Column(JSON)`）
- **问题描述**：
  - `_protect_config_json` 只加密 `smtp_password` 与 `webhook_secret` 两个 key。
  - 但是 webhook 的「真正凭据」是 `webhook_url`（含 `?key=xxx` token，`web/src/pages/NotificationConfig/index.tsx:267`），该字段**完全不加密**地写进 `config_json`。
  - `webhook_url` 出现在 `NotificationLogs.target` 列（`app/services/notification_service.py:374-378` 直接 select），所以日志表 / DB 备份 / 慢查询日志中均含明文 key。
  - 加密 fallback 在 `_get_fernet`：`if not key: return None` — 当 `NOTIFICATION_ENCRYPTION_KEY` 未配置时，**直接返回 None，密码明文存**。无任何告警 / 无启动失败。
  - `app/config.py:179` 默认 `SECRET_KEY = "your-secret-key-change-in-production"` — 若运维没设，会拿这个当 Fernet key，存在伪造解密风险。
- **专业影响**：合规风险 + 数据泄露 — 任何 DB 备份 / 慢查询日志泄漏即等于 webhook key 全泄漏。
- **建议修复**：
  1. 启动时强制校验 `NOTIFICATION_ENCRYPTION_KEY` 长度 ≥ 32 字节，否则 fail-fast
  2. `webhook_url` 写入前必须 sanitize / 加密 token 部分（仅存「key 指针」+ 加密在另一张 secrets 表）
  3. `NotificationLogs.target` 不要 select 明文 URL，改 select `config_id` + 前端根据权限二次解密
- **优先级**：P0

---

#### 4. 部署触发 + Docker socket 暴露给 web — 整个主机可被 admin 端 RCE

- **位置**：
  - `app/services/deployment_service.py:165-202`（`_DockerUnixConnection` + `_docker_api` 直接走 Unix socket，无任何白名单）
  - `app/api/v1/deployments.py:106-114`（`api_trigger_deploy` 触发任意 workflow）
  - `app/main.py:223-225`（`/api/v1/admin` 路径前缀）
  - `app/config.py:128` 默认 `deploy_docker_socket = "/var/run/docker.sock"`
- **问题描述**：
  - backend 容器一旦挂载 `/var/run/docker.sock`，**任何 admin 用户**即可通过 `_docker_api("POST", "/containers/<id>/exec", ...)`、`/containers/create` 等路径执行任意容器命令 — 这是经典的「容器逃逸 → 主机 root」入口（参考 Docker socket 攻击面）。
  - `_docker_api` 方法字符串拼接（`app/services/deployment_service.py:182-202`），允许 admin 拼任意 path（`/v1.43/containers/json?all=1`、`/v1.43/images/search` 等），不只限于只读容器 stats。
  - `trigger_workflow_dispatch` 无 secondary confirm / 二次验证（仅前端一个 `message.confirm`），可被滥用刷 GitHub Actions 配额。
- **专业影响**：安全风险 — admin 端 = 主机 RCE，无审计 + 无 2FA。
- **建议修复**：
  1. backend 容器不挂载 `/var/run/docker.sock`，改读 `/proc/<pid>/status` 或 `prometheus_client` 暴露 stats
  2. 即便保留 socket，`_docker_api` 必须维护白名单 path
  3. `trigger_workflow_dispatch` 加 cooldown + 「最近 N 分钟内已触发」返回 429
- **优先级**：P0

---

#### 5. 登录无 rate-limit / brute-force 保护

- **位置**：
  - `app/api/v1/auth.py:109-138`（`login` 端点，失败仅 `401` 不计入 Redis）
  - `app/api/deps.py:83-122`（无慢启动 / lockout）
  - `app/main.py`（无 `slowapi` / 无 `fastapi-limiter` 接入）
- **问题描述**：
  - 整个 repo 无 `slowapi` / `fastapi-limiter` 接入（grep 0 命中）。登录失败可无限重试。
  - admin / Aidan / 早期用户弱口令一旦泄露，无任何 IP lockout / 失败计数。
  - 无验证码 / 无 MFA / 无 device-binding（refresh token 30 天 + SHA-256 即可永久冒充）。
- **专业影响**：运营风险 — 一次性 admin 凭据泄露 = 完全接管平台。
- **建议修复**：
  1. 加 `slowapi.Limiter` 全局挂载，`/auth/login` 5 次/分钟/IP
  2. 用户级 10 次/小时 lockout
  3. admin 强制 TOTP（M5 路线图里没有这一项）
- **优先级**：P0

---

#### 6. ETL 失败/数据陈旧 — 无任何主动通知

- **位置**：
  - `app/api/v1/etl_status.py:144-172`（`get_etl_status` 计算 `stale_markets` 仅返回给前端展示）
  - `app/core/scheduler.py:58-919`（全部 `run_*` 函数仅 `print(...)` 落 stdout，无 push 通知调用）
  - `app/services/notification_service.py`（只在用户主动触发时调用，无 scheduler / ETL 主动调用入口）
- **问题描述**：
  - `stale_markets` 阈值在 `app/api/v1/etl_status.py:163` hardcode `days_old > 3` — 周末 / 国庆调休均会误报，但更严重的是「当天 18:00 数据没到」不会通知任何人。
  - `ETLLog.error_msg` 落库后无人订阅 — 失败任务停留在 last_run=failed，运营只能主动刷 ops dashboard。
  - `NotificationService` 没有「系统级通知」（无 `system_user_id` / 无 group channel 概念），平台本身没有给自己发告警的能力。
  - 监控 runbook（`docs/dev-notes/20260704-monitoring-runbook.md:240-250`）已说明「钉钉 webhook 未接入」，这是已知 gap 但无 deadline。
- **专业影响**：运营风险 — ETL 静默失败 24h+ 才会被管理员发现，期间用户查到的数据全是过期的。
- **建议修复**：
  1. 在 `init_scheduler()` 末尾注册 `run_*` 的统一 wrapper：捕获异常 → 写 `etl_log` → 调用 NotificationService 系统通道
  2. `stale_markets` 计算后 + 阈值超出 → 主动调 webhook
  3. 增加每日 09:00 cron 健康巡检，发到钉钉 / 企业微信
- **优先级**：P0

---

#### 7. `SECRET_KEY` 默认值在源码里 — 生产忘设就裸奔

- **位置**：
  - `app/config.py:179` `SECRET_KEY: str = "your-secret-key-change-in-production"`
  - `app/services/notification_service.py:33-44`（fallback 用 `auth_settings.SECRET_KEY` 作 Fernet key）
  - `app/api/deps.py:93-99`（JWT 用此 SECRET_KEY）
- **问题描述**：
  - 默认值就是「请改」，但启动无任何校验。`mem-leak` 风险：
    - 若运维忘设 `AUTH_SECRET_KEY`，所有生产 JWT 用同一弱 key，攻击者签发 admin token 即可
    - NotificationService 自动 fallback 用同一弱 key 加密 webhook secret
  - 与之相比 `notification_encryption_key: str = ""`（line 123）也有同样问题但更隐蔽。
- **专业影响**：安全风险 — 整个认证 / 加密体系默认等于 0 防护。
- **建议修复**：
  1. startup hook：`if SECRET_KEY.startswith("your-") or len(SECRET_KEY) < 32: raise RuntimeError("Set AUTH_SECRET_KEY before boot")`
  2. CI 部署前检查 `deploy/aliyun-ecs/update.sh` 已确认 key 已 rotate
- **优先级**：P0

---

### P1 重要级

#### 8. 调度任务在 UI 上 0 可见 — 改 cron / 改 trigger 只能改代码重启

- **位置**：
  - `app/core/scheduler.py:1032-1561`（`init_scheduler` 全是 `scheduler.add_job` 硬编码）
  - `web/src/pages/ETLOpsDashboard/index.tsx`（仅展示 last_run，不展示 cron / next_run）
  - `app/api/v1/etl_status.py`（无 `/jobs` / `/trigger/<name>` 端点）
- **问题描述**：
  - 改一个 cron 时间（如「美股改成 04:30」）必须改 `scheduler.py` → push → 走完 GitHub Actions → 重启 backend → 全程 5-15 分钟，期间 leader 端 heartbeat 中断。
  - `StrategyConfig` 表里存了 strategy 参数（`app/models/etl.py:89-111`），cron 配置却完全在代码里 — 数据/控制分离不一致。
  - `web/src/pages/ETLOpsDashboard/index.tsx:58` `refetchInterval: 30_000` 但每个任务只看 `last_run`，没有 `next_run_time`、`is_running`、`misfire_grace` 等关键调度健康指标。
- **专业影响**：运营效率 — 每次业务变更要走完整发布链路，无法敏捷响应。
- **建议修复**：
  1. 把 `cron_trigger` 配置抽到 `etl_job_config` 表，UI 上可改、可立即 reload
  2. `etl_status` 加 `/jobs/scheduler-list` / `/jobs/reload` / `/jobs/run-now/<name>` 端点
  3. Ops dashboard 卡片显示 `next_run_in` + 漂移告警
- **优先级**：P1

---

#### 9. SSE log 流有 query-param JWT 后门 — 不可审计

- **位置**：`app/api/v1/deployments.py:39-79`（`_require_admin_for_sse`）
- **问题描述**：
  - 解释性注释提到「EventSource 无法加自定义 header」，但 query 参数 token 会：
    1. 写入 nginx access log（明文 JWT，泄露 token）
    2. 写入浏览器历史
    3. 任何前端 bug 都会把 admin token 暴露在 referer
  - 该端点无调用日志、无 admin 自我保护。
- **专业影响**：安全风险 — SSE 流一旦开启，所有日志（含敏感 `_sanitize` 漏掉的）随 token 泄漏。
- **建议修复**：
  1. 优先用 `Cookie + SameSite=Strict` + JWT，前端不再依赖 `EventSource(query-param)`
  2. nginx 配置 `log_format` 过滤 `token=`
- **优先级**：P1

---

#### 10. `_sanitize` 漏防 — token / password 仍会进 log stream

- **位置**：
  - `app/services/deployment_service.py:23-34`（4 条 sanitize 正则）
  - `app/services/deployment_service.py:318-354`（`get_container_logs`）
- **问题描述**：
  - 正则只覆盖 `password/passwd`、`token/api_key/secret/key`、`AUTH_SECRET_KEY/AUTH_ADMIN_PASSWORD/POSTGRES_PASSWORD`、`ghp_xxx`。
  - 漏防：
    - JWT token（`eyJxxx...`）— 部署 log 经常打 user JWT
    - `TUSHARE_TOKEN=` / `DEEPSEEK_API_KEY=` / `TIINGO_API_KEY=` — 走 `key=` 模式但大小写不敏感，已被覆盖，但子 token 字段（如 `tushare_token=abc`）无前缀覆盖
    - URL 中的 `?access_token=` / `?api_key=`（雪球 / Finnhub 等）— 不是 `key=`
    - JSON 中的 `"password": "xxx"` — 不是 `password=`
  - `_log_tailer` 把 sanitize 后的日志 publish 到 Redis pub/sub，前端在浏览器显示并落 history。
- **专业影响**：合规风险 — 部署日志含凭据时任何前端用户都可读到。
- **建议修复**：
  1. 改用结构化日志（JSON）+ 字段级 redaction（不再用正则）
  2. 关键 secret 不应通过 stdout 输出
- **优先级**：P1

---

#### 11. 调度器 leader 漂移 / 多副本下行为未定义

- **位置**：
  - `app/core/scheduler.py:51-52`（`scheduler = BackgroundScheduler()` 全局单例）
  - `app/core/scheduler.py:1571-1624`（心跳机制）
  - `app/core/scheduler.py:1551-1561`（`scheduler.start()` 每次 import 都启一次）
- **问题描述**：
  - 多 worker 部署（uvicorn 多进程 / 多容器）下：
    - `BackgroundScheduler()` 是 in-process，全局 `scheduler` 在每个 worker 都启一次 → **同一 cron 在每个 worker 都会触发**。Redis 锁（`redis_lock`）只防「同 pipeline 同 worker 重复」，但多 worker 之间也会被锁阻塞，性能浪费。
    - `_SCHEDULER_HEARTBEAT_KEY` 任何 worker 都会写，新人 5 秒覆盖旧人，无法判断真正的 leader。
    - `init_scheduler()` 在 import 时执行 — `app/main.py` 启动 + worker 启动都会触发，可能重复注册导致 `replace_existing` 异常。
  - 没有基于 Redis 的 leader election（`SELECT ... FOR UPDATE` 风格 / Redlock），横向扩缩容下行为不确定。
- **专业影响**：运营风险 — 任务重复触发 → DB 写竞争 / 配额烧光 / 误告警。
- **建议修复**：
  1. 引入 leader election（`redis_lock("scheduler_leader", expire=60)` + 续约）
  2. `init_scheduler` 只在 leader 上跑
  3. 或者迁移到 Celery Beat（`celery beat_schedule`）— 已有 Celery 应用（`app/core/celery_app.py`）但调度器却用 APScheduler，**两套调度并存**也是 P1 问题（见 #12）。
- **优先级**：P1

---

#### 12. Celery Beat 没启用 + APScheduler 并存 — 双调度源混乱

- **位置**：
  - `app/core/celery_app.py:14-23`（`celery_app` 已创建，含 `app.tasks.indicator` / `cninfo` / `cninfo_pdf`）
  - `app/core/celery_app.py:42-50`（`task_default_queue="celery"` + `worker_prefetch_multiplier=1`）
  - `app/core/scheduler.py`（APScheduler 在 backend 进程内）
- **问题描述**：
  - 所有「重 ETL」任务（`calculate_indicators.delay`）通过 Celery 推；
  - 但「何时触发」由 APScheduler 决定 — 两个调度系统没有任何同步。
  - 没有 `celery beat` 进程配置（`docker-compose.yml` 也没启动 beat 容器 — 需确认），意味着 Celery 的 `task_acks_late=True`（celery_app.py:39）已经准备好分布式重试，但 beat 完全缺席。
  - Celery 任务失败无 dead-letter、无最大重试配置（`celery_app.py:25-46` 没设 `task_annotations`）。
- **专业影响**：运营风险 — Celery 任务实际跑在哪里 / 失败怎么 retry 完全没有 runbook 文档。
- **建议修复**：
  1. 二选一：要么把 cron 配置全迁到 Celery Beat，要么把 Celery 任务迁到 APScheduler 子进程
  2. 当前架构下，至少把 beat 启起来，并把所有 `run_*` 都改为 Celery task + beat schedule
- **优先级**：P1

---

#### 13. ETL 调度 / 数据修复工具：缺「手动重跑 + 参数化」端点

- **位置**：
  - `app/api/v1/etl_status.py`（仅 GET，无 POST 触发）
  - `app/api/v1/etl.py`（仅 GET /status，无 trigger）
  - 整个 repo 内 `grep "router.post.*etl"` 0 命中
- **问题描述**：
  - 当某一天 Tushare 失败，运营想「重跑 2026-07-10 A 股 ETF 日线」，**没有 UI / API 可调**。只能 ssh 容器跑 python -c，依赖具体函数签名（`run_a_share_etl(target_date=...)`，`app/core/scheduler.py:58`）。
  - `ETLStatus` 前端 `web/src/pages/ETLStatus/index.tsx` 只读 log，无重跑按钮。
  - 缺失工具：
    - 单日 / 单市场 / 单代码数据回填
    - 数据质量扫描（`stale_markets` 只看 bar 不看 indicator 完整性）
    - 「delist 后仍存在的孤儿 ETF」清理
- **专业影响**：运营效率 — 1 次 ETL 失败 → 5-10 分钟手工操作。
- **建议修复**：
  1. 加 `POST /api/v1/etl/rerun` body `{job_name, target_date}`，调对应 `run_*`
  2. 前端「ETL 状态」表格加「重跑」按钮 + 二次确认
  3. 加 `GET /api/v1/etl/data-quality` 扫「indicator 行数 vs bar 行数」差异
- **优先级**：P1

---

#### 14. 「数据修复」UI 缺失：补全 / 删除 / 重算只能 ssh + SQL

- **位置**：全文 grep 不到 admin-facing 数据修复端点
- **问题描述**：
  - 已知问题列表 `docs/dev-notes/20260714-a-share-indicator-completeness.md` 里说的「指标不完整」情况，目前没有任何平台工具：
    - 看「哪些 ETF 缺 5 日均线」
    - 看「哪些 ETL 任务上次失败但没重试」
    - 看「哪些用户配置错（如 indicator_calculation 不带 market_filter）」
  - 现唯一入口是 `scripts/data_completeness_check.py` — ssh 容器跑，且无 cron 化。
- **专业影响**：运营效率 — 一旦发现数据 gap，排查只能 ssh。
- **建议修复**：建 `/api/v1/admin/data-quality/*` 端点 + 前端面板
- **优先级**：P1

---

#### 15. 用户管理无会话列表 / 强制登出 — admin 不能查谁在线 / 踢人

- **位置**：
  - `app/models/refresh_token.py`（refresh token 表存在但无 admin 端点）
  - `app/api/v1/admin_users.py`（无 `/users/{id}/sessions` / `/revoke`）
  - `app/core/redis_client.py:88-97`（`is_token_blacklisted` 单 token 粒度）
- **问题描述**：
  - admin 想强制某用户下线，必须 `UPDATE refresh_token SET revoked=true WHERE user_id=?`（无端点）。
  - 想看某用户当前所有登录设备 / 最后活跃时间 — 无 UI。
  - `UserDevice`（`app/models/user_device.py`）有 `last_active_at`，但 admin_users 列表里没有这个字段（`web/src/pages/AdminUsers/index.tsx:131-209`）。
- **专业影响**：运营效率 — 离职员工 token 撤销要走 SSH。
- **建议修复**：
  1. 加 `GET /admin/users/{id}/devices` / `DELETE /admin/users/{id}/devices/{device_id}` / `POST /admin/users/{id}/revoke-tokens`
  2. 前端用户列表加「最后活跃」「设备数」列
- **优先级**：P1

---

#### 16. Notification 配置无测试 schedule — 推送失败只能等真实 cron 触发

- **位置**：
  - `app/api/v1/notifications.py:70-78`（`test_config` 端点存在但仅「发一条 test 消息」）
  - `app/services/notification_service.py:158-199`（`send_notification` 仅手动调用）
- **问题描述**：
  - 平台目前没有 cron 推送机制 — 即便配好 webhook，谁来触发？调 `NotificationService.send_notification(...)` 的地方 grep 不到，意味着**整个推送系统是死代码**，只在 admin 手动点「测试」时发。
  - 即便接 cron，**失败重试机制缺失**（`NotificationLog` 表里 status=failed 行永远无人重发）。
- **专业影响**：运营风险 — 用户配好 webhook 后「以为已经接好」，实际收不到任何东西。
- **建议修复**：
  1. 接 cron / Celery Beat 调度推送（如每周 6 / 收盘 16:30 推周报）
  2. `failed` 状态 → 5min / 30min / 2h 三次重试
- **优先级**：P1

---

#### 17. 数据陈旧告警阈值不合理 — 3 天才标 stale，且无 per-job 阈值

- **位置**：`app/api/v1/etl_status.py:151-164`
- **问题描述**：
  - 全平台统一 `days_old > 3` — 但：
    - A 股 ETF 当天收盘数据，1 天没到就该报警
    - 美股 daily ETL 失败 1 天没到该报警
    - 季度 ETF holdings 5 天没到可能正常（季报披露窗口）
  - 没有 per-job threshold 配置（`app/models/etl.py:ETLLog` 也无 `expected_max_lag_minutes` 字段）。
- **专业影响**：运营风险 — 误报 + 漏报并存。
- **建议修复**：
  1. `etl_job_config` 表加 `expected_max_lag_minutes: int` + `slack_channel: str`
  2. etl_status 计算 stale 时按 job 而非 market
- **优先级**：P1

---

#### 18. 多环境（dev/staging/prod）隔离缺失

- **位置**：
  - `app/config.py:109` `app_env: str = "development"` — 但 `docker-compose.yml` 没有 `APP_ENV=production` 强制
  - 全 repo 无 `staging` / `dev` 配置文件
  - `docs/dev-notes/20260624-aliyun-ecs-deployment.md` 仅描述「生产 ECS」
- **问题描述**：
  - 单一 `docker-compose.yml` 即是开发也是生产。
  - 没有 staging 环境 — 任何 push 直接进生产。
  - `secret-rotate-3-providers`（`docs/dev-notes/20260705-secret-rotate-3-providers.md`）显示 secret 轮换在生产做，没有 pre-prod 验证。
- **专业影响**：合规 + 运营 — 改一行代码就上生产，无法回滚评估。
- **建议修复**：
  1. 拆分 `docker-compose.dev.yml` / `docker-compose.staging.yml` / `docker-compose.prod.yml`
  2. 引入 GitHub Actions `environment: production` + required reviewers
  3. staging 环境用同一套 alembic + 独立 DB
- **优先级**：P1

---

#### 19. Docker socket 暴露面过大 — 即使只读 stats 也危险

- **位置**：`app/services/deployment_service.py:182-202`（`_docker_api` 通用方法）
- **问题描述**：
  - 该方法是「HTTP 方法 + 任意 path」任意拼接。理论上 admin 可用：
    - `POST /v1.43/containers/{id}/exec` 启动 bash
    - `POST /v1.43/volumes/create` 写主机文件系统
    - `POST /v1.43/networks/create` 改网络拓扑
  - 当前只用了 `GET /containers/json` / `GET /containers/{id}/stats` / `GET /containers/{id}/logs`，其他 path 完全可以开放。
- **专业影响**：安全 — 见 #4，但本条聚焦于「代码层面」未做白名单。
- **建议修复**：`_docker_api(method, path, allow=("GET",))` + 白名单 path prefix
- **优先级**：P1

---

#### 20. 容器化 / worker 健康无统一探针

- **位置**：
  - `app/main.py`（无 `/health` 路由定义，需确认其他文件）
  - `app/core/celery_app.py`（无 `celery inspect ping` 入口）
  - `app/core/scheduler.py`（`is_scheduler_running` 已实现但无 API 暴露）
- **问题描述**：
  - 监控 runbook `docs/dev-notes/20260704-monitoring-runbook.md` 提到 `/health` 探针，但未给出后端实现路径。
  - 容器日志 size 限制 100m × 5（监控 runbook line 20）— `exit 5` 后查不到历史日志。
  - 没有 Prometheus `/metrics` 端点（`prometheus_fastapi_instrumentator` 未接入）。
- **专业影响**：运营 — 见 #6 同时缺乏机器可读指标。
- **建议修复**：
  1. 在 `app/main.py` 加 `/health` / `/health/scheduler` / `/health/celery`
  2. 接入 `prometheus_fastapi_instrumentator`
- **优先级**：P1

---

#### 21. 日志聚合入口缺失 — 后端日志无集中查询 UI

- **位置**：
  - `app/main.py`（无 `/api/v1/logs/search` 类端点）
  - `web/src/pages/AdminDeployments/index.tsx:235-340`（仅 SSE 流，无历史日志搜索）
- **问题描述**：
  - 唯一「查历史日志」入口是 AdminDeployments 的 `container/{container}/logs?tail=N`（`app/api/v1/deployments.py:135-143`） — 只能查容器最近 N 行。
  - 没有 ELK / Loki 接入；runbook §四「推荐 Loki」但未实现。
- **专业影响**：运营效率 — 一次事故调查要 ssh 翻 `docker logs`。
- **建议修复**：
  1. 接入 Loki / Promtail + 在 AdminDeployments 加「历史日志」tab
  2. 或者实现轻量 DB 化日志：`log_buffer` 表 + 全文搜索
- **优先级**：P1

---

#### 22. 配置变更无版本化 / diff 视图

- **位置**：
  - `app/api/v1/admin_users.py:58-77`（`update_user` 直接覆盖 role / is_active）
  - `app/api/v1/notifications.py:43-55`（`update_config` 直接覆盖）
  - 数据库无 `*_history` 表
- **问题描述**：
  - 改 webhook URL → 旧值丢失；误改后无法「一键回滚」。
  - 用户角色变更无 history，前端「操作日志」是空白。
- **专业影响**：合规 / 运营 — 误改 → 全平台影响（如 admin 把自己降级，#2；改 webhook URL 致推送全挂）。
- **建议修复**：所有 admin 写操作走 `*_history` 表 + 前端展示 diff / 回滚按钮。
- **优先级**：P1

---

### P2 一般级

#### 23. Scheduler 日志仅 print — 无结构化 logging

- **位置**：`app/core/scheduler.py:69, 96, 124, ...`（20+ 处 `print(...)` 而非 `logger.info(...)`）
- **问题描述**：与下文一致的 `print`（如 line 155-160 heartbeat 失败 print）— grep 不到 `logging.getLogger(__name__).warning`。
- **建议修复**：替换为 `logger = logging.getLogger(__name__)`。
- **优先级**：P2

---

#### 24. `api_v1_prefix` 拆分可读性差 — admin 路由散落在两个前缀

- **位置**：
  - `app/main.py:218-220` `admin/users` 前缀
  - `app/main.py:223-225` `admin` 前缀（内部又有 `deployments` / `server/health` 等）
  - `app/main.py:193` `etl` 前缀下挂了 `etl_status`
- **问题描述**：URL 路径设计不一致。
- **建议修复**：统一 `/admin/*` 与 `/ops/*`。
- **优先级**：P2

---

#### 25. `NotificationService` 大量 print（无 logger）

- **位置**：`app/services/notification_service.py:189, 196`（实际是 `log.status = "failed"` 不算 print；其他 grep 几乎无 print，但异常捕获用 `except Exception` 吞错，无 `logger.exception`）。
- **问题描述**：smtplib 失败 / requests 失败仅回写 `log.error_msg`，**前端 alert 没有任何日志落结构化日志**。无法 trace 谁发的失败通知。
- **建议修复**：加 `logger.exception` 在 catch 分支。
- **优先级**：P2

---

#### 26. `NotificationLog` 字段缺失 actor / 触发器

- **位置**：`app/models/notification.py:36-64`
- **问题描述**：
  - `NotificationLog` 仅有 `config_id` / `report_id`，无 `triggered_by`（user_id 或 system）。
  - 无 `channel_response`（HTTP status / SMTP 250 等）。
  - 关联的 `NotificationConfig` 无 `user_id` 字段不一致（实际有，见 line 14）。
- **建议修复**：加 `triggered_by_user_id` / `triggered_by_system` / `response_payload` 字段。
- **优先级**：P2

---

#### 27. 调度器漂移检测缺 owner / 责任链

- **位置**：`docs/dev-notes/20260704-monitoring-runbook.md:267-273`（§六 TODO）
- **问题描述**：runbook 已说明「TODO 接入 Prometheus / 钉钉」但无负责人 / deadline。
- **建议修复**：补 owner + 季度复盘。
- **优先级**：P2

---

#### 28. 推送系统缺乏「静默时间 / 频控」配置

- **位置**：`app/services/notification_service.py:158-199`
- **问题描述**：连发 N 条不会去重 / 不会降频，紧急 ETL 失败时可能短时间打满 webhook 配额。
- **建议修复**：加 `cooldown_seconds` / `max_per_hour` per config。
- **优先级**：P2

---

#### 29. SSE 心跳 / keepalive 与 nginx timeout 未对齐

- **位置**：`app/api/v1/deployments.py:184` (`yield ": keepalive\n\n"` 间隔 100ms)
- **问题描述**：与 `Cache-Control: no-cache` + `X-Accel-Buffering: no` 配套。100ms 频率过密，会造成 nginx worker 忙。
- **建议修复**：keepalive 间隔 15-30s 即可。
- **优先级**：P2

---

#### 30. 多语言 / i18n：admin UI 全中文

- **位置**：`web/src/pages/AdminUsers/index.tsx`、`AdminDeployments/index.tsx` 等
- **问题描述**：运营文档提及 i18n roadmap（`docs/dev-notes/20260711-competitor-design-survey.md`）但 admin UI 全硬编码中文。
- **建议修复**：i18n key 替换硬编码字符串。
- **优先级**：P2

---

## 二、缺失的运维能力（按重要性排序）

1. **统一的 admin 操作审计表 + UI** — 全部 admin 写操作 (用户 / 通知 / 部署) 必须留 actor / before / after / ip trail
2. **最后一名 admin / super-admin 保护** — 防单点误操作
3. **登录 brute-force 限流 + admin TOTP MFA** — 安全基线
4. **失败 ETL 主动通知 + per-job stale 阈值** — 改「被动 dashboard」为「主动告警」
5. **WebSocket / SSE 替换 query-param JWT** — 防 token 落 nginx log
6. **手动重跑 ETL 端点 + UI** — 改 ssh 重跑为 admin 一键重跑
7. **数据质量扫描面板** — 哪些 indicator / bar / score 缺 / 漂移
8. **admin 强制下线 / 会话管理** — 离职合规
9. **Celery Beat 启用 + 单调度源** — 与 APScheduler 二选一
10. **leader election（多 worker 横向扩展）** — 防重复触发
11. **历史日志聚合 UI（Loki / Promtail 接入）** — 改 ssh 翻 log 为 UI 搜索
12. **通知失败重试机制 + 静默时间 / 频控** — 推送系统从「死代码」变可用
13. **staging 环境 + GitHub Actions environment 守卫** — 防 push 即生产
14. **/health/* 多探针 + Prometheus /metrics 端点** — 监控机器可读化
15. **配置变更历史 / 一键回滚** — 防误改 → 全平台故障
16. **通知凭据加密强化（Fernet key 强制启动校验 + webhook_url 加密）** — 合规
17. **scheduler UI 配置面板 + reload** — 改 cron 不用发版
18. **多语言 admin UI（i18n）** — 海外运营准备
19. **scheduler 漂移 / misfire owner 责任矩阵** — runbook 升级
20. **on-call 排班 / 升级链 / SLA 定义** — runbook `20260704-ops-runbook.md:267-273` §八仅一句「紧急变更 ssh」远不够

---

## 三、值得肯定的设计（避免「只挑刺」）

- ✅ CORS 默认拒绝 wildcard（`app/config.py:161-163`）— 生产安全底线守住
- ✅ refresh token SHA-256 存储 + 轮换（`app/api/v1/auth.py:71-77, 165-177`）
- ✅ 分布式 Redis 锁防任务重叠（`app/core/scheduler.py` 多处 `redis_lock(...)`）
- ✅ 调度器 heartbeat 跨 worker 可见（`app/core/scheduler.py:1571-1624`）
- ✅ A 股指标 17:00 兜底二次跑（`run_a_share_indicator_fallback`，`scheduler.py:314-357`）
- ✅ log stream 4 层 sanitize（`deployment_service.py:23-34`）— 虽不完整但有兜底意识
- ✅ NotificationConfig 字段级加密（`_protect_config_json` / `_expose_config_json`）— 思路正确
- ✅ 容器化部署 + GitHub Actions workflow_dispatch 手动触发（`deployment_service.py:135-159`）
- ✅ runbook 已建覆盖 deploy / monitoring / celery / secret-rotate 等关键场景

---

## 四、关键文件引用一览

| 文件 | 用途 | 行数 |
|---|---|---|
| `app/api/v1/admin_users.py` | 用户管理 API | 110 |
| `app/api/v1/deployments.py` | 部署管理 API + SSE | 226 |
| `app/api/v1/etl_status.py` | ETL ops 看板 | 172 |
| `app/api/v1/etl.py` | ETL 历史日志 | 52 |
| `app/api/v1/notifications.py` | 推送配置 + 日志 API | 93 |
| `app/api/v1/auth.py` | 登录 / 登出 / 设备 | 282 |
| `app/api/deps.py` | 依赖注入 + admin gate | 294 |
| `app/services/deployment_service.py` | Docker + GH Actions 调用 | 455 |
| `app/services/notification_service.py` | 推送实现 + Fernet 加密 | 401 |
| `app/core/scheduler.py` | APScheduler 全部 cron | 1656 |
| `app/core/celery_app.py` | Celery 配置 | 50 |
| `app/core/redis_client.py` | 分布式锁 + JWT 黑名单 | 97 |
| `app/models/user.py` | User 模型 | 28 |
| `app/models/notification.py` | 推送表 | 64 |
| `app/models/etl.py` | ETLLog / StrategyConfig | 178 |
| `app/schemas/user.py` | 用户管理 Pydantic | 40 |
| `app/schemas/auth.py` | 登录 schema | 50 |
| `app/schemas/notification.py` | 推送 schema | 71 |
| `app/schemas/deployment.py` | 部署 schema | 50 |
| `app/main.py` | FastAPI 应用入口（路由挂载 line 168-260） | — |
| `app/config.py` | Pydantic Settings（secret 在 line 123, 126-128, 179） | — |
| `web/src/pages/AdminUsers/index.tsx` | 用户管理前端 | 345 |
| `web/src/pages/AdminDeployments/index.tsx` | 部署前端 + SSE | 483 |
| `web/src/pages/ETLOpsDashboard/index.tsx` | ETL 看板前端 | 256 |
| `web/src/pages/ETLStatus/index.tsx` | ETL 日志前端 | 115 |
| `web/src/pages/NotificationConfig/index.tsx` | 推送配置前端 | 327 |
| `web/src/pages/NotificationLogs/index.tsx` | 推送日志前端 | 121 |
| `docs/dev-notes/20260704-ops-runbook.md` | 主 runbook | 282 |
| `docs/dev-notes/20260704-monitoring-runbook.md` | 监控 runbook | 271 |

---

## 五、建议的修复优先级路线图

| 阶段 | 目标 | 项 |
|---|---|---|
| **第 1 周** | 安全基线 | #2 last-admin / #5 login rate-limit / #7 SECRET_KEY 启动校验 / #4 docker socket 白名单 |
| **第 2 周** | 合规基线 | #1 audit_log 表 + UI / #3 webhook_url 加密 / #9 SSE 不传 query token / #10 sanitize 升级 |
| **第 3 周** | 运维可观测 | #6 ETL 主动告警 / #13 重跑端点 / #15 会话管理 / #22 配置历史 |
| **第 4 周** | 多 worker / 多环境 | #11 leader election / #12 Celery Beat 启 / #18 staging / #20 /metrics |
| **第 5 周+** | 体验 / 高级 | #8 cron UI 配置 / #14 数据质量面板 / #16 推送重试 / #21 日志聚合 |

---

> 本报告基于 2026-07-16 仓库快照，仅描述问题，不含任何代码改动建议的实施。后续修复请配合 `docs/dev-notes/` 中的 runbook 同步更新。