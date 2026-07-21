# 新手教学增强 Roadmap（K14）

> 目标受众：对「资本市场 / 政治 / 经济」知识不资深、不完备的用户。
> 与 K6（术语字典 + AI Help 上下文）的关系：K6 偏「解释术语 / 上下文精准问答」；K14 偏「新手完整上手、情景化引导、个性化层级」。避免重叠。
> 日期：2026-07-04 · 负责 agent：K14 · 状态：P0 已落地；P1 已落地 3/6 项（2026-07-21 核实，见 §3 内标注）

> 最后核实更新：2026-07-21

---

## 1. 调研摘要

### 1.1 现有可复用资产

| 组件 / 文件 | 行数 | 接口要点 |
| --- | --- | --- |
| `web/src/components/HelpPopover.tsx` | 156 | 接受 `termKey: string`、`contextData?: string`、`trigger?: 'hover'\|'click'`、`enabled?: boolean`。Popover 内容已经渲染 shortDesc / fullDesc / formula / interpretation / example。可被新增 `mode` props 扩展。 |
| `web/src/components/HelpTrigger.tsx` | 32 | 通用 AI 帮助触发按钮。tooltip 默认 `"AI 解释"`。 |
| `web/src/components/AIHelpDrawer.tsx` | 236 | 右侧 Drawer（移动端 100%），接受来自 `useAIHelp().open({pageType, pageTitle, contextData, initialQuestion, quickQuestions})`。已经具备 `quickQuestions` Chip 区。 |
| `web/src/utils/termDictionary.ts` | 1044 | `TermEntry` 已有字段：`key / title / shortDesc / fullDesc / formula? / interpretation? / example? / relatedPageType?`。**新增 `level` 字段即可实现 novice/pro 区分；本次仅扩展类型与少量示例，不重写。** |
| `web/src/stores/settings.ts` | 24 | zustand + persist，键名 `settings-storage`，只持久化 `colorConvention`。可作为 K14 `mode` 偏好的宿主 store。 |
| `web/src/stores/auth.ts` | – | 提供 `user` 与登录态；Onboarding 应在登录后第一次进首页触发。 |
| `web/src/components/AppLayout.tsx` | 437 | Layout 主壳。Onboarding 注入点位于 `<Outlet />` 之后；新手模式切换入口放在右上角用户 Dropdown。 |
| `web/src/pages/Dashboard/index.tsx` | – | 用户第一次进来就是这里，Onboarding Tour 第一站。 |
| `web/src/pages/Screen/index.tsx` | – | `FilterToolbar` + `Table` 结构清晰，适合放 ContextHint。 |
| `web/src/pages/SignalDashboard/index.tsx` | – | KPI strip + Filter + Table，适合放 ContextHint。 |
| `web/src/pages/PaperTrading/index.tsx` | – | 账户/持仓/订单三段结构，新手最易懵。 |

### 1.2 命名与样式约定

- localStorage 命名风格：
  - zustand persist 用 `xxx-storage`（例如 `settings-storage`）；
  - 自定义键统一前缀 `ad-research:<area>:<key>`（K14 自创，所有键都带此前缀）。
- 样式：项目用 SCSS module-like 字符串 className（`.help-popover__xxx` 风格），新组件沿用同一约定；少量 className 即可，纯 CSS 变量驱动主题，**不引入新依赖**。

### 1.3 与 K6 不重叠的边界

| 关注点 | K6 已有 | K14 新增 |
| --- | --- | --- |
| 术语解释 | Hover Tooltip / Popover | 首次进页的全屏 Tour / 一次性气泡 |
| 术语定义 | 字典式 `shortDesc / fullDesc` | `mode === 'novice'` 时显示「为什么要看 + 类比 + 例子」；`mode === 'pro'` 时等同 K6 行为 |
| AI Help | 上下文 + 快捷问题 | 情景教程入口：dashboard chip、Learning 页静态卡片，自动带初始 question |
| 学习路径 | 无 | 5-6 步 OnboardingTour + Learning 页情景 |

---

## 2. 设计总览：4 大功能层

1. **新手首次上手引导（Onboarding）** — AntD `Tour`，5-6 步覆盖：首页 / 选股器 / 信号看板 / 研究笔记 / 模拟交易。localStorage 持久化完成标记；首次跳过可由 HelpTrigger 重新触发。
2. **上下文提示气泡（Contextual Hints）** — `<ContextHint hintId="…">` 组件包目标 DOM 节点，首次进入页面显示一次性气泡，关闭后写 localStorage。
3. **新手 vs 专业 mode 切换** — `useSettingsStore().mode`，`mode === 'novice'` 时 HelpPopover 显示更长 `fullDesc + example + interpretation`，并在抽屉顶部追加「为什么需要看这个？」类比说明。
4. **情景化教学模块（Scenario Tutorials）** — dashboard 顶部 chip + 新页面 `/learning`，3 个静态情景卡片，逐步跳转不同页面 + 自动打开 AI Help 带 initialQuestion。

---

## 3. 优先级与拆分

### P0（已落地，本次提交）

1. `OnboardingTour` — 5 步 Tour，localStorage 持久化，登录后第一次进 `/dashboard` 触发。
2. `ContextHint` — 一次性气泡组件，三个高频页各 1 处。
3. `useSettingsStore.mode` + HelpPopover 接受 `mode` props + 用户菜单 Segmented 切换。
4. `/learning` 路由 + dashboard chip 入口 + 3 个静态情景卡片。

### P1（后续 agent 接力）

- **P1.1 把 mode 推广到所有 HelpPopover 调用点** ✅ 已落地（2026-07-21 核实：全仓约 100+ 处 `mode={mode}` 调用，覆盖 20 个页面/组件）。
- **P1.2 把 mode 接到 AI Help Drawer** ✅ 已落地：`AIHelpDrawer.tsx` 读 `useSettingsStore().mode` 并显示「新手 / 专业」tag。
- **P1.3 给 TermEntry 补 `noviceDesc` 字段** ❌ 未做：`termDictionary.ts` 仍无 `noviceDesc`，novice 模式沿用 `fullDesc + example` 回退（`relatedTerms` 字段已由 K15 线补上）。
- **P1.4 情景教程自动带 initialQuestion** ⚠️ 部分落地：`/learning` 情景卡已有 `initialQuestion` 字段并以「推荐先问 AI」展示，但点击仍是跳转页面，未自动 `open({ initialQuestion })`。
- **P1.5 OnboardingTour 锚定真实 DOM** ✅ 已落地：步骤定义在 `web/src/hooks/useOnboardingSteps.ts`，通过 `data-onboard` 锚定（welcome-dashboard / filter-toolbar / signals-panel / research-notes / paper-account），找不到锚点时回退居中 modal；步数由 5 步扩为 **6 步**。
- **P1.6 移动端适配**：Tour / ContextHint 在窄屏自动转底部 sheet。

### P2（远期）

- **P2.1 进度追踪**：在用户菜单展示「新手教程完成 X / 5」。
- **P2.2 上下文相关 hint**：基于使用频率，动态决定是否再提示一次。
- **P2.3 多语言**：i18n 当前未接入，新手文案预留 `t('onboarding.step1.title')`。
- **P2.4 教程完成奖励**：完成后解锁某条 shortcut 或隐藏入门 tip。

---

## 4. localStorage 键清单（K14 新增，全部前缀 `ad-research:`）

| Key | 类型 | 用途 |
| --- | --- | --- |
| `ad-research:onboarding:completed` | `'1'` | OnboardingTour 是否已完成（zustand persist 接管，store key `ad-research-onboarding-storage`，字段 `completed: boolean`） |
| `ad-research:hint:<page>:dismissed` | `'1'` | ContextHint 关闭标记，例如 `ad-research:hint:paper-trading:dismissed` |
| `ad-research:mode` | `'novice'` / `'pro'` | 用户偏好；落到现有 `settings-storage` 的 `mode` 字段 |

---

## 5. 路由 / 组件改动清单

| 文件 | 改动 |
| --- | --- |
| `web/src/stores/onboarding.ts` | 新建：zustand persist store，字段 `completed: boolean` |
| `web/src/stores/settings.ts` | 扩展：新增 `mode: 'novice'\|'pro'`，默认 `'novice'`，加入 partialize |
| `web/src/components/OnboardingTour.tsx` | 新建：AntD Tour 包装，从 store 读 completed，按 pathname 决定要不要开 |
| `web/src/components/ContextHint.tsx` | 新建：可包裹子节点，首次显示 Popover，关闭后写 localStorage |
| `web/src/components/HelpPopover.tsx` | 修改：新增 `mode?: 'novice'\|'pro'`；novice 时显示更长的 fullDesc + example 块 |
| `web/src/components/AppLayout.tsx` | 修改：挂 `<OnboardingTour />`；用户菜单添加 mode Segmented；提供「重新触发新手引导」菜单项 |
| `web/src/pages/PaperTrading/index.tsx` | 修改：在账户为空处挂 `<ContextHint hintId="paper-trading-empty">` |
| `web/src/pages/SignalDashboard/index.tsx` | 修改：在 KPI strip 下方挂 `<ContextHint hintId="signal-dashboard-table">` |
| `web/src/pages/Screen/index.tsx` | 修改：在 FilterToolbar 上方挂 `<ContextHint hintId="screen-filter">` |
| `web/src/pages/Dashboard/index.tsx` | 修改：在 masthead 下挂「新手教程 chip」行 |
| `web/src/pages/Learning/index.tsx` | 新建：3 个静态情景卡片 |
| `web/src/routes.tsx` | 修改：新增 `/learning` 路由（不放入左侧菜单，仅 chip + URL 进入） |

---

## 6. 验证

- `npx tsc --noEmit` 通过。
- `npm run build` 通过。
- 不 push 到 GitHub（按 K14 用户授权要求）。

---

## 7. P1 / P2 后续 agent 指南

接手时建议：

1. **从 `useSettingsStore` 入手**：mode 已就绪，只需 `import { useSettingsStore } from '@/stores/settings'`，然后 `const { mode } = useSettingsStore()`。
2. **从 `HelpPopover` 入手**：~~在 K14 P0 基础上，给所有调用点传 `mode={mode}`~~（已完成）。如需更结构化的新手文案，可给 `termDictionary.ts` 添加 `noviceDesc?: string`，novice 模式下优先使用 `noviceDesc`，缺失时回退到 `fullDesc + example`（此字段目前仍未添加）。
3. **从 `OnboardingTour` 入手**：~~把每一步 `target: () => document.querySelector('[data-onboard="xxx"]')` 替换成真实 DOM 锚点~~（已完成，步骤定义见 `web/src/hooks/useOnboardingSteps.ts`；新增步骤时在目标页面加 `data-onboard="step-key"` 即可）。
4. **ContextHint**：已经在三个页面埋点；新增页面时只需 `<ContextHint hintId="page-name-key">`，约定 `ad-research:hint:page-name-key:dismissed`。
5. **情景教程**：K14 P0 已给 3 个静态卡片 + `/learning` 入口；扩展时只需往 `web/src/pages/Learning/scenarios.ts` 添加新条目。

> 备注：所有 K14 新增文案均使用中文，与项目现有风格一致；如未来接 i18n，可抽离成 `web/src/locales/zh-CN/onboarding.json`。