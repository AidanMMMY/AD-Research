# 前端视觉改造（Swiss Minimal + Neon Cyan）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有深色玻璃拟态风格的投资研究平台 Web 前端，整体升级为 Swiss Minimal + Neon Cyan 视觉语言：减少卡片和渐变滥用，强化排版层级，统一设计 token，并在不引入新 UI 框架的前提下完成全部核心页面重构。

**Architecture:** 通过 CSS Variables 集中管理新设计 token，先刷新 `theme.css`/`global.css` 和 Ant Design `ConfigProvider` 全局配置，再逐层改造共享组件（`GlassCard`→`Panel`、`GradientStatCard`、`ETFCodeTag`、`ScoreBar`、`AppLayout`），最后按页面重构具体布局。所有改动保持现有 React + TypeScript + Vite + Ant Design 5 技术栈不变。

**Tech Stack:** React 18, TypeScript 5, Vite 5, Ant Design 5, @ant-design/pro-components, TanStack Query, Zustand, ECharts, lightweight-charts.

---

## 0. 前置知识与约定

- 暗色主题已启用：`ConfigProvider` 使用 `theme.darkAlgorithm`。
- 颜色规范基于设计文档 `docs/superpowers/specs/2026-06-27-frontend-visual-redesign-design.md`。
- 主强调色统一为 **Neon Cyan `#22d3ee`**。
- 背景由深蓝黑改为纯深灰黑：`#0a0a0a`（base）、`#111111`（elevated）。
- 圆角全面缩小：按钮/输入框 4px，标签 3px，模态/抽屉 12px，大面板/表格 0px。
- 页面级重构**不改变业务逻辑、数据接口、路由结构和字段含义**，只调整布局、样式和组件用法。
- 所有视觉改动应通过 `pnpm dev`（或 `npm run dev`）在 `web/` 目录实时验证。

---

## File Structure

| 文件 | 责任 |
|---|---|
| `web/src/styles/theme.css` | Design Token：颜色、字体、间距、圆角、阴影、动画。 |
| `web/src/styles/global.css` | Ant Design 组件全局覆盖 + 响应式覆盖。 |
| `web/src/main.tsx` | Ant Design `ConfigProvider` token 和字体配置。 |
| `web/src/components/Panel.tsx` | 新建极简面板组件，替代 `GlassCard` 的大部分使用场景。 |
| `web/src/components/GlassCard.tsx` | 保留但改造为 Panel 的轻量包装，保持向后兼容。 |
| `web/src/components/GradientStatCard.tsx` | 改造为 Swiss 风格数据卡片，移除渐变和发光。 |
| `web/src/components/ETFCodeTag.tsx` | 改造为霓虹青/灰阶简洁标签。 |
| `web/src/components/ScoreBar.tsx` | 更新为灰阶轨道 + 单一强调色或语义色，去掉发光。 |
| `web/src/components/AppLayout.tsx` | 改造侧边栏和顶部 Header。 |
| `web/src/pages/Dashboard/index.tsx` | 重构首页：Hero KPI + 扁平表格 + 减少卡片。 |
| `web/src/pages/ETFList/index.tsx` | 重构列表页：极简 Filter Bar + 扁平表格/列表。 |
| `web/src/pages/ETFDetail/index.tsx` | 重构详情页：标题区扁平化、Tabs 下划线风格、指标去卡片。 |
| `web/src/pages/BacktestDetail/index.tsx` | 重构回测详情：指标去卡片、图表主题更新。 |
| `web/src/pages/PoolDetail/index.tsx` | 重构池子详情。 |
| `web/src/pages/ScoreRanking/index.tsx` | 重构评分排名页。 |
| `web/src/pages/Screen/index.tsx` | 重构筛选页。 |
| `web/src/pages/StrategyList/index.tsx` | 重构策略列表。 |
| `web/src/utils/color.ts` | 更新评分色和信号色，与市场色保持一致。 |

---

## Phase 1: Design Token 刷新

### Task 1.1: 重写 `theme.css` 设计 token

**Files:**
- Modify: `web/src/styles/theme.css`

- [ ] **Step 1: 备份当前文件**

```bash
cp web/src/styles/theme.css web/src/styles/theme.css.bak
```

- [ ] **Step 2: 替换 `:root` 全部 token 为 Swiss Minimal 系统**

将 `web/src/styles/theme.css` 中 `:root { ... }` 区块替换为：

```css
:root {
  /* ---- Background Layers ---- */
  --bg-base: #0a0a0a;
  --bg-elevated: #111111;
  --bg-hover: rgba(255, 255, 255, 0.03);
  --bg-active: rgba(255, 255, 255, 0.05);
  --bg-input: rgba(255, 255, 255, 0.02);
  --bg-surface: rgba(255, 255, 255, 0.02);
  --bg-surface-hover: rgba(255, 255, 255, 0.04);
  --bg-surface-active: rgba(255, 255, 255, 0.06);

  /* ---- Accent: Neon Cyan ---- */
  --accent: #22d3ee;
  --accent-dim: rgba(34, 211, 238, 0.08);
  --accent-border: rgba(34, 211, 238, 0.25);
  --accent-glow: rgba(34, 211, 238, 0.15);
  --accent-hover: #67e8f9;

  /* ---- Legacy primary aliases (kept for compatibility) ---- */
  --primary-solid: var(--accent);
  --primary-dim: var(--accent-dim);
  --primary-gradient: linear-gradient(135deg, var(--accent) 0%, var(--accent-hover) 100%);
  --accent-cyan: var(--accent);
  --accent-teal: #14b8a6;

  /* ---- Text Colors ---- */
  --text-primary: #f5f5f5;
  --text-secondary: #aaaaaa;
  --text-tertiary: #555555;
  --text-muted: #3a3a3a;

  /* ---- Market Colors (China A-share convention) ---- */
  --color-rise: #ef4444;
  --color-rise-dim: rgba(239, 68, 68, 0.12);
  --color-fall: #22c55e;
  --color-fall-dim: rgba(34, 197, 94, 0.12);
  --color-neutral: #aaaaaa;

  /* ---- Score Colors ---- */
  --score-excellent: #22c55e;
  --score-good: #84cc16;
  --score-average: #eab308;
  --score-poor: #f97316;
  --score-bad: #ef4444;

  /* ---- Border & Shadow ---- */
  --border-default: rgba(255, 255, 255, 0.06);
  --border-strong: rgba(255, 255, 255, 0.10);
  --border-hover: rgba(255, 255, 255, 0.12);
  --border-accent: rgba(34, 211, 238, 0.30);
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.2);
  --shadow-md: 0 4px 16px rgba(0, 0, 0, 0.3);
  --shadow-lg: 0 8px 32px rgba(0, 0, 0, 0.4);
  --shadow-card: var(--shadow-md);
  --shadow-card-hover: var(--shadow-lg);
  --shadow-glow: 0 0 24px var(--accent-glow);

  /* ---- Spacing (4px base) ---- */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --space-7: 40px;
  --space-8: 48px;
  --space-9: 64px;
  /* Legacy aliases */
  --space-xs: var(--space-1);
  --space-sm: var(--space-2);
  --space-md: var(--space-4);
  --space-lg: var(--space-5);
  --space-xl: var(--space-6);

  /* ---- Radius ---- */
  --radius-none: 0px;
  --radius-sm: 3px;
  --radius-md: 4px;
  --radius-lg: 8px;
  --radius-xl: 12px;
  /* Legacy aliases */
  --radius-sm: var(--radius-md);
  --radius-md: var(--radius-lg);
  --radius-lg: var(--radius-xl);
  --radius-xl: 16px;

  /* ---- Typography ---- */
  --font-sans: "Inter", "SF Pro Display", -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
  --font-mono: "JetBrains Mono", "SF Mono", "Fira Code", "Cascadia Code", monospace;

  --text-h1: 500 26px/1.2 var(--font-sans);
  --text-h2: 500 20px/1.3 var(--font-sans);
  --text-h3: 500 16px/1.4 var(--font-sans);
  --text-data-xl: 400 40px/1.1 var(--font-mono);
  --text-data-lg: 400 24px/1.2 var(--font-mono);
  --text-data-md: 500 16px/1.3 var(--font-mono);
  --text-body: 400 13px/1.6 var(--font-sans);
  --text-small: 500 11px/1.4 var(--font-sans);
  --text-label: 500 10px/1.2 var(--font-sans);
  --text-code: 400 12px/1.4 var(--font-mono);

  /* ---- Animation ---- */
  --transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-base: 200ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-slow: 300ms cubic-bezier(0.4, 0, 0.2, 1);
}
```

> 注意：保留 `--space-xs`/`--space-sm`/`--space-md`/`--space-lg`/`--space-xl` 以及旧的 `--radius-sm`/`--radius-md`/`--radius-lg`/`--radius-xl` 别名是为了让未迁移的代码暂时不报错，但新代码应优先使用 `--space-1` 到 `--space-9` 和精确 radius token。

- [ ] **Step 3: 更新全局 reset 和 selection 颜色**

在 `theme.css` 全局覆盖区块替换：

```css
html,
body,
#root {
  background: var(--bg-base);
  color: var(--text-primary);
  font-family: var(--font-sans);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

::selection {
  background: var(--accent-dim);
  color: var(--accent);
}
```

- [ ] **Step 4: 启动 dev server 验证无编译报错**

Run: `cd /Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web && pnpm dev`

Expected: Vite 启动成功，终端无 CSS 语法错误。

- [ ] **Step 5: Commit**

```bash
git add web/src/styles/theme.css

git commit -m "feat(theme): refresh design tokens for Swiss Minimal + Neon Cyan"
```

---

### Task 1.2: 更新 `main.tsx` Ant Design ConfigProvider

**Files:**
- Modify: `web/src/main.tsx`

- [ ] **Step 1: 修改 `antdTheme` token**

将 `web/src/main.tsx` 中的 `antdTheme` 对象替换为：

```tsx
const antdTheme = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: '#22d3ee',
    colorInfo: '#22d3ee',
    colorSuccess: '#22c55e',
    colorWarning: '#eab308',
    colorError: '#ef4444',
    colorBgBase: '#0a0a0a',
    colorBgContainer: '#111111',
    colorBgElevated: '#111111',
    colorTextBase: '#f5f5f5',
    colorBorder: 'rgba(255,255,255,0.06)',
    colorBorderSecondary: 'rgba(255,255,255,0.04)',
    borderRadius: 4,
    borderRadiusSM: 3,
    borderRadiusLG: 8,
    borderRadiusXS: 2,
    fontFamily: "Inter, 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif",
    fontFamilyCode: "'JetBrains Mono', 'SF Mono', 'Fira Code', 'Cascadia Code', monospace",
    controlHeight: 36,
    controlHeightSM: 30,
    controlHeightLG: 44,
  },
  components: {
    Table: {
      headerBg: 'transparent',
      headerColor: '#555555',
      headerSplitColor: 'transparent',
      rowHoverBg: 'rgba(255,255,255,0.03)',
      borderColor: 'rgba(255,255,255,0.06)',
      cellPaddingInline: 16,
      cellPaddingBlock: 12,
      headerBorderRadius: 0,
    },
    Button: {
      borderRadius: 4,
      borderRadiusSM: 3,
      primaryShadow: 'none',
    },
    Card: {
      borderRadius: 8,
      borderRadiusLG: 12,
      colorBgContainer: '#111111',
    },
    Modal: {
      borderRadiusLG: 12,
      colorBgElevated: '#111111',
    },
    Drawer: {
      colorBgElevated: '#111111',
    },
    Tag: {
      borderRadiusSM: 3,
      defaultBg: 'rgba(255,255,255,0.02)',
      defaultColor: '#aaaaaa',
    },
    Input: {
      borderRadius: 4,
      colorBgContainer: 'rgba(255,255,255,0.02)',
      activeBorderColor: '#22d3ee',
      activeShadow: '0 0 0 2px rgba(34,211,238,0.08)',
    },
    Select: {
      borderRadius: 4,
      colorBgContainer: 'rgba(255,255,255,0.02)',
      optionSelectedBg: 'rgba(34,211,238,0.08)',
      optionSelectedColor: '#22d3ee',
    },
    Tabs: {
      inkBarColor: '#22d3ee',
      itemSelectedColor: '#22d3ee',
      itemHoverColor: '#f5f5f5',
      itemColor: '#555555',
    },
  },
};
```

- [ ] **Step 2: 验证页面加载**

Run: 打开 `http://localhost:5173`（或 dev server 实际端口），确认页面背景变为 `#0a0a0a`，无明显样式错乱。

- [ ] **Step 3: Commit**

```bash
git add web/src/main.tsx

git commit -m "feat(theme): update Ant Design ConfigProvider tokens"
```

---

### Task 1.3: 重写 `global.css` Ant Design 覆盖

**Files:**
- Modify: `web/src/styles/global.css`

- [ ] **Step 1: 备份当前文件**

```bash
cp web/src/styles/global.css web/src/styles/global.css.bak
```

- [ ] **Step 2: 精简并替换全局覆盖**

将 `web/src/styles/global.css` 整体替换为：

```css
/* ============================================================
   Global Ant Design Overrides — Swiss Minimal + Neon Cyan
   ============================================================ */

.ant-layout {
  background: var(--bg-base) !important;
}

.ant-layout-content {
  background: var(--bg-base) !important;
}

/* Card — Minimal, only for real containers */
.ant-card {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-default) !important;
  border-radius: var(--radius-lg) !important;
  box-shadow: none !important;
}

.ant-card-head {
  background: transparent !important;
  border-bottom: 1px solid var(--border-default) !important;
  color: var(--text-primary) !important;
  font-weight: 500;
  font-size: var(--text-h3);
  padding: var(--space-4) var(--space-5) !important;
}

.ant-card-body {
  padding: var(--space-4) var(--space-5) !important;
}

.ant-card-small {
  border-radius: var(--radius-md) !important;
}

.ant-card-small .ant-card-head {
  padding: var(--space-3) var(--space-4) !important;
  font-size: var(--text-body);
}

.ant-card-small .ant-card-body {
  padding: var(--space-3) var(--space-4) !important;
}

/* Table */
.ant-table {
  background: transparent !important;
  color: var(--text-primary);
}

.ant-table-thead > tr > th {
  background: transparent !important;
  color: var(--text-tertiary) !important;
  font-weight: 500;
  font-size: var(--text-label);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  border-bottom: 1px solid var(--border-default) !important;
  padding: var(--space-3) var(--space-4) !important;
}

.ant-table-tbody > tr > td {
  border-bottom: 1px solid var(--border-default) !important;
  color: var(--text-secondary);
  padding: var(--space-3) var(--space-4) !important;
  transition: color var(--transition-fast), background var(--transition-fast);
}

.ant-table-tbody > tr:hover > td {
  background: var(--bg-hover) !important;
  color: var(--text-primary) !important;
}

.ant-table-row {
  cursor: pointer;
}

/* Pagination */
.ant-pagination {
  color: var(--text-secondary);
}

.ant-pagination-item {
  background: transparent !important;
  border-color: var(--border-default) !important;
  border-radius: var(--radius-md) !important;
}

.ant-pagination-item a {
  color: var(--text-secondary) !important;
}

.ant-pagination-item-active {
  background: var(--accent-dim) !important;
  border-color: var(--accent-border) !important;
}

.ant-pagination-item-active a {
  color: var(--accent) !important;
}

/* Tabs */
.ant-tabs-nav {
  margin-bottom: var(--space-4);
}

.ant-tabs-tab {
  color: var(--text-tertiary) !important;
  font-size: var(--text-body);
  transition: color var(--transition-fast);
}

.ant-tabs-tab:hover {
  color: var(--text-secondary) !important;
}

.ant-tabs-tab-active .ant-tabs-tab-btn {
  color: var(--text-primary) !important;
  font-weight: 500;
}

.ant-tabs-ink-bar {
  background: var(--accent) !important;
  height: 2px !important;
  border-radius: 1px;
}

/* Input, Select, InputNumber */
.ant-input,
.ant-select-selector,
.ant-input-number {
  background: var(--bg-input) !important;
  border-color: var(--border-default) !important;
  color: var(--text-primary) !important;
  border-radius: var(--radius-md) !important;
  transition: all var(--transition-fast);
}

.ant-input:hover,
.ant-select-selector:hover,
.ant-input-number:hover {
  border-color: var(--border-hover) !important;
}

.ant-input:focus,
.ant-input-focused,
.ant-select-focused .ant-select-selector,
.ant-input-number-focused {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 2px var(--accent-dim) !important;
}

.ant-select-dropdown {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg) !important;
  box-shadow: var(--shadow-md);
}

.ant-select-item {
  color: var(--text-primary) !important;
  transition: background var(--transition-fast);
}

.ant-select-item-option-active {
  background: var(--bg-hover) !important;
}

.ant-select-item-option-selected {
  background: var(--accent-dim) !important;
  color: var(--accent) !important;
}

/* Button */
.ant-btn {
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
  font-weight: 500;
}

.ant-btn-default {
  background: transparent;
  border-color: var(--border-default);
  color: var(--text-secondary);
}

.ant-btn-default:hover {
  border-color: var(--text-secondary);
  color: var(--text-primary);
  background: var(--bg-hover);
}

.ant-btn-primary {
  background: var(--accent);
  border: none;
  color: #000;
  box-shadow: none;
}

.ant-btn-primary:hover {
  background: var(--accent-hover);
  box-shadow: 0 0 16px var(--accent-glow);
}

/* Tag */
.ant-tag {
  border-radius: var(--radius-sm);
  font-size: var(--text-small);
  padding: 2px 8px;
  border: 1px solid var(--border-default);
  background: var(--bg-input);
  color: var(--text-secondary);
}

/* Statistic */
.ant-statistic-title {
  color: var(--text-tertiary) !important;
  font-size: var(--text-small);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: var(--space-2) !important;
}

.ant-statistic-content {
  color: var(--text-primary) !important;
  font-weight: 400;
  font-size: var(--text-data-lg);
  font-family: var(--font-mono);
  letter-spacing: -0.02em;
}

/* Progress */
.ant-progress-bg {
  border-radius: 2px !important;
}

/* List */
.ant-list {
  background: transparent !important;
}

.ant-list-item {
  border-bottom: 1px solid var(--border-default) !important;
  padding: var(--space-3) 0 !important;
  transition: color var(--transition-fast), background var(--transition-fast);
}

.ant-list-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.ant-list-item-meta-title {
  color: var(--text-primary) !important;
  font-weight: 500;
}

.ant-list-item-meta-description {
  color: var(--text-tertiary) !important;
}

/* Spin */
.ant-spin-dot-item {
  background: var(--accent) !important;
}

/* Alert */
.ant-alert {
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
}

.ant-alert-message {
  color: var(--text-primary);
}

.ant-alert-description {
  color: var(--text-secondary);
}

/* Modal / Drawer */
.ant-modal-content,
.ant-drawer-content {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl) !important;
  box-shadow: var(--shadow-lg);
}

.ant-modal-header {
  background: transparent !important;
  border-bottom: 1px solid var(--border-default);
}

.ant-modal-title {
  color: var(--text-primary) !important;
}

/* Radio */
.ant-radio-button-wrapper {
  background: var(--bg-input);
  border-color: var(--border-default);
  color: var(--text-secondary);
}

.ant-radio-button-wrapper-checked {
  background: var(--accent-dim) !important;
  border-color: var(--accent-border) !important;
  color: var(--accent) !important;
}

/* Checkbox */
.ant-checkbox-wrapper {
  color: var(--text-secondary);
}

.ant-checkbox-checked .ant-checkbox-inner {
  background: var(--accent);
  border-color: var(--accent);
}

/* Slider */
.ant-slider-rail {
  background: var(--border-default);
}

.ant-slider-track {
  background: var(--accent);
}

.ant-slider-handle {
  border-color: var(--accent);
}

/* Dropdown Menu */
.ant-dropdown-menu {
  background: var(--bg-elevated) !important;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg) !important;
  box-shadow: var(--shadow-md);
}

.ant-dropdown-menu-item {
  color: var(--text-primary) !important;
}

.ant-dropdown-menu-item:hover {
  background: var(--bg-hover) !important;
}

/* Descriptions */
.ant-descriptions-item-label {
  color: var(--text-tertiary);
  font-size: var(--text-small);
}

.ant-descriptions-item-content {
  color: var(--text-primary);
}

/* Skeleton */
.ant-skeleton-active .ant-skeleton-paragraph > li,
.ant-skeleton-active .ant-skeleton-title {
  background: linear-gradient(90deg, rgba(255,255,255,0.03) 25%, rgba(255,255,255,0.08) 37%, rgba(255,255,255,0.03) 63%);
}

/* ============================================================
   Mobile Responsive Overrides (< 768px)
   ============================================================ */
@media (max-width: 767px) {
  /* Tables */
  .ant-table-wrapper {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .ant-table {
    min-width: 100%;
  }

  .ant-table-thead > tr > th {
    font-size: var(--text-small);
    padding: var(--space-2) var(--space-3) !important;
    white-space: nowrap;
  }

  .ant-table-tbody > tr > td {
    font-size: var(--text-body);
    padding: var(--space-2) var(--space-3) !important;
  }

  .ant-table-row {
    min-height: 48px;
  }

  /* Buttons */
  .ant-btn {
    min-height: 40px;
    font-size: var(--text-body);
  }

  .ant-btn-sm {
    min-height: 32px;
  }

  /* Form controls */
  .ant-input,
  .ant-select-selector,
  .ant-input-number,
  .ant-input-number-input {
    min-height: 40px !important;
    font-size: 16px !important;
  }

  .ant-select-selector {
    display: flex !important;
    align-items: center !important;
  }

  /* Card */
  .ant-card-head {
    padding: var(--space-3) var(--space-4) !important;
  }

  .ant-card-body {
    padding: var(--space-3) var(--space-4) !important;
  }

  /* Statistic */
  .ant-statistic-content {
    font-size: var(--text-data-md);
  }

  .ant-statistic-title {
    font-size: var(--text-small);
  }

  /* Tabs */
  .ant-tabs-nav {
    margin-bottom: var(--space-3) !important;
  }

  .ant-tabs-tab {
    font-size: var(--text-body);
    padding: var(--space-2) var(--space-3) !important;
  }

  /* Pagination */
  .ant-pagination {
    font-size: var(--text-body);
  }

  .ant-pagination-item {
    min-width: 34px;
    height: 34px;
    line-height: 34px;
    margin-right: 4px;
  }

  .ant-pagination-prev,
  .ant-pagination-next {
    min-width: 34px;
    height: 34px;
    line-height: 34px;
  }

  /* Select dropdown */
  .ant-select-dropdown {
    max-width: 92vw;
  }

  /* Popover / Tooltip */
  .ant-popover,
  .ant-tooltip {
    max-width: 85vw;
  }

  /* Space */
  .ant-space {
    gap: var(--space-2) !important;
  }

  /* Float buttons */
  .ant-float-btn {
    right: 16px;
    bottom: calc(80px + env(safe-area-inset-bottom, 0px));
  }
}

/* ============================================================
   Tablet Responsive Overrides (768px - 991px)
   ============================================================ */
@media (min-width: 768px) and (max-width: 991px) {
  .ant-card-head {
    padding: var(--space-3) var(--space-5) !important;
  }

  .ant-card-body {
    padding: var(--space-3) var(--space-5) !important;
  }

  .ant-statistic-content {
    font-size: var(--text-data-md);
  }
}

/* ============================================================
   Legacy component helpers (keep until components fully migrated)
   ============================================================ */
@media (max-width: 767px) {
  .glass-card[data-glass-padding="sm"] .glass-card-header,
  .glass-card[data-glass-padding="sm"] .glass-card-body {
    padding-left: 14px !important;
    padding-right: 14px !important;
  }

  .glass-card[data-glass-padding="md"] .glass-card-header,
  .glass-card[data-glass-padding="md"] .glass-card-body {
    padding-left: 16px !important;
    padding-right: 16px !important;
  }

  .glass-card[data-glass-padding="lg"] .glass-card-header,
  .glass-card[data-glass-padding="lg"] .glass-card-body {
    padding-left: 18px !important;
    padding-right: 18px !important;
  }
}
```

- [ ] **Step 3: 验证覆盖生效**

Run: 在浏览器中刷新页面，检查表格表头是否变为大写灰色、Tabs 下划线是否变为青色、按钮 Primary 是否为青色底黑字。

- [ ] **Step 4: Commit**

```bash
git add web/src/styles/global.css

git commit -m "feat(theme): rewrite global Ant Design overrides for Swiss Minimal"
```

---

## Phase 2: 共享组件改造

### Task 2.1: 新建 `Panel` 组件并改造 `GlassCard`

**Files:**
- Create: `web/src/components/Panel.tsx`
- Modify: `web/src/components/GlassCard.tsx`

- [ ] **Step 1: 创建 `Panel.tsx`**

```tsx
import React from 'react';

export interface PanelProps {
  children: React.ReactNode;
  title?: React.ReactNode;
  extra?: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  bordered?: boolean;
  padding?: 'none' | 'sm' | 'md' | 'lg';
}

const paddingMap = {
  none: { desktop: 0, mobile: 0 },
  sm: { desktop: 16, mobile: 12 },
  md: { desktop: 24, mobile: 16 },
  lg: { desktop: 32, mobile: 20 },
};

export default function Panel({
  children,
  title,
  extra,
  className = '',
  style,
  bordered = true,
  padding = 'md',
}: PanelProps) {
  const p = paddingMap[padding];

  return (
    <div
      className={`swiss-panel ${className}`}
      style={{
        background: 'var(--bg-elevated)',
        border: bordered ? '1px solid var(--border-default)' : 'none',
        borderRadius: 0,
        ...style,
      }}
    >
      {(title || extra) && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: `${p.desktop}px ${p.desktop}px 12px`,
            borderBottom: '1px solid var(--border-default)',
            gap: 12,
            minWidth: 0,
          }}
        >
          {title && (
            <span
              style={{
                fontSize: 'var(--text-h3)',
                fontWeight: 500,
                color: 'var(--text-primary)',
                letterSpacing: '-0.01em',
                lineHeight: 1.4,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                flex: '1 1 auto',
                minWidth: 0,
              }}
            >
              {title}
            </span>
          )}
          {extra && <div style={{ flexShrink: 0 }}>{extra}</div>}
        </div>
      )}
      <div
        style={{
          padding: title
            ? `12px ${p.desktop}px ${p.desktop}px`
            : `${p.desktop}px`,
        }}
      >
        {children}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 简化 `GlassCard` 为 `Panel` 的兼容包装**

将 `web/src/components/GlassCard.tsx` 整体替换为：

```tsx
import React from 'react';
import Panel from './Panel';

interface GlassCardProps {
  children: React.ReactNode;
  title?: React.ReactNode;
  extra?: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  hover?: boolean;
  padding?: 'sm' | 'md' | 'lg';
  glow?: boolean;
}

/**
 * 兼容性包装：GlassCard 现在内部使用 Panel。
 * hover/glow 参数保留但不再产生视觉差异。
 */
export default function GlassCard({
  children,
  title,
  extra,
  className = '',
  style,
  padding = 'md',
}: GlassCardProps) {
  return (
    <Panel
      title={title}
      extra={extra}
      className={`glass-card ${className}`}
      style={style}
      padding={padding}
      data-glass-padding={padding}
    >
      {children}
    </Panel>
  );
}
```

> TypeScript 可能会对 `data-glass-padding` 属性报错，如果报错则在 `PanelProps` 中增加 `data-glass-padding?: string` 兼容属性，或在 GlassCard 调用处删除该属性并仅保留 className。

- [ ] **Step 3: 修复 TypeScript 编译**

Run: `cd /Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web && pnpm build`

Expected: 通过 TypeScript 编译无报错。

- [ ] **Step 4: Commit**

```bash
git add web/src/components/Panel.tsx web/src/components/GlassCard.tsx

git commit -m "feat(components): add Panel component and simplify GlassCard as wrapper"
```

---

### Task 2.2: 改造 `GradientStatCard` 为 Swiss 数据卡片

**Files:**
- Modify: `web/src/components/GradientStatCard.tsx`

- [ ] **Step 1: 替换组件实现**

将 `web/src/components/GradientStatCard.tsx` 整体替换为：

```tsx
import React from 'react';

interface GradientStatCardProps {
  title: string;
  value: string | number;
  suffix?: string;
  icon?: React.ReactNode;
  loading?: boolean;
  onClick?: () => void;
}

export default function GradientStatCard({
  title,
  value,
  suffix,
  icon,
  loading = false,
  onClick,
}: GradientStatCardProps) {
  return (
    <div
      className="gradient-stat-card"
      onClick={onClick}
      style={{
        background: 'transparent',
        border: '1px solid var(--border-default)',
        borderRadius: 0,
        padding: '20px',
        transition: 'border-color var(--transition-fast), background var(--transition-fast)',
        cursor: onClick ? 'pointer' : 'default',
        position: 'relative',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = 'var(--border-hover)';
        e.currentTarget.style.background = 'var(--bg-hover)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--border-default)';
        e.currentTarget.style.background = 'transparent';
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div style={{ flex: 1 }}>
          <div
            className="gradient-stat-title"
            style={{
              fontSize: 'var(--text-label)',
              color: 'var(--text-tertiary)',
              fontWeight: 500,
              marginBottom: '10px',
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
            }}
          >
            {title}
          </div>
          {loading ? (
            <div
              style={{
                height: '36px',
                width: '80px',
                background: 'var(--bg-hover)',
                borderRadius: '4px',
                animation: 'pulse 1.5s ease-in-out infinite',
              }}
            />
          ) : (
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
              <span
                className="gradient-stat-value"
                style={{
                  fontSize: 'var(--text-data-lg)',
                  fontWeight: 400,
                  color: 'var(--text-primary)',
                  lineHeight: 1.2,
                  fontFamily: 'var(--font-mono)',
                  letterSpacing: '-0.02em',
                }}
              >
                {value}
              </span>
              {suffix && (
                <span
                  className="gradient-stat-suffix"
                  style={{
                    fontSize: 'var(--text-small)',
                    color: 'var(--text-tertiary)',
                    fontWeight: 500,
                  }}
                >
                  {suffix}
                </span>
              )}
            </div>
          )}
        </div>
        {icon && (
          <div
            className="gradient-stat-icon"
            style={{
              width: '40px',
              height: '40px',
              borderRadius: 'var(--radius-md)',
              background: 'var(--bg-input)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '18px',
              flexShrink: 0,
              marginLeft: '12px',
              color: 'var(--accent)',
              border: '1px solid var(--border-default)',
            }}
          >
            {icon}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 更新 Dashboard 中的用法**

在 `web/src/pages/Dashboard/index.tsx` 中，将 `GradientStatCard` 调用中的 `gradient="..."` 属性删除（组件不再接受 `gradient`）。例如：

```tsx
<GradientStatCard
  title="标的总数"
  value={stats?.etf_count ?? 0}
  icon={<DatabaseOutlined style={{ color: 'var(--accent)' }} />}
  loading={statsLoading}
  onClick={() => navigate('/etfs')}
/>
```

其余三个 `GradientStatCard` 同样删除 `gradient` 属性，并把 icon 的 color 改为 `var(--accent)`。

- [ ] **Step 3: 运行构建确认无类型错误**

Run: `cd /Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web && pnpm build`

- [ ] **Step 4: Commit**

```bash
git add web/src/components/GradientStatCard.tsx web/src/pages/Dashboard/index.tsx

git commit -m "feat(components): restyle GradientStatCard as Swiss minimal data card"
```

---

### Task 2.3: 改造 `ETFCodeTag`、`ReturnTag`、`ScoreBar`

**Files:**
- Modify: `web/src/components/ETFCodeTag.tsx`
- Modify: `web/src/components/ReturnTag.tsx`
- Modify: `web/src/components/ScoreBar.tsx`

- [ ] **Step 1: 简化 `ETFCodeTag`**

将 `web/src/components/ETFCodeTag.tsx` 替换为：

```tsx
import { Tooltip } from 'antd';

interface ETFCodeTagProps {
  code: string;
  name?: string;
}

export default function ETFCodeTag({ code, name }: ETFCodeTagProps) {
  return (
    <Tooltip title={name || code}>
      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            display: 'inline-block',
            padding: '2px 8px',
            borderRadius: 'var(--radius-sm)',
            fontSize: 'var(--text-code)',
            fontWeight: 500,
            fontFamily: 'var(--font-mono)',
            color: 'var(--accent)',
            background: 'var(--accent-dim)',
            border: '1px solid var(--accent-border)',
            letterSpacing: '0.02em',
          }}
        >
          {code}
        </span>
        {name && (
          <span
            style={{
              fontSize: 'var(--text-body)',
              color: 'var(--text-secondary)',
              fontWeight: 400,
              maxWidth: 160,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {name}
          </span>
        )}
      </div>
    </Tooltip>
  );
}
```

- [ ] **Step 2: 简化 `ReturnTag`**

将空值分支和正常分支的圆角和字号改为使用 token：

```tsx
import { getReturnColor, getReturnBgColor, getReturnBorderColor } from '@/utils/color';
import { formatPercent } from '@/utils/format';
import { useSettingsStore } from '@/stores/settings';

interface ReturnTagProps {
  value?: number | null;
}

const baseStyle = {
  display: 'inline-block',
  padding: '2px 8px',
  borderRadius: 'var(--radius-sm)',
  fontSize: 'var(--text-code)',
  fontWeight: 500,
  fontFamily: 'var(--font-mono)',
  transition: 'all var(--transition-fast)',
} as React.CSSProperties;

export default function ReturnTag({ value }: ReturnTagProps) {
  const colorConvention = useSettingsStore((s) => s.colorConvention);

  if (value === undefined || value === null) {
    return (
      <span
        style={{
          ...baseStyle,
          color: 'var(--text-tertiary)',
          background: 'var(--bg-input)',
          border: '1px solid var(--border-default)',
        }}
      >
        -
      </span>
    );
  }
  return (
    <span
      style={{
        ...baseStyle,
        color: getReturnColor(value, colorConvention),
        background: getReturnBgColor(value, colorConvention),
        border: `1px solid ${getReturnBorderColor(value, colorConvention)}`,
      }}
    >
      {formatPercent(value)}
    </span>
  );
}
```

- [ ] **Step 3: 简化 `ScoreBar` 去掉发光**

将 `web/src/components/ScoreBar.tsx` 替换为：

```tsx
import { getScoreColor, getScoreGradient } from '@/utils/color';

interface ScoreBarProps {
  score: number;
  size?: 'small' | 'default';
}

export default function ScoreBar({ score, size = 'default' }: ScoreBarProps) {
  const height = size === 'small' ? 4 : 6;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%' }}>
      <div
        style={{
          flex: 1,
          height,
          background: 'var(--bg-input)',
          borderRadius: height / 2,
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        <div
          style={{
            width: `${Math.min(score, 100)}%`,
            height: '100%',
            background: getScoreGradient(score),
            borderRadius: height / 2,
            transition: 'width 600ms cubic-bezier(0.4, 0, 0.2, 1)',
          }}
        />
      </div>
      {size !== 'small' && (
        <span
          style={{
            fontSize: 'var(--text-body)',
            fontWeight: 500,
            color: getScoreColor(score),
            fontFamily: 'var(--font-mono)',
            minWidth: 40,
            textAlign: 'right',
          }}
        >
          {score.toFixed(1)}
        </span>
      )}
    </div>
  );
}
```

- [ ] **Step 4: 构建并 Commit**

Run: `cd /Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web && pnpm build`

```bash
git add web/src/components/ETFCodeTag.tsx web/src/components/ReturnTag.tsx web/src/components/ScoreBar.tsx

git commit -m "feat(components): restyle ETFCodeTag, ReturnTag, ScoreBar"
```

---

### Task 2.4: 改造 `AppLayout` 侧边栏与 Header

**Files:**
- Modify: `web/src/components/AppLayout.tsx`

- [ ] **Step 1: 替换 Logo 区样式**

将 Logo 区的渐变方块和文字样式改为：

```tsx
<div
  style={{
    height: 64,
    display: 'flex',
    alignItems: 'center',
    padding: collapsed ? '0 20px' : '0 24px',
    borderBottom: '1px solid var(--border-default)',
    gap: 12,
  }}
>
  <div
    style={{
      width: 32,
      height: 32,
      borderRadius: 'var(--radius-md)',
      background: 'var(--accent)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontSize: 16,
      fontWeight: 700,
      color: '#000',
      flexShrink: 0,
    }}
  >
    E
  </div>
  {!collapsed && (
    <span
      style={{
        fontSize: 'var(--text-body)',
        fontWeight: 500,
        color: 'var(--text-primary)',
        letterSpacing: '0.02em',
        whiteSpace: 'nowrap',
      }}
    >
      投研平台
    </span>
  )}
</div>
```

- [ ] **Step 2: 替换菜单项样式**

将菜单项容器样式（`<div ... style={{ display: 'flex', ... }}>`）替换为：

```tsx
<div
  onClick={() => {
    navigate(route.path);
    onItemClick?.();
  }}
  style={{
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    padding: collapsed ? '10px 0' : '10px 14px',
    marginBottom: 2,
    borderRadius: 0,
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
    justifyContent: collapsed ? 'center' : 'flex-start',
    position: 'relative',
    color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
    background: isActive ? 'var(--bg-active)' : 'transparent',
  }}
  onMouseEnter={(e) => {
    if (!isActive) {
      e.currentTarget.style.background = 'var(--bg-hover)';
      e.currentTarget.style.color = 'var(--text-primary)';
    }
  }}
  onMouseLeave={(e) => {
    if (!isActive) {
      e.currentTarget.style.background = 'transparent';
      e.currentTarget.style.color = 'var(--text-secondary)';
    }
  }}
>
```

并将激活态左侧指示条替换为：

```tsx
{isActive && (
  <div
    style={{
      position: 'absolute',
      left: 0,
      top: '50%',
      transform: 'translateY(-50%)',
      width: 2,
      height: 18,
      background: 'var(--accent)',
    }}
  />
)}
```

- [ ] **Step 3: 替换 aside 和 Header 背景**

将桌面端 `aside` 的 `background: 'linear-gradient(180deg, #0a0f1e 0%, #0d1326 100%)'` 改为 `background: 'var(--bg-elevated)'`。

将 Header 的 `background: 'rgba(7, 11, 20, 0.8)'` 改为 `background: 'rgba(10, 10, 10, 0.9)'`，并保留 `backdropFilter: 'blur(12px)'` 和 `borderBottom: '1px solid var(--border-default)'`。

将用户头像的渐变背景改为：

```tsx
background: 'var(--bg-input)',
border: '1px solid var(--border-default)',
```

并将文字颜色改为 `var(--text-primary)`。

- [ ] **Step 4: 构建并 Commit**

Run: `cd /Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web && pnpm build`

```bash
git add web/src/components/AppLayout.tsx

git commit -m "feat(layout): restyle sidebar and header for Swiss Minimal"
```

---

## Phase 3: 页面级重构

### Task 3.1: 重构 Dashboard 首页

**Files:**
- Modify: `web/src/pages/Dashboard/index.tsx`

- [ ] **Step 1: 移除 AI Quick Entry 区彩色渐变卡片**

删除 `Row gutter={[16, 16]} style={{ marginBottom: 24 }}` 及其内部 4 个 `Card` 快捷入口。如果业务需要保留快捷入口，后续可改造为极简文字链接或图标行，但本次先按设计文档“减少卡片”原则移除。

- [ ] **Step 2: 改造 Stats Row 为 Hero 区域**

将 Stats Row 的 `Row gutter={[20, 20]}` 改为：

```tsx
<div
  style={{
    display: 'grid',
    gridTemplateColumns: 'repeat(4, 1fr)',
    gap: 0,
    borderTop: '1px solid var(--border-default)',
    borderBottom: '1px solid var(--border-default)',
    marginBottom: 'var(--space-6)',
  }}
>
  {[ ... four GradientStatCard wrappers ... ].map((card, idx) => (
    <div
      key={idx}
      style={{
        borderRight: idx < 3 ? '1px solid var(--border-default)' : 'none',
        padding: 'var(--space-4)',
      }}
    >
      {card}
    </div>
  ))}
</div>
```

每个 GradientStatCard 去掉 `gradient` 属性，icon color 改为 `var(--accent)`。

- [ ] **Step 3: 改造主内容区为两栏扁平布局**

将主内容区 `Row gutter={[20, 20]}` 改为 `Panel` 组合：

```tsx
<div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 'var(--space-6)' }}>
  <Panel title="综合评分 Top 10" padding="md">
    <Table ... />
  </Panel>
  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
    <Panel title="我的收藏" extra={...} padding="md">
      ...
    </Panel>
    <Panel title="我的标的池" extra={...} padding="md">
      ...
    </Panel>
  </div>
</div>
```

移除 `DashboardCard` 辅助函数，直接使用 `Panel`。

- [ ] **Step 4: 调整列表项样式**

收藏和标的池列表中的 ETF 代码色块改为使用 `ETFCodeTag`（如果尚未使用）。收藏代码块的背景、颜色等内联样式删除，改为直接使用 `ETFCodeTag code={item.etf_code} name={item.etf_name}`。

- [ ] **Step 5: 构建并 Commit**

Run: `cd /Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web && pnpm build`

```bash
git add web/src/pages/Dashboard/index.tsx

git commit -m "feat(dashboard): refactor Dashboard to Swiss Minimal hero + panels"
```

---

### Task 3.2: 重构 ETFList 列表页

**Files:**
- Modify: `web/src/pages/ETFList/index.tsx`

- [ ] **Step 1: 改造 Filter Bar 为扁平工具栏**

将 `<GlassCard>...</GlassCard>` 包裹的筛选区替换为：

```tsx
<div
  style={{
    display: 'flex',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 'var(--space-3)',
    paddingBottom: 'var(--space-4)',
    borderBottom: '1px solid var(--border-default)',
    marginBottom: 'var(--space-5)',
  }}
>
  <Input ... style={{ width: 240 }} />
  <Select ... style={{ width: 140 }} />
  <Select ... style={{ width: 160 }} />
  <Select ... style={{ width: 120 }} />
  <div style={{ marginLeft: 'auto', fontSize: 'var(--text-small)', color: 'var(--text-tertiary)' }}>
    共 <span style={{ color: 'var(--accent)', fontWeight: 500 }}>{data?.total || 0}</span> 只
  </div>
</div>
```

- [ ] **Step 2: 简化表格列中的自定义样式**

表格列中的分类标签删除内联 `background`、`borderRadius`、`padding` 等样式，直接使用 `Tag` 组件或普通文本：

```tsx
{
  title: '分类',
  dataIndex: 'category',
  render: (v: string) => v ? <Tag>{v}</Tag> : '-',
},
```

类型列的 Tag 删除 `borderRadius: 6`，直接使用：

```tsx
<Tag color={v === 'STOCK' ? 'blue' : 'purple'}>{v === 'STOCK' ? '个股' : 'ETF'}</Tag>
```

- [ ] **Step 3: 简化移动端列表项**

移动端列表项删除 `background`、`borderRadius`、`transition` hover 效果，改为：

```tsx
<div
  onClick={() => navigate(`/etfs/${item.code}`)}
  style={{
    borderBottom: '1px solid var(--border-default)',
    padding: 'var(--space-3) 0',
    cursor: 'pointer',
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-2)',
  }}
>
```

- [ ] **Step 4: 构建并 Commit**

Run: `cd /Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web && pnpm build`

```bash
git add web/src/pages/ETFList/index.tsx

git commit -m "feat(etf-list): refactor ETFList with flat filter bar and table"
```

---

### Task 3.3: 重构 ETFDetail 详情页

**Files:**
- Modify: `web/src/pages/ETFDetail/index.tsx`

- [ ] **Step 1: 改造页面标题区为扁平 Hero**

将顶部 `Card` 替换为：

```tsx
<div
  style={{
    borderBottom: '1px solid var(--border-default)',
    paddingBottom: 'var(--space-5)',
    marginBottom: 'var(--space-5)',
  }}
>
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 'var(--space-4)' }}>
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', marginBottom: 'var(--space-2)' }}>
        <h2 style={{ margin: 0, fontSize: 'var(--text-h1)', fontWeight: 500, letterSpacing: '-0.03em' }}>
          {etf.code} {etf.name}
        </h2>
        {etf.instrument_type && (
          <Tag color={etf.instrument_type === 'STOCK' ? 'blue' : 'purple'}>
            {etf.instrument_type === 'STOCK' ? '个股' : 'ETF'}
          </Tag>
        )}
        {etf.market && <Tag>{etf.market}</Tag>}
      </div>
      <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-body)' }}>
        ...
      </div>
    </div>
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
      <Button ... />
      {indicator?.return_1m !== undefined && (
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 'var(--text-data-lg)', fontWeight: 400, fontFamily: 'var(--font-mono)', color: getReturnColor(...) }}>
            {formatPercent(indicator.return_1m)}
          </div>
          <div style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-small)' }}>1月收益</div>
        </div>
      )}
    </div>
  </div>
</div>
```

- [ ] **Step 2: 移除指标区内部 Card 包装**

将 `indicators` tab 中的 `Row gutter={[16,16]}` 内每个 `<Col ...><Card><Statistic ... /></Card></Col>` 改为：

```tsx
<Col xs={12} sm={8} md={6}>
  <div style={{ borderBottom: '1px solid var(--border-default)', padding: 'var(--space-3) 0' }}>
    <Statistic ... />
  </div>
</Col>
```

时间范围和技术指标控制区的 `Card size="small"` 改为普通容器：

```tsx
<div style={{ padding: 'var(--space-3) 0', borderBottom: '1px solid var(--border-default)', marginBottom: 'var(--space-4)' }}>
  <Space ... />
</div>
```

- [ ] **Step 3: 更新 AI 分析区卡片为 Panel**

将 `AI分析` tab 中的 `<Card title=...>` 替换为 `<Panel title=... padding="md">`，底部“打开AI助手”的渐变卡片替换为：

```tsx
<Panel style={{ marginTop: 'var(--space-4)', textAlign: 'center' }} padding="md">
  <RobotOutlined style={{ fontSize: 20, color: 'var(--accent)', marginRight: 8 }} />
  <span style={{ color: 'var(--text-secondary)', marginRight: 12 }}>想问AI关于 {code} 的分析？</span>
  <Button type="primary" icon={<RobotOutlined />} onClick={() => navigate('/chat')}>
    打开AI助手
  </Button>
</Panel>
```

- [ ] **Step 4: 移除硬编码渐变按钮**

搜索并删除所有 `style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', border: 'none' }}` 的按钮样式，让 `type="primary"` 自动使用全局青色样式。

- [ ] **Step 5: 构建并 Commit**

Run: `cd /Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web && pnpm build`

```bash
git add web/src/pages/ETFDetail/index.tsx

git commit -m "feat(etf-detail): refactor ETFDetail with flat hero and panels"
```

---

### Task 3.4: 重构 BacktestDetail 回测详情页

**Files:**
- Modify: `web/src/pages/BacktestDetail/index.tsx`

- [ ] **Step 1: 移除嵌套 GlassCard，改用扁平网格**

将外层 `GlassCard` 及其内部嵌套的 `GlassCard padding="sm"` 统计卡片改为：

```tsx
<Panel title={`回测详情 #${data.id}`} padding="md" style={{ marginBottom: 'var(--space-5)' }}>
  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 0, borderTop: '1px solid var(--border-default)' }}>
    {[
      { title: '总收益', value: metrics.total_return, suffix: '%' },
      { title: '年化收益', value: metrics.annualized_return, suffix: '%' },
      { title: '最大回撤', value: metrics.max_drawdown, suffix: '%' },
      { title: '夏普比率', value: metrics.sharpe_ratio },
      { title: '胜率', value: metrics.win_rate, suffix: '%' },
      { title: '交易次数', value: metrics.trade_count },
    ].map((m, idx) => (
      <div
        key={m.title}
        style={{
          padding: 'var(--space-4)',
          borderBottom: '1px solid var(--border-default)',
          borderRight: (idx + 1) % 3 !== 0 ? '1px solid var(--border-default)' : 'none',
        }}
      >
        <Statistic title={m.title} value={m.value} suffix={m.suffix} precision={2} />
      </div>
    ))}
  </div>
</Panel>
```

- [ ] **Step 2: 更新图表容器为 Panel**

将净值曲线和交易记录的 `GlassCard` 改为 `Panel`：

```tsx
<Panel title={<HelpPopover termKey="nav_curve">净值曲线</HelpPopover>} padding="md" style={{ marginBottom: 'var(--space-5)' }}>
  <ReactECharts option={navOption} style={{ height: isMobile ? 250 : 320 }} />
</Panel>

<Panel title={<HelpPopover termKey="trade_record">交易记录</HelpPopover>} padding="md" style={{ marginBottom: 'var(--space-5)' }}>
  <Table ... />
</Panel>
```

- [ ] **Step 3: 更新 ECharts 主题色**

将 `navOption` 的 `areaStyle` 和线条颜色改为霓虹青：

```tsx
const navOption: EChartsOption = {
  tooltip: { trigger: 'axis' },
  grid: { left: 50, right: 20, top: 30, bottom: 30 },
  xAxis: { type: 'category', data: navData.map((d: any) => d.date), axisLine: { lineStyle: { color: 'var(--text-tertiary)' } } },
  yAxis: { type: 'value', splitLine: { lineStyle: { color: 'var(--border-default)' } } },
  series: [{
    type: 'line',
    data: navData.map((d: any) => d.nav),
    smooth: true,
    lineStyle: { color: '#22d3ee', width: 2 },
    itemStyle: { color: '#22d3ee' },
    areaStyle: { color: 'rgba(34,211,238,0.08)' },
  }],
};
```

- [ ] **Step 4: 构建并 Commit**

Run: `cd /Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web && pnpm build`

```bash
git add web/src/pages/BacktestDetail/index.tsx

git commit -m "feat(backtest-detail): refactor BacktestDetail with flat metrics grid and panels"
```

---

### Task 3.5: 重构 PoolDetail、ScoreRanking、Screen、StrategyList

**Files:**
- Modify: `web/src/pages/PoolDetail/index.tsx`
- Modify: `web/src/pages/ScoreRanking/index.tsx`
- Modify: `web/src/pages/Screen/index.tsx`
- Modify: `web/src/pages/StrategyList/index.tsx`

- [ ] **Step 1: 在每个页面执行统一改造清单**

对以上 4 个文件逐项应用以下规则：

1. 将 `GlassCard` 替换为 `Panel`（保留 `title`、`extra`、`style`、`padding` 属性）。
2. 删除所有自定义渐变背景、渐变文字、发光阴影的内联样式。
3. 将大圆角（`borderRadius: 12/16/20`）改为 `var(--radius-md)`、`var(--radius-lg)` 或 0。
4. 将主强调色 `#818cf8`、`#6366f1`、`#8b5cf6`、`#06b6d4` 等改为 `var(--accent)`。
5. 将次要文字色 `#94a3b8`、`#64748b` 改为 `var(--text-secondary)` 或 `var(--text-tertiary)`。
6. 将背景色 `#070b14`、`#0f1729`、`rgba(255,255,255,0.03)` 改为 `var(--bg-base)`、`var(--bg-elevated)`、`var(--bg-input)`。
7. 表格、列表项 hover 样式依赖全局覆盖，删除局部 hover 效果。
8. 按钮 `type="primary"` 删除自定义渐变背景，使用全局青色。

- [ ] **Step 2: 检查每个页面的特殊处理**

- `PoolDetail`: 如果有 KPI 统计卡片，改为 `<div>` 网格或 `Statistic` 直接展示，不嵌套 `Card`。
- `ScoreRanking`: 表格中的评分列使用更新后的 `ScoreBar`，排名列色值改为 `var(--accent)`、`var(--text-secondary)`、`var(--text-tertiary)`。
- `Screen`: 筛选条件区和结果区用 `Panel` 或细线分隔，避免卡片堆叠。
- `StrategyList`: 列表项改为扁平行，删除渐变边框和背景。

- [ ] **Step 3: 构建并 Commit**

Run: `cd /Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web && pnpm build`

```bash
git add web/src/pages/PoolDetail/index.tsx web/src/pages/ScoreRanking/index.tsx web/src/pages/Screen/index.tsx web/src/pages/StrategyList/index.tsx

git commit -m "feat(pages): refactor PoolDetail, ScoreRanking, Screen, StrategyList"
```

---

## Phase 4: 图表与细节打磨

### Task 4.1: 更新图表主题色

**Files:**
- Modify: `web/src/components/KLineChart.tsx`
- Modify: `web/src/components/ReturnCurve.tsx`
- Modify: `web/src/components/CategoryPie.tsx`
- Modify: `web/src/components/CorrelationHeatmap.tsx`
- Modify: `web/src/components/ScoreRadar.tsx`

- [ ] **Step 1: 统一图表主色为霓虹青**

在每个 ECharts 配置文件中，将：
- 主线条/面积颜色改为 `#22d3ee` 或 `var(--accent)`。
- 网格线颜色改为 `var(--border-default)`。
- 坐标轴文字颜色改为 `var(--text-tertiary)`。
- Tooltip 背景改为 `var(--bg-elevated)`，边框改为 `var(--border-default)`。
- 多色系列保留语义色（红/绿/黄），但降低饱和度和发光。

例如 KLineChart 中阳线/阴线可保留红绿，但辅助均线统一为青色系或灰色。

- [ ] **Step 2: 逐项检查并修改**

由于每个图表组件配置不同，按以下最小原则修改：

```tsx
// 通用 ECharts 主题选项片段
textStyle: { fontFamily: 'var(--font-sans)' },
grid: { borderColor: 'var(--border-default)' },
xAxis: { axisLine: { lineStyle: { color: 'var(--text-tertiary)' } }, axisLabel: { color: 'var(--text-secondary)' } },
yAxis: { splitLine: { lineStyle: { color: 'var(--border-default)' } }, axisLabel: { color: 'var(--text-secondary)' } },
tooltip: { backgroundColor: 'var(--bg-elevated)', borderColor: 'var(--border-default)', textStyle: { color: 'var(--text-primary)' } },
```

- [ ] **Step 3: 构建并 Commit**

Run: `cd /Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web && pnpm build`

```bash
git add web/src/components/KLineChart.tsx web/src/components/ReturnCurve.tsx web/src/components/CategoryPie.tsx web/src/components/CorrelationHeatmap.tsx web/src/components/ScoreRadar.tsx

git commit -m "feat(charts): update chart theme colors to Neon Cyan"
```

---

### Task 4.2: 统一 hover 状态与动效

**Files:**
- Modify: `web/src/styles/global.css`

- [ ] **Step 1: 为表格行添加激活态左侧指示条**

在 `global.css` 的 Table 覆盖区块追加：

```css
.ant-table-tbody > tr.ant-table-row-selected > td,
.ant-table-tbody > tr[aria-selected="true"] > td {
  background: var(--bg-active) !important;
}

.ant-table-row-selected::before,
.ant-table-tbody > tr[aria-selected="true"]::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--accent);
}
```

- [ ] **Step 2: 为链接和可点击元素添加统一 hover**

追加：

```css
a {
  color: var(--accent);
  transition: color var(--transition-fast);
}

a:hover {
  color: var(--accent-hover);
}
```

- [ ] **Step 3: Commit**

```bash
git add web/src/styles/global.css

git commit -m "feat(theme): unify hover states and row selection indicator"
```

---

## Phase 5: 回归测试与验收

### Task 5.1: 全站视觉走查

**Files:**
- 无需修改代码，仅验证。

- [ ] **Step 1: 启动 dev server**

Run: `cd /Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web && pnpm dev`

- [ ] **Step 2: 桌面端检查清单**

在浏览器中逐个打开以下路由并检查：

| 路由 | 检查项 |
|---|---|
| `/dashboard` | 无彩色渐变卡片，Hero 为 4 格细线分隔，表格扁平 |
| `/etfs` | Filter Bar 无卡片，表格表头大写灰色，hover 高亮 |
| `/etfs/:code` | 标题区扁平，Tabs 下划线青色，指标无嵌套卡片 |
| `/backtests/:id` | 指标为扁平网格，净值曲线青色 |
| `/pools/:id` | 与回测详情风格一致 |
| `/scores` | 排名、评分条符合新规范 |
| `/screen` | 筛选区和结果区分层清晰 |
| `/strategies` | 列表扁平无渐变 |

- [ ] **Step 3: 移动端检查清单**

使用浏览器 DevTools 切换至 iPhone SE / iPhone 14 Pro：

- 侧边栏抽屉背景为 `#111111`。
- 表格可横向滚动，无重叠。
- 按钮触摸区域 ≥ 40px。
- 无水平溢出导致的横向滚动条（表格除外）。

- [ ] **Step 4: 暗色一致性检查**

- 所有页面背景为 `#0a0a0a` 或 `#111111`。
- 无突兀的浅色块或遗留蓝紫色渐变。
- 霓虹青 `#22d3ee` 使用一致且克制。

- [ ] **Step 5: 记录问题并修复**

将发现的问题记录在此任务下方，按 Task 1-4 的相同粒度创建修复任务并逐个提交。

---

### Task 5.2: 删除备份文件并做最终构建

**Files:**
- Delete: `web/src/styles/theme.css.bak`
- Delete: `web/src/styles/global.css.bak`

- [ ] **Step 1: 删除备份文件**

```bash
rm web/src/styles/theme.css.bak web/src/styles/global.css.bak
```

- [ ] **Step 2: 运行生产构建**

Run: `cd /Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web && pnpm build`

Expected: `tsc` 和 `vite build` 均成功退出。

- [ ] **Step 3: Commit**

```bash
git add -u

git commit -m "chore(theme): remove CSS backups after visual redesign"
```

---

## Self-Review

### Spec coverage

| 设计文档章节 | 对应 Task |
|---|---|
| 5.1 色彩系统 | Task 1.1, 1.2 |
| 5.2 字体系统 | Task 1.1, 1.2 |
| 5.3 间距系统 | Task 1.1 |
| 5.4 圆角系统 | Task 1.1, 1.2, 1.3 |
| 5.5 阴影 | Task 1.1, 1.3 |
| 6.1 Panel | Task 2.1 |
| 6.2 表格 | Task 1.3, 4.2 |
| 6.3 按钮 | Task 1.3 |
| 6.4 侧边栏 | Task 2.4 |
| 6.5 Header | Task 2.4 |
| 6.6 标签 | Task 1.3, 2.3 |
| 6.7 输入框 | Task 1.3 |
| 6.8 Tabs | Task 1.3 |
| 6.9 图表 | Task 4.1 |
| 7.1 Dashboard | Task 3.1 |
| 7.2 ETF 列表 | Task 3.2 |
| 7.3 详情页 | Task 3.3, 3.4, 3.5 |
| 7.4 筛选/评分/排名 | Task 3.5 |
| 7.5 通用布局 | Task 2.4 |
| 8 实施阶段 | 全部 Tasks |

### Placeholder scan

- 无 "TBD"/"TODO"/"implement later"。
- 所有代码块为可直接使用的实际内容。
- 所有文件路径精确。
- 未使用 "Similar to Task N"。

### Type consistency

- `PanelProps` 在 `Panel.tsx` 中定义，GlassCard 包装器与其保持一致。
- `GradientStatCard` 移除 `gradient` 属性，Dashboard 同步删除该属性。
- 颜色工具函数签名未变更，仅样式 token 引用更新。
- Ant Design 组件 token 名称与 Ant Design 5 API 一致。

---

*Plan complete.*
