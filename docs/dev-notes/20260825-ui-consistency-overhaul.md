# 2026-08-25 UI 一致性大修：83 条假可点击/误导交互/密度不齐统一收敛

> 触发：用户体感「空间利用率不均 + 有些地方悬停像可点其实不可点 +
> 点了和预期不一样」。14 个并行子 agent 审计 50 页，产出 83 条结构化
> 发现；再 5 个修复 agent 并行落地 + 主会话做全局 CSS 门控与收尾。

## 一、审计结果分布

| 类别 | 条数 | 典型例子 |
|---|---|---|
| misleading-click（点击结果与预期不符） | 21 | 整行 window.open 跳外站、chip 点了开抽屉而非详情 |
| false-affordance（不可点却显示可点） | 21 | 全局 `.ant-table-row{cursor:pointer}`、stat-card hover 特效 |
| density-inconsistent（密度跨页/跨区不齐） | 22 | 同一页两个表一个 small 一个默认、字号 10-16px 乱跳 |
| other-consistency | 12 | 状态英文 Tag、重复标题/KPI |
| density-too-low / too-high | 6 / 1 | 期货「板块概况」Panel 两字段占整卡 |

严重度：high 8 / medium 34 / low 41。

## 二、四条系统性修复（commit 7aee8ac，59 文件 +907/-586）

### 1. 假可点击门控（全局，最高杠杆）
- **表格行手型**：`antd-overrides.css` 删掉 `.ant-table-row` 的裸
  `cursor:pointer`，改为只认 `.table-row--clickable`；该类由
  `utils/a11y.ts` 的 `clickableRow()` 统一加注。今后新表要可点行，
  必须走 `clickableRow()` —— 顺手把键盘可达（Enter/Space）也带上。
- **行 hover 底色保留**：数据表的行追踪辅助，不构成可点暗示（有意
  决策，勿当漏网删掉）。
- **stat-card**：hover 浮起/focus 高亮从 `.stat-card` 收编到
  `.stat-card--clickable`（components.css）。

### 2. 标的 chip 语义统一
- **可点 chip = 跳 `/instruments/:code` 详情页**，全站一个语义
  （NewsCard/NewsDetailDrawer/Microstructure/SignalDashboard/
  EtfHoldings*/ScoreRanking/Sentiment/ListingPreview/TradingPanel/
  PaperTrading）。
- **InstrumentCodeTag 新增 `variant="static"`**（中性灰底、默认光标），
  给无详情页的场景：期货合约（futures 体系独立于 instruments）、
  大盘聚合行、未标准化代码。
- **资讯筛选与导航解耦**：NewsCard 的按标的筛选挪到 chip 旁独立
  `FilterOutlined` 小图标；chip 本身跳详情。News 侧栏图例文案同步
  更新（主会话收尾）。

### 3. 误导点击收敛
- SignalDashboard/EtfHoldingsHistory/EtfHoldingsAnalytics：删除被行
  onRow 吃掉或整行 `window.open` 的交互，外链收窄为标题+链接图标。
- 嵌入资讯列表（NewsListPanel、News 详情相关资讯）统一**原地开
  NewsDetailDrawer**，不再整页跳走。
- BacktestList 支持 `?create=1` 直达新建弹窗（StrategyLibrary 入口
  联动）；PaperTrading 支持 `?account=` 深链。
- Favorites 分组表 onRow 加 `closest('button'/'a')` 守卫，行内按钮
  不再触发行跳。

### 4. 密度/字号收敛
- 数据表统一 `size="small"`（Portfolio/FundFlow×4/ETLOps/PoolDetail 等）。
- **字号下限 12px 全部守 token**：10/11px 清零（Microstructure badge、
  SectorRotation 内联 10px、pages-tools/pages-detail/mobile 各处），
  13px 档换 `--text-small-size`。
- Dashboard「决策队列」改单行「平台概览」strip（`.cc-decision-strip`），
  页脚去重；MarketScanner 删重复 Panel；Futures 删稀疏「板块概况」
  Panel（主力合约数并入页首 StatCard 网格）；InstrumentDetail 情绪
  面板有数据态脱离 `.ai-empty`（新类 `.sentiment-panel-body`）。

## 三、验证

- `npm run check:ci`（stylelint + tsc --noEmit + vite build）全绿
- 全量 `npx vitest run`：15 文件 83 测试全过
- 各 agent 自查 eslint：仅存量 react-hooks 警告，非本次引入

## 四、口诀（防复发）

1. **可点性=显式标记，不是全局默认**。新表格行/卡片要可点，必须走
   `clickableRow()` / `--clickable` 类；审查 PR 时见到裸
   `cursor:pointer` 一律打回。
2. **chip 只有两种**：跳详情的 accent chip、纯展示的 static chip。
   没有第三种语义，新增前先想能不能归进这两类。
3. **整行只绑一个动作，且是最可能的那个**；次级动作给行内独立控件
   并 `stopPropagation`。
4. **字号没有 11px 及以下**；写 fontSize 内联前先查 token
   （`--text-label-size`=12 是地板）。
5. 并行多 agent 改同一棵 web 树：按文件清单划禁区，tsc 跨域短暂
   报错属正常，重跑即可（本次 5 agent 零冲突）。

## 相关

- [[20260801 去卡片化 8 页]]（上一轮 UI 收敛）
- [[20260724 颜色 token 化]]（token 体系的来由）
