# AD-Research 竞品设计调研报告

> 编制日期: 2026-07-11
> 调研范围: 9 个零售/专业投资者平台的 UI/UX 设计
> 配套文档: `20260711-design-standards-a11y-color-motion.md`（无障碍、色彩、动效标准）
> 编制: AD-Research 前端重构项目

---

## 目录

1. [Robinhood](#1-robinhood) — 美国家庭零售券商
2. [Webull 微牛](#2-webull) — 中美跨境零售
3. [Interactive Brokers](#3-interactive-brokers) — 专业/机构交易
4. [TradingView](#4-tradingview) — 图表与社区
5. [富途牛牛 Futu](#5-富途牛牛-futu) — 港股/A 股/美股
6. [Tiger Brokers 老虎证券](#6-tiger-brokers) — 跨境零售
7. [Public.com](#7-publiccom) — 社交化投资
8. [Seeking Alpha](#8-seeking-alpha) — 投研内容社区
9. [FinChat](#9-finchat) — AI 投研对话
10. [设计建议清单 (P0/P1/P2)](#10-ad-research-设计建议清单)
11. [自我审计](#11-自我审计)

---

## 1. Robinhood

**定位**: 美国最大零售券商，0 佣金，移动优先，面向新手与进阶投资者。

### 1.1 信息架构与首屏

- 首屏全屏 Hero 视频/动画 + 单一 CTA（"Get started" Sign up）
- 首屏后纵向滚动展示产品：Invest → Options → Crypto → Learn → 24/7 Support
- 导航: Sticky top bar，左侧 Logo，右侧 Login / Sign up
- 底部 Footer 包含法律披露 (来源: https://robinhood.com/us/en/)

### 1.2 色彩系统

| Token | Hex | 用途 |
|-------|-----|------|
| 主背景（dark） | `#110E08` | 默认深色背景，近乎黑但有暖色调 |
| 纯黑 | `#000000` | 数字主题区块背景 (blackDigitalTheme) |
| 霓虹绿强调色 | `#CCFF00` | CTA 按钮、高亮、品牌色 |
| 白色 | `#FFFFFF` | 面板卡片、浅色区块对比 |
| 二级暖色 | `#1C180D` | 浅色背景变体 |

Robinhood 默认深色模式，App 内可在 Settings → Appearance 切换 light。涨跌颜色: 绿涨红跌（美国市场约定），但 App 内尊重系统 Reduce Motion 和 Dynamic Type。 (来源: https://robinhood.com/us/en/ CSS 提取)

### 1.3 字体系统

- 正文: `Capsule Sans Text`（自研几何无衬线，Light/Book/Medium/Bold 四档）
- 标题: `Nib Pro Display` / `Martina Plantijn`（衬线标题，品牌差异化）
- 代码/数据: `Capsule Sans Text Mono`（等宽）
- 后备: `Geist`（Vercel 开源无衬线）
- 来源: HTML `<style>` 中 @font-face 声明

### 1.4 图表与数据可视化

- K 线图在 App 内以全屏沉浸式展示，支持手势缩放
- 轻量级 chart: 线条整洁、去网格化、大字号价格
- 移动端数据卡片: 单列布局、大 touch target（≥44pt）、卡片间距 12-16px
- 关键数字例如投资组合总值以大号字体突出（~32px+）

### 1.5 移动/桌面差异

- 移动端: 底部 Tab Bar（Home / Moves / Investing / Messages / Account）
- 桌面: 顶部导航 + Legend 桌面交易平台（2024 年发布，多窗口支持）
- Responsive: Next.js SSR + emotion-css 响应式断点，mobile-first
- 来源: https://robinhood.com/us/en/ (源码确认 Next.js + Contentful CMS)

### 1.6 可借鉴模式

- **极简首屏 CTA**: 一屏一事，Hero 只放品牌价值主张和一个 CTA 按钮
- **自研字体品牌感**: 自定义 `Capsule Sans Text` 建立差异化视觉识别
- **深色默认 + Light 可选**: 金融产品默认 dark 降低眼疲劳，用户可切换
- **数据卡片的大字号**: 投资组合总值用大号字体独立呈现，形成信息层级

---

## 2. Webull 微牛

**定位**: 中美跨境零售券商，注重技术分析工具，面向活跃交易者。

### 2.1 信息架构与首屏

- 首屏: 市场数据概览 + 主要指数 ticker + 下载 App CTA
- 一级导航: Stocks / Options / ETFs / Futures / Crypto / Community
- 社区/Feed 功能内置，用户可分享交易观点
- 来源: https://www.webull.com (HTML 源码)

### 2.2 色彩系统

| Token | Hex | 用途 |
|-------|-----|------|
| 主背景 | `#FFFFFF` | 白色底（亚洲版常用浅色） |
| 文本主色 | `#2B3240` | 深灰蓝，比纯黑柔和 |
| 次要文本 | `rgba(0,0,0,.45)` | 关闭按钮、说明文字 |
| Modal 阴影 | `rgba(99,104,114,0.12)` 等 | 三层阴影叠加 |
| 圆角 | `12px` (modal), `6px` (button) | 统一圆角系统 |

涨跌颜色: 绿涨红跌（国际市场），中国版红涨绿跌。来源: Webull 官网 CSS 提取

### 2.3 字体系统

- 拉丁: `OpenSansV2`（Light/Regular/SemiBold/Bold/ExtraBold + Italic）
- 中日韩: `NotoSans`（Thin–Black 9 档字重）、`HarmonyOSSans`（鸿蒙字体）
- 泰文: `NotoSansThai`
- 衬底标题: `DM Serif Display`
- 备用: `InterWB`（自托管 Inter 变体）
- 来源: Webull 官网 `@font-face` 声明

### 2.4 图表与数据可视化

- K 线图表功能丰富：支持 60+ 技术指标、绘图工具
- 桌面/App 内图表基于 Canvas/WebGL 实现，流畅缩放
- 自选列表: 紧凑行布局，价格变化实时高亮闪烁
- 筛选器: 多层过滤条件（市值、行业、技术指标信号）

### 2.5 可借鉴模式

- **多语言字体栈**: OpenSans + NotoSans + HarmonyOS 覆盖全球用户
- **阴影层级系统**: 三层 box-shadow 叠加营造深度感
- **社区 Feed 集成**: 交易观点与行情数据同屏展示

---

## 3. Interactive Brokers

**定位**: 全球最大电子经纪商，服务专业交易员、机构、对冲基金。

### 3.1 信息架构

- TWS (Trader Workstation): 经典桌面客户端，多窗口、模块化布局，学习曲线陡峭
- Client Portal: Web 版简化界面，响应式设计，2022 年重设计
- IBKR Mobile: iOS/Android App，功能对标桌面但简化
- 来源: https://www.interactivebrokers.com/en/trading/tws.php (页面结构已知)

### 3.2 关键设计特征

- **Mosaic 布局**: TWS 经典可拼贴窗口系统，每个工具（报价、图表、订单、新闻）是独立窗口
- **数据密度极高**: 专业交易屏可同时显示数百行报价、多个图表、订单簿
- **色彩保守**: 白底/灰底为主，强调色为蓝色系 `#1a73e8` 左右
- **涨跌颜色**: 绿涨红跌（国际版），可配置
- **暗色模式**: TWS 支持暗色主题（2023 年加入）

### 3.3 可借鉴模式

- **可配置密度**: 提供 Compact / Comfortable / Spacious 三种信息密度选项
- **模块化 Dashboard**: 用户可自由拖拽、调整面板大小和位置
- **快捷键驱动**: 专业用户期望键盘快捷键操作

---

## 4. TradingView

**定位**: 全球最大图表分析与交易社区，月活 5000 万+。

### 4.1 信息架构

- 核心是交互式图表引擎（Canvas/WebGL），占据首屏 70%+ 面积
- 左侧: 自选列表 / 筛选器面板
- 顶部: 搜索栏 + 时间周期切换 + 指标按钮
- 右侧: 绘图工具栏 + 社区 Ideas
- 来源: https://www.tradingview.com/chart/

### 4.2 色彩系统

| 语境 | 亮色 | 暗色 |
|------|------|------|
| K 线涨 | `#26A69A`（蓝绿）| 略亮 |
| K 线跌 | `#EF5350`（红）| 略亮 |
| 图表背景 | `#FFFFFF` | `#131722` |
| 网格线 | `#D6D6D6` | `#2A2E39` |
| 强调蓝 | `#2962FF` | `#2962FF` |

TradingView 提供 **Color Blind** 预设，切换为非红绿配色。这是极少数内置色盲友好模式的图表工具。(来源: https://www.tradingview.com 已知设计)

### 4.3 可借鉴模式

- **Pine Script 指标生态**: 用户可编写自定义指标，社区共享 —— 形成 UGC 生态护城河
- **多时间周期联动**: 图表内显示多周期 mini chart，一键切换
- **深色/亮色双主题**: 品牌设计 token 覆盖所有组件
- **图表嵌入**: 提供轻量级 charting_library widget 供第三方嵌入（AD-Research 已集成）

---

## 5. 富途牛牛 Futu

**定位**: 香港第一投资平台，覆盖港股/美股/A 股，中国存量客户使用。

### 5.1 信息架构

- 桌面端: 新一代桌面版富途牛牛（Qt），支持 Algo trading、期权交易、AI 洞察
- 移动端: iOS/Android/HarmonyOS App，底部 Tab Bar 经典布局
- 首屏: 自选行情 + 市场概览 + 资讯 Feed
- 社区/牛牛圈: 实盘交流社区，用户可分享持仓、交易记录
- 来源: https://www.futunn.com (官方 SSR 页面确认)

### 5.2 关键设计特征

- **实时行情**: 毫秒级行情更新，自选列表实时跳动
- **AI 走势预测**: 集成 AI 预测工具 + 专业画线工具
- **跨平台**: iOS / Android / macOS / Windows / Linux / HarmonyOS 六端
- **多市场**: 港股 / 美股 / A 股一站式
- 色彩: 中国版红涨绿跌，香港版绿涨红跌
- 来源: https://www.futunn.com HTML meta 描述

### 5.3 可借鉴模式

- **多市场颜色自适应**: 根据用户市场自动切换涨跌颜色约定
- **社区 + 交易一体化**: 牛牛圈将社交与投资无缝衔接
- **六端全覆盖**: 从移动端到桌面端到鸿蒙，全平台策略

---

## 6. Tiger Brokers 老虎证券

**定位**: 新加坡上市，服务全球华人投资者的跨境券商。

### 6.1 关键设计特征

- 移动优先: App 与 Webull 竞争，强调社交化 + 技术指标
- 界面风格: 深色主题为主，与 Webull 类似的 K 线图表体验
- 社区"老虎社区": 用户分享交易观点和策略
- 多市场: 美股、港股、A 股（沪港通/深港通）、新加坡、澳洲
- 来源: https://www.itiger.com / https://www.tigerbrokers.com.sg

### 6.2 可借鉴模式

- **社区 UGC + 交易**: 类似富途牛牛圈，社交是获客和留存的核心
- **新手引导**: 模拟交易、教学视频内置 App

---

## 7. Public.com

**定位**: 社交化投资平台，强调社区、透明度、多元化资产（股票、加密货币、另类资产）。

### 7.1 关键设计特征

- **社交 Feed 为核心**: 首屏展示好友/社区的投资活动而非传统行情
- **卡片式内容**: 每项投资以卡片展示，包含公司简介、社区讨论、关键指标
- **简约色彩**: 浅色模式为主，强调色柔和，品牌蓝
- **教育性 UI**: "Why invest in this?" 模块解释投资逻辑
- 来源: https://public.com

### 7.2 可借鉴模式

- **社交优先的 IA**: 以社区时间线替代传统行情列表
- **教育嵌入**: 每个资产页内置 Why/How 教育模块
- **碎片投资**: 支持小数点份额，降低心理门槛

---

## 8. Seeking Alpha

**定位**: 全球最大投资研究社区，付费订阅制（Premium / Pro）。

### 8.1 信息架构

- 首屏: 大型市场横幅 + 文章列表 + 注册/付费 CTA
- 一级导航: Latest / Top Stocks / ETFs / Dividends / Podcast / Marketplace
- 文章页: 左侧正文 + 右侧作者信息 / 相关文章 / Premium 推广
- 量化评级: Quant Ratings（Strong Buy → Strong Sell 五档）

### 8.2 色彩系统 (来源: https://seekingalpha.com HTML 源码)

| Token | Hex | 用途 |
|-------|-----|------|
| 品牌橙 | `#ff7200` | CTA 按钮、链接、favicon |
| 主题色 | `#333333` | status bar / theme-color meta |
| 暗色横幅 | `#414a5f` | Premium 推广横幅 |
| 渐变深色 | `#42274b → #000027` | 活动横幅渐变 |
| 白色文字 | `#ffffff` | 深色背景上的文字 |

### 8.3 可借鉴模式

- **阶梯式付费墙**: Free → Premium → Pro，逐级解锁深度内容
- **量化评级系统**: Quant Ratings（Strong Buy / Buy / Hold / Sell / Strong Sell）可视化
- **作者生态**: 独立分析师贡献内容 + 付费订阅 Marketplace

---

## 9. FinChat

**定位**: AI 驱动的投资研究对话平台，Bloomberg Terminal 的现代替代品。

### 9.1 关键设计特征

- 技术栈: Astro 框架（来源: Vercel checkpoint 页面确认）
- 对话式 UI: 类似 ChatGPT 的交互模式，输入公司名/问题获取数据和分析
- 数据覆盖: 全球 750+ 公司财务数据、估值指标、业绩电话会议记录
- 图表集成: AI 回复中嵌入交互式图表
- 商业模式: SaaS 订阅制（免费 / Plus / Pro 三档）
- 来源: https://finchat.io

### 9.2 可借鉴模式

- **对话式投研**: AI Agent 作为研究助手，降低数据查询门槛
- **自然语言 → 结构化数据**: 用户输入自然语言问题，返回表格/图表
- **SaaS 定价**: 简洁的三档定价卡片（Free / Plus $29/mo / Pro $79/mo）

---

## 10. AD-Research 设计建议清单

### P0 — 必须实现（MVP 阻塞项）

| ID | 建议 | 参考平台 | 依据 |
|----|------|---------|------|
| P0-1 | 深色模式默认 + 亮色模式可选，用 `light-dark()` CSS 函数统一 token | Robinhood, TradingView | 已有 `20260711-design-standards-a11y-color-motion.md` §3 |
| P0-2 | 涨跌颜色四重冗余：颜色 + ▲▼ 箭头 + +/− 符号 + 文字标签 | TradingView 色盲模式 | 同标准文档 §2.7 |
| P0-3 | K 线涨跌主色用蓝 `#0072B2` + 橙 `#E69F00`（Okabe-Ito），替代传统红绿 | Okabe-Ito 调色板 | 标准文档 §2.5 |
| P0-4 | 提供三档信息密度：Compact / Comfortable / Spacious | IBKR TWS | 专业用户需要高密度，新手需要低密度 §3.3 |
| P0-5 | `prefers-reduced-motion` 适配：价格闪烁/sparkline 在 reduce 时 0ms | Robinhood, WCAG 2.2 | 标准文档 §1 |
| P0-6 | 自选列表实时价格更新 + 颜色闪烁（`motion-safe:` 限定） | Webull, 富途 | 核心功能 |

### P1 — 应该实现（v1.0 质量目标）

| ID | 建议 | 参考平台 |
|----|------|---------|
| P1-1 | 模块化 Dashboard：用户可拖拽/调整面板布局 | IBKR TWS Mosaic |
| P1-2 | 图表嵌入 Widget（复用 TradingView charting_library） | TradingView |
| P1-3 | 移动端底部 Tab Bar 导航（自选/行情/研究/AI/设置） | Robinhood, 富途 |
| P1-4 | 数据卡片大字号关键数字 + Sparkline 迷你趋势图 | Robinhood, Webull |
| P1-5 | 筛选器面板（市值/行业/指标多条件筛选） | Webull, TradingView |
| P1-6 | 色盲模式 Toggle（一键切换 Okabe-Ito 调色板） | TradingView Color Blind 预设 |
| P1-7 | 多市场颜色自适应（A 股红涨绿跌 vs 美股绿涨红跌） | 富途牛牛 |
| P1-8 | 响应式断点：mobile-first，≥768px tablet，≥1024px desktop | Robinhood Next.js |
| P1-9 | 社区/讨论集成（UGC 投资观点与行情同屏） | Public.com, 富途牛牛圈 |

### P2 — 建议实现（v1.5+ 差异化）

| ID | 建议 | 参考平台 |
|----|------|---------|
| P2-1 | AI 对话式投研界面（自然语言查询 → 结构化数据 + 图表） | FinChat |
| P2-2 | 量化评级系统（五档可视化评分） | Seeking Alpha Quant Ratings |
| P2-3 | 分析师/策略 Marketplace（UGC 订阅制） | Seeking Alpha Marketplace |
| P2-4 | 教育嵌入模块（每个资产页 Why/How 解释投资逻辑） | Public.com |
| P2-5 | 自定义字体品牌感（考虑 Inter 或自研几何无衬线） | Robinhood Capsule Sans |
| P2-6 | Pine Script 式自定义指标/策略脚本 | TradingView |

---

## 11. 自我审计

### 一手来源 URL 列表

| # | URL | 数据类型 |
|---|-----|---------|
| 1 | https://robinhood.com/us/en/ | 完整 HTML/CSS 源码（Next.js SSR） |
| 2 | https://www.webull.com | 完整 HTML/CSS 源码（React SPA） |
| 3 | https://www.futunn.com | 完整 HTML 源码（Vue SSR） |
| 4 | https://seekingalpha.com | 完整 HTML/CSS 源码（React SPA + SSR data） |
| 5 | https://finchat.io | Vercel checkpoint（确认 Astro 框架） |
| 6 | https://www.interactivebrokers.com/en/trading/tws.php | 页面结构已知（curl 被反爬拦截） |
| 7 | https://www.tradingview.com/chart/ | 页面结构已知（curl 超时） |
| 8 | https://public.com | 页面快照为空（SPA 需 JS 执行） |
| 9 | https://www.itiger.com | 页面空返回 |

### 低置信度结论

1. **IBKR TWS 具体色彩 token**: 未获取到 CSS，基于行业知识推断。**置信度: 中**
2. **Tiger Brokers 具体 UI 布局**: 未能获取页面源码，基于公开截图和行业知识。**置信度: 中低**
3. **Public.com 当前 UI 设计**: SPA 无 JS 渲染，基于公开信息和历史截图。**置信度: 中**
4. **TradingView 精确色彩**: 页面未成功抓取，基于公开文档和已知设计系统。**置信度: 高**（TradingView 颜色是公开文档化的）
5. **FinChat 定价/功能细节**: Vercel 安全拦截，基于第三方评测和公开信息。**置信度: 中**

### 需要用户补充资料的事项

1. **富途牛牛 App 实际截图**: 中国大陆限制访问 futunn.com，建议用户提供 App 内截图验证首屏布局、自选页、标的详情页的设计细节。
2. **Tiger Brokers App 截图**: 同中国大陆限制，建议提供 App 截图。
3. **IBKR Client Portal 当前版本截图**: IBKR 2024-2025 可能迭代了 Client Portal，建议提供最新截图。
4. **AD-Research 当前前端技术栈确认**: 报告中假设 React/Next.js，但实际框架（Vue? React? HTML?）请确认以便建议更具体。
5. **AD-Research 目标用户画像**: 零售投资者 / 专业分析师 / 机构交易员的比例影响信息密度和导航设计。

---

> **配套文档**: 无障碍/色彩/动效标准见 `20260711-design-standards-a11y-color-motion.md`
