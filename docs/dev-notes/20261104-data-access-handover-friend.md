# AlloyResearch 数据接入交接文档（给外部项目/其 AI 代理）

> 版本：2026-11-04 · 平台：https://www.alloyresearch.net
> 读者：接入方的开发者或 AI 代理。本文档自包含，按顺序读即可完成接入。
> 凭据安全：登录凭据**不在本文档中**，由平台所有者另行安全交付（见 §2.4）。

## 0. 平台数据资产总览（2026-11-04 生产实测）

| 资产 | 规模 | 深度/周期 |
|---|---|---|
| 标的宇宙（active） | A 股 **7,247** · 美股 **579** · 加密 **25** | — |
| 日线行情 | **1,670 万行** | 2010-01-04 至今 |
| 技术指标（日线） | **1,657 万行** | 2010-01-04 至今 |
| 综合评分 | **248 万行** | 2010 至今（逐日） |
| 交易信号 | **275 万行** | 2026-06 至今 |
| 资讯文章 | **96.4 万篇**，其中 82.5 万有全文 | 170+ 中英采集源，分钟级增量 |
| 每日 AI 研报 | 93 期 | 每交易日 06:30 |
| 研究报告库 | 6,891 篇 | — |
| 巨潮公告（A 股） | 12.2 万份 | 含 PDF 提取文本 |
| SEC 文件（美股） | 1,477 份 | — |
| 宏观指标 | 7.2 万条 | FRED/BEA/BLS 等 |
| 龙虎榜 | 7,068 条 | — |
| 申万行业指数 | 14,601 条 | — |
| 搜索趋势 | 2,938 条 | — |

（实时数字可用 `/stats/overview` 与 `/news/stats/sources` 自查。）

## 1. 你能拿到什么（与不能碰什么）

**开放范围**：平台全部市场数据与资讯的**只读访问**——A 股/美股/港股/日股/加密货币行情与指标、综合评分、交易信号、资金流、资讯（170+ 源中英双语）、每日 AI 研报、宏观指标、SEC 文件、巨潮公告、微观结构、学习中心语料、搜索趋势、期货。历史全量、无调用配额、无额外审批。

**不开放（工程原因，非针对）**：`/admin/*`、`/live-trading/*`、`/paper-trading/*` 的写操作、`/internal/*`、通知配置、设备管理、其他用户的个人数据。这些域包含平台凭据与他人隐私，接入方账号调用会得到 403——这是预期行为，不要重试。

## 2. 接入方式（首选 API Key：一个请求头，无登录无过期）

### 2.1 Base URL

```
https://www.alloyresearch.net/api/v1
```

### 2.2 首选：静态 API Key（推荐，零生命周期管理）

所有请求带一个请求头即可，永不过期、无需登录/刷新：

```bash
curl -H "X-API-Key: <交付的 API Key>" \
  "https://www.alloyresearch.net/api/v1/news?page=1&page_size=5"
```

- Key 形如 `Ak-<随机串>`，由平台所有者私密交付
- 除 §1 禁区外与登录态完全同权（user 角色，全部只读数据端点可达）
- 保管：存密钥管理，勿入代码仓库/URL/日志；泄露或停用请联系所有者轮换

### 2.3 备用：账号登录 + JWT（当 Key 通道维护时）

```bash
# 登录（令牌务必缓存复用——登录有按 IP 限流）
curl -X POST https://www.alloyresearch.net/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"<交付的用户名>","password":"<交付的密码>"}'
# → {access_token(8h), refresh_token}；请求带 Authorization: Bearer <access_token>
# 过期前刷新：POST /auth/refresh {"refresh_token": ...}（轮换式，只保留最新一对）
```

### 2.4 凭据交付与保管

API Key 与（备用）账号密码均由平台所有者通过私密渠道交付，本文档不含任何凭据。不要修改备用账号密码（会触发平台强制策略并踢掉会话）；不要共享凭据。

### 2.5 第一个验证请求

见 2.2 的 curl——返回 200 与资讯列表即接入成功。

## 3. 数据域端点目录（全部 GET，180+ 端点中的核心组）

完整机器可读目录：`GET /openapi.json`（无需认证）。

| 域 | 端点（前缀 /api/v1） | 说明 |
|---|---|---|
| **资讯** | `/news`、`/news/{id}`、`/news/stats/sources`、`/news/event-signals`、`/news/watchlist` | 170+ 源中英资讯，支持分页/筛选；`/news/{id}` 含全文 |
| **AI 研报** | `/digest/latest`、`/digest/by-date/{date}`、`/digest/{id}`、`/reports` | 每日 06:30 生成；`/digest/latest/summary` 轻量版 |
| **股票/ETF** | `/stocks`、`/stocks/{code}`(+`/financials`)、`/etfs`、`/etfs/{code}`(+`/holdings`、`/sparkline`)、`/etf-holdings/*` | code 形如 `600519` / `510300` / `AAPL` |
| **指标** | `/indicators/{code}`(+`/history`)、`/indicators/batch/latest` | 技术指标（MACD/RSI/布林等） |
| **评分** | `/scores`、`/scores/{etf_code}`、`/scores/templates` | 综合评分 0-100 |
| **信号** | `/signals`、`/signals/latest` | 策略信号 |
| **资金流** | `/fund-flow/market`、`/sector`、`/individual`、`/individual/{ts_code}`、`/signals` | 主力/融资/龙虎榜合成信号 |
| **加密货币** | `/crypto`、`/crypto/{code}`(+`/history`、`/indicators`、`/score`、`/signals`) | |
| **宏观** | `/macro/latest`、`/macro/indicators/{code}`、`/macro/indices/global` | FRED/BEA/BLS 等 |
| **SEC 文件** | `/sec-filings`、`/sec-filings/{id}`、`/coverage` | 美股披露 |
| **巨潮公告** | `/cninfo-reports`、`/{id}`(+`/download`) | A 股公告 PDF/提取文本 |
| **微观结构** | `/microstructure/hsgt`、`/lhb`、`/margin`、`/restricted-releases` | 北向/龙虎榜/融资融券/解禁 |
| **板块轮动** | `/sector-rotation`、`/sectors/{sector}/constituents` | 申万行业 |
| **筛选/分析** | `/analysis/ranking`、`/correlation`、`/screen`、`/screen/presets`、`/stock-fundamentals/{code}` | |
| **学习中心** | `/learning/feed`、`/learning/topics`、`/learning/bookmarks` | 知识文章语料 |
| **搜索趋势** | `/search-trends`、`/compare`、`/dashboard` | |
| **期货** | `/futures/contracts`、`/daily`、`/leaderboard` | |
| **健康/状态** | `/health`（无需认证）、`/news/health`、`/etl/status` | 数据新鲜度自查 |

## 4. 通用约定

- **分页**：`?page=1&page_size=50`（多数列表端点，page_size 上限普遍 100-200）
- **日期**：`YYYY-MM-DD`；历史回溯直接传 `start_date/end_date` 或 `date`
- **响应包裹**：列表多为 `{items|data, total, page, page_size}` 形态；以 `/openapi.json` 的 schema 为准
- **错误语义**：401=令牌过期（去刷新）；403=越权或未验证；422=参数错（响应体会指明字段）；429=过频（登录域）；5xx=平台侧故障

## 5. 数据新鲜度（Asia/Shanghai）

| 数据 | 更新时点 |
|---|---|
| A 股日终 ETL | 交易日 15:30 后 |
| 指标计算 | 08:00（依赖 ETL 完成，可能顺延） |
| 综合评分 | 08:30 · 交易信号 09:00 |
| 每日研报 | 06:30 |
| 资讯 | 全天增量（分钟级） |
| 美股/加密 | 按各自市场节奏，T+1 或实时 |

## 6. 接入方守则（保持全量开放的前提）

1. **只读**：只用 GET；所有 POST/PUT/DELETE 不在开放范围
2. **礼貌并发**：无硬限流 ≠ 鼓励轰炸；建议 ≤10 并发、指数退避重试（5xx 后 30s 起）
3. **令牌缓存**：一天登录一次的频率足够
4. **User-Agent**：带上你的项目标识（如 `User-Agent: friend-project/1.0`），便于平台侧排查与沟通
5. **变更感知**：平台迭代可能增删端点，接入前以 `/openapi.json` 为准；重大不兼容变更平台方会提前通知所有者

## 7. 故障排查速查

| 症状 | 处置 |
|---|---|
| 401 立刻失效 | refresh_token 未保存最新（轮换式，只留最新一对） |
| 403 | 撞到非开放域，检查是否 §1 禁区 |
| 429 on login | 令牌没缓存；改为缓存+刷新 |
| 数据为空 | 对应市场当天 ETL 未跑完（见 §5 时点）或日期参数超出范围 |
| 全站 5xx | `/health` 自查后联系所有者 |

## 8. 联系

平台所有者：Aidan（通过交付凭据的渠道联系）。平台状态页：`https://www.alloyresearch.net/health`。
