# 2026-07-23 P2 收尾 / Backend CI / 采集故障告警

> 三个低成本修复同日落地：清理 P2 死代码、补 Backend CI 缺口、把 orchestrate
> silent failure 接入 NotificationLog。背景详见
> `docs/dev-notes/20260720-ecs-ops-audit-and-fixes.md` 与 7-19 平台指标审计报告。

---

## 1. P2 低成本收尾

| 项目 | 文件 | 收益 |
| --- | --- | --- |
| `/stocks` / `/stocks/:code` 永久 redirect → `/instruments` | [web/src/routes.tsx](../../web/src/routes.tsx) | 合并两个重复入口，去掉未使用的 lazy import |
| 删除已废弃 `ContentCard.tsx` 桩组件 | [web/src/components/ContentCard.tsx](../../web/src/components/ContentCard.tsx)（已删） | -448 字节 + .content-card CSS 17 行 |
| NewsHealth 全量改用 Panel | [web/src/pages/NewsHealth/index.tsx](../../web/src/pages/NewsHealth/index.tsx) | ContentCard 最后一个消费方清零 |
| Dashboard v8 (command-center) a11y 测试 | [web/tests/a11y/command-center.test.tsx](../../web/tests/a11y/command-center.test.tsx) | topbar/sidebar/3-up 网格 keyboard-reachable + axe-core 0 违规 |
| `.gitignore` 清理 | `.gitignore` | 屏蔽 `.bak` / `*.swp` / IDE 临时文件 |

### 1.1 Stock 路由重定向

`/stocks` 与 `/instruments` 在 2026-07-23 前并存（同一份 stocks list，但挂两条路由）。为避免后续 oncall
看到 `/stocks` 没人维护、又要在两个文件改 filter 参数，统一走 `/instruments?type=stock`；`:code`
路径同样转发。`<Navigate replace />` 保证浏览器历史不脏。

### 1.2 ContentCard 删除

`ContentCard.tsx` 自 v7 Dashboard 重构后只剩 `NewsHealth` 5 处引用，迁到 `Panel` 之后引用为 0，
纯桩组件删除即可，无功能回归。`web/src/styles/global/components.css` 同步删除 `.content-card*`
17 行 CSS，避免保留死样式。

---

## 2. Backend Pytest CI（PR-244 关闭 P0）

文件：[`.github/workflows/backend-ci.yml`](../../.github/workflows/backend-ci.yml)

之前 backend 完全无 CI —— 7-19 平台审计时已列为 P0。本次新增 workflow：

- **触发**：`pull_request` + `push to main`，命中 `app/**` `alembic/**` `scripts/**` `pyproject.toml` `poetry.lock` `.github/workflows/backend-ci.yml`
- **执行**：`poetry install --with dev` + `pytest -q --deselect app/tests/e2e --no-header --tb=short --maxfail=20`
- **超时**：15 min；失败时 `actions/upload-artifact` 把 junit + pytest log 上传
- **E2E deselect**：`app/tests/e2e/` 需要真 DB + 真 ETL，前置条件太多，CI 不跑

本次实际跑通结果（本地）：**933 passed, 85 deselected, 67 warnings in 152.64s**。
后续每次 PR 自动跑，避免回归。

---

## 3. 采集故障告警 → NotificationLog

> 背景：7-19 ~ 7-21 之间 `orchestrate_v2` 因为 docker image 缺失导致 8 个 source 全挂 16h，
> 无人察觉。详见 `docs/dev-notes/20260719-orchestrate-image-fix.md`。
>
> 本次目标：silent failure → NotificationLog（与既有 `/admin/etl-status` / `/api/v1/notifications` 通路对齐）。

### 3.1 后端：`app/api/v1/internal.py`

新增 **internal** router（受 `INTERNAL_API_TOKEN` Bearer 保护）：

- `POST /api/v1/internal/orchestrate-alert`
  - payload：`failed_workers: list[{name, exit_code, items, duration, error}]` + `schedule` + `total_duration_seconds` + `host` + `threshold`
  - 返回：`{ accepted, notification_log_id, status: "skipped" | "below_threshold" | "logged", failed_count }`
  - 状态机：
    - `failed_workers` 空 → `skipped`（一切正常）
    - `failed_count < threshold` → `below_threshold`（单点抖动，不告警）
    - 其余 → `logged`，写一条 `NotificationLog`（status=`failed` 若 failed_count ≥ max(threshold,3)，否则 `success`；error_msg 截断到 500 字符）
- `GET /api/v1/internal/health`：watchdog 自检用

**安全模型**：

```python
# 必须设置 INTERNAL_API_TOKEN；未设置时所有 internal 路由返回 503，永不开放。
# 对比用 hmac.compare_digest（Python 3.11 Homebrew build 上 hashlib.compare_digest 不直接暴露）。
INTERNAL_API_TOKEN 不存在 → 503
Authorization Bearer 不匹配 → 403
匹配 → 200
```

`_ensure_alert_config(db)` 在 `notification_config` 表里查 `channel_type='system_alert'` +
`name='orchestrate_watchdog'`，找不到则插入一行占位 cfg（user_id=1），不暴露在 UI。

### 3.2 触发端：`agent/scripts/orchestrate_v2.py`

新增 CLI flags：

- `--alert-threshold`（默认 2）—— 同 tick 内多少 worker 失败才告警
- `--alert-backend-url`（默认 `http://alloyresearch-backend:8000/api/v1/internal/orchestrate-alert`，可通过 `ORCHESTRATE_ALERT_URL` 覆盖）
- `--alert-token`（默认读 `ORCHESTRATE_ALERT_TOKEN`，缺省回退 `INTERNAL_API_TOKEN`）
- `--alert-disable`（本地调试用）

新增 helper：

- `_failed_workers(results)` — 从 aggregate 提取 exit != 0 / error != None 的 worker
- `_post_watchdog_alert(...)` — 调 `requests.post` + 10s 超时 + try/except `RequestException`，**永不 raise**（cron 必须继续）

watchdog 在 `aggregate.json` 写完之后、`return 0` 之前同步跑。token 未设置时 warning + skip。

### 3.3 测试：`app/tests/test_internal_api.py`

6 个测试覆盖：token 必需、错 token、no failures skipped、below_threshold、
threshold 触发 logged（用 FastAPI `app.dependency_overrides[get_db]` 注入 fake session，
**不**走真实 DB，**不** monkey-patch module-level symbol —— 那是上一版失败的根因）、
未配置 INTERNAL_API_TOKEN → 503。

#### 3.3.1 上一个版本的 monkey-patch 失败

`monkeypatch.setattr("app.api.deps.get_db", fake_get_db)` 没生效，原因是
`importlib.reload(internal_mod)` 在 fixture 中执行时把 `from app.api.deps import get_db`
重新解析了一次，仍然拿回旧引用；monkey-patch 之后再 reload 也被 import caching 兜回
原版。改成 FastAPI 官方 `app.dependency_overrides[get_db] = ...`，绕过 module-level
import 缓存，可靠生效。fake session 也补了 `flush()` 方法（`_ensure_alert_config` 调
`db.flush()` 拿 cfg.id）—— 上一版 fake session 没 `.flush()`，即便 get_db 被换也会
抛 AttributeError。

---

## 4. 部署注意

### 4.1 Backend 新增环境变量

```bash
# backend 容器 (alloyresearch-backend) 必须新增
INTERNAL_API_TOKEN="<openssl rand -hex 32>"

# cron 容器 (alloyresearch-agent 或 orchestrate host) 同样持有该 token
ORCHESTRATE_ALERT_TOKEN="$INTERNAL_API_TOKEN"
# 可选，覆盖 backend URL（默认 http://alloyresearch-backend:8000/...）
ORCHESTRATE_ALERT_URL="..."
```

不配置 `INTERNAL_API_TOKEN` = watchdog 全部静默跳过（warning log）—— 这是有意为之，
允许旧部署不破坏 cron 行为；但**应当尽快配**，否则 silent failure 仍然存在。

### 4.2 Backend CI

PR 自动跑 933 tests；首次引入会有 ~3 min 跑测开销。后续如需提速：
`pytest -q --deselect app/tests/e2e --no-header -n auto`（pytest-xdist），但当前 serial 已经 2:32 OK。

---

## 5. 验证

- [x] `app/tests/test_internal_api.py` 6 passed
- [x] `pytest --deselect app/tests/e2e` 933 passed, 85 deselected in 152.64s
- [x] `web/tests/a11y/command-center.test.tsx` 2 passed（vitest）
- [x] 前端 `tsc --noEmit` + `npm run build`（commit e0cb4c5 已验证）

---

## 6. 后续 TODO（不在本次范围）

- P2 `[NotificationLog]` `user_id` 字段未使用（130 业务处硬编码颜色）—— 后续 sprint 统一
- `app/tests/e2e` 仍未接 CI —— 后续接入 staging DB
- Alert threshold 默认 2 是否合适需要观察 1~2 周 —— 可通过 `--alert-threshold` 现场调整