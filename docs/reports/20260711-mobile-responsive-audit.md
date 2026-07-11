# AD-Research 前端移动端适配问题审计报告

**审计日期**：2026-07-11  
**审计范围**：

- `/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/components/AppLayout.tsx`
- `/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/Login.tsx`
- `/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/AdminUsers/index.tsx`
- `/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/AdminDeployments/index.tsx`
- `/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/ETLOpsDashboard/index.tsx`
- `/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/NotificationConfig/index.tsx`
- 相关样式文件：`web/src/styles/global.css`、`web/src/components/AppLayout.css` 等

**审计断点**：375px（小屏手机）、768px（平板/小桌面）  
**严重度说明**：

- **P0**：阻塞级，移动端功能不可用或内容无法阅读，必须立即修复。
- **P1**：重要，显著影响移动端可用性或操作准确性，建议高优先级修复。
- **P2**：轻微，体验打磨项，可后续迭代处理。

---

## 关键发现摘要

本次审计共发现 **2 个 P0、16 个 P1 和 16 个 P2** 问题。最严重的问题集中在：

1. **AppLayout 主内容区在移动端未重置 `margin-left: 240px`**，导致 375px 视口下可用宽度仅剩约 103px，页面基本无法阅读。
2. **Login 登录面板在 375px 下因 `content-box` 内边距导致总宽度溢出视口 64px**，用户名、密码输入框被截断。

其余高频问题包括：

- 大量 `size="small"` 的 Ant Design 操作按钮高度仅 32px，低于 44px 触控目标。
- 多个管理表格列宽过宽（AdminDeployments 7 列约 740px、NotificationConfig 固定列宽 550px+），移动端需大量横向滚动。
- 768px 断点未充分覆盖，平板/小桌面仍走桌面布局，控件拥挤。
- 多处未处理 `100dvh`、安全区（safe-area-inset）和文本截断。

---

## P0 阻塞级问题

### 1. AppLayout — 移动端主内容区未重置 `margin-left: 240px`

- **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/components/AppLayout.tsx` 第 596 行；`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/styles/global.css` 第 3088-3095 行
- **问题**：在 `<768px` 时桌面侧边栏被条件渲染移除，但 `.app-layout__main` 仍保持 `margin-left: 240px`。`app-layout__main--mobile` 类没有对应的 CSS 重置。在 375px 视口下，主内容区实际可用宽度仅剩约 103px，所有页面内容被严重压缩，基本无法阅读或操作。
- **严重度**：P0
- **修复建议**：在移动端媒体查询中重置主内容区边距：
  ```css
  @media (max-width: 767px) {
    .app-layout__main { margin-left: 0; }
  }
  ```
  或显式给 `.app-layout__main--mobile` 添加 `margin-left: 0`。

### 2. Login — 375px 下登录面板因 content-box 内边距溢出截断

- **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/styles/global.css` 第 6953-6962 行、第 7254-7268 行
- **问题**：`.login-glass` 使用 `padding: 32px`，`.login-brand-panel` / `.login-form-panel` 使用 `width: 100%`，但未设置 `box-sizing: border-box`。内容宽 335px 加上 64px 内边距后渲染总宽 399px，超出 375px 视口 64px，导致登录面板左右被截断、出现横向滚动。
- **严重度**：P0
- **修复建议**：为 `.login-glass` 及两个面板添加 `box-sizing: border-box`，或改用 `max-width: calc(100vw - 40px)` 并在移动端收紧 padding。

---

## P1 重要问题

### 3. AppLayout — 主题切换按钮在移动端设置菜单中被隐藏

- **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/components/AppLayout.css` 第 84-89 行；`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/components/AppLayout.tsx` 第 361-376、699 行
- **问题**：`ThemeToggle` 复用了 `.app-layout__header-collapse` 类，该类在 `@media (max-width: 767px)` 下被 `display: none` 隐藏。由于移动端把主题切换放在“设置”下拉菜单中，菜单里的主题按钮完全不可见，用户无法在移动端切换主题。
- **严重度**：P1
- **修复建议**：为 `ThemeToggle` 单独定义一个非 `app-layout__header-collapse` 的类名；或直接移除对该类的移动端 `display: none`（`CollapseToggle` 已通过 `!isMobile` 条件渲染，移动端不会出现在 header 中）。

### 4. AppLayout — 移动端抽屉导航项触控目标不足

- **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/styles/global.css` 第 8519-8521 行、第 8523-8528 行
- **问题**：移动端抽屉中的分组标题 `.app-layout__nav-group-header` 仅设置 `padding: 8px var(--space-3)`，实际高度约 32-36px；二级导航项 `.app-layout__nav-item` 设置 `min-height: 40px`，均低于 44px 推荐触控目标。用户展开/切换菜单时极易误触。
- **严重度**：P1
- **修复建议**：将抽屉内分组标题和导航项统一设为 `min-height: 44px`，上下 padding 调整为 10-12px，并设置 `align-items: center`。

### 5. AppLayout — 768px 平板侧边栏触控目标仍偏小

- **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/styles/global.css` 第 2834-2852 行、第 2926-2954 行、第 8171-8461 行
- **问题**：在 768px 断点，`useIsMobile` 返回 `false` 显示桌面侧边栏。但 `.app-layout__nav-item` 默认 `min-height: 36px`，分组标题约 36px，collapsed 图标项 40px，均未达到 44px 触控目标。平板触屏体验不佳。
- **严重度**：P1
- **修复建议**：在 `max-width: 991px` 媒体查询下，为 `.app-layout__nav-item` 和 `.app-layout__nav-group-header` 统一设置 `min-height: 44px`；collapsed 图标项改为 44×44px。

### 6. AppLayout — 使用 `100vh` 而非 `100dvh`

- **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/styles/global.css` 第 6-10 行、第 2764 行
- **问题**：`html, body` 与 `.app-layout` 使用 `min-height: 100vh`。在 iOS Safari 等移动浏览器中，动态工具栏（地址栏收缩/展开）会导致 100vh 高度计算不准确，footer 可能被遮挡或出现不可点击区域。
- **严重度**：P1
- **修复建议**：改为 `min-height: 100dvh`，并保留 `100vh` 回退：
  ```css
  min-height: 100vh;
  min-height: 100dvh;
  ```

### 7. AppLayout — 固定元素未处理安全区

- **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/styles/global.css` 第 3102-3115 行（header）、第 3214-3222 行（footer）、第 8510 行（drawer logo）
- **问题**：吸顶 header、抽屉 logo、footer 等固定元素未使用 `env(safe-area-inset-top/bottom)`。在 iPhone 刘海/灵动岛或 PWA 模式下，header 顶部可能被状态栏遮挡，底部内容可能被 Home 指示条覆盖。
- **严重度**：P1
- **修复建议**：在 `index.html` 的 viewport meta 添加 `viewport-fit=cover`；给 header 添加 `padding-top: env(safe-area-inset-top, 0)`；给 footer 添加 `padding-bottom: env(safe-area-inset-bottom, 0)`。

### 8. AppLayout — 768px 平板 header 右侧控件拥挤

- **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/components/AppLayout.tsx` 第 663-669 行
- **问题**：在 768px 且侧边栏展开时，header 右侧同时渲染 `CollapseToggle`、`DensityToggle`、`ColorConventionToggle`、`ThemeToggle`。中文标签较长，加上长面包屑后，可用空间紧张，右侧控件可能被 `overflow: hidden` 截断或挤压面包屑。
- **严重度**：P1
- **修复建议**：在 `768px-991px` 断点将 `DensityToggle` 与 `ColorConventionToggle` 也移入 settings dropdown（与 `<768px` 保持一致），或给 header-controls 添加 `flex-wrap` 并允许在极端窄屏下换行。

### 9. Login — 输入框 14px 字体会触发 iOS 缩放

- **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/styles/global.css` 第 7139-7148 行
- **问题**：`.login-page--sci-fi .login-input` 的 `font-size: 14px` 小于 16px。在 iOS Safari 聚焦输入框时会触发页面缩放，破坏登录体验，且缩放后退出焦点可能无法还原。
- **严重度**：P1
- **修复建议**：在 `@media (max-width: 767px)` 中覆盖为 `font-size: 16px`；或全局把 `.login-input` 改为 16px（placeholder 可保留 14px）。

### 10. Login — 100vh + overflow:hidden 导致小屏/横屏内容无法滚动

- **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/styles/global.css` 第 6574-6582 行
- **问题**：`.login-page` 同时设置 `height: 100vh` 与 `overflow: hidden`。在 375px 高度（如 iPhone SE 横屏）下，堆叠后的品牌面板+表单面板+免责声明会超出 100vh，且无法滚动，导致登录按钮和底部文字被截断。
- **严重度**：P1
- **修复建议**：在移动端媒体查询中改为：
  ```css
  .login-page { height: auto; min-height: 100vh; overflow-y: auto; }
  ```

### 11. Login — 768px 断点未覆盖，双列布局品牌名溢出

- **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/styles/global.css` 第 6943-6950 行、第 6999-7028 行、第 7247 行
- **问题**：移动端断点为 `max-width: 767px`，在 768px 时仍然走双列布局。受 content-box 大内边距（40px×2）影响，品牌面板内容区被压缩到约 202px，扣除图标和间隙后仅剩约 140px，而 `font-size: 28px` 的 “AD-Research” 宽度超出可用空间，导致文字溢出或被截断。
- **严重度**：P1
- **修复建议**：将媒体查询改为 `max-width: 768px`（或更宽松的 991px），使 768px 直接切换为单列布局；同时降低品牌名字号并缩小面板内边距。

### 12. AdminUsers — 操作列 240px 过宽且按钮未堆叠

- **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/AdminUsers/index.tsx` 第 157-196 行
- **问题**：操作列固定宽度 240px，内部并排放置编辑、重置密码、删除三个按钮。在 375px 视口下，该列本身就占掉约 2/3 屏幕宽度，导致表格必须水平滚动；按钮在移动端仍保持单行，无法自动堆叠。
- **严重度**：P1
- **修复建议**：移动端将三个操作按钮合并为「操作」下拉菜单，或使用 `flex-wrap: wrap` / `flex-direction: column` 在小屏下堆叠按钮；移除或降低操作列固定 240px 宽度，允许其收缩。

### 13. AdminUsers — 操作按钮高度仅 32px

- **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/AdminUsers/index.tsx` 第 161-195 行
- **问题**：操作按钮使用 `size="small"`。全局 CSS 对移动端的 `.ant-btn-sm` 仅设置 `min-height: 32px`，低于 44px 推荐触控目标。
- **严重度**：P1
- **修复建议**：操作按钮在移动端改用 `size="middle"`，或通过媒体查询强制 `.ant-btn-sm` 在移动端最小高度为 44px；同时增大按钮间距。

### 14. AdminDeployments — 部署历史表格 7 列合计过宽

- **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/AdminDeployments/index.tsx` 第 63-156 行
- **问题**：部署历史表格有 7 列，固定宽度合计约 740px。在 375px 和 768px 下都远超可用视口，必须依赖水平滚动才能查看完整信息。
- **严重度**：P1
- **修复建议**：在 768px 以下隐藏次要列（如分支、耗时、触发人），或切换到卡片/列表视图；保留 `scroll={{ x: 'max-content' }}` 与全局 `.ant-table-wrapper` 的 `overflow-x: auto` 作为兜底。

### 15. AdminDeployments — Commit SHA 未截断撑开列宽

- **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/AdminDeployments/index.tsx` 第 97-113 行
- **问题**：Commit 列显示完整 40 位 SHA，未做截断。虽然列声明 `width: 120`，但长内容会自然撑开列宽，进一步加剧表格横向滚动。
- **严重度**：P1
- **修复建议**：将 SHA 截断为 7-8 位并加 `text-overflow: ellipsis`，把完整 SHA 放到 Tooltip 中；或给链接添加 `.ad-truncate` 工具类。

### 16. ETLOpsDashboard — Descriptions 组件强制两列布局

- **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/ETLOpsDashboard/index.tsx` 第 147 行
- **问题**：`Descriptions` 使用 `column={2}`，在 375px 下会强制两列布局。面板内边距 + PageShell 内边距后可用宽度仅约 311px，每列仅 150px 左右，标签与内容严重拥挤，日期/状态文本容易换行或撑破单元格。
- **严重度**：P1
- **修复建议**：改为响应式列数：`column={{ xs: 1, sm: 1, md: 2, lg: 2 }}`；或在小屏下使用单列表。

### 17. ETLOpsDashboard — freshnessBadge 长文本溢出

- **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/ETLOpsDashboard/index.tsx` 第 156-175 行（结合第 35-52 行）
- **问题**：“A 股数据 / 美股数据 / 加密数据 / 陈旧市场” 四个 `Descriptions.Item` 都渲染 `freshnessBadge`，包含完整日期 + “(<N>d 前)”。在 375px 两列布局中字符串过长，极易撑满单元格并导致水平溢出或异常换行。
- **严重度**：P1
- **修复建议**：移动端精简显示，例如仅保留 `ageDays` 或日期；或给 `Badge` 的 `text` 设置 `max-width` + 省略号，并通过 Tooltip 显示完整信息。

### 18. NotificationConfig — 通知配置表格固定列宽过宽

- **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/NotificationConfig/index.tsx` 第 92-152 行
- **问题**：表格列固定宽度合计已达 550px（名称 180 + 渠道 120 + 状态 90 + 操作 160），再加上“详情”列内容。即使外层 `phase5c-table-wrap` 有 `overflow-x: auto`，375px 下也必须大幅横向滚动；在 768px 可用宽度约 696px 时仍可能因“详情”内容过长而触发滚动。
- **严重度**：P1
- **修复建议**：小屏下降低列宽（如名称 120、操作 120），或在 ≤767px 时隐藏次要列（如“详情”），改为点击行展开详情。

---

## P2 优化问题

### AppLayout

19. **Header 焦点环被裁剪**
    - **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/styles/global.css` 第 3177 行
    - **问题**：移动端 `.app-layout__header` 设置了 `overflow: hidden`，会裁剪 icon 按钮 `focus-visible` 的 outline 与 box-shadow，键盘/辅助操作焦点可能不可见。
    - **修复建议**：将 `overflow: hidden` 改为在子容器上设置 `min-width: 0` 来收缩面包屑，或在 header 各触控区增加足够 padding 以容纳 focus 环。

20. **桌面 header 折叠/主题按钮 36px 偏小**
    - **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/components/AppLayout.css` 第 53-67 行
    - **问题**：`.app-layout__header-collapse` 固定宽高 36px，低于 44px 触控建议；在 768px+ 平板上容易误触。
    - **修复建议**：将按钮尺寸提升到 44px；或在 `@media (max-width: 991px)` 下使用 44px 并保留 36px 视觉尺寸时扩展 invisible hit-area。

21. **移动端设置项嵌套在 Dropdown 中**
    - **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/components/AppLayout.tsx` 第 673-721 行
    - **问题**：在 `<768px` 时，“密度/涨跌色/主题”开关被塞进 `Dropdown` 的 `menu.items` 中，形成嵌套可交互区域。`Segmented` 单个选项和主题按钮的点击区域均小于 44px，且 `stopPropagation()` 与 `role="button"` 组合可能影响键盘可访问性。
    - **修复建议**：移动端改为独立的 BottomSheet/Modal/抽屉面板承载这些设置，确保每个控件热区 ≥44px；或至少给每个 menu item 设置 `min-height: 44px` 并用大内边距包裹控件。

22. **Drawer 缺少显式关闭按钮**
    - **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/components/AppLayout.tsx` 第 573-579 行
    - **问题**：移动端 Drawer 设置 `closable={false}`，没有关闭按钮。虽然点击遮罩可关闭，但缺少明确的关闭 affordance。
    - **修复建议**：设置 `closable={true}` 让 Ant Design 渲染关闭按钮，或添加自定义 header 与 `CloseOutlined` 关闭按钮，同时保留遮罩点击关闭。

23. **面包屑未设置 `min-width: 0`，可能撑开 header-left**
    - **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/styles/global.css` 第 3131-3161 行
    - **问题**：`.app-layout__breadcrumb` 子项使用 `white-space: nowrap` 但没有 `min-width: 0`。当标签较长时，flex 子项无法正确收缩，可能撑开 header-left 并把右侧控件顶出可视区。
    - **修复建议**：为 `.app-layout__breadcrumb-link` 和 `.app-layout__breadcrumb-current` 添加 `min-width: 0` 与 `overflow: hidden; text-overflow: ellipsis`；或在 375px 下仅显示“首页”与当前页。

24. **首屏 SSR/客户端切换闪烁**
    - **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/hooks/useBreakpoint.ts` 第 15-20 行
    - **问题**：`useIsMobile` 在 `screens` 为空时保守返回 `false`，首次渲染会渲染 desktop 侧边栏（240px margin），随后客户端断点计算完成才切换为 mobile，可能出现布局一闪而过的抖动。
    - **修复建议**：在 CSS 中通过 `@media (max-width: 767px) { .app-layout__sidebar { display: none; } }` 默认隐藏 mobile 下的侧边栏；或根据 `navigator.userAgent` 做首次猜测。

### Login

25. **免责声明 10px 字号过小**
    - **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/styles/global.css` 第 7288-7291 行
    - **问题**：移动端免责声明 `font-size: 10px` 低于 12px 最小可读字号，在 375px 小屏上可读性差。
    - **修复建议**：在移动端媒体查询中改为 `font-size: 12px`，并适当增加 `padding: 0 16px`。

26. **768px 断点未覆盖常用平板宽度**
    - **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/styles/global.css` 第 7247 行
    - **问题**：移动端断点 `max-width: 767px` 没有覆盖 768px 这个常用平板宽度，导致 768px 继续运行紧凑的双列布局。
    - **修复建议**：调整为 `@media (max-width: 768px)` 或 `@media (max-width: 991px)`，与设计系统常用断点对齐。

### AdminUsers

27. **用户名、创建时间未设置最大宽度或截断**
    - **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/AdminUsers/index.tsx` 第 132 行、第 151-155 行
    - **问题**：长用户名或长日期字符串会撑大列宽，使表格更宽。
    - **修复建议**：为 `username` 和 `created_at` 列添加 `ellipsis: true` 或固定 `width`/`maxWidth`，并通过 `title` 或 Tooltip 展示完整文本。

28. **Modal 使用固定宽度 480px**
    - **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/AdminUsers/index.tsx` 第 230-239 行、第 278-287 行、第 308-318 行
    - **问题**：三个 Modal 均显式设置 `width={480}`，超过 375px 视口。虽然全局 CSS 通过 `max-width: calc(100vw - 32px)` 兜底，但依赖全局覆盖较脆弱。
    - **修复建议**：使用响应式宽度（如 `width={{ xs: '90%', sm: 480 }}`），或移除固定宽度让弹窗自适应，并确保弹窗内容可滚动。

### AdminDeployments

29. **服务器健康卡片镜像标签未限制宽度**
    - **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/AdminDeployments/index.tsx` 第 216-220 行；`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/styles/global.css` 第 6108-6113 行
    - **问题**：镜像标签直接展示完整 Docker 镜像名，未限制最大宽度，长镜像名可能在窄屏下溢出卡片。
    - **修复建议**：为 `.admin-server-card__image` 添加 `max-width` 和 `text-overflow: ellipsis`，保留 Tooltip 展示完整镜像名。

30. **卡片内边距在移动端过大**
    - **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/AdminDeployments/index.tsx` 第 175-224 行；`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/styles/global.css` 第 6073-6078 行
    - **问题**：`.admin-server-card` 内边距固定为 `var(--space-5) var(--space-6)`（20px 32px），在移动端挤压内容可用空间。
    - **修复建议**：在 `@media (max-width: 767px)` 中将卡片内边距收紧为 `var(--space-4)` 或 `var(--space-3)`。

31. **日志容器选择器固定宽度 130px**
    - **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/AdminDeployments/index.tsx` 第 268-278 行；`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/styles/global.css` 第 6125-6127 行
    - **问题**：日志容器选择器固定宽度 130px，在极小屏下与其他控件同处一行时不够协调。
    - **修复建议**：将选择器宽度改为响应式，移动端当控件换行时设置为 `width: 100%`，桌面端保持 130px；或使用 `min-width` 替代固定宽度。

### ETLOpsDashboard

32. **刷新按钮点击热区仅文字大小**
    - **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/ETLOpsDashboard/index.tsx` 第 137 行
    - **问题**：PageHeader extra 的“刷新”是裸 `<a>` 文本，点击热区只有文字本身，高度约 14-20px，低于 44px 推荐触控目标。
    - **修复建议**：替换为 `<Button type="link" size="small">刷新</Button>` 或给链接增加 `padding: 12px 0` 以扩大热区。

33. **错误列未截断**
    - **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/ETLOpsDashboard/index.tsx` 第 121-127 行
    - **问题**：“错误”列直接输出完整错误字符串，未做截断或最大宽度限制。一旦报错信息较长，会显著拉大表格横向滚动距离。
    - **修复建议**：设置 `max-width` + `text-overflow: ellipsis`，并提供 `title` 或 Tooltip 查看完整内容。

34. **任务 ID 无宽度限制**
    - **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/ETLOpsDashboard/index.tsx` 第 71-75 行
    - **问题**：任务 ID（`row.name`）无宽度限制与截断，可能很长，导致“任务”列在小屏下成为表格最宽列。
    - **修复建议**：给 `.admin-task-label__id` 增加 `max-width: 160px` + 省略号，或允许换行。

### NotificationConfig

35. **Tabs 在 FilterToolbar 中可能被拉宽**
    - **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/NotificationConfig/index.tsx` 第 182-192 行
    - **问题**：`Tabs` 被放在 `FilterToolbar` 的 `filters` 槽中。全局移动端样式会让 `.filter-toolbar__filters > *` 强制 `flex: 1 1 auto; min-width: 140px`，可能把 Tabs 拉成不自然宽度；当计数较大或标签较长时，375px 下 Tabs 标签可能溢出或被截断。
    - **修复建议**：给 `Tabs` 外层加一个不触发 `flex:1` 的 wrapper，或改用 `type="line"` 的 `tabBarGutter` 控制，必要时在 375px 下使用更小字号。

36. **详情列 URL/邮箱未截断**
    - **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/NotificationConfig/index.tsx` 第 113-131 行
    - **问题**：“详情”列直接渲染 `webhook_url` 前 40 字符 + 平台标签，以及邮件地址 + 主题前缀。该列没有固定宽度，长 URL 或邮箱会让列宽不可控。
    - **修复建议**：给详情文本设置固定 `max-width`（如 200px/375px 下 120px）+ 省略号，Tooltip 显示完整内容。

37. **Modal 在 375px 下局促**
    - **文件**：`/Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform/web/src/pages/NotificationConfig/index.tsx` 第 210-215 行
    - **问题**：`Modal` 显式设置 `width={560}`，虽然全局 CSS 在小屏下会 clamp 到 `calc(100vw - 32px)`，但表单字段较多，在 375px 视口（内容区约 343px）中横向空间局促，且 `Input.TextArea` 与长 URL 输入框可读性受限。
    - **修复建议**：移动端改为 `Drawer` 或保留 Modal 但确保表单 `Input`/`Select` 宽度 100% + 可滚动；必要时为 375px 单独设置 `width: 360`。

---

## 跨页面观察与建议

1. **表格横向滚动均限制在容器内**：所有 Ant Design 表格都通过 `scroll={{ x: 'max-content' }}` 或 `phase5c-table-wrap` 的 `overflow-x: auto` 将横向滚动限制在表格内部，未产生页面级横向滚动，符合响应式基本要求。但表格内部滚动距离过长，仍显著影响移动端可用性。

2. **`size="small"` 按钮触控目标不足**：AdminUsers、AdminDeployments、NotificationConfig 等页面大量使用 `size="small"` 操作按钮（32px 高），低于 44px 推荐触控目标。建议建立移动端按钮规范：操作按钮在 768px 以下统一使用 `size="middle"` 或媒体查询强制 `min-height: 44px`。

3. **768px 断点覆盖不足**：Login、AppLayout 等多个页面的媒体查询使用 `max-width: 767px`，导致 768px 这个常见平板宽度仍走桌面紧凑布局。建议统一使用 `max-width: 768px` 或 `991px` 作为移动端/平板断点。

4. **Modal 宽度固定**：AdminUsers 和 NotificationConfig 的 Modal 使用固定宽度（480px/560px），虽然全局 CSS 有小屏兜底，但建议改为 Ant Design 响应式宽度对象或 Drawer，提升小屏可用性。

5. **文本截断策略缺失**：长用户名、SHA、URL、邮箱、错误信息、任务 ID 等均未做截断，是表格横向滚动过长的主要原因之一。建议为所有数据列建立统一的 `ellipsis` + Tooltip 截断策略。

---

## 修复优先级建议

| 优先级 | 问题类型 | 建议处理项 |
|--------|----------|------------|
| **立即** | P0 阻塞 | AppLayout 主内容区 margin-left 重置；Login 面板 content-box 溢出 |
| **高优** | P1 可用性 | AppLayout 触控目标、安全区、主题切换；Login 输入框缩放/滚动/断点；管理表格列宽/按钮堆叠/SHA 截断；ETLOps Descriptions 单列；NotificationConfig 表格列宽 |
| **后续** | P2 打磨 | 文本截断、Modal 响应式宽度、卡片内边距、focus 环、Dropdown 设置入口、免责声明字号等 |

---

*本次审计仅检查代码，未修改任何源文件。*
