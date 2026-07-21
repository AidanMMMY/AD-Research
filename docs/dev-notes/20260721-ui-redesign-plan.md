# 2026-07-21 全站 UI 视觉评审与统一重构方案

> 方法：Playwright 真实截图 43 张（生产、admin 账号）→ 8 个评审 agent 分域核对截图+代码 → 100+ 条证据化发现。
> 趋势参照（2026 联网调研）：dark-first、bento 克制使用、色彩功能化、数据密集但有呼吸感、AI-native、5 秒法则、微动效服务状态。

## 一、系统性主题（跨页共性问题）

### T1 色彩语义纪律（最优先）
- 零值/空值被染成"涨"：getReturnColor(0)→rise（板块轮动市场平均 0.00% 红色）、Dashboard 动量条 null 落红色分支、资金流大数字硬编码 --cc-rise 显示红色 "—"、微结构北向 0.00 亿元红色
- 色彩倒置：微结构表格涨跌幅无色但 KPI 零值红；SEC "已提取 120" 红 / "待提取 1289" 蓝
- 装饰色过载：扫描计数染涨跌色、名次染来源色、事件 chip 五色高饱和
- 方案：getReturnColor 加 0→neutral 分支；null 永不进 rise/fall 分支；占位（—）一律 text-tertiary；色彩只表语义

### T2 主题裂缝
- Dashboard cc-* 硬编码暗色 token 不随主题切换（浅壳+黑内容）；双顶栏+三品牌重复（AppLayout header / cc-topbar / 页内标题）
- 方案：cc-* 映射 theme.css 语义 token；删 cc-topbar 品牌区；登录页 Aurora 收敛（后续）

### T3 布局执行 bug
- FilterToolbar 裸 total：macro "25"、scanner "17"、notification "0"、research-reports "20" —— 组件级修复：total 统一格式化为「共 N 条」
- ContextHint inline-flex 压坏工具栏（Screen 筛选、SignalDashboard Select 压成药丸）
- 筛选区 ad-w-full 全宽堆叠吃掉首屏：crypto-list、research-reports、cninfo-reports、listing-preview
- 日期列 110px 折行（多页）→ 120px
- SignalDashboard ad-kpi-* 类名漂移（样式整体失效）
- ScoreBar 浅色轨道隐形（global.css:5697）

### T4 原值上屏
- ISO 时间戳（cninfo 披露时间、笔记 generated_at T）、英文枚举（pending/skipped/note_type/SUCCESS/FAILED）、来源内部 key+计数（news wallstreetcn(525)）
- 时间格式混乱：英文日期 + AM/PM（ETLStatus/NewsHealth/NotificationLogs/AdminDeployments "an hour ago"）→ 统一 formatDateTime/formatRelative

### T5 信息层级（5 秒法则）
- InstrumentDetail hero 无现价/当日涨跌（只有 -7.44% 1月收益）
- GlobalMarkets 首屏被 8 条事件流占满，利率表只露 1.5 行 → 默认 4 条
- Sentiment 默认阈值致全空；AIChat 空态大白卡；学习页卡头竖排
- 详情面板重复：InstrumentDetail StatCard 与指标 Panel 四项重复

### T6 交易域一致性
- BacktestList 缺失值伪装 0、收益无色；Portfolio Tag 冒充 CTA；空态缩左上角；实盘横幅 info 蓝应 warning

## 二、实施批次（8 个并行包，文件域不重叠）

| 包 | 范围 | 关键修复 |
|---|---|---|
| A 色彩语义 | utils/color、Microstructure、SECFilings | 零值 neutral、表格涨跌色、KPI 语义纠正 |
| B Dashboard | command-center.css、Dashboard/index.tsx | cc-* 映射 token、删双品牌、PULSE 假柱、动量 null、资金流色、表头错位、决策队列 |
| C 组件修复 | FilterToolbar、global.css(ScoreBar/ContextHint)、Screen、SignalDashboard | total 格式化、anchor block、popover 触发、ad-kpi 类名、强度分档 |
| D 筛选布局 | CryptoList、ResearchReports、CninfoReports、ListingPreview | 删 ad-w-full、日期列 120、重置按钮 |
| E 原值治理 | CninfoReports、SECFilings、ResearchNotes、News、ETLStatus、NewsHealth、NotificationLogs、AdminDeployments | 时间格式统一、枚举中文化、skipped 映射、来源 label |
| F 信息层级 | InstrumentDetail、GlobalMarkets、Macro、SearchTrends | hero 现价、事件 4 条、头条网格、统计卡合并 |
| G 交易域 | BacktestList、PaperTrading、TradingPanel、Portfolio、PoolList | 收益色/缺失、空态居中、warning 横幅、Tag 伪按钮 |
| H AI/内容/学习 | AIChat、Learning、Sentiment、SentimentDashboard、Favorites | 空态改造、卡头 wrap、阈值、死代码 |

## 三、后续阶段（本方案不含）
- global.css 拆分（8608 行地层沉积）、GlassCard/ContentCard 下线 + ESLint 守门
- 登录页 Aurora 收敛、PoolList 卡片网格化、详情抽屉四模式统一
- 深色主题设为默认（dark-first）
