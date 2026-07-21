# 前端视觉重构 Phase 2 — 共享组件改造 + 6 个新组件

> **注**：本文为 2026-07-05 的时点记录，部分内容可能已过时（如 `global.css` 已拆分为 `web/src/styles/global/` 目录、文中行号引用已失效，以代码现状为准）。

**日期**：2026-07-05
**分支**：`main`
**前置 commit**：`22034b9` (Phase 1 — design tokens + 朱色 #E11D48 + light clean 默认)
**后续 Phase**：3 (AppLayout) / 4 (Dashboard + 高频列表) / 5 (详情 + 工具/报告/AI/策略/交易) / 6 (管理页 + inline style 收尾)

---

## 背景

Phase 1 已建立完整的 design token 系统（朱色 `#E11D48`、light/dark 双主题、
China/US 涨颜色约定切换、CSS 变量化的字号 / 间距 / 圆角 / 阴影 / 行高）。

Phase 2 负责**共享组件层**：把 7 个已有组件统一对齐 token，新增 6 个高频复用
组件作为 Phase 4/5 的页面构建块。本 Phase **不触碰** `global.css` / `AppLayout.tsx` /
任何 `pages/**` 文件 — 那些是 Phase 1/3/4/5/6 的工作面。

---

## 改造 7 个现有共享组件（API 保持不变）

| 文件 | 改动要点 |
|---|---|
| `web/src/components/Panel.tsx` | 重写 className 组装逻辑（去掉 `data-glass-padding` legacy），统一注释头说明 token 策略；API 不变 (`title` / `extra` / `padding` / `variant` / `className` / `style`)。 |
| `web/src/components/PageHeader.tsx` | 微调注释与 import 顺序；`eyebrow` / `title` / `description` / `extra` / `compact` / `tutorial` 全部走 CSS class (`.page-header-eyebrow` 等)，对应 CSS 已经用 `--text-h1-size` / `--space-5` / `--text-body-size` 等 token。 |
| `web/src/components/StatCard.tsx` | 注释更新，明确"hover 用 `.stat-card:hover` CSS 实现，不再走 `onMouseEnter/Leave` DOM 操作"；审计确认组件内已无 mouse handler。 |
| `web/src/components/ReturnTag.tsx` | 注释说明 China/US 颜色约定切换逻辑；颜色全部走 `var(--color-rise)` / `var(--color-fall)`，light/dark + 红涨/绿涨自动跟随。 |
| `web/src/components/ThemeTag.tsx` | className 组装改用 `.filter(Boolean).join(' ')`；注释补充"全部 token 化"说明；`style` 透传保留以兼容未来动态覆盖。 |
| `web/src/components/InstrumentCodeTag.tsx` | 仅补注释；代码本身已 token 化（`--accent` / `--accent-dim` / `--accent-border` 等）。 |
| `web/src/components/TickerTape.tsx` | 注释说明 Phase 2 把高度降到 32px、去掉重边框；唯一 inline `style={{ animationDuration }}` 是 prop 驱动（`durationSeconds`），按 plan 允许保留为动态值。 |

### 审计结果

```bash
$ grep -nE "#[0-9a-fA-F]{3,8}|rgba?\(" \
    web/src/components/{Panel,PageHeader,StatCard,ReturnTag,ThemeTag,InstrumentCodeTag,TickerTape,PageShell,FilterToolbar,ResponsiveGrid,ContentCard,EmptyState,SectionHeading}.tsx
# → 无匹配（13 个文件零硬编码 hex / rgba）

$ grep -nE "fontSize:\s*['\"][0-9]+px|width:\s*['\"][0-9]+px|height:\s*['\"][0-9]+px|padding:\s*['\"][0-9]+px|margin:\s*['\"][0-9]+px" \
    web/src/components/{Panel,PageHeader,StatCard,ReturnTag,ThemeTag,InstrumentCodeTag,TickerTape,PageShell,FilterToolbar,ResponsiveGrid,ContentCard,EmptyState,SectionHeading}.tsx
# → 无匹配（13 个文件零硬编码 px 数值）

$ grep -nE "onMouseEnter|onMouseLeave|data-glass" \
    web/src/components/{Panel,PageHeader,StatCard,ReturnTag,ThemeTag,InstrumentCodeTag,TickerTape}.tsx
# → 无匹配（无 legacy mouse handler / glass-padding 残留）
```

唯一一处 inline `style` 是 `TickerTape.tsx` 的 `animationDuration` —
prop 驱动的动态值，按 Phase 2 plan "能保留真正动态值" 的约定保留。

---

## 新增 6 个共享组件

| 文件 | 用途 | 关键 API |
|---|---|---|
| `web/src/components/PageShell.tsx` | 页面内容包装，控制响应式 padding + 可选 max-width（`reading` 720px / `wide` 1280px / `full` 100%） | `<PageShell maxWidth="reading\|wide\|full" className>{children}</PageShell>` |
| `web/src/components/FilterToolbar.tsx` | 标准化搜索/筛选/操作/结果数工具条，移动端自动全宽堆叠 | `<FilterToolbar total={123} extra={...}>{leftFilters}</FilterToolbar>` |
| `web/src/components/ResponsiveGrid.tsx` | 响应式 CSS grid helper，1/2/3/4 列自动在 576/992px 折叠 | `<ResponsiveGrid cols={4} gap="md">{children}</ResponsiveGrid>` |
| `web/src/components/ContentCard.tsx` | 薄封装 antd `Card`，统一新 padding (`--space-4 --space-5`)、圆角 (`--card-radius`)、hover 阴影 | `<ContentCard title="..." extra={...}>{children}</ContentCard>` |
| `web/src/components/EmptyState.tsx` | 可复用空状态（虚线边框 + `--bg-elevated` 背景 + 居中三段式：icon / title / description / action） | `<EmptyState icon={...} title="..." description="..." action={...} />` |
| `web/src/components/SectionHeading.tsx` | 小节标题（可选 eyebrow + title + action），与 PageHeader 配套用于页面内分块 | `<SectionHeading eyebrow="..." title="..." action={...} />` |

### 使用示例

```tsx
// 标准列表页模板
<PageShell maxWidth="wide">
  <PageHeader
    eyebrow="ETF投研"
    title="评分排名"
    description="查看全市场标的综合评分排名"
    extra={<Button type="primary">导出</Button>}
  />
  <FilterToolbar total={ranking.length} extra={<DensityToggle />}>
    <Input.Search placeholder="搜索代码或名称" />
    <Select placeholder="类型" options={typeOptions} />
  </FilterToolbar>
  <ResponsiveGrid cols={4} gap="md">
    {ranking.map((r) => <StatCard key={r.code} title={r.name} value={r.score} />)}
  </ResponsiveGrid>
</PageShell>

// 详情页读型布局
<PageShell maxWidth="reading">
  <PageHeader title="研报笔记" />
  <ContentCard title="摘要" extra={<Tag>2026Q2</Tag>}>
    <Markdown source={report.body} />
  </ContentCard>
  <SectionHeading eyebrow="市场行情" title="相关标的" action={<a>查看更多</a>} />
  <ResponsiveGrid cols={3} gap="md">{/* ... */}</ResponsiveGrid>
</PageShell>

// 空状态
<EmptyState
  icon={<InboxOutlined />}
  title="暂无数据"
  description="尝试调整筛选条件或稍后再来"
  action={<Button onClick={refetch}>重新加载</Button>}
/>
```

### 已被 Phase 4/5 之前的页面使用（验收佐证）

```bash
$ grep -rn "from '@/components/PageShell'\|from '@/components/FilterToolbar'\|from '@/components/ResponsiveGrid'\|from '@/components/SectionHeading'\|from '@/components/EmptyState'" web/src/pages/
web/src/pages/BacktestDetail/index.tsx
web/src/pages/ReturnComparison/index.tsx
web/src/pages/SectorRotation/index.tsx
web/src/pages/Microstructure/index.tsx
# ... 等等
```

> 说明：这 6 个新组件是 Phase 1 commit 中已落地的（CSS 与 TSX 文件都已在仓库），
> Phase 2 的工作是 **确认 API 与 token 对齐 + 编写本 dev-note**。Phase 4/5 已经在引用。

---

## 验证

| 验证项 | 命令 | 结果 |
|---|---|---|
| TypeScript 类型检查 | `cd web && npx tsc --noEmit` | `EXIT=0`（零错误）|
| 生产构建 | `cd web && npm run build` | `EXIT=0`，产物正常输出到 `dist/` |
| 硬编码 hex/rgba 审计 | grep 13 个文件 | 零匹配 |
| 硬编码 px 数值审计 | grep 13 个文件 | 零匹配 |
| Legacy `data-glass-padding` / `onMouseEnter` 审计 | grep 7 个改造组件 | 零匹配 |
| 主题切换（light ↔ dark） | 由 `var(--xxx)` token 自动跟随 | 通过（CSS 在 `theme.css:209` `:root[data-theme="dark"]` 中覆盖） |
| China/US 涨颜色约定切换 | 由 `var(--color-rise/fall)` + `useSettingsStore.colorConvention` 驱动 | 通过（CSS 在 `theme.css:184` `:root[data-color-convention="us"]` 中覆盖） |

---

## Phase 2 触及的文件清单（13 个）

```
web/src/components/Panel.tsx              (重写 className 组装 + 注释)
web/src/components/PageHeader.tsx         (注释 + import 顺序整理)
web/src/components/StatCard.tsx           (注释 + 审计确认 CSS hover)
web/src/components/ReturnTag.tsx          (注释 + 注释 China/US 切换)
web/src/components/ThemeTag.tsx           (className 整理 + 注释)
web/src/components/InstrumentCodeTag.tsx  (注释)
web/src/components/TickerTape.tsx         (注释 + 注释 Phase 2 调整)
web/src/components/PageShell.tsx          (API 锁定，无改动)
web/src/components/FilterToolbar.tsx      (API 锁定，无改动)
web/src/components/ResponsiveGrid.tsx     (API 锁定，无改动)
web/src/components/ContentCard.tsx        (API 锁定，无改动)
web/src/components/EmptyState.tsx         (API 锁定，无改动)
web/src/components/SectionHeading.tsx     (API 锁定，无改动)
```

## 未触碰的文件（按 plan 约束）

- ❌ `web/src/styles/theme.css`（Phase 1 已 commit）
- ❌ `web/src/styles/global.css`（Phase 6 收尾）
- ❌ `web/src/main.tsx`（Phase 1 已 commit）
- ❌ `web/src/hooks/useTheme.ts`（Phase 1 已 commit）
- ❌ `web/src/components/AppLayout.tsx`（Phase 3 改）
- ❌ 所有 `web/src/pages/**/*.tsx`（Phase 4/5 改）

---

## Phase 3/4/5 接力要点

1. **统一使用 `PageShell` 包页面**：
   - Dashboard 类 → `maxWidth="wide"`
   - 详情 / 报告 / AI 笔记 → `maxWidth="reading"`
2. **Dashboard 网格**：所有 `repeat(4, 1fr)` 改为 `<ResponsiveGrid cols={4}>`，
   自动在 768px 折 2 列、375px 折 1 列。
3. **列表页**：`<PageHeader>` + `<FilterToolbar>` + `<ResponsiveGrid>` 三件套。
4. **涨跌幅**：直接用 `<ReturnTag>` 或 `<ThemeTag variant="rise|fall">`，
   不要自己写 `style={{ color: ... }}`。
5. **空状态**：所有"暂无数据"页面用 `<EmptyState>` 替代 antd `Empty` 包装。

---

## 后续建议（Phase 6+）

- 清理 `global.css` 中仍存在的 `glass-card[data-glass-padding=...]` legacy 块（lines 599-616），
  已被新组件完全替代，可直接删除。
- 检查是否还有页面仍在 `style={{ color: 'red' }}` 这种硬编码颜色 — Phase 6 grep 审计目标。
- 给新组件补 Storybook（如果有 storybook 配置）。