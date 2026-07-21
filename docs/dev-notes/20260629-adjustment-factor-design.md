# 拆股/分红复权因子改造方案（方案 B）

> 日期：2026-06-29
> 状态：~~设计完成，待 backfill 结束后一次性部署~~ **已实施并部署**（最后核实更新：2026-07-21）
>
> **实施情况核实（2026-07-21）**：
> - `instrument_daily_bar.adj_factor` 列与 `etf_corporate_action` 表均已入库（migration `a1b2c3d4e5f6_add_adj_factor_and_etf_corporate_action`）；
> - 指标计算（`app/data/indicators/calculator.py`）与回测引擎（`app/services/backtest_engine.py`）均已切换到复权价格体系；
> - A 股侧缺口也已补上：`TushareProvider.fetch_adj_factor()` + `app/scripts/backfill_a_share_adj_factor.py`；
> - **后续演进**：在原方案基础上新增了 `adj_factor_history` 表（migration `i9j0k1l2m3n4`），完整保存 Tushare 原始累计复权因子，前复权价按 `close * adj_factor / latest_adj_factor` 计算，`instrument_daily_bar.adj_factor` 保持同步以兼容旧逻辑。正文中的伪代码（`adj_close = close * adj_factor`）对应的是最初的归一化方案，与现实现略有差异，以代码为准。
>
> 关联文件：
> - `app/models/etf.py`
> - `app/data/providers/yfinance_provider.py`
> - `app/data/providers/tiingo_provider.py`
> - `app/data/indicators/calculator.py`
> - `app/services/backtest_engine.py`
> - `app/scripts/backfill_us_deep_history.py`
> - Alembic migration（已生成并执行：`a1b2c3d4e5f6`、`i9j0k1l2m3n4`）

## 背景

当前 `instrument_daily_bar` 只存储 OHLCV + amount，没有记录拆股、分红等复权事件。yfinance 默认返回的是**已拆股调整的价格**，但存在两个问题：

1. **调整数据错误**：如 `UVXY.US` 2011 年出现 $5145 亿的异常 close，导致 `volume * close` 溢出 `DECIMAL(18,4)`。
2. **无法区分真实行情与复权行情**：回测如果用复权价计算信号但用真实价成交，会不一致；反之若完全用真实价，拆股前后会出现跳空，指标失真。

## 目标

1. 在数据库层面记录每日复权因子 `adj_factor`。
2. Provider 拉取数据时同时采集拆股/分红事件，计算并保存 `adj_factor`。
3. 指标计算统一使用**前复权价格**（`close * adj_factor`）。
4. 回测信号生成用前复权价格，成交/佣金计算用真实价格。
5. 保留异常过滤作为兜底，防止错误数据入库。

## 方案设计

### 1. 数据库模型改造

#### `instrument_daily_bar` 新增字段

```python
adj_factor = Column(DECIMAL(18, 8), default=1.0, comment="复权因子：当日收盘价相对最新日期的累计调整系数")
```

- `adj_factor = 1.0` 表示无需复权。
- `adj_factor < 1.0` 表示历史上发生过拆股或分红，需把历史价格往上调。
- `adj_factor > 1.0` 表示反向拆股（reverse split）。
- 使用前复权价：`adj_close = close * adj_factor`。

#### 新增 `etf_corporate_action` 表

```python
class ETFCorporateAction(Base):
    __tablename__ = "etf_corporate_action"

    id = Column(Integer, primary_key=True, autoincrement=True)
    etf_code = Column(String(20), ForeignKey("etf_info.code", ondelete="CASCADE"), nullable=False, comment="标的代码")
    action_date = Column(Date, nullable=False, comment="事件生效日")
    action_type = Column(String(20), nullable=False, comment="事件类型：split/dividend/reverse_split")
    ratio = Column(DECIMAL(18, 8), nullable=False, comment="拆分/分红比例")
    source = Column(String(50), comment="数据来源")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("etf_code", "action_date", "action_type", name="uq_corp_action_code_date_type"),
        Index("idx_corp_action_code", "etf_code"),
        Index("idx_corp_action_date", "action_date"),
    )
```

事件类型：
- `split`：正向拆股，如 1:2，ratio=0.5（1 股变 2 股，历史价格 ×0.5）。
- `reverse_split`：反向拆股，如 2:1，ratio=2.0。
- `dividend`：现金分红，ratio = 分红金额 / 除权前收盘价。

### 2. Provider 改造

#### yfinance

yfinance 默认返回的价格已经是 split + dividend adjusted。为了得到**真实交易价**并自行计算复权因子，应使用：

```python
hist = yf.Ticker(ticker).history(start=..., end=..., auto_adjust=False, actions=True)
```

返回的 DataFrame 包含：
- `Open`, `High`, `Low`, `Close`, `Volume`：未调整的真实行情
- `Dividends`, `Stock Splits`：复权事件

计算每日复权因子（后复权 → 前复权转换）：

```python
# 从最新日期往最早日期倒推，累计乘上拆股比例和分红因子
splits = hist["Stock Splits"].replace(0, 1)
dividends = hist["Dividends"]
adj_factor = pd.Series(1.0, index=hist.index)
cum_factor = 1.0
close = hist["Close"]
for date in reversed(hist.index):
    split = splits.loc[date]
    div = dividends.loc[date]
    adj_factor.loc[date] = cum_factor
    if split != 1:
        cum_factor *= split
    if div > 0 and close.loc[date] > 0:
        cum_factor *= (close.loc[date] - div) / close.loc[date]
```

入库字段：
- `open/high/low/close/volume`：使用 `auto_adjust=False` 的真实行情
- `amount = volume * close`
- `adj_factor`：上述计算结果

#### Tiingo

Tiingo EOD API 支持 `?format=json` 返回字段：
- `open`, `high`, `low`, `close`, `volume`：未调整
- `adjOpen`, `adjHigh`, `adjLow`, `adjClose`, `adjVolume`：已调整

可以直接计算：

```python
adj_factor = adjClose / close if close else 1.0
```

同时保存拆股事件到 `etf_corporate_action`（Tiingo 不直接返回事件列表，可用 adj_factor 变化反推，或后续用 yfinance 补充）。

### 3. 指标计算改造

`app/data/indicators/calculator.py` 中读取 bar 时：

```python
df = pd.DataFrame([{
    "trade_date": b.trade_date,
    "open": b.open,
    "high": b.high,
    "low": b.low,
    "close": b.close * b.adj_factor,
    "volume": b.volume,
    "amount": b.amount,
} for b in bars])
```

所有技术指标（MA/RSI/MACD/ATR/布林带）和收益/回撤/夏普等风险指标均基于复权后的 close。

### 4. 回测引擎改造

`app/services/backtest_engine.py` 当前完全从 `AkshareProvider` 拉取 A 股数据，且未处理复权。需要：

1. 支持从 `instrument_daily_bar` 读取数据（已有 DB session 或新 query）。
2. 信号生成用 `close * adj_factor`。
3. 成交价格用真实 `close`（因为交易发生在真实市场价格）。
4. 分红再投资：可在卖出时按 `adj_factor` 变化追加现金，或简化为信号用复权价、成交用真实价。

最小改动版本：

```python
# 读取 bar
bars = db.query(ETFDailyBar).filter(...).all()
df = pd.DataFrame([{
    "trade_date": b.trade_date,
    "close": b.close,
    "adj_close": b.close * b.adj_factor,
} for b in bars])

# 信号基于 adj_close
signals = get_strategy_signals(df.assign(close=df["adj_close"]), strategy_type, params)

# 成交基于真实 close
for i, row in df.iterrows():
    price = row["close"]  # 真实成交价
    signal = signals.iloc[i]
    ...
```

### 5. 异常过滤兜底

在 `backfill_us_deep_history.py` 的 yfinance fetcher 中保留：

```python
MAX_PRICE = 100_000_000.0
MAX_AMOUNT = 100_000_000_000_000.0
if open_ > MAX_PRICE or high > MAX_PRICE or low > MAX_PRICE or close > MAX_PRICE or amount > MAX_AMOUNT:
    skip row
```

防止数据源错误导致数据库溢出。

## 部署步骤（已执行完毕，留档备查）

1. 合并代码改动到 `main`
2. 生成并执行 Alembic migration：
   ```bash
   alembic revision --autogenerate -m "add adj_factor and corporate_action table"
   alembic upgrade head
   ```
3. 重建 Docker 镜像并重启 backend：
   ```bash
   docker compose -f deploy/aliyun-ecs/docker-compose.yml up -d --build backend
   ```
4. 对已有历史数据回填 `adj_factor`：
   - 对美股：重新运行一次 `backfill_us_deep_history.py --tier all --provider yfinance`，provider 会覆盖写入 `adj_factor`
   - 对 A 股：akshare 默认提供复权数据，可单独处理
5. 重新计算所有指标：
   ```bash
   # 调用 indicator_calc pipeline
   ```
6. 重新跑已有策略回测（可选，因历史信号已变化）

## 风险与回滚

- 加 nullable 字段 `adj_factor` 到 `instrument_daily_bar` 需要短暂表锁，但 PostgreSQL 加 nullable DEFAULT 列是 O(1)。
- 新增 `etf_corporate_action` 空表无影响。
- 若 provider 改造后数据异常，可快速将 `adj_factor` 重置为 1.0，回退到当前行为。

## 不纳入本轮的范围

- A 股复权细节（akshare 已提供复权接口，可后续统一）
- 分红再投资的精确回测建模
- 跨币种汇率对复权收益的影响
