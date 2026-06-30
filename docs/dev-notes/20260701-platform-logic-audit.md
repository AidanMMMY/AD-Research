# AD-Research 全平台业务逻辑与功能逻辑检查报告

**状态**：审查完成，2026-07-01 启动修复 Sprint

**检查日期**：2026-07-01  
**检查范围**：后端服务、数据管道、指标/评分算法、策略回测信号、模拟/真实交易、前端 UI、安全运维  
**检查方法**：代码走查 + 专业投研平台最佳实践对照 + 公开资料检索  
**数据资源**：akshare（A 股）、Tushare Pro（A 股股票/基本面）、yfinance（跨境）、Finnhub / Tiingo / FMP（美股）、Binance（加密货币）、DeepSeek（AI 研报）

---

## 1. 执行摘要

AD-Research 已经从“手工 ETF 投研”演进为一个**功能较完整的 Web 投研平台**：覆盖 A 股 ETF/个股、美股 ETF/个股、港股/日股、加密货币的多市场数据采集；具备技术指标、综合评分、筛选排名、标的池管理、策略回测、交易信号、模拟/真实交易、AI 研报、自动化报告等模块。

但在本次检查中发现：

1. **若干影响正确性的逻辑/算法 bug** 必须尽快修复（数据 provider 接口契约、回测成本模型、风控日盈亏计算、AI 研报属性错误等）。
2. **真实交易模块存在权限与风控缺口**，在启用真实资金前必须补齐。
3. **前端有多个“已实现后端但未挂路由/未接线”的功能**，导致部分能力无法使用（加密货币列表、真实交易面板、绩效归因、SSE 行情流等）。
4. 与 Bloomberg Terminal、Wind、聚宽/米筐、Portfolio123、Portfolio Visualizer 等专业平台相比，平台在**因子库、VaR/压力测试、点-in-time 基本面、组合优化、实时行情、 survivorship-bias-free 回测**等方面仍有明显差距。

本报告按模块列出问题与建议，并在第 9 章给出**按优先级与数据可得性排序**的补全清单。

---

## 2. 平台现状速览

### 2.1 后端能力

| 模块 | 状态 | 关键文件 |
|------|------|---------|
| 认证/用户/设备 | 已实现 | [app/api/v1/auth.py](app/api/v1/auth.py) |
| ETF/股票/加密货币列表与详情 | 已实现 | [app/api/v1/etfs.py](app/api/v1/etfs.py)、[app/api/v1/stocks.py](app/api/v1/stocks.py)、[app/api/v1/crypto.py](app/api/v1/crypto.py) |
| 行情 OHLCV | 已实现 | [app/api/v1/market_data.py](app/api/v1/market_data.py) |
| 技术指标/批量指标 | 已实现 | [app/data/indicators/](app/data/indicators/) |
| 综合评分/模板 | 已实现 | [app/services/scoring_service.py](app/services/scoring_service.py) |
| 筛选器/排名/板块轮动 | 已实现 | [app/services/screening_service.py](app/services/screening_service.py)、[app/services/sector_rotation_service.py](app/services/sector_rotation_service.py) |
| 标的池/权重/快照/相关性 | 已实现 | [app/services/pool_service.py](app/services/pool_service.py)、[app/services/pool_enhancement_service.py](app/services/pool_enhancement_service.py) |
| 策略/回测/信号 | 已实现 | [app/services/backtest_engine.py](app/services/backtest_engine.py)、[app/services/signal_generator.py](app/services/signal_generator.py) |
| 模拟交易 | 已实现 | [app/services/paper_trading_service.py](app/services/paper_trading_service.py) |
| 真实交易（Binance） | 已实现但路由/权限有风险 | [app/api/v1/live_trading.py](app/api/v1/live_trading.py)、[app/services/risk_control.py](app/services/risk_control.py) |
| AI 研报/聊天 | 已实现 | [app/services/research_service.py](app/services/research_service.py) |
| 报告/通知/部署面板 | 已实现 | [app/services/report_service.py](app/services/report_service.py)、[app/api/v1/deployments.py](app/api/v1/deployments.py) |

### 2.2 前端能力

| 页面 | 状态 |
|------|------|
| Dashboard / ETF 列表 / 详情 / 筛选器 / 池 / 评分 / 报告 | 已实现 |
| 板块轮动 / 相关性 / 收益对比 / 信号 / 策略 / 回测 | 已实现 |
| 加密货币列表 | 已实现页面，但 hooks 为 stub，数据为空 |
| 真实交易面板 | 已实现页面，但**未注册路由** |
| 回测绩效归因 | 后端已提供，前端未接入 |
| SSE 实时行情流 | 后端已提供，前端未接入 |

---

## 3. 数据源与 ETL 逻辑检查

### 3.1 已确认的逻辑/契约错误

#### 1) `ETFInfo` dataclass 字段缺失导致运行时 TypeError

- [app/data/providers/base.py:8](app/data/providers/base.py#L8) 中的 `ETFInfo` 只有 `code/name/market/exchange/category/manager/currency/is_qdii/underlying_index/inception_date/instrument_type`，**没有 `sector/industry/list_date`**。
- 但 [app/data/providers/fmp_provider.py:88-98](app/data/providers/fmp_provider.py#L88-L98) 的 public CSV fallback 会传入 `sector=`、`industry=`。
- [app/data/providers/tushare_provider.py:191-200](app/data/providers/tushare_provider.py#L191-L200) 会传入 `list_date=`。
- **结果**：当调用这些 provider 的 `fetch_etf_list()` 时，会抛出 `TypeError`。

**建议**：要么在 `ETFInfo` 中补齐 `sector`、`industry`、`list_date`（推荐），要么删除调用处的额外字段。

#### 2) A 股 ETF 日终采集未按 `instrument_type` 过滤

- [app/data/pipelines/a_share.py:40-45](app/data/pipelines/a_share.py#L40-L45) 只过滤 `market == "A股"` 和 `status == "active"`。
- 如果 `etf_info` 中同时存在 A 股个股（`instrument_type == "STOCK"`），这些个股也会被传给 `AkshareProvider.fetch_daily_bars()`，而 Akshare 的接口是 ETF 专用，会导致失败或异常。

**建议**：增加 `.filter(ETFInfo.instrument_type == "ETF")`。

#### 3) Binance 涨跌幅计算错误

- [app/data/providers/binance_provider.py:256-261](app/data/providers/binance_provider.py#L256-L261) 中：

```python
"change_pct": ((close_px - float(candle[2])) / float(candle[2]) * 100)
```

`candle[2]` 是 **high**，不是 open 或 prev_close。这会导致 `change_pct` 变成 `(close - high) / high`，经常出现负数或错误值。

**建议**：使用 `(close - open) / open` 或接入前一日 close 计算真实涨跌幅。

#### 4) Crypto seed 列表与 Provider 默认列表不一致

- [app/data/pipelines/crypto_daily.py:28-44](app/data/pipelines/crypto_daily.py#L28-L44) 只 seed 了 15 个币种。
- [app/data/providers/binance_provider.py:32-58](app/data/providers/binance_provider.py#L32-L58) 默认列表有 25 个。
- 注释声称“matches BinanceProvider._DEFAULT_CRYPTO”，实际不匹配。

**建议**：让 pipeline 直接引用 `BinanceProvider._DEFAULT_CRYPTO` 或保持显式同步。

#### 5) 复权/公司行为处理缺失

- 数据库已存在 [app/models/etf.py:116-158](app/models/etf.py#L116-L158) 的 `ETFCorporateAction` 表，但**没有任何 pipeline 写入数据**。
- A 股 ETF 通过 Akshare 取的是前复权数据，但 `adj_factor` 被保留为默认值 `1.0`，原始价格丢失。
- 美股 yfinance 批量下载在 [app/data/providers/yfinance_provider.py:157](app/data/providers/yfinance_provider.py#L157) 处直接写 `adj_factor=1.0`，而价格未做 split/dividend 调整。
- 这会导致美股个股在拆股/分红后的指标、收益、回测结果失真。

**建议**：
- 对于 A 股个股，用 Tushare `adj_factor` 计算并存储 `adj_close` 和 `adj_factor`。
- 对于美股，从 yfinance `actions` 或 Tiingo 元数据填充 `ETFCorporateAction`，并基于事件表计算复权因子。
- 回测和指标计算统一使用 adjusted close。

#### 6) 数据校验层存在缺口

- L2 业务校验只检查 `high >= low`、`close ∈ [low, high]`、`volume >= 0`，**未检查 `open ∈ [low, high]`**。
- L3 对 `|change_pct| > 20%` 仅告警，但对加密货币/A 股小盘股来说 20% 并不异常，阈值应分市场/品种设置。
- L4 完整性校验只列出缺失代码，**不阻止写入**，导致某只 ETF 缺失数据时，指标/评分表仍会被后续任务覆盖为旧值或空值。

**建议**：增加 `open` 校验、分市场阈值、当 L4 缺失比例超过阈值时可选阻断 load。

#### 7) upsert 时丢弃合法零值

- [app/data/pipelines/a_share.py:94-95](app/data/pipelines/a_share.py#L94-L95) 使用 `{k: v for k, v in record.items() if v is not None}`。
- 这会**丢弃 `volume=0`、`change_pct=0` 等合法零值**，导致 ON CONFLICT UPDATE 时旧值不会被清零。

**建议**：改为 `if v is not None or (k in nullable_numeric_fields and v == 0)`，或直接保留所有非 None 字段。

#### 8) 收益率窗口存在 off-by-one

- [app/data/indicators/risk.py:140-144](app/data/indicators/risk.py#L140-L144)：

```python
result["return_1w"] = result["close"].rolling(window=6, min_periods=2).apply(lambda x: calc_return(x, 5))
```

`rolling(window=6)` 传入的是一个长度为 6 的序列，但 `calc_return(x, 5)` 取 `x.iloc[-1] / x.iloc[-5] - 1`，两者差 4 根 K 线。对于完整窗口，实际计算的是 **4 日收益** 而非 5 日收益；对于更长期限（1m/3m/6m/1y）也存在同样问题。

**建议**：`rolling(window=n+1)` 或 `calc_return(x, window-1)`，并统一检查所有期限窗口。

#### 9) ATR 使用简单移动平均而非 Wilder 平滑

- [app/data/indicators/technical.py](app/data/indicators/technical.py) 中 ATR 用的是 `rolling(14).mean()`，而经典 ATR 使用 Wilder 平滑（指数加权）。

**建议**：若要与主流软件一致，改用 Wilder 平滑 ATR。

---

### 3.2 市场覆盖与数据可得性

| 市场 | 数据源 | 现状 | 可补全 |
|------|--------|------|--------|
| A 股 ETF | akshare | 完整，约 1500 只 | 需修复上述 filter/零值/复权问题 |
| A 股个股 | Tushare Pro | 已接入日线、估值、财报 | 需修复 dataclass 字段缺失；免费 tier 有积分限制 |
| 美股 ETF | Finnhub + yfinance/Tiingo | 仅约 70 只 hard-code，动态性不足 | 改用 ETF.com / StockAnalysis 公开列表或付费数据源 |
| 美股个股 | FMP/public CSV + yfinance/Tiingo | 仅 S&P 500 | 可扩展至 Nasdaq-100/Russell 2000，但免费额度有限 |
| 港股/日股 | yfinance | 有映射但**无发现 pipeline 和定时任务** | 若需要应补 discovery + ETL，否则删除 dead code |
| 加密货币 | Binance | 25 只精选币种 | 可扩展至 top 100，但需关注 API 限流 |

**专业实践对照**：Bloomberg、Morningstar Direct、Wind 等平台都会维护**点-in-time（PIT）基本面**和**无幸存者偏差**的历史数据。当前平台使用“最新列表回测”，存在幸存者偏差；且未处理公司行为，回测结果在美股长周期上可信度较低。

---

## 4. 指标与评分算法检查

### 4.1 评分方向与权重

- [app/services/scoring_service.py:37-63](app/services/scoring_service.py#L37-L63) 配置：
  - `return/sharpe/liquidity/trend` → `direction: "asc"`（越高越好）
  - `risk` → `direction: "desc"`（越低越好）
- 经核对 [app/data/indicators/scoring.py:103-106](app/data/indicators/scoring.py#L103-L106) 的翻转逻辑，`desc` 会把低风险的低百分位翻转为高分，**方向配置是正确的**。
- 但 `scoring_service.py` 中命名容易误导，建议加注释说明 `asc = 越高越好，desc = 越低越好`。

### 4.2 评分方法论评估

- 当前评分是**横截面百分位排名**：对每个维度内的指标取平均后，计算全市场百分位，再按权重合成。
- **优点**：简单、直观、对异常值不敏感。
- **缺点**：
  - 缺少**因子有效性检验**（IC、IR、分层收益、换手率）。
  - 缺少**因子正交化/去相关**，收益、趋势、夏普可能高度相关。
  - 当某个 ETF 缺失某维度指标时，该维度被直接忽略，导致不同 ETF 的合成基础不一致。
  - 未考虑**市场/品种差异**：A 股 ETF、美股个股、加密货币的波动特征不同，直接跨市场排名可比性弱。

**建议**：
- 对缺失维度填充中性分（50）或单独标记，避免“因缺失而得分偏高/偏低”。
- 增加 IC/IR 报表，追踪各维度预测能力。
- 对跨市场场景，可先按市场分别排名，再提供“同市场排名”作为主要参考。

### 4.3 板块轮动

- [app/services/sector_rotation_service.py](app/services/sector_rotation_service.py) 计算板块平均收益、夏普、波动率、RSI，相对强弱 = 板块收益 - 全市场平均收益。
- 轮动信号：排名较上周上升/下降 ≥3 位触发 `up`/`down`。
- **评价**：逻辑简洁可用，但缺少**动量 half-life**、**相关性聚类**、**资金流**等进阶维度。

---

## 5. 策略、回测、信号与交易逻辑检查

### 5.1 回测引擎

#### 1) 交易成本模型错误

- [app/services/backtest_engine.py:110-117](app/services/backtest_engine.py#L110-L117)：

```python
def _apply_transaction_costs(price, commission_rate, slippage_rate):
    total_cost = commission_rate + slippage_rate
    return price * (1 - total_cost)
```

该函数被同时用于买入和卖出：
- 买入时：`effective_price = price * (1 - total_cost)`，相当于以更低价买入，**低估了成本**。
- 卖出时：`sale_proceeds = position * effective_price`，也低估了滑点/佣金。

正确的做法是对**成交金额**扣除双边成本：`cost = notional * (commission + slippage)`，买入时现金减少 `notional + cost`，卖出时现金增加 `notional - cost`。

#### 2) 信号基于复权价格，执行却用未复权价格

- [app/services/backtest_engine.py:169-183](app/services/backtest_engine.py#L169-L183)：
  - 生成信号时把 `close` 替换为 `adj_close`。
  - 模拟成交时却用 `row["close"]`（未复权）。
- 这会导致拆股/分红后，信号与成交价不在同一价格体系，收益计算失真。

**建议**：整个回测统一使用 `adj_close` 作为成交价；若需要展示真实价格，单独记录。

#### 3) 动量策略窗口语义

- `momentum = data["close"].pct_change(window)` 得到的是 `t - t-window` 的收益，符合常规“动量”定义，正确。

### 5.2 信号服务

#### 4) 去重逻辑无效

- [app/services/signal_service.py:38-41](app/services/signal_service.py#L38-L41)：

```python
seen_keys = set()
for sig in signals:
    key = (strategy_id, etf_code, trade_date)
    if key in seen_keys:
        continue
    seen_keys.add(key)
```

由于 `strategy_id/etf_code/trade_date` 在整个循环内固定，`seen_keys` 永远不会命中，无法去重。

**建议**：若需要按 signal_type 去重，key 应包含 `sig["type"]`；若每个 (strategy, etf, date) 只保留一条信号，则把去重提前到循环外。

### 5.3 模拟交易

#### 5) 胜率计算是占位逻辑

- [app/services/paper_trading_service.py:346-347](app/services/paper_trading_service.py#L346-L347)：

```python
if total_realized > 0:
    win_count = max(1, trade_count // 2)  # rough estimate
```

这是估算而非真实胜率，会导致绩效指标失真。

**建议**：通过每笔 SELL 订单对应的 BUY 成本计算 realized PnL，再统计正负。

### 5.4 AI 研报

#### 6) `_build_score_text` 属性名错误

- [app/services/research_service.py:288-293](app/services/research_service.py#L288-L293) 访问 `score.return_score`、`score.risk_score`、`score.trend_score`。
- 但 [app/models/scoring.py:84-88](app/models/scoring.py#L84-L88) 实际列名为 `score_return`、`score_risk`、`score_trend`。
- **结果**：当 ETF 有评分数据时，调用 AI 研报会触发 `AttributeError`。

**建议**：立即修正为 `score.score_return` 等。

### 5.5 真实交易（Binance）

#### 7) 下单/撤单权限过宽

- [app/api/v1/live_trading.py:311-317](app/api/v1/live_trading.py#L311-L317) 中 `place_order` 仅要求 `get_current_user`（任意登录用户），而配置管理才需要 admin。
- **风险**：任何被盗用的普通用户账号都可以下单，只要某个 config 已启用。

**建议**：下单/撤单端点至少要求 `require_admin`，或增加“交易操作”独立权限角色。

#### 8) 风控日盈亏计算错误

- [app/services/risk_control.py:163-178](app/services/risk_control.py#L163-L178) 的 `_daily_realized_pnl()` 直接对 `LiveTradePosition.realized_pnl` 求和，**没有时间过滤**。
- 这会累计所有历史已实现盈亏，导致日亏损熔断被错误触发或永不触发。

**建议**：按 `created_at/trade_date` 过滤今日订单/成交，再计算当日 realized PnL。

#### 9) 动态风险规则表未启用

- [app/models/trading.py:274](app/models/trading.py#L274) 定义了 `RiskRule` 表，但 [app/services/risk_control.py](app/services/risk_control.py) 所有检查均硬编码读取 `LiveTradeConfig`，从未查询 `RiskRule`。

**建议**：要么移除 `RiskRule` 表，要么实现从表中读取规则并动态评估。

#### 10) 缺少交易所级别的必要校验

- 未校验 `LOT_SIZE` / `MIN_NOTIONAL` / `PRICE_FILTER` 等 Binance symbol filters。
- 未校验账户 USDT 余额是否足够。
- 未对市价单增加滑点缓冲。
- 缺少本地订单与交易所状态的定时对账（partial fill、状态变更）。
- 熔断器是内存级，重启后状态丢失。

**建议**：在真实交易启用前，必须补齐上述校验；熔断器改为 Redis 持久化。

---

## 6. 前端 / UI 功能检查

### 6.1 已确认的前端 bug/缺失

| 问题 | 位置 | 影响 |
|------|------|------|
| 加密货币 hooks 是 stub，未调用 `cryptoApi` | [web/src/hooks/useCrypto.ts](web/src/hooks/useCrypto.ts) | `/crypto` 页面始终为空 |
| 真实交易面板未注册路由 | [web/src/routes.tsx](web/src/routes.tsx) | 13 个 live-trading API 无 UI 入口 |
| 回测详情缺少绩效归因 tab | [app/api/v1/attribution.py](app/api/v1/attribution.py) | 后端能力浪费 |
| SSE 实时行情流未接入 | [app/api/v1/stream.py](app/api/v1/stream.py) | 页面价格静态，无实时感 |
| 评分模板管理 UI 缺失 | [web/src/api/score.ts](web/src/api/score.ts) | 后端支持 CRUD，前端只能查看 |
| 通知日志 UI 缺失 | [web/src/api/notification.ts](web/src/api/notification.ts) | 用户无法查看发送历史与失败原因 |
| 部署面板未加 admin guard | [web/src/App.tsx](web/src/App.tsx) | `/admin/deployments` 任意登录用户可访问 |
| 报告生成无状态轮询 | [web/src/pages/ReportBrowser](web/src/pages/ReportBrowser) | 用户需手动刷新才能看到完成 |

### 6.2 与专业投研 Dashboard 的差距

- **无全局标的搜索/命令面板**：TradingView、Koyfin、Wind 都提供 `Cmd+K` 式全局搜索。
- **无实时 tick/深度行情**：当前只有日线级别数据。
- **无表格导出（CSV/Excel）和报告 PDF 导出**。
- **无组合基准比较**：池分析和收益对比缺少与指数/自定义基准的叠加。
- **无 ETL/数据健康状态看板**：用户看不到数据是否最新、哪条 pipeline 失败。

---

## 7. 安全、风控与运维检查

### 7.1 已确认的安全风险

1. **CORS 过宽**：[app/main.py:54](app/main.py#L54) `allow_origins=["*"]` 且 `allow_credentials=True`，这是生产环境的严重反模式。
2. **默认密钥过弱且复用**：
   - [app/config.py:91](app/config.py#L91) `SECRET_KEY = "your-secret-key-change-in-production"`。
   - [app/config.py:67](app/config.py#L67) 当 `notification_encryption_key` 为空时，使用 `SECRET_KEY` 作为 Fernet 密钥来源。
   - 一旦 `SECRET_KEY` 泄露，JWT 和 Binance API 密钥同时暴露。
3. **SSE 部署日志接口通过 query 参数传 JWT**：[app/api/v1/deployments.py:52](app/api/v1/deployments.py#L52)，token 可能泄露在日志/代理中。
4. **真实交易总开关是全局的**：`binance_trading_enabled=True` 会同时武装所有 config，没有环境级 testnet 强制。
5. **无审计日志表**：admin 操作、真实交易下单、熔断重置等行为没有持久化审计记录。

### 7.2 运维隐患

1. **Scheduler 在模块加载时启动**：[app/main.py:198](app/main.py#L198)。若使用 Gunicorn 多 worker，每个 worker 都会启动 scheduler，导致任务重复执行。
   - **建议**：只在主进程/单 worker 中启动；或改用独立 scheduler 进程。
2. **CronTrigger 未指定 timezone**：[app/core/scheduler.py:631](app/core/scheduler.py#L631) 等。APScheduler 默认使用系统本地时区；若容器时区非 Asia/Shanghai，所有定时任务会错位。
   - **建议**：统一 `CronTrigger(hour=..., minute=..., timezone="Asia/Shanghai")`。
3. **Job 失败仅打印日志**，无告警（邮件/企业微信/飞书）。
4. **无请求限流/输入校验中间件**：部分排序字段依赖服务端白名单，但缺少全局 rate limit。

---

## 8. 与专业投研平台最佳实践对比

结合公开资料检索，专业投研平台（Bloomberg Terminal、Morningstar Direct、Wind、聚宽/米筐、Portfolio123、Portfolio Visualizer、OpenBB、Koyfin）普遍具备以下能力：

| 能力维度 | 专业平台做法 | AD-Research 现状 | 差距 |
|---------|-------------|-----------------|------|
| **数据质量** | 点-in-time 基本面、无幸存者偏差、公司行为复权、多源对账 | 仅日线数据，未处理 PIT/幸存者偏差/公司行为 | 大 |
| **因子/alpha 研究** | 因子库（IC/IR、分层测试、换手率、相关性、正交化） | 只有固定 5 维度评分 | 大 |
| **回测** | 事件驱动/向量化双引擎、交易成本、滑点、参数稳健性、walk-forward | 已实现基础回测，但成本模型和复权处理有误 | 中 |
| **风险分析** | VaR、Expected Shortfall、压力测试、情景分析、因子暴露 | 只有波动率/回撤/夏普 | 大 |
| **组合优化** | 均值-方差、风险平价、Black-Litterman、目标波动率 | 池内只有等权/评分加权/风险平价建议权重 | 中 |
| **绩效归因** | Brinson、因子归因、基准跟踪误差 | 已实现简化 Brinson，但前端未展示 | 中 |
| **实时行情** | tick/分钟级数据、WebSocket 推送 | 只有日线，SSE 未接入 | 大 |
| **报告/导出** | PDF/HTML/Excel、定时推送 | HTML/Markdown，无 PDF/Excel | 中 |
| **基准数据** | 指数/ETF 基准日线 | 未单独维护基准表 | 中 |

参考来源：[Hebbia: 10 Best Investment Research Software](https://www.hebbia.com/resources/investment-research-software)、[AlphaSense: 12 Alternatives to Bloomberg Terminal](https://www.alpha-sense.com/compare/alternatives-to-bloomberg-terminal/)、[Koyfin: 10 Best Alternatives to Bloomberg Terminal](https://www.koyfin.com/blog/best-bloomberg-terminal-alternatives/)、[Liberated Stock Trader: Top 10 Backtesting Tools](https://www.liberatedstocktrader.com/best-stock-backtesting-software-strategies/)、[Databricks Financial Services Lakehouse for Quantitative Research](https://www.databricks.com/blog/databricks-financial-services-lakehouse-quantitative-research)、[FactorMiner/OpenReview](https://openreview.net/pdf?id=TTsecyqrW3)、[QuantInsti: Building a Quant Research Pipeline](https://blog.quantinsti.com/financial-data-apis-algorithmic-trading-fmp/)、[量化投资中的 AT 系统与策略回测框架详解](https://edu.51cto.com/article/note/9094.html)。

---

## 9. 可补全建议（按优先级与数据可得性）

### P0 — 必须立即修复（影响正确性或安全）

1. **修复 `ETFInfo` dataclass 字段缺失**（[base.py:8](app/data/providers/base.py#L8)、[fmp_provider.py:88](app/data/providers/fmp_provider.py#L88)、[tushare_provider.py:191](app/data/providers/tushare_provider.py#L191)）。
2. **修复 Binance `change_pct` 计算**（[binance_provider.py:256](app/data/providers/binance_provider.py#L256)）。
3. **修复 A 股 ETF pipeline 的 instrument_type 过滤**（[a_share.py:40](app/data/pipelines/a_share.py#L40)）。
4. **修复 upsert 丢弃零值**（[a_share.py:94](app/data/pipelines/a_share.py#L94)）。
5. **修复回测交易成本模型**（[backtest_engine.py:110](app/services/backtest_engine.py#L110)）。
6. **统一回测价格体系**（使用 adj_close 执行，[backtest_engine.py:183](app/services/backtest_engine.py#L183)）。
7. **修复 AI 研报属性名错误**（[research_service.py:288](app/services/research_service.py#L288)）。
8. **修复 RiskControl 日盈亏计算**（[risk_control.py:163](app/services/risk_control.py#L163)）。
9. **限制真实交易下单/撤单为 admin**（[live_trading.py:311](app/api/v1/live_trading.py#L311)）。
10. **收紧 CORS**（[main.py:54](app/main.py#L54)）。
11. **修复 return_1w 等收益率窗口 off-by-one**（[risk.py:140](app/data/indicators/risk.py#L140)）。
12. **修复信号去重逻辑**（[signal_service.py:38](app/services/signal_service.py#L38)）。
13. **修复模拟交易胜率占位逻辑**（[paper_trading_service.py:346](app/services/paper_trading_service.py#L346)）。
14. **同步 Crypto seed 与 provider 列表**（[crypto_daily.py:28](app/data/pipelines/crypto_daily.py#L28)）。

### P1 — 短期补齐（显著提升可用性）

1. **前端接入加密货币 API**（[useCrypto.ts](web/src/hooks/useCrypto.ts)）并新增 `/crypto/:code` 详情页。
2. **注册 `/trading` 路由**让真实交易面板可用（[routes.tsx](web/src/routes.tsx)）。
3. **回测详情增加绩效归因 tab**（[attribution.py](app/api/v1/attribution.py)）。
4. **前端接入 SSE 实时行情流**（[stream.py](app/api/v1/stream.py)），Dashboard/列表页展示实时价格。
5. **评分模板管理 UI**（创建/编辑/删除）。
6. **通知日志页面**。
7. **ETL 状态/数据健康看板**（调用 `/api/v1/etl/status`）。
8. **报告生成状态轮询 + PDF 导出**。
9. **CORS、scheduler 时区、多 worker 启动**等运维修复。
10. **真实交易补齐 symbol filters、余额检查、市价单滑点、订单对账、Redis 熔断器**。
11. **A 股个股复权因子接入**（Tushare `adj_factor`）。
12. **增加数据验证的 open 校验、分市场阈值、L4 缺失阻断选项**。

### P2 — 中期战略能力（取决于数据投入）

1. **建立因子库/alpha 库**：
   - 定义因子 DSL（基于已有指标扩展）。
   - 单因子测试：IC、IR、分层收益、换手率、最大回撤。
   - 因子相关性分析与正交化。
   - 因子有效性监控与失效预警。
2. **点-in-time 基本面数据管道**：
   - 对 A 股 `StockIncome`/`StockBalanceSheet` 按报告期与披露日对齐，避免前视偏差。
3. **公司行为与复权体系**：
   - 维护 `ETFCorporateAction`，所有指标/回测基于 adjusted close。
4. **风险分析模块**：
   - VaR（历史模拟/参数法）、Expected Shortfall、压力测试、情景分析。
   - 池级风险：行业集中度、单一标的比例、VaR 贡献。
5. **组合优化器**：
   - 均值-方差有效前沿、风险平价、Black-Litterman、目标波动率约束。
6. **基准数据与权益历史**：
   - 新增 `benchmark_daily_bar` 和 `account_balance_history` 表。
   - 池分析、回测、收益对比均支持基准叠加。
7. **无幸存者偏差回测**：
   - 回测时使用历史时刻的标的列表，而不是当前 active 列表。
8. **另类数据/舆情**：
   - 接入新闻、雪球/东方财富舆情、宏观数据，用于情绪指标和 AI 研报增强。
9. **移动端优化**：
   - K 线、相关性、对比页面的移动端适配，底部导航。
10. **全局搜索/命令面板与键盘快捷键**。

---

## 10. 参考来源

- [Hebbia: 10 Best Investment Research Software Platforms [2026]](https://www.hebbia.com/resources/investment-research-software)
- [AlphaSense: 12 Alternatives to Bloomberg Terminal for 2026](https://www.alpha-sense.com/compare/alternatives-to-bloomberg-terminal/)
- [Koyfin: 10 Best Alternatives to Bloomberg Terminal in 2026](https://www.koyfin.com/blog/best-bloomberg-terminal-alternatives/)
- [Investopedia: What Is a Bloomberg Terminal?](https://www.investopedia.com/terms/b/bloomberg_terminal.asp)
- [Liberated Stock Trader: Top 10 Backtesting Tools](https://www.liberatedstocktrader.com/best-stock-backtesting-software-strategies/)
- [Portfolio123 vs YCharts – Feature-by-feature comparison](https://www.findmymoat.com/vs/portfolio123-vs-ycharts)
- [testfolio: Portfolio Backtester for ETFs and Asset Allocation](https://testfol.io/)
- [Databricks Financial Services Lakehouse for Quantitative Research](https://www.databricks.com/blog/databricks-financial-services-lakehouse-quantitative-research)
- [QuantInsti: Building a Quant Research Pipeline Using Financial Data APIs](https://blog.quantinsti.com/financial-data-apis-algorithmic-trading-fmp/)
- [FactorMiner / OpenReview](https://openreview.net/pdf?id=TTsecyqrW3)
- [Quantt: Big Data Pipelines in Finance](https://www.quantt.co.uk/resources/big-data-pipelines-in-finance)
- [量化投资中的 AT 系统与策略回测框架详解](https://edu.51cto.com/article/note/9094.html)
- [量化投资对于数据源、回测、实盘平台的选择](https://www.cnblogs.com/sljsz/p/16155146.html)
- [OpenBB Terminal](https://openbb.co/)（开源投研终端参考）

---

*本报告为本地检查文档，未做任何代码修改，也未推送到远程仓库。*
