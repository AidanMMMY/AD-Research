# 2026-10-25 前端健康摸底报告（web/）

> 基线：main @ 212a9ec。方法：5 个并行只读摸底切片（类型契约 / 死代码与审计遗留 / 运行效率 / 状态管理与一致性 / 构建产物与 lint 实测）。
> 全程未修改任何源代码、未做任何 git 写操作；dist/ 构建产物因 `npm run build` 被覆盖（任务允许范围）。
> 类型契约核对铁律：web TS 类型与后端 schema 漂移时，一律以后端为准。

## 一、结论速览

**总体判断：架构健康度中上。** tsc 0 错误、build 11.2s 成功、无死页面、51 页全部 lazy + manualChunks 分包合理、Zustand/React Query 使用克制、口诀 3「整行单动作」0 违例。短板集中在三处：

1. 前后端类型契约漂移 16 处，其中 3 条已是运行时缺陷（digest 分节状态判断恒 false、pool analytics 字段读不到、signals 请求体错配）；
2. 列表运行效率反模式成片：26+ 页 columns 无 useMemo、Favorites 在 SSE 下每 ~3s 整表重渲染、行内 sparkline 每行一个 HTTP 请求（一页 50 并发）；
3. 20260825 UI 一致性大修「字号 ≤11px 清零」宣称存在存量漏网 33 处（全部为大修前引入，无新增）；clickableRow 绕过 3 处（其一键盘不可达）；a11y 测试 0 个真实页面覆盖。

**分级统计：P0 = 4 条，P1 = 11 条，P2 = 13 条。**

关键数字：

- 构建：tsc 0 错误；build 成功（wall 11.2s，vite 本体 5.18s，5224 模块）；dist 5.0MB（121 JS + 39 CSS + 74 字体文件 1.2MB）；首屏 eager ≈ 1.94MB raw / ~549KB gzip。
- 超 500KB chunk 仅 2 个（ui 1.22MB、echarts 714KB），且 echarts / lightweight-charts 均为 lazy 页面 chunk，未进首屏。
- lint：0 errors / 125 warnings（全为存量，44 个文件）；check:ci 脚本链不含 eslint，是否有 CI 门禁拦截待核实。
- Zustand：6 个正式 store + 1 个游离 store 共 286 行，最大 82 行，无跨职责巨型 store、无与 React Query 重复的服务端缓存。
- React Query：约 142 处 useQuery，40 处未显式设 staleTime（落默认 60s）；轮询 8 处均有场景且大多有终止条件。
- 一致性口诀违例：字号 33 处、可点行绕过 3 处、chip/Tag 绕过 4 处、整行多动作 0 处。

## 二、P0（运行时缺陷，4 条）

### P0-1 digest 研报分节契约双漂移：status 枚举错 + retries 幽灵必填字段

- 证据：`web/src/api/digest.ts:19`（分节 status 定义 'ok' / 'degraded' / 'failed'）与 `:39-45`（DigestSection 的 retries 为必填 number）vs 后端实际写库 `app/services/digest/generator.py:157-160`（每节只有 {key, title, status, chars}，status 取值仅 success / failed，从不写 retries 键）。
- 影响：前端任何 `status === 'ok'` 判断恒为 false，分节健康态展示错误；retries 是幽灵必填字段。历史记忆「retries 可选」实为后端根本没有该键。外层 status 枚举已修复一致，残留漂移在 section 级。
- 修复建议：分节 status 收敛为 'success' / 'failed'；删除 retries 或改可选并注明来源；补 digest 契约单测。

### P0-2 GET /pools/{id}/analytics 响应契约漂移：顶层 name 读不到，members 元素结构错

- 证据：`web/src/types/pool.ts:32-54`（PoolAnalytics：name: string；members: PoolWeight[]，含 target_weight 必填、weight_source、suggested_weight）vs `app/schemas/pool.py:97-107`（字段名是 pool_name: str 或 None，另有 member_count 前端缺失）与 `:86-94`（members 元素为 PoolAnalyticsMember：etf_code/etf_name/name_zh/category/target_weight/added_at，无 weight_source/suggested_weight）。
- 影响：前端读 analytics.name 得 undefined，池分析页名称/成员数展示空；members 元素字段对不上。
- 修复建议：前端类型整体改写为 PoolAnalyticsResponse / PoolAnalyticsMember 形状（pool_name + member_count + 新 members 结构），并在 PoolDetail 页回归验证。

### P0-3 POST /signals/generate 请求体契约漂移：strategy_id 后端必填、前端可选 + 幽灵字段

- 证据：`web/src/types/signal.ts:22-28`（strategy_id?: number 可选，另发 strategy_type?、event_signal_id?）vs `app/schemas/signal.py:32-38`（strategy_id: int 必填，body 只收 strategy_id / etf_code / trade_date）。
- 影响：任何允许 strategy_id 留空的调用路径直接 422；strategy_type / event_signal_id 被 Pydantic 静默忽略，是从未生效的假参数。
- 修复建议：strategy_id 改必填，删除两个幽灵字段；核对 SignalDashboard / 策略页实际传参是否已全部带 strategy_id。

### P0-4 AIHelp Provider value 未 useMemo：AI 流式输出期间全站级联重渲染

- 证据：`web/src/components/AIHelpProvider.tsx:315`（裸对象 value）、`:331`（直接传入 Provider）；Provider 包裹整个应用（`web/src/App.tsx:140`）；常驻消费者 `App.tsx:173`（AIHelpDrawer）、`components/DailyLesson.tsx:46`、`components/HelpPopover.tsx:40`（被 ScoreRanking 等页面表格列标题大量实例化）。
- 影响：流式回复每个 SSE chunk 触发 setStreamedText，Provider 重渲染使 value 引用变化，所有 useAIHelp 消费者全量重渲染，流式期间可达每秒数十次级联渲染，是全站最大的运行效率缺陷。
- 修复建议：value 用 useMemo 包裹；更彻底是拆「动作 Context（稳定引用）+ 状态 Context（高频）」两层，流式文本只让 Drawer 订阅状态层。

## 三、P1（11 条）

### P1-1 Favorites 在 SSE 推送下每 ~3s 整表重渲染

- 证据：`web/src/pages/Favorites/index.tsx:71`（useMarketStream，约 3s 一推）、`:147`（columns 在组件体内每次渲染重建，无 useMemo）、`:175-200`（实时价/涨跌幅列 render 内联闭包直读 liveLatest），全文件无 React.memo。
- 影响：交易时段自选页每条 SSE 消息整表 reconcile；对照 InstrumentList 已用 memo(LivePriceCellImpl) + 自定义比较（`pages/InstrumentList/index.tsx:73-85`）+ useMemo columns（`:353`）解决同类问题，属同题不同标。
- 修复建议：照搬 InstrumentList 方案：实时价单元格抽 memo 组件 + 自定义比较，columns useMemo。

### P1-2 26+ 页面 AntD Table columns 每次渲染重建（无 useMemo）

- 证据（代表位置，均在组件体内）：`pages/ETLStatus/index.tsx:50`、`ReportBrowser/index.tsx:218`、`ScoreRanking/index.tsx:90`（列标题内联 HelpPopover，:125-127）、`Favorites/index.tsx:147`、`SignalDashboard/index.tsx:254`、`CryptoList/index.tsx:180`、`GlobalMarkets/index.tsx:249`、`SectorRotation/index.tsx:411`、`CninfoReports/index.tsx:273`、`ListingPreview/index.tsx:226`、`AdminUsers/index.tsx:169`、`Macro/index.tsx:248`、`ETLOpsDashboard/index.tsx:73`、`SECFilings/index.tsx:132`、`Screen/index.tsx:180`、`ResearchReports/index.tsx:253`、`Sentiment/index.tsx:397`、`NewsHealth/index.tsx:169`、FundFlow（多组 columns）等；全站仅 `InstrumentList/index.tsx:353` 一处 useMemo。
- 影响：与轮询叠加（ETLOpsDashboard 30s、NewsHealth 30s、Sentiment 60s、SignalDashboard 60s）后，每次数据到达即重建全部列对象并整表 diff。
- 修复建议：columns 统一 useMemo；纯静态列提升到模块作用域。

### P1-3 行内 sparkline 每行一个 HTTP 请求（请求风暴）

- 证据：`web/src/components/SparklineCell.tsx:16`（每行一个 useSparkline）；`hooks/useSparkline.ts:13-17`（key ['sparkline', code, days]，staleTime 5min）；`pages/InstrumentList/index.tsx:484`（每页 50 行 = 50 并发）；`pages/FundFlow/index.tsx:110-119`（FlowSparklineCell 每行调 useFundFlowIndividualHistory，`api/fundFlow.ts:221`）。
- 影响：翻页/筛选时每行独立请求，首屏与后端双慢；渲染本身廉价（Sparkline 为纯 SVG + useMemo，设计良好），问题纯在网络层。
- 修复建议：后端提供批量 sparkline 端点（codes 数组一次返回），或列表接口内联 points 字段。

### P1-4 字号地板 12px 违例 33 处（全部为大修前存量，无新增）

- 证据：tsx 数值型 fontSize 10/11 共 12 处（`components/PerformanceIndicator.tsx:100,182,242`；`pages/SectorRotation/index.tsx:260,315,331,368,384`；`pages/SearchTrends/index.tsx:219,224`；`pages/Macro/index.tsx:332,337`）+ CSS font-size 10px/11px 共 21 处（`styles/global/pages-dashboard.css:101,117,329,395,446,540`；`learning.css:51,107`；`pages-tools-cleanup.css:33,189`；`components/AppLayout.css:74,171`；`pages-tools.css:226`；`sidebar-refresh.css:158`；`sidebar.css:203`；`pages-admin.css:59`；`pages/Learning/styles.css:198`；`pages/SignalDashboard/styles.css:118,336`；`pages/Macro/styles.css:96,102`）。git blame 确认全部引入于 2026-07-02 ~ 07-29，早于 20260825 大修。
- 影响：与「字号没有 11px 及以下」口诀冲突，大修宣称的清零存在漏网。其中 ECharts axisLabel 属 canvas 配置（非 DOM 字号）是否计入地板需产品定夺，但 CSS/tsx 的 DOM 字号是明确违例。
- 修复建议：CSS 21 处改 token（--text-label-size=12 地板）；tsx 12 处区分 DOM 字号（必改）与 ECharts canvas 配置（产品定夺）。

### P1-5 clickableRow 3 处绕过（其一键盘不可达）

- 证据：`pages/GlobalMarkets/index.tsx:351-353`（手写 onRow + 内联 cursor:pointer，无 tabIndex/role/onKeyDown，键盘完全不可达，最严重）；`components/TypeAwareModules.tsx:241-252`（手写 onRow + 内联 cursor，键盘齐全但绕过统一标记类）；`pages/Screen/index.tsx:627-638`（手写 onRow，可点行反而无手型标记，反向不一致）。三处均为大修前（07-03 ~ 08-01）存量。
- 影响：违反「可点性 = clickableRow 显式标记」口诀；GlobalMarkets 行对键盘用户不可用（实际 a11y 缺陷）。
- 修复建议：统一改 `utils/a11y.ts:18` 的 clickableRow()；顺带核对 CSS 裸 cursor:pointer 存量 64 处/25 文件（多数在真实可点元素上，逐处核对即可）。

### P1-6 a11y 测试 0 个真实页面覆盖

- 证据：`web/tests/a11y/` 仅 3 个文件（smoke / command-center / detail-drawer），全部是 fixture 或共享组件冒烟（注释明确「不渲染真实 Dashboard 页，它拉 30+ hooks 和真 API」）；`src/pages/` 约 57 个路由页 a11y 覆盖为 0。
- 影响：页面级 a11y 回归（如 P1-5 的键盘不可达行、33 处小字号）axe 完全测不到。
- 修复建议：按「mock 数据渲染真实页面组件」模式补至少 FundFlow / InstrumentDetail / News / SignalDashboard 四个高频页用例。

### P1-7 auth store 双写 localStorage + token 全量持久化

- 证据：`web/src/stores/auth.ts`（persist 写 auth-storage 键），同时 login/setTokens/logout 内手动 localStorage.setItem('token'/'refresh_token')（:39-40 等）；token 与 refreshToken 全量持久化在 localStorage。
- 影响：两套存储并存，任一路径漏更新即不同步（结合此前 native 端刷新回写竞态史，风险非理论）；token 长期躺在 localStorage 放大 XSS 暴露面。
- 修复建议：收敛为单一 persist 出口（partialize 只留必要字段）；评估 refresh token 迁移 httpOnly cookie。

### P1-8 图表字面量色未走 resolveChartColor，换主题不跟随

- 证据：token 体系已完备（theme.css 240 个 token、light/dark 双声明；`utils/chartColors.ts` 的 resolveChartColor(s) 为单一事实源，62 处使用），残余字面量色集中在图表组件：`ReturnCurve.tsx`（15 处 hex）、`PerformanceIndicator.tsx`（15）、`pages/SectorRotation/index.tsx`（13）、`CategoryPie.tsx`（9）、`ScoreRadar.tsx`（6）、`KLineChart.tsx`（5）、`MacroLineChart.tsx`（4）。业务侧硬编码 hex 约 103 处（另有 Login.tsx 11 + login.css 等）。
- 影响：换主题（dark / accent / US 配色约定）时这些图表不跟随，是 20260724 token 化（原 130 处）后的残余尾巴。
- 修复建议：图表组件逐个接入 resolveChartColor(s)；Login/特效类列第二批。

### P1-9 AGENTS.md 技术栈描述与实际漂移：Tailwind CSS 4 实际零接入

- 证据：`web/package.json` 声明 tailwindcss + @tailwindcss/vite，但 `vite.config.ts:5` plugins 仅 [react()]；全部 CSS 无 @import "tailwindcss"；dist CSS 0 处 --tw- 变量。项目实际是手写 CSS 设计系统（styles/theme.css + global.css）。同类：stylelint-config-standard 在 `.stylelintrc.json` 中无 extends，实际未启用（只挂自研 no-bare-color-values 插件）。
- 影响：AGENTS.md 第 2/5 节把 Tailwind 4 / stylelint-config-standard 列为栈内事实，会误导后续 AI 代理与新成员按 Tailwind 心智写样式（如尝试 text-[11px] 类）。
- 修复建议：要么真接入（重写工作量大，不建议），要么从 AGENTS.md 与 package.json 同步移除这两个幽灵事实。

### P1-10 news 全部路由无 response_model（契约漂移温床）

- 证据：`app/api/v1/news.py:225,344,503,1007,1102,1226,1321,1380,1426` 共 8+ 个路由直接返回 dict；本次只能按 _article_to_dict（`news.py:143-202`）核对列表与详情，/news/watchlist、/news/event-signals、/news/retail-sentiment/{symbol}、/news/stats/sources、/news/health 的返回未逐字段核对（前端类型在 `web/src/types/news.ts:191-387`）。
- 影响：news 是最高流量页面之一，无 schema 即无静态对齐手段，漂移只能人肉发现（本次已发现 source_id / category 两字段前端缺失）。
- 修复建议：为 news 路由补 Pydantic response_model（可用 _article_to_dict 字段清单直接建模）。

### P1-11 macro 双 hook 双 queryKey（缓存分裂陷阱）

- 证据：`web/src/hooks/useMacro.ts:31-38`（useMacroLatest，key ['macro-latest', region]）与 `web/src/api/macro.ts:123-130`（同名 useMacroLatest，key ['macro','latest', region]）并存；页面只用 api 版，hooks 版现为 0 引用死代码；另 `hooks/useMacro.ts:7`（['macro-indicators', region]）与 `api/macro.ts:115`（['macro','list', params]）疑似同端点两套 key。
- 影响：暂无运行时重复请求（一侧已死），但任何人复用 hooks 版即产生同端点双缓存、失效不同步。
- 修复建议：删除 hooks/useMacro.ts 重复 hook，统一 ['macro', ...] 前缀。

## 四、P2（13 条，工程卫生与优化）

### P2-1 确认死代码 8 个文件 + 连带孤儿 CSS

- 证据（全仓双模式 grep 计数 0）：`components/CategoryPie.tsx`、`FavoriteToggleButton.tsx`、`IndicatorCard.tsx`、`ParticleBackground.tsx`、`TermTooltip.tsx`、`TickerTape.tsx`（内部引用 useMarketStream，删除无连带）、`hooks/useChartResize.ts`（85 行整文件）、`stores/pool.ts`（usePoolStore 整 store）；连带 `styles/global/components-cleanup.css:635/839/1245/1261` 四段孤儿样式。另 `stores/settings.ts:5` 的 export type HelpMode 仅文件内使用，export 冗余。
- 建议：按清单删除（动手前再 grep 复验）；注意 `pages/SentimentDashboard` 与 `pages/Screen` 是有意保留的活代码（页内 Tab / 已恢复路由），勿清理。

### P2-2 幽灵依赖与锁文件残留

- 证据：`motion` ^12.42.2（动画层已改纯 CSS，`hooks/useChartMotion.ts:22-24` 注释自证）、`tailwindcss` + `@tailwindcss/vite`（见 P1-9）、`stylelint-config-standard`（无 extends）四个依赖零引用；仓库根 package.json + package-lock.json（7 月 11 日旧物，依赖在 web 外 0 引用，疑似历史误在根目录 npm install）；`web/pnpm-lock.yaml` 陈旧（CI 与 Docker 均走 npm ci）。
- 建议：清理四个依赖；删根 package.json/lock 与 web/pnpm-lock.yaml 前确认无脚本引用。

### P2-3 字体全子集导入：74 个字体文件 1.2MB（占 dist 24%）

- 证据：`main.tsx:15-20` 引入 @fontsource/inter/{400..700}.css 等全子集入口，产出 greek/cyrillic/vietnamese/latin-ext 全套。
- 建议：改 @fontsource/inter/latin-400.css 形式子集导入，dist 减约 1MB（浏览器有 unicode-range 兜底，网络影响小，主要是部署体积与镜像层）。

### P2-4 AIHelpDrawer 静态 import 拖 react-markdown 进入口 chunk

- 证据：`App.tsx` 静态引入 AIHelpDrawer，Markdown.tsx:2-3 引 react-markdown + remark-gfm；入口 chunk 137KB raw / 48KB gzip 中约一半是 markdown 解析器；组件注释自己写着「AIHelpDrawer 仅登录后需要」。
- 建议：改 React.lazy / 动态 import，首屏关键路径立减约 48KB gzip。

### P2-5 echarts chunk 714KB，注册清单与注释已翻倍

- 证据：`utils/echarts.ts` 头注释「构建后约 350KB」，实际 714,123B raw / 237KB gzip；当前注册 5 charts + 12 components（含 Toolbox / Graphic / Aria / VisualMap 等重组件）。
- 建议：审计 echarts.use([]) 清单，重点核对 Toolbox（自带图标 dataURL，体积大户）/ Graphic / Aria / VisualMap 是否真有页面在用；该 chunk 虽 lazy，但 237KB gzip 影响图表页 FCP。

### P2-6 lint 存量 125 warnings，无门禁拦截（待核实）

- 证据：npm run lint（--max-warnings=0）exit 1：0 errors / 125 warnings / 44 文件。分布：react-hooks/set-state-in-effect 40、exhaustive-deps 37、jsx-a11y/no-static-element-interactions 12、click-events-have-key-events 11、失效 eslint-disable 注释 11、react-hooks/refs 5、rules-of-hooks 4 等；密集文件 AppLayout.tsx(14)、InstrumentList(12)。check:ci 脚本链（stylelint + tsc + vite build）不含 eslint；web-ci 是否单独跑 lint 未核实。
- 建议：核实 .github/workflows/web-ci.yml 实际步骤；如上门禁，先清 set-state-in-effect / exhaustive-deps 两个大头再开。

### P2-7 Zustand 全站零 selector（地雷式反模式）

- 证据：全站 Store(s => ...) 选择器 0 处；整 store 订阅：`App.tsx:14,16,88`（auth，顶层订阅牵动整路由树）、`AppLayout.tsx:475,496,527`（settings 一次解构 7 字段）、`Screen/index.tsx:99`、`CryptoList/index.tsx:123`（只为 filters 却订阅整 store）等。
- 影响：当前 store 更新稀疏代价小；未来任何 store 加入高频状态（如实时价格）会瞬间放大为全页重渲染。
- 建议：统一改 useAuthStore(s => s.user) 形式的原子 selector。

### P2-8 约 40/142 处查询未显式设 staleTime（落默认 60s）

- 证据：全局默认 staleTime 60s + refetchOnWindowFocus false + retry 1（`main.tsx:36-46`）整体健康；未显式设置的集中在 useCrypto（4）、usePoolDetail（5）、Dashboard 计数类（4）、InstrumentDetail（4）、api/fundFlow（4/6）等。
- 建议：元数据/计数类统一提长 staleTime 至 5-10min，纯增收益。

### P2-9 EtfHoldingsHistory 无分页无虚拟滚动

- 证据：`pages/EtfHoldingsHistory/index.tsx:358-365`（dataSource 全量 + pagination={false}）；全站 0 处虚拟化。单期持仓可达数百行（纯文本行，卡顿程度取决于数据量）。其余 pagination={false} 的表行数小，可不动。
- 建议：加 pageSize 50 分页即可，无需引入虚拟化库。

### P2-10 onRow 内联函数 19 处（卫生项）

- 证据：Microstructure:428,498,539、ScoreRanking:407、InstrumentList:1096、Favorites:345,505、ListingPreview:547、FundFlow:1030,1143,1284、GlobalMarkets:351、CninfoReports:506、SignalDashboard:631、Macro:469、Screen:627、ResearchReports:571、CryptoList:390、TypeAwareModules:241。
- 建议：与行级 memo 优化一并 useCallback 化，单独不值得动。

### P2-11 store persist 无 version 字段 + 游离 store 位置不规范

- 证据：仅 settings.ts 有 version:3 迁移管理（正确做法）；auth / screen / crypto / onboarding 无 version；aiChatSheetStore.ts 位于 pages/AIChat/（游离，注释质量高、刻意不持久化）。
- 建议：给 persist store 补 version:1 占位；游离 store 迁入 stores/。

### P2-12 平台审计遗留两项未闭环

- 证据：20260701-platform-logic-audit.md 的「报告 PDF 导出」仍未实现（仅 `api/researchReports.ts:17` 外链 pdf_url 与页面外链按钮）；「移动端优化」仅 BottomSheet 体系落地（8 页消费），K 线/相关性/对比页未逐页验证。其余 12 项前端审计条目已抽查确认闭环（crypto 实现、live-trading 路由、回测归因 tab、SSE 行情、模板管理、通知日志、admin guard、报告轮询、ETL 看板、命令面板、导出按钮、/crypto/:code 合并 redirect）。
- 建议：PDF 导出如无计划，在 ROADMAP 标注退役；移动端按页清单化验收。

### P2-13 杂项：类型重复定义与交互式 Tag 绕过

- 证据：SparklineResponse 在 `api/stocks.ts:13-18` 与 `api/instrument.ts:10-15` 重复定义（当前一致）；4 处疑似交互式 AntD Tag 绕过共享 chip/tag 体系（`AIHelpDrawer.tsx:202`、`SentimentDashboard/index.tsx:244`（点击语义是「查询」而非跳详情，与口诀语义漂移）、`AIChatConversation.tsx:157,167`）；InstrumentCodeTag 只有 accent/static 两种（合规），但另有 ThemeTag 8 种语义并存，新 UI 易选错体系。
- 建议：重复类型收敛到 types/；4 处 Tag 收敛进 ThemeTag（自带键盘可达）或 InstrumentCodeTag。

## 五、类型漂移清单（后端为准，16 条）

路径省略前缀 web/src/ 与 app/。「前端认为 / 后端实际」列中枚举值用斜杠分隔。

| # | 端点 | 前端 (file:line) | 后端 (file:line) | 漂移字段 | 前端认为 | 后端实际 | 严重度 |
|---|------|------------------|------------------|----------|----------|----------|--------|
| 1 | GET /digest/latest、/{id}、/by-date | api/digest.ts:39-45 | services/digest/generator.py:157-160 | 分节 status 枚举 | ok / degraded / failed（digest.ts:19） | 仅 success / failed | 高 |
| 2 | 同上 | 同上 | 同上 | retries | 必填 number（:44） | 从不写该键 | 高 |
| 3 | GET /pools/{id}/analytics | types/pool.ts:32-54 | schemas/pool.py:97-107 | 顶层 name、member_count | name: string（:34） | pool_name: str 或 None；另有 member_count 前端缺 | 高 |
| 4 | 同上 | 同上 | schemas/pool.py:86-94 | members 元素结构 | PoolWeight[]（target_weight 必填、weight_source、suggested_weight） | PoolAnalyticsMember（etf_code/etf_name/name_zh/category/target_weight/added_at） | 中 |
| 5 | POST /signals/generate | types/signal.ts:22-28 | schemas/signal.py:32-38 | strategy_id 等 | 可选；另发 strategy_type、event_signal_id | strategy_id 必填；另两字段不存在 | 高 |
| 6 | GET /pools（members 嵌套） | types/pool.ts:12-20 | schemas/pool.py:7-13 | note 拼写、pool_id、is_active | note?: string；pool_id 必填；is_active 可选 | notes: str 或 None；无 pool_id、无 is_active | 中 |
| 7 | POST /pools/{id}/weights/suggest | api/pool.ts:17-18 | api/v1/pools.py:217；schemas/pool.py:76-83 | 返回元素结构 | PoolWeight[] | 仅 etf_code/etf_name/name_zh/suggested_weight/algorithm | 中 |
| 8 | GET /scores、/scores/{code} | types/score.ts:20-47 | schemas/scoring.py:53-81 | template_id 幽灵、必填性 | template_id 必填（:28）；trade_date/composite_score/score_*/rank_* 全必填 | item 级无 template_id；上述字段全部可 None | 中 |
| 9 | GET /scores 外壳 | types/score.ts:49-54 | schemas/scoring.py:84-90 | trade_date 必填性 | 必填 string | date 或 None | 低 |
| 10 | GET /etfs/{code}/holdings | types/instrument.ts:113-126 | schemas/etf.py:104-134 | snapshot_date | 无此字段 | item 级（:121）与响应级（:134）均返回 snapshot_date | 中 |
| 11 | GET /market-data/{code}/history | api/market.ts:5-6；types/instrument.ts:78-86 | schemas/market_data.py:6-26 | 外壳与 bar 字段 | 外壳缺 etf_code/etf_name；OHLCV 缺 adj_close/amount/change_pct/turnover_rate；价量必填 | 外层有 etf_code/etf_name；bar 含 adj_close 等；价量全部可 None | 中 |
| 12 | GET /stocks、/etfs 列表与详情 | types/instrument.ts:1-29 | schemas/etf.py:6-36 | expense_ratio 幽灵、market 必填性 | expense_ratio 可选；market 必填 | 无 expense_ratio；market: str 或 None | 低 |
| 13 | POST /auth/refresh | api/auth.ts:23-26 | schemas/auth.py:52-55 | token_type 缺失 | 无 | 恒返回 token_type = bearer | 低 |
| 14 | GET /auth/me | api/auth.ts:8-14 | schemas/auth.py:8-15 | role 枚举、must_change_password | role 窄枚举 admin/user；must_change_password 可选 | role 为自由 str；must_change_password 恒返回 bool | 低 |
| 15 | GET /news 列表/详情条目 | types/news.ts:46-129 | api/v1/news.py:143-202 | source_id、category 缺失 | 无这两个字段 | news.py:146 返回 source_id、:171 返回 category | 低 |
| 16 | GET /digest 列表与详情 | api/digest.ts:21-29,48-58 | schemas/digest.py:19-28,45-61 | 列表缺 created_at；详情缺 data_snapshot_json/error_msg/report_metadata_id/started_at/created_at | 无 | 后端均返回 | 低 |

核对一致（抽样，未列全）：auth 的 login / change-password / devices / logout；etfs/{code}/sparkline；etfs/options；持仓快照索引与 diff；signals 的列表/最新/生成响应；favorites 全家；market-data/snapshot；news 分页外壳与文章主体（历史线索 title_zh 已一致）；digest 外层 status 枚举（success/partial/failed 等与写库值完全相同）；scores 请求参数（market 取 cn_a/us 与 instrument_type 取 ETF/STOCK 均有后端映射）；macro/indicators；pools 的 CRUD / correlation / snapshots 主体。

无法核实（需补 schema 或查 DB）：news 8+ 路由无 response_model（watchlist / event-signals / retail-sentiment / stats/sources / health）；SignalItem.signal_type 枚举（后端 str，实际值在策略层）；PoolWeight.weight_source 枚举（后端 str，DB 取值未核实）；NewsArticle.sentiment_label（DB 取值未核实）；macro 的 /latest /codes /indicators-list；digest/{id}/regenerate（前端未调用）；stocks/{code}/financials（前端未见调用）。

## 六、bundle 体积表（build 实测，2026-10-25）

构建：成功；wall 11.2s（vite 本体 5.18s，CPU 205%）；5224 模块；dist 5.0MB；sourcemap 刻意关闭（曾使 dist 翻倍至 8.5MB）。

| 产物 | raw (B) | gzip (B) | 来源 | 超 500KB raw | 超 100KB gzip |
|------|---------|----------|------|--------------|---------------|
| ui-3SC9fheI.js | 1,216,091 | 372,043 | antd 5 + @ant-design/icons + rc-* 系 | 是 | 是 |
| echarts-CNm9MIs1.js | 714,123 | 237,158 | echarts/core 按需（5 charts + 12 components）+ zrender | 是 | 是 |
| vendor-CgjBoXJv.js | 278,291 | 88,090 | react / react-dom / react-router-dom | 否 | 否 |
| lightweight-charts-CYZL7y4I.js | 162,412 | 51,686 | lightweight-charts v4 | 否 | 否 |
| index-DFKy3qFf.js（入口） | 137,034 | 48,255 | app shell + AIHelpDrawer + react-markdown/remark-gfm/micromark | 否 | 否 |
| data-BkEDVKe3.js | 111,864 | 38,898 | @tanstack/react-query + axios + zustand + dayjs | 否 | 否 |
| termDictionary-DcD_X5Ow.js | 62,371 | 21,366 | 自研术语词典数据 | 否 | 否 |
| index-DlsOFBOb.css | 201,880 | 45,521 | antd-overrides + 全局手写 CSS（首屏） | 否 | 否 |
| 字体文件（74 个） | ~1.2MB | — | @fontsource 全子集 | — | — |

- 首屏 eager（入口 + modulepreload 的 vendor/data/ui + 主 CSS）约 1.94MB raw / ~549KB gzip；echarts 与 lightweight-charts 均为 lazy 页面 chunk，未进首屏，分包目的已达成。
- chunkSizeWarningLimit = 500 是刻意保持默认以在 CI 暴露大 chunk（vite.config.ts 有注释说明），勿顺手调大。
- 优化优先级：AIHelpDrawer lazy（首屏 -48KB gzip）> 字体 latin 子集（dist 约 -1MB）> echarts 注册清单审计（lazy chunk -?KB）。ui chunk 1.22MB 短期不再拆：vite 注释说明 icons 单拆会引发运行时循环依赖，antd v5 CSS-in-JS 天然按需。

## 七、做得好的（避免误伤）

- 51 页全部 React.lazy + manualChunks 五组分包；echarts 按需注册（utils/echarts.ts 走 echarts/core）；双图表库分工明确（K 线 lightweight-charts、其余 echarts），各自独立 lazy chunk。
- Sparkline 为纯 SVG + useMemo 路径计算，行内迷你图零图表库实例。
- InstrumentList 是列表页优化范本（服务端分页 50/页 + useMemo columns + memo 实时价单元格 + 自定义比较），P1-1 / P1-2 修复照抄即可。
- useReportStatus 条件轮询（终态自动停）是正确范式；轮询全部集中在管理/监控页，且 tab 切走即停。
- News 用 useInfiniteQuery 渐进加载（PAGE_SIZE 20）。
- Zustand 无巨型 store、无服务端数据副本；aiChatSheetStore 注释明确 messages 留在 react-query cache。
- 口诀 3「整行单动作」抽样 8 页 0 违例，stopPropagation 守卫落实良好。
- 行 hover 底色全表默认是 20260825 大修时的有意决策（行追踪辅助），勿当漏网删掉。
- settings 的 persist version:3 是演进管理的正确做法。

## 八、值得沉淀的口诀/知识清单（只列清单，落库由主会话策展）

1. 契约核对法：无 response_model 的路由（news 全家 8+ 处）是漂移温床，前端类型要按 _article_to_dict 之类实际 dict 生成器核对，不能只看 Pydantic。
2. Provider value 必须 useMemo；高频流式文本拆「动作 / 状态」两层 Context，只让真正的订阅者付重渲染代价。
3. 列表页优化范本 = InstrumentList（服务端分页 + useMemo columns + memo 单元格 + 自定义比较），新列表页照抄而非重造。
4. 行内迷你图/每行小查询 = 请求风暴：一页 50 行就是 50 并发；解法是批量端点或列表内联字段，而不是前端缓存调参。
5. 「大修宣称清零」要用 grep 复验（本次字号 33 处全是宣称清零后的存量漏网，git blame 可验引入时间）。
6. 依赖三步验尸法：grep import + grep 构建指令（@tailwind/@apply）+ 查 dist 产物特征（--tw-），三者皆零才是幽灵依赖；本仓库 Tailwind 是「声明在栈内、实际零接入」的典型。
7. 图表颜色单一事实源 = resolveChartColor(s)（62 处）；图表组件里写字面量色 = 换主题不跟随，新图表必须走 resolver。
8. 本项目 token 体系是无前缀命名（--accent* / --bg-* / --chart-series-*），--vital-* 仅 3 个，别按旧记忆找 vital 前缀。
9. 字体导入用 latin-{weight}.css 子集入口，不用 {weight}.css 全子集入口（74 文件 1.2MB 的教训）。
10. chip 双体系：InstrumentCodeTag（accent/static，标的跳详情语义）与 ThemeTag（8 种状态语义）并存；可点 chip = 跳 /instruments/:code 全站一个语义，新增先选对体系。
11. chunkSizeWarningLimit 保持默认 500 让 CI 暴露大 chunk 是刻意团队约定，勿调大；dist 的 sourcemap 也是刻意关闭。
12. 排查前端「读不到字段」类 bug 时，先做本报告第五节这种漂移表（后端为准），再查 UI 逻辑——一半的展示 bug 根因在契约。
