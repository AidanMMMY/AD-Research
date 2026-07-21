# ETF Research Platform - 定时任务恢复操作指南

> 本文档记录当服务端定时任务中断、数据落后时的完整恢复流程。
> 适用场景：A 股 ETF 日线数据未自动更新、指标/评分/信号停滞。

> 最后核实更新：2026-07-21

---

## 一、问题判断标准

出现以下任一情况，即说明服务端定时任务可能已中断：

1. `instrument_daily_bar` 最新交易日明显落后当天（如落后 2 个以上交易日）。
2. `etl_log` 表中 `a_share_daily_etl` 最近一次成功时间距现在超过 1 天。
3. 服务器进程列表中无 `uvicorn` / `python app/main.py` / APScheduler 相关进程。
4. `data_completeness_check.py` 输出中“最新日线日期”不是最近交易日。

---

## 二、前置检查

### 2.1 确认基础设施（PostgreSQL + Redis）

#### 方式 A：本地或裸机部署

```bash
# PostgreSQL
pg_isready -h localhost -p 5432 -U etf

# Redis
redis-cli ping
# 应返回 PONG
```

如果 `pg_isready` 命令不存在，可安装客户端：

```bash
apt update && apt install -y postgresql-client-common postgresql-client
```

#### 方式 B：Docker Compose 部署

```bash
cd /opt/ad-research/deploy/aliyun-ecs  # 生产 compose 所在目录
docker compose ps
```

应看到 `alloyresearch-postgres`、`alloyresearch-redis` 状态为 `running`。如果不在：

```bash
docker compose up -d postgres redis
```

---

## 三、启动后端服务

### 3.1 本地 Python 启动

```bash
cd /opt/ad-research
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

成功标志：

```text
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
[Scheduler] Started
INFO:     Application startup complete.
```

**必须看到 `[Scheduler] Started`**，否则 APScheduler 定时任务不会执行。

### 3.2 Docker Compose 启动

```bash
cd /opt/ad-research/deploy/aliyun-ecs
docker compose up -d --build backend
```

查看日志：

```bash
docker compose logs -f backend
```

### 3.3 使用 tmux/screen 后台运行

SSH 会话断开后服务会被杀掉，建议挂到 tmux：

```bash
tmux new -s alloyresearch-backend
cd /opt/ad-research
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

# 按 Ctrl+B，然后按 D，退出 tmux 但保留服务
```

重新进入：

```bash
tmux attach -t alloyresearch-backend
```

---

## 四、补跑缺失数据

### 4.1 不回测版本（推荐首次恢复使用）

`scripts/update_daily_data.py` 第 5 步会执行全量回测，数量级为 `3 策略 × 1511 ETF ≈ 4533` 个任务，耗时数小时。首次恢复数据时建议跳过回测，只补齐日线、指标、评分、信号。

仓库里已有现成的 `scripts/update_daily_data_nobacktest.py`（内容与 `update_daily_data.py` 相同，仅注释掉了回测调用），直接执行即可：

```bash
cd /opt/ad-research
source .venv/bin/activate
python scripts/update_daily_data_nobacktest.py
```

> ⚠️ 已知问题（2026-07-21 核实）：该文件第 1 行混入了一行误粘贴的文本
> `406 /opt/ad-research/scripts/update_daily_data_nobacktest.py`（疑似 `wc -l`
> 输出残留），会导致 Python 语法错误。执行前请先删掉这一行。

如果脚本不存在或损坏，也可以手动重新生成：复制 `scripts/update_daily_data.py`，
然后注释掉 `main()` 中的回测调用：

```python
        # 首次恢复时跳过回测，避免跑数小时
        # backtest_count = run_backtests(db)
        # print(f"   已完成 {backtest_count} 个回测")
```

### 4.2 预期输出

```text
📊 Step 1: Fetching daily bars for 1514 ETFs up to 2026-06-26...
   Batch 1/152: 10 ETFs
   ...
   Inserted/updated XXXX daily bar records
   已更新 XXXX 条指标记录
   已更新 XXXX 条评分记录
   已生成 XXXX 个信号
✅ Data Update Summary:
   Daily bars: 1514 ETFs, latest=2026-06-26
   Indicators: XXXXXX records, latest=2026-06-26
   Scores: XXXXX records, latest=2026-06-26
   Signals: XXXX records for 2026-06-26
```

如果 Step 1 仍显示 `Fetched 0 raw records`，说明 akshare 数据源接口异常，参考第六节排错。

### 4.3 单独跑回测（可选）

数据补齐且服务稳定后，再执行完整回测：

```bash
# 挂到 tmux，因为可能跑数小时
tmux new -s etf-backtest
cd /opt/ad-research
source .venv/bin/activate
python scripts/update_daily_data.py
```

---

## 五、验证数据恢复

### 5.1 快速检查最新日线日期

```bash
source .venv/bin/activate
python - <<'PY'
from app.core.database import SessionLocal
from sqlalchemy import func
from app.models.etf import InstrumentDailyBar

db = SessionLocal()
latest = db.query(func.max(InstrumentDailyBar.trade_date)).scalar()
print(f"最新日线日期: {latest}")
db.close()
PY
```

应返回最近一个交易日（如 `2026-06-26` 或 `2026-06-25`，取决于当天是否开市）。

### 5.2 完整数据健康检查

```bash
cd /opt/ad-research
source .venv/bin/activate
python scripts/data_completeness_check.py
```

重点关注第三节输出：

```text
最新日线日期: 2026-06-26
最新指标日期: 2026-06-26
最新评分日期: 2026-06-26
最新信号日期: 2026-06-26
```

四项一致且为最近交易日，即表示恢复成功。

---

## 六、补数据失败排错

### 6.1 检查 akshare 数据源

```bash
source .venv/bin/activate
python - <<'PY'
from datetime import date, timedelta
from app.data.providers.akshare_provider import AkshareProvider

p = AkshareProvider(prefer_sina=True)
df = p.fetch_daily_bars(
    ["510300.SH"],
    date.today() - timedelta(days=7),
    date.today() - timedelta(days=1)
)
print(df.head())
print(f"records: {len(df)}")
PY
```

如果返回空，尝试：

1. 升级到最新 akshare：
   ```bash
   pip install -U akshare
   ```
2. 在 `scripts/update_daily_data.py` 中把 `AkshareProvider()` 改为 `AkshareProvider(prefer_sina=True)`，使用新浪接口更稳定。

### 6.2 检查数据库连接

```bash
source .venv/bin/activate
python - <<'PY'
from app.core.database import SessionLocal
db = SessionLocal()
print("DB connected")
db.close()
PY
```

### 6.3 查看服务日志

```bash
# Docker
cd /opt/ad-research/deploy/aliyun-ecs
docker compose logs -f backend

# 本地（如果启动时重定向了日志）
tail -f /var/log/alloyresearch-backend.log
```

---

## 七、防止服务再次掉线

### 7.1 Docker Compose 设置自动重启

编辑 `docker-compose.yml`，在 `backend` 服务下添加：

```yaml
backend:
  restart: always
  deploy:
    restart_policy:
      condition: any
      delay: 5s
      max_attempts: 3
```

然后：

```bash
docker compose up -d
```

### 7.2 systemd 服务（Linux 裸机部署）

创建 `/etc/systemd/system/alloyresearch-backend.service`：

```ini
[Unit]
Description=ETF Research Platform Backend
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=aidanliu
WorkingDirectory=/opt/ad-research
Environment=PATH=/opt/ad-research/.venv/bin
ExecStart=/opt/ad-research/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

加载并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable alloyresearch-backend
sudo systemctl start alloyresearch-backend
sudo systemctl status alloyresearch-backend
```

### 7.3 定时任务监控

每天可通过 API 检查最近 ETL 状态：

```bash
curl http://localhost:8000/api/v1/etl/status?limit=5
```

---

## 八、定时任务清单

服务启动后，APScheduler 会自动按 cron 执行任务（完整清单见
[app/core/scheduler.py](../../app/core/scheduler.py)，运行中实例可用
`bash scripts/check_scheduler_drift.sh` 巡检）。与数据恢复直接相关的核心任务：

| 时间（北京时间） | 任务 | 对应函数 |
|------------------|------|----------|
| 05:00 | 美股日终采集 | `run_us_etl` |
| 05:30 | 美股指标计算（Celery） | `run_us_indicator_calculation` |
| 07:00 | A 股 ETF 前十大持仓采集 | `run_etf_holdings` |
| 08:00 | A 股指标计算（Celery） | `run_indicator_calculation` |
| 08:05 | 加密货币日终采集 | `run_crypto_etl` |
| 08:30 | 评分计算 | `run_score_calculation` |
| 08:30 | 加密货币指标计算（Celery） | `run_crypto_indicator_calculation` |
| 09:00 | 交易信号生成 | `run_signal_generation` |
| 15:30 | **A 股 ETF 日终采集** | `run_a_share_etl` |
| 16:00 | A 股个股日终采集 | `run_a_share_stock_etl` |
| 16:30 | A 股个股估值数据 / 国内期货日线 | `run_a_share_stock_fundamental` / `run_futures_daily` |
| 17:00 | A 股指标 17 点兜底补算 | `run_a_share_indicator_fallback` |
| 17:00 | 巨潮定期报告日刷（Celery） | `run_cninfo_reports_daily` |
| 17:30 | A 股资金流向刷新 | `run_fund_flow_daily` |
| 18:00 | A 股研报日抓取 | `run_research_reports_daily` |
| 19:30 | A 股微结构数据刷新 | `run_microstructure_daily` |
| 每小时 :00 | 美股历史数据回填（小批量轮转） | `run_us_historical_backfill` |
| 周一 01:00 / 02:00 | A 股个股发现 / 个股财报采集 | `run_a_share_stock_discovery` / `run_a_share_stock_financials` |
| 周日 01:00 / 02:00 | 美股 ETF 发现 / 美股个股发现 | `run_us_etf_discovery` / `run_us_stock_discovery` |
| 周日 03:00 | 全市场 ETF 扫描 | `run_etf_scan` |
| 周日 03:30 / 04:00 | A 股复权因子全历史回填 / ETF 元数据补全 | `run_a_share_adj_factor_backfill` / `run_etf_metadata_enrichment` |
| 周日 22:00 | 池周报生成 | `run_weekly_pool_reports` |

> 注：指标计算、cninfo 回填等长任务由 scheduler 通过 `.delay()` 提交到 Celery
> worker 执行（队列 `indicator` / `cninfo`），详见
> `20260712-celery-worker-runbook.md`。此外 scheduler 还注册了新闻抓取
> （5–30 分钟间隔）、宏观数据、模拟仓、磁盘巡检等任务，此处未一一列出。

---

## 九、常用命令速查

| 目的 | 命令 |
|------|------|
| 启动后端 | `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1` |
| Docker 启动全部 | `docker compose up -d` |
| 查看后端日志 | `docker compose logs -f backend` |
| 补数据（跳过回测） | `python scripts/update_daily_data_nobacktest.py` |
| 完整补数据 | `python scripts/update_daily_data.py` |
| 数据健康检查 | `python scripts/data_completeness_check.py` |
| 进入 tmux 会话 | `tmux attach -t alloyresearch-backend` |
| 查看 ETL 日志 API | `curl http://localhost:8000/api/v1/etl/status?limit=5` |

---

*文档生成时间：2026-06-27*
