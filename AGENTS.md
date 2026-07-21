# AGENTS.md — AlloyResearch（AD-Research）投研平台

> 本文件面向 AI 编码代理，介绍项目架构、命令与约定。文档与 README 以中文为主，代码注释以英文为主。
>
> 最后核实更新：2026-07-21

## 1. 项目概览

AlloyResearch 是一个多市场（A 股 / 美股 / 港股 / 日股 / 加密货币）的 Web 投研平台，集成数据采集、技术指标、综合评分、标的池管理、策略回测、交易信号、模拟/真实交易、AI 研报与报告引擎。

- 主分支：`main`（内部项目，无开源 License）
- 线上部署在阿里云 ECS（见 `deploy/aliyun-ecs/README.md` 新手向部署手册）
- 产品域名：`www.alloyresearch.net`

## 2. 技术栈

- **后端**：Python 3.11/3.12、FastAPI 0.115、SQLAlchemy 2.0、Pydantic 2、Alembic、PostgreSQL 16、Redis 7
- **后台任务**：APScheduler（Asia/Shanghai，进程内调度）+ Celery 5（Redis broker，队列：`indicator`、`celery,cninfo,industry`）
- **数据源**：akshare、Tushare、yfinance、Tiingo、Finnhub、FMP、Binance、雪球、Reddit、SEC EDGAR、FRED/BEA 等
- **LLM**：MiniMax（默认，OpenAI 兼容）/ DeepSeek（legacy），经 `openai` SDK 调用
- **前端**：React 18 + Vite 5 + TypeScript 5 + Ant Design 5 + Tailwind CSS 4 + ECharts / lightweight-charts / recharts + Zustand + TanStack React Query + axios
- **鉴权**：JWT（python-jose + bcrypt），覆盖全部 router；admin-only 端点包括真实交易、用户管理、部署面板
- **部署**：Docker Compose（开发）+ 阿里云 ECS 生产编排 + Nginx 反代/HTTPS

## 3. 目录结构

```
app/                    # FastAPI 后端（Python 包名 app）
  main.py               # 应用入口；import app.strategies 以自注册内置策略
  config.py             # Pydantic Settings；AUTH_SECRET_KEY 弱密钥校验在导入时执行
  api/v1/               # 约 40 个 router（auth/etfs/stocks/pools/backtests/signals/...）
  core/                 # database、scheduler、celery_app、redis_client、rate_limit 等
  models/               # SQLAlchemy ORM 模型
  schemas/              # Pydantic schema
  services/             # 业务服务层（scoring/screening/backtest/pool/trading/llm/news/macro...）
  strategies/           # 策略模板（momentum/mean_reversion/trend_following/event...）
  data/                 # providers（数据源适配）、pipelines、repositories、indicators
  tasks/                # Celery 任务（indicator、cninfo、sw_industry）
  scheduler_jobs/       # APScheduler 任务
  templates/            # Jinja2 报告模板
  tests/                # pytest 测试（见第 6 节）
  scripts/              # 后端侧初始化/回填脚本
alembic/                # 数据库迁移（alembic.ini 在仓库根目录）
scripts/                # 运维脚本（回填、审计、备份、部署检查等，约 70 个）
web/                    # React 前端（真正的前端工程；仓库根的 package.json 只是少量共享依赖）
  src/pages/            # 约 50 个页面
  src/api|components|stores|hooks|utils
  tests/a11y/           # axe-core 可访问性冒烟测试
deploy/aliyun-ecs/      # 生产编排：docker-compose.yml、nginx.conf、deploy.sh、update.sh
agent/                  # 独立的数据采集 worker（独立镜像 alloyresearch-agent，跑在 ECS cron）
research/               # AI 研究编排器与 agents（academic/macro_policy/guru_opinion 等）
ios/ADResearch/         # iOS 客户端（SwiftUI，早期）
reports/                # 生成的 HTML 报告产物
docs/dev-notes/         # 开发文档，命名约定：YYYYMMDD-主题.md
tmp/                    # 一次性实验脚本，勿当正式代码
```

## 4. 构建与运行

### 环境要求

- Python 3.11+（Poetry 管理依赖，根目录 `pyproject.toml` + `poetry.lock`，本地虚拟环境在 `.venv/`）
- Node 20+（前端用 npm，`web/package-lock.json` 为锁定依据；注意 `web/` 下也有 pnpm-lock，但 CI 用 npm）
- PostgreSQL 16 + Redis 7（本地可用 `docker compose up -d postgres redis`）

### 后端（本地开发）

```bash
poetry install                    # 或使用根目录已有的 .venv
cp .env.example .env              # 按需填写 TUSHARE_TOKEN / AUTH_SECRET_KEY 等
alembic upgrade head              # 在仓库根目录执行
python scripts/seed_users.py      # 初始化 admin 账号（幂等，从 AUTH_ADMIN_USERNAME/AUTH_ADMIN_PASSWORD 读取）
uvicorn app.main:app --reload --port 8000
```

### 前端（本地开发）

```bash
cd web
npm install
npm run dev                       # http://localhost:5173
```

### Docker Compose（一键全栈，开发）

```bash
docker compose up -d
# backend: http://localhost:8001（容器内 8000；根 compose 还含 celery-worker-indicator / celery-worker-cninfo）
```

backend 容器启动命令会自动执行 `alembic upgrade head` 再拉起 uvicorn。

### 常用脚本

- 首次数据：`python scripts/init_demo_data.py && python scripts/update_daily_data.py`
- 审计/回填类脚本集中在 `scripts/`，多数为一次性运维用途，运行前先读脚本头部注释

## 5. 代码风格

### Python

- 格式化：black（line-length 100，target py312）
- Lint：ruff（line-length 100，启用 `E,F,W,I,N,UP,B,C4,SIM`，忽略 `E501`；`app/api/**` 忽略 `B008`，`scripts/**` 忽略 `E402`，`alembic/**` 忽略 `E402,F403`）
- 分层约定：`api/v1`（路由）→ `services`（业务）→ `models`/`data.repositories`；新增路由需在 `app/main.py` 注册
- 策略模板放入 `app/strategies/`，通过 `import app.strategies` 自注册

### TypeScript / 前端

- ESLint flat config（`web/eslint.config.js`），启用 `jsx-a11y` 与 `react-hooks`，`--max-warnings=0`
- stylelint（`stylelint-config-standard`）检查 `src/**/*.{css,scss}`
- 路径别名 `@` → `./src`（vite/vitest 均配置）
- 提交前本地检查：`cd web && npm run check:ci`（lint:css + tsc --noEmit + vite build）

## 6. 测试

### 后端

```bash
pytest                            # testpaths = app/tests，asyncio_mode = auto
pytest app/tests/test_scoring.py -v
```

- `app/tests/conftest.py` 提供 `db_session` / `db_session_module` fixture：**内存 SQLite + `Base.metadata.create_all`**，service 层测试不依赖真实 PostgreSQL，新测试应复用该模式
- 测试按模块组织：`test_api/`、`services/`、`strategies/`、`test_data/`、`news/`、`e2e/` 及根级 `test_*.py`
- 注意：模型若使用 PostgreSQL 专有类型，在 SQLite 下建表可能失败——新增模型后跑一遍相关测试确认

### 前端

```bash
cd web
npm test                          # vitest run（当前主要为 tests/a11y 冒烟，jsdom + axe-core）
npm run test:a11y                 # 只跑可访问性套件
npm run check:ci                  # stylelint + tsc --noEmit + vite build
```

### CI（.github/workflows）

- `web-ci.yml`：PR / push main 且 `web/**` 变更时跑 lint/typecheck/build + a11y
- `deploy.yml`：push main 自动部署到阿里云（self-hosted runner）；支持手动触发（`ref` / `skip_migrations` / `dry_run`）
- `secrets-scan.yml`：密钥扫描
- **提 PR 前必须本地跑过 `pytest` + `tsc` + `vite build`**

## 7. 后台调度与任务架构

- APScheduler 在 FastAPI 进程内启动（`app/core/scheduler.py`），时区 Asia/Shanghai
- **多 worker/多容器部署时必须只有一处开调度**：`ENABLE_SCHEDULER=true` 的实例才启动 scheduler，并以 flock + Redis 分布式锁防重（如 `_LOCK_DAILY_PIPELINE`）；指标/评分/信号任务会等待日终 ETL 完成
- Celery app 在 `app/core/celery_app.py`；worker 按队列拆分：`indicator`（指标计算）与 `celery,cninfo,industry`（巨潮公告/PDF、申万行业）
- 关键定时任务：A 股日终 ETL（15:30）、指标计算（08:00）、评分（08:30）、信号（09:00）、池周报（周日 22:00）、全市场 ETF 扫描（周日 03:00）
- 资讯正文落库：采集入库时即时抓取正文（`scheduler_jobs._write_to_db` / 雪球入库闭包 → `fetch_full_content_for_ids`，受 `NEWS_CONTENT_FETCH_ON_INGEST` / `NEWS_CONTENT_INGEST_TIME_BUDGET_SEC` 控制）；`news_full_content_10m` 定时任务（每 10 分钟，批量 50）消化积压。抽取链路在 `app/services/news/content_fetcher.py`：trafilatura 本地抽取 → Jina Reader → LLM 兜底（`NEWS_CONTENT_LLM_FALLBACK`），正文存 `news_article.full_content`

## 8. 部署流程（重要）

生产在阿里云 ECS，编排文件在 `deploy/aliyun-ecs/`。核心事实：

- **backend 容器内的 `/app/app/` 来自镜像构建时的 `COPY app/ ./app/`，不是宿主机 bind mount**——改代码必须 rebuild 镜像 + recreate 容器才生效（`docker compose up -d --build --no-deps backend`，即根目录 `redeploy.sh`）
- 更新流程：`git push origin main` → 服务器 `git pull --ff-only` → `bash redeploy.sh`（或等 `deploy.yml` 自动跑）
- 部署后必须验证容器内代码与预期一致（README「部署拓扑」一节有验证命令模板）
- 数据库迁移由 backend 容器启动命令自动执行；`deploy.yml` 默认做 alembic 迁移校验
- Dockerfile 为多阶段：Node 20 构建前端 → Python 3.11-slim 装 Poetry 依赖；`GIT_SHA` 构建参数注入 `/health` 版本信息；PyPI 默认清华镜像，可用构建参数覆盖
- 生产事故复盘与运维手册见 `docs/dev-notes/`（如 `20260719-deploy-tripwires.md`）

## 9. 安全注意事项

- 所有密钥经环境变量注入（`.env`，已在 .gitignore），**禁止硬编码**；`AUTH_SECRET_KEY` 使用已知弱值时，非 development 环境会直接拒绝启动（`app/config.py`）
- Binance 真实交易有多重开关：`BINANCE_TRADING_ENABLED=true` 才会下真实订单，另有单笔限额 / 每日亏损熔断 / 每日订单数上限；**API key 只在 Testnet 测试**
- 通知 webhook/邮件凭据用 `NOTIFICATION_ENCRYPTION_KEY` 加密存储
- CORS 由 `CORS_ORIGINS` 配置，生产必须填确切域名
- 修改 `.env` / 凭据相关逻辑后，注意 `secrets-scan.yml` 会扫描提交

## 10. 其他约定

- 文档命名：`docs/dev-notes/YYYYMMDD-主题.md`（同主题常配一份 `.html` 导出）
- `tmp/` 为临时实验区，不要把一次性脚本提升为正式代码而不移入合适目录
- `agent/` 目录的采集 worker 与主平台同仓库但独立部署（独立镜像、cron 触发，ECS 上位于 `/root/ad-research/agent/`）
- 功能路线与已知问题：参考 `docs/dev-notes/20260628-ROADMAP.md` 与 `20260701-platform-logic-audit.md`
