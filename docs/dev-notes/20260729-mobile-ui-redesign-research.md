# 移动端 UI 设计风格深度调研：卡片式之外的候选方向

> 日期：2026-07-29
> 调研方式：外部设计趋势调研（2024-2026 金融/数据平台设计范式，30+ 引用来源）× 平台内容盘点（46 路由页面 / 58 组件 / 22 个全局 CSS 实测）
> 结论：**推荐「A 列表优先去边框」为骨架 +「B 数据/内容双轨排版」为血肉 +「C Bottom-sheet 分层」为交互 +「D AI 层」渐进叠加**

---

## 一、问题定义：不是审美问题，是结构性空间问题

平台当前卡片式布局在移动端的损耗可量化（390px 视口实测）：

| 损耗来源 | 量化 | 证据 |
|---|---|---|
| 横向 chrome（页边距+卡边框+卡 padding） | **66px / 16.9% 屏宽**；嵌套场景 98px / **25.1%** | theme.css:134-215、components.css:92-122 |
| 纵向 chrome（每个 Panel header+padding） | **~73px/个**；标的详情页 9 个 Panel ≈ 800px ≈ **一整屏** | components.css、InstrumentDetail/index.tsx |
| StatCard 单卡 chrome 占比 | **~43%**（padding+border 34px vs 内容 45px） | components.css:219 |
| 卡中卡实例 | 6 处（评分嵌套、脉搏 tile、策略参数面板、新闻容器、表格卡头、TypeAware 模块） | 见 §五 |
| 移动端首屏有效信息量 | 仅为桌面的 **25-40%** | 逐页测量见 §五 |
| Dashboard 移动端 | cc-* 体系零收紧，padding/gap 保 20px，首屏被标题区+脉搏网格垄断 | command-center.css:106-139 |

Nielsen Norman Group 的可用性研究早已证实：**列表视图空间效率高、易于扫读排序；卡片视图适合视觉浏览与异质内容分组**。小屏上卡片强制用户滚动更多、依赖短期记忆比对内容，认知负荷上升。金融平台用户是任务导向型（查数、比对、决策），天平天然偏向高密度。

## 二、业界现状：没有一家主流金融 App 在移动端用卡片嵌套卡片

| 产品 | 布局范式 | 对本平台的启示 |
|---|---|---|
| 同花顺 | 工具型高密度：极窄行高列表塞多字段 | 中文金融用户接受甚至偏好极高密度；代价是繁杂误触 |
| 富途 | 列表流 + 底部固定操作模块 | 「内容区高密度 + 操作区底部固定」分层，适合详情页 |
| 雪球 | feed-first：1px 分隔线信息流，低装饰 | 资讯流/研究笔记参照：分隔线而非卡片，密度与可读兼得 |
| Robinhood | 极简列表 + 大数字：watchlist 行=名称+迷你 sparkline+价格+涨跌幅 | 行情列表最佳范式：一屏 8-10 行，零卡片边框 |
| Webull | 深色终端风 + 高密度行情磁带 | 进阶用户路径：深色+紧凑+等宽数字 |
| Bloomberg/Reuters | 双轨制：新闻 editorial 排版、数据终端风紧凑表 | 正是本平台「资讯+行情+研究」三合一需要的范式 |
| TradingView | 图表优先 + bottom sheet：二级信息全部下沉抽屉 | 图表页移动端范式：主内容满屏、详情抽屉化 |

**共识收敛**：列表行是行情的基本单元、feed 流是资讯的基本单元、bottom sheet 是二级详情的容器、深色终端风是专业密度的视觉载体。

## 三、2024-2026 设计趋势逐项评估（13 种风格）

| 风格 | 屏宽利用率 vs 卡片 | 适合本平台内容 | 实现成本 | 判定 |
|---|---|---|---|---|
| **List-first 高密度列表** | 最高（~98%） | 行情表/自选/资金流/策略库/持仓 | 低 | ✅ 主方向 |
| **Typography-driven（Linear/Vercel 系）** | 很高 | KPI/宏观看板/研究笔记层级 | 低-中 | ✅ 主方向（中文需重设字距规则） |
| **Feed/stream 信息流** | 高 | 资讯流/研究笔记列表/公告 | 低 | ✅ |
| **Bottom sheet 交互** | 间接提升 | 个股速览/筛选器/AI 对话 | 中 | ✅ 交互层 |
| **深色终端风** | 高 | 行情/图表/宏观看板 | 低（已有 dark token） | ✅ B 轨数据侧 |
| **Editorial/Swiss 杂志风** | 中（为可读性牺牲密度） | 长文研究笔记/资讯正文 | 中 | ✅ B 轨内容侧，**不适合仪表盘** |
| **Command palette** | 不直接相关 | 全站搜索直达 | 中 | 🔶 桌面端价值更高 |
| **AI-native 界面** | 中性 | AI 笔记/智能问答/摘要行 | 高 | 🔶 渐进叠加 |
| **Tokenized design system** | 间接 | 全部 | 低-中（已 token 化） | ✅ 基础设施 |
| **Bento grid** | **移动端反而更低** | — | 中 | ❌ 移动端共识：塌缩单列，等于换皮卡片 |
| **Glassmorphism** | 低 | 仅浮层 | 低 | ❌ 全屏已过气伤可读性 |
| **Neubrutalism** | 低-中（粗边框吃宽度） | 营销页 | 低 | ❌ 与金融严谨信任感冲突 |
| **Invisible UI/去边框化** | 最高 | 所有数据密集页 | 低 | ✅ 与 list-first 一体两面 |

## 四、四个候选设计方向（可组合）

### 方向 A：List-first 高密度 + 去边框化 —— 推荐骨架
- **做法**：内容卡片容器退场，改为 1px hairline 分隔的紧凑列表行（行高 44-56px）；行情行内嵌 sparkline + 右对齐 tabular-nums 等宽数字；层级全靠 typography（字重/字号/语义色）。
- **优点**：屏宽利用率 ~75%→~98%；一屏信息条数提升 60-100%；实现成本最低（样式层重构）；与 Robinhood/同花顺验证的金融用户心智一致。
- **缺点**：高级感依赖排版功力，做糙了像后台管理系统；需严格 token 纪律。
- **页面映射**：标的列表/自选股/资金流/评分排名/策略库列表/ETF 持仓/信号/回测列表——全部列表化。

### 方向 B：双轨制 —— 数据终端风 + 内容编辑风 —— 推荐血肉
- **做法**：数据区（行情/宏观看板/KPI/评分）走终端风：紧凑表格、等宽数字、克制语义色、hairline 网格；内容区（资讯正文/AI 研究笔记长文）走 editorial 风：大标题、宽松行距、单点缀色。
- **优点**：Bloomberg 验证；直接解决平台「三合一」身份分裂。
- **缺点**：维护两套排版尺度；深浅主题过渡需设计。
- **页面映射**：Macro/评分/资金流/情绪 → 终端风；资讯详情/研究笔记阅读 → 编辑风；列表页 → 方向 A。

### 方向 C：Bottom-sheet 分层导航 —— 推荐交互（与 A/B 正交）
- **做法**：主屏永远留给列表/图表；个股详情、筛选器、AI 对话、二次确认收进三档吸附 bottom sheet（peek/half/full）；桌面端对应 command palette。
- **优点**：消除跳页上下文丢失；符合拇指热区；TradingView/富途验证。
- **缺点**：需 drawer 组件 + 滚动嵌套/手势冲突处理，开发量中等。
- **页面映射**：行情列表点个股 → half-sheet 速览（上拉全屏进详情）；20 个筛选+表格页的筛选器 → sheet（治 P1 工具栏首屏侵占）；AI 问答 → 全局 sheet 入口。

### 方向 D：AI-native 增强层 —— 渐进叠加
- **做法**：资讯流/研究笔记叠加 AI 摘要行、对话式追问入口、「今日必读」个性化生成；AI 内容明确标注。复用现有 MiniMax 翻译/摘要管线。
- **判定**：产品功能升级而非样式重构，不阻塞 A/B/C。

### 明确排除
- **Bento grid**：移动端主流实践判定需塌缩单列，对本平台是"换名卡片式"，不解决密度。
- **Neubrutalism / 全屏 glassmorphism**：与金融数据严谨气质冲突，粗边框/留白进一步降密度。

## 五、平台 7 种原子内容类型 × 设计方向映射

| 原子类型 | 高频页面 | 当前移动端首屏 | 目标范式 | 关键改动 |
|---|---|---|---|---|
| ① KPI 数值卡（12+ 页） | Macro/资金流/期货/详情 | 3-4 张卡（43% chrome） | **A+B**：去卡改 hairline 指标行/双列紧凑格，tabular-nums 大数字 | StatCard 移动端去边框去阴影、padding 16→8 |
| ② 筛选器+表格（~20 页，最高频） | 标的列表/筛选器/报告/信号 | 工具栏换行吃 30% 首屏 | **A+C**：行式列表 + 筛选器收 bottom sheet | 统一 mobile-list-item 降级（现仅 5/20 页有） |
| ③ 时间序列图表 | 详情/板块/回测/Macro | 图表起点在折叠线附近 | **C**：主图满屏、工具栏/周期选择收 sheet | detail-toolbar 纵向改 sheet |
| ④ 新闻/条目流 | News/Dashboard/研究笔记 | 仅 2 条/首屏 | **A**：hairline feed 行（雪球范式），去条目卡 | ad-news-card 去卡改分隔线行 |
| ⑤ 行情快照/脉搏块 | Dashboard/Global/情绪 | 2 列 tile 垄断首屏 | **A**：脉搏网格改紧凑磁带行（ticker tape） | cc-pulse-item 去 tile 改行 |
| ⑥ 策略/工具卡片网格 | 策略库/教程/标的池 | 2.5 张卡/首屏 | **A**：策略卡改列表行（名称+关键参数+评分一行化） | StrategyCard 移动端行式变体 |
| ⑦ 长文阅读/AI 流式 | 资讯详情/笔记/AI 助手 | — | **B 编辑风**：大标题+宽行距+单点缀色 | 阅读页排版尺度重构 |

## 六、落地路线图（对齐 React + AntD + 自研 token 栈）

| 阶段 | 内容 | 风险 |
|---|---|---|
| **P0 基础** | 建密度 token（行高/分隔线/tabular-nums/紧凑 padding）；统一断点（767/768 双轨并一，收编 575/479 零散断点）；全站 `@media (hover:hover)` 守卫 + `touch-action: manipulation` + viewport-fit=cover + dvh | 低 |
| **P1 骨架** | Dashboard 先行（问题最典型）：cc-card 去边框化、自选股/要闻/信号流行式化、脉搏磁带化；StatCard 移动端去 chrome | 低-中 |
| **P2 列表化** | 20 个筛选+表格页统一行式降级；资讯流去卡片；策略库行式变体 | 中 |
| **P3 交互层** | bottom sheet 承载个股速览/筛选器/AI 对话；桌面 command palette | 中 |
| **P4 双轨排版** | Macro/评分终端风尺度；资讯详情/研究笔记 editorial 尺度 | 中 |
| **P5 AI 层** | feed 摘要行、对话追问（复用 MiniMax 管线） | 渐进 |

## 七、核心判断

**金融移动端的未来不是更漂亮的卡片，而是没有卡片**——用排版代替容器、用列表代替网格、用抽屉代替跳页、用密度换取专业用户的信任。对本平台，这意味着一次以 Dashboard 和 20 个表格页为主战场的「去卡片化」演进，而非推翻重写：token 体系、组件库、数据层全部保留，改的是容器语言与排版尺度。

---

## 附录 A：平台卡片空间开销实测明细

- Token 基准：`--card-radius: 12px`、边框 1px、三层 `--shadow-card`、Panel body padding 桌面 20px → 移动 16px、页面 padding 32→16px。
- 全宽 Panel 横向 chrome：页面 16×2 + 边框 1×2 + body 16×2 = 66px（16.9%）；嵌套 +32px → 98px（25.1%）。
- 纵向 chrome：Panel header ~45px + body 上下 28px ≈ 73px/个 + section 间距 16px。
- 卡中卡实例：① InstrumentDetail 评分嵌套（index.tsx:548）② Dashboard 脉搏 tile（command-center.css:169-227）③ StrategyCard 参数面板（components-cleanup.css:1072-1081）④ ad-news-feed 容器套条目（pages-tools.css:157-169）⑤ ad-table-card（pages-tools.css:520-528）⑥ TypeAwareModules 三处 Panel 嵌入（:348/:463/:598）。
- 首屏密度：Dashboard ~21 小字 tile（功能卡被挤出）、News 仅 2 条、标的详情 ≈ 1 条价格、Macro 3-4 张 KPI、策略库 2.5 张卡。
- 适配缺口：无 hover 守卫、无 touch-action、无 dvh/viewport-fit=cover、表格降级仅 5/20 页、断点双轨（767 CSS vs 768 antd Grid + 575/479 零散）。

## 附录 B：主要引用来源

- NN/g: Card View vs. List View / Cards 组件定义 / Bottom Sheets 指南（nngroup.com）
- LogRocket: Balancing Information Density / Bottom Sheet 优化（blog.logrocket.com）
- 竞品：人人都是产品经理（同花顺&雪球竞品分析）/ 简书（富途行情交易互通）/ Itexus（Robinhood UI Secrets）/ Pineify（Bloomberg vs TradingView 2025）
- 趋势：FuseLab 2025/26 移动设计趋势 / Pixelmatters 2025 八大 UI 趋势 / DLM Digital 2025 UX 趋势 / Lyssna 2026 App 设计趋势
- Bento 争议：UX StackExchange / Superfiles 移动端指南 / SaaSFrame 实践指南 / DigitalHeroes
- Linear/Vercel 系：Seedflip Vercel 设计系统拆解 / Mantlr 高级 UI / Open Design Vercel tokens
- 其他：UI Style Guide Editorial Grid / Groteskly 2025 字体趋势 / Diverse Website Design Glassmorphism 2025 / Neubrutalism 指南 / Mobbin Bottom Sheet 规范
