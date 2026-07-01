# Admin / Aidan 密码重置 Runbook

> 本文档记录当 admin 或 Aidan 账户密码丢失、忘记、或 `.env` 里没保存
> 初始密码时的应急重置流程。**旧密码不可恢复**（bcrypt 哈希单向），
> 一旦重置，原密码即作废。

## 一、什么场景需要走这条流程

满足任一条件，即应使用本 runbook 重置密码而不是排查原密码：

1. 部署时 `.env` 里没有 `AUTH_ADMIN_PASSWORD`，但 admin 账户已存在于数据库
   （说明是更早的部署创建的，密码已经无法找回）。
2. 知道密码，但用户主动要求重置（离职交接、安全事件响应）。
3. 数据库里 `users.password_hash` 因人为误操作被覆写成无效值，登录失败。
4. 紧急安全事件：怀疑密码泄露，立即原地重置堵截。

**不要**做这些事：

- ❌ 不要试图反推 bcrypt 哈希 —— 不可能。
- ❌ 不要直接用 `psql` 写一个手写的"假" bcrypt 字符串占位 —— 用户会登不进去，
  且会进一步污染 `password_hash` 字段（参考 2026-07-01 事故复盘第四节）。
- ❌ 不要清空 `password_hash` 让用户变成"无密码" 状态 —— 后端 bcrypt
  解码会直接抛异常而不是放行。

---

## 二、前置检查

### 2.1 确认基础设施

```bash
# Docker Compose 部署
ssh ad-research "cd /opt/ad-research && docker compose ps"
```

应看到 `etf-postgres`（healthy）和 `etf-backend`（up）。

### 2.2 确认目标用户存在

```bash
ssh ad-research "docker exec etf-postgres psql -U etf -d ad_research \
  -c \"SELECT id, username, role, is_active, created_at FROM users ORDER BY id;\""
```

对照现有用户名。**注意大小写** —— 用户名是大小写敏感的。常见用户名：

| 用户名 | 角色 | 备注 |
|---|---|---|
| `admin` | admin | 部署时从 `AUTH_ADMIN_USERNAME` seed 默认账号 |
| `Aidan` | user | 首字母大写 |
| `Haoyang` / `Owen` / `Larry` / `Zack` | user | 其他注册用户 |

如果目标用户不存在，应通过管理界面或 `scripts/create_user.py` 创建，**不要**
靠重置流程凭空造用户。

---

## 三、重置流程

### 3.1 在 backend 容器内运行 reset 脚本（推荐）

容器内已经装好 Python + sqlalchemy + bcrypt 依赖，是唯一可靠的执行路径。
**host 上没有依赖**，会报 `ModuleNotFoundError: No module named 'sqlalchemy'`。

```bash
# 单用户：把 admin 改成新密码
ssh ad-research "docker exec etf-backend \
  python3 scripts/reset_user_password.py admin --password '<NEW_PASSWORD>'"

# 多用户：必须分两次跑（脚本 --password 一刀切模式不支持每个用户独立密码）
ssh ad-research "docker exec etf-backend \
  python3 scripts/reset_user_password.py Aidan --password '<NEW_PASSWORD>'"
```

输出应类似：

```
  ✅ Reset password for 'admin' (role=admin, active=True)

[reset] Done.
```

### 3.2 密码强度建议

最少 12 位。生产建议 16 位随机（混合大小写字母 + 数字 + 特殊符号）：

```bash
python3 -c "
import secrets, string
print(''.join(secrets.choice(string.ascii_letters + string.digits + '!@#%^*_-') for _ in range(16)))
"
```

**重置后必须**：

1. 把新密码立即写入密码管理器（1Password / Bitwarden / macOS Keychain）。
2. 在团队 wiki / IM 里同步新密码（用临时一次性链接，不要发群里永久可见）。
3. 通知相关用户尽快登录并改为自己能记住的密码。

### 3.3 验证

```bash
# 方法 1：检查哈希是否被更新
ssh ad-research "docker exec etf-postgres psql -U etf -d ad_research \
  -c \"SELECT username, length(password_hash), left(password_hash, 7), updated_at FROM users WHERE username IN ('admin','Aidan');\""
```

合法 bcrypt 哈希长度固定 60 字符、前缀 `$2b$12$`、`updated_at` 应是刚刚。

```bash
# 方法 2：通过 API 登录测试
curl -X POST https://your-domain/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<NEW_PASSWORD>"}'
```

应返回 `access_token`。

---

## 四、事故复盘：2026-07-01 admin / Aidan 密码误改事件

**症状**：admin 和 Aidan 无法登录，bcrypt 验证失败。

**根因**：运维在排查 admin 原密码时，先用 `docker exec etf-postgres psql -c "UPDATE users SET password_hash = '...'"` 把占位字符串写进了数据库。该字符串不是合法 bcrypt 哈希，bcrypt 解码时报 `InvalidHash` 异常，登录直接 401。期间另两个用户（Haoyang / Owen / Larry / Zack）哈希未被影响。

**修复**：在 `etf-backend` 容器内跑 `reset_user_password.py admin Aidan --password '...'` 重新写入合法哈希。

**教训**：

1. **永远不要手动 UPDATE `password_hash`**。即便只是临时清空也会导致登录失败。
   bcrypt 字段只能由 `reset_user_password.py` 或应用自身的注册 / 改密路径写入。
2. **任何 UPDATE 前先 SELECT 现状**，尤其是 `WHERE` 子句要走 `username = '...'` 显式限定，
   不要省略谓词。
3. **psql 命令里的引号转义容易出错**（`$` 符号在 bash 双引号里会被吃掉、
   `\\\$` 转义层数对不齐）。建议优先用脚本而不是裸 SQL。

**预防**：

- 本 runbook 写好后，任何人遇到 admin 密码问题都先看这里，按 § 3.1 走标准流程。
- 后续可在 CI 加一个 lint 规则，禁止非 `app/` 或 `scripts/` 之外的代码路径访问
  `users.password_hash`（监控 `git diff` 历史，PR review 时人工把关）。

---

## 五、长期改进（待办）

- [ ] 给 `reset_user_password.py` 加 `--password-stdin` 支持，避免明文密码进
  `docker exec` 命令历史（`docker exec ... --password 'XXX'` 会留在 shell
  history 里）。
- [ ] 在部署 `.env.example` 顶部加红字警告："**部署完成后请把
  `AUTH_ADMIN_PASSWORD` 写入 1Password；不要保留明文在 `.env` 里超过 7 天**"。
- [ ] admin 第一次登录后强制改密（已登录过的凭据不能再用旧值）—— 需要改
  `app/api/v1/auth.py` 的登录逻辑 + `users` 表加 `must_change_password` 字段。
- [ ] 把"admin 密码"加入 deploy checklist 的强制项，每次部署后 grep
  `.env` 确认存在；不存在则运维告警。

---

## 六、相关文件

| 路径 | 作用 |
|---|---|
| `scripts/reset_user_password.py` | 密码重置脚本（唯一安全入口） |
| `scripts/create_user.py` | 手动建用户 |
| `scripts/seed_users.py` | 部署时根据 `.env` 自动 seed admin |
| `app/api/v1/auth.py` | 登录 / 登出 / refresh-token 接口 |
| `app/services/auth_service.py` | bcrypt 校验 / JWT 签发 |
| `app/models/user.py` | `users` 表模型 |

---

**编写日期**：2026-07-01
**适用版本**：所有 ≥ 2026-06-23（commit `35b0646` 移除硬编码用户之后）的部署