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
ssh alloy-research "cd /opt/alloy-research && docker compose ps"
```

应看到 `alloyresearch-postgres`（healthy）和 `alloyresearch-backend`（up）。

### 2.2 确认目标用户存在

```bash
ssh alloy-research "docker exec alloyresearch-postgres psql -U etf -d alloy_research \
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
ssh alloy-research "docker exec alloyresearch-backend \
  python3 scripts/reset_user_password.py admin --password '<NEW_PASSWORD>'"

# 多用户：必须分两次跑（脚本 --password 一刀切模式不支持每个用户独立密码）
ssh alloy-research "docker exec alloyresearch-backend \
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
ssh alloy-research "docker exec alloyresearch-postgres psql -U etf -d alloy_research \
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

**根因**：运维在排查 admin 原密码时，先用 `docker exec alloyresearch-postgres psql -c "UPDATE users SET password_hash = '...'"` 把占位字符串写进了数据库。该字符串不是合法 bcrypt 哈希，bcrypt 解码时报 `InvalidHash` 异常，登录直接 401。期间另两个用户（Haoyang / Owen / Larry / Zack）哈希未被影响。

**修复**：在 `alloyresearch-backend` 容器内跑 `reset_user_password.py admin Aidan --password '...'` 重新写入合法哈希。

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

## 四 B、追加事故：2026-07-01 登录 500 误诊为密码错误

### 症状

按 § 3.1 重置 admin / Aidan 密码后，前端登录依然报"用户名密码不正确"。但
`docker exec alloyresearch-postgres psql` 查询 `users.password_hash` 显示是合法的
`$2b$12$` 60 位 bcrypt，`updated_at` 是刚刚 reset 的时间。

### 真正的根因

不是密码问题 —— 而是 `app/api/v1/auth.py:137` 的 `login` endpoint 构造
`UserResponse` 时漏传了 `id` 字段：

```python
# 错误（commit 1fce9dd 引入的 bug）
return LoginResponse(
    ...
    user=UserResponse(username=user.username, role=user.role),
)

# 正确
return LoginResponse(
    ...
    user=UserResponse(id=user.id, username=user.username, role=user.role),
)
```

`UserResponse` schema 强制 `id` 必填（`app/schemas/auth.py:10`）。后端
bcrypt 校验**确实通过**了，但在响应序列化阶段抛 `ValidationError` → HTTP 500。
前端把所有非 2xx 都笼统显示成"用户名密码不正确"，于是看起来像密码错。

### 诊断路径

```bash
# 在 backend 容器内直接 POST 一次，看 HTTP 状态码和 body
ssh alloy-research "docker exec alloyresearch-backend python3 -c \"
import requests
r = requests.post('http://127.0.0.1:8000/api/v1/auth/login',
                  json={'username':'admin','password':'<password>'})
print(r.status_code, r.text[:200])
\""
```

看到 `HTTP 500` 而不是 `HTTP 401`，就是后端逻辑错误，不是密码错。然后：

```bash
ssh alloy-research "docker logs --tail=200 alloyresearch-backend 2>&1 \
  | grep -A 20 'auth.py.*137\\|UserResponse'"
```

看到 `ValidationError ... id Field required` 就是本 bug。

### 修复 + 验证

1. 修改 `app/api/v1/auth.py:137`，加 `id=user.id`。
2. 加回归测试 `app/tests/test_auth_login.py`：
   - 登录成功响应里必须包含 `user.id`
   - 错密码返回 401（不是 500）
   - 停用账户返回 401（不是 500）
3. commit + push 到 origin main。

### ⚠️ 关键陷阱：服务器部署拓扑

**仅 git pull 不够 —— 必须 rebuild image + recreate container**。

服务器实际 mounts（`docker inspect alloyresearch-backend --format '{{json .Mounts}}'`）：

```json
[
  {"Type":"volume","Destination":"/app/web/dist",...},   // 前端产物
  {"Type":"bind","Destination":"/var/run/docker.sock",...} // Docker socket
]
```

注意：**没有 `.:/app` bind mount**。`/app/app/...` 是 `Dockerfile` 里
`COPY app/ ./app/` 拷贝到镜像层的。所以本地代码修改 ≠ 容器内代码修改。

正确的代码部署路径：

```bash
# 1. 本地
git add -A && git commit -m "..." && git push origin main

# 2. 服务器
cd /opt/alloy-research
git pull --ff-only origin main   # 或 fetch + reset --hard origin/main
bash redeploy.sh                  # rebuild image + recreate container
```

`redeploy.sh` 实际做的事（看 `cat redeploy.sh`）：

```bash
cd /opt/alloy-research/deploy/aliyun-ecs
docker compose up -d --build --no-deps backend
```

`--build` 触发 Dockerfile 重 build，`--no-deps` 不动 Postgres/Redis，
`-d` 后台运行。recreate 期间 backend 短暂不可用（约 30-90 秒），数据库不受影响。

### 重建后一定要 curl 验证

```bash
ssh alloy-research "curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{\"username\":\"admin\",\"password\":\"<NEW_PASSWORD>\"}' \
  -w '\nHTTP %{http_code}\n'"
```

必须看到 `HTTP 200` 和完整的 `user` 对象（含 `id`），**不要只 rebuild 不验证**。

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
- [ ] **前端区分 HTTP 500 和 401 提示**：现在所有非 2xx 都显示"用户名密码不正确"，
  应该是 500 → "服务器错误，请稍后再试" / 401 → "用户名或密码错误"。
  这能避免下次再把 500 误诊为密码问题。
- [ ] **CI 加 lint 防止 Pydantic schema 构造漏字段**：用 `model_validate(obj)`
  替代 `Model(**obj)`，强制走 schema 校验，缺字段直接报错而不是运行时崩溃。
- [ ] **在 README / CLAUDE.md 里写明部署拓扑**：本地代码 ≠ 容器代码，
  代码变更必须走 `redeploy.sh`，避免下次再绕远路。

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