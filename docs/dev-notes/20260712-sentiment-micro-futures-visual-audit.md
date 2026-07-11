# AD-Research 前端 5 页视觉层级与布局审计报告

> **审计范围**：`Sentiment` / `SentimentDashboard` / `CorrelationAnalysis` / `Microstructure` / `Futures` 五个页面及其对应的 `styles.css`，外加其依赖的共享组件 (`PageShell` / `PageHeader` / `Panel` / `FilterToolbar` / `CorrelationHeatmap` / `StatCard` / `ResponsiveGrid` / `EmptyState`) 与全局样式 `global.css`。
> **审计维度**：分组/分类、图标位置、卡片对齐、图表对齐、表格对齐、雷达图/分布图可读性、响应式 + 跨页面一致性。
> **审计日期**：2026-07-12
> **本报告仅记录问题，不修改代码。**

---

## 0. 摘要：跨页面共性问题（建议优先修复）

| # | 问题 | 涉及页面 | 严重度 |
| - | --- | --- | --- |
| C1 | `SentimentDashboard` 完全没有用 `PageShell / PageHeader`，与项目其它页面风格不一致 | SentimentDashboard | 高 |
| C2 | `SentimentDashboard` 用 Antd `<Empty>`，其余 4 页都用项目 `EmptyState` 组件 | SentimentDashboard | 中 |
| C3 | `Microstructure` 顶部 4 张 KPI 用 `Card+Statistic`，与 Futures 的 `StatCard` 自定义组件样式不一致 | Microstructure / Futures | 中 |
| C4 | `Microstructure` 引用了别的页面的样式类 `detail-kpi-rise/fall`（不存在于 Microstructure/styles.css），本地 `microstructure__kpi-*` 反而是死代码 | Microstructure | 中 |
| C5 | `Sentiment` 热力图 `heatmapColor` 函数未读 `useSettingsStore.colorConvention`，切换美股/A 股配色后，热力图方向反了 | Sentiment | 高 |
| C6 | `phase5c-` 前缀（早期）与 `ad-` 前缀（当前）的工具类混用，命名约定不一致 | 全部 5 页 | 中 |
| C7 | `FilterToolbar.total` 在 `Microstructure` 显示的是"当前 tab 的数据量"，位置错位——应该挂在 Tab 标签的 badge 上 | Microstructure | 中 |
| C8 | `PageHeader.eyebrow` 只有 `Futures` 一页在用，5 页视觉层级基准不一致 | 全部 5 页 | 低 |
| C9 | `Microstructure/styles.css` 定义了 `microstructure__kpi-rise/fall` / `microstructure__filter-input` 但代码从未引用，本地样式文件基本是死代码 | Microstructure | 低 |
| C10 | `CorrelationAnalysis/styles.css` 完全为空（只剩注释），本应是该页样式归口 | CorrelationAnalysis | 低 |
| C11 | 5 页中有 3 页用 legacy `phase5c-input--md / phase5c-select--xxs` / `phase5c-icon-title`，utility 命名空间混乱 | Sentiment / Microstructure / SentimentDashboard | 中 |

---

## 1. Sentiment（散户情绪看板）

文件：`web/src/pages/Sentiment/index.tsx`（607 行，无独立 `styles.css`，全部样式在 `global.css`）

### 1.1 分组/分类
- **市场分类 Segmented（全部 / A 股 / 美股 / 加密）**：OK，但持久化键 `sentiment-market` 写在 `localStorage`，没考虑登录用户偏好（设置里）。
- **情绪类型**：`positive / neutral / negative` 通过 `POLL_SLICE_COLORS` 映射到 `color-rise / text-tertiary / color-fall`，**映射方向与中国习惯相反（红=涨=positive，绿=跌=negative）**。详情面板里的 `ad-detail-score-value--positive` 又映射到 `color-fall`（绿），**热力图与详情面板同一页内颜色方向不一致**（见 1.5）。

### 1.2 图标位置
- Panel title 图标仅 `Sentiment` 一页用到（`<HeartOutlined>` + `<FireOutlined>`），**与其它页 Panel title 纯文字不一致**。
- "情绪最强烈" Panel 的 `FireOutlined` 与 Panel 内 mover row 的 `ArrowUpOutlined / ArrowDownOutlined` 出现图标重复。

### 1.3 卡片对齐
- 热力图单元格 `min-width: 120px / min-height: 64px`（global.css `.ad-heatmap-cell`），1280px 容器下大约 8 列；50+ 标的时很密集。
- 单标详情面板里 `<ResponsiveGrid cols={2}>`：
  - 左：PieBreakdown（手写 SVG，56×56）
  - 右：多空比文本 + Button
  - 两列高度差大，左列垂直居中（`ad-items-center`），但右列含文字 + Button 垂直跨度更大 → 视觉上两列不对齐。
- DistributionRadar 在 Panel 底部独占一行，与上方 `Sparkline + PieBreakdown` 之间靠 `ad-mt-4` 隔开，**没有视觉分组**（缺 divider 或 section heading）。

### 1.4 图表对齐
- 热力图 `auto-fill, minmax(120px, 1fr)` + `gap: var(--space-2)`：OK，但在 mobile (`<576px`) 没有特别处理，会退化为 1-2 列。
- `Sparkline` 写死 `width={240}, height={48}`，放进 `ResponsiveGrid cols={2}` 时容器宽度 <240 会被压缩或溢出 → **硬编码尺寸破坏响应式**。
- `PieBreakdown`：硬编码 56×56，**缺刻度/百分比标签**，只能 hover Tooltip 看。
- `DistributionRadar`：硬编码 80×80，**字号 8px 偏小**，5 轴标签容易重叠。

### 1.5 颜色一致性（重要 Bug）
代码片段：
```ts
const POLL_SLICE_COLORS: Record<SentimentLabel, string> = {
  positive: 'var(--color-rise)',     // 红
  neutral:  'var(--text-tertiary)',  // 灰
  negative: 'var(--color-fall)',     // 绿
};
```
而 `ad-detail-score-value--positive` 映射到 `color-fall`（绿）。两个方向不一致，且都不响应 `useSettingsStore.colorConvention`。

热力图 `heatmapColor(score, importance)` 直接硬编码 RGB：
```ts
const r = score > 0 ? 82 : score < 0 ? 245 : 140;
const g = score > 0 ? 196 : score < 0 ? 34 : 140;
```
**没有经过 `resolveChartColors` 或 `colorConvention`**，切配色后方向仍固定为中国习惯（红=positive）。

### 1.6 Top Movers 列表
- `ad-mover-row` 用 `flex + gap`，但行内 `ad-mover-name` 用 `flex: 1`，**InstrumentCodeTag 内部可能塞 1-2 行（name + name_zh）**，行高不一致。
- 颜色：`ad-mover-arrow--up` 映射 `color-fall`（绿），`ad-mover-arrow--down` 映射 `color-rise`（红）—— **箭头方向与字面颜色相反**，用户首次看到容易迷惑（向上箭头却是绿色 = 跌？还是涨？）。

### 1.7 响应式
- `.ad-news-layout` 在 ≤991px 自动 `grid-template-columns: 1fr`（OK）。
- 但右栏 `dashboard-side-stack` 的 2 个 Panel 在 mobile 上垂直堆叠，**单标详情 Panel 在未选中时显示 EmptyState 占高度** → 浪费屏效。
- 热力图 `min-width: 120px` 在 360px 屏上会裁掉，仅 2-3 列。

### 1.8 小结（Sentiment）
最该修的是 **C5（颜色约定不响应切换）+ 1.5 的 POLL_SLICE_COLORS / detail-score-value 方向不一致**，以及 **1.6 mover 箭头颜色与方向反向**。

---

## 2. SentimentDashboard（情绪看板 / 单标的情绪）

文件：`web/src/pages/SentimentDashboard/index.tsx`（164 行，无 `styles.css`）

### 2.1 整体架构偏离项目约定
- **没有 `<PageShell maxWidth="wide">` 包裹**：在宽屏下内容会铺满整个 `Layout.Content`（1600px+），显得空旷。
- **没有 `<PageHeader>`**：用 `<h1 className="page-header-title">` + `<p className="page-header-description ad-mb-8">`。但 PageHeader 的 `data-onboard`、`tutorial` (新手模式教学)、`extra` 槽都没有 → **与项目其它页面 header 行为不一致**。
- `<GlassCard>` 直接包工具栏，但工具栏用 `phase5c-flex-wrap`，**没有用项目 `<FilterToolbar>`**，导致：
  - 无 `filter-toolbar__meta` 区域，无 `total` 显示
  - 无 `data-onboard` 锚点
  - 移动端没有统一的子项 `flex: 1 1 auto / min-width: 140px` 行为

### 2.2 工具栏布局
- 横向：`Input` + 文字"回溯 X 天" + `Slider` + `Button`。
- `Slider` 的 `min={1} max={30}` 长度无限制（不是自定义宽度），**在中宽屏下会把 Button 挤到第二行，且 Slider 会变长**。
- 文字"回溯 N 天" 与 Slider 中间的视觉关联弱（用户得知道 Slider 控制的是这个）。
- **"重要性 ≥" 这类一致 label 在本页面不存在**，对照 Sentiment 页使用 `<span className="ad-filter-label">重要性 ≥</span>` 风格 → 跨页 label 写法不统一。

### 2.3 结果卡片（SentimentCard）
- 单卡布局：图标 → 分数 40px → 主题标签 → bar → 计数 → 共 N 篇 · 近 N 天
- `ad-sentiment-bar` `max-width: 320px` + `margin: var(--space-lg) auto 0`：在窄屏 360px 下因 `max-width: 320px` 不会撑满，左右各 20px 居中 → OK 但若想横线视觉更明显，可以 `width: 100%` 拉满 Panel。
- "正/中/负" 计数 `ad-flex ad-justify-center ad-gap-5`：垂直方向上与上方 bar 之间无明确分隔（仅靠 5px gap）。
- 卡片下方"共 N 篇 · 近 N 天"信息密度低，与 `Period_days` 重复（`共 ... 文章 · 近 ... 天` 把两个值都打出但没解释）。
- **`sentiment-icon-wrapper` 字号走 `text-data-xl-size`，而图标自身 24px**，在 retina 屏下容易模糊。

### 2.4 空状态
- 用 Antd `<Empty description="输入标的代码开始情绪分析">`，**没有项目 `<EmptyState>` 的圆形 icon 背景**，视觉权重低于其它页面。

### 2.5 响应式
- 没有 PageShell → 在 ≤576px mobile 下，Slider 仍然是大宽度元素，可能顶出容器。
- GlassCard 自身 padding 在 mobile 是否收紧未确认。

### 2.6 小结（SentimentDashboard）
最该修的是 **C1（缺 PageShell/PageHeader）+ C2（空状态不一致）+ 2.2 工具栏应改用 FilterToolbar**。

---

## 3. CorrelationAnalysis（相关性分析）

文件：`web/src/pages/CorrelationAnalysis/index.tsx`（113 行）+ 空 `styles.css`（只注释）

### 3.1 配置面板布局
- 顶部 `<Panel title="相关性分析配置">` 内嵌 `<FilterToolbar>`：两层包装，外 Panel + 内 FilterToolbar，padding 重复。
- `<Row gutter={[16, 16]}>` + 三 `<Col xs={24} md={12/6/6}>`：在 mobile 下三列垂直堆叠（OK），但 InstrumentSelector 单独占满 1 行宽度 100%，Select 各占 1 行 100% → **mobile 屏空间利用率低**。
- **filter-label 与 Select 之间靠堆叠**：
  ```tsx
  <div className="ad-filter-label">窗口期：</div>
  <Select ... className="ad-w-full" />
  ```
  没有"label + control 一行"布局，**mobile 下每个控件都先 label 后控件垂直堆叠，浪费屏效**。

### 3.2 Select 文本
- `METHOD_OPTIONS` 的 label 用 `<HelpPopover>` 包裹 Pearson/Spearman，**hover 才有 tooltip**。但 Select 收起时显示的是 "Pearson / Spearman"，展开时也是同文字 → tooltip 仅在 chip 内有效，**用户第一次打开不知道含义**。
- "窗口期" 和 "计算方法" 标题都用 `:` 结尾 + 单独 div，**与项目其它页面 label 写法（直接跟 control）不一致**。

### 3.3 热力图布局
- 直接用 `<CorrelationHeatmap>`，外层包 `<div className="ad-chart-container">`。`ad-chart-container` 高度固定 `300px`，但 `<CorrelationHeatmap>` 内部 `style={{ height: isMobile ? 300 : 400 }}` → **外层 300px 与内层 400px 冲突**，容器被强制 300px 但 echarts 内部期望 400px。
- **正确做法**应该是用 `ad-chart-container--tall`（height: 420px）或去掉固定高度，让内部 echarts 决定。
- visualMap 横向放底部 `bottom: 0`，x 轴 label `rotate: 45` → 20 行 label 时底部空间 `60px` 偏紧，文字可能贴住 visualMap。

### 3.4 颜色方向
- `inRange.color = [colorFall, bgBase, colorRise]`，min=-1 max=1。
- 默认 dark 主题 `colorFall=#5fa87a`（绿）→ -1 显示绿色，+1 显示红色。
- **正负相关方向与"涨/跌"颜色方向相反**：colorRise=正相关，但"rise" 字面是涨 → 用户容易混淆。
- 没有读 `colorConvention`，**切换 A 股/美股配色后颜色方向不会变**。

### 3.5 响应式
- 配置行 `xs={24} md={12} md={6} md={6}` 在 ≤991px → InstrumentSelector 全宽、两个 Select 全宽堆叠（OK）。
- 热力图在 mobile height=300，但 mobile 标签 fontsize=8，视觉权重太弱。
- **mobile 下没有"全部重置/重新计算"按钮**（可能想换标的），用户得改完 3 个 Select 再等下一次 query。

### 3.6 标题与配置冗余
- 顶部 PageHeader "相关性分析" + description；紧接着又有一个 Panel "相关性分析配置"，**"相关性" 在 1 屏内出现 3 次**（title / panel / 实际图表）。

### 3.7 小结（CorrelationAnalysis）
最该修的是 **3.1 (label+control 一行布局) + 3.3 (ad-chart-container 高度冲突) + 3.4 (颜色方向)**。

---

## 4. Microstructure（微结构数据）

文件：`web/src/pages/Microstructure/index.tsx`（313 行）+ `styles.css`（28 行）

### 4.1 顶部 KPI 卡
- 4 张 `<Card><Statistic ... /></Card>`：
  - "最新龙虎榜条数" 带 `prefix={<FundOutlined />}` + `suffix="(2026-07-11)"`，其它 3 张没 prefix。
  - "北向净流入" 用 `detail-kpi-rise / detail-kpi-fall` 控制颜色，但**这两个 className 是在别的页面（detail 页）的 styles.css 定义的**，Microstructure 本地 styles.css 里的 `.microstructure__kpi-rise/fall` 反而是死代码（从未被引用）。
  - **跨页面样式耦合 + 本地 styles.css 失效 → 改名或搬过来**。
- 4 张卡视觉高度不一致（prefix 的那张因 padding 多 ~4px）。
- 与 Futures 页 `<StatCard>` 组件相比，Card+Statistic 没有统一的 token 化样式（font-mono、letter-spacing、value 字号都对不齐）。

### 4.2 工具栏
- `<FilterToolbar total={tabTotal}>`：`total` 是当前 tab 的数据量，**位置错位**（应当在 Tab 标签上以 badge 显示，而不是 toolbar meta）。
- `<Input>` 用 `phase5c-input--md` (220px) + `<Select>` `phase5c-select--xxs` (90px)：**`marginExchange` 仅在 `tab === 'margin'` 时出现**，切换 tab 时 DOM 中 Select 消失，**工具栏间距跳变**。
- 没有 Segment / Segmented，市场/分类筛选缺失（只有 tab 切换"数据类型"）。

### 4.3 Tabs（数据分类）
- 4 个 tab：**龙虎榜 / 沪深港通 / 融资融券 / 限售解禁**，全是文字。
- 缺图标 + 缺 badge 总数（如 `龙虎榜 (123)`）。
- mobile 4 个 tab 一行可能超出容器，需要横向滚动但没有视觉提示。

### 4.4 表格对齐
- 4 个 tab 各自 `columns` 写死 `width`（110/100/90/120/80）。
- **"原因"列 `ellipsis: true` 但没有 `Tooltip` 全文字**，hover 看不到完整原因。
- 数字列用 `tabular-nums` + `formatMoney` / `formatPct`：OK，但 `formatMoney` 转换 `亿 / 万 / 原值` 时**单位字号与数字一致**（没小一号），会让 1.23亿 看起来比 1.23 万更"重"。
- 表格在 1280px 容器下，4 张卡宽度加 columns 总和大概够；但 mobile 下 `scroll={{ x: 'max-content' }}` 横向滚动没有指示，用户不知道能滑。
- LHB 表 `name width: 100, ellipsis: true`：中文名称（如"贵州茅台"）OK，但有的名称 6 字会截断。

### 4.5 全量刷新按钮
- `extra={<Space><LastUpdated/><Button>全量刷新</Button></Space>}`：OK。
- 按钮 + LastUpdated 紧贴，没分隔（小问题）。

### 4.6 响应式
- KPI 4 张 `ResponsiveGrid cols={4}`：≤991px → 2 列；≤767px → 1 列。OK。
- Tab 在 mobile 横向溢出。
- 表格 mobile 横向滚动无指示。

### 4.7 小结（Microstructure）
最该修的是 **C4（跨页面样式耦合）+ 4.2（total 错位 + Select 跳变）+ 4.4（原因列缺 Tooltip）+ 4.3（Tab 缺 badge）**。

---

## 5. Futures（商品期货）

文件：`web/src/pages/Futures/index.tsx`（367 行，无 `styles.css`）

### 5.1 顶部 PageHeader
- 唯一用 `eyebrow="期货"` 的页面 → 与其它 4 页不一致（其它页没 eyebrow）。
- description 文字信息密度高，含"金属 / 能源化工 / 农产品 / 金融期货"分类 → description 实际上成了"分类列表"，**与下方 Tabs 重复**。

### 5.2 市场概况 Panel
- 4 张 StatCard（自定义 `StatCard`）：`主力合约总数 / K线记录总数 / 数据日期 / 领头羊 / 领跌`。
- 第 4 张"领头羊 / 领跌"：`value` 是 `<InstrumentCodeTag>` + `/` + `<InstrumentCodeTag>` 放在 `<span className="ad-flex ad-gap-2 ad-items-center">`。
  - 在 mobile `cols={4}` 退化为 1-2 列时，"领头羊 / 领跌" 这张卡可能因为两个 code 标签 + 斜杠导致**内部换行**。
  - StatCard 的 title 走 `text-transform: uppercase, letter-spacing: 0.12em`，中文"主力合约总数"会被强制 uppercase → **中文渲染不受影响，但字间距 0.12em 偏大**，对中文标题显得很散。

### 5.3 分类 Tabs
- 4 个 tab 用 emoji 作为图标：
  ```ts
  const PRODUCT_ICON: Record<Product, string> = {
    金属: '🟡',
    能源化工: '🛢️',
    农产品: '🌾',
    金融期货: '📊',
  };
  ```
- **emoji 渲染依赖 OS**，跨平台不一致（Windows 看 vs Mac 看 vs Linux 看会有差异）。
- emoji 与中文字符基线不对齐 → 标签视觉跳动（参考微调 padding 或固定 line-height）。
- Tab 内嵌 `<Tag>` 显示数量：
  ```tsx
  <Tag color={sectionsByProduct[p] ? 'blue' : 'default'} className="ad-ml-2">
    {sectionsByProduct[p]?.count ?? 0}
  </Tag>
  ```
- **Tab 标签内嵌 Tag 会让 4 个 tab 高度不一致**（含 Tag 的更高），且 Tag 的 border 让文字视觉重量变重。
- Antd Tabs 默认 `ink-bar` 与 tab 等高对齐，tab 高度不齐会让 ink-bar 看起来"漂"。

### 5.4 ProductTab 内部布局（每个板块）
- 顶部：`<Panel title="板块概况">` + `<ProductSummary>` → 3 个 Statistic：主力合约数 / 涨幅最大 / 跌幅最大。
- 中部：`<Row>` 内两个 Card（xs=24 md=12）：涨幅榜 TOP5、跌幅榜 TOP5。
- 底部：`<Panel title="全板块合约">` + BarTable。
- **信息冗余**：板块概况的"涨幅最大" = 涨幅榜 TOP5 第 1 名；"跌幅最大" = 跌幅榜 TOP5 第 1 名 → 同一数据出现 2 次。
- 3 个 Panel 之间间距靠 `ad-mb-5`，**没有视觉分组**（缺 section heading 或 divider）。

### 5.5 BarTable（涨跌榜 / 全板块合约）
- 5 列：代码 / 收盘 / 结算 / 涨跌 / 成交量，**每张表独立定义 columns**（重复代码 3 次）。
- `width: 120 / 90 / 90 / 90 / 100` 固定，mobile 横向滚动无指示。
- "涨跌"列 `changeCell(pct)`：
  - 用 `<CaretUpOutlined>` / `<CaretDownOutlined>` + 绝对值百分比。
  - 但实际显示是 `Math.abs(pct).toFixed(2) + '%'`，**总是正值**，所以 caret 与文字方向不严格一致（caret 是涨/跌方向，文字只给幅度）→ 用户需要点开看才知道涨跌。
  - **建议显示 `+1.23%` / `-0.45%` 带符号**（当前 best/worst performer 已带符号，但 BarTable 没带）。

### 5.6 颜色一致性
- `best_performer.suffix` 用 `detail-kpi-rise/fall` 类 → 与 Microstructure 同问题（C4），是跨页面样式耦合。
- 但 Tab 内嵌 Tag 的 `color="blue"` 是 Antd 蓝，**与项目 `--accent` / rise/fall 三色体系不一致**，信息维度多了一个"信息蓝"。

### 5.7 响应式
- 顶部 4 张 StatCard：≤991px → 2 列；≤767px → 1 列。但"领头羊 / 领跌"卡 mobile 下两个 InstrumentCodeTag + 斜杠可能挤到换行。
- ProductTab 中部两张 Card：≤991px → 1 列堆叠（OK）。
- 全板块合约表格 mobile 横向滚动无指示。
- Tabs 4 个 + emoji + Tag → mobile 大概率溢出横滑。

### 5.8 小结（Futures）
最该修的是 **5.3（Tab emoji + Tag 内嵌导致高度不齐）+ 5.4（板块概况与涨幅榜数据冗余）+ 5.5（涨跌 cell 缺正负号）+ 5.6（跨页面样式耦合）**。

---

## 6. 雷达图 / 分布图可读性专项

### 6.1 Sentiment DistributionRadar
- 80×80 SVG，5 轴（热度 / 看多 / 看空 / 中性 / 强度）。
- **问题**：
  - 字号 8px → 偏小。
  - **没有内网格圈**（只有外圆 + 数据 path + 轴标签）→ 看不出值梯度。
  - 5 个标签拥挤在半径 + 9 处，可能与外圆重叠。
  - "看多 / 看空 / 中性" 三个轴标签互相竞争（视觉上 3/5 都在讲"情绪比例"，信息冗余）。
  - 数据 shape 单色（warning-bright + dim 半透明），**对比度低**，在 light 主题下可能不够明显。

### 6.2 Sentiment PieBreakdown
- 56×56 SVG（多/空/中）。
- **问题**：
  - 无中心文字百分比。
  - hover 才有 Tooltip，**静态视觉信息仅靠颜色区分**，red/green/gray 颜色对比 OK 但**中性灰与背景对比度低**。
  - 三色比例若有 80/15/5，多空对比强烈但视觉上小圆被中央白圆吃掉。

### 6.3 Sentiment Sparkline
- 240×48 固定 → 详情面板 `ResponsiveGrid cols={2}` 中可能溢出。
- 14 日均值曲线，**没有 y 轴基线 / 平均线 / 当前值标记**。
- 颜色走 accent / rise/fall（取决于 score 正负），**没有图例或 hover tooltip**（user 看不到具体哪一天的值）。

### 6.4 建议
- 雷达图：补 2-3 个内网格圈 + 加大字号 + 重命名"看多/看空/中性"为更精简的"多/空/中"。
- Pie：补中心百分比 + 加大字号 + hover 显示中心。
- Sparkline：响应宽度 + 加 hover tooltip + 当前日标记。

---

## 7. 响应式专项

| 页面 | ≤991px (tablet) | ≤767px (mobile) | ≤576px (xs) |
| --- | --- | --- | --- |
| Sentiment | OK（ad-news-layout → 1 列） | OK（dashboard-side-stack 堆叠） | 热力图 1-3 列（拥挤） |
| SentimentDashboard | 无 PageShell，Slider 可能很宽 | 同 | 同 |
| CorrelationAnalysis | 配置 3 列变 3 行 | OK | OK |
| Microstructure | KPI 4→2 列 | KPI 4→1 列 | Tab 横向溢出，表格横向溢出 |
| Futures | KPI 4→2 列，ProductTab 涨/跌→1 列 | KPI 4→1 列 | Tab + emoji + Tag 极易溢出 |

### 7.1 移动端共性问题
- **表格横向滚动无指示**：5 页中 Microstructure 4 张表 + Futures BarTable 都用 `ad-table-scroll`，但用户不知道可以滑。
- **Tab 横向溢出无指示**：Microstructure 4 tab / Futures 4 tab + emoji + Tag。
- **emoji / 图标在小屏偏大**：Futures 的 emoji 🛢️ 在 mobile 上字号不变，相对 Tab label 占比变大。

---

## 8. 跨页面一致性总览

| 元素 | Sentiment | SentimentDashboard | CorrelationAnalysis | Microstructure | Futures |
| --- | --- | --- | --- | --- | --- |
| PageShell | ✓ wide | ✗ 缺失 | ✓ wide | ✓ wide | ✓ wide |
| PageHeader | ✓ + 图标 | ✗ 自写 h1 | ✓ | ✓ + extra | ✓ + eyebrow |
| PageHeader.eyebrow | ✗ | ✗ | ✗ | ✗ | ✓ "期货" |
| FilterToolbar | ✓ | ✗ 用 phase5c-flex-wrap | ✓ | ✓ | ✗ (Tabs 内) |
| EmptyState | ✓ 项目 | ✗ Antd Empty | ✓ | ✓ | ✓ |
| KPI 样式 | n/a | n/a | n/a | Card+Statistic | StatCard |
| 涨跌颜色 | 自定义（红=正） | n/a | 自定义（红=正） | detail-kpi-* | detail-kpi-* |
| colorConvention 支持 | ✗ | ✗ | ✗ | ✗ | ✗ |
| Tooltip / Badge | Tooltip | Tooltip | Tooltip | Tooltip | Tooltip |
| phase5c-* | icon-title / input--md / select--xxs | flex-wrap / form-row__grow | ✗ | icon-title / input--md / select--xxs | ✗ |
| styles.css | 无 | 无 | 空 | 死代码 | 无 |

---

## 9. 建议修复优先级（不实现，只排序）

### P0（视觉功能 / 一致性缺陷）
1. **Sentiment**：heatmap 与 detail-score-value 颜色方向不一致 + 不响应 `colorConvention` → 切换美股配色后方向反。
2. **Sentiment**：mover row 箭头方向与颜色反向（ArrowUp 绿色 / ArrowDown 红色） → 用户理解成本。
3. **SentimentDashboard**：缺 `PageShell` + `PageHeader` + `FilterToolbar` → 与项目其它页不一致。
4. **Microstructure**：顶部 4 张 KPI 引用别的页面的样式类 (`detail-kpi-rise/fall`) → 本地 styles.css 是死代码。

### P1（空间利用 / 视觉层级）
5. **Sentiment**：Sparkline / Pie / Radar 硬编码尺寸 + Radar 字号偏小 + 无网格。
6. **CorrelationAnalysis**：ad-chart-container 与 CorrelationHeatmap 高度冲突（300 vs 400）。
7. **CorrelationAnalysis**：label + control 垂直堆叠（应一行）。
8. **Microstructure**：Tab 缺 badge 总数 + FilterToolbar.total 错位。
9. **Futures**：Tab 内嵌 Tag 导致高度不齐 + emoji 渲染不一致。
10. **Futures**：板块概况"涨幅最大"与涨幅榜 TOP5 数据冗余。

### P2（响应式 / 跨页面）
11. **所有页**：表格 mobile 横向滚动无指示。
12. **所有页**：Tab mobile 横向溢出无指示。
13. **所有页**：`phase5c-*` 与 `ad-*` utility 共存，逐步收敛到 `ad-*`。
14. **Microstructure / Futures**：跨页面样式类 (`detail-kpi-rise/fall`) 应搬回各自本地 styles.css。
15. **CorrelationAnalysis**：空白 styles.css 删掉或加注释说明。

---

## 10. 附录：关键文件清单

| 文件 | 行数 | 说明 |
| --- | --- | --- |
| `/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/Sentiment/index.tsx` | 607 | 主页面，含 2 个手写 SVG (Pie/Radar) |
| `/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/SentimentDashboard/index.tsx` | 164 | 缺 PageShell / PageHeader |
| `/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/CorrelationAnalysis/index.tsx` | 113 | |
| `/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/CorrelationAnalysis/styles.css` | 14 | 仅注释 |
| `/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/Microstructure/index.tsx` | 313 | 4 tab + 4 table + 4 KPI |
| `/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/Microstructure/styles.css` | 28 | 死代码 |
| `/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/Futures/index.tsx` | 367 | emoji + Tag 内嵌 |
| `/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/styles/global.css` | 7000+ | 共享 utility + 散落的页级样式 |

> 报告结束。建议下一轮 sprint 先做 P0（4 项），再视 UI 重排 sprint 排 P1（6 项），P2 渐进收敛。