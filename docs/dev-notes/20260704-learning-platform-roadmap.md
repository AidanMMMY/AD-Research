# AD-Research 学习平台扩展 Roadmap

> 作者：子 agent K15 · 起点：2026-07-04
> 协作：K6（术语词典）、K14（新手教学 / novice-pro mode）
> 范围：把 AD-Research 从"研报工具"扩展为"研报 + 学习平台"。
> 重点：每页都有教学 + 学习模式开关 + AI 引导提示。

---

## 1. 调研摘要

### 1.1 现有基础设施

| 模块 | 文件 | 现状 |
| --- | --- | --- |
| 术语词典 | `web/src/utils/termDictionary.ts` | 80+ 条目；含 `shortDesc`/`fullDesc`/`formula`/`interpretation`/`example`/`relatedPageType`，但**没有** `relatedTerms` 字段，也没有按"分类"或"难度"分组。 |
| AI 教学助手 | `web/src/components/AIHelpDrawer.tsx` + `AIHelpProvider.tsx` + `hooks/useAIHelp.ts` | 右下角抽屉；每页可注入 `quickQuestions`。 |
| 帮助上下文 | `web/src/utils/helpContext.ts` + `web/src/utils/helpPrompts.ts` | 8 类页面的 system prompt + quick questions（K6 已加）。 |
| 浮层解释 | `web/src/components/HelpPopover.tsx` + `HelpTrigger.tsx` + `ContextHint.tsx` + `TermTooltip.tsx` | Popover / Tooltip / 一次性 hint。K14 已新增 `mode: 'novice' \| 'pro'` 切换。 |
| 用户偏好 | `web/src/stores/settings.ts` | 已有 `mode: novice\|pro`、`colorConvention`。 |
| 页面头 | `web/src/components/PageHeader.tsx` + `PageShell.tsx` | 简单 H1 + description + extra。无学习模式开关位。 |
| StatCard / Sparkline / KLineChart | `components/StatCard.tsx` + `Sparkline.tsx` + `KLineChart.tsx` | 纯数据展示，未与教学联动。 |
| 新手教程页 | `web/src/pages/Learning/index.tsx` | 3 个场景卡（估值/央行/回测）。 |
| AppLayout 用户菜单 | `components/AppLayout.tsx` | 已有"教学模式 novice/pro"切换 + "重新触发新手引导" + "新手教程"入口。 |

### 1.2 各页面"教学空白"

| 页面 | 已有教学 | 空白 |
| --- | --- | --- |
| Dashboard | novice/pro 模式、`HelpPopover` 包了头部统计与 Top10 表头、3 chip 跳转 `/learning` | 缺少"今天学什么"伴随、缺少已学词条统计、缺少路由到知识图谱 |
| InstrumentList / InstrumentDetail | `HelpPopover` 包了所有技术字段、stat-block 有 `HelpTrigger` 顶部 | Hero KPIs（RSI/波动率/回撤/月收益）只有数值，没有"这个数值代表什么"小字说明；K 线图没有"怎么看"教学；新手可能不知道先看哪个维度 |
| Screen | 顶部 PageHeader description | 大量筛选条件（综合评分/RSI/夏普/回撤）语义不直白，新手会卡在"我应该选什么" |
| ScoreRanking | 表头 + 行内 `HelpPopover` | 维度权重选择、模板对比解释 |
| BacktestDetail | StatCard + `HelpTrigger` | 净值曲线、最大回撤、夏普、胜率的"如何判断好坏" |
| SignalDashboard | — | 信号强度阈值、家族筛选 |
| PaperTrading / TradingPanel | — | 订单类型（市价/限价）、滑点、熔断 |
| SentimentDashboard | — | 多空比、热度的可信度与阈值 |
| ResearchNotes | — | 笔记类型、置信度 |
| StrategyLibrary | `StrategyCard` 模板列表 | 3 种策略适用场景对比 |

### 1.3 不与 K6/K14 重复

- K6：**术语词典**——已做；K15 不重复写。
- K14：**novice/pro mode + 新手引导 + 5 步 tour + tutorial chips**——已做；K15 只做"learningMode"开关（一个 boolean），与 `useSettingsStore` 复用。
- K15 重点：**每页"伴随"层**（daily lesson + explainer + AI 上下文问题增强）。

---

## 2. Roadmap

### P0（本期必须）

1. **Dashboard「今日学习 3 分钟」卡片**——顶部 Section `daily-lesson`，每天（按当前日期 hash）从 `termDictionary` 抽 1 个词条。包含：
   - 词条标题 + `shortDesc`
   - "展开看 fullDesc"按钮
   - "问 AI"按钮（直接调 `useAIHelp().open()`）
   - "我学会了"按钮（写入 `localStorage.ad-research:learned_terms` Set，今天不再显示）
2. **每页学习模式开关**——`useSettingsStore` 新增 `learningMode: boolean`。**默认关闭**，与 `mode` 独立。开启后：
   - 所有 `StatCard` 下方追加 `<StatExplainer term="..." />` 一行小字（短解释 + 反问/例子）
   - 通过 props 显式 opt-in：`StatCard` 增加 `term`/`explainer` prop，未传则不显示
3. **统一组件 `<StatExplainer termKey="...">`**——`web/src/components/StatExplainer.tsx`。封装：
   - term 不存在 → 静默不渲染
   - learningMode 关 → 不渲染
   - 渲染一行小字，用 `term.shortDesc`，可点击展开 `term.fullDesc`
4. **AI Help quick questions 增强**——在 `helpPrompts.ts` 每页 quick questions 末尾追加一句：`能不能用更简单的语言再解释一遍？`，让 novice 用户可一级级追问（系统 prompt 不动，避免对所有 prompt 加 tokens）。
5. **PageHeader 新增 `tutorial?: ReactNode` slot**——可选 1-3 句话的"怎么读这个页"。
   - 优先在 `InstrumentDetail` / `BacktestDetail` / `TradingPanel` / `StrategyLibrary` 添加。
6. **`learningMode` 在 AppLayout 用户菜单中暴露**——复用现有 Dropdown，加一个 Switch。

### P1（下一轮）

1. **Knowledge Graph 入口**——`/learning` 加 chip「查看知识图谱」；新增轻量可视化（按 relatedPageType 分组）。
2. **`TermEntry.relatedTerms: string[]`**——K6 落地时再补，K15 提供字段支持：在 `HelpPopover` 末尾显示「相关术语」链接（hover 跳转）。
3. **Dashboard 增加「本周学习了 N 个术语」**——读 `localStorage.ad-research:learned_terms`，显示在本周开始至今的计数。
4. **每页教学覆盖率统计**——开发期 devtools（学习模式开时右下角小窗，列出哪些字段还没教学）。

### P2（远期）

1. 后端事件→标的关联挖掘（geopol / news 等影响行业）。
2. "我做对了吗？"回测/模拟交易复盘工具。
3. 教学视频 / PDF 嵌入到 ContextHint。
4. 个性化推荐（基于用户已学词条 + 关注标的，主动推送相关教学）。

---

## 3. 实现细节

### 3.1 `useSettingsStore.learningMode`

```ts
interface SettingsState {
  // 已有
  colorConvention: ColorConvention;
  mode: HelpMode;
  // 新增
  learningMode: boolean;
  setLearningMode: (v: boolean) => void;
}
```

`partialize` 改为包含 `learningMode`，向后兼容已有 localStorage。

### 3.2 `<StatExplainer termKey="...">` 行为

- 静态文本：term.shortDesc 一行，文末"?" icon
- 点击 → 自带 Popover 展示 fullDesc + interpretation
- learningMode 关 + 没传 termKey → 不渲染
- 不依赖 popover 的 trigger 行为，避免与当前页面其他教学叠层

### 3.3 Dashboard daily lesson 的去重

- 用 `localStorage.ad-research:lesson:<YYYYMMDD>` 记录当天是否已抽取 → 同一天稳定同一个词条
- `localStorage.ad-research:learned_terms` Set：用数组存（避免 Set 序列化丢失）
- "我学会了"按钮：将 `term.key` 推入数组去重后写入

### 3.4 helpPrompts 增强

不改 system prompt（避免 token 多花），只在 quick questions 末尾追加：

```ts
'能不能用更简单的语言再解释一遍？'
```

仅增加 1 个 quick question；语义跟现有 quick questions 互补。

---

## 4. 验证方式

- `npx tsc --noEmit` 必须 0 error
- `npm run build` 通过
- 手工：
  - 开启 learningMode 后，Dashboard StatCard 下方有解释
  - daily lesson 模块每天抽一个词条
  - "我学会了"点击后本周统计 +1
- 不 push。

---

## 5. 与既有约束的关系

- 不创建新 store（用 `useSettingsStore`）
- 不重写 `termDictionary`（只读不改）
- 不动 system prompt（只在 quick questions 数组末尾加 1 条）
- 不引入新依赖
