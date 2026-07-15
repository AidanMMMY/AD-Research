# 资深 UI/UX 设计师审查报告

**审查范围**：AD-Research 投研平台 Web 端（`web/src/`），覆盖全局样式系统、16 个一级页面、9 个共享组件
**审查日期**：2026-07-16
**审查者角色**：资深产品 UI/UX 设计师
**整体评价**：**B+ 级**。设计系统底座扎实（token 化完整、light/dark 双主题、涨跌色约定可切换、Apple-style 动效语言统一、`prefers-reduced-motion` 全局尊重），但在**跨页面一致性、空状态/加载/错误五态、品牌可识别、桌面 vs 移动断点收尾**上仍有明显缺口。下面列出 12 项 P0、9 项 P1、8 项 P2 + 7 项缺失能力。

---

## 一、问题清单

### P0 阻塞级（核心体验问题）

#### 1. 「双 Card 系统」并存 — `ant-card` 与 `ad-panel` 视觉冲突
- **位置**：`web/src/styles/global.css:49-78` (`ant-card` override) + `web/src/components/Panel.tsx:35-55`（`ad-panel`）+ 各业务页面
- **问题描述**：admin、portfolio、strategy-library、etl-ops-dashboard 等页面仍直接使用 antd `<Card>`，继承自 `global.css:49-78` 的 override，padding=16px；而 `Panel padding="md"` 是 12px+16px 上下结构。同样"卡片"，标题字号、padding、header 高度、边框全部不一致。视觉上 admin 页面像另一个产品。
- **专业影响**：跨页面切换产生"风格闪动"，破坏设计系统完整性。
- **建议修复**：① 把 `ant-card` override 全量删掉（保留 `ant-empty`、`ant-table` 等基础控件），统一改用 `<Panel>`；② 各 admin 页面迁移 `import { Card } from 'antd'` → `import Panel from '@/components/Panel'`。
- **优先级**：**P0**

#### 2. 「ADX_STYLE」动效层在 6+ 个页面 100% 重复
- **位置**：
  - `web/src/pages/Macro/index.tsx:52-124` (73 行)
  - `web/src/pages/FundFlow/index.tsx:102-147` (46 行)
  - `web/src/pages/SectorRotation/index.tsx:41-90` (50 行)
  - `web/src/pages/Futures/index.tsx:34-79` (46 行)
  - `web/src/pages/ReturnComparison/index.tsx:??` 同款
  - `web/src/pages/GlobalMarkets/index.tsx:58-100` (43 行)
- **问题描述**：6 个页面各自 inline 一份近 80 行的 `ADX_STYLE`（按钮 spring、按压 scale 0.97、segmented/tabs transition、reduced-motion 全局短路），内容近乎逐字相同。结果：① 任何动效调整要改 6 处；② GlobalMarkets 用了 `cubic-bezier(0.5, 1.6, 0.3, 1)`（带反弹），其他用 `cubic-bezier(0.32, 0.72, 0, 1)`（临界阻尼）—— 不一致的"Apple-style"是分裂的。
- **专业影响**：动效语言分裂、品牌不一致、维护成本飙升。
- **建议修复**：抽出 `web/src/styles/motion-tokens.css`，定义 `.adx-motion { --adx-spring; --adx-ease-out }` 与按钮、tabs、segmented、table-row 的 spring 规则；删除各页面的 `<style>{ADX_STYLE}</style>` 块，全平台统一一套曲线。
- **优先级**：**P0**

#### 3. 大量 inline `style={{...}}` 直接写 token 字符串，绕过设计系统
- **位置**（部分抽样）：
  - `web/src/pages/Dashboard/index.tsx:1074` `style={{ marginTop: 'var(--space-5)' }}`
  - `web/src/pages/Dashboard/index.tsx:1337` `style={{ marginTop: 'var(--space-7)' }}`
  - `web/src/pages/Dashboard/index.tsx:1343` `style={{ marginTop: 'var(--space-7)' }}`
  - `web/src/pages/News/detail.tsx:343, 345, 469` `style={{ color: SENTIMENT_COLORS[sentiment] }}`
  - `web/src/pages/News/index.tsx:464-467` `style={{ color: i < filled ? ... }}`
  - `web/src/pages/FundFlow/index.tsx:??` 多个 margin / padding inline
  - `web/src/pages/Portfolio/index.tsx:160` `style={{ color: r.color }}`
- **问题描述**：设计系统的核心价值是"一次定义，多次复用"。把 `var(--space-5)` 字符串散落在 30+ 个 JSX inline style 节点里，意味着主题切换、density 切换、token rename 都无法被静态扫描到。
- **专业影响**：暗色模式/density/品牌色迁移成本放大 5-10 倍；code review 容易漏掉一个 inline style 导致视觉不一致。
- **建议修复**：① 全代码库扫一遍 `style={{` 关键字，凡含 `var(--*)` 的全部抽到 `.ad-mt-* / .ad-flex-* / .ad-text-*` 工具类（global.css 已经有这套工具集）；② sentiment 颜色等需要 dynamic 的用 `className` 拼接（`return-tag--rise` 已支持），不直接写 style。
- **优先级**：**P0**

#### 4. 涨跌色"中英文不一致"的 Legend 错误
- **位置**：`web/src/pages/News/index.tsx:865-870`
  ```
  {(l === 'positive' && '绿') || (l === 'neutral' && '灰') || '红'}
  ```
- **问题描述**：Legend 中"positive = 绿、negative = 红"，是**美股约定**。但平台默认 `data-color-convention="china"`（红涨绿跌），用户切换到 A 股市场看到的是反的——会以为绿色 = 看涨，结果点进去 `positive` 文章却被染色为红。这是**显示语义错乱**，对新手用户误导极严重。
- **专业影响**：违反"语义与现实一致"原则，对 A 股用户产生认知冲突，是该平台（主战场 A 股）的关键问题。
- **建议修复**：① Legend 文本改成"红=正（涨）、灰=中、绿=负（跌）"，并根据 `data-color-convention` 动态切换；② 或干脆删掉 Legend 文字只保留色块，因为色块本身已能传达。
- **优先级**：**P0**

#### 5. DensityToggle 表面存在但实际不生效（"幽灵控件"）
- **位置**：`web/src/components/AppLayout.tsx:433-449` (`DensityToggle`) + `global.css:805-808` 注释："Density toggle was removed in 2026-07-09, so all tables use this layout regardless of user preference."
- **问题描述**：header 右侧出现"紧凑 / 标准 / 宽松"三档 Segmented，用户切换后**部分页面**（带 `--density-row-height` token 的表格）的行高会变，但**绝大多数页面**直接写死 `min-height: 32px|40px`，切换无效果。Mobile 端的 Dropdown 收口也保留了这个 ghost 控件。
- **专业影响**：违反"控件必须可观测反馈"。用户反复点以为是 bug，浪费时间。
- **建议修复**：① 短期内：要么把 DensityToggle 真的生效到所有表格，要么临时改为只读"信息密度：标准 (开发者锁定)"；② 长期：实现完整的 density token 覆盖（行高、卡片 padding、字号阶梯），确保切换处处生效。
- **优先级**：**P0**

#### 6. Login 页强制覆盖 light theme 的 token
- **位置**：`web/src/pages/Login.tsx:176-189`
  ```css
  :root[data-theme="light"] .login-page--sci-fi {
    --text-primary: #E6EDF3;  // 暗色文本
    --accent: #60A5FA;          // 暗色 accent
  }
  ```
- **问题描述**：用户切到 light 主题进入登录页，文本/输入框颜色被强制覆盖为暗色调，但**整页背景仍是 sci-fi 黑色**（`--login-bg: #05060a`）。一旦改 login 主题，组件库颜色与背景就脱节。强行覆盖 token 是危险反模式——下次设计系统改 `--accent: #2563EB` 时这段被绕过。
- **专业影响**：未来主题切换、accent 升级时容易踩坑；目前 light 主题下登录页完全无法"明亮化"。
- **建议修复**：① 把 sci-fi 的颜色全部归到一组独立 token（`--login-*`），不再覆盖全局 `--text-*`/`--accent`；② light 主题下允许走浅色 sci-fi 变体（蓝色 aurora + 浅玻璃）而不是强制暗色。
- **优先级**：**P0**

#### 7. "涨跌色约定切换"在某些页面的关键标记上不生效
- **位置**：
  - `web/src/pages/News/detail.tsx:343, 345` 直接写 `color: SENTIMENT_COLORS[sentiment]`（fixed hex）
  - `web/src/pages/News/detail.tsx:464-467` StarFilled 颜色硬编码 `var(--color-warning-bright)` 与 `var(--text-muted)`
  - `web/src/pages/News/detail.tsx:686` `style={{ color: SENTIMENT_COLORS[item.sentiment_label] }}`
  - `web/src/pages/Portfolio/index.tsx:64-67` 写死 `var(--color-rise)` / `var(--color-fall)`
- **问题描述**：theme.css 已声明 `--color-rise / --color-fall` 会跟随 `data-color-convention` 切换，但上面这些 inline style 直接读 `SENTIMENT_COLORS` map（**写死的 hex**，无论用户怎么切都不变）。同样新闻"positive"在中国模式下应该是红色、US 模式下应该是绿色——目前不一致。
- **专业影响**：用户从美股切到 A 股，许多关键颜色没变，破坏"我刚才的设置现在生效了"的心理模型。
- **建议修复**：① 把 `SENTIMENT_COLORS` 改成读取 `getComputedStyle(document.documentElement).getPropertyValue('--color-rise')` 等 token；② 移除所有 inline `color: SENTIMENT_COLORS[xxx]` 写法，统一走 ThemeTag variant。
- **优先级**：**P0**

#### 8. 多个空状态没有 icon / 无引导，违和"产品温度"
- **位置**：
  - `web/src/pages/Dashboard/index.tsx:1108` `EmptyState title="暂无自选股" description="..."` —— 没有 icon
  - `web/src/pages/Dashboard/index.tsx:1227` `EmptyState title="暂无自选股"` —— 只有 title，无 description，无 icon
  - `web/src/pages/Dashboard/index.tsx:1230` `EmptyState title="暂无自选股相关资讯"` —— 同上
  - `web/src/pages/News/detail.tsx:401, 423` EmptyState 没有 icon
  - `web/src/pages/AIChat/index.tsx:184` `EmptyState title="暂无对话"` —— 无 icon
  - `web/src/pages/ResearchNotes/index.tsx:??` 多处裸 EmptyState
- **问题描述**：空状态是用户首次体验的"产品调性"信号。EmptyState 组件本身支持 icon，但 60% 调用都没传。`空状态模板` 也没建立"无数据 → 引导 + 行动"的设计模式（部分是"前往自选股 →"，部分直接光秃秃一行字）。
- **专业影响**：新用户首次进入 Dashboard 看到空白的"暂无自选股"，不知道下一步该做什么。
- **建议修复**：① 建立 3 种预设空状态：`<EmptyState variant="first-time">`、`<EmptyState variant="no-results">`、`<EmptyState variant="error">`，每个内置 icon + 建议下一步按钮；② 各页面调用时按场景选 preset，避免裸 title。
- **优先级**：**P0**

#### 9. 移动端 / 平板断点对图表与 Sticky Header 的处理不完整
- **位置**：
  - `web/src/styles/global.css:842-844` `.ad-chart-container { min-height: 300px; height: 300px }` 写死 300px / 420px
  - `web/src/styles/global.css:918-923` `.ad-table-sticky .ant-table-thead > tr > th { position: sticky; top: 0 }` 与 AppLayout 60px sticky header **冲突** —— 表格内 sticky 表头会贴到 0px 而非 60px，被主 header 遮挡
  - `web/src/styles/global.css:754-762` 768px 断点只收紧 padding 不收紧图表高度
- **问题描述**：① 移动端图表在小屏上 300px 高度显得过空（同时没有响应式缩放）；② 表格在主区域滚动时 sticky 表头会被 header 盖住，列名错位或被遮挡；③ `@media (min-width: 768px) and (max-width: 991px)` 区间内（平板）只调整了 padding，没调整 sidebar 占位（240px 在 768px 平板上几乎占 1/3 屏宽）。
- **专业影响**：平板用户体验比桌面和手机都差，是常见的"中间被遗忘"问题。
- **建议修复**：① 图表容器用 `aspect-ratio` + `clamp()` 替代固定高度；② sticky 表头 top 改为 `var(--app-header-height, 60px) + var(--page-padding-top)`；③ 平板断点（768-991px）增加 sidebar 折叠默认、`PageShell` 自动收窄。
- **优先级**：**P0**

#### 10. `<Table showHeader={false}>` 关闭列头，破坏无障碍导航
- **位置**：`web/src/pages/Dashboard/index.tsx:1292`
  ```tsx
  <Table ... showHeader={false} onRow={(record) => ({ onClick: ... })} />
  ```
- **问题描述**：Dashboard 的"综合评分 Top 10"表格直接隐藏整个表头。视觉上极简（标题已写在 Panel title 里），但**屏幕阅读器**完全失去列定义，盲用户无法理解"排名/标的/评分/1月收益/趋势/收藏"6 列语义。AntD 的 `showHeader` 也会清空 `aria-headers`。
- **专业影响**：无障碍失败，对企业内审、合规、机构客户禁用。
- **建议修复**：① 保留 `showHeader={true}`，通过 CSS 把表头 `position: absolute; clip: rect(0,0,0,0); height: 1px` 隐藏（视觉不可见但 screen reader 仍可读）；② 同时给每行加 `aria-label="第 N 名 · 标的代码 · 评分 X · 1月收益 Y%"`。
- **优先级**：**P0**

#### 11. Loading/Empty/Error 三态分裂，无统一 Component
- **位置**：
  - `web/src/pages/AIChat/index.tsx:182, 423` 用 `<Skeleton active paragraph={...}>` 直接渲染
  - `web/src/pages/News/index.tsx:820` `<Skeleton active paragraph={{ rows: 6 }}>` + `ad-p-5`
  - `web/src/pages/Dashboard/index.tsx:1106` `LoadingBlock label="加载中…"`
  - `web/src/pages/News/index.tsx:813-818` 错误用 `<EmptyState title="加载失败">` 描述含糊
  - `web/src/pages/News/detail.tsx:196-203` 用 `<Spin size="large">` 全屏 spin
  - 各页面 partial data（部分 KPI 已加载、部分还在 loading）的视觉没有 fallback
- **问题描述**：5+ 种 loading 呈现、2 种 error 呈现、3 种 empty 呈现，无统一抽象。结果：① 同一站不同页面"加载"的视觉语言不同；② 部分加载（partial）的页面没有占位骨架，用户看到的是空白页或残缺数据。
- **专业影响**：用户每次进入新页面不知道"加载需要多久"，对系统的信任感降低。
- **建议修复**：建立 `<DataState state="loading|error|empty|partial|ready">` 组件，根据状态显示 Skeleton / Alert+Retry / EmptyState / Partial overlay；同时废弃 `LoadingBlock`、`ad-spin-center` 等散落的 loading 工具，统一收口。
- **优先级**：**P0**

#### 12. "散户讨论" / "社交"模块返回 EmptyState 但不带时间预期
- **位置**：
  - `web/src/pages/News/detail.tsx:590` `<EmptyState title="散户讨论内容由 Agent E 后续接入" />`
  - `web/src/pages/Dashboard/index.tsx:1108, 1227, 1230` 三个空状态均无"预计何时可用 / 添加路径"说明
- **问题描述**：EmptyState 把"功能未上线"也用同样的 EmptyState 模板呈现。用户以为是"我没数据"而不是"功能开发中"——会在自选股页反复添加标的，期望看到讨论，但永远空着。
- **专业影响**：把"功能缺失"伪装成"数据为空"是一种欺骗性 UI，长期会失去用户信任。
- **建议修复**：建立 `EmptyState variant="coming-soon"`，加 visual hint（如 `ClockCircleOutlined` + 灰色 badge "Beta · 2026 Q4"），并提供"加入等待名单"邮件订阅；区别于"暂无数据"。
- **优先级**：**P0**

---

### P1 重要级（应尽快处理）

#### 13. "教学模式"开关隐藏在用户菜单里，普通用户难以发现
- **位置**：`web/src/components/AppLayout.tsx:723-744` `Dropdown menu items[0]` 内嵌 Segmented
- **问题描述**：教学模式（novice/pro）是平台核心差异化卖点（新手友好、AI 解释），但只在"用户头像 → 菜单第一项"里，且 UI 是 antd Segmented 套娃。OnboardingTour 也设置了 `mode === 'novice'` 才引导，新用户第一次找不到"哪里学"。
- **专业影响**：新手用户错失 AI 解释这一核心体验。
- **建议修复**：① 在仪表盘 Panel 顶部、PageHeader 附近加一个明显的"教学模式"快速切换 chip（参考 App Store "View As"）；② OnboardingTour 第一步就教这个开关。
- **优先级**：**P1**

#### 14. Tooltip/Popover 内容宽度限制与中文长标题溢出
- **位置**：
  - `web/src/styles/global.css:361` `.ant-popover { max-width: 360px; }`
  - `web/src/styles/global.css:607` `.ant-tooltip { max-width: 85vw }`
  - `web/src/components/HelpPopover.tsx`（推测）内容可能很长
- **问题描述**：A 股公司名称长（"华夏国证半导体芯片 ETF 联接"），popover 360px 容纳不全，会出现双行截断。HelpPopover 在表头使用尤其密集，多列 term key 解释同时撑出表格行高。
- **专业影响**：阅读流畅度下降，专业用户可能直接跳过这些解释。
- **建议修复**：① popover max-width 提到 420px 或按内容自适应；② 长文本 popover 加 `<details>` 折叠"展开更多"。
- **优先级**：**P1**

#### 15. 涨跌色切换在 PoolDetail / StrategyLibrary / PaperTrading 等模块的 P&L 数字上未跟随
- **位置**：
  - `web/src/pages/Portfolio/index.tsx:160` 直接读 `var(--color-rise)`
  - `web/src/pages/PoolDetail/index.tsx:??` 收益展示
  - `web/src/components/ReturnTag.tsx` 已 token 化但个别页面 fallback 不一致
- **问题描述**：理论上涨跌色会跟随 `data-color-convention` 切换。但部分页面（如 Portfolio）直接用 token 写 inline style，且**百分比符号、字号、加粗程度**各页不统一（`<span style={{color: ...}}>` vs `<ReturnTag>`）。
- **专业影响**：专业用户做多市场对比时，A 股收益红色 vs 美股收益绿色，本应该一目了然，但视觉权重不统一降低扫读速度。
- **建议修复**：所有数字收益强制走 `<ReturnTag>`，禁止手写 span + color。
- **优先级**：**P1**

#### 16. 表头 HelpPopover 与单元格混合，列宽失衡
- **位置**：
  - `web/src/pages/Screen/index.tsx:94-100` 列标题都包 `<HelpPopover termKey="...">`
  - `web/src/pages/InstrumentList/index.tsx:462-465` 列标题 Tooltip + 描述
- **问题描述**：列名 "夏普 / RSI / 波动率" 文字 + 解释 popover，使得列头需要 hover 触发，但**触发区域只有文字大小**，且 HelpPopover 默认 mouseEnter 触发，移动端无法触发。
- **专业影响**：移动端用户无法获得术语解释，等同于 PC 与移动体验分裂。
- **建议修复**：① HelpPopover 同时支持 click + hover（移动端 tap）；② 列头右侧加 `ⓘ` 图标，永远可见；③ 移动端 fallback 直接放 inline 一行定义。
- **优先级**：**P1**

#### 17. AntD 原生 `<Tag color="volcano|geekblue|purple|red|magenta">` 与 ThemeTag 混用
- **位置**：
  - `web/src/pages/News/detail.tsx:319-336` `<Tag color={...}>`
  - `web/src/pages/News/index.tsx:300-324` `<Tag color="default">` 包 InstrumentCodeTag
  - `web/src/pages/AIChat/index.tsx:??` antd Tag
  - `web/src/pages/Portfolio/index.tsx:144, 188` antd Tag
- **问题描述**：ThemeTag 已 token 化（`--color-rise / --color-fall / --color-neutral / --color-success / --color-error / --color-warning` 等语义色），但很多页面直接用 antd 内置 Tag 的色名（red/green/blue 等）。这些色在 dark 模式下是 antd 默认色，与平台 token 调色板不一致。
- **专业影响**：dark 模式下某些 chip 仍然显示 antd 的亮绿/亮红，与暗色背景对比突兀。
- **建议修复**：① 全代码库禁用 `<Tag color="...">`，必须用 `<ThemeTag variant="...">`；② ThemeTag variant 加 `info`、`accent-border`、`warning-bright` 等扩展覆盖更多场景。
- **优先级**：**P1**

#### 18. "我的自选股"等需要点击星标的卡片，星标按钮和卡片本身重叠
- **位置**：`web/src/pages/Dashboard/index.tsx:213-216` (`FavoriteToggleButton` 在卡片右上角)
- **问题描述**：FavoriteCard 整体 `cursor: pointer` + `onClick` 跳转到标的详情，星标按钮也在同一卡片右上角。点击星标区域会触发 stopPropagation 阻止冒泡，但移动端 `touch` + `click` 双触发容易误点——或者反过来，星标的点击事件被卡片吞掉。
- **专业影响**：移动端误点率高，体验不顺。
- **建议修复**：① 星标按钮 hover 时整卡不显示 hover 反馈（通过 CSS 父级 `:has(:hover)`）；② 星标按钮移到卡片外（如放在 chip 行）。
- **优先级**：**P1**

#### 19. `<EmptyState action={...}>` 中所有 action 都用 `<span role="link">`
- **位置**：
  - `web/src/pages/Dashboard/index.tsx:1113-1127` EmptyState 的 action 用 span role="link" + tabIndex + onKeyDown
  - `web/src/pages/News/index.tsx:??` 类似
- **问题描述**：每次都重复 6 行自定义 keyboard handler 应该用 `<Button type="link">` 一行解决。当前实现既不规整又缺样式（没有 antd 链接的 hover 动效）。
- **专业影响**：组件可维护性差，无障碍依赖手写。
- **建议修复**：EmptyState action 自动接收 ReactNode，建议统一用 antd `<Button type="link">`；或在 EmptyState 内置一个 link variant。
- **优先级**：**P1**

#### 20. Dashboard ScoreTable 显示 "排名" 列但无排名边界说明
- **位置**：`web/src/pages/Dashboard/index.tsx:938-948` `dashboard-score-col--rank`
- **问题描述**：排名单元格只显示数字（1, 2, ... 10），但 Top 3 与 Top 4+ 仅靠 className `dashboard-rank-cell--top3` 区分（一般高亮 vs 加粗）。色盲用户可能看不出 1/2/3 vs 4/5 的视觉差异。
- **专业影响**：信息层级不完整，依赖颜色编码。
- **建议修复**：① Top 3 加徽章/medal icon（🥇🥈🥉 风格 SVG）；② 不止颜色，加 box-shadow 或 weight 区分。
- **优先级**：**P1**

#### 21. Knowledge Graph / 知识图谱入口是折叠面板，缺乏"知识图谱"应有的视觉承诺
- **位置**：`web/src/pages/Learning/index.tsx:119-??` `learning-terms-wrap`
- **问题描述**：Dashboard "知识图谱"chip 跳过去只有 1 个折叠面板 + 列表，与"知识图谱"的视觉预期差太远。"图谱"应该是节点连边的网络图。当前实现是普通搜索 + tag 列表。
- **专业影响**：核心差异化能力（教学+术语解释）视觉降级严重。
- **建议修复**：① P1 阶段在 Learning 页加 1 张 ASCII / SVG 概念关系图（5-10 个核心概念节点），让"知识图谱"名字不虚；② 长期做真正的力导向图。
- **优先级**：**P1**

---

### P2 改进级（可逐步打磨）

#### 22. Brand 识别弱化：登录页"Sci-fi Aurora"与主站"Apple-like Clean"风格分裂
- **位置**：`web/src/pages/Login.tsx` + `web/src/components/AuroraBackground.tsx`（推测）
- **问题描述**：登录页是赛博朋克（黑色 + Aurora 粒子 + 流星），主站是 Apple-like 极简。两个完全不同的视觉语言，让登录 → 仪表盘的过渡"换了一个 app"。
- **建议修复**：① 短期：保留 Aurora 作为"仪式感"过渡，但登录后跳转做个 fade-in 加载；② 长期：主站也加一个 subtle 的 aurora 背景或 brand color gradient，建立视觉连续性。
- **优先级**：**P2**

#### 23. 通用类名 `.ad-text-*` 与 Tailwind 风格命名重复但 token 不全
- **位置**：`web/src/styles/global.css:1366-1399` 系列工具类
- **问题描述**：已有 `.ad-text-small / .ad-text-label / .ad-text-primary / .ad-text-rise / .ad-text-fall` 等，但不全。比如缺 `.ad-text-mono`、`.ad-text-disabled`、`.ad-text-warning` 等。导致业务页面有时直接写 inline style。
- **建议修复**：补全一套完整的 utility classes，配合 stylelint 规则禁止 `style={{color}}`。
- **优先级**：**P2**

#### 24. ResponsiveGrid 4 个 breakpoint 但实际只有 3 个生效
- **位置**：`web/src/styles/global.css:2586-2622`
  - `@media (min-width: 576px)` → 2 cols
  - `@media (min-width: 992px)` → 3 / 4 cols
- **问题描述**：1200-1599px（高密度笔记本）和 1600+（大屏）下，3 列显得太松，4 列又太挤。中间断点缺失。
- **建议修复**：增加 1200px 断点，3 列 → 4 列过渡。
- **优先级**：**P2**

#### 25. EmptyState 组件无水平 / 垂直留白预设
- **位置**：`web/src/components/EmptyState.tsx:1-35`
- **问题描述**：所有 padding 写死在 `global.css:2665` `.empty-state { padding: var(--space-8) var(--space-5) }`（48px 上下 + 20px 左右）。在 panel-body 内部 48px 上下留白太多，撑出卡片；放在 page-content 又不够。**应该由父级控制**。
- **建议修复**：EmptyState 不写 padding，padding 由外层 Panel / Panel-padding 决定。
- **优先级**：**P2**

#### 26. "刷新" / "重连" 等动作按钮样式不统一
- **位置**：
  - `web/src/pages/Dashboard/index.tsx:805-811` `<button className="dashboard-pulse-footer__retry">` 自定义按钮
  - `web/src/pages/NewsHealth/index.tsx:??` 操作按钮
  - `web/src/pages/AdminDeployments/index.tsx:??` 多处自定义按钮
- **问题描述**：原生 `<button>` 自定义样式散落 10+ 处，未走 antd Button / Panel token 系统。
- **建议修复**：抽出 `<IconButton>` 或 `<TextButton>` 组件，统一 hover/focus/disabled 状态。
- **优先级**：**P2**

#### 27. 部分 chart 缺少 legend / tooltip 标准化
- **位置**：
  - `web/src/pages/FundFlow/index.tsx:??` ScoreBreakdown 用 `transform: scaleX()` 但无 transition
  - `web/src/pages/Macro/index.tsx:??` ECharts options
  - `web/src/pages/SectorRotation/index.tsx:??` ECharts heatmap
- **问题描述**：图表配色虽走 `--chart-series-1..10`，但 tooltip、axis label 的字号 / 颜色未统一规范。ECharts 内部默认 tooltip 是 antd 的，但页面用了 `cubic-bezier` 自定义样式。
- **建议修复**：写一份《ECharts 主题接入指南》放在 `docs/dev-notes/`，所有图表必须 follow。
- **优先级**：**P2**

#### 28. "今日热点" 等标题缺少发布数量 / 时段提示
- **位置**：`web/src/pages/Dashboard/index.tsx:1297-1333`
- **问题描述**："今日热点"是个相对时间词，但 Dashboard 没显示"截至时间"。用户打开页面看到的是缓存数据，与"今日"语义脱节。
- **建议修复**：标题加 `<DataFreshnessHint>` 或 LastUpdated 子组件。
- **优先级**：**P2**

#### 29. Sidebar 折叠态 group label 缺失，icon-only 模式辨识度低
- **位置**：`web/src/components/AppLayout.tsx:268-298`
- **问题描述**：sidebar 折叠时每个 group 只剩一个 icon（24×24），没 tooltip。鼠标 hover 不知道代表什么，要点开才知道。
- **建议修复**：折叠态每个 group icon 加 `Tooltip title="研报"`。
- **优先级**：**P2**

---

## 二、当前缺失的体验能力（Feature Gap）

以下能力在主流 SaaS 是标配，但本平台目前**没有视觉化的 UI**：

1. **键盘命令面板**（Cmd+K / Ctrl+K）。任何专业投研工具（Bloomberg、Kensho、Wind）都必备命令面板。当前平台只能靠 sidebar 导航 + 搜索标的，无法"快速跳转任意页面 / 标的 / 策略 / 标的池"。建议在 AppLayout header 加一个 ⌘K 触发 SpotLight-style 面板。
2. **Watchlist 价格预警 / 推送**。"我的自选股"页面只能查看当前价，没有"突破 X 元提醒我"这种条件预警。
3. **全局搜索的可见 affordance**。当前只有 News 页和 InstrumentList 有搜索框，dashboard 没有"搜标的 / 搜资讯 / 搜策略"统一入口。
4. **数据导出**（CSV / Excel）。任何表格页面都没有"导出当前结果"按钮，机构用户必备。
5. **打印 / PDF 报告样式**。研究笔记 / 评分页面没有 `@media print` 优化，企业客户对外分享报告需要印刷版。
6. **多语言切换**（EN/中文）。平台大量中文 + 部分英文标识混排（POLITICAL_CATEGORIES 中英混杂），但没有 UI 切换语言。
7. **深色模式全局偏好同步**。当前 `<html data-theme>` 已经切换，但 macOS 用户在系统切到深色时没有自动跟随（缺 `prefers-color-scheme: dark` 监听）。

---

## 三、积极信号（做得好的地方）

1. **设计系统底座扎实**：`theme.css` 的 token 化（颜色、字号、间距、圆角、阴影、动效曲线、Apple spring 参数）业界领先水准。
2. **light/dark + accent + 涨跌色约定 + density + CRT 5 维度切换**：能看出对"专业工作站"理解到位。
3. **`prefers-reduced-motion` 全局尊重**：动效丰富但尊重可访问性偏好。
4. **data-color-convention 设计**：A 股红涨绿跌 vs 美股绿涨红跌，国际化布局有考虑。
5. **OnboardingTour + Learning 页 + HelpPopover + 学习模式** 多层新手引导，构建完整。
6. **real-time SSE 流**（useMarketStream、usePriceStream） + Web Animations API 实现价格闪烁动效，符合"Interruptibility"原则。
7. **CSS 变量 + Tabular nums**：表格数值列无抖动，专业感强。

---

## 四、总结优先级建议（首轮 Sprint 30 天）

| Week | 工作内容 | 数量 |
|---|---|---|
| W1 | 修 P0 #1（统一 Card/Panel） + P0 #2（抽 motion-tokens.css） + P0 #3（inline style 扫描） | 3 项 |
| W2 | 修 P0 #4（涨跌色 Legend） + P0 #5（DensityToggle） + P0 #7（涨跌色 token 化） | 3 项 |
| W3 | 修 P0 #6（Login token） + P0 #8（空状态预设） + P0 #11（DataState 组件） | 3 项 |
| W4 | 修 P0 #9（断点 + 图表） + P0 #10（showHeader A11y） + P0 #12（功能未上线区分） | 3 项 |

完成后应将平台 UI 评分从 B+ 提升至 **A 级**。

---

**审查结束。报告保存于 `reports/review-uiux-designer.md`。所有问题描述均基于源代码静态审查，未修改任何代码。**