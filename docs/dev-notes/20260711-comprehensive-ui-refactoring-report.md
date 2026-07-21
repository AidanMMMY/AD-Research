# AD-Research 全面前端 UI 重构方案

## 基于 6 维度深度审计的诊断与改造计划

> 编制日期：2026-07-11 | 方法论：6 个独立审计 agent，并行审查 40+ 文件，覆盖间距/组件/交互/AntD/字体/一致性全维度
>
> **注**：本文为时点审计与重构方案，部分描述已过时（2026-07-21 核实）：A 阶段核心项已落地——`main.tsx` ConfigProvider 已改为读取 CSS 变量（与 `theme.css` 单源同步，双轨制已消除）、字体已自托管加载；侧栏现为 10 组 41 项（E1 计划的"6 组 25 项"未完成）；`global.css` 已拆分为 `styles/global/` 下 22 个分块文件（8000+ 行单文件不复存在）。B–F 阶段其余项请对照代码现状判断完成度。

---

## 执行摘要：为什么当前 UI 让你觉得不对劲

三个核心问题的根因诊断：

### 问题 1：为什么总觉得不好用、不精致，既粗糙又低级？

**根因：存在"双轨制主题系统"**。

项目中有三套并行的视觉控制系统：
1. `main.tsx` 的 ConfigProvider（JS token，仍用旧朱红 `#e11d48` 和终端绿 `#5fa87a`）
2. `theme.css` 的 CSS 变量（v2 已升级为蓝靛 `#2563EB`）
3. `global.css` 的 175 处 `!important` 暴力覆盖

三者互相打架，导致 Ant Design 原生组件显示一套颜色、自定义组件显示另一套颜色。这不是"设计选择"，而是**主题系统的技术债务**——上一次升级（蓝色 v2）没有同步到 ConfigProvider。

**此外**：45% 的共享组件缺少 `className` 透传，30% 缺少 `style` 透传。父组件无法追加自定义样式，导致开发者在页面中重复造轮子。

### 问题 2：为什么视觉上不专业、太俗套？

**根因：四个"双轨制"在并行运行。**

| 双轨制 | 轨道 A | 轨道 B | 后果 |
|--------|--------|--------|------|
| 主题颜色 | ConfigProvider 朱红 `#e11d48` | CSS 变量蓝靛 `#2563EB` | 同一页面两种强调色 |
| 暗色底色 | ConfigProvider 终端黑 `#0a0a0a` | theme.css GitHub Dark `#0D1117` | 组件表面颜色不一致 |
| 字体族 | 亮色 KPI 用 Inter sans-serif | 暗色 KPI 用 JetBrains Mono monospace | 切换主题时数据数字字体突变 |
| 布局方式 | antd Row/Col/Space | 自定义 ad-flex/ad-gap CSS 工具类 | 三种布局方式并存 |

**此外**：
- ContextHint 组件的 CSS 类定义了但从未实现（6 个 CSS class 只有 1 个有样式）——这是典型的"半成品感"。
- 侧栏 11 个分组、41 个菜单项——信息过载，用户找不到想用的功能。
- Inter 字体之前未加载（本次会话已修复），长期依赖系统回退字体，macOS 和 Windows 用户看到的是完全不同的字体。

### 问题 3：为什么有很多低级错误？（控件间距不统一、边距没对齐）

**根因：没有严格执行设计系统的"纪律"。**

具体数据：
- `global.css` 中有 **40+ 处硬编码 px 值** 未使用 `--space-*` token（如 `14px`、`7px`、`10px`、`24px`、`32px`）
- `global.css` 中有 **175 处 `!important`**，覆盖了 85+ 个不同的 Ant Design class
- `theme.css` 和 `global.css` 在 768-991px 断点下对 `.ant-card-body` 的 padding 存在**互相矛盾的规则**
- 移动端 `@media (max-width: 767px)` 规则分散在 `theme.css`（360-503 行）和 `global.css`（466-600 行）两个文件中，未做合并设计
- 页面 section 间距不统一：Dashboard 是 32px，InstrumentDetail 是 20px
- RSI 数值精度不统一：Screen 用 `.toFixed(1)`，SectorRotation 用 `.toFixed(0)`
- 空值符号不统一：`-` vs `—` vs `暂无数据` vs `N/A` 混用
- 日期格式化方式分裂：AdminUsers 用原生 `toLocaleString('zh-CN')`，其他页面用共享 `utils/datetime.ts`（含时区校正）

---

## 一、六维度审计核心发现

### 1.1 间距与布局一致性

**审计范围**：theme.css（541行）、global.css（8211行）、AppLayout.css、5 个关键页面

**主要发现**：

| 问题 | 位置 | 严重度 |
|------|------|--------|
| 40+ 处硬编码 px 值未使用 `--space-*` token | `global.css` 全文件 | 🔴 |
| 响应式规则分散在两个文件中，存在互相矛盾的覆盖 | `theme.css` 360-503 行 vs `global.css` 466-600 行 | 🔴 |
| Dashboard section 间距 32px，InstrumentDetail 仅 20px | `Dashboard/styles.css` vs `InstrumentDetail/styles.css` | 🟡 |
| PageHeader 的 `margin: 0 0 32px` 硬编码 | `global.css:607` | 🟡 |
| 移动端 `.ant-space { gap: var(--space-2) !important }` 覆盖所有 Space 的 size prop | `global.css:578` | 🟡 |
| 768-991px 断点下 card-body padding 有 `18px 20px` vs `12px 0` 两个矛盾规则 | `theme.css:493-494` vs `global.css:594-595` | 🟡 |
| 侧栏导航项 `padding: 7px 12px 7px 14px` 使用非标准网格值 | `global.css:2757` | 🟢 |

### 1.2 组件质量与精致度

**审计范围**：`components/` 目录下全部 .tsx 文件，重点关注 15 个核心组件

**综合评分**：

| 组件 | 问题数 | 最严重问题 |
|------|--------|-----------|
| **ContextHint** | 🔴 1 | CSS 类定义了但未实现（仅 1/7 有样式）——典型半成品 |
| **AppLayout** | 🔴 2 | 键盘焦点环被 `outline: none` 覆盖；Hover 对比度不可见 |
| **TickerTape** | 🔴 1 | 自动滚动 + `role="button"` 导致键盘用户无法聚焦 |
| **StatCard** | 🟡 3 | 长数字溢出无截断；缺 `className` 透传；gap 硬编码 6px |
| **PageHeader** | 🟡 2 | margin 硬编码 32px；缺 `className` 透传 |
| **FilterToolbar** | 🟡 1 | 长标题无截断 |
| **ReturnTag** | 🟡 2 | 缺 `className` 透传；gap 硬编码 2px |
| **EmptyState** | 🟡 1 | 缺 `className` 透传 |
| **Panel** | 🟢 1 | 良好 |

**全局问题**：
- ~45% 组件缺少 `className` 透传（8/18 个主要组件）
- ~30% 组件缺少 `style` 透传
- 交互组件普遍缺少 `:active` 按压态（只有 hover + focus-visible）
- 动画缓动函数 3 种并存：`ease` / `ease-in-out` / `cubic-bezier(0.4,0,0.2,1)`

### 1.3 交互逻辑与操作体验

**审计范围**：7 个核心页面 + 侧栏路由配置（41 个菜单项）

**核心问题**：

| 问题 | 严重度 | 影响 |
|------|--------|------|
| **侧栏 11 组 41 项 → 认知过载** | 🔴 | 用户找不到功能，研究类分组 8 项堆积 |
| **详情页 → Screen 筛选器无入口** | 🔴 | 用户看到标的后无法"找类似标的" |
| **面包屑在 `/instruments/:code` 下断裂** | 🔴 | 因为动态路由不在 `menuRoutes` 中 |
| **表格普遍无排序能力** | 🟡 | 列头点击无排序指示器，无法按涨跌幅/评分排序 |
| **筛选模式不统一** | 🟡 | Screen 用 Zustand store，InstrumentList 用 URL params+本地状态，Macro 裸用 Segmented |
| **加载态碎片化** | 🟡 | Screen 用 Table loading prop，Macro 用 Spin+Skeleton，Correlation 用 Spin center |
| **详情页缺少"收藏"按钮的即时反馈** | 🟡 | Star 切换有 API 调用但无 optimistic update |
| **移动端表格无横滑提示** | 🟢 | 表格设置了 `scroll={{ x }}` 但无视觉提示 |

**典型用户路径摩擦分析**（"开盘前查看自选股→筛选潜力标的→查看详情→AI分析"）：

1. Dashboard → 点击自选股项 → 进入 InstrumentDetail ✅
2. 在详情页想"找类似标的"→ **无入口** → 被迫回到侧栏找 Screen 筛选器 ❌
3. 在 Screen 筛选结果中 → 想按涨跌幅排序 → **列头不可排序** ❌
4. 点击某个标的进入详情 → 面包屑显示"首页 > 510300"而非"首页 > 标的详情 > 510300" ❌
5. 在详情页用 AI Help → 点击后跳到 `/chat` 独立页面，离开当前研究上下文 ❌

### 1.4 Ant Design 集成质量

**审计范围**：main.tsx ConfigProvider 配置 + global.css 中全部 `.ant-*` 覆盖

**核心发现：双重主题系统冲突（最严重的技术债务）**

这是本报告中最关键的发现。`main.tsx` 第 45-248 行的 ConfigProvider 定义了完整的 JS token 主题（亮色+暗色两套），但 **JS 端的颜色从未跟随 v2 设计升级更新**：

| 属性 | ConfigProvider (JS) | theme.css (CSS 变量) | 后果 |
|------|---------------------|---------------------|------|
| 亮色主色 | `#e11d48`（朱红） | `#2563EB`（蓝靛） | AntD 组件 vs 自定义区域显示不同强调色 |
| 暗色主色 | `#5fa87a`（终端绿） | `#60A5FA`（去饱和蓝） | 同上 |
| 暗色 Card 背景 | `#111111`（组件 token） | `#1C2128`（CSS `--card-bg`） | 卡片颜色分裂 |

**数据统计**：
- `global.css` 约 500 行是 `.ant-*` 覆盖代码
- 175 处 `!important` 覆盖了 85+ 个 Ant Design CSS 类
- 其中约 40% 是必要的设计定制，35% 可通过补充 ConfigProvider component token 消除，25% 是纯粹冗余
- **零使用 antd v5 Flex 组件**，取而代之的是自定义 40+ 行 CSS 工具类

### 1.5 字体排印与视觉层级

**审计范围**：theme.css typography token + 4 个关键页面

**22 个问题，按严重度**：

**🔴 P0（2个）**：
1. 亮/暗模式下 KPI 数字字体族不同（亮=Inter sans-serif，暗=JetBrains Mono monospace），切换主题时字体突变
2. 暗色模式下 H2/H3 字号收缩（H2 24→20px，H3 18→16px），且字重降级（H2 600→500）——好消息是本次会话已修复

**🟡 P1（6个）**：
3. 13px/14px 区分度不足，且字重逻辑颠倒（`--text-small` 500 > `--text-body` 400）
4. 30+ 处硬编码 9/10/11px 违反了"最小 12px"规则
5. PingFang SC vs 微软雅黑的 x-height 差异，导致跨平台中英文混排不一致
6. KPI 大数字 36px weight-400 略显轻薄，金融数据应更稳重
7. 正负号表达在 ReturnTag 组件 / `formatSigned` 函数 / 裸 `toFixed()` 三者间分裂
8. JetBrains Mono 与中文后缀（如"亿"、"万"）混排时存在垂直对齐偏移

**🟢 P2（14个）**：
- 空值符号 `-` vs `—` vs `暂无数据` vs `N/A` 混用
- 千分位分隔符：`formatAmount` 渲染 `12345678` 而非 `12,345,678`
- 日期格式化存在 3 种方式（`toLocaleString`/`toLocaleDateString`/`.slice(0,16)`）
- TickerTape 和侧边栏标签缺少 Tooltip 显示完整文本
- 百分比小数位数无规范（0 位/1 位/2 位随意使用）

### 1.6 跨页面一致性

**审计范围**：4 组共 15 个页面

| 页面组 | 一致性评分 | 最突出问题 |
|--------|-----------|-----------|
| **列表页**（5个） | 2.5/5 | SparklineCell 在 3 个文件中逐文件复制粘贴；空状态实现有 4 种不同写法 |
| **详情页**（4个） | 2.5/5 | 布局模式分裂（InstrumentDetail 线性平铺 vs 其余 Tabs 布局）；KPI 涨跌展示 3 种不同方式；AI 分析区 ~150 行代码重复 |
| **分析/工具页**（4个） | 3.0/5 | 缺少统一的"参数选择→展示结果"页面骨架；FilterToolbar 有的被 Panel 包裹、有的裸用、有的根本不用 |
| **管理/配置页**（2个） | 3.0/5 | AdminUsers 日期格式化未使用共享 utils（时区错误）；EmptyState 未使用 |

**共享组件使用率**：

| 组件 | 应使用页面数 | 实际使用页面数 | 使用率 |
|------|-------------|--------------|--------|
| PageShell | 15 | 15 | 100% |
| PageHeader | 15 | 14 | 93% |
| Panel | 15 | 13 | 87% |
| FilterToolbar | 10 | 3 | 30% |
| EmptyState | 15 | 8 | 53% |
| ResponsiveGrid | 10 | 6 | 60% |
| ContentCard | 5 | 0 | 0% |
| StatCard | 8 | 6 | 75% |

**关键发现**：`FilterToolbar`、`EmptyState`、`ContentCard` 三个共享组件的使用率严重偏低。每个页面都在重复造轮子。

---

## 二、问题根本原因总结

三个"为什么"的统一答案：

### "粗糙感"的根源：三套并行系统互相打架

```
                 ┌─────────────────┐
                 │ main.tsx (JS)   │  ConfigProvider tokens
                 │ 强调色 #e11d48  │  ← 从未更新
                 └────────┬────────┘
                          │ 冲突
    ┌─────────────────────┼─────────────────────┐
    │                     ▼                     │
    │  ┌─────────────────────────────┐          │
    │  │ theme.css (CSS 变量)         │          │
    │  │ 强调色 #2563EB              │          │
    │  │ ─────────────────           │          │
    │  │ global.css (!important ×175)│ 覆盖层    │
    │  └─────────────────────────────┘          │
    │                                            │
    │  Ant Design 组件 ←→ 自定义组件             │
    │  显示不同颜色        显示不同颜色           │
    └────────────────────────────────────────────┘
```

### "低级的间距/对齐错误"的根源：设计系统缺乏执行纪律

- 4px 基准网格已定义（`theme.css` 中 `--space-1` 到 `--space-9`），但 40+ 处硬编码 px 值绕过了它
- 有些是历史残留（如 7px padding 来自 Phase 2 之前的旧代码）
- 有些是"快速修补"（如 inline `style={{ marginTop: 12 }}` 来快速对齐）
- 有些是两套响应式规则放在两个文件中，从未做合并审计

### "不像一个团队做的"的根源：复制粘贴 + 缺乏共享骨架

- 4 个详情页像 4 个不同产品（不同时间、不同模式构建）
- SparklineCell 在 3 个列表页中逐字复制
- AI 分析区域 ~150 行代码在 2 个详情页中完全相同
- 没有"列表页模板"、"详情页模板"、或"分析工具页模板"来强制收敛页面结构

---

## 三、全面重构方案

### 方案结构

| 阶段 | 内容 | 预计工时 | 解决的核心问题 |
|------|------|---------|--------------|
| **A** | 消除双轨制（ConfigProvider 同步 + 删除冗余 `!important`） | 2天 | #1 粗糙感、#2 不专业 |
| **B** | 组件补齐（className/style 透传 + 状态完整性 + 缺失 CSS） | 2天 | #1 粗糙感、#3 低级错误 |
| **C** | 页面骨架标准化（列表页/详情页/分析页统一模板） | 3天 | #2 不专业、#3 低级错误 |
| **D** | 间距系统收敛（消除硬编码 px + 统一响应式规则） | 1天 | #3 低级错误 |
| **E** | 交互优化（导航重构 + 表格排序 + 筛选统一） | 2天 | #1 不好用 |
| **F** | 字体与格式化（统一数字格式 + 空值 + 日期 + 百分比） | 1天 | #2 不专业 |

**总计：约 11 个工作日**

---

### A 阶段：消除双轨制（最重要，立即执行）

**目标**：让 ConfigProvider JS token 和 theme.css CSS 变量使用相同的颜色。

**具体任务**：

#### A1：ConfigProvider 同步到 v2 蓝靛方案
```tsx
// main.tsx — 亮色主题 lightAlgorithm
colorPrimary: '#2563EB',           // 从 #e11d48 改为蓝靛
colorPrimaryBg: 'rgba(37,99,235,0.08)',
colorPrimaryBorder: 'rgba(37,99,235,0.20)',

// main.tsx — 暗色主题 darkAlgorithm
colorPrimary: '#60A5FA',           // 从 #5fa87a（终端绿）改为去饱和蓝
colorPrimaryBg: 'rgba(96,165,250,0.12)',
colorPrimaryBorder: 'rgba(96,165,250,0.25)',

// Card 暗色背景
Card: { colorBgContainer: '#1C2128' },  // 从 #111111 同步到 GitHub Dark
```

#### A2：从 global.css 中删除已被 ConfigProvider token 覆盖的冗余规则
- 删除 Table header 的三重覆盖（保留 CSS 中的 uppercase 定制，删除 background/color 重复）
- 删除 Card background 的 `!important`（ConfigProvider 的 `colorBgContainer` 已处理）
- 删除 Select option 的重复颜色定义（已有 `optionSelectedBg` token）

**预计效果**：从 global.css 删除约 150 行冗余代码，Ant Design 组件和自定义区域颜色完全一致。

#### A3：建立单一来源原则
新增 `useAntdTheme` hook 或修改现有逻辑，从 `document.documentElement.dataset.theme` 和 `dataset.accent` 读取当前主题，动态生成 ConfigProvider theme——确保未来修改主题只需改 `theme.css` 一处。

---

### B 阶段：组件补齐

**目标**：让每个共享组件"写完"——包括全部交互状态、className/style 透传、内容溢出处理。

**具体任务**：

#### B1：批量添加 className 和 style 透传（8 个组件）
```
StatCard, PageHeader, EmptyState, InstrumentCodeTag, ReturnTag,
ScoreBar, FilterToolbar, SectionHeading
```
统一模式：
```tsx
interface Props {
  className?: string;
  style?: React.CSSProperties;
  // ... existing props
}
// 在最外层 div 上合并：
<div className={`base-class ${className ?? ''}`} style={style} />
```

#### B2：修复 ContextHint 的缺失 CSS（6 个未实现 class）
```
.context-hint { padding: var(--space-3); max-width: 320px; }
.context-hint__title { font-size: var(--text-body-size); font-weight: 600; }
.context-hint__body { font-size: var(--text-small-size); color: var(--text-secondary); }
/* ... 等 */
```

#### B3：统一交互状态补全（全部交互组件）
为以下组件添加 `:active` 按压态：
- `StatCard`（`transform: scale(0.98)` + `transition: transform 100ms`）
- `Panel` 内的可点击元素
- 侧栏导航项（`translateX(1px)` 微反馈）

#### B4：补全内容溢出处理
- `StatCard` value：`overflow: hidden; text-overflow: ellipsis; white-space: nowrap`
- `FilterToolbar` title：同上
- `ReturnTag`：长百分比添加 Tooltip
- `InstrumentCodeTag` name：已有截断 ✅

---

### C 阶段：页面骨架标准化

**目标**：建立 3 种标准页面骨架，将所有同类页面收敛到统一模板。

**具体任务**：

#### C1：列表页标准骨架
```tsx
// Template: <ListPageShell>
<PageShell maxWidth="wide">
  <PageHeader eyebrow="..." title="..." description="..." extra={<LastUpdated />} />
  <Panel variant="default" padding="md">
    <FilterToolbar total={total} extra={<Button>导出</Button>}>
      {/* 统一的筛选控件 */}
    </FilterToolbar>
    <Table size="small" columns={sharedColumns} dataSource={items}
           pagination={{ pageSize: 50 }} loading={isLoading}
           locale={{ emptyText: <EmptyState title="暂无数据" /> }} />
  </Panel>
</PageShell>
```
需要重构的页面：InstrumentList、StocksList、CryptoList、PoolList、ScoreRanking
统一内容：页面结构、Table size、EmptyState、SparklineCell（抽取为共享组件，消除 3 处复制粘贴）

#### C2：详情页标准骨架
```tsx
// Template: <DetailPageShell>
<PageShell maxWidth="wide">
  <PageHeader eyebrow="..." title="..." description="..." extra={<FavoriteButton />} compact />
  {/* 统一标签行：InstrumentCodeTag + 市场 Tag + 分类 Tag + 板块 Tag */}
  <SectionHeading title="核心指标" />
  <ResponsiveGrid cols={4}><StatCard ... /></ResponsiveGrid>
  <Tabs items={[
    { key: 'chart', label: 'K线行情', children: <KLineChartSection /> },
    { key: 'indicators', label: '指标数据', children: <IndicatorSection /> },
    { key: 'score', label: '综合评分', children: <ScoreSection /> },
    { key: 'ai', label: 'AI 分析', children: <DetailAIAnalysis code={code} /> },
    { key: 'news', label: '相关新闻', children: <NewsListPanel code={code} /> },
  ]} />
</PageShell>
```
需要重构的页面：InstrumentDetail（从线性布局→Tabs）、StockDetail、CryptoDetail、PoolDetail
抽取共享组件：
- `<DetailAIAnalysis>` —— 消除 InstrumentDetail 和 StockDetail 中 ~150 行的重复代码
- `<IndicatorSection>` —— 统一的技术指标面板
- `<KPIHeroStats>` —— 统一的顶部 KPI 行（解决 4 种不同 heroStats 结构）
- `<RelatedActions>` —— "找类似标的" + "AI 分析" + "加入自选" 的统一操作区

#### C3：分析/工具页标准骨架
```tsx
// Template: <AnalysisPageShell>
<PageShell maxWidth="wide">
  <PageHeader eyebrow="..." title="..." description="..." extra={controls} />
  <Panel variant="default" padding="md">
    <FilterToolbar>{/* 统一的参数选择区 */}</FilterToolbar>
  </Panel>
  {/* 结果区：图表 / 表格 / 热力图 */}
</PageShell>
```
需要重构的页面：Screen、Macro、CorrelationAnalysis、SectorRotation
统一内容：FilterToolbar 的使用模式（当前 4 个页面 4 种不同做法）、加载态模式、SectionHeading 命名

---

### D 阶段：间距系统收敛

**目标**：消除所有非标准网格值，统一响应式规则。

**具体任务**：

#### D1：替换 40+ 处硬编码 px 值
搜索并替换所有不使用 `--space-*` token 的 margin/padding/gap：
```
14px → var(--space-4) 或新增 --space-3-5: 14px（如果确实需要非标值）
10px → var(--space-3)（12px 相近）或保持（极少数场景可接受）
7px  → 标准化为 var(--space-2)（8px）
```
使用 `grep -rn ":\s*\d+px" global.css` 逐条审计。

#### D2：合并分散的响应式规则
将 `theme.css`（360-503 行）和 `global.css`（466-600 行）中的移动端规则合并到一个文件中，消除互相矛盾的覆盖（如 `.ant-card-body` 的 padding）。

#### D3：统一页面 section 间距
```css
:root {
  --section-gap: var(--space-6);  /* 统一 32px */
}
/* 所有 SectionHeading 下方统一 */
.section-heading, .ad-section-heading { margin-bottom: var(--section-gap); }
```

---

### E 阶段：交互优化

**目标**：让平台"好用"——导航清晰、操作流畅、反馈及时。

**具体任务**：

#### E1：侧栏重构——从 11 组 41 项 到 6 组 25 项
合并方案：
- `report` + `research-reports` + `cninfo-reports` → 合并为"投研报告"（含子 Tab）
- `notify`（仅 2 项）→ 合并到顶部 Header 通知 bell 图标
- `admin`（仅 2 项）→ 保留但默认折叠
- 移除低频入口到"更多"折叠组

#### E2：补齐关键导航路径
- InstrumentDetail 的 PageHeader extra 添加"筛选类似标的"按钮（`→ /screen?market=...&category=...`）
- Dashboard 全球速览卡添加"更多 → /macro"链接
- Sidebar 高亮逻辑修复：确保动态路由（`:code`）匹配到正确的侧栏项

#### E3：表格排序能力
在所有数据表格中添加 Ant Design 的 `sorter` 属性：
- 涨跌幅列：`sorter: (a, b) => a.change_pct - b.change_pct`
- 评分列：`sorter: (a, b) => a.score - b.score`
- 日期列：`sorter: (a, b) => dayjs(a.date).unix() - dayjs(b.date).unix()`

#### E4：面包屑修复
在 `AppLayout.tsx` 的面包屑逻辑中，为动态路由 `/instruments/:code` 添加硬编码映射：
```tsx
const DYNAMIC_SEGMENTS: Record<string, string> = {
  instruments: '标的详情',
  stocks: '个股详情',
  // ...
};
```

---

### F 阶段：字体与格式化统一

**目标**：让数字、日期、单位在全平台有一致的呈现。

**具体任务**：

#### F1：建立统一的数据格式化工具集
```typescript
// utils/format.ts 扩展
export function formatNumber(v: number | null, decimals = 2): string {
  if (v == null) return '—';
  return v.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function formatPercent(v: number | null, decimals = 2, signed = true): string {
  if (v == null) return '—';
  const sign = signed && v > 0 ? '+' : '';
  return `${sign}${v.toFixed(decimals)}%`;
}

export function formatDate(iso: string): string {
  return dayjs(iso).tz('Asia/Shanghai').format('YYYY-MM-DD HH:mm:ss');
}

export function formatEmpty(v: any, fallback = '—'): string {
  return v == null || v === '' ? fallback : String(v);
}
```

#### F2：全平台搜索替换
- `new Date(v).toLocaleString('zh-CN')` → `formatDate(v)`（AdminUsers）
- `v?.toFixed(1)` → `formatPercent(v, 1)`（统一小数位）
- `'-'` → `'—'`（统一空值符号，em-dash）

---

## 四、实施路线图

```
第1周                     第2周                     第3周
├──── A阶段 ────┤├──── B阶段 ────┤├──── C阶段 ────────────┤
│ ConfigProvider ││ 组件 className ││ 列表页骨架标准化      │
│ 同步 + 删冗余  ││ 补齐+状态补全  ││ 详情页骨架标准化      │
│                ││               ││                       │
│ D阶段（穿插）  ││ E阶段（穿插）  ││ F阶段（穿插）         │
│ 间距硬编码替换 ││ 侧栏重构       ││ 格式化工具统一        │
└────────────────┴────────────────┴────────────────────────┘

总计约 11 个工作日，可按优先级分批执行
```

---

## 五、预期效果

| 维度 | 当前 | 改造后 |
|------|------|--------|
| 主题一致性 | 三套系统互相打架 | 单源（theme.css），ConfigProvider 动态同步 |
| 组件 API 完整度 | 55% 缺少 className 透传 | 100% 支持 className + style |
| 页面骨架一致性 | 4 种模式（无模板） | 3 种标准骨架（列表/详情/分析） |
| 间距系统合规率 | ~85% 使用 token | ~98% 使用 token |
| 数据格式化一致性 | 3 种日期格式 + 3 种空值 + 混合精度 | 统一工具集 |
| 导航可用性 | 11 组 41 项 | 6 组 ~25 项 |
| `!important` 数量 | 175 | ~60（仅保留必要的设计定制） |
| tsc 错误 | 0 | 0 |
| Build | ~5.5s | ≤6s |

---

*报告编制：AD-Research 全面 UI 审计 | 2026-07-11 | 基于 6 个独立审计 agent × 40+ 文件深度审查*
