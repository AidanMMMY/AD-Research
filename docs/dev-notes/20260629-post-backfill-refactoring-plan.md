# 回填完成后重构 TODO

> 记录 A 股全量数据（日线 + 财报）回填完成后需要做的架构与数据质量改进，以及与 US-Stock 02 会话中已完成的美股复权改造方案的衔接。
>
> 最后核实更新：2026-07-21
>
> **整体进度（2026-07-21 核实）**：本 TODO 的大部分事项已完成——美股复权分支已合入 main 并执行 migration；A 股 `adj_factor` 已补全；`instrument_daily_bar` 表重命名已生效；回测引擎已统一走本地价格库；ETF 元数据 enrichment pipeline 已上线（`etf_metadata_enrichment`，scheduler 每周日 04:00）。各项明细状态见下文每节的「进度」标注。唯一未完整落地的是第 5 节指标层的 `NOT_YET_LISTED` / `PARTIAL` 打标（回测侧已有 list_date/delist_date 钳制）。
>
> ~~当前回填仍在进行中：bars v8 日线约 2,566/5,530，财报待日线完成后启动；美股 deep backfill 也在推进中（US-Stock 02 会话监控）。~~（回填已完成，此行为当时进度快照）

---

## 重要前提：美股复权方案已由 US-Stock 02 实现

US-Stock 02 会话已创建分支 `feature/adj-factor-corporate-actions`，并完成以下工作：

- `app/models/etf.py`：新增 `ETFDailyBar.adj_factor` 字段 + `ETFCorporateAction` 表
- Alembic migration：`...e5f6_add_adj_factor_and_etf_corporate_action.py`（未执行）
- `app/data/providers/yfinance_provider.py`：单只票拉取时计算 `adj_factor`
- `app/data/providers/tiingo_provider.py`：用 `adjClose / close` 计算 `adj_factor`
- `app/data/indicators/calculator.py`：指标计算使用 `close * adj_factor`
- `app/services/backtest_engine.py`：信号用复权价、成交用真实价
- `app/scripts/backfill_us_deep_history.py`：修复 Tiingo fallback bug + 增加异常价格过滤
- 设计文档：`docs/dev-notes/20260629-adjustment-factor-design.md`

**结论**：美股侧实现已经完整，本 TODO **不复述、不重复实施**美股部分，只补充 A 股侧缺口和统一部署顺序。

---

## 1. A 股复权因子补全（当前缺口）

> **进度（2026-07-21）**：✅ 已完成。`TushareProvider.fetch_adj_factor()` 已实现并在 `fetch_daily_bars()` / `fetch_daily_all_market()` 中 merge；`backfill_a_stock_2026.py` 的 `_BAR_FIELDS` 已含 `adj_factor`；独立回填脚本已存在（`scripts/backfill_a_share_adj_factor.py`、`app/scripts/backfill_a_share_adj_factor.py`）；`backtest_engine.py` 已统一使用 `adj_close`。此外还演进出了 `adj_factor_history` 表完整保存 Tushare 原始累计因子。

### 1.1 问题

US-Stock 02 的方案明确把 A 股复权细节列为"不纳入本轮的范围"。但当前 A 股 backfill：
- 用 Tushare `daily()` 拉取，返回的是**未复权价格**
- `TushareProvider` 没有调用 `adj_factor()` 接口
- `backfill_a_stock_2026.py` 的 `_BAR_FIELDS` 不包含 `adj_factor`
- `backtest_engine.py` 的 A 股 legacy fallback 写了 `# no adjustment info`

如果不补 A 股，`adj_factor` 列对 A 股将始终为 1.0，指标和回测会受拆股/分红影响。

### 1.2 方案

**复用 `feature/adj-factor-corporate-actions` 分支的模型和 migration**，只新增 A 股数据获取逻辑：

1. **`TushareProvider` 新增 `fetch_adj_factor(ts_code, start, end)`**
   - 调用 Tushare `adj_factor()` 接口
   - 返回 `ts_code, trade_date, adj_factor`

2. **`TushareProvider.fetch_daily_bars()` / `fetch_daily_all_market()` merge `adj_factor`**
   - 在拿到 `daily()` 数据后，按 (ts_code, trade_date) 左连接 adj_factor
   - 缺失的 trade_date 默认填 1.0

3. **`backfill_a_stock_2026.py` 更新 `_BAR_FIELDS`**
   - 增加 `"adj_factor"`

4. **已有 A 股日线数据补 adj_factor**
   - 不需要重拉日线（浪费配额）
   - 单独写一个 `app/scripts/backfill_a_share_adj_factor.py`
   - 按 (stock_code, trade_date) 从 Tushare 取 adj_factor 并 UPDATE 现有行

5. **`backtest_engine.py` A 股 fallback 改 adj_close 计算**
   - `adj_close = close * adj_factor`

### 1.3 美股与 A 股的统一点

| 层面 | 美股（已有） | A 股（待补） |
|---|---|---|
| 模型 | `ETFDailyBar.adj_factor` + `ETFCorporateAction` | 复用同一套 |
| migration | 已生成 | 复用同一套 |
| 数据源 | yfinance actions / Tiingo adjClose | Tushare `adj_factor()` |
| backfill 脚本 | `backfill_us_deep_history.py` 已改 | `backfill_a_stock_2026.py` + 独立 adj_factor 回填脚本 |
| 消费侧 | `calculator.py` / `backtest_engine.py` 已改 | 只需改 A 股 fallback |

---

## 2. `instrument_daily_bar` 表重命名为 `instrument_daily_bar`

> **进度（2026-07-21）**：✅ 表重命名已完成（`app/models/etf.py` 中 `InstrumentDailyBar.__tablename__ = "instrument_daily_bar"`）。⚠️ 但主键列名仍为 `etf_code`（外键指向 `etf_info.code`），未改为 `instrument_code`，下文提到的外键改名未执行。

**原因**：该表现在存储 ETF、A 股个股、美股、加密等多种品种的日线，表名已产生误导。

**影响面**：约 29 个文件引用此表名，需统一修改：
- ORM 模型定义（`app/models/etf.py`）
- Alembic 迁移脚本
- 所有 pipeline、service、API 中的表名/字段名引用
- 前端类型定义（如有）

**注意**：同步检查外键 `etf_code` 是否也需要改为 `instrument_code`。

**建议时机**：在 adj_factor 改造完成后、重新跑指标前做，避免同时大改模型两次。

---

## 3. 统一价格查询层

> **进度（2026-07-21）**：✅ 核心目标已达成，但落地形式与原文设想不同：统一查询层落在 `app/data/repositories/price_repository.py`（`get_bars` / `get_bars_for_codes`），`backtest_engine._load_bars()` 已强制要求 DB session 并从本地库读 `adjusted=True` 的复权数据，不再直接调用 Tushare/akshare API（原 `:134` 直连已移除）。`app/services/market_data_service.py` 提供的是 `get_history()` / `get_snapshot()`，并无 `get_bars()` 方法。

**目标**：让策略/回测/资产配置统一走 `MarketDataService.get_bars()`，而不是直接调用 Tushare/akshare API。

**已知问题点**：
- `backtest_engine.py:134` 直接调 Tushare API 取历史价格
- 这会导致策略回测时绕过本地数据库，既慢又容易触发数据源配额

**做法**：
- 强化 `MarketDataService.get_bars()` 覆盖所有品种（A 股个股、ETF、美股、加密）
- 回测引擎只调用 service 层
- 缺失数据由 service 触发后台补数，而不是回测时实时拉取

---

## 4. ETF 产品元数据 enrichment pipeline（新增）

> **进度（2026-07-21）**：✅ 已完成。`app/data/pipelines/etf_metadata_enrichment.py`（job：`etf_metadata_enrichment`）已上线并在 scheduler 中注册（每周日 04:00，`app/core/scheduler.py:1510` 附近）；`ETFInfo` 模型已包含 `list_date` 字段（另有 `delist_date`）。

**原因**：当前 `ETFInfo` 中大量 ETF 的以下字段为空：
- `category` / `sub_category`（分类）
- `manager`（管理公司）
- `underlying_index`（跟踪指数）
- `fund_size`（规模）
- `inception_date`（成立日期）
- `list_date`（上市日期，当前模型甚至缺失该字段）

这些空字段不是数据缺失，而是 discovery 阶段根本没抓取。

**数据质量要求**：
**每只 ETF 必须同时记录 `inception_date` 和 `list_date`**。
- `inception_date`（成立日）用于判断产品生命周期；
- `list_date`（上市日）用于判断何时开始有可交易价格；
- 缺少这两个日期，将无法区分"指标缺失是因为 ETF 尚未上市"还是"pipeline 漏算/数据源缺失"。

**推荐数据源**：
1. **主源**：Tushare `fund_basic(market='E', status='L')`，一次调用返回管理公司、基金类型、成立日、上市日、规模、业绩比较基准等；
2. **补源**：akshare `fund_info_ths(symbol)` 单只补抓缺失字段；akshare `fund_etf_scale_sse/szse()` 补充最新份额和管理公司。

**字段映射建议**：
- Tushare `management` → `manager`
- Tushare `benchmark` → `underlying_index`
- Tushare `fund_type` / `invest_type` → `category` / `sub_category`
- Tushare `found_date` → `inception_date`
- Tushare `list_date` → `list_date`（新增字段）
- Tushare `issue_amount` 或 akshare 最新份额 → `fund_size`

**调度**：每周随 ETF scanner 一起运行，增量更新新上市/变更的 ETF。

---

## 5. 指标/收益计算增加成立日/上市日兜底

> **进度（2026-07-21）**：⚠️ 部分实现。回测侧已有兜底——`backtest_engine._load_bars()` 会用 `price_repository.get_list_date()` / `get_delist_date()` 钳制回测区间；但指标计算层的 `NOT_YET_LISTED` / `PARTIAL` 打标机制未实现（代码库中无此标记）。

在回填完成且元数据补齐后，指标计算（1 年收益、3 月收益等）应增加逻辑：
- 若请求区间早于 ETF `list_date`，直接返回 `None` 并标记为 `NOT_YET_LISTED`；
- 若请求区间部分覆盖上市初期，按实际可用数据计算并打标 `PARTIAL`；
- 只有数据完整时才返回正常指标值。

这样前端/回测就能明确区分：
- `NOT_YET_LISTED`：成立/上市晚，不是 bug
- `DATA_MISSING`：上市后有数据空洞，需要补数

---

## 6. 统一执行顺序（待所有 backfill 完成后）

> **进度（2026-07-21）**：步骤 1–8 已基本执行完毕（分支合并、migration、A 股 adj_factor、回测修复、list_date + enrichment pipeline、表重命名、统一价格查询层均已落地）。步骤 10 的指标层 `NOT_YET_LISTED` 打标未实现（见第 5 节）。

1. **A 股 bars v8 + 财报回填完成**；美股 deep backfill 完成（US-Stock 02 会话 watcher 会通知）。
2. **合并 `feature/adj-factor-corporate-actions` 到 main**
   - 包含：模型、`adj_factor` migration、美股 provider/backfill 改造、指标/回测消费侧改造
3. **跑 Alembic migration**：`alembic upgrade head`
   - 新增 `instrument_daily_bar.adj_factor` 列 + `etf_corporate_action` 表
4. **补 A 股 `adj_factor`**
   - 改 `TushareProvider` 拉取 adj_factor
   - 改 `backfill_a_stock_2026.py` 的 `_BAR_FIELDS`
   - 运行独立脚本回填已有 A 股日线数据的 `adj_factor`
5. **修复 `backtest_engine.py` A 股 fallback**：`adj_close = close * adj_factor`
6. **新增 `ETFInfo.list_date` 字段 + ETF metadata enrichment pipeline**
7. **重命名 `instrument_daily_bar` → `instrument_daily_bar`**
8. **统一价格查询层**，改造 `backtest_engine.py` 不再直接调外部 API
9. **重新计算所有技术指标**（因复权价变化）
10. **在指标计算中接入 `inception_date` / `list_date` 兜底逻辑**
11. **可选**：重新跑已有策略回测，对比信号变化

---

## 7. 当前分支状态提醒

> **进度（2026-07-21）**：以下为当时快照，已过时——`feature/adj-factor-corporate-actions` 已合入 main，相关 migration（`a1b2c3d4e5f6`、`i9j0k1l2m3n4`）已在 `alembic/versions/` 中。

- 当前本地工作区在 `feature/adj-factor-corporate-actions` 分支
- 该分支包含美股复权改造的完整代码，但**未合并到 main**
- 远程服务器上运行的 backfill 进程基于 main 分支代码，**不受影响**
- 等 backfill 全部完成后，再合并分支、跑 migration、重启容器

---

## 8. 与 US-Stock 02 会话的衔接

- US-Stock 02 已承诺在美股 deep backfill 完成后提醒用户继续部署方案 B。
- 本会话负责在 A 股 bars v8 + 财报回填完成后提醒用户。
- **两个 backfill 都完成后**，按上述"统一执行顺序"一次性部署，避免多次 migration/重启。
