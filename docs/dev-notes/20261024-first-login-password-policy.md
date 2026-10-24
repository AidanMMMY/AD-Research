# 首登强制改密与统一密码策略

> 日期：2026-10-24
> 范围：管理后台用户创建/重置、用户自助改密、认证依赖、运维脚本、Web 与原生客户端、测试
> 状态：本地实现与回归完成；部署以实际生产验证为准

## 1. 需求与结论

本次实现以下行为：

- 管理员新增用户时可留空密码，后端用 `secrets` 生成 16 位随机初始密码。
- 管理员重置密码同样支持自动生成；显式密码走统一策略校验。
- 密码要求为 12–64 个 Unicode 字符，至少含一个 ASCII 英文字母和一个 ASCII 数字。
- 为避免 bcrypt 只使用前 72 字节，额外限制 UTF-8 编码不超过 72 字节。
- 用户创建或密码重置后设置 `users.must_change_password=true`，首次登录必须改密。
- 初始明文密码只在创建/重置响应中返回一次；数据库只保存 bcrypt 哈希，不写明文日志或审计。
- 改密成功后吊销全部旧 refresh token，同时给当前会话返回新 access/refresh token，避免当前浏览器在 access token 到期后掉线。

存量用户通过迁移默认值 `false` 保持原状；`seed_users.py` 的首次部署 bootstrap 行为不变。

## 2. 后端实现

### 2.1 数据模型与迁移

- `app/models/user.py`：新增 `must_change_password`，非空、服务端默认 `false`。
- `alembic/versions/b3c5d7e9f1a2_add_users_must_change_password.py`：父版本为 `e2f4a6b8c0d3`，形成单一 head `b3c5d7e9f1a2`。
- `app/services/password_policy.py`：集中密码校验和随机密码生成，供 API 与脚本复用。

### 2.2 创建、重置与自助改密

- `app/api/v1/admin_users.py`：创建/重置均可自动生成初始密码，统一设置强制改密标志；重置吊销目标用户 refresh token。
- `app/api/v1/auth.py`：登录和 `/auth/me` 返回标志；新增 `/auth/change-password`。
- 自助改密校验旧密码、拒绝弱密码和新旧密码相同，更新哈希后清除标志并轮换令牌。
- 改密接口复用登录的 Redis 限流，按 IP 与用户名计数；超限返回 429 和 `Retry-After`，成功后清除用户失败计数。

### 2.3 后端强制访问限制

强制改密不能只靠前端跳转。默认 `get_current_user` 会拒绝待改密用户访问普通 API，返回 403 而不是 401，避免 axios 把有效会话误判为过期并触发 refresh。

仅以下恢复/退出路径使用允许待改密的专用依赖：

- `GET /auth/me`
- `POST /auth/change-password`
- `POST /auth/logout`

`require_admin`、设备管理及其他受保护接口均走默认拒绝逻辑；可选认证在待改密时降级为匿名，不授予用户态权限。部署面板 SSE 的自定义 query-token admin 认证也单独补齐了相同 403 检查，避免绕过统一依赖。

### 2.4 运维脚本一致性

- `scripts/create_user.py`：复用密码策略，创建后强制首次改密。
- `scripts/reset_user_password.py`：弱密码直接拒绝；重置后设置标志并吊销全部未吊销 refresh token。
- 保留既有函数签名，未修改 `scripts/seed_users.py`。

## 3. Web 前端实现

- 新增 `/change-password` 页面，包含当前密码、新密码和确认密码。
- `RequireAuth` 以本次 `/auth/me` 响应为强制跳转依据，不再依赖可能滞后一帧的持久化用户状态；数据未返回前不挂载受保护页面。
- 改密成功后先保存新令牌，再同步用户状态与 TanStack Query 的 `me` 缓存，最后跳转 dashboard。
- 用户管理页可留空自动生成密码；一次性密码弹窗支持复制，关闭后清除本地明文。
- 创建/重置弹窗接入 pending 状态，防止双击重复请求和请求期间关闭。
- 一次性密码交给本地展示 state 后立即 reset mutation，并设置 `gcTime: 0`，避免明文留在 TanStack mutation cache。
- 前后端共享相同规则语义；前端用 `Array.from()` 按 Unicode code point 计数，避免 UTF-16 长度与 Python 不一致。
- `me` 查询按 access token 隔离且不再使用 5 分钟身份缓存；登出清理身份查询，防止同标签页换账号复用上一用户响应。
- 待改密页面不挂载全局 AI Help Drawer，避免发出必然被 403 的 AI 请求。

### 3.1 原生客户端兼容

两套现有 Swift 客户端均同步了认证契约，避免后端启用强制门控后原生端无法恢复账号：

- 旧 `ios/ADResearch` 与现行 `native/ADResearch` 均在登录和 `/auth/me` 会话恢复中识别 `must_change_password`，缺少该字段的旧响应按 `false` 解码。
- 待改密用户进入专用改密页；改密成功并持久化后端返回的新 access/refresh token 后，才清除标志并进入主界面。native 的令牌写入 Keychain 和 `APIClient`，旧 iOS 写入其既有会话存储。
- 改密页包含旧密码、新密码、确认密码、本地策略校验、后端错误展示与退出登录；native 在提交和退出期间禁用冲突操作。
- native `RootView` 在主 Shell 前分流，会话恢复等待 `/auth/me` 返回，避免在线恢复时先闪现主界面。
- 保留 native 既有离线恢复策略：`/auth/me` 非 401 失败时允许本地会话进入 Shell，但所有普通后端 API 仍由服务端 403 门控，不能借离线状态修改数据或取得用户态 API 权限。

## 4. 审查发现与处理

独立代码审查未发现初始明文密码持久化或正常改密主流程的 Critical 问题。审查后补齐了：

1. 后端待改密访问限制，而非仅前端跳转。
2. 改密旧密码校验的速率限制。
3. 运维脚本绕过密码策略、强制标志和 refresh 吊销的问题。
4. fresh `/me` 返回前的 stale 状态与受保护页面提前挂载。
5. 创建/重置弹窗重复提交导致展示密码与最终哈希可能不一致。
6. mutation cache 明文保留、孤立 Unicode surrogate 导致 500、前后端字符计数不一致。
7. 新 access 经过真实认证依赖访问受保护端点、相同新旧密码、CLI 等回归测试。
8. 部署日志 SSE 自定义认证的待改密绕过。
9. 同标签页跨账号复用旧 `me` 缓存，以及强制改密页仍挂载 AI Drawer。
10. 旧 iOS 与现行 native 客户端的强制改密恢复路径，避免只修 Web 后原生端契约失效。
11. native 最终复审发现自动刷新令牌的 detached 回写可能覆盖改密新令牌；改为等待持久化后再重放请求，并以模拟 401→refresh→改密的延迟回调测试完成红绿验证。两套 Swift 客户端同时将密码长度改为 Unicode scalar 计数，与后端 code point 口径一致。

## 5. 验证记录

主会话独立执行：

- 密码策略、SSE 与登录相关后端测试：34 passed。
- 后端全量：1951 passed，2 skipped。
- 前端 `check:ci`：stylelint、TypeScript、Vite production build 通过；本次改动源文件与测试的 ESLint 零 warning。全仓 `npm run lint` 仍会被未改动文件的既有 warning 阻断，不能据此宣称全仓 ESLint 通过。
- 前端 Vitest：19 个文件、96 tests 全绿。
- 旧 iOS：standalone 认证 DTO/端点/密码策略测试通过，全部 Swift 源码 `swiftc -parse` 通过。
- native：standalone 认证 DTO/端点/密码策略测试通过，全部 Swift 源码 `swiftc -parse` 通过；复用 CLT 打包流程剥除 `#Preview` 后，完整 macOS 应用源码以 `swiftc` 编译通过。新增模拟 access 过期→refresh→改密的延迟持久化回归测试，验证改密令牌不会被旧刷新回调覆盖。
- Alembic：单一 head `b3c5d7e9f1a2`。
- ruff、black、`git diff --check` 通过。

实现 agent 在最终后端改动上执行：

- 后端全量：1950 passed，2 skipped。
- black、ruff 通过。
- 密码相关修复均先复现失败，再实现到通过；关键红测包括普通/admin API 未拦截、限流未生效、CLI 弱密码/标志/refresh 吊销缺失及 surrogate 500。

## 6. 已知边界与后续事项

- 本次承诺吊销 refresh token，没有引入 session version/JWT 安全纪元。正常自助改密后，其他会话已经签发的旧 access token 仍保留既有最长 15 分钟有效期；极端并发 refresh 竞态也未在本次重做。
- 管理员重置后会设置强制改密标志，因此旧 access 即使未过期，也会被普通 API 的待改密检查以 403 拒绝。
- 一次性密码弹窗关闭后无法再次查看；如未保存，只能再次重置。
- 原生端未执行完整 `xcodebuild`、iOS SDK 编译、模拟器/真机 UI 或真实后端联调；当前验证不替代这些发布前验收。native 离线恢复可展示本地 Shell，但在线 API 仍由后端强制门控。
- 旧 `ios/ADResearch` 的通用 `refreshTokenIfNeeded` 既有实现只持久化新 access token，未保存后端轮换的新 refresh token；本次未扩大重写该归档候选客户端，若继续保留维护需单独修复并做完整会话验收。
- 生产部署需要重建 backend 镜像并执行 Alembic 迁移；部署后验证创建、登录、强制改密、新令牌刷新及管理 API 恢复访问的完整链路。原生客户端需另行构建/发布，不随后端部署自动更新。

## 7. 相关文档

- [Admin 密码重置 Runbook](20260701-admin-password-reset-runbook.md)
- [TLS 证书过期与自动续期](20261024-tls-cert-expiry-acme-fix.md)
