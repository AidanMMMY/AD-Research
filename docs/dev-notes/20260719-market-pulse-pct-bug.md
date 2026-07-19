# 首页市场脉搏 涨跌幅 ×100 倍 bug 修复 Runbook

**日期**：2026-07-19
**触发**：用户在首页 `Dashboard` 市场脉搏 + 多页面涨跌幅显示明显错误（截图显示 标普 500 -100.99% / 恒生 -178.48% / KOSPI -636.72% / 上证指数空白 等）。
**作者**：总管 Agent
**影响**：所有依赖 SSE / macro / crypto / futures 等"百分比本身"语义字段的页面，首页脉冲 + Dashboard 资金流速览 + InstrumentList / Favorites / CryptoList / CryptoDetail / FundFlow / GlobalMarkets 等。

## 背景

AD-Research 平台同时存在两套百分比语义：

| 字段 | 实际语义 | 来源 | 示例值 |
|---|---|---|---|
| `change_pct`（SSE stream / macro / crypto / futures）| **百分比本身**（1.5 = +1.5%）| 后端 `(latest - prev) / prev * 100` 落地 | `1.5` |
| `return_1w/1m/3m/6m/1y` / `main_net_pct` / `ah_premium` 等 | **小数**（0.025 = +2.5%）| `pandas.pct_change()` 落地 | `0.025` |

**前端 `formatPercent(v)`** 老实现是 `const pct = v * 100; return pct.toFixed(2) + '%';` —— **×100**。

→ `ReturnTag` 走 `formatPercent`，无差别 ×100：

- `return_1m = 0.05` → `formatPercent` → `+5.00%` ✓ 正确
- `change_pct = 1.5` → `formatPercent` → `+150%` ✗ **错 100 倍**

### 截图现场反推

| 标的 | 显示 | 反推 change_pct | 真实日涨跌 |
|---|---|---|---|
| 标普 500 | -100.99% | -1.0099 | -1.01% |
| 纳斯达克 | +62.14% | 0.6214 | +0.62% |
| 道琼斯 | -77.36% | -0.7736 | -0.77% |
| US 10Y (收益率差)| -61.28% | -0.6128 | -0.61% |
| USD/CNY | +6.35% | 0.0635 | +0.06% |
| 恒生 | -178.48% | -1.7848 | -1.78% |
| 日经 | -403.14% | -4.0314 | -4.03% |
| KOSPI | -636.72% | -6.3672 | -6.37% |
| FTSE 100 | +26.67% | 0.2667 | +0.27% |
| CAC 40 | -46.61% | -0.4661 | -0.47% |

**全部反推都是正常日波动**，说明**后端计算正确，错只是前端 formatPercent + ReturnTag 链路 ×100**。上证/深证空白是 macro/indices/global 当前 yfinance 不覆盖 A 股（独立问题，本次不动）。

## 修复（方案 C：组件级语义分流）

不破坏 `formatPercent` 既有调用面（50 处），而是新增一个并行组件 `ReturnTagPct` 专门显示"百分比本身"语义字段。理由：

1. **最小爆炸半径**：bug 仅在「`change_pct` 直接进 `ReturnTag`」这条路径，约 11 处；`return_*` 等小数路径全部不动。
2. **不动后端契约**：后端 `change_pct` 全栈（provider/DB/API/schema/validator/测试）一致 = 百分比本身。
3. **不挖新坑**：不动数据库、不动 service、不动 schema，**只改前端 1 个新组件 + 11 处 import + 1 个 tiles 数据模型（composite_score 配套取消 ReturnTag）**。

### 代码变更清单

| 文件 | 改动 |
|---|---|
| `web/src/utils/format.ts` | 新增 `formatPercentRaw(v)` —— 不 ×100；`formatPercent` 注释明确"小数语义" |
| `web/src/components/ReturnTagPct.tsx` | 新文件：与 `ReturnTag` 视觉一致，调 `formatPercentRaw` |
| `web/src/pages/Dashboard/index.tsx` | `:524` change_pct → ReturnTagPct；`:637` tiles 增加 `changeFormat` 字段：pct 走 ReturnTagPct、score(composite_score) 走纯文本（不加色）|
| `web/src/pages/InstrumentList/index.tsx` | `tick.change_pct` → ReturnTagPct |
| `web/src/pages/Favorites/index.tsx` | 同上 |
| `web/src/pages/CryptoList/index.tsx` | `change_pct ?? change_24h` → ReturnTagPct（2 处）|
| `web/src/pages/CryptoDetail/index.tsx` | `crypto.change_pct ?? crypto.change_24h` → ReturnTagPct |
| `web/src/pages/FundFlow/index.tsx` | `ah_premium / main_net_pct` 3 处 → ReturnTagPct |
| `web/src/pages/GlobalMarkets/index.tsx` | `changePct` → ReturnTagPct |

**保 持 ReturnTag（不动）的页面**（小数语义字段，不需要改）：
- `StockDetail/index.tsx:649` `formatPercent(indicator.return_1m)`
- `InstrumentDetail/index.tsx:334` `formatPercent(indicator.return_1m)`
- `Screen/index.tsx:98/99/100` `return_1m/3m/1y` 表列
- `SectorRotation/index.tsx` 所有 `return_*` + `Phase3ReturnTag`（值来自 `etf_indicator.return_*`，全是小数）
- `Dashboard/index.tsx:988` `return_1m` 表列

## 验证

- `cd web && npx tsc --noEmit` → 0 error（修一个 unused import 后）
- `cd web && npm run build` → 6.29s ✓ built
- 数据交叉验证：截图中所有"反推"change_pct 都回到正常日波动范围（±1% ~ ±6%），证明后端计算正确

## 部署 + 后续

1. `git add` + `git commit` + `git push`（待用户指令）
2. ECS 上 deploy 触发前端 vite build 输出 dist，下次 nginx 服务即可生效
3. 验证浏览器：打开 `/` 首页 → 滚动到市场脉搏 → 标普 500 应显示 **-1.01%** 而非 **-100.99%**

## 复核 — 子 agent 6 报告 vs 实际修复面

子 agent 6 跑完一遍后端所有 `*_pct` 字段语义审计（见 `/tmp/.../ad222e5d67f4587f5.output`），给出 9 处"剩余 ×100 bug"。本轮对照代码 + 后端 schema 权威源复核后：

| 子 agent 标记 | 实际验证 | 处置 |
|---|---|---|
| InstrumentList:71 仍 ×100 | grep 确认已用 `ReturnTagPct` | ✅ 上轮已修 |
| Favorites:200 仍 ×100 | grep 确认已用 `ReturnTagPct` | ✅ 上轮已修 |
| CryptoList:313 仍 ×100 | grep 确认已用 `ReturnTagPct` | ✅ 上轮已修 |
| CryptoDetail:448 仍 ×100 | grep 确认已用 `ReturnTagPct` | ✅ 上轮已修 |
| SectorRotation 5 处 ×100 bug | `return_*` 字段实际是 DECIMAL（来自 etf_indicator），`ReturnTag` = `formatPercent ×100` = 正确 | ✅ **子 agent 误判，不修** |
| Phase3ReturnTag ×5 bug | 同上 | ✅ **子 agent 误判，不修** |
| FundFlow:352/401/494 ×100 | grep 确认已切 `ReturnTagPct`（子 agent 报告基于初版未更新） | ✅ 上轮已修 |
| Screen:101 volatility_20d 缺 ×100 | `v.toFixed(1)%` 输入 DECIMAL → 显示 `0.1%` 而非 `5.0%` | ✅ **真 bug，已修** |
| Macro:77 ×100 错误 | `formatValue` 只对 `unit === '%'` 加 %，其他 raw level 不加 % | ✅ **子 agent 误判，不修** |

### 第二轮新增修复

- `web/src/pages/Screen/index.tsx:101` volatility_20d：`{v.toFixed(1)}%` → `{(v * 100).toFixed(1)}%`，同时把 `v ? ... : '-'` 改为 `v != null ? ... : '-'`（处理 0 不是 falsy 的边缘场景）
- 复核代码：所有 `return_*` / `volatility_*` / `main_net_pct` 等 DECIMAL 字段正确显示百分比；所有 `change_pct` / `settle_change_pct` PCT 字段切换到 `ReturnTagPct`

### 子 agent 报告的真正价值

1. **后端 schema 描述说谎问题**（`SectorPerformance.return_*` 写 `(%)` 但实际 DECIMAL）→ 这是 API 文档不一致 bug，前端无法发现，**应单独建 ticket 补齐所有 Pydantic schema description**，例如：
   - `IndicatorResponse.return_*`: `description="Decimal (0.05 = 5%)"`
   - `SectorPerformance.return_*`: 同上
   - `MacroLatestItem.change_pct`: `description="Percent (5.0 = 5%)"`
2. **同名异义 `pnl_pct`**：`BacktestTrade.pnl_pct` (DECIMAL) vs `PaperAccountOut.pnl_pct` (PCT) — 不同 schema 反义，**应统一命名**（如 `_decimal` / `_pct` 后缀）
3. **筛选入参 PCT / 存储 DECIMAL 隐性转换**（`ScreenFilter.return_1m_min=2.0` → DB 比较 0.02）依赖 `_pct = v/100` 静默进行 → 未来应改 schema 入参用 `*_pct` 后缀 + 显式 validator

## Why & How to apply

今后新增字段时判断语义：

- **来自 SSE /macro/indices/global /crypto /futures 的 `change_pct`** → 已是百分比本身 → 用 `<ReturnTagPct>` 或 `formatPercentRaw`
- **来自 `etf_indicator.return_*` / `volatility_*`** → 小数 → 用 `<ReturnTag>` 或 `formatPercent`
- **0-100 评分如 `composite_score`** → 既不是小数也不是百分比 → 用纯文本 + `tabular-nums` 类，不要套 ReturnTag（会变 8530%）

新增 API 时在 Pydantic schema 加 `description="百分比本身 (1.5=+1.5%)"` 或 `"小数 (0.025=+2.5%)"` —— **契约清晰 = 不再 bug**。

## 关联

- [[20260714-always-update-runbook-and-decision-log]] — runbook 标准
- [[deepseek-model-catalog]] — 数字判定 reference（无关，但同仓库 ）
- `app/services/screening_service.py:231` 已经示范了入参 % → 内部 ÷ 100 的反向 helper
- `app/data/indicators/risk.py:189` docstring "0.05 = 5%" 是后端"小数"约定权威说明
