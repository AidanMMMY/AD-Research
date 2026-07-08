# AD-Research UI/UX 现代化方案 — 现场诊断 + 点子库 + 实施计划

> 编制日期: 2026-07-08
> 角色: UI/UX 顾问 (不出手改代码，只出方案)
> 参考基准: Linear · Notion · Vercel · Stripe · Anthropic 网站
> 定位: 在不破坏 light clean (朱色 #E11D48) 主题、不动 dark theme、不破坏现有数据契约的前提下，做"小改动、大效果"的精致化

---

## Part 1 — 现场诊断

### 1.1 已读文件清单

| 文件 | 行数 | 关键观察 |
|---|---|---|
| `web/src/pages/Dashboard/index.tsx` | 845 | 看板主体结构，8 个 section，全球速览 / KPI / 一课 / 健康度 / 行情 / 资讯 / 评分 / 自选 |
| `web/src/styles/theme.css` | 487 | Token 系统完整: bg/text/border/shadow/space/radius/typography 都已定义 |
| `web/src/styles/global.css` | 8101 | Ant Design 主题覆盖 + Phase 2/3/4/5 组件库 (Panel/StatCard/Sparkline/TickerTape 等) |
| `web/src/components/AppLayout.tsx` | 765 | 侧栏 (240/72) + sticky header + 移动端 drawer + 面包屑 + 学习模式开关 |
| `web/src/components/Panel.tsx` | 57 | 轻量封装，3 variant × 4 padding |
| `web/src/components/StatCard.tsx` | 62 | KPI 卡，CSS-only hover，含 StatExplainer (K15) |
| `web/src/components/PageShell.tsx` | 27 | max-width 3 档 |
| `web/src/components/PageHeader.tsx` | 75 | eyebrow / title / description / extra / breadcrumb / tutorial |
| `web/src/components/EmptyState.tsx` | 27 | icon + title + description + action |
| `web/src/components/Sparkline.tsx` | 142 | 80×20 迷你折线，自带涨/跌方向三角标记 |
| `web/src/components/ReturnTag.tsx` | 51 | rise/fall 胶囊，跟随 China/US 颜色约定 |
| `web/src/components/StatExplainer.tsx` | 76 | K15 学习模式 explainer，hover/click 弹气泡 |

### 1.2 当前架构亮点 (不能丢)

1. **Token 化彻底** — 颜色 / 间距 / 圆角 / 字号 / 阴影全走 CSS 变量，新增效果只需扩展 token。
2. **light/dark 双主题 + 红涨/绿涨双约定** — 用 `<html data-theme>` / `data-color-convention` 切换，已是 Linear 级别做法。
3. **统一的 Panel/PageShell/PageHeader** — Phase 2/3/4 已收敛出"卡片 + 容器 + 页头"三层结构。
4. **密度三档 + Ant Design 兼容** — 表格 + 表单的密度可调 (dense/comfortable/spacious)。
5. **学习模式 / 新手引导 / K15 StatExplainer** — 信息架构做得很深。

### 1.3 现状里"差一口气"的 10 个具体位置

按视觉冲击从大到小排序:

| # | 位置 (代码锚点) | 现状 | 缺什么 |
|---|---|---|---|
| 1 | `.dashboard-index-card` 顶部 + 底部 + 价格 (`global.css:3640-3695`) | 大白卡只有 6×6 灰圆点表示连接，价格用 24px mono 直出 | 缺 **轻量视觉锚点** — 顶部 1px 朱色线 / 价格区极淡 radial 渐变背景 / 价格变化方向的细微色条 |
| 2 | `.stat-card:hover` (`global.css:2031-2036`) | 只改 border + bg + box-shadow | 缺 **1px translateY(-1px) + 极淡 accent 描边** — Linear 风格的"卡片抬升" |
| 3 | `.dashboard-news-row` 顶部 (`global.css:3916+`) | 整行作为点击区，但 hover 时只有 `bg-hover`，无视觉锚点 | 缺 **左侧 2px accent 滑入条 + 字色渐亮** |
| 4 | Sparkline (80×20, 1.25px stroke) (`Sparkline.tsx`) | 单线 1.25px，无 fill | 缺 **下方 8-12px 渐隐面积** — 增加视觉重量，更现代 |
| 5 | Section 之间的间距 (`.dashboard-section` = 32px) (`global.css:3613`) | 全靠 margin 间隔 | 缺 **section heading 上方一条 24px 渐隐 hairline** — 让章节有"换气感" |
| 6 | Stat card 数值 (`stat-card__value`) | 改值时直接重渲染，无动效 | 缺 **150ms 数字淡入 + 上推 2px** — 进入感 |
| 7 | Ant Table 表头 (`global.css:86-95`) | uppercase, letter-spacing 0.12em, 11px | 太克制；缺 **sticky 表头 + 极淡 bg-elevated 底色** — 与正文明暗对比 |
| 8 | Button 涟漪 (`ant-btn-primary`) (`global.css:233-243`) | hover 时只有 box-shadow 16px accent-glow | 缺 **按下时 scale(0.97) + 内层 highlight** — Material/Tailwind UI 都有 |
| 9 | EmptyState icon 32px (`global.css:2536-2540`) | 单图标 + 1em 字号 | 缺 **48-56px 图标 + 16px 极淡 accent ring** — 让空状态"被看见" |
| 10 | PageHeader eyebrow (`global.css:637-644`) | uppercase 11px 朱灰色，字间距 0.12em | 缺 **左侧 3px × 12px 朱色色块** 当 anchor — Linear/Notion 都这么做 |
| 11 | (额外) 全局缺 **路由切换淡入** | 路由之间直接切换 | 缺 **120-180ms cross-fade** |

---

## Part 2 — 点子库 (10 条)

### Idea 1 · 卡片"线性抬升" (Card Elevation Lift)

- **现状**: `.stat-card:hover` 只切换 border/bg/shadow，没有位移。
- **改进**: 增加 `transform: translateY(-1px)`，配合 `--shadow-card-hover` 提升；同时给可点击卡片左侧加 2px 朱色 inset shadow（默认透明，hover 时滑入）。
- **预期效果**: 卡片"活起来"，鼠标进入有"被邀请"的感觉，与 Linear/Vercel 卡片一致。
- **工作量**: 小 (15 行 CSS)
- **风险**: 极低；只需在 `.stat-card--clickable` 子集生效，不影响普通 panel。
- **位置**: `web/src/styles/global.css` 第 2027-2036 行。

### Idea 2 · Sparkline 加"渐隐面积" (Sparkline Area Fill)

- **现状**: Sparkline 是 80×20 单线，无 fill，视觉重量轻。
- **改进**: 在 line 下方画一个同 path 的 closed polygon，fill 用 `linear-gradient(to bottom, ${stroke} 30%, transparent)`，opacity 0.18。
- **预期效果**: 像 TradingView / Robinhood 的迷你 sparkline，"涨/跌"一眼看出。
- **工作量**: 小 (改 `Sparkline.tsx` 加 1 个 `<path fill="url(#sparkGrad-${id})">` 和 `<defs>`)
- **风险**: 极低；纯 SVG，dark/light 都跟 token。
- **位置**: `web/src/components/Sparkline.tsx` 第 120-139 行。

### Idea 3 · 数字"轻量出场" (Number Tween-in)

- **现状**: Stat-card 数字从 0 / skeleton 跳到真值，没有动画。
- **改进**: 给 `.stat-card__value` 加 `@keyframes number-in { from { opacity: 0; transform: translateY(2px); } to { opacity: 1; transform: translateY(0); } }`，duration 200ms。
- **预期效果**: 数据加载/刷新时"有呼吸感"，类似 Vercel Analytics 数字出现。
- **工作量**: 小 (10 行 CSS + 可选 `key={value}` 触发重播)
- **风险**: 极低；key 已随数据变化。
- **位置**: `web/src/styles/global.css` 第 2064-2071 行附近追加。

### Idea 4 · Section Heading 上方"淡入 hairline"

- **现状**: section 之间靠 32px margin 区分，没有视觉分割。
- **改进**: 在 `.ad-section-heading` 上方加 `::before { content: ''; display: block; height: 1px; background: linear-gradient(to right, transparent, var(--border-default) 20%, var(--border-default) 80%, transparent); margin-bottom: var(--space-4); }`。
- **预期效果**: 类似 Stripe 文档的章节分割，"呼吸感"更清晰；让 Dashboard 长滚动更耐看。
- **工作量**: 极小 (5 行 CSS)
- **风险**: 极低；可被 `--section-divider: none` 关闭 (给密集页面留 escape hatch)。
- **位置**: `web/src/styles/global.css` 第 2561-2583 行附近。

### Idea 5 · Button 按下"按下感" (Button Press Feedback)

- **现状**: ant-btn-primary hover 时只有 box-shadow 16px accent-glow。
- **改进**: 增加 `:active { transform: scale(0.97); transition-duration: 60ms; }`，配合 `--accent-active` (#9f1239) 短暂 60ms 颜色。
- **预期效果**: 按钮"按下去"有物理反馈，类似 Linear 按钮。
- **工作量**: 极小 (3 行 CSS)
- **风险**: 极低；所有按钮统一受益。
- **位置**: `web/src/styles/global.css` 第 233-243 行附近。

### Idea 6 · PageHeader Eyebrow 加"朱色锚点块"

- **现状**: `.page-header-eyebrow` 只有字号 / 字间距 / uppercase，没有几何锚点。
- **改进**: 加 `::before { content: ''; display: inline-block; width: 3px; height: 12px; background: var(--accent); border-radius: 1px; vertical-align: -1px; margin-right: var(--space-2); }`。
- **预期效果**: 与 Ant Design 默认 / Linear 默认都不同，多了一个"编辑部"质感。
- **工作量**: 极小 (5 行 CSS)
- **风险**: 极低；纯装饰。
- **位置**: `web/src/styles/global.css` 第 637-644 行。

### Idea 7 · 路由切换淡入 (Route Cross-Fade)

- **现状**: 路由切换没有动画，新页面直接渲染。
- **改进**: 给 `<Outlet>` 包裹层加 `@keyframes route-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }` 160ms。
- **预期效果**: 类似 Vercel / Linear 路由切换，丝滑感显著。
- **工作量**: 小 (10 行 CSS + 1 个 wrapper div in AppLayout)
- **风险**: 中 — 需要在 `prefers-reduced-motion` 下禁用；当前 global.css 已有 media query 兜底 (第 784 行)。
- **位置**: `web/src/components/AppLayout.tsx` 第 753 行 + `global.css` 末尾追加。

### Idea 8 · EmptyState 图标"放大 + 极淡 ring"

- **现状**: 图标 32px、color muted，无 ring。
- **改进**: 加一个 56-64px 的容器，背景 `var(--accent-dim)`，圆角 50%，padding 16px；图标放进去。
- **预期效果**: 空状态"被看见"，新人引导时更友好；Stripe Dashboard 的空状态就是这么做的。
- **工作量**: 小 (改 EmptyState.tsx 8 行 + CSS 10 行)
- **风险**: 极低；不破坏现有 props。
- **位置**: `web/src/components/EmptyState.tsx` 第 17-25 行 + `global.css:2536-2540`。

### Idea 9 · Dashboard 行情卡"上方朱色 hairline + 极淡 radial"

- **现状**: 4 张实时行情卡 (`dashboard-index-card`) 全是白底 + 边框，价格 24px mono。
- **改进**: 给 `.dashboard-index-card` 加 `::before { content: ''; position: absolute; top: -1px; left: 12px; right: 12px; height: 2px; background: linear-gradient(to right, transparent, var(--accent-border), transparent); border-radius: 1px; }` + 在 body 区 `background: radial-gradient(circle at 0% 0%, var(--accent-dim), transparent 50%)`。
- **预期效果**: 让"实时"卡片从一堆白色 panel 里跳出来，但仍是 light clean。
- **工作量**: 小 (15 行 CSS)
- **风险**: 低；只影响 4 张行情卡 (类名限定)。
- **位置**: `web/src/styles/global.css` 第 3640-3695 行。

### Idea 10 · Sticky Table Header + 极淡 bg

- **现状**: Ant Table 表头随滚动消失 (`global.css:86-95`)。
- **改进**: 在评分 Top 10 表格 (`Dashboard/index.tsx:706-715`) 和其他 sticky 候选表里增加 `className="ad-table-sticky"`，使用现有的 `.ad-table-sticky` (第 881-886 行) 已有的 sticky 实现，并加 `background: var(--bg-elevated)` 而非 transparent — 滚动时不会与内容"混在一起"。
- **预期效果**: 长列表滚动时永远知道自己在哪一列。
- **工作量**: 小 (1 行 className × N 处；CSS 已就绪)
- **风险**: 极低；纯类名应用。
- **位置**: `web/src/styles/global.css:881-886` + `Dashboard/index.tsx:706` 表格。

---

## Part 3 — 三个最值得做的实施方案

按"视觉收益 / 工作量 / 风险"评分 (5 分制):

| Idea | 视觉收益 | 工作量 | 风险 | 性价比 |
|---|---|---|---|---|
| 1 卡片抬升 | 5 | 1 | 1 | 5.0 |
| 2 Sparkline 面积 | 5 | 1 | 1 | 5.0 |
| 4 Section hairline | 4 | 1 | 1 | 4.0 |
| 3 数字出场 | 3 | 1 | 1 | 3.0 |
| 5 Button 按下 | 3 | 1 | 1 | 3.0 |
| 6 Eyebrow 锚点 | 4 | 1 | 1 | 4.0 |
| 7 路由淡入 | 4 | 2 | 2 | 2.0 |
| 8 EmptyState ring | 3 | 2 | 1 | 1.5 |
| 9 行情卡 hairline | 4 | 2 | 1 | 2.0 |
| 10 Sticky 表头 | 3 | 1 | 1 | 3.0 |

**Top 3 选出**: Idea 1 (卡片抬升) + Idea 2 (Sparkline 面积) + Idea 4 (Section hairline) — 都是 5.0 性价比，纯 CSS / SVG，无破坏性。

---

### 实施 1 · Idea 1 — 卡片线性抬升

**改动文件**: `web/src/styles/global.css` (仅 CSS，无 TSX)

**当前代码** (2031-2036 行):
```css
.stat-card:hover,
.stat-card:focus-visible {
  border-color: var(--border-hover);
  background: var(--bg-elevated);
  box-shadow: var(--shadow-card-hover);
}
```

**目标代码**:
```css
.stat-card--clickable {
  position: relative;
  overflow: hidden;
}

.stat-card--clickable::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  width: 2px;
  background: var(--accent);
  border-radius: 1px;
  transform: translateX(-4px);
  opacity: 0;
  transition: transform var(--transition-base), opacity var(--transition-base);
}

.stat-card:hover,
.stat-card:focus-visible {
  border-color: var(--border-hover);
  background: var(--bg-elevated);
  box-shadow: var(--shadow-card-hover);
}

.stat-card--clickable:hover,
.stat-card--clickable:focus-visible {
  transform: translateY(-1px);
}

.stat-card--clickable:hover::before,
.stat-card--clickable:focus-visible::before {
  transform: translateX(0);
  opacity: 1;
}
```

**验收标准**:
1. 鼠标悬停 4 张 KPI 卡 → 卡片整体上移 1px，左侧 2px 朱色锚点从左侧滑入，阴影变深。
2. 不影响 `.ad-panel` 的其他普通卡片。
3. 暗色主题下阴影颜色自动跟随 token，无需额外配置。
4. 移动端 (hover 不存在) 不显示 transform，避免误触。

**风险**: 极低，已限定 `--clickable` 子集。

---

### 实施 2 · Idea 2 — Sparkline 渐隐面积

**改动文件**: `web/src/components/Sparkline.tsx` (1 个 SVG `<defs>` + 1 个 `<path fill="url(...)">`)

**当前结构** (第 120-139 行):
```tsx
return (
  <svg ... >
    <path d={path} fill="none" stroke={stroke} strokeWidth={strokeWidth} ... />
    {directionMarker && <path d={directionMarker} fill={stroke} />}
  </svg>
);
```

**目标结构**:
```tsx
// 在 path 计算附近新增 areaPath (closed polygon)
const areaPath = useMemo(() => {
  if (!path) return '';
  // path 已形如 "M x y L x y ...", 闭合到 baseline
  return `${path} L ${width} ${height} L 0 ${height} Z`;
}, [path, width, height]);

const gradientId = useMemo(
  () => `spark-grad-${Math.random().toString(36).slice(2, 9)}`,
  [stroke]
);

// JSX:
return (
  <svg ...>
    <defs>
      <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={stroke} stopOpacity="0.28" />
        <stop offset="100%" stopColor={stroke} stopOpacity="0" />
      </linearGradient>
    </defs>
    {areaPath && <path d={areaPath} fill={`url(#${gradientId})`} stroke="none" />}
    <path d={path} fill="none" stroke={stroke} strokeWidth={strokeWidth} ... />
    {directionMarker && <path d={directionMarker} fill={stroke} />}
  </svg>
);
```

**验收标准**:
1. 4 张行情卡 / 自选股的 sparkline 在 line 下方出现淡入面积 (从 stroke 颜色 28% 透明度渐变到 0)。
2. 涨绿跌红 (或 US 反转) 自动跟随 stroke 颜色。
3. 空数据 (`data.length === 0`) 时不渲染 areaPath (现有 early return 仍生效)。
4. 暗色主题下面积透明度自动适配 — 因为 stroke 来自 token，opacity 是固定值，dark 不会显得突兀。

**风险**: 极低；不破坏现有 API，只新增 1 个 path。

---

### 实施 3 · Idea 4 — Section Heading 淡入 Hairline

**改动文件**: `web/src/styles/global.css` (5 行 CSS)

**当前代码** (2561-2583 行):
```css
.ad-section-heading {
  margin: 0 0 var(--space-4);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
}
```

**目标代码** (在前面插入 `::before` 块):
```css
.ad-section-heading {
  margin: 0 0 var(--space-4);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
  position: relative;
}

/* 在第一个 section 不显示分割线 — 让页面顶部更干净 */
.dashboard-section:first-of-type .ad-section-heading {
  margin-top: 0;
}

.ad-section-heading::before {
  content: '';
  display: block;
  position: absolute;
  top: calc(var(--space-4) * -1 - 1px);
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(
    to right,
    transparent 0%,
    var(--border-default) 15%,
    var(--border-default) 85%,
    transparent 100%
  );
  pointer-events: none;
}

/* 不想用 hairline 的页面 — 加 `data-no-divider` 属性即可关闭 */
.ad-section-heading[data-no-divider]::before {
  display: none;
}
```

**验收标准**:
1. Dashboard 滚动到第 2 个 section 起，每个 section 上方出现一条 12-16% 边距处淡入淡出 hairline。
2. 不影响 `.panel-extra-link` 和 `__action` 的布局。
3. 暗色主题下 `var(--border-default)` 自动从 `rgba(255,255,255,0.06)` 取值。
4. 数据加载慢时，分割线已经先渲染出来 — 不会出现"先无后有"的跳动。

**风险**: 极低；仅装饰，分割线 `pointer-events: none` 不阻挡点击。

---

## 验证三件套 (实施后跑)

```bash
# 1. TypeScript 检查 (无新增 TS)
cd web && npx tsc --noEmit

# 2. Lighthouse 视觉对比 (手动)
#    - 打开 /dashboard，hover 4 张 KPI 卡
#    - 滚动看 section 分割
#    - 截图 4 张 sparkline 卡对比

# 3. 回归清单
#    - light/dark 主题切换 ✓
#    - China/US 颜色约定 ✓
#    - 移动端 < 768px (hover 不生效) ✓
#    - prefers-reduced-motion ✓ (Idea 1/4 已被全局禁用 transform/transition)
```

---

## 附录 · 不在本轮做但值得记下来的 (P2 Backlog)

- **P2-1** · 暗色模式"终端扫描线"过于复古 (line 1700-1730)，与"现代 SaaS"定位冲突 — 建议改成纯黑 (0,0,0) + 极淡 (255,255,255,0.04) 边框，移除 vignette + scanline。
- **P2-2** · Tooltip 的"卡片化"可以更精致 — 当前 bg-card, border-card, radius-md (350-360 行) 偏朴素；建议加 4px blur + 极淡 shadow-lg + 6px radius。
- **P2-3** · Stat-card 数字应该接 number-tweening (200ms ease-out) — 当前没有数字 tween，只有 skeleton → value 硬切。
- **P2-4** · `data-card-density` 应该作用到 `.stat-card` / `.ad-panel` 的内边距，不仅限于表格。
- **P2-5** · 列表 hover 时缺 **左侧 2px 渐入锚点** (类似 Idea 1，但作用于 `.ant-list-item`)。
- **P2-6** · 给"中国市场 / 美股市场"切换增加 **数据流畅动画** (Idea 2 配合)，数字/颜色 tween 200ms。
- **P2-7** · Hero page (首页 / Learning) 可以加 **顶部 200px radial 渐变背景** (accent-dim 8% → transparent) — Linear / Vercel 都这么做，给页面"温度"。

---

> 报告完成。**不直接动手改代码**；实施需要用户审批后启动，每个 Idea 改动文件 ≤ 3 处，且全部走 token，不破坏 light/dark 双主题、不破坏 China/US 颜色约定、不破坏 prefers-reduced-motion。