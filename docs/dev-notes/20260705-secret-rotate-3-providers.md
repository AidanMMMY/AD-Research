# 3 家外部服务 secret rotate 实操 Runbook（2026-07-05）

> 本 runbook 是 `20260704-secret-rotate-runbook.md`（v1 通用清单）的
> **深度执行版**，只覆盖用户决定本轮 sprint 要做的 **3 家**：
>
> 1. **DeepSeek** (LLM API key)
> 2. **雪球 Xueqiu** (Cookie = 登录态凭证)
> 3. **Tushare** (A 股数据 token)
>
> **Finnhub / Tiingo / FMP / Sentry DSN / Fernet** 等本轮**不动**，参见
> 后续 sprint。**Polygon.io** 已不在生产 env（截至 2026-07-05 阿里云 ECS
> `/opt/ad-research/deploy/aliyun-ecs/.env` 排查结果）。

---

## 〇、生产现状（2026-07-05 SSH 排查结果）

⚠️ **本 runbook 写于生产 backend 容器 crashlooping 期间**：

```
alloyresearch-backend | Restarting (1) 10 seconds ago
```

容器因 alembic migration 报错反复重启（`alembic_version` 列长度 32 不够，
新 version_num `2026_07_05_add_user_id_to_live_trade_config` 41 字符塞不下）。
**与 secret rotate 无关**，但执行步骤 § 3.3 的 `update.sh` 之前**必须先修
这个 migration bug**，否则 `--force-recreate` 启动后还是 crashloop，
新 env 不会生效。

### 3 家 secret 当前状态

| Provider | env 名 | `.env` 中是否存在 | 长度 / 前缀 | 健康度评估 | 紧急度 |
|---|---|---|---|---|---|
| DeepSeek | `DEEPSEEK_API_KEY` | ✅ 存在 | 35 字符 / `sk-00478...` | 格式合法（`sk-` 前缀 + 35 字符是 DeepSeek 标准格式） | **中**：历史已泄露（旧 .env 在 git 历史），需 rotate |
| 雪球 Xueqiu | `XUEQIU_COOKIE` | ❌ **缺失** | — | 不可用（cookie 从未配置 / 已失效） | **高**：cookie 本就未生效，rotate 没意义；需先用浏览器登录导出 cookie |
| Tushare | `TUSHARE_TOKEN` | ✅ 存在 | 56 字符 / `9e2b99ad...` | 格式合法（hex 字符串） | **中**：历史已泄露，需 rotate |

**说明**：

- 雪球 cookie 不在 `.env` 里 = 生产 A 股社交舆情 / 散户情绪数据通道
  **从部署至今就**没**生效过**（`docs/20260702-data-source-map.md` 第 61 行
  已标 ⏳ 待用户填入）。本 runbook 既覆盖"首次填入"也覆盖"后续 rotate"，
  操作步骤相同。
- DeepSeek / Tushare 当前 `.env` 里的值与 git 历史里 commit 进仓库的明文
  **一致**（因为 `git filter-repo` 只抹了仓库历史但生产从未 rotate）。任何
  能 clone 仓库历史的开发者都还持有这些 key。

### 代码侧 key 注入入口（验证 rotate 后只改 env 即可）

| Provider | 代码入口 | 读取方式 |
|---|---|---|
| DeepSeek | `app/services/llm/deepseek_provider.py:40` | `os.getenv("DEEPSEEK_API_KEY", "")` |
| DeepSeek | `app/api/v1/research.py:41` | `os.getenv("DEEPSEEK_API_KEY", "")` |
| DeepSeek | `app/services/news/translation_service.py:185` | `raise RuntimeError("DEEPSEEK_API_KEY is not configured...")` |
| Xueqiu | `app/services/news/sources/xueqiu_auth.py:66` | `os.getenv("XUEQIU_COOKIE", "")` |
| Xueqiu | `deploy/aliyun-ecs/docker-compose.yml:82` | `${XUEQIU_COOKIE:-}` 注入容器 env |
| Tushare | `app/data/providers/tushare_provider.py:180` | `get_settings().tushare_token` |
| Tushare | `app/config.py:28` | `tushare_token: str = ""` (Pydantic Settings 自动读 env) |

**结论**：rotate 只需改 `deploy/aliyun-ecs/.env`，**不需要改任何代码**。改完
后 `update.sh --force-recreate` 让 backend 容器重启以清掉 Pydantic Settings
的 `@lru_cache`。

---

## 一、通用前置（每家共用）

### 1.1 SSH 到生产 server

```bash
ssh ad-research      # 已配免密，直接连
cd /opt/ad-research
```

### 1.2 备份当前 `.env`（rotate 失败的快速回滚保险）

```bash
# 在 host 上备份到 /root，不入仓库
sudo cp /opt/ad-research/deploy/aliyun-ecs/.env \
        /root/.env.backup-$(date +%Y%m%d-%H%M%S)

# 确认备份存在
ls -la /root/.env.backup-*
```

**回滚**：把备份 cp 回去即可（§ 3.4 详述）。

### 1.3 别在 git 仓库里留任何 key 痕迹

- ❌ 不要 `git commit` 任何含 key 的文件（`.env` / `.env.production` / 临时 `.bak`）
- ❌ 不要 `git add .` 或 `git add -A`，先 `git status` 看
- ❌ 不要把新 key 贴到 IM / 邮件 / Slack（哪怕私聊）—— 用 1Password / Bitwarden / macOS Keychain 转交

### 1.4 时间预估

| Provider | 用户手动操作 | 后端验证 | 合计 |
|---|---|---|---|
| DeepSeek | 3 分钟 | 1 分钟 | ~4 分钟 |
| 雪球 Xueqiu | 5 分钟（首次填入含登录；rotate 只 3 分钟） | 1 分钟 | ~6 分钟 |
| Tushare | 3 分钟 | 1 分钟 | ~4 分钟 |

---

## 二、逐家执行步骤

### 2.1 DeepSeek

#### 步骤 1：在浏览器里生成新 key

1. 打开浏览器（推荐 Chrome / Edge），无痕窗口更安全。
2. 访问 **https://platform.deepseek.com/**
3. 顶部右上角点击 **"登录"**，用账号密码 + 手机验证码登入（不要选"记住密码"在公共电脑）。
4. 登录后左侧菜单点 **"API Keys"**（或中文界面叫 **"API 密钥管理"**）。
5. 在 **"API Keys"** 页面看到现有 keys 列表。找到当前 .env 里的那个
   （前缀 `sk-00478...`，长度 35），点最右侧的 **"删除"**（红框垃圾桶图标）。
6. 弹出确认框 → 输入 key 名（或留空）→ 点 **"确认删除"**。
7. 列表回到空状态后，点页面右上角 **"创建新 Key"**（"+ Create new secret key"）。
8. 弹出窗口：
   - **Key 名称**：填 `ad-research-prod-20260705`（带日期方便以后 rotate 追溯）
   - **权限范围**：保持默认 "All scopes"
   - 点 **"创建"**
9. ⚠️ **关键**：新 key **只显示一次**！弹窗里有一长串字符串（`sk-...` 开头约 35 字符），立即：
   - 用 1Password / Bitwarden / macOS Keychain 新建条目 **"DeepSeek Prod 2026-07-05"** 粘贴保存
   - 不要截图、不要贴 IM、不要 commit
10. 关掉弹窗。**关掉之后再也无法看到完整 key**（只能重新生成）。

#### 步骤 2：把新 key 注入生产（不 commit）

```bash
ssh ad-research
cd /opt/ad-research/deploy/aliyun-ecs

# 2.1 用 vi / nano 编辑 .env，找到 DEEPSEEK_API_KEY= 那一行
vi .env

# 2.2 把 sk-00478... 整行替换成新 key
#    ⚠️ 等号后不要加引号、不要加空格、不要带换行
#    修改后应该是这样：
#      DEEPSEEK_API_KEY=sk-NEWKEYxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
#    保存退出（vi: :wq）

# 2.3 验证改对了（只看长度，不显示完整 key）
grep -E "^DEEPSEEK_API_KEY=" .env | awk -F= '{print "DEEPSEEK_API_KEY: len=" length($2) " prefix=" substr($2,1,8)}'

# 应输出：DEEPSEEK_API_KEY: len=35 prefix=sk-NEWKEY
#         ^^^^^^^^    必须仍是 35 字符
```

#### 步骤 3：触发后端加载新 key

```bash
# 在生产 server 上
cd /opt/ad-research/deploy/aliyun-ecs

# ⚠️ 重要：先解决 §〇提到的 alembic migration crashloop bug，
# 否则 update.sh 起来后 backend 还是 Restarting 状态。
# 修法：手动改 alembic_version.version_num 列长度到 64：
#   docker exec alloyresearch-postgres psql -U etf -d ad_research \
#     -c "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64);"
# 改完后再跑：

bash update.sh
```

> **不要**直接跑 `docker compose up -d --force-recreate --no-deps backend`
> —— update.sh 还会触发 frontend rebuild + 跑 alembic 迁移，是更完整的路径。

#### 步骤 4：验证

```bash
# 4.1 确认容器已起来
ssh ad-research "docker ps --filter name=alloyresearch-backend --format '{{.Names}} | {{.Status}}'"
# 应输出：alloyresearch-backend | Up X minutes (healthy)

# 4.2 健康检查
ssh ad-research "curl -sf http://127.0.0.1:8000/health"
# 应输出：{"status":"ok",...}

# 4.3 看 backend 是否真读到新 key（看启动日志里的 AI provider init）
ssh ad-research "docker logs --tail=100 alloyresearch-backend 2>&1 | grep -iE 'deepseek|AI|llm' | tail -10"
# 应输出 DeepSeek provider loaded（无 401 / invalid api key）
```

#### 步骤 5：直接打一次 DeepSeek API 验证（绕过 backend）

```bash
# 在你本地 Mac 上（不要在生产 server，避免日志留痕）
NEW_KEY="sk-NEWKEYxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"   # 从 1Password 复制
curl -sS -X POST https://api.deepseek.com/v1/chat/completions \
  -H "Authorization: Bearer ${NEW_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-v4-flash",
    "messages": [{"role":"user","content":"ping"}],
    "max_tokens": 8
  }' | python3 -m json.tool

# 期望输出（截断版）：
# {
#   "id": "chatcmpl-...",
#   "object": "chat.completion",
#   "model": "deepseek-v4-flash",
#   "choices": [{"message": {"role": "assistant", "content": "..."}}],
#   "usage": {...}
# }

# 失败信号（说明新 key 还没生效 / 复制错了 / 控制台没创建成功）：
#   - HTTP 401 → key 无效，回到步骤 1 重新生成
#   - HTTP 402 → 账户欠费，去 platform.deepseek.com 充值
#   - HTTP 429 → 速率限制，等 1 分钟重试
#   - curl: (6) Could not resolve host → 本地网络问题，与 key 无关
```

#### 步骤 6：回滚（如新 key 立刻炸了）

```bash
ssh ad-research
cd /opt/ad-research/deploy/aliyun-ecs

# 找到最近的备份
ls -la /root/.env.backup-*

# 把备份 cp 回去
sudo cp /root/.env.backup-20260705-XXXXXX .env

# 重新部署让旧 key 生效
bash update.sh
```

⚠️ **回滚后旧 key 已经被 revoker（步骤 1 已经删了），DeepSeek API 全线 401，
所以这个回滚只用于"等新 key 生效期间"短暂顶住 1-2 分钟**，然后立刻去
控制台**重新生成 key**（不能再用旧的）或者找 DeepSeek 工单恢复。

---

### 2.2 雪球 Xueqiu（⚠️ 现状：cookie 缺失，本节也是"首次填入"流程）

雪球 cookie 不是 API key，是**浏览器登录态字符串**，每次 rotate 的核心
是"重新登录 → 复制新 Cookie header"。**没有 cookie 一切 API 调用都会被
限流到几乎不可用**。

#### 步骤 1：在浏览器里登录雪球

1. 打开 Chrome / Edge **无痕窗口**（防止已有 cookie 干扰）。
2. 访问 **https://xueqiu.com/**
3. 点右上角 **"登录"** → 弹窗选 **"手机验证码登录"** 或 **"账号密码登录"**。
4. 用手机号收验证码 / 输入密码登录。
5. 登录成功后，**确认右上角显示你的头像 / 昵称**（不是"登录"按钮）。
6. ⚠️ **保持窗口开着**，下一步要从 DevTools 复制 Cookie。

#### 步骤 2：从 DevTools 导出 Cookie 字符串

1. 在雪球页面上按 **F12**（Mac: **Cmd + Option + I**）打开 DevTools。
2. 顶部切到 **"Network"（网络）** 标签。
3. 在雪球页面上随便点一个股票（比如首页"沪深"列表任一代码），触发 1 次网络请求。
4. 在 Network 列表里随便点一条请求（带 status 200 的，类型通常是 `xhr` 或 `fetch`）。
5. 右侧面板切到 **"Headers"** 标签，往下翻找到 **"Request Headers"** 区域。
6. 在 Request Headers 里找到 **`Cookie:`** 字段（很长的一行，类似 `xq_a_token=...; u=...; device_id=...; s=...; bid=...; __utma=...`）。
7. ⚠️ **只复制 `Cookie:` 后面的值**，不要带 `Cookie:` 字面量、不要带前后的引号。
8. 完整粘贴到 1Password 新条目 **"Xueqiu Cookie 2026-07-05"**。
9. **必须包含**以下子串（缺一个就不可用）：
   - `xq_a_token=` —— 核心鉴权 token
   - `u=` —— 用户 ID
   - `device_id=` —— 设备指纹
10. 关闭无痕窗口（无需主动登出，新窗口会自动清理）。

#### 步骤 3：把 cookie 注入生产 .env

```bash
ssh ad-research
cd /opt/ad-research/deploy/aliyun-ecs

# 3.1 编辑 .env，找到 # XUEQIU_COOKIE= 注释行或已有的旧 cookie 行
vi .env

# 3.2 把整行替换为新 cookie（注意：等号后整段是一行，不要加换行 / 引号）
#    完整格式：
#      XUEQIU_COOKIE=xq_a_token=eyJxxx...; u=1234567890; device_id=abc...; s=xyz...; bid=...
#    如果 .env.example 里只有注释（首次填入），把 # 去掉、= 后贴 cookie：
#      XUEQIU_COOKIE=xq_a_token=...; u=...; device_id=...
#    保存退出

# 3.3 验证改对了
grep -E "^XUEQIU_COOKIE=" .env | awk -F= '{print "XUEQIU_COOKIE: len=" length($2) " has_xq_a_token=" (index($2,"xq_a_token=")>0)}'

# 应输出：XUEQIU_COOKIE: len=300+ has_xq_a_token=1
#         ^^^^^^^^^^^^^^^^^^^   长度通常 200-500 字符
```

#### 步骤 4：触发后端加载新 cookie

```bash
cd /opt/ad-research/deploy/aliyun-ecs
bash update.sh
```

#### 步骤 5：验证

```bash
# 5.1 容器起来 + 健康
ssh ad-research "docker ps --filter name=alloyresearch-backend --format '{{.Names}} | {{.Status}}'"

# 5.2 看 scheduler 是否启动时 probe 雪球成功
ssh ad-research "docker logs --tail=200 alloyresearch-backend 2>&1 | grep -iE 'xueqiu|雪球' | tail -10"
# 应看到类似：
#   [xueqiu] Cookie loaded: xq_a_token=eyJxxx..., u=..., device_id=...
#   [xueqiu] Public timeline probe OK
# 不应看到：
#   XueqiuAuthError: XUEQIU_COOKIE is not set
#   xueqiu probe failed: 401 / 403

# 5.3 直接 curl 一次雪球（绕过 backend）
ssh ad-research 'docker exec alloyresearch-backend sh -c "
  curl -sS -o /tmp/xq.json -w \"HTTP %{http_code}\\n\" \
    \"https://stock.xueqiu.com/v5/stock/realtime/quotec.json?symbol=SH000001\" \
    -H \"Cookie: $(grep ^XUEQIU_COOKIE= /opt/ad-research/deploy/aliyun-ecs/.env | cut -d= -f2-)\"
  cat /tmp/xq.json | head -c 300
"'
# 应输出：
#   HTTP 200
#   {"data":...,"error_code":0,...}
```

#### 步骤 6：回滚

雪球 cookie 没有"revoke"概念，旧 cookie 在新 cookie 启用后会自然失效
（雪球服务器只允许单一活跃 session）。所以 rotate 失败时的回滚就是
"用上次保存的旧 cookie 顶 5-10 分钟，重新走步骤 1-2 拿一组新 cookie"。

```bash
# 在 1Password 里找到上一次保存的 Xueqiu Cookie 条目
# 复制 → ssh 上去 vi .env 覆盖 → update.sh
```

---

### 2.3 Tushare

#### 步骤 1：在浏览器里重置 token

1. 打开浏览器无痕窗口，访问 **https://tushare.pro/**
2. 顶部点 **"登录"**，用注册时的手机号 / 微信扫码登录。
3. 登录后右上角点 **"个人中心"**（或头像下拉菜单）。
4. 在个人中心左侧菜单找 **"接口 TOKEN"** 或 **"Token 管理"**。
5. 看到当前的 token（`9e2b99ad...` 开头 56 字符）—— **不要复制走**，
   直接点右边的 **"重置"** 或 **"刷新"** 按钮。
6. 弹出确认框 → 输入短信验证码（如果要求）→ 点 **"确认重置"**。
7. 重置后页面会刷新显示新 token（一长串 hex 字符串，长度通常 56）。
8. ⚠️ **关键**：立即用 1Password 新建条目 **"Tushare Prod 2026-07-05"** 保存。
9. 不要截图、不要贴 IM、不要 commit。

#### 步骤 2：把新 token 注入生产

```bash
ssh ad-research
cd /opt/ad-research/deploy/aliyun-ecs

# 2.1 编辑 .env
vi .env

# 2.2 找到 TUSHARE_TOKEN=9e2b99ad... 那一行，替换为新 token
#    修改后：
#      TUSHARE_TOKEN=NEW_TOKEN_HERE_56_CHARS_HEX
#    保存退出

# 2.3 验证
grep -E "^TUSHARE_TOKEN=" .env | awk -F= '{print "TUSHARE_TOKEN: len=" length($2)}'
# 应输出：TUSHARE_TOKEN: len=56
#         ^^^^^^^^^^^^^^^^^^  必须仍是 56 字符
```

#### 步骤 3：触发后端加载新 token

```bash
cd /opt/ad-research/deploy/aliyun-ecs
bash update.sh
```

#### 步骤 4：验证

```bash
# 4.1 容器起来
ssh ad-research "docker ps --filter name=alloyresearch-backend --format '{{.Names}} | {{.Status}}'"

# 4.2 看 backend 日志里 Tushare provider 是否正常
ssh ad-research "docker logs --tail=200 alloyresearch-backend 2>&1 | grep -iE 'tushare' | tail -10"
# 应看到：
#   [tushare] Provider initialized
#   [tushare] Health check OK (stock_basic returned N rows)
# 不应看到：
#   [tushare] 401 / token 无效 / please check token

# 4.3 直接 curl 一次 Tushare（绕过 backend）
ssh ad-research 'docker exec alloyresearch-backend sh -c "
  curl -sS -X POST https://api.tushare.pro \
    -H \"Content-Type: application/json\" \
    -d \"{\\\"api_name\\\":\\\"stock_basic\\\",\\\"token\\\":\\\"$(grep ^TUSHARE_TOKEN= /opt/ad-research/deploy/aliyun-ecs/.env | cut -d= -f2-)\\\",\\\"params\\\":{\\\"exchange\\\":\\\"\\\",\\\"list_status\\\":\\\"L\\\",\\\"fields\\\":\\\"ts_code\\\",\\\"limit\\\":1},\\\"fields\\\":\\\"\\\"}\"
"'
# 应输出包含：
#   {"code":0,"msg":"","data":{"fields":["ts_code"],"items":[["000001.SZ"]]}}
# 失败信号：
#   {"code":-1,"msg":"token 无效"}    → 新 token 没生效，回滚
#   {"code":20001,"msg":"积分不足"}    → 账户欠费，去 tushare.pro 充值
#   {"code":40209,"msg":"权限不足"}    → 需要 Pro 套餐
```

#### 步骤 5：回滚

```bash
ssh ad-research
cd /opt/ad-research/deploy/aliyun-ecs

# 找到最近备份
ls -la /root/.env.backup-*
sudo cp /root/.env.backup-20260705-XXXXXX .env
bash update.sh
```

⚠️ **回滚后旧 token 已经被 Tushare 控制台重置（步骤 1 已重置），Tushare
API 全线 invalid token。回滚只用于"等新 token 生效期间"短暂顶 1-2 分钟**，
然后立刻去 Tushare 控制台**重新 reset token**（无法恢复旧的）。

---

## 三、整体收尾

### 3.1 三家都 rotate 完后，1 小时内必须做的端到端验证

```bash
# 在生产 server 上
ssh ad-research
cd /opt/ad-research/deploy/aliyun-ecs

echo "=== 1. 容器健康 ==="
docker ps --filter name=alloyresearch-backend --format '{{.Names}} | {{.Status}}'
curl -sf http://127.0.0.1:8000/health && echo "  /health OK"

echo "=== 2. scheduler 是否在用新 key 拉数据 ==="
sleep 30  # 等下一个调度 tick
docker logs --tail=300 alloyresearch-backend 2>&1 \
  | grep -iE 'deepseek|tushare|xueqiu' \
  | grep -iE 'failed|error|401|403|invalid' \
  | tail -10
# 应输出为空（或只有老的 stale error，无新错误）

echo "=== 3. LLM 流式输出（DeepSeek） ==="
TOKEN=$(curl -sS -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"'"$(grep ^AUTH_ADMIN_PASSWORD= .env | cut -d= -f2-)"'"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
curl -N -X POST http://127.0.0.1:8000/api/v1/llm/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"stream":true,"message":"ping"}' \
  | head -5
# 应看到 data: {...} 流式输出

echo "=== 4. Tushare A 股数据 ==="
curl -sS http://127.0.0.1:8000/api/v1/a-stocks/health | python3 -m json.tool
# 应输出 status: ok

echo "=== 5. 雪球舆情拉取 ==="
curl -sS http://127.0.0.1:8000/api/v1/news/sources | python3 -m json.tool
# 应看到 xueqiu: enabled / last_fetch_recent
```

### 3.2 不要做（再次强调）

- ❌ 不要把 `.env` / `.env.production` commit 到 git
- ❌ 不要把新 key / cookie / token 写到任何 `.md` / `.txt` / Slack 消息 / 邮件 / 截图
- ❌ 不要把新 key 贴到 CI / GitHub Actions secrets / Vercel env 里（这些是公开变量池，反而扩大暴露面）
- ❌ 不要"先 deploy，再 rotate"——必须先 revoke 旧的，**deploy 只是为了让新值生效**
- ❌ 不要跳过 § 1.2 备份——回滚就靠它

### 3.3 前置必做：修 alembic migration crashloop

§〇提到的 `alembic_version.version_num VARCHAR(32)` 长度不够，是 rotate 的
前置修复，否则 update.sh 起来后 backend 持续 Restarting，新 env 永远不生效：

```bash
ssh ad-research
docker exec alloyresearch-postgres psql -U etf -d ad_research \
  -c "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64);"
# 改完后跑 update.sh 验证 backend 能正常 Up
cd /opt/ad-research/deploy/aliyun-ecs && bash update.sh
```

### 3.4 git 历史抹除（可选，但强烈建议）

本 runbook 完成后，**真正的 secret 已经 rotate**，但 git 历史里的明文 `.env`
仍然在仓库历史里。任何人 clone 仓库都能看到旧值（已经 rotate 失效，但**未来
如果开发者手贱把旧值填回 .env**，等于白 rotate）。

```bash
# ⚠️ 这是不可逆操作，先和所有 fork 维护者沟通
pip install git-filter-repo
cd /Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform
git filter-repo --invert-paths --path .env
git filter-repo --invert-paths --path .env.production
git remote add origin <your-repo-url>
git push origin --force --all
git push origin --force --tags
```

---

## 四、风险清单

| 风险 | 概率 | 症状 | 缓解 |
|---|---|---|---|
| 新 key 复制时漏字符 / 多空格 | 高 | DeepSeek / Tushare 返回 401 | § 2.x 步骤 5 的直连 curl 验证，1 分钟内发现 |
| Xueqiu cookie 复制时漏 `xq_a_token=` | 中 | backend 日志报 `XueqiuAuthError: cookie missing xq_a_token` | 步骤 2.2 第 9 步的格式校验；步骤 5.2 日志 |
| update.sh 起来后 backend 还是 crashloop | 高（已知前置 bug） | `Restarting (1)` | § 3.3 先修 alembic migration |
| rotate 完成后 24h 内旧 token 还在被攻击者用 | 中（视攻击者发现速度） | DeepSeek 控制台 → 用量暴增 | 步骤 1 第一时间 revoke 旧 key |
| 雪球 rotate 后旧 cookie 仍有效几分钟 | 高 | 同一账号两处登录互踢 | 不算风险，是设计如此；用户应主动退出其他设备 |
| 备份 `.env` 留在 host 上被其他运维看到 | 中 | host 上 `~/.bash_history` / `/root/` 列出 .env.backup-* | 用 `chmod 600` 限权限；rotate 成功 24h 后 `shred -u /root/.env.backup-*` |
| 回滚时旧 key 已被 revoke 导致全线 401 | 高（预期） | 所有调用 401 | 不要回滚超过 5 分钟；立刻重新生成 |

---

## 五、相关文件 / memory

| 路径 | 作用 |
|---|---|
| `deploy/aliyun-ecs/.env` | 生产 backend 容器 env 唯一来源（rotate 目标） |
| `deploy/aliyun-ecs/update.sh` | 触发 backend rebuild + recreate（让新 env 生效） |
| `deploy/aliyun-ecs/docker-compose.yml` | env 注入声明（`${XUEQIU_COOKIE:-}` 等） |
| `app/config.py` | Pydantic Settings，`tushare_token` / `xueqiu_cookie` 字段定义 |
| `app/services/llm/deepseek_provider.py` | DeepSeek LLM 入口 |
| `app/services/news/sources/xueqiu_auth.py` | 雪球 cookie 解析 + 验证 |
| `app/data/providers/tushare_provider.py` | Tushare Pro 数据 provider |
| `docs/dev-notes/20260704-secret-rotate-runbook.md` | v1 通用 runbook（Finnhub / Tiingo / FMP 也覆盖） |
| `docs/dev-notes/20260704-deploy-verification.md` | 生产 deploy 后验证清单 |
| `memory/20260704-secret-rotate-runbook.md` | rotate 决策记录（推迟 → 本轮执行） |

---

**编写日期**：2026-07-05
**适用范围**：本轮 sprint（2026-07-05 ~ 07-12）只覆盖 DeepSeek / 雪球 / Tushare 3 家
**Owner**：DevOps + 用户手动操作（rotate 步骤 1 必须用户在浏览器完成）
**预计总耗时**：15-20 分钟（用户手动 12 分钟 + 验证 / 修复 8 分钟）