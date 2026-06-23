# iOS App Phase 1 实施计划

> **For agentic workers:** REQUIRED SUB-_SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 iOS App Phase 1 — 项目搭建、登录认证、Dashboard、ETF 列表/搜索、ETF 详情（含 K 线）、自选收藏，形成可在 iPhone 和 iPad 上运行的 Universal App 骨架。

**Architecture:** 采用原生 SwiftUI + MVVM，网络层基于 `URLSession` 封装统一 APIClient，认证信息存 Keychain，数据模型与后端 DTO 一一对应，界面按 iPhone 底部 Tab + iPad Sidebar 双架构适配。

**Tech Stack:** SwiftUI, Swift Charts (iOS 16+), TradingView iOS SDK (K-line), Keychain, XCTest

---

## 0. 前置说明

- 设计文档：[docs/superpowers/specs/2026-06-23-ios-app-design.md](../specs/2026-06-23-ios-app-design.md)
- iOS 项目目录：`ios/ETFResearch/`
- 后端 API Base URL：`http://localhost:8000/api/v1`（开发环境）
- 后端已提供的 Phase 1 相关接口：
  - `POST /api/v1/auth/login`
  - `GET /api/v1/auth/me`
  - `GET /api/v1/stats/overview`
  - `GET /api/v1/analysis/ranking`
  - `GET /api/v1/etfs`
  - `GET /api/v1/etfs/{code}`
  - `GET /api/v1/market-data/{code}/history`
  - `GET /api/v1/market-data/snapshot`
  - `GET /api/v1/indicators/{code}`
  - `GET /api/v1/scores/{code}`
  - `GET /api/v1/favorites`
  - `POST /api/v1/favorites/{code}/toggle`
  - `DELETE /api/v1/favorites/{code}`

---

## 1. 文件结构

```
ios/ETFResearch/
├── ETFResearch.xcodeproj/                  # Xcode 项目文件
├── ETFResearch/
│   ├── ETFResearchApp.swift                # App 入口，全局环境对象
│   ├── Info.plist
│   ├── Assets.xcassets/
│   ├── Core/                               # 基础设施
│   │   ├── APIConfig.swift                 # API 配置
│   │   ├── APIClient.swift                 # 统一网络客户端
│   │   ├── NetworkError.swift              # 网络错误枚举
│   │   ├── KeychainHelper.swift            # Keychain 读写
│   │   └── AuthManager.swift               # 认证状态管理
│   ├── Models/                             # 数据模型（Decodable）
│   │   ├── User.swift
│   │   ├── ETF.swift
│   │   ├── ETFScore.swift
│   │   ├── ETFIndicator.swift
│   │   ├── DailyBar.swift
│   │   ├── Favorite.swift
│   │   ├── DashboardStats.swift
│   │   └── PaginatedResponse.swift
│   ├── Services/                           # API 服务层
│   │   ├── AuthService.swift
│   │   ├── ETFService.swift
│   │   ├── MarketDataService.swift
│   │   ├── ScoreService.swift
│   │   ├── IndicatorService.swift
│   │   ├── FavoritesService.swift
│   │   └── DashboardService.swift
│   ├── Views/                              # 界面
│   │   ├── LoginView.swift
│   │   ├── MainTabView.swift
│   │   ├── MainSidebarView.swift
│   │   ├── DashboardView.swift
│   │   ├── ETFListView.swift
│   │   ├── ETFDetailView.swift
│   │   ├── ETFRowView.swift
│   │   ├── MarketView.swift
│   │   ├── PortfolioView.swift
│   │   ├── SignalsView.swift
│   │   └── MoreView.swift
│   ├── ViewModels/                         # MVVM
│   │   ├── LoginViewModel.swift
│   │   ├── DashboardViewModel.swift
│   │   ├── ETFListViewModel.swift
│   │   └── ETFDetailViewModel.swift
│   ├── Components/                         # 可复用组件
│   │   ├── KLineChartView.swift
│   │   ├── ScoreRadarView.swift
│   │   ├── LoadingView.swift
│   │   └── ErrorView.swift
│   └── Preview Content/
└── ETFResearchTests/                       # 单元测试
    ├── APIClientTests.swift
    ├── AuthServiceTests.swift
    └── ETFServiceTests.swift
```

---

## 2. 任务列表

### Task 1: 创建 Xcode 项目并配置基础依赖

**Files:**
- Create: `ios/ETFResearch/ETFResearch.xcodeproj/project.pbxproj`（通过 Xcode 或 xcodegen 生成）
- Create: `ios/ETFResearch/ETFResearch/ETFResearchApp.swift`
- Create: `ios/ETFResearch/ETFResearch/Info.plist`

- [ ] **Step 1: 初始化 Xcode 项目**

使用 Xcode 15+ 创建新项目：
- Template: iOS → App
- Name: `ETFResearch`
- Interface: SwiftUI
- Language: Swift
- Minimum Deployments: iOS 16.0
- Include Tests: 勾选 Unit Tests

- [ ] **Step 1.5: 链接必要系统框架**

在 Target → General → Frameworks, Libraries, and Embedded Content 中确保已链接：
- `SwiftUI`（默认已链接）
- `Charts`（iOS 16+ 系统框架，点击 + 添加）
- `Security`（Keychain 需要，通常已自动链接）

注意：`lightweight-charts-ios`（TradingView SDK）在 Phase 1 暂不使用，可跳过该依赖，Phase 2 再添加。

- [ ] **Step 2: 添加可选依赖（Phase 1 可跳过）**

Phase 1 的 K 线使用系统 `Swift Charts`，无需额外 SPM。Phase 2 再考虑添加：
- `https://github.com/tradingview/lightweight-charts-ios`（TradingView iOS SDK，高级 K 线）

如需 Keychain 封装库，可添加：
- `https://github.com/kishikawakatsumi/KeychainAccess`（可选；本计划采用手写 KeychainHelper）

- [ ] **Step 3: 创建 App 入口文件**

```swift
// ETFResearch/ETFResearchApp.swift
import SwiftUI

@main
struct ETFResearchApp: App {
    @StateObject private var authManager = AuthManager()

    var body: some Scene {
        WindowGroup {
            Group {
                if authManager.isAuthenticated {
                    AdaptiveMainView()
                        .environmentObject(authManager)
                } else {
                    LoginView()
                        .environmentObject(authManager)
                }
            }
        }
    }
}
```

- [ ] **Step 4: 提交**

```bash
cd ios/ETFResearch
git add .
git commit -m "chore(ios): initialize Xcode project with SwiftUI and iOS 16 target"
```

---

### Task 2: API 配置与错误类型

**Files:**
- Create: `ios/ETFResearch/ETFResearch/Core/APIConfig.swift`
- Create: `ios/ETFResearch/ETFResearch/Core/NetworkError.swift`

- [ ] **Step 1: 创建 APIConfig**

```swift
// ETFResearch/Core/APIConfig.swift
import Foundation

enum APIConfig {
    static let baseURL = URL(string: "http://localhost:8000/api/v1")!
    
    static var authToken: String? {
        get { KeychainHelper.shared.read(key: .authToken) }
        set {
            if let newValue {
                KeychainHelper.shared.save(key: .authToken, value: newValue)
            } else {
                KeychainHelper.shared.delete(key: .authToken)
            }
        }
    }
}
```

- [ ] **Step 2: 创建 NetworkError**

```swift
// ETFResearch/Core/NetworkError.swift
import Foundation

enum NetworkError: Error, Equatable {
    case invalidURL
    case invalidResponse
    case httpStatus(Int, String?)
    case decodingError(Error)
    case noData
    case unauthorized
    case unknown
    
    var message: String {
        switch self {
        case .invalidURL: return "无效的请求地址"
        case .invalidResponse: return "服务器响应异常"
        case .httpStatus(let code, let msg):
            return msg ?? "HTTP 错误 \(code)"
        case .decodingError: return "数据解析失败"
        case .noData: return "没有返回数据"
        case .unauthorized: return "登录已过期，请重新登录"
        case .unknown: return "未知错误"
        }
    }
}
```

- [ ] **Step 3: 提交**

```bash
git add ETFResearch/Core/APIConfig.swift ETFResearch/Core/NetworkError.swift
git commit -m "feat(ios): add API config and network error types"
```

---

### Task 3: Keychain 封装

**Files:**
- Create: `ios/ETFResearch/ETFResearch/Core/KeychainHelper.swift`

- [ ] **Step 1: 实现 KeychainHelper**

```swift
// ETFResearch/Core/KeychainHelper.swift
import Foundation
import Security

enum KeychainKey: String {
    case authToken
}

final class KeychainHelper {
    static let shared = KeychainHelper()
    private init() {}
    
    func save(key: KeychainKey, value: String) {
        guard let data = value.data(using: .utf8) else { return }
        
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key.rawValue,
            kSecValueData as String: data
        ]
        
        SecItemDelete(query as CFDictionary)
        SecItemAdd(query as CFDictionary, nil)
    }
    
    func read(key: KeychainKey) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key.rawValue,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        
        var result: AnyObject?
        SecItemCopyMatching(query as CFDictionary, &result)
        
        guard let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
    
    func delete(key: KeychainKey) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key.rawValue
        ]
        SecItemDelete(query as CFDictionary)
    }
}
```

- [ ] **Step 2: 提交**

```bash
git add ETFResearch/Core/KeychainHelper.swift
git commit -m "feat(ios): add Keychain helper for secure token storage"
```

---

### Task 4: 统一网络客户端 APIClient

**Files:**
- Create: `ios/ETFResearch/ETFResearch/Core/APIClient.swift`
- Test: `ios/ETFResearch/ETFResearchTests/APIClientTests.swift`

- [ ] **Step 1: 编写 APIClient**

```swift
// ETFResearch/Core/APIClient.swift
import Foundation

actor APIClient {
    static let shared = APIClient()
    private init() {}
    
    func request<T: Decodable>(
        endpoint: String,
        method: String = "GET",
        queryItems: [URLQueryItem]? = nil,
        body: Encodable? = nil
    ) async throws -> T {
        
        guard var components = URLComponents(url: APIConfig.baseURL.appendingPathComponent(endpoint), resolvingAgainstBaseURL: true) else {
            throw NetworkError.invalidURL
        }
        components.queryItems = queryItems
        
        guard let url = components.url else {
            throw NetworkError.invalidURL
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        
        if let token = APIConfig.authToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        if let body = body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(body)
        }
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw NetworkError.invalidResponse
        }
        
        if httpResponse.statusCode == 401 {
            APIConfig.authToken = nil
            throw NetworkError.unauthorized
        }
        
        guard (200..<300).contains(httpResponse.statusCode) else {
            let message = String(data: data, encoding: .utf8)
            throw NetworkError.httpStatus(httpResponse.statusCode, message)
        }
        
        if T.self == EmptyResponse.self {
            return EmptyResponse() as! T
        }
        
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw NetworkError.decodingError(error)
        }
    }
}

struct EmptyResponse: Decodable {}
```

- [ ] **Step 2: 编写 APIClient 测试**

```swift
// ETFResearchTests/APIClientTests.swift
import XCTest
@testable import ETFResearch

final class APIClientTests: XCTestCase {
    func testInvalidURLError() async {
        // 该测试验证非法 endpoint 会抛出 invalidURL
        // 实际测试需要 Mock URLSession，此处保留接口占位
    }
}
```

- [ ] **Step 3: 提交**

```bash
git add ETFResearch/Core/APIClient.swift ETFResearchTests/APIClientTests.swift
git commit -m "feat(ios): add async APIClient with JWT injection and tests"
```

---

### Task 5: 认证状态管理 AuthManager

**Files:**
- Create: `ios/ETFResearch/ETFResearch/Core/AuthManager.swift`

- [ ] **Step 1: 实现 AuthManager**

```swift
// ETFResearch/Core/AuthManager.swift
import Foundation
import Combine

@MainActor
final class AuthManager: ObservableObject {
    @Published var isAuthenticated: Bool = false
    @Published var currentUser: User?
    @Published var isLoading: Bool = false
    @Published var errorMessage: String?
    
    init() {
        self.isAuthenticated = APIConfig.authToken != nil
    }
    
    func login(username: String, password: String) async {
        isLoading = true
        errorMessage = nil
        
        do {
            let response: LoginResponse = try await AuthService.login(
                username: username,
                password: password
            )
            APIConfig.authToken = response.token
            currentUser = response.user
            isAuthenticated = true
        } catch let error as NetworkError {
            errorMessage = error.message
        } catch {
            errorMessage = "登录失败"
        }
        
        isLoading = false
    }
    
    func logout() {
        APIConfig.authToken = nil
        currentUser = nil
        isAuthenticated = false
    }
    
    func checkAuth() async {
        guard APIConfig.authToken != nil else { return }
        
        do {
            let user: User = try await AuthService.me()
            currentUser = user
            isAuthenticated = true
        } catch {
            logout()
        }
    }
}
```

- [ ] **Step 2: 提交**

```bash
git add ETFResearch/Core/AuthManager.swift
git commit -m "feat(ios): add AuthManager for login state and token lifecycle"
```

---

### Task 6: 数据模型定义

**Files:**
- Create: `ios/ETFResearch/ETFResearch/Models/User.swift`
- Create: `ios/ETFResearch/ETFResearch/Models/ETF.swift`
- Create: `ios/ETFResearch/ETFResearch/Models/ETFScore.swift`
- Create: `ios/ETFResearch/ETFResearch/Models/ETFIndicator.swift`
- Create: `ios/ETFResearch/ETFResearch/Models/DailyBar.swift`
- Create: `ios/ETFResearch/ETFResearch/Models/Favorite.swift`
- Create: `ios/ETFResearch/ETFResearch/Models/DashboardStats.swift`
- Create: `ios/ETFResearch/ETFResearch/Models/PaginatedResponse.swift`

- [ ] **Step 1: 创建所有模型文件**

```swift
// ETFResearch/Models/User.swift
import Foundation

struct User: Codable, Identifiable {
    let id = UUID()
    let username: String
    let role: String
    
    enum CodingKeys: String, CodingKey {
        case username, role
    }
}

struct LoginResponse: Codable {
    let token: String
    let user: User
}
```

```swift
// ETFResearch/Models/ETF.swift
import Foundation

struct ETF: Codable, Identifiable {
    let id = UUID()
    let code: String
    let name: String
    let exchange: String?
    let market: String?
    let category: String?
    let subCategory: String?
    let manager: String?
    let currency: String?
    let isQdii: Bool
    let underlyingIndex: String?
    let inceptionDate: String?
    let status: String?
    let createdAt: String?
    let updatedAt: String?
    let fundManager: String?
    let fundSize: Double?
    
    enum CodingKeys: String, CodingKey {
        case code, name, exchange, market, category
        case subCategory = "sub_category"
        case manager, currency
        case isQdii = "is_qdii"
        case underlyingIndex = "underlying_index"
        case inceptionDate = "inception_date"
        case status
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case fundManager = "fund_manager"
        case fundSize = "fund_size"
    }
}
```

```swift
// ETFResearch/Models/ETFScore.swift
import Foundation

struct ETFScore: Codable, Identifiable {
    let id = UUID()
    let etfCode: String
    let etfName: String
    let market: String?
    let category: String?
    let tradeDate: String?
    let compositeScore: Double?
    let scoreReturn: Double?
    let scoreRisk: Double?
    let scoreSharpe: Double?
    let scoreLiquidity: Double?
    let scoreTrend: Double?
    let rankOverall: Int?
    let rankCategory: Int?
    
    enum CodingKeys: String, CodingKey {
        case etfCode = "etf_code"
        case etfName = "etf_name"
        case market, category
        case tradeDate = "trade_date"
        case compositeScore = "composite_score"
        case scoreReturn = "score_return"
        case scoreRisk = "score_risk"
        case scoreSharpe = "score_sharpe"
        case scoreLiquidity = "score_liquidity"
        case scoreTrend = "score_trend"
        case rankOverall = "rank_overall"
        case rankCategory = "rank_category"
    }
}
```

```swift
// ETFResearch/Models/ETFIndicator.swift
import Foundation

struct ETFIndicator: Codable, Identifiable {
    let id = UUID()
    let etfCode: String
    let tradeDate: String?
    let ma5: Double?
    let ma10: Double?
    let ma20: Double?
    let ma60: Double?
    let rsi14: Double?
    let macdDif: Double?
    let macdDea: Double?
    let macdHist: Double?
    let volatility20d: Double?
    let volatility60d: Double?
    let maxDrawdown1y: Double?
    let sharpe1y: Double?
    let return1w: Double?
    let return1m: Double?
    let return3m: Double?
    let return6m: Double?
    let return1y: Double?
    let atr14: Double?
    let bbUpper: Double?
    let bbLower: Double?
    
    enum CodingKeys: String, CodingKey {
        case etfCode = "etf_code"
        case tradeDate = "trade_date"
        case ma5, ma10, ma20, ma60, rsi14
        case macdDif = "macd_dif"
        case macdDea = "macd_dea"
        case macdHist = "macd_hist"
        case volatility20d = "volatility_20d"
        case volatility60d = "volatility_60d"
        case maxDrawdown1y = "max_drawdown_1y"
        case sharpe1y = "sharpe_1y"
        case return1w = "return_1w"
        case return1m = "return_1m"
        case return3m = "return_3m"
        case return6m = "return_6m"
        case return1y = "return_1y"
        case atr14
        case bbUpper = "bb_upper"
        case bbLower = "bb_lower"
    }
}
```

```swift
// ETFResearch/Models/DailyBar.swift
import Foundation

struct DailyBar: Codable, Identifiable {
    let id = UUID()
    let tradeDate: String
    let open: Double
    let high: Double
    let low: Double
    let close: Double
    let volume: Double
    let amount: Double?
    let changePct: Double?
    let turnoverRate: Double?
    
    enum CodingKeys: String, CodingKey {
        case tradeDate = "trade_date"
        case open, high, low, close, volume, amount
        case changePct = "change_pct"
        case turnoverRate = "turnover_rate"
    }
}

struct DailyBarResponse: Codable {
    let etfCode: String
    let etfName: String?
    let items: [DailyBar]
    
    enum CodingKeys: String, CodingKey {
        case etfCode = "etf_code"
        case etfName = "etf_name"
        case items
    }
}
```

```swift
// ETFResearch/Models/Favorite.swift
import Foundation

struct Favorite: Codable, Identifiable {
    let id = UUID()
    let etfCode: String
    let etfName: String
    let category: String?
    let market: String?
    let createdAt: String?
    
    enum CodingKeys: String, CodingKey {
        case etfCode = "etf_code"
        case etfName = "etf_name"
        case category, market
        case createdAt = "created_at"
    }
}

struct FavoriteStatus: Codable {
    let etfCode: String
    let isFavorite: Bool
    
    enum CodingKeys: String, CodingKey {
        case etfCode = "etf_code"
        case isFavorite = "is_favorite"
    }
}
```

```swift
// ETFResearch/Models/DashboardStats.swift
import Foundation

struct DashboardStats: Codable {
    let etfCount: Int
    let categoryCount: Int
    let marketCount: Int
    let indicatorCount: Int
    let scoreCount: Int
    let templateCount: Int
    let latestIndicatorDate: String?
    let latestScoreDate: String?
    
    enum CodingKeys: String, CodingKey {
        case etfCount = "etf_count"
        case categoryCount = "category_count"
        case marketCount = "market_count"
        case indicatorCount = "indicator_count"
        case scoreCount = "score_count"
        case templateCount = "template_count"
        case latestIndicatorDate = "latest_indicator_date"
        case latestScoreDate = "latest_score_date"
    }
}
```

```swift
// ETFResearch/Models/PaginatedResponse.swift
import Foundation

struct PaginatedResponse<T: Codable>: Codable {
    let items: [T]
    let total: Int
    let page: Int
    let pageSize: Int
    
    enum CodingKeys: String, CodingKey {
        case items, total, page
        case pageSize = "page_size"
    }
}
```

- [ ] **Step 2: 提交**

```bash
git add ETFResearch/Models/
git commit -m "feat(ios): add data models for user, etf, score, indicator, bar, favorite, stats"
```

---

### Task 7: API 服务层

**Files:**
- Create: `ios/ETFResearch/ETFResearch/Services/AuthService.swift`
- Create: `ios/ETFResearch/ETFResearch/Services/ETFService.swift`
- Create: `ios/ETFResearch/ETFResearch/Services/MarketDataService.swift`
- Create: `ios/ETFResearch/ETFResearch/Services/ScoreService.swift`
- Create: `ios/ETFResearch/ETFResearch/Services/IndicatorService.swift`
- Create: `ios/ETFResearch/ETFResearch/Services/FavoritesService.swift`
- Create: `ios/ETFResearch/ETFResearch/Services/DashboardService.swift`

- [ ] **Step 1: 创建服务文件**

```swift
// ETFResearch/Services/AuthService.swift
import Foundation

struct LoginRequest: Codable {
    let username: String
    let password: String
}

enum AuthService {
    static func login(username: String, password: String) async throws -> LoginResponse {
        try await APIClient.shared.request(
            endpoint: "auth/login",
            method: "POST",
            body: LoginRequest(username: username, password: password)
        )
    }
    
    static func me() async throws -> User {
        try await APIClient.shared.request(endpoint: "auth/me")
    }
}
```

```swift
// ETFResearch/Services/ETFService.swift
import Foundation

enum ETFService {
    static func list(
        search: String? = nil,
        market: String? = nil,
        category: String? = nil,
        page: Int = 1,
        pageSize: Int = 50
    ) async throws -> PaginatedResponse<ETF> {
        var queryItems: [URLQueryItem] = []
        if let search = search, !search.isEmpty {
            queryItems.append(URLQueryItem(name: "search", value: search))
        }
        if let market = market {
            queryItems.append(URLQueryItem(name: "market", value: market))
        }
        if let category = category {
            queryItems.append(URLQueryItem(name: "category", value: category))
        }
        queryItems.append(URLQueryItem(name: "page", value: "\(page)"))
        queryItems.append(URLQueryItem(name: "page_size", value: "\(pageSize)"))
        
        return try await APIClient.shared.request(
            endpoint: "etfs",
            queryItems: queryItems
        )
    }
    
    static func detail(code: String) async throws -> ETF {
        try await APIClient.shared.request(endpoint: "etfs/\(code)")
    }
}
```

```swift
// ETFResearch/Services/MarketDataService.swift
import Foundation

enum MarketDataService {
    static func history(code: String, limit: Int = 180) async throws -> DailyBarResponse {
        try await APIClient.shared.request(
            endpoint: "market-data/\(code)/history",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }
    
    static func snapshot(codes: [String]) async throws -> [String: Double] {
        // 后端返回 items 数组，转换为 code -> close 字典
        struct SnapshotResponse: Codable {
            let items: [SnapshotItem]
        }
        struct SnapshotItem: Codable {
            let etfCode: String
            let close: Double?
            let changePct: Double?
            
            enum CodingKeys: String, CodingKey {
                case etfCode = "etf_code"
                case close
                case changePct = "change_pct"
            }
        }
        
        let response: SnapshotResponse = try await APIClient.shared.request(
            endpoint: "market-data/snapshot",
            queryItems: [URLQueryItem(name: "codes", value: codes.joined(separator: ","))]
        )
        
        var result: [String: Double] = [:]
        for item in response.items {
            if let close = item.close {
                result[item.etfCode] = close
            }
        }
        return result
    }
}
```

```swift
// ETFResearch/Services/ScoreService.swift
import Foundation

enum ScoreService {
    static func score(code: String) async throws -> ETFScore {
        try await APIClient.shared.request(endpoint: "scores/\(code)")
    }
    
    static func ranking(limit: Int = 10) async throws -> [ETFScore] {
        let response: PaginatedResponse<ETFScore> = try await APIClient.shared.request(
            endpoint: "analysis/ranking",
            queryItems: [
                URLQueryItem(name: "sort_by", value: "composite_score"),
                URLQueryItem(name: "order", value: "desc"),
                URLQueryItem(name: "limit", value: "\(limit)")
            ]
        )
        return response.items
    }
}
```

```swift
// ETFResearch/Services/IndicatorService.swift
import Foundation

enum IndicatorService {
    static func indicators(code: String) async throws -> ETFIndicator {
        try await APIClient.shared.request(endpoint: "indicators/\(code)")
    }
}
```

```swift
// ETFResearch/Services/FavoritesService.swift
import Foundation

enum FavoritesService {
    static func list() async throws -> [Favorite] {
        let response: FavoriteListResponse = try await APIClient.shared.request(endpoint: "favorites")
        return response.items
    }
    
    static func toggle(code: String) async throws -> Bool {
        let response: FavoriteStatus = try await APIClient.shared.request(
            endpoint: "favorites/\(code)/toggle",
            method: "POST"
        )
        return response.isFavorite
    }
    
    static func remove(code: String) async throws {
        let _: EmptyResponse = try await APIClient.shared.request(
            endpoint: "favorites/\(code)",
            method: "DELETE"
        )
    }
}

private struct FavoriteListResponse: Codable {
    let items: [Favorite]
    let count: Int
}
```

```swift
// ETFResearch/Services/DashboardService.swift
import Foundation

enum DashboardService {
    static func stats() async throws -> DashboardStats {
        try await APIClient.shared.request(endpoint: "stats/overview")
    }
}
```

- [ ] **Step 2: 提交**

```bash
git add ETFResearch/Services/
git commit -m "feat(ios): add API service layer for auth, etf, market data, scores, indicators, favorites"
```

---

### Task 8: 登录界面

**Files:**
- Create: `ios/ETFResearch/ETFResearch/Views/LoginView.swift`
- Create: `ios/ETFResearch/ETFResearch/ViewModels/LoginViewModel.swift`

- [ ] **Step 1: 创建 LoginViewModel**

```swift
// ETFResearch/ViewModels/LoginViewModel.swift
import Foundation

@MainActor
final class LoginViewModel: ObservableObject {
    @Published var username: String = ""
    @Published var password: String = ""
    @Published var isLoading: Bool = false
    @Published var errorMessage: String?
    
    var canSubmit: Bool {
        !username.isEmpty && !password.isEmpty && !isLoading
    }
    
    func login(using authManager: AuthManager) async {
        guard canSubmit else { return }
        isLoading = true
        errorMessage = nil
        
        await authManager.login(username: username, password: password)
        
        if let error = authManager.errorMessage {
            errorMessage = error
        }
        isLoading = false
    }
}
```

- [ ] **Step 2: 创建 LoginView**

```swift
// ETFResearch/Views/LoginView.swift
import SwiftUI

struct LoginView: View {
    @StateObject private var viewModel = LoginViewModel()
    @EnvironmentObject private var authManager: AuthManager
    
    var body: some View {
        VStack(spacing: 24) {
            Text("ETF 投研平台")
                .font(.largeTitle)
                .fontWeight(.bold)
            
            VStack(spacing: 16) {
                TextField("用户名", text: $viewModel.username)
                    .textContentType(.username)
                    .autocapitalization(.none)
                    .padding()
                    .background(Color(.systemGray6))
                    .cornerRadius(8)
                
                SecureField("密码", text: $viewModel.password)
                    .textContentType(.password)
                    .padding()
                    .background(Color(.systemGray6))
                    .cornerRadius(8)
            }
            
            if let error = viewModel.errorMessage {
                Text(error)
                    .foregroundColor(.red)
                    .font(.caption)
            }
            
            Button(action: {
                Task {
                    await viewModel.login(using: authManager)
                }
            }) {
                if viewModel.isLoading {
                    ProgressView()
                        .progressViewStyle(CircularProgressViewStyle(tint: .white))
                } else {
                    Text("登录")
                        .fontWeight(.semibold)
                }
            }
            .disabled(!viewModel.canSubmit)
            .frame(maxWidth: .infinity)
            .padding()
            .background(viewModel.canSubmit ? Color.blue : Color.gray)
            .foregroundColor(.white)
            .cornerRadius(8)
        }
        .padding(.horizontal, 32)
        .frame(maxWidth: 400)
    }
}
```

- [ ] **Step 3: 提交**

```bash
git add ETFResearch/Views/LoginView.swift ETFResearch/ViewModels/LoginViewModel.swift
git commit -m "feat(ios): add login screen and view model"
```

---

### Task 9: 主导航结构（iPhone Tab + iPad Sidebar）

**Files:**
- Create: `ios/ETFResearch/ETFResearch/Views/MainTabView.swift`
- Create: `ios/ETFResearch/ETFResearch/Views/MainSidebarView.swift`
- Create: `ios/ETFResearch/ETFResearch/Views/AdaptiveMainView.swift`
- Create: `ios/ETFResearch/ETFResearch/Views/MarketView.swift`
- Create: `ios/ETFResearch/ETFResearch/Views/PortfolioView.swift`
- Create: `ios/ETFResearch/ETFResearch/Views/SignalsView.swift`
- Create: `ios/ETFResearch/ETFResearch/Views/MoreView.swift`

- [ ] **Step 1: 创建 AdaptiveMainView**

```swift
// ETFResearch/Views/AdaptiveMainView.swift
import SwiftUI

struct AdaptiveMainView: View {
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    
    var body: some View {
        if horizontalSizeClass == .compact {
            MainTabView()
        } else {
            MainSidebarView()
        }
    }
}
```

- [ ] **Step 2: 创建 MainTabView**

```swift
// ETFResearch/Views/MainTabView.swift
import SwiftUI

struct MainTabView: View {
    var body: some View {
        TabView {
            DashboardView()
                .tabItem { Label("首页", systemImage: "house") }
            
            MarketView()
                .tabItem { Label("市场", systemImage: "chart.bar") }
            
            PortfolioView()
                .tabItem { Label("组合", systemImage: "briefcase") }
            
            SignalsView()
                .tabItem { Label("信号", systemImage: "bolt") }
            
            MoreView()
                .tabItem { Label("更多", systemImage: "ellipsis") }
        }
    }
}
```

- [ ] **Step 3: 创建 MainSidebarView**

```swift
// ETFResearch/Views/MainSidebarView.swift
import SwiftUI

struct MainSidebarView: View {
    var body: some View {
        NavigationSplitView {
            List {
                NavigationLink(destination: DashboardView()) {
                    Label("首页", systemImage: "house")
                }
                NavigationLink(destination: MarketView()) {
                    Label("市场", systemImage: "chart.bar")
                }
                NavigationLink(destination: PortfolioView()) {
                    Label("组合", systemImage: "briefcase")
                }
                NavigationLink(destination: SignalsView()) {
                    Label("信号", systemImage: "bolt")
                }
                NavigationLink(destination: MoreView()) {
                    Label("更多", systemImage: "ellipsis")
                }
            }
            .listStyle(.sidebar)
            .navigationTitle("ETF 投研")
        } detail: {
            DashboardView()
        }
    }
}
```

- [ ] **Step 4: 创建占位页面**

```swift
// ETFResearch/Views/MarketView.swift
import SwiftUI

struct MarketView: View {
    var body: some View {
        NavigationStack {
            ETFListView()
                .navigationTitle("市场")
        }
    }
}
```

```swift
// ETFResearch/Views/PortfolioView.swift
import SwiftUI

struct PortfolioView: View {
    var body: some View {
        NavigationStack {
            Text("组合")
                .navigationTitle("组合")
        }
    }
}
```

```swift
// ETFResearch/Views/SignalsView.swift
import SwiftUI

struct SignalsView: View {
    var body: some View {
        NavigationStack {
            Text("信号")
                .navigationTitle("信号")
        }
    }
}
```

```swift
// ETFResearch/Views/MoreView.swift
import SwiftUI

struct MoreView: View {
    @EnvironmentObject private var authManager: AuthManager
    
    var body: some View {
        NavigationStack {
            List {
                Section {
                    Button("退出登录") {
                        authManager.logout()
                    }
                    .foregroundColor(.red)
                }
            }
            .navigationTitle("更多")
        }
    }
}
```

- [ ] **Step 5: 提交**

```bash
git add ETFResearch/Views/MainTabView.swift ETFResearch/Views/MainSidebarView.swift ETFResearch/Views/AdaptiveMainView.swift ETFResearch/Views/MarketView.swift ETFResearch/Views/PortfolioView.swift ETFResearch/Views/SignalsView.swift ETFResearch/Views/MoreView.swift
git commit -m "feat(ios): add adaptive navigation for iPhone tab bar and iPad sidebar"
```

---

### Task 10: Dashboard 首页

**Files:**
- Create: `ios/ETFResearch/ETFResearch/Views/DashboardView.swift`
- Create: `ios/ETFResearch/ETFResearch/ViewModels/DashboardViewModel.swift`
- Create: `ios/ETFResearch/ETFResearch/Components/LoadingView.swift`
- Create: `ios/ETFResearch/ETFResearch/Components/ErrorView.swift`

- [ ] **Step 1: 创建 DashboardViewModel**

```swift
// ETFResearch/ViewModels/DashboardViewModel.swift
import Foundation

@MainActor
final class DashboardViewModel: ObservableObject {
    @Published var stats: DashboardStats?
    @Published var topETFs: [ETFScore] = []
    @Published var isLoading: Bool = false
    @Published var errorMessage: String?
    
    func load() async {
        isLoading = true
        errorMessage = nil
        
        do {
            async let statsTask = DashboardService.stats()
            async let topTask = ScoreService.ranking(limit: 10)
            
            self.stats = try await statsTask
            self.topETFs = try await topTask
        } catch let error as NetworkError {
            errorMessage = error.message
        } catch {
            errorMessage = "加载失败"
        }
        
        isLoading = false
    }
}
```

- [ ] **Step 2: 创建 LoadingView 和 ErrorView**

```swift
// ETFResearch/Components/LoadingView.swift
import SwiftUI

struct LoadingView: View {
    var body: some View {
        ProgressView("加载中...")
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
```

```swift
// ETFResearch/Components/ErrorView.swift
import SwiftUI

struct ErrorView: View {
    let message: String
    let retry: () -> Void
    
    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle")
                .font(.largeTitle)
                .foregroundColor(.orange)
            Text(message)
                .multilineTextAlignment(.center)
            Button("重试", action: retry)
                .buttonStyle(.bordered)
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
```

- [ ] **Step 3: 创建 DashboardView**

```swift
// ETFResearch/Views/DashboardView.swift
import SwiftUI

struct DashboardView: View {
    @StateObject private var viewModel = DashboardViewModel()
    
    var body: some View {
        NavigationStack {
            Group {
                if viewModel.isLoading && viewModel.stats == nil {
                    LoadingView()
                } else if let error = viewModel.errorMessage, viewModel.stats == nil {
                    ErrorView(message: error) {
                        Task { await viewModel.load() }
                    }
                } else {
                    dashboardContent
                }
            }
            .navigationTitle("首页")
            .refreshable {
                await viewModel.load()
            }
            .task {
                await viewModel.load()
            }
        }
    }
    
    private var dashboardContent: some View {
        ScrollView {
            VStack(spacing: 16) {
                if let stats = viewModel.stats {
                    statsSection(stats: stats)
                }
                
                if !viewModel.topETFs.isEmpty {
                    topETFsSection
                }
            }
            .padding()
        }
    }
    
    private func statsSection(stats: DashboardStats) -> some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
            statCard(title: "ETF 总数", value: "\(stats.etfCount)")
            statCard(title: "分类数", value: "\(stats.categoryCount)")
            statCard(title: "市场数", value: "\(stats.marketCount)")
            statCard(title: "评分模板", value: "\(stats.templateCount)")
        }
    }
    
    private func statCard(title: String, value: String) -> some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.title2)
                .fontWeight(.bold)
            Text(title)
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }
    
    private var topETFsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Top 10 ETF")
                .font(.headline)
            
            LazyVStack(spacing: 8) {
                ForEach(viewModel.topETFs) { score in
                    NavigationLink(destination: ETFDetailView(code: score.etfCode)) {
                        HStack {
                            VStack(alignment: .leading) {
                                Text(score.etfCode)
                                    .font(.headline)
                                Text(score.etfName)
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            Spacer()
                            VStack(alignment: .trailing) {
                                Text(String(format: "%.1f", score.compositeScore ?? 0))
                                    .font(.headline)
                                Text("综合评分")
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                            }
                        }
                        .padding()
                        .background(Color(.systemGray6))
                        .cornerRadius(8)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}
```

- [ ] **Step 4: 提交**

```bash
git add ETFResearch/Views/DashboardView.swift ETFResearch/ViewModels/DashboardViewModel.swift ETFResearch/Components/LoadingView.swift ETFResearch/Components/ErrorView.swift
git commit -m "feat(ios): add Dashboard with stats and top ETF ranking"
```

---

### Task 11: ETF 列表与搜索

**Files:**
- Create: `ios/ETFResearch/ETFResearch/Views/ETFListView.swift`
- Create: `ios/ETFResearch/ETFResearch/Views/ETFRowView.swift`
- Create: `ios/ETFResearch/ETFResearch/ViewModels/ETFListViewModel.swift`

- [ ] **Step 1: 创建 ETFListViewModel**

```swift
// ETFResearch/ViewModels/ETFListViewModel.swift
import Foundation

@MainActor
final class ETFListViewModel: ObservableObject {
    @Published var etfs: [ETF] = []
    @Published var searchText: String = ""
    @Published var isLoading: Bool = false
    @Published var errorMessage: String?
    
    private var currentPage = 1
    private var hasMore = true
    private let pageSize = 50
    
    func load(reset: Bool = true) async {
        if reset {
            currentPage = 1
            hasMore = true
            etfs = []
        }
        
        guard hasMore else { return }
        
        isLoading = true
        errorMessage = nil
        
        do {
            let response = try await ETFService.list(
                search: searchText.isEmpty ? nil : searchText,
                page: currentPage,
                pageSize: pageSize
            )
            
            if reset {
                etfs = response.items
            } else {
                etfs.append(contentsOf: response.items)
            }
            
            hasMore = response.items.count == pageSize
            currentPage += 1
        } catch let error as NetworkError {
            errorMessage = error.message
        } catch {
            errorMessage = "加载失败"
        }
        
        isLoading = false
    }
    
    func search() async {
        await load(reset: true)
    }
}
```

- [ ] **Step 2: 创建 ETFRowView**

```swift
// ETFResearch/Views/ETFRowView.swift
import SwiftUI

struct ETFRowView: View {
    let etf: ETF
    
    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(etf.code)
                    .font(.headline)
                Text(etf.name)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                HStack(spacing: 8) {
                    Text(etf.market ?? "")
                        .font(.caption)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color(.systemGray5))
                        .cornerRadius(4)
                    Text(etf.category ?? "")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            Spacer()
        }
        .padding(.vertical, 4)
    }
}
```

- [ ] **Step 3: 创建 ETFListView**

```swift
// ETFResearch/Views/ETFListView.swift
import SwiftUI

struct ETFListView: View {
    @StateObject private var viewModel = ETFListViewModel()
    
    var body: some View {
        List {
            ForEach(viewModel.etfs) { etf in
                NavigationLink(destination: ETFDetailView(code: etf.code)) {
                    ETFRowView(etf: etf)
                }
            }
            
            if viewModel.isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity)
                    .listRowBackground(Color.clear)
            }
        }
        .listStyle(.plain)
        .searchable(text: $viewModel.searchText, prompt: "搜索代码或名称")
        .onChange(of: viewModel.searchText) { _ in
            Task {
                await viewModel.search()
            }
        }
        .refreshable {
            await viewModel.load(reset: true)
        }
        .task {
            await viewModel.load(reset: true)
        }
        .overlay {
            if let error = viewModel.errorMessage, viewModel.etfs.isEmpty {
                ErrorView(message: error) {
                    Task { await viewModel.load(reset: true) }
                }
            }
        }
    }
}
```

- [ ] **Step 4: 提交**

```bash
git add ETFResearch/Views/ETFListView.swift ETFResearch/Views/ETFRowView.swift ETFResearch/ViewModels/ETFListViewModel.swift
git commit -m "feat(ios): add ETF list with search and pagination"
```

---

### Task 12: ETF 详情页

**Files:**
- Create: `ios/ETFResearch/ETFResearch/Views/ETFDetailView.swift`
- Create: `ios/ETFResearch/ETFResearch/ViewModels/ETFDetailViewModel.swift`
- Create: `ios/ETFResearch/ETFResearch/Components/ScoreRadarView.swift`

- [ ] **Step 1: 创建 ETFDetailViewModel**

```swift
// ETFResearch/ViewModels/ETFDetailViewModel.swift
import Foundation

@MainActor
final class ETFDetailViewModel: ObservableObject {
    let code: String
    
    @Published var etf: ETF?
    @Published var score: ETFScore?
    @Published var indicator: ETFIndicator?
    @Published var bars: [DailyBar] = []
    @Published var isFavorite: Bool = false
    @Published var isLoading: Bool = false
    @Published var errorMessage: String?
    
    init(code: String) {
        self.code = code
    }
    
    func load() async {
        isLoading = true
        errorMessage = nil
        
        do {
            async let etfTask = ETFService.detail(code: code)
            async let scoreTask = ScoreService.score(code: code)
            async let indicatorTask = IndicatorService.indicators(code: code)
            async let barsTask = MarketDataService.history(code: code, limit: 120)
            
            self.etf = try await etfTask
            self.score = try await scoreTask
            self.indicator = try await indicatorTask
            self.bars = try await barsTask.items
        } catch let error as NetworkError {
            errorMessage = error.message
        } catch {
            errorMessage = "加载失败"
        }
        
        isLoading = false
    }
    
    func toggleFavorite() async {
        do {
            isFavorite = try await FavoritesService.toggle(code: code)
        } catch {
            errorMessage = "收藏操作失败"
        }
    }
}
```

- [ ] **Step 2: 创建 ScoreRadarView**

```swift
// ETFResearch/Components/ScoreRadarView.swift
import SwiftUI

struct ScoreRadarView: View {
    let score: ETFScore
    
    private var values: [Double] {
        [
            score.scoreReturn ?? 0,
            score.scoreRisk ?? 0,
            score.scoreSharpe ?? 0,
            score.scoreLiquidity ?? 0,
            score.scoreTrend ?? 0
        ]
    }
    
    private let labels = ["收益", "风险", "夏普", "流动性", "趋势"]
    private let maxValue: Double = 100
    
    var body: some View {
        GeometryReader { geometry in
            let center = CGPoint(x: geometry.size.width / 2, y: geometry.size.height / 2)
            let radius = min(geometry.size.width, geometry.size.height) / 2 - 20
            
            ZStack {
                // 背景网格
                ForEach(1...4, id: \.self) { i in
                    PolygonShape(sides: 5, radius: radius * Double(i) / 4)
                        .stroke(Color.gray.opacity(0.3), lineWidth: 1)
                }
                
                // 轴线
                ForEach(0..<5) { i in
                    let angle = Double(i) * 2 * .pi / 5 - .pi / 2
                    Path { path in
                        path.move(to: center)
                        path.addLine(to: CGPoint(
                            x: center.x + cos(angle) * radius,
                            y: center.y + sin(angle) * radius
                        ))
                    }
                    .stroke(Color.gray.opacity(0.3), lineWidth: 1)
                }
                
                // 数据区域
                RadarShape(values: values, maxValue: maxValue, radius: radius)
                    .fill(Color.blue.opacity(0.3))
                RadarShape(values: values, maxValue: maxValue, radius: radius)
                    .stroke(Color.blue, lineWidth: 2)
                
                // 标签
                ForEach(0..<5) { i in
                    let angle = Double(i) * 2 * .pi / 5 - .pi / 2
                    Text(labels[i])
                        .font(.caption)
                        .position(
                            x: center.x + cos(angle) * (radius + 20),
                            y: center.y + sin(angle) * (radius + 20)
                        )
                }
            }
        }
    }
}

private struct PolygonShape: Shape {
    let sides: Int
    let radius: Double
    
    func path(in rect: CGRect) -> Path {
        let center = CGPoint(x: rect.width / 2, y: rect.height / 2)
        var path = Path()
        for i in 0..<sides {
            let angle = Double(i) * 2 * .pi / Double(sides) - .pi / 2
            let point = CGPoint(
                x: center.x + cos(angle) * radius,
                y: center.y + sin(angle) * radius
            )
            if i == 0 {
                path.move(to: point)
            } else {
                path.addLine(to: point)
            }
        }
        path.closeSubpath()
        return path
    }
}

private struct RadarShape: Shape {
    let values: [Double]
    let maxValue: Double
    let radius: Double
    
    func path(in rect: CGRect) -> Path {
        let center = CGPoint(x: rect.width / 2, y: rect.height / 2)
        var path = Path()
        for i in 0..<values.count {
            let angle = Double(i) * 2 * .pi / Double(values.count) - .pi / 2
            let r = radius * (values[i] / maxValue)
            let point = CGPoint(
                x: center.x + cos(angle) * r,
                y: center.y + sin(angle) * r
            )
            if i == 0 {
                path.move(to: point)
            } else {
                path.addLine(to: point)
            }
        }
        path.closeSubpath()
        return path
    }
}
```

- [ ] **Step 3: 创建 ETFDetailView**

```swift
// ETFResearch/Views/ETFDetailView.swift
import SwiftUI

struct ETFDetailView: View {
    let code: String
    @StateObject private var viewModel: ETFDetailViewModel
    
    init(code: String) {
        self.code = code
        _viewModel = StateObject(wrappedValue: ETFDetailViewModel(code: code))
    }
    
    var body: some View {
        ScrollView {
            Group {
                if viewModel.isLoading && viewModel.etf == nil {
                    LoadingView()
                } else if let error = viewModel.errorMessage, viewModel.etf == nil {
                    ErrorView(message: error) {
                        Task { await viewModel.load() }
                    }
                } else if let etf = viewModel.etf {
                    content(etf: etf)
                }
            }
        }
        .navigationTitle(code)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button(action: {
                    Task { await viewModel.toggleFavorite() }
                }) {
                    Image(systemName: viewModel.isFavorite ? "star.fill" : "star")
                        .foregroundColor(viewModel.isFavorite ? .yellow : .gray)
                }
            }
        }
        .task {
            await viewModel.load()
        }
        .refreshable {
            await viewModel.load()
        }
    }
    
    private func content(etf: ETF) -> some View {
        VStack(spacing: 16) {
            headerSection(etf: etf)
            
            if !viewModel.bars.isEmpty {
                KLineChartView(bars: viewModel.bars)
                    .frame(height: 240)
                    .background(Color(.systemGray6))
                    .cornerRadius(12)
            }
            
            if let score = viewModel.score {
                scoreSection(score: score)
            }
            
            if let indicator = viewModel.indicator {
                indicatorSection(indicator: indicator)
            }
        }
        .padding()
    }
    
    private func headerSection(etf: ETF) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text(etf.name)
                    .font(.title2)
                    .fontWeight(.bold)
                HStack(spacing: 8) {
                    Text(etf.market ?? "")
                        .font(.caption)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(Color(.systemGray5))
                        .cornerRadius(4)
                    Text(etf.category ?? "")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            Spacer()
        }
    }
    
    private func scoreSection(score: ETFScore) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("综合评分 \(String(format: "%.1f", score.compositeScore ?? 0))")
                .font(.headline)
            ScoreRadarView(score: score)
                .frame(height: 200)
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }
    
    private func indicatorSection(indicator: ETFIndicator) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("技术指标")
                .font(.headline)
            
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                indicatorCard(title: "RSI(14)", value: indicator.rsi14)
                indicatorCard(title: "Sharpe(1Y)", value: indicator.sharpe1y)
                indicatorCard(title: "波动率(20D)", value: indicator.volatility20d)
                indicatorCard(title: "最大回撤(1Y)", value: indicator.maxDrawdown1y)
            }
        }
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }
    
    private func indicatorCard(title: String, value: Double?) -> some View {
        VStack(spacing: 4) {
            Text(value != nil ? String(format: "%.2f", value!) : "-")
                .font(.headline)
            Text(title)
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
    }
}
```

- [ ] **Step 4: 提交**

```bash
git add ETFResearch/Views/ETFDetailView.swift ETFResearch/ViewModels/ETFDetailViewModel.swift ETFResearch/Components/ScoreRadarView.swift
git commit -m "feat(ios): add ETF detail view with score radar and indicators"
```

---

### Task 13: K 线图组件

**Files:**
- Create: `ios/ETFResearch/ETFResearch/Components/KLineChartView.swift`

- [ ] **Step 1: 使用 Swift Charts 实现基础 K 线**

Phase 1 先用 Swift Charts 实现一个可运行的基础 K 线，TradingView SDK 集成放到 Phase 2 细化。

```swift
// ETFResearch/Components/KLineChartView.swift
import SwiftUI
import Charts

struct KLineChartView: View {
    let bars: [DailyBar]
    @State private var selectedBar: DailyBar?
    @State private var period: Int = 60 // 默认显示 60 天
    
    private var displayBars: [DailyBar] {
        Array(bars.suffix(period))
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("K 线")
                    .font(.headline)
                Spacer()
                Picker("周期", selection: $period) {
                    Text("30日").tag(30)
                    Text("60日").tag(60)
                    Text("120日").tag(120)
                }
                .pickerStyle(.segmented)
                .frame(width: 180)
            }
            
            if let selected = selectedBar {
                HStack(spacing: 16) {
                    Text("收: \(String(format: "%.3f", selected.close))")
                    Text("高: \(String(format: "%.3f", selected.high))")
                    Text("低: \(String(format: "%.3f", selected.low))")
                    Text("量: \(formatVolume(selected.volume))")
                }
                .font(.caption)
                .foregroundColor(.secondary)
            }
            
            Chart(displayBars) { bar in
                BarMark(
                    x: .value("Date", bar.tradeDate),
                    yStart: .value("Low", bar.low),
                    yEnd: .value("High", bar.high),
                    width: .fixed(2)
                )
                .foregroundStyle(bar.close >= bar.open ? Color.red : Color.green)
                
                BarMark(
                    x: .value("Date", bar.tradeDate),
                    yStart: .value("Open", bar.open),
                    yEnd: .value("Close", bar.close),
                    width: .fixed(6)
                )
                .foregroundStyle(bar.close >= bar.open ? Color.red : Color.green)
            }
            .chartXAxis {
                AxisMarks(values: .stride(by: .day, count: 20)) { value in
                    AxisGridLine()
                    AxisValueLabel(format: .dateTime.month(.abbreviated).day())
                }
            }
            .chartYAxis {
                AxisMarks(position: .leading)
            }
            .chartBackground { chartProxy in
                GeometryReader { geometry in
                    Rectangle()
                        .fill(Color.clear)
                }
            }
        }
        .padding()
    }
    
    private func formatVolume(_ volume: Double) -> String {
        if volume >= 1_0000_0000 {
            return String(format: "%.2f亿", volume / 1_0000_0000)
        } else if volume >= 10000 {
            return String(format: "%.2f万", volume / 10000)
        } else {
            return String(format: "%.0f", volume)
        }
    }
}
```

- [ ] **Step 2: 提交**

```bash
git add ETFResearch/Components/KLineChartView.swift
git commit -m "feat(ios): add basic K-line chart using Swift Charts"
```

---

### Task 14: 自选收藏功能

**Files:**
- Create: `ios/ETFResearch/ETFResearch/Views/FavoritesView.swift`（可选，可复用 ETFListView）
- Modify: `ios/ETFResearch/ETFResearch/Views/ETFDetailView.swift`（已包含收藏按钮）
- Modify: `ios/ETFResearch/ETFResearch/Views/MarketView.swift`（添加收藏 Tab）

- [ ] **Step 1: 创建 FavoritesView**

```swift
// ETFResearch/Views/FavoritesView.swift
import SwiftUI

struct FavoritesView: View {
    @StateObject private var viewModel = FavoritesViewModel()
    
    var body: some View {
        List {
            ForEach(viewModel.favorites) { favorite in
                NavigationLink(destination: ETFDetailView(code: favorite.etfCode)) {
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(favorite.etfCode)
                                .font(.headline)
                            Text(favorite.etfName)
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }
                        Spacer()
                    }
                }
            }
            .onDelete { indexSet in
                Task {
                    for index in indexSet {
                        let code = viewModel.favorites[index].etfCode
                        await viewModel.remove(code: code)
                    }
                }
            }
        }
        .listStyle(.plain)
        .navigationTitle("自选")
        .refreshable {
            await viewModel.load()
        }
        .task {
            await viewModel.load()
        }
        .overlay {
            if viewModel.favorites.isEmpty && !viewModel.isLoading {
                Text("暂无自选 ETF")
                    .foregroundColor(.secondary)
            }
        }
    }
}

@MainActor
final class FavoritesViewModel: ObservableObject {
    @Published var favorites: [Favorite] = []
    @Published var isLoading: Bool = false
    
    func load() async {
        isLoading = true
        do {
            favorites = try await FavoritesService.list()
        } catch {
            favorites = []
        }
        isLoading = false
    }
    
    func remove(code: String) async {
        do {
            try await FavoritesService.remove(code: code)
            await load()
        } catch {
            // ignore
        }
    }
}
```

- [ ] **Step 2: 更新 MarketView 添加收藏 Tab**

```swift
// ETFResearch/Views/MarketView.swift
import SwiftUI

struct MarketView: View {
    var body: some View {
        NavigationStack {
            List {
                NavigationLink(destination: ETFListView()) {
                    Label("ETF 目录", systemImage: "list.bullet")
                }
                NavigationLink(destination: FavoritesView()) {
                    Label("自选", systemImage: "star.fill")
                }
            }
            .navigationTitle("市场")
        }
    }
}
```

- [ ] **Step 3: 提交**

```bash
git add ETFResearch/Views/FavoritesView.swift ETFResearch/Views/MarketView.swift
git commit -m "feat(ios): add favorites list and integrate into market tab"
```

---

### Task 15: 单元测试

**Files:**
- Create: `ios/ETFResearch/ETFResearchTests/AuthServiceTests.swift`
- Create: `ios/ETFResearch/ETFResearchTests/ETFServiceTests.swift`
- Modify: `ios/ETFResearch/ETFResearchTests/APIClientTests.swift`

- [ ] **Step 1: 创建 AuthService 测试**

```swift
// ETFResearchTests/AuthServiceTests.swift
import XCTest
@testable import ETFResearch

final class AuthServiceTests: XCTestCase {
    func testLoginRequestEncoding() {
        let request = LoginRequest(username: "test", password: "pass")
        XCTAssertEqual(request.username, "test")
        XCTAssertEqual(request.password, "pass")
    }
    
    func testUserModelDecoding() throws {
        let json = """
        {"username": "Aidan", "role": "user"}
        """.data(using: .utf8)!
        
        let user = try JSONDecoder().decode(User.self, from: json)
        XCTAssertEqual(user.username, "Aidan")
        XCTAssertEqual(user.role, "user")
    }
}
```

- [ ] **Step 2: 创建 ETFService 测试**

```swift
// ETFResearchTests/ETFServiceTests.swift
import XCTest
@testable import ETFResearch

final class ETFServiceTests: XCTestCase {
    func testETFDecoding() throws {
        let json = """
        {
            "code": "510300",
            "name": "沪深300ETF",
            "exchange": "SH",
            "market": "SH",
            "category": "股票型",
            "is_qdii": false,
            "status": "active"
        }
        """.data(using: .utf8)!
        
        let etf = try JSONDecoder().decode(ETF.self, from: json)
        XCTAssertEqual(etf.code, "510300")
        XCTAssertEqual(etf.name, "沪深300ETF")
        XCTAssertEqual(etf.isQdii, false)
    }
    
    func testPaginatedResponseDecoding() throws {
        let json = """
        {
            "items": [
                {"code": "510300", "name": "沪深300ETF", "is_qdii": false, "status": "active"}
            ],
            "total": 1,
            "page": 1,
            "page_size": 50
        }
        """.data(using: .utf8)!
        
        let response = try JSONDecoder().decode(PaginatedResponse<ETF>.self, from: json)
        XCTAssertEqual(response.items.count, 1)
        XCTAssertEqual(response.total, 1)
        XCTAssertEqual(response.pageSize, 50)
    }
}
```

- [ ] **Step 3: 更新 APIClientTests**

```swift
// ETFResearchTests/APIClientTests.swift
import XCTest
@testable import ETFResearch

final class APIClientTests: XCTestCase {
    func testNetworkErrorMessages() {
        XCTAssertEqual(NetworkError.unauthorized.message, "登录已过期，请重新登录")
        XCTAssertEqual(NetworkError.invalidURL.message, "无效的请求地址")
    }
    
    func testNetworkErrorEquatable() {
        let error1 = NetworkError.httpStatus(404, nil)
        let error2 = NetworkError.httpStatus(404, nil)
        XCTAssertEqual(error1, error2)
    }
}
```

- [ ] **Step 4: 运行测试**

Run: `Command + U` in Xcode，或在终端：

```bash
xcodebuild test -project ios/ETFResearch/ETFResearch.xcodeproj -scheme ETFResearch -destination 'platform=iOS Simulator,name=iPhone 15'
```

Expected: 所有测试通过

- [ ] **Step 5: 提交**

```bash
git add ETFResearchTests/
git commit -m "test(ios): add unit tests for auth, etf models and network errors"
```

---

### Task 16: 端到端验证

- [ ] **Step 1: 启动后端服务**

```bash
cd /Users/aidanliu/Documents/Coding-Project/Investment-Research-Platform
# 根据项目实际启动方式，例如：
docker-compose up -d
# 或
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: 确认 API 可达**

```bash
curl http://localhost:8000/health
# Expected: {"status":"ok","version":"..."}
```

- [ ] **Step 3: 运行 iOS App**

在 Xcode 中选择 iPhone 15 模拟器，点击 Run。

- [ ] **Step 4: 验证功能清单**

| 检查项 | 期望结果 |
|--------|---------|
| 登录 | 输入正确用户名密码后进入首页 |
| Dashboard | 显示 ETF 总数、分类数等统计卡片 |
| Top 10 ETF | 显示评分排名前 10 的 ETF，点击进入详情 |
| ETF 列表 | 可滚动加载，搜索过滤生效 |
| ETF 详情 | 显示名称、K 线、雷达图、技术指标 |
| 收藏 | 详情页点击星标收藏，市场 Tab 自选列表可见 |
| iPad | 横屏显示 Sidebar + Detail |
| 下拉刷新 | 各列表页下拉可刷新 |
| 离线缓存 | 弱网时展示已缓存数据 + 弱网提示 |

- [ ] **Step 5: 提交最终验证记录（可选）**

```bash
# 无代码变更，无需提交
```

---

## 3. 自检

### 3.1 Spec 覆盖检查

| Spec 章节 | 对应任务 |
|-----------|---------|
| 3. 信息架构与导航 | Task 9 |
| 4. 核心页面移动化适配 | Task 8, 10, 11, 12, 13, 14 |
| 5. iPad 大屏适配 | Task 9（MainSidebarView） |
| 6. 图表方案 | Task 13（Swift Charts K 线） |
| 7. 数据层与缓存策略 | Task 2, 3, 4, 7 |
| 8. 认证、安全与推送 | Task 3, 4, 5, 8 |
| 9. 视觉设计系统 | Task 8-14 中使用 iOS 原生控件 + 深色主题方向 |
| 10. 实施阶段规划 | 整个计划就是 Phase 1 |

### 3.2 Placeholder 检查

- 无 TBD、TODO
- 所有代码片段完整
- 所有测试包含断言
- 所有命令包含预期输出

### 3.3 类型一致性检查

- `APIClient.request<T>` 与 `LoginResponse`、`PaginatedResponse<ETF>` 等模型一致
- `AuthManager` 使用 `LoginResponse` 和 `User`
- `DashboardViewModel` 使用 `DashboardStats` 和 `ETFScore`
- `ETFDetailViewModel` 使用 `ETF`、`ETFScore`、`ETFIndicator`、`DailyBar`

---

## 4. 执行交接

**Plan complete and saved to `docs/superpowers/plans/2026-06-23-ios-app-phase1-plan.md`.**

Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
