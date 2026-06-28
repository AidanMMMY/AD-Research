# 前端视觉改造设计文档：Swiss Minimal + Neon Cyan

**日期：** 2026-06-27  
**范围：** 投资研究平台 Web 前端（`web/` 目录）  
**类型：** 页面级视觉重构 + Design Token 刷新  
**状态：** 待实现

---

## 1. 项目概述

当前前端采用 React + Ant Design 5，视觉风格为深色科技感（Dark-first + Glassmorphism + Aurora Gradients），设计令牌集中在 `web/src/styles/theme.css`。用户反馈现有风格"太老套"、卡片滥用、信息层级不够清晰，希望通过借鉴欧洲现代设计、Microsoft Fluent、Apple Liquid Glass、Google Material You 等当代设计语言，升级为更现代、高级、简洁的视觉方案。

经过多轮视觉方向对比，最终确定采用 **Swiss Minimal（瑞士极简机构风）+ Neon Cyan（霓虹青）强调色** 的融合方案。

---

## 2. 设计目标

1. **提升高级感**：摆脱"科技蓝紫渐变疲劳"，转向克制、专业的机构金融气质。
2. **优化信息层级**：用排版、留白、线条替代卡片框，让数据本身成为视觉焦点。
3. **减少视觉噪音**：卡片、渐变、阴影、圆角全面克制，只在必要时使用。
4. **统一全平台体验**：所有核心页面按同一套视觉语言重构。
5. **保持开发可行性**：在现有 Ant Design 5 + CSS Variables 架构上实现，不引入新的 UI 框架。

---

## 3. 设计方向

### 3.1 名称

**Swiss Minimal + Neon Cyan**

### 3.2 灵感来源

- **Swiss International Style**：网格系统、强排版层级、大量留白、功能性优先。
- **European Fintech**：如 Revolut、Trade Republic、Lightyear 等产品的克制专业感。
- **Apple Liquid Glass**：有机的玻璃质感启发（局部使用，不主导）。
- **Microsoft Fluent**：Reveal Highlight 的边缘光效启发（表格 hover、侧边栏激活态）。

### 3.3 气质关键词

克制、专业、清晰、机构、数据优先、未来感。

---

## 4. 核心设计原则

### 4.1 卡片最少化

- 默认不使用卡片框区分内容区域。
- 用**细线分隔**、**留白**、**字号层级**来组织信息。
- 仅在以下场景允许使用卡片：
  - 模态框 / 抽屉 / 浮层
  - 需要明确与背景分离的交互容器
  - 部分 KPI 组合（可选，视页面而定）

### 4.2 排版即层级

- 页面大标题：26px / 500 / 紧凑字距
- 区域标签：10–11px / 500 / 大写 / 宽字距 / 灰色
- 核心数据：32–40px / 400–500 / 等宽或主字体
- 正文：13px / 400 / 灰色
- 辅助信息：11px / 400 / 更灰色

### 4.3 严格网格系统

- 基准间距：4px
- 常用间距：8 / 12 / 16 / 24 / 32 / 40 / 48 / 64
- 所有元素对齐到 8px 或 12px 网格，拒绝随意间距。

### 4.4 克制用色

- 背景：深灰黑单色系
- 文字：白 → 灰 → 深灰三阶
- 强调色：单一霓虹青（Neon Cyan），用于激活态、关键指标、标签、图表
- 市场色：保留红涨绿跌 / 绿涨红跌切换逻辑

### 4.5 圆角克制

- 默认直角或极小圆角。
- 仅在以下场景使用圆角：
  - 按钮：4px
  - 标签 / Chips：3–4px
  - 模态框 / 抽屉：12px
  - 极少数需要"柔和感"的面板：8px
- 表格、卡片、大面积面板避免大圆角。

### 4.6 数据优先

- 数字使用大字号、清晰对齐。
- ETF 代码、价格、收益率使用等宽字体。
- 涨跌颜色保持语义明确。

---

## 5. 视觉规范

### 5.1 色彩系统

#### 5.1.1 背景色

| Token | 色值 | 用途 |
|---|---|---|
| `--bg-base` | `#0a0a0a` | 页面主背景 |
| `--bg-elevated` | `#111111` | 侧边栏、模态框、抽屉、浮层 |
| `--bg-hover` | `rgba(255,255,255,0.03)` | 行 hover、按钮 hover |
| `--bg-active` | `rgba(255,255,255,0.05)` | 激活态背景 |
| `--bg-input` | `rgba(255,255,255,0.02)` | 输入框背景 |

#### 5.1.2 文字色

| Token | 色值 | 用途 |
|---|---|---|
| `--text-primary` | `#f5f5f5` | 主标题、核心数据 |
| `--text-secondary` | `#aaaaaa` | 正文、次要信息 |
| `--text-tertiary` | `#555555` | 标签、禁用、辅助说明 |
| `--text-muted` | `#3a3a3a` | 分割线、placeholder |

#### 5.1.3 强调色

| Token | 色值 | 用途 |
|---|---|---|
| `--accent` | `#22d3ee` | 主强调色：激活态、关键指标、标签边框、图表高亮 |
| `--accent-dim` | `rgba(34,211,238,0.08)` | 强调色浅背景 |
| `--accent-border` | `rgba(34,211,238,0.25)` | 强调色边框 |
| `--accent-glow` | `rgba(34,211,238,0.15)` | 光晕 / 阴影 |

#### 5.1.4 状态色

| 状态 | 色值 | 用途 |
|---|---|---|
| 成功（涨 / 正向） | `#22c55e` | 上涨、正向收益 |
| 错误（跌 / 负向） | `#ef4444` | 下跌、负向收益、错误 |
| 警告 | `#eab308` | 警告、中性偏负 |
| 信息 | `#22d3ee` | 提示、强调（与 accent 一致） |

#### 5.1.5 边框与分割线

| Token | 色值 | 用途 |
|---|---|---|
| `--border-default` | `rgba(255,255,255,0.06)` | 默认分隔线 |
| `--border-strong` | `rgba(255,255,255,0.10)` | 区域分隔线 |
| `--border-hover` | `rgba(255,255,255,0.12)` | hover 时边框 |
| `--border-accent` | `rgba(34,211,238,0.30)` | 强调色边框 |

### 5.2 字体系统

#### 5.2.1 字体栈

```css
--font-sans: "Inter", "SF Pro Display", -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
--font-mono: "JetBrains Mono", "SF Mono", "Fira Code", "Cascadia Code", monospace;
```

> 注：如引入 Inter / JetBrains Mono 需要添加到项目依赖，或保持系统字体作为 fallback。

#### 5.2.2 字号层级

| Token | 字号 | 字重 | 行高 | 字距 | 用途 |
|---|---|---|---|---|---|
| `--text-h1` | 26px | 500 | 1.2 | -0.03em | 页面大标题 |
| `--text-h2` | 20px | 500 | 1.3 | -0.02em | 卡片/面板标题 |
| `--text-h3` | 16px | 500 | 1.4 | -0.01em | 小节标题 |
| `--text-data-xl` | 40px | 400 | 1.1 | -0.04em | 核心大数字 |
| `--text-data-lg` | 24px | 400 | 1.2 | -0.02em | 次级数字 |
| `--text-data-md` | 16px | 500 | 1.3 | 0 | 普通数字 |
| `--text-body` | 13px | 400 | 1.6 | 0 | 正文 |
| `--text-small` | 11px | 500 | 1.4 | 0.05em | 小标签、辅助文字 |
| `--text-label` | 10px | 500 | 1.2 | 0.10em | 区域标签，大写 |
| `--text-code` | 12px | 400 | 1.4 | 0 | ETF 代码、价格 |

### 5.3 间距系统

| Token | 值 |
|---|---|
| `--space-1` | 4px |
| `--space-2` | 8px |
| `--space-3` | 12px |
| `--space-4` | 16px |
| `--space-5` | 24px |
| `--space-6` | 32px |
| `--space-7` | 40px |
| `--space-8` | 48px |
| `--space-9` | 64px |

### 5.4 圆角系统

| Token | 值 | 用途 |
|---|---|---|
| `--radius-none` | 0px | 表格、大面积面板 |
| `--radius-sm` | 3px | 标签、小徽章 |
| `--radius-md` | 4px | 按钮、输入框 |
| `--radius-lg` | 8px | 小面板、卡片（可选） |
| `--radius-xl` | 12px | 模态框、抽屉 |

### 5.5 阴影

阴影全面弱化，仅在浮层和模态使用：

| Token | 值 | 用途 |
|---|---|---|
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.2)` | 轻微浮起 |
| `--shadow-md` | `0 4px 16px rgba(0,0,0,0.3)` | 抽屉、下拉菜单 |
| `--shadow-lg` | `0 8px 32px rgba(0,0,0,0.4)` | 模态框 |

---

## 6. 组件规范

### 6.1 面板 / Panel（替代 GlassCard）

- 背景：`--bg-elevated` 或透明
- 边框：1px solid `--border-default`（可选）
- 圆角：0 或 `--radius-lg`（8px）
- 阴影：无
- 使用场景：确实需要与背景分离的内容组

### 6.2 表格 / Table

- 表头：10px 大写、灰色、底部 1px 分隔线
- 行：无背景色，hover 时文字变白 + 底部出现 subtle 强调线
- 单元格：左对齐，数字右对齐
- 边框：仅保留行底部细线
- 选中行：左侧 2px 霓虹青指示条

### 6.3 按钮 / Button

- Primary：霓虹青填充（`--accent`）+ 深色文字 + 4px 圆角
- Secondary：1px 白色/灰色边框 + 透明背景 + 4px 圆角
- Ghost：无背景，hover 时 `--bg-hover`
- 危险：红色边框或红色文字，保持扁平

### 6.4 侧边栏 / Sidebar

- 背景：`--bg-elevated`
- 菜单项：编号 + 图标 + 文字，灰色默认
- 激活态：白色文字 + 左侧 2px 霓虹青指示线
- hover：背景 `--bg-hover`
- 不使用大圆角和渐变背景

### 6.5 顶部导航 / Header

- 背景：`--bg-base` 或 `rgba(10,10,10,0.9)` + backdrop-blur
- 底部 1px 分隔线
- 内容：Logo、页面标题、用户操作
- 不使用阴影和复杂装饰

### 6.6 标签 / Tag

- 小尺寸（11px）
- 细边框或单色背景
- 圆角 3px
- 强调标签：霓虹青边框 + 霓虹青文字

### 6.7 输入框 / Input、Select

- 背景：`--bg-input`
- 边框：1px solid `--border-default`
- 圆角：4px
- 聚焦：边框变为 `--accent` + 0 0 0 2px `--accent-dim`

### 6.8 Tabs

- 下划线风格：选中态霓虹青下划线
- 或 Pill 风格：选中态霓虹青背景 + 深色文字
- 推荐下划线风格，更克制

### 6.9 图表

- 主色调：霓虹青渐变
- 辅助色：灰阶、成功绿、错误红
- 去除复杂渐变和发光，保持清晰可读

---

## 7. 页面重构范围

所有核心页面统一按 Swiss Minimal 风格重构：

### 7.1 Dashboard / 首页

- 顶部 Hero 区域：3 个核心大数字横向排列，用细线分隔
- 中部：左右分栏，左侧持仓表格，右侧收益走势图
- 减少卡片数量，用线条和留白区分模块

### 7.2 ETF / 股票列表页

- 顶部：极简 Filter Bar，搜索 + 少量筛选条件
- 主体：高密度表格，hover 高亮
- 移动端：列表视图同样扁平化

### 7.3 详情页（ETF、回测、策略、池子）

- Tab 改为下划线或 minimal pill 风格
- 内容分块用细线分隔
- KPI 区域可用扁平数字展示
- 图表和表格按新规范调整

### 7.4 筛选 / 评分 / 排名页

- 条件区与结果区明确分层
- 条件标签使用 neon cyan 强调
- 结果以表格为主，评分用数字或简单色块表示

### 7.5 通用布局

- 侧边栏 + 顶部 Header + 内容区统一调整
- 内容区 padding：桌面 32–40px，移动端 16px
- 页面最大宽度控制，避免过宽阅读困难

---

## 8. 实施阶段

### 阶段一：Design Token 刷新（1–2 天）

- 重写 `web/src/styles/theme.css` 中的颜色、字体、间距、圆角、阴影变量
- 更新 `web/src/main.tsx` 中的 Ant Design `ConfigProvider` token
- 更新 `web/src/styles/global.css` 中的全局覆盖

### 阶段二：通用组件改造（2–3 天）

- 改造 `GlassCard` → `Panel`（保留兼容或新建组件）
- 更新表格样式（全局 Ant Design Table 覆盖）
- 更新按钮、标签、输入框、Tabs、Sidebar、Header 样式
- 统一图表主题色

### 阶段三：页面级重构（3–5 天）

- 按第 7 节范围逐个页面调整布局和结构
- 优先改造 Dashboard、列表页、详情页
- 保持功能不变，只改视觉和布局

### 阶段四：细节打磨与动效（1–2 天）

- hover 状态统一
- 表格行高亮
- 侧边栏激活态
- 页面切换过渡（可选，保持克制）

### 阶段五：验收与回归测试

- 桌面端视觉走查
- 移动端适配检查
- 暗色主题一致性检查
- 交互功能回归

---

## 9. 关键文件清单

| 文件 | 变更内容 |
|---|---|
| `web/src/styles/theme.css` | 全面更新 Design Token |
| `web/src/styles/global.css` | 更新 Ant Design 组件覆盖 |
| `web/src/main.tsx` | 更新 Ant Design ConfigProvider token |
| `web/src/components/GlassCard.tsx` | 改造或新建 Panel 组件 |
| `web/src/components/GradientStatCard.tsx` | 改造为 Swiss 风格数据卡片 |
| `web/src/layouts/*` | 调整 Sidebar、Header 布局 |
| `web/src/pages/Dashboard/index.tsx` | 重构首页布局 |
| `web/src/pages/ETF*/index.tsx` | 重构列表和详情 |
| `web/src/pages/BacktestDetail/index.tsx` | 重构详情页 |
| `web/src/pages/PoolDetail/index.tsx` | 重构详情页 |
| `web/src/pages/ScoreRanking/index.tsx` | 重构排名页 |
| `web/src/pages/Screen/index.tsx` | 重构筛选页 |
| `web/src/pages/StrategyList/index.tsx` | 重构策略列表 |

---

## 10. 验收标准

- [ ] 所有页面不再滥用卡片和渐变
- [ ] 信息层级清晰，核心数据一眼可见
- [ ] 霓虹青强调色使用一致且克制
- [ ] 表格、按钮、标签、侧边栏符合新规范
- [ ] 桌面端和移动端均无视觉回归
- [ ] Ant Design 组件覆盖无冲突
- [ ] 动画和过渡保持克制，不喧宾夺主

---

## 11. 风险与注意事项

1. **Ant Design 覆盖复杂度**：全局 CSS 覆盖较多，需谨慎调整，避免破坏现有组件功能。
2. **图表库适配**：ECharts 和 lightweight-charts 的主题色需要同步更新。
3. **移动端信息密度**：Swiss Minimal 依赖留白，移动端需确保不浪费空间。
4. **用户习惯**：从玻璃拟态到极简风格变化较大，需要确保核心操作路径不受影响。
5. **字体引入**：如使用 Inter / JetBrains Mono，需评估加载性能和中文显示效果。

---

## 12. 附录：方向决策记录

| 决策项 | 选择 | 原因 |
|---|---|---|
| 整体方向 | Swiss Minimal | 用户要求高级感、少卡片、强排版 |
| 强调色 | Neon Cyan #22d3ee | 现代、在深色背景上清晰、区别于常见蓝紫 |
| 改动范围 | 页面级重构 | 覆盖全部核心页面，统一设计语言 |
| 卡片使用 | 克制使用 | 只在浮层、模态、部分 KPI 组使用 |
| 圆角 | 保留但克制 | 按钮 4px、标签 3px、模态 12px，大面板避免圆角 |
| 字体 | Inter + JetBrains Mono | 现代、清晰、适合数据和标题 |

---

*本设计文档经用户确认后，将进入 implementation plan 阶段。*
