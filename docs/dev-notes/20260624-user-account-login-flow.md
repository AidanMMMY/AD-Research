# 用户账号启用与登录方式说明

> 记录当前 AD-Research 平台的账号体系、启用流程和登录校验逻辑。
> 更新日期：2026-06-24
> 最后核实更新：2026-07-21

---

## 1. 账号存储位置

所有用户都保存在 PostgreSQL 的 `users` 表里，字段包括：

| 字段 | 说明 |
|------|------|
| `id` | 自增 ID |
| `username` | 登录名，唯一 |
| `password_hash` | bcrypt 哈希后的密码 |
| `role` | `admin` 或 `user` |
| `is_active` | 是否启用（`true`/`false`） |
| `created_at` / `updated_at` | 创建/更新时间 |

---

## 2. 初始管理员怎么启用

不再写死在代码里，而是通过环境变量注入。首次部署时运行：

```bash
python scripts/seed_users.py
```

它会读取：

- `AUTH_ADMIN_USERNAME`（默认 `admin`）
- `AUTH_ADMIN_PASSWORD`（必须设置，否则报错退出）

然后在数据库里创建一个 `role=admin`、`is_active=true` 的初始管理员。

---

## 3. 普通用户怎么创建/启用

### 方式一：管理员在 Web 后台操作

登录管理员账号后，侧边栏有「用户管理」菜单，可以：

- 新增用户（设置用户名、密码、角色、是否启用）
- 修改用户角色/启用状态
- 重置密码
- 删除用户

只有 `role=admin` 能看到这个菜单和访问 `/admin/users` 页面。

### 方式二：命令行工具

使用 `scripts/create_user.py` 脚本创建：

```bash
python scripts/create_user.py --username alice --password changeme --role user
```

---

## 4. 登录流程

前端 `/login` 页面输入用户名密码后，调用：

```bash
POST /api/v1/auth/login
```

后端逻辑（见 `app/api/v1/auth.py`）：

0. **登录限流**（P0-5，2026-07-16 加入）：Redis 计数，5 次/IP/分钟 +
   20 次/用户名/小时，超限返回 429（带 `Retry-After` 头）
1. 根据 `username` 查 `users` 表
2. 用 bcrypt 校验密码，失败返回 401 `Invalid credentials`
3. 检查 `is_active`：
   - `false` → 返回 401 `User is inactive`
   - `true` → 签发**双 token**并返回
4. 前端把两个 token 存到 `localStorage`（`token` / `refresh_token`），
   后续请求带 `Authorization: Bearer <access_token>`

**Token 模型**（2026-07 改为双 token，此前是单 JWT）：

- `access_token`：短寿命 JWT，**15 分钟**（`auth.py` 中 `ACCESS_TOKEN_MINUTES`
  硬编码），payload 含 `jti` 用于注销吊销
- `refresh_token`：长寿命不透明随机串，**30 天**，数据库 `refresh_tokens`
  表只存 SHA-256 哈希
- `POST /api/v1/auth/refresh`：用 refresh token 换新 access token，并
  **轮换** refresh token（旧的一次性作废）
- `POST /api/v1/auth/logout`：把当前 access token 的 `jti` 写入 Redis
  黑名单（TTL = 剩余有效期），`get_current_user` 每次请求都查黑名单
- 前端 axios 拦截器（`web/src/api/client.ts`）在 401 时自动用 refresh
  token 换新 token 并重试，用户无感

JWT payload 包含：

```json
{
  "sub": "username",
  "role": "admin|user",
  "jti": "吊销用唯一 ID",
  "iat": "签发时间",
  "exp": "过期时间"
}
```

> **注意**：`AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` 环境变量（`AuthSettings`，
> 默认 1440）目前**没有被登录链路使用**——access token 的 15 分钟是
> `auth.py` 里的常量。改这个 env 不会改变 token 有效期。

---

## 5. 禁用账号的效果

把用户的 `is_active` 改成 `false` 后**立即生效**：

- 该用户**下次登录**返回 401 `User is inactive`
- 该用户**已持有的 access token 也会立刻失效**：`app/api/deps.py` 的
  `get_current_user` 在每次请求校验 JWT 后都会查库并检查 `is_active`
  （不满足返回 401 `Invalid or inactive user`）——2026-07 前这里不查库，
  旧文档中"token 校验阶段未检查 is_active"的说明已过时
- `POST /auth/refresh` 同样检查 `is_active`，被禁用用户无法续期

> 另：`admin_users` 写路径有"至少保留一个启用 admin"保护
> （`app/api/deps.py` 的 `assert_would_keep_at_least_one_admin`），
> 降级/禁用最后一个 admin 会返回 409。

---

## 6. 相关文件

| 文件 | 说明 |
|------|------|
| `app/models/user.py` | User 表模型 |
| `app/models/refresh_token.py` | Refresh token 表（SHA-256 哈希存储，支持轮换/吊销） |
| `app/models/user_device.py` | 用户设备表（登录后可登记设备，用于推送） |
| `app/api/v1/auth.py` | 登录、/me、/refresh、/logout、/devices 接口 |
| `app/api/v1/admin_users.py` | 管理员用户管理 CRUD |
| `app/api/deps.py` | `get_current_user`（含 is_active 检查）、`require_admin` 依赖 |
| `app/core/rate_limit.py` | 登录限流（Redis） |
| `app/schemas/user.py` / `app/schemas/auth.py` | 用户管理与认证相关 Pydantic Schema |
| `app/config.py` | `AuthSettings`（`AUTH_ADMIN_USERNAME` / `AUTH_ADMIN_PASSWORD` / `AUTH_SECRET_KEY`） |
| `scripts/seed_users.py` | 初始化管理员脚本（幂等，已存在则跳过） |
| `scripts/create_user.py` | 命令行创建用户脚本 |
| `scripts/reset_user_password.py` | 命令行重置密码脚本 |
| `web/src/pages/AdminUsers/index.tsx` | 用户管理前端页面 |
| `web/src/App.tsx` / `web/src/routes.tsx` | 管理员路由守卫（`AdminRouteGuard`，`/admin/users`） |
| `web/src/api/client.ts` | axios 拦截器：401 自动 refresh 重试 |

---

## 7. 安全建议

- 生产环境务必设置强密码的 `AUTH_ADMIN_PASSWORD`
- `AUTH_SECRET_KEY` 必须替换默认值——已有强制校验（P0-7，2026-07-16）：
  非 `development` 环境下，弱密钥（`secret`/`change-me`/历史占位符等）、
  未设置、或长度 < 32 的 `AUTH_SECRET_KEY` 会在启动时直接拒绝运行
  （`app/config.py`）
- 不要在代码或 Git 中提交 `.env` 文件
- 普通用户应通过管理员后台创建，不保留任何硬编码账号
