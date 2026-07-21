# 资金流监控 (Plan C) 实施与运维 Runbook

> 最后核实更新：2026-07-21

## 1. 背景

调研确认：在**零付费**前提下，A 股主力资金流、板块资金流、ETF 申赎方向、综合资金情绪都可以通过 akshare + 东方财富 push2 直连 + 公开披露拼齐。Tushare 资金流接口在免费额度（120 积分）下全部不可用；akshare 与 Tushare 2000 积分档同源同质（都来自东方财富 push2his 接口）。

「实时北向分时」因监管 2024-08 取消而**任何渠道都拿不到**，只能拿到收盘后/季度大额持股披露。

## 2. 数据源

| 数据 | 来源 | 接口 | 频率 | Provider |
|---|---|---|---|---|
| 个股主力资金流 | akshare（东方财富 push2his） | `stock_individual_fund_flow_rank(indicator='今日')` | T+0 盘后 | `fund_flow_provider.py` |
| 板块资金流 | akshare | `stock_sector_fund_flow_rank(sector_type='行业资金流'\|'概念资金流'\|'地域资金流')` | T+0 盘后 | 同上 |
| 大盘整体 | akshare | `stock_market_fund_flow()` | 日 | 同上 |
| 北向持股排行 | akshare | `stock_hsgt_hold_stock_em` | T+0 盘后 | 同上 |
| ETF 折溢价 + 份额 | akshare | `fund_etf_spot_em` + `fund_etf_fund_daily_em` | 日 | `etf_flow_provider.py` |
| 融资余额 | akshare（沪深所） | `stock_margin_detail_sse/_szse` | 日 | `flow_signals_provider.py` |
| 龙虎榜机构席位 | akshare | `stock_lhb_detail_em` | 日 | 同上 |
| 股东户数 | akshare | `stock_zh_a_gdhs` | 季度 | 同上 |
| AH 溢价 | akshare | `stock_zh_ah_spot` | 实时 | 同上 |
| 大宗交易 | akshare | `stock_dzjy_mrtj` | 日 | 同上 |
| 个股资金流历史（备用） | 东财 push2his | `push2his.eastmoney.com/api/qt/stock/fflow/daykline/get` | 日 | `eastmoney_fund_flow_provider.py` |
| 个股资金流实时（备用） | 东财 push2 | `push2.eastmoney.com/api/qt/stock/get` | 实时 | 同上 |

## 3. 数据模型

迁移：`alembic/versions/2026_07_14_create_fund_flow_tables.py`（4 张基础表）+ `alembic/versions/2026_07_18_0001_add_market_fund_flow_table.py`（大盘资金流表）

| 表 | 关键字段 | 唯一键 |
|---|---|---|
| `individual_fund_flow` | ts_code, trade_date, main/super_large/large/medium/small × net/pct | (ts_code, trade_date) |
| `sector_fund_flow` | sector_name, sector_type, trade_date, main_net, leading_stock | (sector_name, sector_type, trade_date) |
| `etf_fund_flow` | ts_code, trade_date, premium_rate, shares_change, inferred_net_inflow | (ts_code, trade_date) |
| `flow_signal` | ts_code, trade_date, composite_score, score_breakdown JSONB | (ts_code, trade_date) |
| | `ix_flow_signal_composite` 索引 `composite_score DESC` | 用于 Top N 查询 |
| `market_fund_flow` | trade_date, market（ALL/SH/SZ）, main_net 等 | (trade_date, market) |

> `market_fund_flow` 为 2026-07-18 新增：`ALL` 行来自 `ak.stock_market_fund_flow`，`SH`/`SZ` 行由 `individual_fund_flow` 按代码后缀派生（见 `app/data/pipelines/market_fund_flow.py`）。

## 4. `composite_score` 综合评分公式

每个分量先按阈值归一化到 `[-1, +1]`（线性 clip），再乘权重 × 100：

| 分量 | 权重 | 阈值（满分量=+1） | 含义 |
|---|---|---|---|
| `main` | **0.40** | 1 亿元 | 主力净流入（akshare / 东财） |
| `margin` | **0.20** | 5 千万 | 融资余额日变化 |
| `lhb` | **0.20** | 5 千万 | 龙虎榜机构席位净买 |
| `block` | **0.10** | 5 千万 | 大宗交易净买 |
| `shareholder` | **0.05** | 1 万户 | 股东户数变化（反向：负=集中→正向加分） |
| `ah` | **0.05** | 50 个百分点 | AH 溢价 |
| **合计** | **1.00** | — | 输出 `[-100, +100]` |

`score_breakdown` JSONB 保留每个分量的精确贡献（4 位小数），用于前端详情展开。

**设计原则**：主力资金是直接信号权重最高（40%）；融资 + 龙虎榜是强机构信号（各 20%）；其余是辅助弱信号（≤10%）。

## 5. Pipeline 调度

- **cron**：`hour=17, minute=30, timezone="Asia/Shanghai"`（**每日**执行，无 `day_of_week` 限制；`app/core/scheduler.py` `fund_flow_daily`）
- **后续任务**：`market_fund_flow_daily` 每日 18:35 执行，在 `fund_flow_daily` 落地 `individual_fund_flow` 后派生 SH/SZ 大盘净流入写入 `market_fund_flow`
- **为什么 17:30**：A 股 15:00 收盘，15:30 ETF ETL（akshare）+ 16:00 STOCK ETL（Tushare）+ 16:30 STOCK 估值 ETL 完成，17:00 A 股指标兜底补算后，17:30 再跑资金流；所有上游数据已落库，且早于 19:30 的 microstructure 日刷
- **总耗时**：~1-2 分钟（含失败重试 + DB 写入）
- **失败容错**：每个子任务独立 `try/except`，单源失败不阻塞其他子任务

```python
# app/data/pipelines/fund_flow.py: run_daily(trade_date=None)
# 手动触发
poetry run python -c "from datetime import date; from app.data.pipelines.fund_flow import run_daily; print(run_daily(trade_date=date.today()))"
```

## 6. API 路由

8 个 GET 端点 + 1 个 POST 端点（`/api/v1/fund-flow/*`），全部要求登录：

| 路由 | 参数 | 用途 |
|---|---|---|
| `/individual` | date / sort / limit | 全市场个股资金流排行 |
| `/individual/{ts_code}` | days | 单只历史 |
| `/sector` | date / sector_type / sort | 板块资金流 |
| `/sector/{sector_name}` | days | 单板块历史 |
| `/market` | date | 大盘整体（读 `market_fund_flow` 表：ALL 来自 akshare，SH/SZ 由个股资金流派生） |
| `/etf` | date / sort / limit | ETF 折溢价 + 推算净流入 |
| `/signals` | date / sort / limit | 综合信号 Top N（按 composite_score） |
| `/signals/{ts_code}` | days | 单只信号历史 |
| `/refresh`（POST, admin） | trade_date | 手动触发 ETL |

## 7. 前端页面

`/fund-flow` 路由（自动出现在侧边栏「市场行情」分组）。

布局：
1. **大盘资金流概览**：4 个 StatCard（沪市/深市/合计/5日趋势 sparkline）
2. **综合资金信号 Top 20**：按 `composite_score` 降序，染色（>20 红流入 / <-20 绿流出 / 中间灰）
3. **Tabs**：[个股资金流] [板块资金流] [ETF 资金流]
4. **数据来源说明**（折叠）：akshare / 东方财富 / 交易所公开披露

> Dashboard 首页的 `PulseFundFlowStrip`（3 个快速访问 tile）已在后续前端重构中移除（2026-07-21 核实）；现 Dashboard 改为「资金流」卡片（净流入合计 + 涨跌幅，点击跳转 `/fund-flow`）与信号流中的资金流 Top3 条目。

## 8. 运维常见操作

```bash
# (1) 手动触发今日资金流 ETL（admin only 或 celery 调用）
docker exec alloyresearch-backend python3 -c "
from app.data.pipelines.fund_flow import run_daily
print(run_daily())
"

# (2) 查看某只股票的完整资金信号
curl 'https://host/api/v1/fund-flow/signals/600519.SH?days=30' \
  -H 'Authorization: Bearer <token>'

# (3) 检查某板块资金流
curl 'https://host/api/v1/fund-flow/sector?sector_type=行业资金流&date=2026-07-14' \
  -H 'Authorization: Bearer <token>'

# (4) 数据来源异常排查
docker exec alloyresearch-backend python3 -c "
import akshare as ak
df = ak.stock_individual_fund_flow_rank(indicator='今日')
print(len(df))
"
# 频繁 ConnectionError / JSONDecodeError 是东财 push2his 上游抖动，等 30-60 分钟后重试

# (5) 监控 cron 注册状态
docker logs alloyresearch-backend | grep 'fund_flow_daily'
```

## 9. 已知陷阱与限制

1. **akshare `push2his.eastmoney.com` 频繁 502/超时**：所有 Provider 已做 2 次重试 + 1s 退避 + try/except 兜底；生产环境沙箱外表现更稳定
2. **ETF 申赎 T+1 确认**：`inferred_net_inflow` 是基于份额日变化 × 价格推算的代理量，不是直接申赎数据
3. **股东户数季度更新**：`stock_zh_a_gdhs` 实际更新频率约季度，pipeline 每天跑也无新数据
4. **AH 溢价 220 行限制**：港股通标的就这么多，超出范围的标的查不到
5. **scheduled-task-recovery-guide**：若 cron 因 backend 重启错过，参考既有「定时任务恢复操作指南」（`docs/dev-notes/20260627-scheduled-task-recovery-guide.md`）手动 `run_daily()` 补跑
6. **ETF 子任务 upsert 键不一致导致 SQL 编译错误**：ETF 合并 `fund_etf_spot_em`（含 `shares_outstanding`、`turnover`）与 `fund_etf_fund_daily_em`（不含这两个字段）后，传入 `insert(EtfFundFlow).values([...])` 的字典键不统一；SQLAlchemy 在 `ON CONFLICT ... SET excluded.shares_outstanding` 时抛出 `CompileError: INSERT value for column shares_outstanding is explicitly rendered as a boundparameter...`。修复：`app/data/pipelines/fund_flow.py` 的 `_upsert_etf()` 在构建 `insert` 前先统一所有字典键，缺失字段补 `None`。后续新增数据源合并时，务必保证 upsert 字典键一致或为缺失键提供默认值。