# iOS 原生 APP 产品规划文档

> 2026-06-28 | 基于投研平台现有架构的完整规划
>
> 前置阅读：[iOS APP 可行性评估报告](./20260628-ios-app-feasibility-report.md)

## 目录

1. [总体决策](#一总体决策)
2. [技术选型](#二技术选型)
3. [Swift 工程结构](#三swift-工程结构)
4. [认证与安全](#四认证与安全)
5. [图表方案](#五图表方案)
6. [实时行情与离线缓存](#六实时行情与离线缓存)
7. [数据同步策略](#七数据同步策略)
8. [商业化与 App Store](#八商业化与-app-store)
9. [开发排期](#九开发排期)
10. [后端改造清单](#十后端改造清单)

---

## 一、总体决策

| 决策 | 结论 |
|---|---|
| 平台 | **iOS 原生**（Swift + SwiftUI/UIKit 混合） |
| 底座 | **复用现有 FastAPI 后端**，API 直接调用 |
| 开发模式 | **MVVM + Combine + async/await** |
| 图表 | **DGCharts（K线）+ Swift Charts（辅助）** — 免费 |
| 实时行情 | **SSE 推送** — 1-5秒刷新 |
| 本地数据库 | **GRDB** — SQL 友好、高性能 |
| 离线策略 | **本地优先展示 + 后台静默刷新** |
| 商业化 | **免费 + 内购订阅（Pro 版 ¥18-38/月）** |
| 首发市场 | **香港区或美国区 App Store** |

**决策依据：**
- 团队前端是 React，但 K线/金融体验原生 Swift 最优
- 预算不包含额外库授权费 → DGCharts（Apache 2.0 免费）
- 散户级用户 → 1-5秒刷新足够，不需要 tick 级实时
- 不提供具体投资建议 → 产品定位为"数据分析工具"

---

## 二、技术选型

| 层级 | 推荐方案 | 备选 | 选型理由 |
|---|---|---|---|
| **UI 框架** | SwiftUI 主体 + UIKitRepresentable 包裹图表 | 纯 UIKit | 新页面 SwiftUI 开发快；图表用 UIKit 性能更好 |
| **架构模式** | MVVM + Combine | MVVM + async/await | Combine 适合响应式数据流 |
| **网络层** | Alamofire + Codable | 原生 URLSession | 拦截器成熟，上传下载方便 |
| **本地缓存** | GRDB | SwiftData / Core Data | 金融查询复杂，SQL 更直接 |
| **认证存储** | Keychain | — | JWT 必须安全存储 |
| **K线图表** | DGCharts | TradingView（付费） | 免费、开源、散户级够用 |
| **辅助图表** | Swift Charts | DGCharts | 系统原生，收益曲线/饼图 |
| **图片加载** | Kingfisher | SDWebImage | 列表缩略图缓存 |
| **推送** | APNs 原生 | — | 系统级推送 |
| **路由** | NavigationStack | UIKit Coordinator | iOS 16+ 标准方案 |

---

## 三、Swift 工程结构

### 3.1 项目目录

```
ADResearch/
├── App/
│   ├── ADResearchApp.swift          # @main 入口
│   ├── AppDelegate.swift            # APNs / Background Fetch
│   ├── SceneDelegate.swift          # 多窗口（iPad 可选）
│   └── Info.plist                   # 权限声明
├── Models/
│   ├── Domain/                      # 业务模型（纯 struct）
│   │   ├── Instrument.swift
│   │   ├── Candle.swift
│   │   ├── Pool.swift
│   │   ├── Score.swift
│   │   ├── Signal.swift
│   │   └── User.swift
│   ├── DTO/                         # API 传输对象（Codable）
│   │   ├── AuthDTO.swift
│   │   ├── ETFListDTO.swift
│   │   └── ...（按模块分拆）
│   └── Local/                       # GRDB 持久化模型（Record）
│       ├── InstrumentRecord.swift
│       ├── CandleRecord.swift
│       └── ...
├── Services/
│   ├── Network/
│   │   ├── APIClient.swift          # Alamofire 配置 + 拦截器
│   │   ├── AuthInterceptor.swift    # Token 自动注入 / 401 处理
│   │   └── APIError.swift           # 统一错误模型
│   ├── API/                         # 按后端 api/*.ts 一对一翻译
│   │   ├── AuthService.swift
│   │   ├── ETFService.swift
│   │   ├── PoolService.swift
│   │   ├── MarketDataService.swift
│   │   ├── ScoreService.swift
│   │   ├── ScreenService.swift
│   │   ├── BacktestService.swift
│   │   ├── SignalService.swift
│   │   ├── StrategyService.swift
│   │   ├── NotificationService.swift
│   │   ├── FavoriteService.swift
│   │   ├── ReportService.swift
│   │   ├── AnalysisService.swift
│   │   ├── ScannerService.swift
│   │   ├── ResearchService.swift
│   │   ├── ChatService.swift
│   │   └── AdminService.swift
│   ├── Local/                       # 本地数据库
│   │   ├── LocalStore.swift         # GRDB 初始化 + 迁移
│   │   ├── InstrumentRepository.swift
│   │   ├── CandleRepository.swift
│   │   ├── FavoriteRepository.swift
│   │   └── ...
│   ├── Stream/                      # 实时行情
│   │   ├── PriceStream.swift        # SSE 客户端
│   │   └── SubscriptionManager.swift
│   ├── Sync/                        # 数据同步
│   │   ├── SyncManager.swift
│   │   ├── ConflictResolver.swift
│   │   └── BackgroundSyncService.swift
│   ├── Auth/
│   │   ├── AuthManager.swift        # 登录/登出/refresh
│   │   └── KeychainStore.swift
│   └── Push/
│       └── PushManager.swift        # APNs 注册/接收
├── ViewModels/                      # MVVM ViewModel
│   ├── Auth/
│   ├── Dashboard/
│   ├── Instruments/
│   ├── InstrumentDetail/
│   ├── Pools/
│   ├── AI/
│   └── Settings/
├── Views/                           # SwiftUI View
│   ├── Common/                      # 通用组件
│   │   ├── KLineChartView.swift     # DGCharts UIKitRepresentable
│   │   ├── SimpleChartView.swift    # Swift Charts 封装
│   │   ├── OfflineBanner.swift
│   │   ├── LoadingView.swift
│   │   └── ErrorView.swift
│   ├── Tab/                         # TabBar 主结构
│   │   └── MainTabView.swift
│   ├── Dashboard/
│   ├── Instruments/
│   ├── InstrumentDetail/
│   ├── Pools/
│   ├── AI/
│   └── Settings/
├── Theme/
│   ├── Theme.swift                  # 色彩/字体常量（与 Web theme.css 对齐）
│   └── ChartTheme.swift            # 图表配色常量
├── Utilities/
│   ├── Formatters.swift             # 数字/日期格式化
│   ├── Extensions.swift             # Swift 扩展
│   └── Constants.swift              # API URL / 超时配置
└── Resources/
    ├── Assets.xcassets/             # 图标/图片
    └── Localizable.xcstrings        # 多语言
```

### 3.2 设计模式

- **Service 层**：调用 API，返回 `Result<DTO, APIError>`
- **Repository 层**：封装 GRDB CRUD，返回领域模型
- **ViewModel 层**：组合 Service + Repository，暴露 `@Published` 状态
- **View 层**：纯 SwiftUI，通过 `@StateObject` / `@ObservedObject` 绑定 ViewModel

```swift
// ViewModel 典型结构
@MainActor
final class InstrumentListViewModel: ObservableObject {
    @Published var state: LoadingState<[Instrument]> = .idle
    @Published var searchText = ""
    @Published var selectedMarket: String?
    
    private let service = ETFService.shared
    private let repo = InstrumentRepository.shared
    
    func load() async {
        // 1. 先展示本地
        let cached = try? await repo.all()
        if let cached { state = .loaded(cached) }
        
        // 2. 后台刷新
        do {
            let dtos = try await service.fetchList()
            let list = dtos.map { $0.toDomain() }
            try await repo.saveAll(list)
            state = .loaded(list)
        } catch {
            if cached != nil { return } // 有缓存不报错
            state = .error(error)
        }
    }
}
```

---

## 四、认证与安全

### 4.1 当前认证（需改造）

```
POST /api/v1/auth/login → JWT (1天过期)
GET  /api/v1/auth/me    → 用户信息
Authorization: Bearer <token>
```

**缺失：** Refresh Token、登出、设备管理

### 4.2 改造后认证（推荐）

```
POST /api/v1/auth/login       → access_token (短期) + refresh_token (长期)
POST /api/v1/auth/refresh     → 新 access_token
POST /api/v1/auth/logout      → 置失效 token
POST /api/v1/auth/device      → 注册设备
GET  /api/v1/auth/devices     → 查看已登录设备
DELETE /api/v1/auth/devices/:id → 踢掉设备
```

**Token 设计：**

| Token | 有效期 | 存储位置 |
|---|---|---|
| access_token | 15 分钟 | 内存 |
| refresh_token | 30 天 | Keychain |

### 4.3 iOS 端认证流

```swift
final class AuthManager: ObservableObject {
    @Published var isAuthenticated = false
    @Published var currentUser: User?
    
    private let keychain = KeychainStore.shared
    private let service = AuthService.shared
    
    // 启动时检查
    func restoreSession() async {
        if let refreshToken = keychain.refreshToken {
            do {
                let result = try await service.refresh(refreshToken)
                keychain.save(accessToken: result.accessToken, refreshToken: result.refreshToken)
                currentUser = result.user
                isAuthenticated = true
            } catch {
                keychain.clear()
                isAuthenticated = false
            }
        }
    }
    
    // 登录
    func login(username: String, password: String) async throws {
        let result = try await service.login(username: username, password: password)
        keychain.save(accessToken: result.accessToken, refreshToken: result.refreshToken)
        currentUser = result.user
        isAuthenticated = true
        
        // 注册设备
        try? await service.registerDevice(deviceToken: await getDeviceToken())
    }
    
    // 自动刷新
    func ensureValidToken() async throws -> String {
        guard let accessToken = keychain.accessToken else {
            throw AuthError.notAuthenticated
        }
        
        if JWTDecoder.willExpireSoon(accessToken) {
            guard let refreshToken = keychain.refreshToken else {
                throw AuthError.notAuthenticated
            }
            let result = try await service.refresh(refreshToken)
            keychain.save(accessToken: result.accessToken, refreshToken: result.refreshToken)
            return result.accessToken
        }
        
        return accessToken
    }
    
    // 登出
    func logout() async {
        _ = try? await service.logout()
        keychain.clear()
        currentUser = nil
        isAuthenticated = false
    }
}
```

### 4.4 API 拦截器自动注入 Token

```swift
final class AuthInterceptor: RequestInterceptor {
    func adapt(_ urlRequest: URLRequest, completion: @escaping (Result<URLRequest, Error>) -> Void) {
        var request = urlRequest
        Task {
            if let token = try? await AuthManager.shared.ensureValidToken() {
                request.addValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            }
            completion(.success(request))
        }
    }
    
    func retry(_ request: Request, dueTo error: Error, completion: @escaping (RetryResult) -> Void) {
        if let afError = error.asAFError, afError.responseCode == 401 {
            Task {
                // 尝试刷新 token 后重试
                if let _ = try? await AuthManager.shared.ensureValidToken() {
                    completion(.retry)
                } else {
                    await AuthManager.shared.logout()
                    completion(.doNotRetry)
                }
            }
        } else {
            completion(.doNotRetry)
        }
    }
}
```

### 4.5 Keychain 封装

```swift
final class KeychainStore {
    static let shared = KeychainStore()
    
    var accessToken: String? { get { get("access_token") } set { set("access_token", value: newValue) } }
    var refreshToken: String? { get { get("refresh_token") } set { set("refresh_token", value: newValue) } }
    
    func clear() {
        accessToken = nil
        refreshToken = nil
    }
    
    private func get(_ key: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var result: AnyObject?
        SecItemCopyMatching(query as CFDictionary, &result)
        guard let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
    
    private func set(_ key: String, value: String?) {
        guard let value, let data = value.data(using: .utf8) else {
            SecItemDelete([kSecClass: kSecClassGenericPassword, kSecAttrAccount: key] as CFDictionary)
            return
        }
        SecItemDelete([kSecClass: kSecClassGenericPassword, kSecAttrAccount: key] as CFDictionary)
        SecItemAdd([
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        ] as CFDictionary, nil)
    }
}
```

---

## 五、图表方案

### 5.1 选型结论

| 图表类型 | 库 | 原因 |
|---|---|---|
| **K线主图** | **DGCharts**（原 ios-charts） | 免费开源、Apache 2.0、散户级够用 |
| **收益曲线** | Swift Charts | 系统原生、声明式、与 SwiftUI 配合好 |
| **分类饼图** | Swift Charts | 简单、原生 |
| **相关性热力图** | DGCharts 或自研 Canvas | Swift Charts 无热力图 |
| **评分雷达图** | DGCharts | 原生支持 RadarChart |

**为什么不选 TradingView iOS：** 需要商业授权付费，预算不允许。DGCharts GitHub 27k+ stars，社区成熟。

### 5.2 K线图表关键配置

```swift
struct KLineChartView: UIViewRepresentable {
    let candles: [Candle]
    @Binding var crosshairDate: Date?
    
    func makeUIView(context: Context) -> CandleChartView {
        let view = CandleChartView()
        view.delegate = context.coordinator
        
        // 主题
        view.backgroundColor = UIColor(hex: "#0a0a0a")
        view.gridBackgroundColor = .clear
        view.borderColor = UIColor(hex: "#1f1f1f")
        
        // A股红涨绿跌
        view.candleData?.increasingColor = UIColor(hex: "#ef4444")
        view.candleData?.decreasingColor = UIColor(hex: "#22c55e")
        view.candleData?.shadowColorSameAsCandle = true
        
        // 手势
        view.pinchZoomEnabled = true
        view.doubleTapToZoomEnabled = true
        view.dragEnabled = true
        
        // 时间周期选择器
        view.timeframes = [.day, .week, .month]
        
        return view
    }
    
    func updateUIView(_ uiView: CandleChartView, context: Context) {
        let dataSet = candles.toCandleChartDataSet()
        uiView.data = CombinedChartData.combinedData(from: dataSet)
        uiView.notifyDataSetChanged()
    }
}
```

### 5.3 DGCharts 性能调优

| 场景 | 优化 |
|---|---|
| 日线 > 1000 根 | 页面加载限制 252 根（1年），按需加载更早数据 |
| 缩小时 | 合并数据点（OHLC 聚合） |
| 滑动时 | 只绘制可见区域 |
| 多指标叠加 | 主图最多 3 条 MA，副图最多 2 个指标 |

### 5.4 辅助图表（Swift Charts）

收益曲线示例：

```swift
struct ReturnCurveChart: View {
    let series: [ReturnSeries]
    
    var body: some View {
        Chart {
            ForEach(series) { s in
                ForEach(s.dataPoints) { point in
                    LineMark(
                        x: .value("日期", point.date),
                        y: .value("收益", point.value)
                    )
                    .foregroundStyle(by: .value("标的", s.name))
                }
            }
        }
        .chartForegroundStyleScale([
            "标的A": Color(hex: "#22d3ee"),
            "标的B": Color(hex: "#555555")
        ])
        .chartXAxis { AxisMarks(values: .automatic(desiredCount: 6)) }
    }
}
```

---

## 六、实时行情与离线缓存

### 6.1 架构概览

```
┌──────────────┐    SSE（实时价格）     ┌──────────────┐
│   iOS App    │ ◄──────────────────►   │   FastAPI    │
│              │    REST（历史K线）       │   Backend    │
│ ┌──────────┐ │                        │              │
│ │  GRDB    │ │◄── 后台定时同步 ──────► │  ┌─────────┐ │
│ │ (本地DB) │ │                        │  │ Market   │ │
│ └────┬─────┘ │                        │  │ Service  │ │
│      │ read  │                        │  └─────────┘ │
│ ┌────┴─────┐ │                        │              │
│ │ SwiftUI  │ │                        │  ┌─────────┐ │
│ │   View   │ │                        │  │ SSE      │ │
│ └──────────┘ │                        │  │ Stream   │ │
└──────────────┘                        └──────────────┘
```

### 6.2 数据分层

| 数据类型 | 存储位置 | 更新频率 | 离线可用 |
|---|---|---|---|
| 历史 K线（日/周/月） | GRDB | 每天 1 次 | ✅ |
| 当日分时 | GRDB + 内存 | 交易时段 1-5s | ⚠️ 有限 |
| 最新快照 | 内存 | 交易时段 1-5s | ❌ |
| 标的元数据 | GRDB | 每天 1 次 | ✅ |
| 用户收藏 | GRDB | 即时 | ✅ |
| 标的池 | GRDB | 即时 | ✅ |
| 评分/指标 | GRDB | 每天 1 次 | ✅ |
| AI 研究笔记 | GRDB | 打开时刷新 | ✅ |
| 聊天消息 | GRDB | 实时 | ✅ |

### 6.3 GRDB 表结构

```sql
CREATE TABLE instruments (
    code TEXT PRIMARY KEY,
    market TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT,
    instrumentType TEXT,
    fundManager TEXT,
    underlyingIndex TEXT,
    fundSize REAL,
    marketCap REAL,
    updatedAt INTEGER NOT NULL,
    syncStatus INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE candles (
    code TEXT NOT NULL,
    market TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    PRIMARY KEY (code, market, timeframe, timestamp)
) WITHOUT ROWID;

CREATE TABLE snapshots (
    code TEXT PRIMARY KEY,
    market TEXT NOT NULL,
    price REAL NOT NULL,
    changePct REAL NOT NULL,
    volume REAL NOT NULL,
    updatedAt INTEGER NOT NULL
);

CREATE TABLE favorites (
    code TEXT PRIMARY KEY,
    createdAt INTEGER NOT NULL,
    syncStatus INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE pools (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    memberCount INTEGER NOT NULL,
    updatedAt INTEGER NOT NULL,
    syncStatus INTEGER NOT NULL DEFAULT 0
);
```

### 6.4 SSE 实时推送

```
GET /api/v1/stream/prices?codes=510300,159915,510050
Content-Type: text/event-stream

data: {"type":"price_update","code":"510300","price":3.845,"change_pct":0.32,"volume":123456789,"timestamp":1762054200000}
data: {"type":"price_update","code":"159915","price":4.210,"change_pct":-0.15,"volume":98765432,"timestamp":1762054201000}
```

iOS 端：

```swift
final class PriceStream {
    static let shared = PriceStream()
    private var urlSession: URLSession?
    
    func connect(codes: [String]) {
        let url = URL(string: "\(Constants.apiBaseURL)/stream/prices?codes=\(codes.joined(separator: ","))")!
        var request = URLRequest(url: url)
        request.setValue("Bearer \(keychain.accessToken ?? "")", forHTTPHeaderField: "Authorization")
        
        // SSE 自动处理重连
        urlSession = URLSession(configuration: .default, delegate: SSEDelegate(), delegateQueue: .main)
        urlSession?.dataTask(with: request).resume()
    }
    
    // 逐行解析 SSE
    func onEvent(_ data: Data) {
        guard let snapshot = try? JSONDecoder().decode(SnapshotDTO.self, from: data) else { return }
        Task {
            await PriceStore.shared.update(snapshot.toDomain())
        }
    }
}
```

---

## 七、数据同步策略

### 7.1 核心原则

1. **本地优先展示** — 打开 App 永远有数据看
2. **后台静默刷新** — 不阻塞用户操作
3. **乐观更新** — 收藏/编辑等操作立即反馈
4. **自动重试** — 网络恢复后自动同步 pending
5. **冲突用时间戳解决** — 简单可靠
6. **定期清理** — 防止数据库无限膨胀

### 7.2 同步状态

```swift
enum SyncStatus: Int {
    case synced = 0      // 已同步
    case pending = 1     // 本地修改，待推送
    case conflict = 2    // 同步冲突
}
```

### 7.3 收藏同步示例

```swift
func toggleFavorite(code: String) async throws {
    // 1. 乐观更新本地
    let isFav = try repo.isFavorite(code: code)
    if isFav {
        try repo.delete(code: code)
    } else {
        try repo.save(code: code, status: .pending)
    }
    
    // 2. 通知 UI 立刻更新
    await MainActor.run {
        NotificationCenter.default.post(name: .favoritesDidChange, object: nil)
    }
    
    // 3. 后台推送到服务器
    Task.detached(priority: .background) {
        do {
            if isFav {
                try await FavoriteService.shared.remove(code: code)
            } else {
                try await FavoriteService.shared.add(code: code)
            }
            try repo.markSynced(code: code)
        } catch {
            // 失败保持 pending，SyncManager 自动重试
        }
    }
}
```

### 7.4 冲突解决

- **收藏/关注：** 以服务器为准，服务器是 Single Source of Truth
- **池子权重：** 比较 `updatedAt`，最后修改时间胜出

### 7.5 后台刷新（iOS Background Fetch）

```swift
// AppDelegate
func application(_ application: UIApplication, performFetchWithCompletionHandler completionHandler: @escaping (UIBackgroundFetchResult) -> Void) {
    Task {
        do {
            try await SyncManager.shared.backgroundSync()
            completionHandler(.newData)
        } catch {
            completionHandler(.failed)
        }
    }
}
```

### 7.6 锁屏组件（Widget）

```swift
// 自选标的桌面 Widget
struct WatchlistWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "Watchlist", provider: WatchlistProvider()) { entry in
            WatchlistView(entry: entry)
        }
        .configurationDisplayName("自选标的")
        .description("快速查看关注标的最新价格")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge])
    }
}
```

---

## 八、商业化与 App Store

### 8.1 商业模式

| 等级 | 价格 | 功能 |
|---|---|---|
| **免费版** | ¥0 | 查看基础行情、标的列表、3条评分 |
| **Pro 版** | ¥18-38/月 或 ¥198-398/年 | 全部评分、高级筛选、回测、AI 笔记、无广告 |
| **机构版** | 联系销售 | API 接入、自定义策略、白标 |

### 8.2 StoreKit 2 实现

```swift
@MainActor
class StoreManager: ObservableObject {
    @Published var products: [Product] = []
    @Published var isSubscribed = false
    
    init() { Task { await listenForTransactions() } }
    
    func loadProducts() async {
        products = try? await Product.products(for: [
            "com.adresearch.pro.monthly",
            "com.adresearch.pro.yearly"
        ])
    }
    
    func purchase(_ product: Product) async throws {
        let result = try await product.purchase()
        if case .success(let verification) = result {
            let transaction = try verification.payloadValue
            // 传给后端验证
            try await AuthService.shared.verifyPurchase(transactionID: String(transaction.id))
            isSubscribed = true
            await transaction.finish()
        }
    }
}
```

### 8.3 App Store 审核关键

| 风险点 | 规避方法 |
|---|---|
| **提供投资建议** | 产品定位"数据分析工具"，所有页面标注"仅供参考，不构成投资建议" |
| **AI 生成内容** | 标注"AI 生成，需人工复核，不构成投资建议" |
| **诱导付费** | 不承诺收益率 |
| **数据合规** | 提供隐私政策 URL、账号注销功能 |

### 8.4 需要准备的材料

- [ ] 隐私政策（Privacy Policy）URL
- [ ] 用户协议（Terms of Service）URL
- [ ] 免责声明文案
- [ ] App 截图（6 张）
- [ ] 审核说明（测试账号、功能说明）
- [ ] App 备案（中国区）
- [ ] ICP 备案（如在中国大陆）

### 8.5 上线路径

```
阶段 1：TestFlight 内测（1-3 个月）
  → 收集反馈、修复 bug、验证留存

阶段 2：App Store 香港/美国区上架（3-6 个月）
  → 免费下载、积累用户、验证付费意愿

阶段 3：增加内购订阅（6-12 个月）
  → StoreKit 2 集成、后端验证

阶段 4：中国大陆区上架（视备案进展）
  → 需要 App 备案 + 金融信息服务资质准备
```

---

## 九、开发排期

### MVP 范围（8 周）

**四个 Tab：首页 / 标的 / 池子 / 我的**

| 周次 | 目标 | 产出 |
|---|---|---|
| **W1** | 工程搭建 + 网络层 | Xcode 项目、Alamofire 配置、AuthInterceptor、Keychain |
| **W2** | 登录 + 首页 Dashboard | 登录页、统计卡片、评分 Top10 列表 |
| **W3** | 标的列表 + 筛选器 | 搜索、市场/分类/类型筛选、本地缓存 |
| **W4** | 标的详情 + K线 | DGCharts 集成、K线图、关键指标卡片 |
| **W5** | 池子列表 + 详情 | 池子成员、权重展示、收益分析 |
| **W6** | AI 研究笔记 + 收藏 | Research 页面、收藏 toggle、收藏列表 |
| **W7** | 推送 + 我的页面 | APNs 集成、设备注册、设置页、关于页 |
| **W8** | 测试 + 性能优化 | 离线体验、UI 打磨、TestFlight 上架准备 |

### 砍掉的功能（第二阶段）

- 全市场筛选器（表单复杂，移动端场景待验证）
- 回测创建/管理（参数多，输入体验差）
- 策略管理（偏后台配置）
- 相关性分析（需要大屏热力图）
- 板块轮动（可后续卡片形式简化）
- 管理员功能（APP 面向用户，非管理员）

---

## 十、后端改造清单

### 10.1 MVP 必须做（blocker）

| 优先级 | 改造项 | 工作量 | 说明 |
|---|---|---|---|
| P0 | **Refresh Token + 刷新端点** | 3-5 天 | `POST /auth/refresh`；`/auth/login` 返回 refresh_token |
| P0 | **Token 黑名单（登出用）** | 1-2 天 | Redis 存储失效 token |
| P0 | **设备绑定表 + API** | 2-3 天 | 多端登录管理 |
| P1 | **SSE 价格流端点** | 5-7 天 | `GET /stream/prices?codes=...` |
| P1 | **批量快照接口** | 1-2 天 | `GET /market-data/snapshots?codes=...` |
| P1 | **API 分页统一** | 2-3 天 | `page`/`page_size` 标准化 |
| P2 | **APNs 推送集成** | 3-5 天 | 价格预警、信号通知、报告生成通知 |

### 10.2 建议做（体验提升）

| 改造项 | 工作量 | 说明 |
|---|---|---|
| **增量接口** | 2-3 天 | `GET /etfs?since=...` 用 `updated_at` 过滤 |
| **ETag 支持** | 1-2 天 | 避免重复传输全量数据 |
| **PDF 报告导出** | 2-3 天 | WeasyPrint 或用 Playwright 截图 |
| **订阅验证 API** | 1-2 天 | Apple App Store Server API 对接 |

---

## 附录 A：与 Web 端的功能对照

| 功能 | Web 实现 | iOS 实现 |
|---|---|---|
| K线图 | `lightweight-charts` | DGCharts |
| 收益曲线 | ECharts | Swift Charts |
| 饼图 | ECharts | Swift Charts |
| 热力图 | ECharts | DGCharts / 自研 |
| 雷达图 | ECharts | DGCharts |
| 表格 | Ant Design `Table` | SwiftUI `List` |
| 表单 | Ant Design `Form` | SwiftUI `Form` |
| 导航 | `react-router-dom` | `NavigationStack` |
| 状态管理 | zustand | `@Observable` / `@Published` |
| 数据获取 | React Query | async/await |
| Token 存储 | localStorage | Keychain |
| 推送 | Webhook / SMTP | APNs |

## 附录 B：Web 端 API 到 iOS Service 映射

| Web API 文件 | iOS Service 文件 | 主要端点 |
|---|---|---|
| `web/src/api/auth.ts` | `Services/API/AuthService.swift` | login, me, refresh, logout, device |
| `web/src/api/etf.ts` | `Services/API/ETFService.swift` | list, detail, categories, markets |
| `web/src/api/market.ts` | `Services/API/MarketDataService.swift` | history, snapshot, intraday |
| `web/src/api/pool.ts` | `Services/API/PoolService.swift` | CRUD, members, weights, snapshots |
| `web/src/api/score.ts` | `Services/API/ScoreService.swift` | scores, detail, templates |
| `web/src/api/screen.ts` | `Services/API/ScreenService.swift` | screen, presets, categories |
| `web/src/api/favorite.ts` | `Services/API/FavoriteService.swift` | list, toggle |
| `web/src/api/research.ts` | `Services/API/ResearchService.swift` | notes, sentiment |
| `web/src/api/chat.ts` | `Services/API/ChatService.swift` | sessions, messages |
| `web/src/api/backtest.ts` | `Services/API/BacktestService.swift` | list, detail, create |
| `web/src/api/signal.ts` | `Services/API/SignalService.swift` | list, latest, generate |
| `web/src/api/notification.ts` | `Services/API/NotificationService.swift` | configs CRUD, logs |
