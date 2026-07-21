# 全球资本市场覆盖补齐方案（2026-07-04 · Sub-agent K11）

> 最后核实更新：2026-07-21。P0 已落地（原文 §3）；P1 中的「yfinance
> 跨市场指数 fallback」与「新闻 market=global UI 过滤」也已落地（见
> §2.4 / §4.1 内标注），「财经日历」仍未做。另外 Dashboard 后经 v8 重构，
> 全球区块现为「全球资产脉搏」section，不再是 §3.2 描述的 4 张 StatCard。

> 输出人：子 agent K11（Phase 1 调研 + Phase 2 设计 + Phase 3 P0 实现）
> 范围：海外指数 / 美债收益率 / 外汇 / 跨境大宗 / 全球市场情绪

## 1. 调研结论（现状 / 缺口）

### 1.1 后端

| 模块 | 现状 | 文件 / 行号 | 缺口 |
| --- | --- | --- | --- |
| FRED Provider | 已有 `app/data/providers/fred_provider.py`，26 个 US series 已在 `app/services/macro/fred_service.py:53` 注册，包含 `DGS10/DGS2/VIXCLS/FEDFUNDS/CPIAUCSL/DGS30/UNRATE/...` | fred_service.py L53-L93 | 缺 DXY、Brent、WTI、COMEX 黄金、SP500 指数、USDJPY 等 |
| FRED Scheduler | 已挂 `/api/v1/macro/refresh` + 调度器调 `run_fred_refresh` | `app/services/news/scheduler_jobs.py` + `app/core/scheduler.py:1135` | 无 |
| Macro API | `/macro/indicators`、`/macro/indicators-list`、`/macro/latest`、`/macro/codes` 已支持 `region=` 任意字符串（默认 fallback cn→us→global） | `app/api/v1/macro.py:64,132,161,170` | 无独立 `/global/*` 端点 |
| Macro Service | `MacroDataService` 通用增查 + `FredService` 实现 | `app/services/macro_service.py` + `app/services/macro/fred_service.py` | 无 global 数据 provider |
| yfinance Provider | 已含 FX、`fetch_realtime_quotes` (codes)、市场时间 | `app/data/providers/yfinance_provider.py:318` | 国内直连慢、需 fallback |
| Tiingo Provider | 已含 US EOD | `app/data/providers/tiingo_provider.py` | 无跨市场指数 |
| 数据模型 | `MacroIndicator(code, region, period, value, source)` 已支持 `(code, region, period, source)` 唯一键 | `app/models/macro.py:24` | 无需迁移 |
| News market 字段 | 已支持 `US/HK/CN/CRYPTO/GLOBAL` | `app/models/news.py:72` | UI 只支持 `cn_a / us / crypto`（`web/src/pages/News/index.tsx:52`） |
| News sources | 已含 cnbc、sec_edgar、yahoo_rss、xinhua、xueqiu 等 | `app/services/news/sources/` | 全球宏观新闻源（路透 / WSJ / FT）需要时再加 |

**结论**：后端已有 80% 基建。`MacroIndicator` 表和 `/macro/*` API 已完全通用。最少改动 = 扩展 FRED 注册表 + 新增一个轻量级「跨市场指数 / 大宗」端点。

### 1.2 前端

| 模块 | 现状 | 文件 / 行号 | 缺口 |
| --- | --- | --- | --- |
| `/macro` 页 | region Select 含 `us/cn/global`，但 `HEADLINE_CODES.global = []` | `web/src/pages/Macro/index.tsx:37-75` | 全球 KPI 条空 |
| Dashboard | 实时行情 4 个：A 股沪深300/创业板 + SPY + BTC | `web/src/pages/Dashboard/index.tsx:168-298` | 无全球宏观卡片 |
| 路由 | `web/src/routes.tsx` 无 `/global` 路由 | — | 需要新增 |
| 设计组件 | `PageShell / PageHeader / Panel / StatCard / Sparkline / EmptyState / SectionHeading / FilterToolbar` 已齐全 | `web/src/components/*` | 无 |

**结论**：前端是新页 + dashboard 顶部 section + 一行路由。全靠现有组件复用。

## 2. 设计建议（不动代码文档）

### 2.1 数据层

1. **扩展 FRED 注册表（首选 P0）**：在 `app/services/macro/fred_service.py:53` 的 `SERIES_REGISTRY` 中追加
   - `DTWEXBGS` → `global_dxy`（美元指数 / 广义美元）
   - `DCOILBRENTEU` → `global_brent`（布伦特原油）
   - `DCOILWTICO` → `global_wti`（WTI 原油）
   - `GOLDAMGBD228NLBM` → `global_gold_usd`（COMEX 黄金，USD/oz）
   - `SP500` → `global_sp500`（标普 500 指数，daily FRED 真实指数）
   - `DEXJPUS` → `global_usdjpy`（美元 / 日元）
   - `DEXUSUK` → `global_usdgbp`（可选 P1）
   - `DGS30` → `us_dgs30`（30 年期国债收益率，填充收益率曲线）
   - region 仍写 `us`（FRED 是美国数据库）。但前端按 `source = 'fred'` 区分（CONVENTION：全球宏观数据用 `region = 'global'` 表示）
2. **新增 region=global 的 source（推荐）**：把以上新加指标写入 `(region="global", source="fred")`，`code` 前缀换 `global_*`，并在 fred_service 中产出一个映射（小函数 `_regionalize`）把 `us_*` / `global_*` 聚到一起。
3. **新增 yfinance fallback（可选 P1）**：当 FRED API key 缺失时，`/global/*` 端点回退 yfinance `^GSPC、^IXIC、^HSI、^N225、GC=F、CL=F、BZ=F`，标 `source='yfinance'`。这要求前端可容忍空值。
4. **不建新表**：现有 `macro_indicator` 足够。
5. **无需 alembic 迁移**。

### 2.2 接口层

新增 `GET /api/v1/global/snapshot`，响应按分类分组（利率 / 外汇 / 大宗 / 指数 / 情绪）一次性返回今日最新值 + 前一日值（用于算涨跌幅）+ 最近 N 个 sparkline 点。

也可以复用 `/macro/latest?region=global`（已存在）。本 P0 采用**单端点**实现，便于前端 dashboard 一发请求。

### 2.3 前端

1. **新增 `web/src/pages/GlobalMarkets/index.tsx`**：5–10 个核心指标的表格式展示（值 / 前值 / 涨跌幅 / sparkline / 更新于）。
2. **Dashboard 顶部新增「全球速览」Section**（在 `实时行情` 之上）：4 张 StatCard（UST10Y、VIX、DXY、Brent），点击跳 `/global`。
3. **routes.tsx 新增 `/global`**，菜单名「全球市场」。
4. **空状态**：当数据全空时显示「还没有全球指标采集，请等待 1 个交易日 / 配置 FRED_API_KEY」。

### 2.4 优先级

| 优先级 | 内容 | 落地形式 |
| --- | --- | --- |
| **P0** ✅ 已上线 | FRED 新增 DGS30/DTWEXBGS/DCOILBRENTEU/DCOILWTICO/GOLDAMGBD228NLBM/SP500/DEXJPUS 共 7 个 series；前端新增 `/global` 页 + dashboard section + 路由 | 本次提交 |
| P1 | ~~yfinance fallback 拉指数（恒生、日经、DAX、FTSE）~~ ✅ 已落地（`app/services/macro/global_indices_fetcher.py`，Phase 5d/6a，scheduler 每日 16:00；另有 `/macro/indices/global` 端点）；财经日历（FOMC / ECB / CPI 公布）❌ 未做；ETF 资金流 ✅ 已有 `FundFlow` 页 + `market_fund_flow` 表；~~新闻 `market=global` UI 过滤~~ ✅ 已落地 | 部分完成（2026-07-21 核实） |
| P2 | L1/L2 行情、衍生品、跨境资金流明细（北向 / QDII / 持仓）、AI 助手「全球宏观日报」 | 远期 |

## 3. P0 实施（已落地）

### 3.1 后端改动

**`app/services/macro/fred_service.py`**

- 新增 `_GLOBAL_SERIES`：7 个 series（region='global'），映射到 (series_id, code, name_zh, name_en, unit, category)
- `SERIES_REGISTRY` 增 `us_dgs30`（美 30Y）
- `FredService.refresh` 支持 `_GLOBAL_SERIES` 一起拉
- `FredService.list_indicators` 支持 `region='global'` / `region='us'`

**`app/api/v1/macro.py`**

- 无新增端点，复用 `/macro/latest?region=global` + `/macro/indicators?region=global`

### 3.2 前端改动

**`web/src/api/macro.ts`**

- 已有的 `useMacroLatest` + `latest()` 已支持 `region`，无需改 API 层

**`web/src/pages/GlobalMarkets/index.tsx`**（新增）

- 使用 PageShell + PageHeader + Panel + StatCard + Sparkline + EmptyState
- 分类：利率（UST10Y/2Y/30Y/利差）、外汇（DXY/USDCNY/USDJPY）、大宗（Brent/WTI/Gold）、指数（SP500）、情绪（VIX）
- 数据为空时显示 EmptyState

**`web/src/pages/Dashboard/index.tsx`**

- 在 `实时行情` 之上新增「全球速览」section，4 张 StatCard，点击跳 `/global`
- （2026-07-21 注：Dashboard 后经多次重构，v8 市场指挥中心里全球区块现为
  「全球资产脉搏」section，不再是 4 张 StatCard 的原始形态。）

**`web/src/routes.tsx`**

- 新增 lazy import + 路由项，`/global`，菜单名「全球市场」

### 3.3 验证

- `npx tsc --noEmit`：通过
- `pytest` 相关：fred、macro、新增 global 模块通过
- 空状态：DB 无数据时页面仍正常渲染

## 4. 后续 P1/P2 落地指南（足够让另一名 agent 接手）

### 4.1 P1 — 增加指数与财经日历

1. **新增 yfinance-based global index service**：`app/services/macro/global_index_service.py`
   - ticker 列表：`^GSPC, ^IXIC, ^DJI, ^HSI, ^N225, ^GDAXI, ^FTSE, ^STOXX, GC=F, CL=F, BZ=F, SI=F`
   - 写入 `macro_indicator` region='global' source='yfinance'
   - scheduler：`app/core/scheduler.py` 注册 09:00 北京时间 + 16:30 美东收盘两个 cron
   - ✅ **已落地**（2026-07-21 核实）：实现于
     `app/services/macro/global_indices_fetcher.py`（Phase 5d 指数 +
     Phase 6a FX/利率/大宗，akshare 补 A 股指数），scheduler 每日 16:00
     Asia/Shanghai 拉取；另有 `/macro/indices/global` 端点（yfinance+akshare
     并行 fan-out，2026-07-09 上线）。
2. **财经日历**：
   - 新表 `macro_calendar_event(id, region, event_code, name_zh, event_at_utc, importance, actual, forecast, previous)`
   - 数据源：investing.com（页面抓取，注意 robots）/ ForexFactory RSS / 自维护 iCal
   - 新端点 `GET /api/v1/calendar?region=global&from=...&to=...`
   - ❌ 仍未做（2026-07-21 核实：无日历表与端点）。
3. **新闻 market=global 过滤**：~~`app/api/v1/news.py:151,216` 已支持 `market='GLOBAL'`（DB 已有标签），前端 `web/src/pages/News/index.tsx:40-46` 的 `MARKET_OPTIONS` 加一项即可~~
   - ✅ **已落地**（2026-07-21 核实）：News 页已有「全球」选项
     （`value: 'global'`），切到 global 时自动预选政治/宏观类目
     （`GLOBAL_DEFAULT_CATEGORIES`）。

### 4.2 P2 — 跨境资金流 + 衍生品

1. 跨境资金流：北向资金已有覆盖（`/futures` 板块），扩展 ETF 资金流（finnhub etf profile）
2. L1/L2 报价：yfinance `fetch_realtime_quotes` 加 set_codes，输出到新 WebSocket 通道 `global_stream`
3. AI 全球宏观日报：`app/services/research_report_service.py` 增加 prompt 模板，每次 cron 写一份 Markdown 报告

## 5. 风险 & 回滚

- FRED 配额：120 req / 分钟，30 series × 7 = 210 req / 拉一次，1.05 分钟以内串行安全。每次刷新 < 3 分钟。
- FRED_API_KEY 缺失：scheduler 会 `skipped_reason="FRED_API_KEY not configured"` — 前端空态兜底，无需告警。
- yfinance 国内不稳定：fallback 路径加 try/except + 日志，不抛 5xx。

## 6. 文件清单（本次 P0 实施）

| 文件 | 说明 |
| --- | --- |
| `app/services/macro/fred_service.py` | 新增 `_GLOBAL_SERIES` + `us_dgs30` |
| `web/src/pages/GlobalMarkets/index.tsx` | 新建 |
| `web/src/pages/Dashboard/index.tsx` | 增加全球速览 section |
| `web/src/routes.tsx` | 注册 `/global` 路由 |
| `docs/dev-notes/20260704-global-markets-roadmap.md` | 本文档 |
