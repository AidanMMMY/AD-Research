# 真 secret rotate runbook（2026-07-04 起）

> 最后核实更新：2026-07-21

> 当 secret 泄露、团队成员离职、或定期轮换时，按本文档顺序执行。**只针对真
> secret**（API key / cookie / token / 加密密钥），不是 admin 登录密码
> —— 密码重置走 `20260701-admin-password-reset-runbook.md`。

## 何时执行

满足任一条件即应启动 rotate：

1. **真 secret 已泄露**：CI 日志 / Sentry / Slack / 邮件 / 截图里出现了明文 key。
2. **团队成员离职带走 secret**：尤其是 Xueqiu cookie 这种长 session。
3. **定期轮换**：建议每年一次（Q3 末），覆盖所有数据源 key。
4. **数据源大面积异常**：怀疑被对方封禁，需要换一组 key 排查是否 IP / key 被拉黑。
5. **安全审计 / 渗透测试发现** 任意一条历史明文。

---

## 步骤

### 1. 备份（rotate 前先把当前状态定锚）

```bash
# 在 repo 根目录
cd /opt/ad-research
git tag backup-pre-secret-rotate
git tag -l "backup-pre-secret-rotate*" --format='%(refname:short) %(objecttype) %(objectname:short)'
```

**不要**：

- ❌ 不要 `cp .env .env.bak` 然后 commit 入仓库。
- ❌ 不要把 `.env` / `.env.production` 备份到任何 `fetch-depth=0` 的 git 历史。
- ❌ 不要把 `.env.example` 里写真实 key（只能写 key **名**，见 § 6）。

### 2. 各家 secret rotate

逐家去控制台 revoke → reissue，按本节顺序替换到 secret store（阿里云
Parameter Store / 1Password / 团队 vault）。

| 厂商 | 操作 | 替换的 env key |
|---|---|---|
| **MiniMax**（当前默认 LLM provider，`LLM_PROVIDER=minimax`） | 控制台 → API Keys → revoke 旧 key → 新建 → 复制；全球端点与中国端点 key 分开管理 | `MINIMAX_API_KEY` / `MINIMAX_CN_API_KEY` |
| **DeepSeek**（legacy provider，仅 `LLM_PROVIDER=deepseek` 时生效） | 控制台 → API Keys → revoke 旧 key → Create new secret key → 复制 | `DEEPSEEK_API_KEY` |
| **Anthropic** | Console → API Keys → revoke + Create | `ANTHROPIC_API_KEY` |
| **雪球 Xueqiu** | 用任意子账号重新登录拿新 cookie → 让旧 cookie 失效（其他在用的账号也一起退出） | `XUEQIU_COOKIE` |
| **Tushare** | 控制台 → 个人中心 → token 管理 → 重置 token | `TUSHARE_TOKEN` |
| **Finnhub** | Dashboard → API key → Reset | `FINNHUB_API_KEY` |
| **Tiingo** | Account → API token → Regenerate | `TIINGO_API_KEY` |
| **FMP (Financial Modeling Prep)** | Dashboard → API Keys → Revoke + Create new | `FMP_API_KEY` |
| **FRED / BEA / BLS** | 各官网账号后台重新生成 | `FRED_API_KEY` / `BEA_API_KEY` / `BLS_API_KEY` |
| **Polygon.io** | （已移除：代码与 `.env.example` 均已无 Polygon 接入，无需 rotate） | — |
| **AkShare / BaoStock / Eastmoney** | 无 key 类数据源，跳过（但要确认调用频率没被风控） | — |
| **Sentry DSN** | （已移除：当前代码无 Sentry 集成，`app/` 与 `.env.example` 均无 `SENTRY_DSN`） | — |
| **Webhook Fernet 密钥** | 重新生成 `cryptography.fernet.Fernet.generate_key()` | `NOTIFICATION_ENCRYPTION_KEY` |

每家 rotate 后**立刻**更新到 secret store，并同步通知所有持有旧 key 的成员
（包括本地 `~/.bashrc`、CI secret、README 截图等）。这一步比"再 deploy 一遍"
重要得多 —— 留着旧 key 等于没 rotate。

### 3. 历史抹除（如需要）

仅在"明文 key 真的进了 git 历史 / 公开日志"时才做。

```bash
# 安装 git-filter-repo（一次性）
pip install git-filter-repo

# 把 .env 从所有 commit 历史里抹掉
git filter-repo --invert-paths --path .env
git filter-repo --invert-paths --path .env.production
git filter-repo --invert-paths --path .env.example  # 仅当 .env.example 里写过真值

# 强制推送（要先通知所有 fork 维护者，否则他们 merge 时会把历史带回来）
git remote add origin <your-repo-url>   # filter-repo 会清掉 remote
git push origin --force --all
git push origin --force --tags
```

通知模板（发给所有 fork 维护者）：

> 标题：强制历史重写 / forced history rewrite
>
> 我们刚才用 `git filter-repo` 从 main 分支移除了 `*.env*` 文件。
> 请 rebase 你的 fork 到新的 main（旧的 commit hash 已失效），否则
> merge 时会带入旧的 secret 历史。

### 4. 部署侧 secret 注入

阿里云 ECS 上 `deploy/aliyun-ecs/.env` 是 backend 容器 env 的唯一真值来源：
`deploy/aliyun-ecs/docker-compose.yml` 以 `${VAR:-}` 变量插值方式把其中的值注入
容器（compose 没有 `env_file` / bind mount `.env`），所以改 `.env` 后必须
recreate 容器才生效。

```bash
ssh alloy-research
cd /opt/ad-research/deploy/aliyun-ecs

# 4.1 用 vault 里的新 key 覆盖 .env
sops --set /path/to/vault/DEEPSEEK_API_KEY \
     -i .env   # 或手 vi（确保 ssh session 加密）

# 4.2 重新生成 Fernet 加密密钥（仅在 § 2 轮换 NOTIFICATION_ENCRYPTION_KEY 时）
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" \
  >> /tmp/new-fernet.key
# 把 new key 写入 .env 的 NOTIFICATION_ENCRYPTION_KEY=
# ⚠️ 旋转 Fernet key 会让所有旧 webhook payload 解密失败 —— 先通知再 rotate
# 注：NOTIFICATION_ENCRYPTION_KEY 未设置时代码会回退用 AUTH_SECRET_KEY 做 Fernet 密钥
# （app/services/notification_service.py），此时 rotate AUTH_SECRET_KEY 有同样影响。

# 4.3 重启 backend 让新 env 生效
docker compose up -d --force-recreate --no-deps backend

# 4.4 健康检查
sleep 10
curl -sf http://localhost:8000/health
```

**重要**：docker-compose 不会 reload env 文件，必须 `--force-recreate` 而不是
`up -d`。仅 restart 不重读 `.env`。

### 5. 验证（rotate 后 1 小时内必跑）

#### 5.1 scheduler / ETL 时间戳

```bash
# 看 scheduler 是否在用新 key 拉数据
ssh alloy-research "docker logs --tail=200 alloyresearch-backend 2>&1 \
  | grep -iE 'deepseek|tushare|xueqiu|finnhub' | tail -20"
```

应能看到 "使用 key: sk-xxxNEW"（如果日志里打出来的是前缀 hash）或
"API 认证通过"。**绝对不应**看到 401 / 403 / "invalid api key"。

#### 5.2 LLM 流式输出

平台没有 `/api/v1/llm/chat` 端点（已变更）；LLM 对话挂在 research 路由下。
快速验证用 AI 状态接口，完整链路用 chat session 的流式端点：

```bash
# 快速验证：provider 是否可用
curl -sf http://localhost:8000/api/v1/research/ai/status \
  -H "Authorization: Bearer <TOKEN>"

# 完整链路：先建 session，再调流式端点（SSE，data: {...} 逐行）
curl -X POST http://localhost:8000/api/v1/research/chat/sessions \
  -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
  -d '{"title":"rotate-check"}'
curl -N -X POST http://localhost:8000/api/v1/research/chat/sessions/<SESSION_ID>/messages/stream \
  -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
  -d '{"content":"ping"}'
```

应返回 SSE 流（`data: {...}` 逐行）而不是 401 / provider unavailable。

#### 5.3 通知通道推送

没有 `POST /api/v1/notifications/test` 端点（已变更）；测试发送挂在具体
config 上，需先在后台（或 API）创建一条 webhook 配置：

```bash
# 先发一条测试 webhook，看 Fernet 加密 / 解密是否双通
curl -X POST http://localhost:8000/api/v1/notifications/configs/<CONFIG_ID>/test \
  -H "Authorization: Bearer <TOKEN>"
```

到配置的 webhook 接收端（如 webhook.site）上看：

- 解密后的明文 payload 正常到达 → ✅ 旧 + 新 Fernet key 都可用（rotate 兼容）。
- 出现 base64 密文 / 乱码 → ❌ Fernet key rotate 不兼容，需要考虑多 key 回退。

如果做 Fernet 兼容轮换，参考 `cryptography.fernet.MultiFernet`：
new key 放前面、old key 放后面，验证通过后再下掉 old key。

---

## 不应做

- ❌ **不要把 `.env` 写入仓库**，包括"临时的 `.env.example` 也只能写 key 名"：
  ```ini
  # ✅ OK
  DEEPSEEK_API_KEY=<your_deepseek_key_here>

  # ❌ 严禁
  DEEPSEEK_API_KEY=sk-REMOVED-7f8a9b...
  ```
- ❌ **不要把 `.env` 备份到任何 `fetch-depth=0` 的 git 历史**：
  CI 的 `actions/checkout@v4` 用 `fetch-depth: 0` 时会把所有历史拉下来，
  哪怕 commit 里是误提交也会被 gitleaks 抓。备份只放 host 目录或 vault。
- ❌ **不要让 CI 显示明文 key**：Sentry 抓到的请求 body 如果包含 key，
  立即在 Sentry 后台加 redact rule；GHA 日志用 `::add-mask::` 提前屏蔽。
- ❌ **不要在 IM / 邮件 / Slack 明文贴 key**：发完立刻 rotate。
- ❌ **不要"先 deploy，rotate 之后再做"**：secret 泄露后立即 revoke 旧的，
  deploy 只是为了让新值生效。
- ❌ **不要跳过 § 5 验证**：rotate 完 1 小时内必须跑 scheduler / LLM / 通知
  三个通道，否则下一轮定时任务会用旧 key 失败。

---

## 相关文件

| 路径 | 作用 |
|---|---|
| `deploy/aliyun-ecs/.env` | 阿里云 ECS 上 backend 容器 env 的唯一真值来源（compose 变量插值注入） |
| `.env.example` | 仓库内模板（**只写 key 名**，不写真值） |
| `deploy/aliyun-ecs/docker-compose.yml` | backend 服务 env 注入声明（`${VAR:-}` 插值，无 env_file / mount） |
| `.github/workflows/secrets-scan.yml` | PR 触发 gitleaks，挡 secret 进 main |
| `.github/workflows/deploy.yml` | push 触发部署（**不**做 secret 扫描） |
| `app/services/notification_service.py` | Webhook Fernet 加解密入口 |
| `scripts/reset_user_password.py` | admin 密码重置（**不是** secret rotate） |

## 相关 memory

- `memory/20260704-secret-rotate-runbook.md`（delay 列表）
- `memory/20260627-data-source-known-issues.md`（数据源异常处理决策）
- `memory/20260701-admin-password-reset-runbook.md`（admin 密码走另一条流程）

---

**编写日期**：2026-07-04
**适用版本**：所有 ≥ 2026-06-23（首次接入多数据源）部署
**Owner**：DevOps