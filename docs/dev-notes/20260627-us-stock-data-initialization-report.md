# 美股数据初始化报告

> **注**：本文为 2026-06-27 的时点记录，部分内容可能已过时（后续演进见 `20260628-us-equity-seed-and-continuous-backfill.md`）。

> 日期：2026-06-27
> 分支：`fix/etf-list-type-filter`

## 执行摘要

已完成美股标的批量灌入本地数据库，平台现可浏览、筛选、查看 569 只美股标的（69 只 ETF + 500 只 S&P 500 个股）。同时为核心标的补入了 30 天日线数据，可用于 K 线、技术指标及 AI 分析演示。

## 当前数据状态

```text
ETFInfo 总数: 2083
市场分布: [('US', 569), ('A股', 1514)]
类型分布: [('STOCK', 500), ('ETF', 1583)]
US 日线数据: 294 条（覆盖 14 只核心 ETF/个股）
```

| 数据来源 | 数量 | 说明 |
|---------|------|------|
| Finnhub 精选美股 ETF | 69 | SPY、QQQ、VOO、VTI 等高流动性 ETF |
| 公开 S&P 500 CSV | 500 | AAPL、MSFT、GOOGL、AMZN、TSLA、NVDA、META 等成分股 |
| Tiingo 日线回填 | 14 | SPY、QQQ、VOO、IVV、VTI、DIA、IWM、AAPL、MSFT、GOOGL、AMZN、TSLA、NVDA、META |

## 此前看不到美股的原因

1. **数据库为空**：`etf_info` 中仅存在 1514 只 A 股 ETF，无美股记录。
2. **缺少 API Key**：`.env` 中仅配置了 `DEEPSEEK_API_KEY`，未配置美股数据源 Key。
3. **未执行初始化脚本**：`scripts/init_us_etfs.py` 与 `USStockDiscoveryPipeline` 从未运行。
4. **FMP 旧接口已下线**：2025-08-31 后新注册的 FMP 免费 Key 访问 `/sp500_constituent` 等 legacy endpoint 会返回 403，导致原有个股发现逻辑失效。

## 本次代码修复

| 文件 | 修复内容 |
|------|---------|
| `app/data/providers/fmp_provider.py` | FMP 旧接口 403 时自动 fallback 到公开 S&P 500 CSV（`datasets/s-and-p-500-companies`） |
| `app/data/pipelines/us_stock_discovery.py` | 重写 `run()`，跳过针对 OHLCV 的四层校验，正确写入 instrument 元数据 |
| `app/data/providers/tiingo_provider.py` | 修复 Tiingo 返回 ISO 日期时间字符串（如 `2026-06-22T00:00:00.000Z`）的解析错误 |

> 注：以上 3 个文件已提交到当前分支 `fix/etf-list-type-filter`，尚未 push。

## 用户当前可使用的功能

### 1. 标的列表 `/etfs`
- 市场列显示 `US`
- 类型列显示 `ETF` 或 `个股`
- 支持搜索 `SPY.US`、`AAPL.US` 等代码

### 2. 全市场筛选器 `/screen`
- 市场选择器可选择 `美股`
- 类型选择器可选择 `ETF` / `个股`

### 3. 标的详情页 `/etfs/:code`
- 查看 K 线行情、技术指标、综合评分、AI 分析 Tab
- **提示**：仅上述 14 只核心标的有价格数据，其余会显示“暂无历史行情数据”

### 4. AI 功能
- `/research`：输入美股代码生成研报
- `/sentiment`：输入美股代码查看市场情绪
- `/chat`：向 AI 询问关于美股标的的分析

## 环境配置

已写入 `.env`（git 不追踪）：

```env
FINNHUB_API_KEY=<已脱敏，原 key 曾明文入库，视为已泄露，需轮换>
TIINGO_API_KEY=<已脱敏，原 key 曾明文入库，视为已泄露，需轮换>
FMP_API_KEY=<已脱敏，原 key 曾明文入库，视为已泄露，需轮换>
```

> ⚠️ 2026-07-21 文档审查时发现此处三个 API key 为明文且已进 git 历史，已脱敏。请到 Finnhub / Tiingo / FMP 后台重新生成 key 并更新 `.env`。

## 后续工作

### 补全价格数据

yfinance 对批量下载做了严格限流，本次仅成功抓回 14 只核心标的。完整覆盖 569 只标的价格需依赖调度器逐步回填：

```bash
python -m app.core.scheduler
```

调度器已配置：
- `us_daily_etl`：每天北京时间 05:00 执行
- `us_indicator_calculation`：每天北京时间 05:30 执行
- `us_stock_discovery`：每周日 02:00 执行

### 服务器首次部署脚本

在新服务器或清理后的环境首次启用美股时，需手动执行：

```bash
# 1. 确保 .env 中已配置 FINNHUB_API_KEY / TIINGO_API_KEY / FMP_API_KEY

# 2. 初始化美股 ETF
python scripts/init_us_etfs.py --apply

# 3. 初始化美股个股（S&P 500）
python -c "
from app.core.database import SessionLocal
from app.data.pipelines.us_stock_discovery import USStockDiscoveryPipeline
db = SessionLocal()
USStockDiscoveryPipeline(db).run()
"

# 4. 启动调度器，后续自动回填价格
python -m app.core.scheduler
```

## 已知限制

- FMP 免费 Key 已无法获取 S&P 500 成分股，当前使用公开 CSV 作为 fallback。
- yfinance 限流导致大规模历史回填较慢，建议通过调度器分日增量补充。
- Tiingo 免费档 50 请求/小时，不适合一次性回填全部 569 只标的。
