# AD-Research 前端重构设计综合报告

> 编制日期：2026-07-11
> 来源：竞品平台设计调研 + 无障碍/色彩/动效/暗色模式标准文档的综合整理
> 范围：AD-Research 投研平台前端重构的全局设计方向与可落地建议
>
> **注**：本文为时点综合报告。与现状（2026-07-21 核实）的差异：主强调色已由朱色 `#E11D48` 切换为蓝靛 `#2563EB`（朱红经 `data-accent="vermilion"` 保留）；默认主题实际落地为**暗色优先**（dark-first），而非本报告建议的浅色默认；三档信息密度、多市场涨跌色切换（`data-color-convention`）、涨跌色冗余等 P0 项已实现。

---

## 目录

1. [执行摘要](#1-执行摘要)
2. [设计原则与全局标准](#2-设计原则与全局标准)
3. [竞品平台详细分析](#3-竞品平台详细分析)
4. [AD-Research 可落地建议清单](#4-ad-research-可落地建议清单)
5. [两份来源的比对与冲突分析](#5-两份来源的比对与冲突分析)
6. [自我审计](#6-自我审计)

---

## 1. 执行摘要

本报告综合了 9 个竞品平台的 UI/UX 调研与 WCAG 2.2 / Apple HIG / Material Design 3 相关的设计标准，形成 AD-Research 前端重构的完整设计输入。

**核心结论：**

- 默认方向应为 **浅色清爽主调 + 深色模式可选**，避免纯深色 "terminal" 作为唯一主题。
- 涨跌颜色必须 **四重冗余**：颜色 + ▲▼ 箭头 + +/− 符号 + 文字标签，并默认提供色盲安全模式。
- K 线涨跌主色建议采用 Okabe-Ito 蓝 `#0072B2` + 橙 `#E69F00`，替代传统红绿。
- 提供 **三档信息密度**（Compact / Comfortable / Spacious），满足不同专业度用户。
- 必须尊重 `prefers-reduced-motion` 和 `prefers-color-scheme`。
- 移动端采用底部 Tab Bar，桌面端采用模块化 Dashboard + 可拖拽面板。

**关键产出：**

| 文档 | 作用 |
|---|---|
| 本综合报告 | 统一设计方向与落地清单 |
| `20260711-competitor-design-survey.md` | 9 个竞品平台原始分析 |
| `20260711-design-standards-a11y-color-motion.md` | 无障碍/色彩/动效/暗色模式技术细节与代码示例 |

---

## 2. 设计原则与全局标准

### 2.1 无障碍（Accessibility）

#### 2.1.1 减少动效（Reduced Motion）

- **标准**：WCAG 2.2 Success Criterion 2.3.3（Animation from Interactions）。
- **实现**：通过 `@media (prefers-reduced-motion: reduce)` 全局重置。
- **投研平台实战**：
  - 价格颜色闪烁：瞬间切换，无渐变。
  - Sparkline：直接重绘，无 tween。
  - 数字 ticker：直接跳变，无 count-up。
  - **保留**：加载 spinner、实时数据到来、滚动位置更新。

#### 2.1.2 色盲安全

- **推荐调色板**：Okabe-Ito 8 色。

| Hex | 通用名 |
|---|---|
| `#000000` | 黑色 |
| `#E69F00` | 橙色 |
| `#56B4E9` | 天蓝 |
| `#009E73` | 蓝绿 |
| `#F0E442` | 黄色 |
| `#0072B2` | 蓝色 |
| `#D55E00` | 朱红 |
| `#CC79A7` | 紫红 |

- **涨跌颜色**：蓝 `#0072B2` + 橙 `#E69F00` 作主色，辅以 ▲▼ 箭头、+/− 符号、文字标签四重冗余。
- **热力图/多序列**：Viridis / Cividis / ColorBrewer。
- **工具**：Coblis、Colorblindly、Stark、Sim Daltonism、Color Oracle、Who Can Use。

#### 2.1.3 暗色模式

- **实现**：`prefers-color-scheme` + `color-scheme: light dark` + `light-dark()` 函数。
- **模式**：系统默认 → 用户覆盖（Light / Dark / System）→ localStorage 持久化。
- **防 FOWT**：内联阻塞 `<script>` 在 `<head>` 早期设 `document.documentElement.dataset.theme`。
- **案例**：Bloomberg Terminal 仅 dark；Robinhood iOS/Android 默认 dark 但可切 light；Stripe Dashboard 三档 toggle。

### 2.2 信息架构

- **首屏**：一屏一事，Hero 只放品牌价值主张和单一 CTA。
- **导航**：
  - 移动端：底部 Tab Bar（≤5 项）。
  - 桌面端：顶部导航 + 模块化 Dashboard。
- **数据密度**：提供 Compact / Comfortable / Spacious 三档。
- **响应式**：mobile-first，断点 375 / 768 / 1024 / 1440。

### 2.3 色彩与字体

- **强调色**：项目已确认朱色 `#E11D48`（rose-600），用于主按钮、链接、激活态。
- **涨跌约定**：
  - A 股：红涨绿跌（`#dc2626` / `#16a34a`）。
  - 美股/国际：绿涨红跌。
  - 色盲模式：蓝 `#0072B2` + 橙 `#E69F00`。
- **字体栈**：`Inter, "SF Pro Display", -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif`。
- **数据字体**：等宽 `JetBrains Mono`，用于价格、涨跌幅、代码。

---

## 3. 竞品平台详细分析

### 3.1 Robinhood — 美国家庭零售券商

- **首屏**：全屏 Hero 视频/动画 + 单一 CTA。
- **色彩**：默认深色 `#110E08`，霓虹绿 `#CCFF00` 强调色。
- **字体**：自研 `Capsule Sans Text` + 衬线 `Nib Pro Display`。
- **移动端**：底部 Tab Bar（Home / Moves / Investing / Messages / Account）。
- **可借鉴**：极简 CTA、自研字体品牌感、数据卡片大字号关键数字。

### 3.2 Webull 微牛 — 中美跨境零售

- **首屏**：市场数据概览 + 指数 ticker + 下载 App CTA。
- **色彩**：白色底、深灰蓝文本 `#2B3240`、绿涨红跌（中国版红涨绿跌）。
- **字体**：OpenSansV2 + NotoSans + HarmonyOSSans。
- **图表**：60+ 技术指标、Canvas/WebGL、自选列表实时高亮闪烁。
- **可借鉴**：多语言字体栈、三层阴影层级、社区 Feed 集成、多层筛选器。

### 3.3 Interactive Brokers — 专业机构

- **产品**：TWS（桌面多窗口）、Client Portal（Web 简化）、IBKR Mobile。
- **布局**：Mosaic 可拼贴窗口系统，数据密度极高。
- **色彩**：白/灰底为主，蓝色系强调。
- **可借鉴**：三档信息密度、模块化 Dashboard、快捷键驱动。

### 3.4 TradingView — 图表与社区

- **核心**：交互式图表引擎占首屏 70%+。
- **色彩**：亮色 `#FFFFFF` / 暗色 `#131722`，K 线涨 `#26A69A` / 跌 `#EF5350`。
- **特色**：提供 **Color Blind** 预设；Pine Script 指标生态；多时间周期联动。
- **可借鉴**：图表嵌入 Widget、色盲模式、深色/亮色双主题。

### 3.5 富途牛牛 Futu — 港股/美股/A 股

- **产品**：桌面 Qt 版 + iOS/Android/HarmonyOS App。
- **首屏**：自选行情 + 市场概览 + 资讯 Feed + 牛牛圈社区。
- **特色**：毫秒级行情、AI 走势预测、六端全覆盖。
- **色彩**：中国版红涨绿跌，香港版绿涨红跌。
- **可借鉴**：多市场颜色自适应、社区 + 交易一体化、全平台策略。

### 3.6 Tiger Brokers 老虎证券 — 跨境零售

- **定位**：全球华人投资者，移动优先。
- **特色**：深色主题、老虎社区、模拟交易教学。
- **可借鉴**：社区 UGC + 交易、新手引导内置。

### 3.7 Public.com — 社交化投资

- **核心**：社交 Feed 替代传统行情作为首屏。
- **设计**：卡片式内容、柔和品牌蓝、教育性 UI。
- **可借鉴**：社交优先 IA、教育嵌入模块、碎片投资降低门槛。

### 3.8 Seeking Alpha — 投研内容社区

- **架构**：Latest / Top Stocks / ETFs / Dividends / Podcast / Marketplace。
- **特色**：Quant Ratings（Strong Buy → Strong Sell 五档）、阶梯式付费墙、作者生态。
- **色彩**：品牌橙 `#ff7200`。
- **可借鉴**：量化评级可视化、付费墙设计、分析师 Marketplace。

### 3.9 FinChat — AI 投研对话

- **技术栈**：Astro 框架。
- **核心**：ChatGPT 式对话 UI，自然语言 → 结构化数据 + 图表。
- **商业模式**：Free / Plus $29/mo / Pro $79/mo。
- **可借鉴**：AI 对话式投研、自然语言查询、SaaS 定价卡片。

---

## 4. AD-Research 可落地建议清单

### P0 — 必须实现（重构 MVP 阻塞项）

| ID | 建议 | 参考来源 |
|---|---|---|
| P0-1 | 浅色模式默认 + 深色模式可选；用 `light-dark()` 统一 token | Robinhood、TradingView、标准文档 §3 |
| P0-2 | 涨跌颜色四重冗余：颜色 + ▲▼ + +/− + 文字标签 | TradingView 色盲模式、标准文档 §2.7 |
| P0-3 | K 线涨跌主色采用 Okabe-Ito 蓝 `#0072B2` + 橙 `#E69F00`（色盲模式） | 标准文档 §2.5、竞品报告 P0-3 |
| P0-4 | 提供三档信息密度：Compact / Comfortable / Spacious | IBKR TWS §3.3 |
| P0-5 | `prefers-reduced-motion` 适配：价格闪烁/Sparkline 在 reduce 时 0ms | WCAG 2.2、Robinhood、标准文档 §1 |
| P0-6 | 自选列表实时价格更新 + 颜色闪烁（`motion-safe:` 限定） | Webull、富途 |
| P0-7 | 多市场颜色自适应：A 股红涨绿跌 vs 美股绿涨红跌 | 富途牛牛 §5.2 |
| P0-8 | 键盘焦点环可见、tab 导航顺序符合视觉顺序 | WCAG 2.1 / 标准文档 |

### P1 — 应该实现（v1.0 质量目标）

| ID | 建议 | 参考来源 |
|---|---|---|
| P1-1 | 模块化 Dashboard：用户可拖拽/调整面板布局 | IBKR TWS Mosaic |
| P1-2 | 图表嵌入 Widget（复用 TradingView charting_library） | TradingView |
| P1-3 | 移动端底部 Tab Bar 导航（自选/行情/研究/AI/设置） | Robinhood、富途 |
| P1-4 | 数据卡片大字号关键数字 + Sparkline 迷你趋势图 | Robinhood、Webull |
| P1-5 | 筛选器面板（市值/行业/指标多条件筛选） | Webull、TradingView |
| P1-6 | 色盲模式 Toggle（一键切换 Okabe-Ito 调色板） | TradingView Color Blind |
| P1-7 | 响应式断点：mobile-first，375 / 768 / 1024 / 1440 | Robinhood Next.js |
| P1-8 | 社区/讨论集成（UGC 投资观点与行情同屏） | Public.com、富途牛牛圈 |
| P1-9 | 暗色模式三档 toggle：Light / Dark / System | Stripe Dashboard |

### P2 — 建议实现（v1.5+ 差异化）

| ID | 建议 | 参考来源 |
|---|---|---|
| P2-1 | AI 对话式投研界面（自然语言 → 结构化数据 + 图表） | FinChat |
| P2-2 | 量化评级系统（五档可视化评分） | Seeking Alpha Quant Ratings |
| P2-3 | 分析师/策略 Marketplace（UGC 订阅制） | Seeking Alpha Marketplace |
| P2-4 | 教育嵌入模块（每个资产页 Why/How 解释投资逻辑） | Public.com |
| P2-5 | 自定义字体品牌感（Inter 或自研几何无衬线） | Robinhood Capsule Sans |
| P2-6 | Pine Script 式自定义指标/策略脚本 | TradingView |
| P2-7 | 六端全覆盖（iOS / Android / HarmonyOS / macOS / Windows / Web） | 富途牛牛 |

---

## 5. 两份来源的比对与冲突分析

### 5.1 相同点

| 主题 | 竞品报告 | 标准文档 |
|---|---|---|
| 默认深色 vs 浅色 | Robinhood 默认 dark，建议 AD-Research dark 可选 | 详述 dark/light 实现，案例含 Robinhood |
| 涨跌颜色冗余 | 四重冗余（颜色+箭头+符号+标签） | 四重冗余 + Okabe-Ito 具体 hex |
| 色盲模式 | TradingView Color Blind 预设 | Okabe-Ito 调色板、工具链 |
| 减少动效 | Robinhood 尊重 Reduce Motion | WCAG 2.3.3 完整实现指南 |
| 多市场颜色 | 富途牛牛红涨/绿涨自适应 | 未直接提及，但与标准不冲突 |

### 5.2 不同点

| 维度 | 竞品报告 | 标准文档 |
|---|---|---|
| 侧重点 | 具体平台分析、信息架构、设计建议 | 技术实现、CSS 代码、无障碍标准 |
| 平台覆盖 | 9 个竞品 | 主要引用 Bloomberg / Robinhood / Stripe / TradingView |
| 深度 | 平台级设计模式 | 代码级实现标准 |
| 输出形式 | P0/P1/P2 建议清单 | 推荐清单 + 代码示例 |

### 5.3 冲突点

**经比对，两份报告在核心设计决策上无冲突。**

唯一需要补充说明的是：

- **竞品报告**建议 K 线用蓝 `#0072B2` + 橙 `#E69F00` 替代红绿。
- **标准文档**同样建议蓝 `#0072B2` + 橙 `#E69F00`，并强调四重冗余。
- **结论**：两者完全一致，本综合报告直接采用该方案。

**待用户确认的非冲突项：**

1. AD-Research 是否仍保留「红涨绿跌/绿涨红跌」作为默认模式，仅把 Okabe-Ito 作为「色盲模式」toggle？
2. 朱色 `#E11D48` 强调色与 Okabe-Ito 蓝橙如何搭配使用（主按钮仍用朱色，K 线用蓝橙）？

---

## 6. 自我审计

### 6.1 一手来源 URL 列表

| # | URL | 来源文档 |
|---|---|---|
| 1 | https://robinhood.com/us/en/ | 竞品报告 |
| 2 | https://www.webull.com | 竞品报告 |
| 3 | https://www.futunn.com | 竞品报告 |
| 4 | https://seekingalpha.com | 竞品报告 |
| 5 | https://finchat.io | 竞品报告 |
| 6 | https://www.interactivebrokers.com/en/trading/tws.php | 竞品报告 |
| 7 | https://www.tradingview.com/chart/ | 竞品报告 |
| 8 | https://public.com | 竞品报告 |
| 9 | https://www.itiger.com | 竞品报告 |
| 10 | https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html | 标准文档 |
| 11 | https://jfly.uni-koeln.de/color/ | 标准文档 |
| 12 | https://developer.mozilla.org/en-US/docs/Web/CSS/color_value/light-dark | 标准文档 |

### 6.2 低置信度结论

1. IBKR TWS 具体色彩 token：未获取到 CSS，基于行业知识推断。**置信度：中**
2. Tiger Brokers 具体 UI 布局：未能获取页面源码。**置信度：中低**
3. Public.com 当前 UI 设计：SPA 需 JS 渲染。**置信度：中**
4. FinChat 定价/功能细节：Vercel 安全拦截。**置信度：中**

### 6.3 需要用户补充资料的事项

1. 富途牛牛 App 实际截图。
2. Tiger Brokers App 截图。
3. IBKR Client Portal 当前版本截图。
4. AD-Research 当前前端技术栈确认（React/Next.js 是否准确）。
5. 目标用户画像：零售投资者 / 专业分析师 / 机构交易员比例。
6. 涨跌颜色默认策略：红绿默认 + 色盲模式 toggle，还是默认 Okabe-Ito？

---

*综合报告生成时间：2026-07-11 (Asia/Shanghai)*
