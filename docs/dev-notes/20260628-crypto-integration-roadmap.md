# 数字货币交易/分析功能集成建议报告

> 生成日期：2026/06/28  
> 目标：基于现有 AD-Research 投资研究平台，评估并规划接入 Binance 数字货币数据与交易能力的可行路径。
>
> 最后核实更新：2026-07-21
>
> **实施状态**：本报告提出的三个阶段已全部落地——
> - 阶段一（只读分析）：`app/data/providers/binance_provider.py`、`app/data/pipelines/crypto_daily.py`、`app/api/v1/crypto.py`，前端 `CryptoList` / `CryptoDetail` 页面（`/crypto`、`/crypto/:code`）均已上线；
> - 阶段二（模拟交易）：`app/services/paper_trading_service.py` + `app/api/v1/paper_trading.py`，前端 `/paper-trading` 页面；
> - 阶段三（真实交易低/中风险）：`app/services/trading/binance_client.py`、`app/services/risk_control.py`、`app/api/v1/live_trading.py`，前端 `/live-trading` 交易面板，详见 [[20260628-phase3-live-trading-implementation]]。
>
> 正文保留当时的评估与规划原貌，其中"现状：无加密货币相关代码"等描述已不再成立，请以本注为准。

---

## 一、现有平台能力与定位

AD-Research 当前是一个以 ETF 和个股研究为核心的 Web 投资研究平台：

- **后端**：FastAPI + SQLAlchemy（asyncpg）+ Alembic + PostgreSQL 16 + Redis 7
- **前端**：React 18 + Vite + TypeScript + Ant Design 5 + ECharts / lightweight-charts
- **数据层**：已模块化封装 akshare / yfinance / Finnhub / Tiingo / FMP 等 provider
- **核心能力**：ETL 管道、技术指标、复合评分、回测引擎、信号生成、组合管理、AI 研报、调度任务
- **当前资产**：A 股 ETF/个股、美股 ETF/个股、港股/日股 ETF、加密货币（Binance 现货）
- **现状**：~~无加密货币相关代码~~ 加密货币数据与交易能力已按本报告三阶段全部落地（见文首实施状态注）；真实交易具备 Binance 现货下单/撤单能力，带多层风控开关（`binance_trading_enabled` 等，默认关闭）

因此，接入数字货币并非从零开始，而是对现有数据、指标、评分、回测、信号等模块的横向扩展。

---

## 二、可实现的完整功能全景

按风险与复杂度由低到高可分为三个阶段。

### 阶段一：只读数据分析（强烈推荐优先做）

这是风险最低、与现有架构最契合的切入点。

| 功能 | 可复用模块 | 说明 |
|------|-----------|------|
| 币种列表与基础信息 | `etf_info` / 抽象为 `instrument_info` | BTC、ETH、SOL、BNB、DOGE 等现货基础信息 |
| K 线/日线数据抓取 | 现有 ETL pipeline 模式 | 接入 Binance `klines` API，日线/4h/1h |
| 技术指标计算 | `indicator_engine` | RSI、MACD、MA、ATR、Bollinger、波动率、夏普、最大回撤 |
| 评分与排名 | `etf_score` 评分服务 | 5 维度评分，生成排名 |
| 信号生成 | `signal_generator` | 动量、均值回归、RSI 等信号 |
| 回测 | `backtest_engine` | 对数字货币历史 K 线跑策略 |
| 组合/池子管理 | `etf_pools`、`pool_member` | 建立 crypto-only 或混合 pool |
| AI 研究报告 | `research_service` | 对 BTC/ETH 生成技术面/趋势研报 |
| Dashboard 展示 | 前端 KLineChart、ScoreRadar 等 | 新增 Crypto 路由和页面 |

**推荐数据源**：

- Binance REST API（免费，有频率限制）
- `ccxt` 统一库（便于未来切换 OKX、Coinbase 等）

**推荐粒度**：先从日线开始，再扩展到 4h/1h，不建议一开始做秒级/高频。

---

### 阶段二：模拟交易与纸上验证

在真实资金风险之前，验证策略与系统稳定性。

| 功能 | 说明 |
|------|------|
| Binance Testnet 接入 | `testnet.binance.vision`，免费测试 API |
| 模拟仓位跟踪 | 记录虚拟买入/卖出，计算 PnL |
| 信号 → 模拟下单 | 完整闭环验证，但不碰真实资金 |
| 执行质量分析 | 滑点、成交率、延迟、部分成交 |
| 24/7 调度适配 | 数字货币全年无休，需调整 scheduler 逻辑 |

**为什么先这样做**：

- 币安 API 限流、维护、网络抖动比传统金融数据更常见
- 24/7 交易对 scheduler、重试、补偿机制要求更高
- 可在零资金风险下验证信号→下单→成交→PnL 全链路

---

### 阶段三：真实交易执行（按风险分层）

#### 低风险（可做，但需严格控制）

| 功能 | 风险 | 必要措施 |
|------|------|---------|
| 查询余额与持仓 | 低 | API Key 仅授予 `SPOT` 读取权限 |
| 查询订单/历史成交 | 低 | 只读权限即可 |
| 价格/行情订阅 | 低 | 无资金风险 |

#### 中风险（谨慎做，必须加风控）

| 功能 | 风险 | 必要措施 |
|------|------|---------|
| 现货下单/撤单 | 中 | 单笔限额、日限额、IP 白名单、签名安全 |
| 现货止损/止盈/条件单 | 中 | 本地 + 交易所双重风控 |
| 小额自动化策略（现货） | 中 | 独立风控模块、熔断、异常监控 |

#### 高风险（强烈不建议做）

| 功能 | 风险 | 建议 |
|------|------|------|
| 合约/杠杆/期权 | 极高 | 不建议在个人研究平台中实现 |
| 高频/量化自动交易 | 极高 | 需要专门的风控系统、低延迟基础设施 |
| 子账户划转/提现 | 高 | 避免开放此类权限 |

---

## 三、现有架构改造清单

### 后端改造

- 新增 `app/data/providers/binance_provider.py`：获取 K 线、币种信息、实时价格
- 扩展 `etf_info` 或新建 `instrument_info`：统一 ETF / 股票 / 加密货币的 instrument 模型
- 新增 `app/data/pipelines/crypto_daily.py`：加密货币 ETL 管道
- 在 `app/core/scheduler.py` 中增加币安数据任务（考虑 24/7）
- 新增 `app/services/trading/binance_client.py`：封装 Binance API 交互
- 新增 `app/services/risk_control.py`：真实交易必需的风控模块
- 新增 API routers：crypto instruments、bars、scores、signals、paper trading、live trading

### 前端改造

- 新增 Crypto 路由与页面（列表、详情、K 线、评分、信号）
- 复用 `KLineChart`、`ScoreRadar`、`CorrelationHeatmap` 等组件
- 新增 API Key 配置页面（仅限本地/安全环境存储）
- 新增模拟交易/真实交易状态面板

### 数据库改造

- 将 `etf_info` 抽象为 `instrument_info`，增加 `asset_class` 字段（`etf` / `stock` / `crypto`）
- `instrument_daily_bar`、`etf_indicator`、`etf_score`、`signal` 等表已具备 `(code, trade_date)` 复合键，可直接复用
- 新增交易相关表：`paper_trade`、`live_trade`、`trade_config`、`risk_rule`

---

## 四、安全、合规与风控要求

### API Key 安全

1. **绝不将 API Key 写入代码库**，使用环境变量 / Vault / 密钥管理服务
2. **权限最小化**：分析阶段只读；交易阶段仅开通 `SPOT` 交易权限
3. **配置 IP 白名单**：仅允许服务器公网 IP 访问
4. **日志脱敏**：禁止在日志中打印 API Key、签名、余额等敏感信息
5. **资金隔离**：仅将可承受完全损失的小部分资金放入交易账户

### 交易风控（真实交易必备）

- 单笔金额上限
- 每日累计亏损上限 / 连续亏损熔断
- API 超时/异常重试与熔断
- 防止重复下单
- 价格异常波动熔断（如 5 分钟内波动 > 10%）
- 非交易时段/维护窗口保护

### 合规提醒

- **中国大陆**：个人持有加密货币不违法，但境内加密货币交易所已被清退，Binance 对大陆用户 KYC 与访问有政策限制，需自行确认账户合规状态
- **税务**：多数国家/地区对加密货币交易收益有税务申报要求
- **平台责任**：若系统向他人提供资金管理或下单服务，可能触发金融监管牌照要求；仅供个人研究分析使用风险较低

---

## 五、建议实施路线

| 阶段 | 目标 | 预计周期 | 资金风险 |
|------|------|---------|---------|
| **阶段一 MVP** | 接入币安日线数据，展示 BTC/ETH K 线、指标、评分 | 1-2 周 | 无 |
| **阶段二 扩展** | 增加更多币种，接入 4h/1h 数据，crypto pool 与回测 | 2-4 周 | 无 |
| **阶段三 模拟验证** | 接入 Binance Testnet 做模拟交易，跑 1-2 个月 | 1-2 个月 | 无 |
| **阶段四 真实交易（可选）** | 小资金、严格风控、只做现货、单一策略 | 长期迭代 | 中 |

---

## 六、关键结论

- **数据分析/技术指标/回测/评分**：与现有平台高度契合，强烈建议优先实现。
- **模拟交易**：推荐作为验证策略与系统稳定性的必经阶段。
- **真实自动交易**：技术上可行，但需把安全、风控、合规放在第一位；建议只做现货，避免杠杆/合约/高频。
- 如果目标只是增强研究分析能力，阶段一+阶段二已能覆盖 80% 价值；真实交易应作为可选的、长期谨慎迭代的扩展。

---

*本报告作为后续开发规划与实施的参考依据。*
