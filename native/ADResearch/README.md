# AD Research 原生客户端（iOS + macOS）

全原生 SwiftUI 多平台单 target 应用，后端复用现有 `https://alloyresearch.net/api/v1`。

- **无 WebView、无 Catalyst、无跨平台框架**：Markdown 用 `AttributedString(markdown:)` 原生渲染
- **单 target 双平台**：iOS 17+ / macOS 14+，`SDKROOT=auto`，View 层按平台分文件或 `#if os(...)` 分支
- **Xcode 16 文件系统同步组**：`ADResearch/` 是 `PBXFileSystemSynchronizedRootGroup`，
  **往该目录任何子文件夹丢 `.swift` 文件即自动进工程，绝不手改 `project.pbxproj`**

## 打开方式

1. 安装 Xcode 16+，双击 `native/ADResearch/ADResearch.xcodeproj`
2. 选 `ADResearch` scheme，destination 选 iPhone 模拟器或 My Mac，⌘R
3. 首次签名：target → Signing & Capabilities 选自己的 Team（工程未绑定 Team）
4. 调试改后端地址：Scheme → Run → Environment Variables 加 `AD_API_BASE_URL`，
   或 `UserDefaults` 写 `api_base_url_override`（优先级：环境变量 > UserDefaults > 生产默认）

本地无 Xcode 时的验证口径（本仓库纪律）：每个 `.swift` 文件过
`swiftc -parse <file>`（macOS 分支）与 `swiftc -parse -target arm64-apple-ios17.0 <file>`（iOS 分支）。

## 架构

```
ADResearch/
├── App/                        应用壳与路由
│   ├── ADResearchApp.swift     @main；macOS 菜单栏命令（⌘1-5 导航）
│   ├── AppState.swift          AppSection（11 个分区）、AppRoute（路由）、FeatureRouter（唯一登记表）、AppState
│   ├── RootView.swift          启动态 → 已登录 Shell / 登录页
│   ├── PlatformShell_iOS.swift TabView 五 tab + 每 tab 独立 NavigationStack
│   └── PlatformShell_macOS.swift NavigationSplitView 侧栏两组 + toolbar ⌘R 刷新广播
├── Core/
│   ├── Networking/             APIClient(actor, 401→单飞refresh→重放) / APIError / Endpoints / JSONCoding / AppConstants
│   ├── Auth/                   AuthStore(@Observable) / KeychainHelper(AfterFirstUnlockThisDeviceOnly) / LoginView(双平台布局)
│   ├── Models/                 Auth/Digest/News/Macro 四组 Codable 模型（逐字段对齐 web ts 契约）
│   ├── Design/                 Theme(语义色/间距/圆角/字号/动画 token) + Components(共享组件库)
│   └── Utils/                  DateFormatting / NumberFormatting / MarkdownRenderer / Haptics
└── Features/
    ├── Dashboard/              实装：全球资产脉搏 + 每日研报摘要卡（iOS 卡片堆叠 / macOS 三栏）
    ├── Digest/                 实装：今日研报卡 + 历史列表 + 阅读页（原生 Markdown）
    ├── News/                   实装：双语资讯流（筛选/搜索）+ 详情（译文切换/抓取）
    ├── Macro/                  实装：四区快照 + 指数墙 + Swift Charts 历史详情
    ├── Instruments/            实装：标的列表（搜索/筛选）+ 详情（sparkline 区间切换）
    ├── Markets/                实装：行情总览（加密实时列表 + 二级模块入口）
    ├── Sectors/                实装：板块轮动（GICS/申万 + 相对强弱 + 动量）
    ├── Sentiment/              实装：情绪面板（多空总览 + 标的情绪 + 14 日走势）
    ├── Learning/               实装：学习中心（推荐/收藏 + 难度标签 + 左滑收藏）
    ├── Portfolio/              实装：自选 + 标的池（左滑移除，乐观更新）
    ├── Research/               实装：研究笔记（列表 + sheet 详情）
    └── Settings/               实装：账户信息 + 关于 + 登出
```

### 数据流约定

- 网络：`APIClient.shared.send(Endpoint, as: T.self)`，全部 async/await
- 认证：`AuthStore.shared`（@MainActor @Observable），token 在 Keychain；
  刷新成功的新令牌对由 APIClient 回调写回 Keychain（后端轮换 refresh_token）
- 状态：每个 Feature 一个 `@MainActor @Observable final class XxxViewModel`，
  View 里 `@State private var viewModel = XxxViewModel()`
- 时间：DTO 保留 String，`DateFormatting.parse/relative/formatDate` 解析
  （后端混用 YYYY-MM-DD 与 ISO8601 带/不带毫秒，不要加全局 dateDecodingStrategy）

## 契约核对清单（已逐字段核对，模型禁止凭猜）

| 端点 | Swift 模型 | 核对来源 |
|---|---|---|
| POST `/auth/login` | `LoginRequest` / `LoginResponse` / `UserProfile` | `web/src/api/auth.ts` |
| POST `/auth/refresh` | `RefreshRequest` / `RefreshResponse` | `web/src/api/auth.ts`（后端轮换 refresh_token） |
| POST `/auth/logout` | — | `web/src/api/auth.ts` |
| GET `/auth/me` | `UserProfile` | `web/src/api/auth.ts` |
| GET `/digest` | `DigestListResponse` / `DigestListItem` | `web/src/api/digest.ts` |
| GET `/digest/latest` | `DigestReport` / `DigestSection` | `web/src/api/digest.ts` |
| GET `/digest/latest/summary` | `DigestLatestSummary`（404=空态） | `web/src/api/digest.ts` + `components/DigestSummaryCard.tsx` |
| GET `/digest/by-date/{date}` | `DigestReport` | `web/src/api/digest.ts` |
| GET `/news` | `NewsListResponse` / `NewsArticle` / `NewsListParams`（event_category 重复查询参数） | `web/src/types/news.ts` + `web/src/api/news.ts` |
| GET `/news/{id}` | `NewsArticle` | `web/src/types/news.ts` |
| GET `/macro/latest?region=` | `MacroLatestResponse` / `MacroLatestItem` | `web/src/types/macro.ts` |
| GET `/macro/indices/global` | `GlobalIndicesRealtimeResponse` / `GlobalIndexRealtimeItem`（item code 与 macro 内部 code 一致，如 `global_sp500`） | `app/api/v1/macro.py` + `app/data/providers/yfinance_indices_provider.py` |

已知差异（有意为之）：
- web Dashboard 的 SPY.US/BTC.US/510300.SH/159915.SZ 四个 realtime tile 走 websocket
  行情流（`usePriceStream`），地基暂不含；脉搏分组只保留 macro 类 tile，行情流接入后补
- `UserProfile.role` 保留 `String`（ts 为 'admin'|'user'），防后端加角色时解码崩
- `NewsEngagement` 从 ts 索引签名收敛为 likes/comments/shares/views 四个可选字段

## 设计规范（全模块强制）

**标准：非常流畅、美观、现代、大方。**

### 流畅
- 所有状态切换/导航/卡片出现用 SwiftUI 原生动画：统一走 `AppTheme.Motion`
  （`.standard` 状态切换 / `.content` 卡片出现 / `.fade` 轻量淡入），禁止生硬无动画切换
- 适度用 `matchedGeometryEffect` 做卡片→详情连续过渡
- 列表滚动性能：`LazyVStack`/`LazyVGrid` + 缩略图异步加载（`AsyncImage` 带占位）
- iOS 列表页必须 `.refreshable`；轻量触觉反馈走 `Haptics.selection()`（仅 selection changed 场景）
- macOS 页面刷新监听 `Notification.Name.adRefreshRequested`（toolbar ⌘R 已广播，Dashboard 已示范）

### 美观
- SF Symbols 5：`.symbolRenderingMode(.hierarchical)` 为主，调色板模式适度
- material 背景：工具栏/卡片浮层用 `.regularMaterial`/`.thinMaterial`
- 圆角：卡片 14 / 控件 10 / chip 8，一律 `style: .continuous`
- 层级：浅色模式极浅投影（`Color.black.opacity(0.04)`, radius 8, y 2），
  深色模式用明度分层（background < elevated < surface）**不用投影**
- 颜色一律用 `AppTheme.Colors` 语义色（镜像 `web/src/styles/theme.css`，红涨绿跌中国习惯），
  禁止硬编码 Color.red/.green 表达涨跌

### 现代
- iOS 大标题导航；macOS 侧栏风格对齐 macOS 14+ 系统 App（股市/播客）
- 内容优先、留白充足（`AppTheme.Spacing` 4pt 网格，密度宁松勿挤）
- 卡片化信息组织：统一 `ADCard` + `ADCardHeader`
- 图表用 Swift Charts，配渐变面积与细腻网格线

### 大方
- 正文 `.body`/`.callout`（16-17pt 级），行长宽松，动态字号随系统
- 数值一律 `.monospacedDigit()`（`AppTheme.Typography.numeric*`），防跳动
- 空态用 `EmptyStateView`；加载态用骨架屏（`SkeletonBlock`/`.redacted`），**禁止裸 spinner**
- 涨跌幅文本统一 `ChangeText`（红涨绿跌 + 自动 +/- 号）

## 后续模块 agent 接入规则

### 加文件
往 `ADResearch/Features/<你的模块>/` 丢 `.swift` 文件即可，同步组自动进工程。
**绝不手改 `project.pbxproj`**。同名类型会撞 module 命名空间——文件名/类型名加模块前缀。

### 新端点
1. 先读 `web/src/api/<域>.ts` + `web/src/types/<域>.ts` 核对字段，禁止凭猜
2. 模型加到 `Core/Models/`（camelCase 属性，全局 snake_case 自动转换；
   时间字段保留 String）
3. `Core/Networking/Endpoints.swift` 追加静态方法（只加不改既有端点）

### 注册导航
- 新顶层分区：`AppState.swift` 的 `AppSection` 加 case（title/systemImage）→
  `FeatureRouter.rootView(for:)` 加分支。要进 iOS 主 tab 就改 `AppSection.primary`
- 新详情页：`AppRoute` 加 case → `FeatureRouter.destination(for:)` 加分支 →
  调用方 `appState.navigate(to:route:)` 或 `NavigationLink(value:)`
- 这是仅有的两个「登记点」，都在 `App/AppState.swift`，且只允许加 switch 分支

### 共享组件（禁止重造）
`ADCard` / `ADCardHeader` / `ChangeText` / `EmptyStateView` / `LoadErrorView` /
`SkeletonBlock`(`.shimmering()`) / `FeaturePlaceholderView` +
`AppTheme.Colors/Spacing/Radius/Typography/Motion` +
`DateFormatting` / `NumberFormatting` / `MarkdownRenderer` / `Haptics`

### 平台适配
- 共享 Model/网络/ViewModel；View 层 `#if os(iOS)` / `#if os(macOS)` 或平台分文件
  （文件名后缀 `_iOS` / `_macOS`，整文件包在 `#if os(...)` 里，参考 PlatformShell）
- iOS 地道交互：TabView/NavigationStack/sheet/swipeActions/refreshable
- macOS 地道交互：侧栏选中/toolbar/键盘快捷键/菜单命令/多窗口就绪
- 全部中文 UI 文案与注释

### 验收
提交前跑（本机无 Xcode 时的硬门槛）：
```bash
cd native/ADResearch
for f in $(find ADResearch -name "*.swift"); do swiftc -parse "$f" || exit 1; done
for f in $(find ADResearch -name "*.swift"); do swiftc -parse -target arm64-apple-ios17.0 "$f" || exit 1; done
```
两趟全过才算完。代码只用 iOS 17/macOS 14 内的稳定 API，不追新。

## 备注

- 仓库根目录的 `ios/ADResearch/` 是更早的一次未完工尝试（无 Xcode 工程、目录结构不同），
  与本工程无关，不联动；如确认废弃可另行删除
