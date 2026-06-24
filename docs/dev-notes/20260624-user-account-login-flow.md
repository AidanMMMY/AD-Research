# 用户账号启用与登录方式说明

> 记录当前 AD-Research 平台的账号体系、启用流程和登录校验逻辑。
> 更新日期：2026-06-24

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

1. 根据 `username` 查 `users` 表
2. 用 bcrypt 校验密码
3. 检查 `is_active`：
   - `false` → 返回 401 `User is inactive`
   - `true` → 生成 JWT token 返回
4. 前端把 token 存到 `localStorage`，后续请求带 `Authorization: Bearer <token>`

JWT payload 包含：

```json
{
  "sub": "username",
  "role": "admin|user",
  "exp": "过期时间"
}
```

Token 过期时间由 `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` 控制，默认 1 天。

---

## 5. 禁用账号的效果

把用户的 `is_active` 改成 `false` 后：

- 该用户**下次登录**会返回 401 `User is inactive`
- 如果该用户**已登录且 token 未过期**，前端 `/me` 接口目前仍会返回用户信息（token 校验阶段未检查 `is_active`）

> **注意**：如需禁用立即生效（踢掉已登录用户），需要在 `app/api/deps.py` 的 `get_current_user` 依赖中增加 `is_active` 检查。

---

## 6. 相关文件

| 文件 | 说明 |
|------|------|
| `app/models/user.py` | User 表模型 |
| `app/api/v1/auth.py` | 登录、/me 接口 |
| `app/api/v1/admin_users.py` | 管理员用户管理 CRUD |
| `app/api/deps.py` | `get_current_user`、`require_admin` 依赖 |
| `app/schemas/user.py` | 用户管理相关 Pydantic Schema |
| `app/config.py` | `AuthSettings`（`AUTH_ADMIN_USERNAME` / `AUTH_ADMIN_PASSWORD`） |
| `scripts/seed_users.py` | 初始化管理员脚本 |
| `scripts/create_user.py` | 命令行创建用户脚本 |
| `web/src/pages/AdminUsers/index.tsx` | 用户管理前端页面 |
| `web/src/App.tsx` | 管理员路由守卫 |

---

## 7. 安全建议

- 生产环境务必设置强密码的 `AUTH_ADMIN_PASSWORD`
- `AUTH_SECRET_KEY` 必须替换默认值
- 不要在代码或 Git 中提交 `.env` 文件
- 普通用户应通过管理员后台创建，不保留任何硬编码账号
