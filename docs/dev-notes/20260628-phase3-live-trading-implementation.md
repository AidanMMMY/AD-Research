# 阶段三：真实交易（低/中风险）实现报告

> 日期：2026-06-28
> 状态：已完成
> 关联：[[20260627-scheduled-task-recovery-guide]] [[platform-functional-manual]]

---

## 概述

在阶段二（模拟交易）基础上，完成阶段三低/中风险内容：Binance 真实交易客户端、风控模块、真实交易 API、前端交易面板。

---

## 新建文件（7 个）

### 后端 — 服务层

| 文件 | 行数 | 说明 |
|------|------|------|
| `app/services/trading/__init__.py` | 5 | 包入口，导出 `BinanceClient` |
| `app/services/trading/binance_client.py` | 329 | 带签名的 Binance REST 客户端 — HMAC-SHA256 签名、速率限制、`place_order` / `cancel_order` 写操作 + 余额/订单历史读操作 |
| `app/services/risk_control.py` | 312 | 风控模块 — 全局开关、熔断、单笔限额、日亏损/下单数限制、60s 重复订单检测、币种白名单 |

### 后端 — API 层

| 文件 | 行数 | 说明 |
|------|------|------|
| `app/api/v1/live_trading.py` | 354 | 13 个真实交易 API 端点 |

### 前端

| 文件 | 行数 | 说明 |
|------|------|------|
| `web/src/api/liveTrading.ts` | 37 | 前端 API 客户端（10 个方法） |
| `web/src/hooks/useLiveTrading.ts` | 131 | 9 个 React Query hooks + 4 个 mutations |
| `web/src/pages/TradingPanel/index.tsx` | 410 | 交易面板：配置管理、余额总览、持仓/订单表格、下单弹窗、风控状态指示灯 |

---

## 修改文件（5 个）

| 文件 | 变更 |
|------|------|
| `app/config.py` | 新增 6 个 Phase 3 配置项：`binance_testnet_key`、`binance_testnet_secret`、`binance_trading_enabled`、`binance_max_order_value_usdt`、`binance_max_daily_loss_usdt`、`binance_max_daily_orders` |
| `.env.example` | 新增测试网 + 风控环境变量说明 |
| `app/main.py` | 导入 `live_trading` 并注册路由 `prefix="/api/v1/live-trading"` |
| `web/src/routes.tsx` | 新增 `/trading` 路由 + `TradingPanel` 懒加载，菜单图标 `TransactionOutlined` |
| `web/src/types/trading.ts` | 新增 8 个 Phase 3 TypeScript 接口 |
| `web/src/api/index.ts` | 导出 `liveTradingApi` |

---

## 13 个 API 端点

```
GET    /api/v1/live-trading/configs                       列表
POST   /api/v1/live-trading/configs                       创建（加密存储凭据）
PUT    /api/v1/live-trading/configs/{id}                  更新
DELETE /api/v1/live-trading/configs/{id}                  删除
GET    /api/v1/live-trading/configs/{id}/account          账户余额
GET    /api/v1/live-trading/configs/{id}/positions        持仓
GET    /api/v1/live-trading/configs/{id}/orders           订单历史
GET    /api/v1/live-trading/configs/{id}/trades           成交历史
POST   /api/v1/live-trading/configs/{id}/orders           下单（风控检查 → Binance）
DELETE /api/v1/live-trading/configs/{id}/orders/{order_id} 撤单
GET    /api/v1/live-trading/configs/{id}/risk-status      风控状态
POST   /api/v1/live-trading/configs/{id}/circuit-breaker/reset  重置熔断
GET    /api/v1/live-trading/risk-rules                    风控规则列表
```

---

## 风控设计

| 检查 | 类型 | 行为 |
|------|------|------|
| `binance_trading_enabled` 总开关 | 全局 | 关闭时拒绝所有订单 |
| 熔断状态 | 断路器 | 触发后拒绝所有订单，需 admin 手动重置 |
| 币种白名单 | `per_order` | 不在 `allowed_symbols` 的代码拒绝 |
| 单笔金额上限 | `per_order` | 超过 `max_order_value` → 拒绝 |
| 每日下单数 | `daily` | ≥ `max_daily_orders` → 触发熔断 |
| 每日亏损 | `daily` | 超过 `max_daily_loss` → 触发熔断 |
| 重复订单 | `duplicate` | 60s 内相同 (symbol, side) → 拒绝 |

### CircuitBreaker 类

- 内存级熔断器，按 `config_id` 隔离
- `trip(config_id, reason)` — 触发熔断
- `reset(config_id)` — 手动重置
- `is_tripped(config_id)` — 查询状态
- 生产环境建议改为 Redis 实现以支持进程重启后状态持久化

---

## 安全设计

1. **API Key 加密存储**：使用 `cryptography.fernet`（与 `NotificationService` 相同模式），Fernet 加密后以 `enc:` 前缀存入 `live_trade_config.api_key_encrypted` / `api_secret_encrypted`
2. **API 返回绝不包含明文密钥**：`LiveConfigOut` schema 不包含加密后的密钥字段
3. **默认关闭**：`binance_trading_enabled=False`，需手动设为 `True`
4. **创建配置默认 Testnet 模式**：`is_testnet=True`
5. **日志脱敏**：`BinanceClient` 不记录 API key/secret
6. **权限控制**：配置 CRUD 和熔断重置需要 admin 角色
7. **IP 白名单提醒**：文档中提醒用户在 Binance 后台配置 IP 白名单

---

## 关键组件说明

### BinanceClient (`app/services/trading/binance_client.py`)

独立的签名 REST 客户端，与阶段一的 `BinanceProvider`（只读）互补：

```
BinanceClient (authenticated):
  - ping()
  - get_account_info() / get_balances()
  - get_open_orders() / get_order_history() / get_trades()
  - get_exchange_info() / get_ticker_price()
  - place_order() / cancel_order() / get_order()

BinanceProvider (public, from Phase 1):
  - fetch_etf_list() / fetch_daily_bars() / fetch_realtime_quotes()
  - check_health() / get_market_hours()
```

两者共享相同的 `to_binance_symbol()` / `from_binance_symbol()` 转换逻辑。

### RiskControl (`app/services/risk_control.py`)

- `RiskControl.__init__(db, config, settings)` — 接收 ORM 对象和 Settings
- `check_order(instrument_code, side, quantity, price)` → `RiskCheckResult`
- `get_risk_status()` → dict（供 API 使用）
- `reset_circuit_breaker()` → dict

### Live Trading API (`app/api/v1/live_trading.py`)

- 低风险（只读）endpoint 需要登录
- 中风险（写操作）endpoint 需要登录 + 风控检查
- 配置管理端点需要 admin 角色

---

## 前端页面：TradingPanel

路由：`/trading`，菜单：`真实交易` (TransactionOutlined)

功能模块：
1. **配置选择器** — 下拉选择 + Testnet/LIVE 标签 + 启用/禁用开关 + 删除
2. **风控指标卡片** — 今日订单数、单笔上限、今日已实现盈亏、熔断状态 + 重置按钮
3. **账户余额** — 从 Binance 拉取并展示各资产可用/冻结/总量
4. **持仓表格** — 币种、数量、均价、现价、市值、未实现盈亏
5. **订单表格** — 时间、方向、币种、类型、状态 + 撤单按钮
6. **下单弹窗** — 币种代码、方向、限价/市价、数量、限价
7. **创建配置弹窗** — API Key/Secret（密码框）、Testnet 开关、风控参数

---

## 验证结果

- ✅ **Python** — 全部 imports 通过，13 条路由已注册到 `app.main`
- ✅ **TypeScript** — `tsc --noEmit` 零错误
- ✅ **配置** — `.env.example` 和 `config.py` 包含所有 Phase 3 设置项
- ✅ **数据库** — `LiveTradeConfig`、`LiveTradeOrder`、`LiveTradePosition`、`RiskRule` 4 张表已在阶段二的 migration 中创建（`7d05c7c0d4f0`）

---

## 使用方式

1. 在 [testnet.binance.vision](https://testnet.binance.vision) 注册测试 API Key
2. 启动后端 → 前端 `/trading` 页面 → 点击"创建配置"，填入 Testnet API Key/Secret
3. 启用配置 → 查看余额 → 挂小额定单（建议先挂一个不会成交的限价单）
4. 观察订单状态、持仓、风控指标
5. **永远不要用真实 API Key 做测试**

---

## 后续迭代建议

1. CircuitBreaker 改为 Redis 实现（重启后状态持久化）
2. 增加 WebSocket 实时行情推送至交易面板
3. 支持基于信号的自动真实交易（参考 `paper_trading_service.auto_trade_from_signals`）
4. 增加订单确认二次弹窗（防误触）
5. 增加 Binance 账户快照历史记录
