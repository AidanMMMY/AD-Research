# 美股数据种子落地与持续回填方案

> 日期：2026-06-28
> 分支：fix/etf-list-type-filter
> 相关文件：
> - `app/data/pipelines/us_etf.py`
> - `app/data/pipelines/us_backfill.py`（新增）
> - `app/core/scheduler.py`
> - `app/data/providers/fmp_provider.py`
> - `app/data/providers/tiingo_provider.py`

## 执行摘要

2026-06-27 晚间在阿里云服务器完成：
1. 合并 `fix/etf-list-type-filter` 到 `main` 并触发部署；
2. 修复 AI 与美股数据源 Key 未传入容器导致的 503 / 空数据问题；
3. 将 569 只美股标的（69 ETF + 500 S&P 500 个股）写入 `etf_info`；
4. 用 Tiingo 为 33 只核心美股 ETF/个股回填最近 30 个交易日日线；
5. 批量计算技术指标与 3 套评分模板；
6. 通过 API 验证 `SPY.US` 等核心标的已具备 K 线、指标、评分、AI 研报能力。

## 当前数据状态

| 指标 | 数值 | 说明 |
|------|------|------|
| 美股标的总数 | 569 | 69 ETF + 500 S&P 500 个股 |
| 有历史价格的标的 | 33 | 核心 ETF/个股，见下方列表 |
| 美股日线记录 | 1,386 | `etf_daily_bar` |
| 美股指标记录 | 1,546 | `etf_indicator` |
| 美股评分记录 | 1,546 × 3 | `etf_score`，覆盖 3 套模板 |

### 33 只已回填核心标的

```text
SPY.US  QQQ.US  VOO.US  IVV.US  VTI.US  DIA.US  IWM.US
AAPL.US MSFT.US GOOGL.US AMZN.US TSLA.US NVDA.US META.US
BRK.B.US JPM.US  JNJ.US  V.US    XOM.US  UNH.US  HD.US
PG.US   MA.US   BAC.US  ABBV.US PFE.US  KO.US   PEP.US
AVGO.US TMO.US  COST.US WMT.US  MRK.US  ABT.US  MCD.US
```

### 评分 TOP 10（综合分）

| 排名 | 代码 | 名称 | 综合评分 |
|------|------|------|---------|
| 1 | UNH.US | UnitedHealth Group | 71.34 |
| 2 | XLV.US | Health Care Select Sector SPDR Fund | 71.01 |
| 3 | JNJ.US | Johnson & Johnson | 69.56 |
| 4 | TMO.US | Thermo Fisher Scientific | 68.76 |
| 5 | ABT.US | Abbott Laboratories | 67.80 |
| 6 | MRK.US | Merck & Co | 66.44 |
| 7 | PEP.US | PepsiCo | 65.06 |
| 8 | PG.US | Procter & Gamble | 64.84 |
| 9 | KO.US | Coca-Cola | 64.57 |
| 10 | BRK.B.US | Berkshire Hathaway Class B | 64.18 |

## 已修复的关键问题

| 问题 | 根因 | 修复 |
|------|------|------|
| `/research/notes`、`/research/sentiment` 503 | `DEEPSEEK_API_KEY` 在 `.env` 中但未传入容器 | `docker-compose.yml` backend 环境显式传入 6 个 Key |
| `market=US` 返回 total 0 | Redis 缓存了旧列表 | `redis-cli FLUSHALL` 刷新缓存 |
| 美股全量回填 records=0 | yfinance 从云服务器 IP 被限流；Finnhub candle 对新 Key 403 | 改用 Tiingo 单标的手工种子，再让调度器细水长流 |
| `BRK.B.US` Tiingo 失败 | Tiingo 使用 `BRK-B` 而非 `BRK.B` | 种子脚本中做 `TIINGO_CODE_MAP` 映射 |
| `batch_calculate_indicators() got unexpected keyword argument 'codes'` | 函数签名只有 `db`、`target_date`、`full_history` | 移除 `codes` 参数，计算全量活跃标的 |

## 环境配置

服务器 `/opt/ad-research/.env` 已配置（git 不追踪）：

```env
DEEPSEEK_API_KEY=...
ANTHROPIC_API_KEY=...
FINNHUB_API_KEY=...
TIINGO_API_KEY=...
FMP_API_KEY=...
TUSHARE_TOKEN=...
```

> 注意：`docker-compose.yml` 必须显式将这些 Key 传入 backend 容器，`.env` 本身不会自动暴露。

## 持续获取方案

由于免费数据源对云服务器 IP 极不友好，放弃一次性全量回填，改用**低频率轮换调度**：

### 数据源选择

| 数据源 | 免费档限制 | 适用场景 |
|--------|-----------|---------|
| FMP | 250 req/day | 主要历史回填与日常日线 |
| Tiingo | 50 req/hour，500 symbols/month | FMP 失败时的 fallback |
| yfinance | 云服务器基本不可用 | 仅在本地开发时使用 |
| Finnhub | candle endpoint 对新 Key 403 | 仅用于实时行情与新闻 |

### 调度策略

1. **美股日终采集 `us_daily_etl`**
   - 时间：每天北京时间 05:00（美股收盘后 1 小时）
   - 数据源：FMP → Tiingo fallback
   - 任务：获取全部 569 只标的最新交易日数据
   - 限制：FMP 250 req/day，分 5 批，每批 ~114 只不可行，因此改为**每次只请求有数据缺失的标的 + 核心标的优先**

2. **美股历史回填 `us_historical_backfill`**（新增）
   - 时间：每 6 小时一次
   - 数据源：FMP primary，Tiingo fallback
   - 每批 30 只标的，轮询覆盖全部 569 只
   - 每次拉取最近 90 天历史，补全缺失日线
   - 通过 Redis 记录轮换偏移量，保证断点续跑

3. **指标与评分计算**
   - `us_indicator_calculation`：每天 05:30，在日线任务完成后执行
   - `score_calculation`：每天 08:30，覆盖全部活跃标的

### 进度估算

- 历史回填每批 30 只，569 只约需 19 批
- 每 6 小时一批，理论上约 4.75 天完成一轮全量历史回填
- 实际受 FMP 日限额、周末休市、网络波动影响，可能需要 1 周左右

## 监控方式

```bash
# 查看 ETL 执行日志
curl -s http://localhost:8000/api/v1/etl/status?job_name=us_daily_etl | jq
curl -s http://localhost:8000/api/v1/etl/status?job_name=us_historical_backfill | jq

# 查看美股数据覆盖情况（在容器内执行）
docker exec -it etf-backend python -c "
from app.core.database import SessionLocal
from sqlalchemy import func
from app.models.etf import ETFInfo, ETFDailyBar
db = SessionLocal()
total = db.query(ETFInfo).filter(ETFInfo.market == 'US').count()
with_price = db.query(ETFDailyBar.etf_code).distinct().filter(ETFDailyBar.etf_code.like('%.US')).count()
print(f'US total: {total}, with price: {with_price}')
db.close()
"
```

## 已知限制

- FMP 免费 Key 无法使用 `/sp500_constituent` 等 legacy endpoint，已用公开 CSV 替代。
- Tiingo 免费档 500 symbols/month，不适合作为全部 569 只标的的主要回填源。
- yfinance 对云服务器批量下载限流严重，生产环境不再依赖。
- 历史回填速度受免费档限制，无法一次性补全，需持续运行数天。

## 后续优化方向

- 当免费档不足以支撑全量时，可考虑付费数据源（如 Tiingo 付费档、Polygon、Alpha Vantage 付费）。
- 对核心 33 只标的保持高频更新，其余标的按评分/热度优先级回填。
- 前端增加"数据覆盖度"提示，让用户了解哪些美股已有价格数据。
