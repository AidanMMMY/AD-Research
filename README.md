# AlloyResearch

> 多市场（A 股 / 美股 / 港股 / 日股 / 加密货币）的 Web 投研平台，集成数据采集、技术指标、综合评分、标的池管理、策略回测、交易信号、模拟/真实交易、AI 研报。

## ✨ 核心能力

- **数据采集**：akshare（A 股 ETF）、Tushare（A 股个股/基本面）、yfinance（跨境）、Tiingo / Finnhub / FMP（美股）、Binance（加密货币）
- **技术指标**：MA / EMA / MACD / RSI / 布林带 / ATR / 风险指标（波动率 / 最大回撤 / 夏普 / 多周期收益）
- **综合评分**：横截面百分位排名 + 5 维度加权（收益 / 风险 / 夏普 / 流动性 / 趋势），支持自定义模板
- **标的池**：CRUD + 目标权重 + 3 种建议权重算法（等权 / 评分加权 / 风险平价）+ 快照 + 相关性 + 风险分析
- **策略回测**：动量 / 均值回归 / RSI 策略模板 + 成本模型 + 绩效归因（Brinson）+ 多策略对比
- **交易信号**：按策略生成 BUY / SELL / HOLD 信号及强度
- **模拟/真实交易**：Paper trading 全流程模拟 + Binance live trading（admin only）
- **AI 研报**：DeepSeek LLM，结构化输出池分析/标的研报
- **板块轮动**：板块相对强弱、动量排名、轮动信号
- **报告引擎**：HTML / Markdown / JSON 三种格式，Jinja2 模板
- **ETL 看板 + 调度**：APScheduler（Asia/Shanghai）+ Redis 分布式锁 + 多 worker 安全

## 🏗️ 架构

- **后端**：FastAPI 0.115 + SQLAlchemy 2.0 + Pydantic + Alembic + PostgreSQL 16 + Redis 7
- **前端**：React 18 + Vite + TypeScript + Ant Design 5 + ECharts + lightweight-charts + Zustand + TanStack React Query
- **调度**：APScheduler（Asia/Shanghai 时区，单进程启动）
- **鉴权**：JWT（python-jose + bcrypt），覆盖 13 个 router
- **部署**：Docker Compose（postgres / redis / backend）

## 🚀 快速启动

### 环境要求

- Python 3.12+ / Node 20+
- PostgreSQL 16 + Redis 7
- Docker Compose（推荐）或本地安装

### 后端

```bash
cd app
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 编辑 DATABASE_URL / REDIS_URL / AUTH_SECRET_KEY
alembic upgrade head
python -m scripts.seed_users  # 初始化 admin / Aidan / Tee / Zack / Philip
uvicorn main:app --reload --port 8000
```

### 前端

```bash
cd web
npm install
npm run dev  # http://localhost:5173
```

### 首次数据

```bash
python scripts/init_demo_data.py
python scripts/update_daily_data.py
```

### Docker Compose（一键启动）

```bash
docker compose up -d
# backend  http://localhost:8000
# postgres :5432
# redis    :6379
```

## 📦 模块清单

### 后端 API 路由（app/api/v1/）

| 模块 | 路径前缀 | 功能 |
|------|----------|------|
| auth | `/api/v1/auth` | JWT 登录 / 当前用户信息 |
| etfs | `/api/v1/etfs` | ETF 列表 / 详情 / 分类 / 扫描 |
| stocks | `/api/v1/stocks` | 个股列表 / 详情 |
| stock_fundamentals | `/api/v1/stock-fundamentals` | 个股基本面 |
| crypto | `/api/v1/crypto` | 加密货币列表 / 详情 / 行情 |
| etf_scanner | `/api/v1/etf-scanner` | 全市场 ETF 扫描触发与日志 |
| market_data | `/api/v1/market-data` | 历史日线 / 实时行情快照 |
| indicators | `/api/v1/indicators` | 单只/批量最新指标 + 历史 |
| scoring | `/api/v1/scores` | 综合评分 + 模板 CRUD |
| screening | `/api/v1/screen` | 多条件筛选 + 预设 + 分类统计 |
| analysis | `/api/v1/analysis` | 相关性矩阵 / 排名 / 板块轮动 |
| sector_rotation | `/api/v1/analysis/sector-rotation` | 板块相对强弱与轮动信号 |
| attribution | `/api/v1/analysis/attribution` | 绩效归因（Brinson 模型） |
| pools | `/api/v1/pools` | 标的池 CRUD + 成员 + 权重 + 快照 + 分析 + 相关性 |
| strategies | `/api/v1/strategies` | 策略 CRUD + 模板 |
| backtests | `/api/v1/backtests` | 回测运行 / 列表 / 详情 |
| signals | `/api/v1/signals` | 信号生成 / 列表 / 最新 |
| paper_trading | `/api/v1/paper-trading` | 模拟交易账户与订单 |
| live_trading | `/api/v1/live-trading` | Binance 真实交易（admin） |
| reports | `/api/v1/reports` | 报告生成 / 列表 / 下载 |
| notifications | `/api/v1/notifications` | 通知配置 / 测试 / 日志 |
| favorites | `/api/v1/favorites` | 用户自选 |
| stats | `/api/v1/stats` | 平台概览统计 |
| etl | `/api/v1/etl` | ETL 状态 / 日志 |
| stream | `/api/v1/stream` | SSE 实时行情流 |
| research | `/api/v1/research` | AI 研报（DeepSeek） |
| chat | `/api/v1/chat` | AI 聊天 |
| admin_users | `/api/v1/admin/users` | 用户管理（admin） |
| deployments | `/api/v1/deployments` | 部署面板（admin） |

### 前端页面（web/src/pages/）

| 页面 | 路径 | 功能 |
|------|------|------|
| Login | `/login` | JWT 登录 |
| Dashboard | `/dashboard` | 平台概览、Top10 评分、自选、池列表 |
| ETFList | `/etfs` | ETF 列表 + 筛选 + 搜索 |
| ETFDetail | `/etfs/:code` | K 线、指标、综合评分雷达图、自选 |
| Screen | `/screen` | 多条件筛选、预设、分页 |
| ScoreRanking | `/scores` | 按模板查看综合评分排名 |
| PoolList | `/pools` | 创建/查看池 |
| PoolDetail | `/pools/:id` | 成员权重、持仓分布、相关性、快照 |
| ReturnComparison | `/comparison` | 多只 ETF 收益曲线叠加 |
| CorrelationAnalysis | `/correlation` | 相关性热力图 |
| SectorRotation | `/sector-rotation` | 板块表现与轮动信号 |
| ETFScanner | `/scanner` | 触发/查看全市场扫描 |
| SignalDashboard | `/signals` | 最新交易信号看板 |
| StrategyList | `/strategies` | 策略模板、创建、删除 |
| BacktestList | `/backtests` | 创建/查看回测 |
| BacktestDetail | `/backtests/:id` | NAV 曲线、交易记录 |
| ReportBrowser | `/reports` | 生成/下载/预览报告 |
| ResearchNotes | `/research` | AI 研报浏览 |
| AIChat | `/chat` | AI 聊天界面 |
| CryptoList | `/crypto` | 加密货币列表 |
| CryptoDetail | `/crypto/:code` | 加密货币详情 |
| PaperTrading | `/paper-trading` | 模拟交易账户 |
| TradingPanel | `/trading` | Binance 真实交易面板（admin） |
| NotificationConfig | `/notifications` | Webhook/邮件配置与测试 |
| NotificationLogs | `/notifications/logs` | 通知发送历史 |
| ETLStatus | `/etl` | ETL 执行状态 |
| SentimentDashboard | `/sentiment` | 情绪指标看板 |
| AdminUsers | `/admin/users` | 用户管理 |
| AdminDeployments | `/admin/deployments` | 部署管理 |

### 数据源（app/data/providers/）

| Provider | 覆盖市场 | 数据类型 |
|----------|----------|----------|
| AkshareProvider | A 股 ETF | 日线、实时行情 |
| TushareProvider | A 股个股 | 日线、基本面、复权因子 |
| YFinanceProvider | 美股 / 港股 / 日股 / 外汇 | 日线、行情 |
| TiingoProvider | 美股 | 日线、EOD 价格 |
| FinnhubProvider | 美股 ETF | 基础信息 |
| FMPProvider | 美股 | 基础信息、行情 |
| BinanceProvider | 加密货币 | K 线、行情 |

### 定时任务（app/core/scheduler.py）

| 任务 ID | Cron | 说明 | 分布式锁 |
|---------|------|------|---------|
| `a_share_daily_etl` | 每天 15:30 | A 股 ETF 日终采集 | `_LOCK_DAILY_PIPELINE` |
| `indicator_calculation` | 每天 08:00 | 批量计算指标 | 等待日终 ETL |
| `score_calculation` | 每天 08:30 | 评分日终计算 | 等待日终 ETL |
| `signal_generation` | 每天 09:00 | 生成交易信号 | 等待日终 ETL |
| `weekly_pool_reports` | 每周日 22:00 | 生成所有池周报 | 无 |
| `etf_market_scan` | 每周日 03:00 | 全市场 ETF 扫描 | 无 |

## 🧪 测试

```bash
cd app && pytest tests/ -v
cd web && npm run build && npx tsc --noEmit
```

测试覆盖：scoring、screening、pool、data、api、us_etf_discovery、us_stock_enrichment 等模块。

## 📚 文档

- [系统平台功能逻辑说明手册](docs/user-manual/20260622-系统平台功能逻辑说明手册.md)
- [2026-07-01 平台审查报告](docs/dev-notes/20260701-platform-logic-audit.md)
- [定时任务恢复操作指南](docs/dev-notes/20260627-scheduled-task-recovery-guide.md)
- [数据源已知问题备忘](docs/dev-notes/20260627-data-source-known-issues.md)
- [功能路线图](docs/ROADMAP.md)

## 🔒 安全

- JWT 鉴权覆盖 13 个 router，未登录访问受限端点返回 401
- 真实交易、用户管理、部署面板等敏感端点仅 admin
- CORS 默认本地开发，env 配置；生产环境必须收紧
- `AUTH_SECRET_KEY` / `NOTIFICATION_ENCRYPTION_KEY` 通过 env 注入，禁止硬编码
- 真实交易启用前必须配置 Binance API key（建议 testnet）

## 🚢 部署拓扑（重要！）

服务器上 `alloyresearch-backend` 容器的代码来源：

- **`/app/app/...`** 来自镜像 `alloy-research:latest` 的 `COPY app/ ./app/` 层，**不是 host 的 bind mount**
- host 上的 `/opt/alloy-research/app/` 修改 → 容器内**不会**自动更新
- 必须 rebuild image + recreate container 才生效

```bash
# 本地：改完代码
git add -A && git commit -m "..." && git push origin main

# 服务器：
cd /opt/alloy-research
git pull --ff-only origin main   # 或 fetch + reset --hard origin/main
bash redeploy.sh                  # 触发 docker build + recreate
```

`redeploy.sh` 做的事：

```bash
cd /opt/alloy-research/deploy/aliyun-ecs
docker compose up -d --build --no-deps backend
```

- `--build`：触发 Dockerfile 重 build（拷进新的 `app/`）
- `--no-deps`：只重建 backend，不动 Postgres/Redis
- recreate 期间 backend 短暂不可用（30–90 秒），数据不受影响

**必须重建后验证**，否则容易出现"代码改了但 500 还在"的诡异现象：

```bash
ssh alloy-research "docker exec alloyresearch-backend sed -n '137p' /app/app/api/v1/auth.py"
ssh alloy-research "curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{\"username\":\"<user>\",\"password\":\"<pw>\"}' -w '\nHTTP %{http_code}\n'"
```

详见事故复盘：`docs/dev-notes/20260701-admin-password-reset-runbook.md` § 4-B。

## 📄 License

TBD（内部项目）

## 🤝 贡献

- 主分支：`main`
- 提 PR 前必须跑 `pytest` + `tsc` + `build`
- 参考 `docs/ROADMAP.md` 了解子项目进度
- 参考 `docs/dev-notes/20260701-platform-logic-audit.md` 了解已知问题与修复 Sprint
