# AD-Research 投研平台管理员模块深度审查报告

**版本**：v1.0  
**审查日期**：2026-07-16  
**审查人**：资深运营管理员视角  
**审查范围**：用户管理 `/admin/users`、部署管理 `/admin/deployments`、ETL 运维看板 `/admin/etl-status`、通知配置 `/notifications`（用户原文 `/notification-config` 与实际路由 `/notifications` 不一致，见 P2-08）、登录 `/login`  
**审查方式**：基于本地代码仓库静态审查，未启动 dev server，未修改源代码。

---

## 一、审查结论摘要

AD-Research 平台已具备基础的管理员功能：JWT 认证、用户 CRUD、部署历史/健康/日志、ETL 状态看板、通知渠道配置。认证机制（bcrypt、短期 JWT、Redis 黑名单、refresh token rotation）设计合理，前端也实现了管理员路由守卫和侧边栏菜单隔离。

但从**金融系统运营、合规审计、生产安全**角度看，当前平台在以下方面存在显著 gaps：

1. **权限模型过于粗糙**：仅 `admin/user` 两个角色，无数据隔离、无功能权限矩阵、无只读管理员/运维角色。
2. **缺乏审计与合规基础设施**：没有审计日志表，没有登录/管理操作留痕，无法满足金融行业审计追踪要求。
3. **登录安全防御不足**：无登录速率限制、无账户锁定、无验证码、无设备/IP 风控，面临暴力破解风险。
4. **部署管理权限过大**：单一管理员即可触发生产部署、实时查看日志，缺乏审批、回滚、维护窗口等运营控制。
5. **ETL 可观测性停留在表层**：仅展示最近一次运行状态，缺少历史趋势、告警通道、自动重试与数据质量监控。
6. **通知配置缺少运营视角**：完全按用户隔离，管理员无法查看/维护全局通知，缺少事件类型、模板、升级策略。

本报告共列出 **22 项问题/建议**，其中 **P0 7 项**、**P1 10 项**、**P2 5 项**。建议按优先级分 sprint 修复。

---

## 二、问题清单与修复建议

### 2.1 权限模型与访问控制

#### P1-01：权限模型只有 admin/user 两个角色，无法支撑运营分工
- **位置**：
  - 后端：`app/models/user.py`（`role` 字段为 `String(20)`，仅 `admin|user`）
  - 后端：`app/schemas/user.py`（`role` 校验 regex `^(admin|user)$`）
  - 前端：`web/src/pages/AdminUsers/index.tsx`（`ROLE_OPTIONS` 仅两项）
  - 前端：`web/src/App.tsx`（`AdminRouteGuard` 仅判断 `role === 'admin'`）
- **问题描述**：
  平台角色体系只有管理员和普通用户。无法定义"运维管理员"（只看部署/ETL，不能改用户）"数据管理员"（管理数据管道，不能触发生产部署）"只读审计员"等角色。所有管理员拥有相同的最高权限。
- **运营影响**：
  在团队规模扩大或外包运维场景下，权限无法最小化，任何管理员账号泄露或被误操作都可能导致全平台风险。也不符合最小权限原则（PoLP）。
- **建议修复方案**：
  1. 将角色模型扩展为权限矩阵（RBAC）：引入 `roles` 表与 `permissions` 表，或至少预定义 `super_admin`、`ops_admin`、`data_admin`、`auditor`、`user` 等角色。
  2. 将权限粒度拆分为 `users:read/write`、`deployments:trigger/read`、`etl:read/control`、`notifications:read/write`、`system:config` 等。
  3. `require_admin` 依赖改为 `require_permission(...)`；前端 `AdminRouteGuard` 同步检查具体权限。
- **优先级**：P1

#### P1-02：无用户级数据隔离（所有用户共享全量数据）
- **位置**：
  - 全平台业务接口：以 `pools`、`favorites`、`strategies` 为例，虽有 `user_id` 字段，但大量数据类接口（ETF、行情、宏观、报告）默认返回全量。
  - 文档：`docs/dev-notes/20260622-系统平台功能逻辑说明手册.md` 角色表也仅按功能区分。
- **问题描述**：
  当前平台更像是"单租户内部工具"，没有用户数据隔离。普通用户可以看到其他用户的池、策略、报告、通知配置等，虽然前端可能隐藏入口，但后端接口并未按用户过滤。
- **运营影响**：
  如果平台未来对外部客户或不同团队开放，存在数据越权风险；即使内部使用，也不利于分团队管理。
- **建议修复方案**：
  1. 在 `User` 模型中增加 `tenant_id` / `org_id` 或 `data_scope` 字段。
  2. 在 `get_current_user` 依赖中注入 `user.tenant_id`，所有业务查询默认追加 `tenant_id=...` 过滤。
  3. 对 pools、strategies、backtests、reports、notification_config 等明确按 `user_id` 过滤的接口，补充 `tenant_id` 过滤条件。
- **优先级**：P1

---

### 2.2 用户生命周期管理

#### P0-01：管理员可在后台删除/重置自己，且后端未做保护
- **位置**：
  - 后端：`app/api/v1/admin_users.py`（`update_user`、`delete_user`、`reset_password` 仅检查 `require_admin`，不检查目标是否为自己）
  - 前端：`web/src/pages/AdminUsers/index.tsx`（仅 UI 按钮 `disabled={self}`，属于客户端控制）
- **问题描述**：
  前端虽然禁用了"编辑/重置/删除自己"按钮，但后端接口没有限制。通过直接调用 API，管理员可以删除自己、重置自己的密码，甚至把自己角色改为 `user` 从而失去管理员权限。如果这是最后一个 admin，会导致平台无法管理。
- **运营影响**：
  误操作或恶意脚本可能导致管理员自锁，生产环境无法恢复（除非走 `docker exec` 密码重置 runbook，成本高）。
- **建议修复方案**：
  1. 后端在 `update_user`/`delete_user`/`reset_password` 中增加 `if user.id == current_user.id: raise HTTPException(400, "不能操作自己的账号")`。
  2. 至少保留一个 `super_admin` 或 `admin` 不可被删除/降级：删除/降级时检查剩余管理员数量。
  3. 如确实需要管理员修改自己信息，应提供单独的 `/me/change-password` 等接口。
- **优先级**：P0

#### P0-02：用户密码策略过弱，且无密码历史/过期机制
- **位置**：
  - 后端：`app/schemas/user.py`（`password` 仅 `min_length=6`）
  - 后端：`app/api/v1/admin_users.py`（`reset_password` 未校验复杂度）
  - 脚本：`scripts/create_user.py`、 `scripts/seed_users.py`（无复杂度校验）
- **问题描述**：
  仅要求密码长度 >= 6，无大小写、数字、特殊字符要求，也无常见弱密码黑名单。重置密码时同样不校验。没有密码过期、历史密码（防止循环使用）、首次登录强制改密机制。
- **运营影响**：
  金融系统弱密码极易被字典/爆破攻击。当前策略不符合等保/金融行业安全基线。
- **建议修复方案**：
  1. 在 Pydantic 校验中增加密码复杂度：至少 8 位，包含大小写字母、数字、特殊字符中的 3 类；可使用 `zxcvbn` 或自定义规则。
  2. 增加 `password_history` 字段/表，重置密码时禁止与最近 N 次相同。
  3. 增加 `password_changed_at` 字段，超期（如 90 天）强制修改；首次登录或管理员重置后强制改密。
  4. 后台提供"密码策略"配置开关，避免一刀切影响本地开发。
- **优先级**：P0

#### P1-03：无用户登录/操作审计，无法满足合规要求
- **位置**：
  - 后端：无 `audit_log` / `login_history` 相关模型
  - 前端：`web/src/pages/AdminUsers/index.tsx` 无审计入口
- **问题描述**：
  平台没有记录用户何时登录、从哪个 IP、什么设备、做了什么管理操作（创建用户、重置密码、触发部署、修改配置等）。也无法查看登录失败记录、异常登录地告警。
- **运营影响**：
  金融/投研平台通常需要满足审计与合规要求。出现安全事件时无法溯源；无法发现异常登录或内部滥用。
- **建议修复方案**：
  1. 新增 `audit_log` 表，字段至少包含 `user_id`、`action`、`resource_type`、`resource_id`、`ip_address`、`user_agent`、`timestamp`、`status`、`details`。
  2. 记录关键事件：登录成功/失败、密码修改、用户 CRUD、角色变更、部署触发、ETL 手动干预、通知配置变更、数据导出等。
  3. 提供 `/admin/audit-logs` 页面，支持按时间、用户、action 筛选、导出 CSV/JSON。
  4. 异步写入审计日志（避免阻塞请求），敏感字段脱敏。
- **优先级**：P1

#### P1-04：缺少用户自助改密和个人资料管理
- **位置**：
  - 后端：`app/api/v1/auth.py` 无 `/me/password` 等接口
  - 前端：用户头像下拉菜单仅有模式切换、主题、退出登录，无"个人设置"
- **问题描述**：
  用户无法自行修改密码，必须联系管理员重置。管理员重置密码后也没有强制改密流程，密码可能被管理员知晓。
- **运营影响**：
  增加管理员工作负担，降低安全性（管理员知道用户密码），也不符合用户隐私保护要求。
- **建议修复方案**：
  1. 新增 `POST /auth/me/change-password`（需要旧密码验证）。
  2. 新增 `GET/PUT /auth/me/profile`（用户名、邮箱、昵称等）。
  3. 前端个人头像下拉菜单增加"账号设置"入口，管理员可保留额外字段（如邮箱）编辑权限。
- **优先级**：P1

#### P1-05：用户模型无邮箱、手机号、真实姓名等运营字段
- **位置**：
  - 后端：`app/models/user.py`（仅 `username`、 `password_hash`、 `role`、 `is_active`）
  - 前端：`web/src/pages/AdminUsers/index.tsx`（仅显示用户名、角色、状态）
- **问题描述**：
  用户表只有用户名，没有邮箱、手机号、部门、备注、最后登录时间等运营必需字段。管理员也无法通过邮件联系用户或做密码找回。
- **运营影响**：
  无法做通知邮件发送（通知配置里需要手动填收件人），无法做密码找回，无法做用户分层管理。
- **建议修复方案**：
  1. 在 `users` 表增加 `email`、`phone`、`display_name`、`department`、`last_login_at`、`last_login_ip`、`notes` 等字段。
  2. 管理员后台用户列表支持展示这些字段并提供编辑入口。
  3. 登录成功后更新 `last_login_at` / `last_login_ip`。
- **优先级**：P1

---

### 2.3 登录与认证安全

#### P0-03：登录接口无速率限制、无验证码、无账户锁定
- **位置**：
  - 后端：`app/api/v1/auth.py`（`login` 端点无任何限流）
  - 配置：`app/config.py`（无相关配置项）
  - 依赖：仓库中无 `slowapi`/`Limiter` 等限流库
- **问题描述**：
  `/auth/login` 对失败登录次数没有任何限制，攻击者可进行暴力破解或密码喷洒。Redis 存在但未被用于登录失败计数。
- **运营影响**：
  弱密码 + 无限尝试 = 高概率账号被攻破。金融系统这是高危风险。
- **建议修复方案**：
  1. 使用 Redis 记录 `failed_login:{username}` 和 `failed_login:{ip}`，失败 5 次后锁定 15 分钟。
  2. 或引入 `slowapi` 对 `/auth/login` 做全局/按 IP 速率限制（如 10 次/分钟）。
  3. 连续失败多次后要求图形验证码或邮件验证码（MFA 第一步）。
  4. 登录接口返回通用错误信息，不区分"用户名不存在"和"密码错误"，防止用户枚举。
- **优先级**：P0

#### P0-04：登录页禁用密码管理器 autofill，削弱安全与用户体验
- **位置**：
  - 前端：`web/src/pages/Login.tsx`（`autoComplete="off"` 及 `data-1p-ignore` / `data-bwignore` / `data-lpignore` 等属性）
- **问题描述**：
  登录页刻意阻止浏览器和密码管理器自动填充。虽然意图是避免开发时 credential 混乱，但会让用户倾向于使用简单、可记忆密码，反而降低安全性。
- **运营影响**：
  用户可能设置弱密码并手动输入；企业场景下无法使用 1Password/Bitwarden 等密码管理器，降低安全基线。
- **建议修复方案**：
  1. 移除 `autoComplete="off"` 和 `data-*-ignore` 属性；用户名使用 `autoComplete="username"`，密码使用 `autoComplete="current-password"`。
  2. 若必须抑制开发环境 autofill，可通过环境变量 `APP_ENV=development` 条件控制，生产环境必须允许。
- **优先级**：P0

#### P1-06：无多因素认证（MFA）与设备管理
- **位置**：
  - 后端：`app/models/user_device.py`（只有 `device_name`、 `platform`、 `push_token`，无信任设备/多设备撤销）
  - 后端：`app/api/v1/auth.py`（无 TOTP/OTP 相关接口）
- **问题描述**：
  平台仅依赖密码单因素认证。管理员账号一旦被钓鱼或撞库，可直接进入后台。也没有"可信设备"或"异地登录提醒"。
- **运营影响**：
  管理员账号是高价值目标，缺少 MFA 是金融系统的重大合规与安全缺口。
- **建议修复方案**：
  1. 为 `users` 表增加 `mfa_secret` / `mfa_enabled` 字段，支持 TOTP（Google Authenticator/Authy）。
  2. 新增 `/auth/mfa/setup`、`/auth/mfa/verify` 接口；管理员角色强制启用 MFA。
  3. 增加"可信设备"管理：首次在新设备登录时邮件/OTP 验证，登录后保留设备 token，支持用户在后台撤销设备。
- **优先级**：P1

#### P1-07：Token/会话管理缺少全局撤销能力
- **位置**：
  - 后端：`app/api/v1/auth.py`（`logout` 仅黑名单当前 access token 的 jti，refresh token 未全局撤销）
  - 后端：`app/api/deps.py`（`get_current_user` 检查 Redis 黑名单，但无"用户级 token 版本号"机制）
- **问题描述**：
  当用户密码被改、账号被禁用、或管理员怀疑账号泄露时，无法一键撤销该用户的所有已登录 token。只能等待 15 分钟 access token 过期或逐个设备登出。
- **运营影响**：
  安全事件响应慢。例如管理员重置用户密码后，该用户的旧 token 仍可能继续访问平台。
- **建议修复方案**：
  1. 在 `users` 表增加 `token_version`（或 `password_changed_at`）字段，登录时写入 JWT；每次验证时比对。
  2. 修改密码、重置密码、禁用账号、撤销 MFA 时递增 `token_version`，使所有旧 token 失效。
  3. 提供管理员"强制下线用户"功能，可撤销指定用户的所有 refresh token 与已签发 access token。
- **优先级**：P1

---

### 2.4 部署管理可观测性

#### P0-05：手动部署按钮缺乏审批与二次确认，单管理员即可触发生产变更
- **位置**：
  - 后端：`app/api/v1/deployments.py`（`api_trigger_deploy` 仅 `require_admin`）
  - 前端：`web/src/pages/AdminDeployments/index.tsx`（`handleTrigger` 直接调用，仅 `message.success`）
  - 工作流：`.github/workflows/deploy.yml`（`workflow_dispatch` 也支持手动触发）
- **问题描述**：
  任何管理员登录后，点击"手动部署"即可触发 GitHub Actions 生产部署。没有二次确认弹窗、没有变更审批、没有维护窗口/冻结期检查。没有回滚能力。
- **运营影响**：
  误触、内部威胁、账号被盗都可能导致未经评审的生产变更。金融行业通常要求变更管理（Change Management）和双人复核。
- **建议修复方案**：
  1. 前端增加"确认部署"二次弹窗，显示当前分支/HEAD、变更摘要（git log）、预计影响。
  2. 后端增加"部署窗口"检查：非维护窗口禁止部署（可配置）。
  3. 引入"审批模式"：关键环境部署需要另一名管理员在审批表（`deployment_approvals`）中确认；单人审批模式可通过配置关闭，但默认开启。
  4. 保留上一个 HEAD，触发部署时记录 `previous_head`，支持一键回滚 API。
- **优先级**：P0

#### P0-06：实时日志 SSE 使用 URL 参数传 token，存在泄露风险
- **位置**：
  - 后端：`app/api/v1/deployments.py`（`_require_admin_for_sse` 从 `request.query_params.get("token", "")` 读取 JWT）
  - 前端：`web/src/hooks/useDeployments.ts`（需确认实现，未读到源文件，但 SSE 通常只能 URL 传参）
- **问题描述**：
  EventSource 无法设置自定义 Header，因此将 JWT 放在 URL 查询参数中。该 URL 会被浏览器历史、代理日志、服务器访问日志、CDNs 记录下来，高敏感的管理员 token 可能泄露。
- **运营影响**：
  一旦日志或访问日志被未授权人员访问，可能拿到管理员 token 进而操作后台。日志本身也可能包含敏感信息。
- **建议修复方案**：
  1. 为 SSE 使用短期、一次性 `stream_token`（如 30 秒有效、绑定到用户+容器），而非长期 access token。
  2. 或者使用 `fetch` + `ReadableStream` 代替原生 EventSource，从而支持 Header 中的 Authorization Bearer token。
  3. 在 Nginx/代理层对 `/api/v1/admin/logs/stream` 的访问日志做关闭或脱敏处理。
- **优先级**：P0

#### P1-08：容器健康与日志功能存在硬编码与安全边界问题
- **位置**：
  - 后端：`app/services/deployment_service.py`（硬编码容器名前缀 `alloyresearch-*`，且直接访问 Docker Unix Socket）
  - 生产配置：`deploy/aliyun-ecs/docker-compose.yml`（backend 与 celery-worker 均挂载 `/var/run/docker.sock:/var/run/docker.sock:ro`）
- **问题描述**：
  1. 前端 `AdminDeployments` 中容器下拉选项硬编码 `alloyresearch-backend`、`alloyresearch-postgres` 等；如果容器改名或扩展服务，UI 无法自适应。
  2. backend 容器挂载 Docker socket 后，即使只读 `ro`，也相当于给应用容器开了"容器逃逸"的口子；部署服务可通过 Docker API 启停容器。
- **运营影响**：
  后端服务被入侵后，攻击者可利用 Docker socket 横向移动、提权、影响生产环境。容器列表硬编码也限制了扩展性。
- **建议修复方案**：
  1. 健康/日志接口从后端服务自身采集改为调用独立"运维 sidecar"或暴露 Prometheus/Docker 日志驱动到 Loki/Fluentd，避免给业务容器 Docker socket 权限。
  2. 如果必须保留 Docker API，使用只读权限+token 鉴权的 Docker 代理，而非直接 mount socket。
  3. 容器列表从 API 动态获取（`get_container_stats` 已返回 `name`），前端下拉选项改为动态加载。
- **优先级**：P1

#### P1-09：部署历史只有 GitHub Actions 数据，缺少回滚/变更摘要/审批记录
- **位置**：
  - 后端：`app/api/v1/deployments.py`（仅 list GitHub Actions runs、get run logs、trigger dispatch）
  - 前端：`web/src/pages/AdminDeployments/index.tsx`（展示 runs 列表、健康、日志）
- **问题描述**：
  部署管理页面缺少回滚按钮、缺少变更摘要（commit diff）、缺少审批记录、缺少维护窗口状态。失败时通知也仅写本地日志（`.github/workflows/deploy.yml` 第 6 步）。
- **运营影响**：
  出现部署故障时，运营人员需要登录服务器/GitHub 手动查看，无法一站式处理；缺少回滚能力会延长 MTTR。
- **建议修复方案**：
  1. 新增 `deployments` 本地表，记录每次部署触发人、审批人、分支/HEAD、前序 HEAD、状态、回滚命令、失败原因。
  2. 提供 `POST /admin/deployments/{id}/rollback` 接口，回滚到上一个 HEAD。
  3. 部署失败时除了本地日志，调用平台通知配置中的告警渠道发送告警。
  4. 页面增加"变更摘要"和"一键回滚"按钮。
- **优先级**：P1

---

### 2.5 ETL 运维看板

#### P0-07：ETL 状态看板缺少告警通道与失败自动通知
- **位置**：
  - 后端：`app/api/v1/etl_status.py`（仅聚合状态，无告警逻辑）
  - 前端：`web/src/pages/ETLOpsDashboard/index.tsx`（仅展示状态，无告警配置）
- **问题描述**：
  看板只显示任务最近一次运行状态和数据新鲜度，没有与通知系统联动的告警机制。任务失败或数据过期时不会自动通知管理员，需要人工反复查看页面。
- **运营影响**：
  数据 Pipeline 是投研平台核心，一旦失败或延迟，下游所有策略、信号、报告都会出错。缺少告警会导致故障发现时间（MTTD）变长。
- **建议修复方案**：
  1. 在 `notification_config` 或新增 `alert_rule` 表中配置 ETL 告警规则：任务失败、数据陈旧超过 N 小时、连续失败 N 次等。
  2. 在 ETL 调度器（`app/core/scheduler.py`）或 `etl_status` 后台任务中触发告警，调用 `NotificationService` 发送。
  3. 前端看板增加"告警规则"入口，显示当前告警状态与历史告警记录。
- **优先级**：P0

#### P1-10：数据新鲜度检查口径不完整，且陈旧阈值不精确
- **位置**：
  - 后端：`app/api/v1/etl_status.py`（`_latest_bar_date` 仅检查 `InstrumentDailyBar` + `ETFInfo`）
  - 后端：`_TRACKED_JOBS` 包含 A股个股、美股、加密、宏观等多种数据源，但新鲜度只看 ETF/股票的日 K 线
- **问题描述**：
  1. 数据新鲜度仅基于 `instrument_daily_bar` 的 ETF 日线，不检查个股、加密货币、宏观指标、财报、新闻、基金流等数据。
  2. "陈旧"阈值固定为 >3 天，没有考虑交易日历（例如周一到周三仍是 3 天，但周五到周一可能超过 3 天但仍是"1 个交易日"）。
- **运营影响**：
  可能误判数据新鲜度，或遗漏其他数据源落后。ETL 任务明明在跑，但看板不能真实反映全平台数据健康。
- **建议修复方案**：
  1. 按数据源/表维护新鲜度检查器（stocks、crypto、macro、news、fund_flow、etf_holdings 等），汇总为多维健康度。
  2. 使用交易日历计算"交易日"间隔，而非自然日；或允许每个任务配置自己的最大允许延迟（如"T+1 08:00"）。
  3. 增加"预期下次运行时间"与"实际延迟时长"展示。
- **优先级**：P1

#### P1-11：ETL 看板只展示最后一次运行，缺少历史趋势与排障信息
- **位置**：
  - 后端：`app/api/v1/etl_status.py`（`_build_task_summary` 只取 `ETLLog` 最新一条）
  - 前端：`web/src/pages/ETLOpsDashboard/index.tsx`（只有任务列表与总体健康）
- **问题描述**：
  看板无法查看任务历史运行曲线（成功率、耗时、影响行数趋势），失败时也难以快速查看日志、重试任务。
- **运营影响**：
  运营排障困难，无法判断某个任务是偶发失败还是慢性故障，也无法评估 ETL 性能趋势。
- **建议修复方案**：
  1. 新增 `GET /admin/etl-status/jobs/{name}/history` 接口，返回最近 N 次运行记录。
  2. 前端增加任务详情抽屉/页面，展示历史状态、耗时、影响行数折线图、错误日志。
  3. 提供"手动重试"按钮，调用对应 pipeline 的 run 方法（需加锁与排队控制）。
- **优先级**：P1

---

### 2.6 通知配置

#### P1-12：通知配置完全按用户隔离，管理员无法维护全局通知
- **位置**：
  - 后端：`app/api/v1/notifications.py`（所有接口依赖 `get_current_user`，`service.get_configs(user_id=...)`）
  - 后端：`app/services/notification_service.py`（`get_configs` 按 `user_id` 过滤）
  - 前端：`web/src/pages/NotificationConfig/index.tsx`（普通用户视角）
- **问题描述**：
  通知配置属于用户个人资产，管理员无法查看、编辑或删除其他用户的通知配置。对于全局告警（如 ETL 失败、部署失败），需要有一个管理员可维护的"系统级通知配置"或"全局告警渠道"。
- **运营影响**：
  关键系统告警（ETL 失败、部署失败）没有统一出口；用户离职或禁用后，其通知配置失效，无法持续发送告警。
- **建议修复方案**：
  1. 在 `notification_config` 表增加 `scope` 字段（`personal`/`system`/`tenant`），系统级配置仅 admin 可维护。
  2. 管理员可查看所有用户配置（只读或维护），支持为整个平台设置告警渠道。
  3. 通知发送时，系统级事件使用系统配置，用户级报告使用用户配置。
- **优先级**：P1

#### P1-13：通知缺少事件类型、模板与升级策略
- **位置**：
  - 后端：`app/services/notification_service.py`（仅支持 `webhook` 和 `email` 两种渠道，内容固定为报告通知或测试文本）
  - 前端：`web/src/pages/NotificationConfig/index.tsx`（仅配置渠道，无事件订阅）
- **问题描述**：
  用户无法选择订阅哪些事件（ETL 完成、报告生成、ETL 失败、部署失败、价格异动等），也没有模板管理。每个通知内容都是硬编码字符串，无法自定义。
- **运营影响**：
  通知粒度太粗，用户可能收到过多无关通知，或错过关键告警。运营也无法统一品牌模板与告警语义。
- **建议修复方案**：
  1. 引入事件类型：`report_ready`、`etl_failed`、`etl_stale`、`deploy_failed`、`price_alert` 等。
  2. 增加 `notification_templates` 表，支持按事件类型配置标题/正文模板（Markdown/HTML）。
  3. 增加升级策略：关键告警在 N 分钟未恢复时升级发送到更高优先级渠道或更多人。
- **优先级**：P1

#### P1-14：Webhook 缺少签名验证，测试接口可被滥用
- **位置**：
  - 后端：`app/services/notification_service.py`（`_send_webhook` 直接 POST，无签名）
  - 后端：`app/api/v1/notifications.py`（`test_config` 无频率限制）
- **问题描述**：
  1. Webhook 不支持企业微信/钉钉/飞书的签名验证（如企业微信需要 key、钉钉需要加签），配置可能因安全校验失败而实际不可用。
  2. `POST /notifications/configs/{id}/test` 没有限流，用户可反复点击测试，向外部服务发送大量请求，存在滥用或误触风险。
- **运营影响**：
  Webhook 容易被接收方拒绝；测试接口滥用可能影响外部服务或平台声誉。
- **建议修复方案**：
  1. 支持各平台的签名/校验机制：企业微信 key、钉钉加签、飞书 sign/timestamp。
  2. 对 `test_config` 增加速率限制（如每个配置 1 次/分钟，按用户 5 次/分钟）。
  3. 测试消息增加标识，避免被误认为是真实告警。
- **优先级**：P1

---

### 2.7 合规与审计

#### P2-01：无数据保留策略与 GDPR/隐私合规能力
- **位置**：
  - 全平台缺少数据保留策略配置
  - 无用户数据导出/删除接口
- **问题描述**：
  没有定义日志、通知、ETL、报告等数据的保留期限，也没有提供用户导出或删除个人数据的功能。
- **运营影响**：
  长期数据积累导致存储成本增加；如果面向外部客户，可能不符合隐私法规要求。
- **建议修复方案**：
  1. 制定并文档化数据保留策略（如审计日志 1 年、通知日志 90 天、ETL 日志 90 天）。
  2. 新增定时清理任务，按策略清理过期数据。
  3. 提供管理员/用户数据导出（JSON）和删除功能。
- **优先级**：P2

#### P2-02：CORS 配置依赖环境变量，生产默认值不安全
- **位置**：
  - 后端：`app/config.py`（`cors_origins` 默认空，生产环境 origin 为空列表，但方法允许所有方法/头）
  - 后端：`app/main.py`（CORS 中间件使用 `allow_methods=["*"]`、`allow_headers=["*"]`）
- **问题描述**：
  生产环境默认 CORS origin 为空，理论上只允许同源。但如果运维人员误配 `CORS_ORIGINS=*`，生产环境也会接受所有跨源请求（虽然代码会去掉通配符，但配置流程本身无校验）。同时 `allow_methods`/`allow_headers` 为 `*` 也过于宽松。
- **运营影响**：
  配置错误可能导致跨域攻击或 credentials 泄露。
- **建议修复方案**：
  1. 启动时校验 CORS 配置：若 `APP_ENV=production` 且 `CORS_ORIGINS` 未设置，打印 warning 或拒绝启动。
  2. 生产环境默认只允许特定 origin，且 `allow_methods`/`allow_headers` 应限制为实际使用的值。
  3. 在 `/health` 或启动日志中暴露 CORS 配置状态，便于审计。
- **优先级**：P2

#### P2-03：Swagger/OpenAPI 文档在生产环境暴露
- **位置**：
  - 后端：`app/main.py`（`docs_url="/docs"`、`redoc_url="/redoc"`）
- **问题描述**：
  FastAPI 默认文档在生产环境也对外开放，可能暴露接口结构、schema、测试表单，增加攻击面。
- **运营影响**：
  攻击者可利用 `/docs` 快速了解所有接口，进行定向攻击。
- **建议修复方案**：
  1. 生产环境禁用 `docs_url`/`redoc_url`，或将其限制为内网/管理员访问。
  2. 或增加 HTTP Basic Auth 保护 `/docs`。
- **优先级**：P2

---

### 2.8 运营日常缺失功能

#### P2-04：缺少系统级配置管理（维护模式、功能开关、数据源配置）
- **位置**：
  - 后端：`app/models/etl.py` 有 `DataSourceConfig` 模型，但无管理 API
  - 无 `feature_flag` / `system_setting` 模型
- **问题描述**：
  管理员无法通过 Web 界面配置数据源开关、调整调度任务、开启维护模式或灰度功能。所有操作需要改环境变量或进数据库。
- **运营影响**：
  日常运营效率低，故障时需要手动改配置或重启服务，增加 MTTR。
- **建议修复方案**：
  1. 新增 `system_settings` 表，支持维护模式、全局公告、功能开关等。
  2. 提供 `/admin/system-settings` 页面，管理员可在线修改并记录审计日志。
  3. 提供 `/admin/data-sources` 页面，管理 `DataSourceConfig` 的启用/禁用、API key、rate limit。
  4. 提供 `/admin/scheduler` 页面，查看 APScheduler 任务、暂停/恢复/手动触发任务。
- **优先级**：P2

#### P2-05：缺少用户支持与模拟登录功能
- **位置**：
  - 无相关接口与页面
- **问题描述**：
  管理员无法以用户视角查看平台（用户模拟/impersonation），排查用户问题时需要知道用户密码或让用户共享屏幕。
- **运营影响**：
  用户支持效率低，且可能涉及用户隐私泄露。
- **建议修复方案**：
  1. 提供"模拟登录"功能：管理员可在用户管理页点击"以该用户登录"，生成一次性、只读/受限 token，并记录审计日志。
  2. 模拟会话在超时或退出后自动失效，不可执行敏感操作（如交易、部署）。
- **优先级**：P2

#### P2-06：系统文档中账号体系描述已过时
- **位置**：
  - `docs/dev-notes/20260622-系统平台功能逻辑说明手册.md` 第 1.3 节称"平台内置 5 个账号"，且提到 `AuthSettings.USERS`。
  - `docs/dev-notes/20260624-user-account-login-flow.md` 第 5 节称 `is_active` 在 token 校验阶段未检查，但当前 `app/api/deps.py` 已检查。
- **问题描述**：
  系统手册中的账号描述与当前代码不符（已改为环境变量+数据库），且对禁用账号的即时生效描述已不准确。
- **运营影响**：
  新入职开发/运维可能被文档误导，增加沟通成本。
- **建议修复方案**：
  1. 更新系统手册中用户账号章节，说明当前基于数据库+环境变量初始化的模式。
  2. 移除或修正关于 `is_active` 未生效的描述，并说明 token 版本号机制（如后续实现）。
  3. 建立代码变更后同步更新运行手册的流程（可参考 MEMORY.md 中"永远更新 runbook 与决策日志"）。
- **优先级**：P2

#### P2-07：缺少缓存与后台任务管理工具
- **位置**：
  - 无 `/admin/cache`、`/admin/tasks` 页面
- **问题描述**：
  平台使用 Redis 缓存和 Celery 任务，但管理员无法查看缓存命中率、清除缓存、查看 Celery 队列状态或重试失败任务。
- **运营影响**：
  数据更新后缓存未失效、Celery 任务堆积等问题排查困难。
- **建议修复方案**：
  1. 提供 `/admin/cache` 页面：按前缀搜索 key、查看 TTL、删除 key/模式。
  2. 提供 `/admin/tasks` 页面：查看 Celery 队列长度、worker 状态、失败任务、手动重试。
- **优先级**：P2

#### P2-08：用户描述的通知配置路径与实际路由不一致
- **位置**：
  - 用户要求审查 `/notification-config`，但代码中实际路由为 `/notifications`（`web/src/routes.tsx` 第 155 行）。
- **问题描述**：
  路径不一致可能导致文档、培训材料或用户沟通时出错。`/notification-config` 并不是当前有效的路由。
- **运营影响**：
  低，但会造成沟通混乱。
- **建议修复方案**：
  1. 统一使用 `/notifications` 作为标准路径，并在文档中明确。
  2. 如需保留 `/notification-config` 作为别名，可添加 `Navigate` 重定向。
- **优先级**：P2

---

## 三、问题优先级总览

| 编号 | 类别 | 问题 | 优先级 |
|------|------|------|--------|
| P0-01 | 用户生命周期 | 管理员可删除/重置自己，后端无保护 | P0 |
| P0-02 | 用户生命周期 | 密码策略过弱，无历史/过期机制 | P0 |
| P0-03 | 登录安全 | 登录无速率限制/验证码/账户锁定 | P0 |
| P0-04 | 登录安全 | 登录页禁用密码管理器 autofill | P0 |
| P0-05 | 部署管理 | 手动部署缺乏审批与二次确认 | P0 |
| P0-06 | 部署管理 | SSE 日志使用 URL 参数传 token | P0 |
| P0-07 | ETL 运维 | 缺少告警通道与失败自动通知 | P0 |
| P1-01 | 权限模型 | 只有 admin/user 两个角色 | P1 |
| P1-02 | 权限模型 | 无用户级数据隔离 | P1 |
| P1-03 | 用户生命周期 | 无登录/操作审计日志 | P1 |
| P1-04 | 用户生命周期 | 无用户自助改密 | P1 |
| P1-05 | 用户生命周期 | 用户表缺少邮箱/最后登录等字段 | P1 |
| P1-06 | 登录安全 | 无 MFA/多因素认证 | P1 |
| P1-07 | 登录安全 | 缺少全局 token 撤销能力 | P1 |
| P1-08 | 部署管理 | 容器硬编码与 Docker socket 挂载风险 | P1 |
| P1-09 | 部署管理 | 缺少回滚/变更摘要/审批记录 | P1 |
| P1-10 | ETL 运维 | 数据新鲜度口径不完整、阈值不精确 | P1 |
| P1-11 | ETL 运维 | 只看最后一次运行，无历史趋势 | P1 |
| P1-12 | 通知配置 | 通知配置完全按用户隔离，无全局配置 | P1 |
| P1-13 | 通知配置 | 缺少事件类型、模板、升级策略 | P1 |
| P1-14 | 通知配置 | Webhook 无签名验证，测试接口可滥用 | P1 |
| P2-01 | 合规审计 | 无数据保留策略与 GDPR 能力 | P2 |
| P2-02 | 合规审计 | CORS 配置依赖环境变量，生产默认需加固 | P2 |
| P2-03 | 合规审计 | Swagger 文档在生产环境暴露 | P2 |
| P2-04 | 运营功能 | 缺少系统级配置管理 | P2 |
| P2-05 | 运营功能 | 缺少用户支持与模拟登录 | P2 |
| P2-06 | 运营功能 | 系统文档账号体系描述过时 | P2 |
| P2-07 | 运营功能 | 缺少缓存与后台任务管理工具 | P2 |
| P2-08 | 运营功能 | 通知配置路径与实际路由不一致 | P2 |

---

## 四、已观察到的好实践

在审查过程中，也注意到以下值得肯定的点，应保留：

1. **认证设计**：使用 bcrypt 存储密码、JWT 15 分钟短期有效、refresh token 30 天并 rotation、Redis 黑名单实现登出、token 含 jti。
2. **前端路由保护**：`App.tsx` 中 `RequireAuth` + `AdminRouteGuard` 对管理员路由做保护，侧边栏按角色动态过滤 `admin` 分组。
3. **日志脱敏**：`deployment_service.py` 的 `_sanitize` 函数对密码、token、secret 等做正则脱敏。
4. **健康检查**：`/health` 严格检查 DB 和 Redis，失败返回 503，便于负载均衡和监控。
5. **部署失败通知**：`.github/workflows/deploy.yml` 虽尚未接入 webhook，但已预留 `DEPLOY_ALERT_WEBHOOK` 和失败日志记录。
6. **代码注释与 runbook**：关键修复（如 2026-07-01 登录响应缺少 `id`）有测试和 runbook 记录，符合"永远更新 runbook 与决策日志"的要求。

---

## 五、修复路线图建议

### Sprint 1（安全基线，P0 必做）
- 后端阻止管理员自操作（P0-01）
- 增强密码策略 + 历史/过期（P0-02）
- 登录接口速率限制 + 账户锁定（P0-03）
- 登录页恢复密码管理器 autofill（P0-04）
- 手动部署增加二次确认 + 部署窗口检查（P0-05）
- SSE token 改用短期 stream_token 或 fetch ReadableStream（P0-06）
- ETL 失败/陈旧告警接入通知渠道（P0-07）

### Sprint 2（权限与审计，P1）
- 引入 RBAC/角色扩展（P1-01）
- 数据租户/用户隔离（P1-02）
- 审计日志表 + 管理页面（P1-03）
- 用户自助改密 + 个人资料（P1-04）
- 用户表扩展字段（P1-05）
- MFA/TOTP 支持（P1-06）
- token 版本号与全局撤销（P1-07）

### Sprint 3（运维与通知，P1+P2）
- 部署管理：回滚、变更摘要、审批记录（P1-09）
- 容器列表动态化与 Docker socket 权限收紧（P1-08）
- ETL 历史趋势与手动重试（P1-11）
- 全量数据新鲜度与交易日历（P1-10）
- 通知：全局配置、事件类型、模板、Webhook 签名（P1-12、P1-13、P1-14）
- 系统设置、缓存/任务管理、模拟登录（P2-04、P2-05、P2-07）

### Sprint 4（合规加固，P2）
- 数据保留策略与清理任务（P2-01）
- CORS 与 Swagger 生产加固（P2-02、P2-03）
- 文档同步更新（P2-06、P2-08）

---

**报告生成完毕。** 本报告仅反映 2026-07-16 代码库静态审查结果，未执行任何源代码修改或部署操作。
