import Foundation
import Observation

/// Dashboard 数据仓库。
///
/// 数据源（逐一对齐 web Dashboard ``useGlobalPulseData`` + ``DigestSummaryCard``）：
/// - ``GET /digest/latest/summary``：研报摘要卡；404 = 「今日研报生成中」空态
/// - ``GET /macro/latest?region=global`` + ``region=us``：宏观脉搏底数
/// - ``GET /macro/indices/global``：实时快照覆盖（内部 code 与 macro 一致，
///   如 global_sp500；单项失败后端跳过，响应恒 200）
/// - ``GET /stats/overview``：平台 KPI 卡（macOS 第三栏）
/// - ``GET /favorites`` + ``GET /market-data/snapshot``：自选异动横条（|涨跌幅| 前 5）
///
/// 与 web 差异：web 的 SPY.US/BTC.US/510300.SH/159915.SZ 四个 realtime tile
/// 走 websocket 行情流（usePriceStream），原生地基暂不含该流，
/// 脉搏分组只保留 macro 类 tile；行情流接入后在此补齐。
@MainActor
@Observable
final class DashboardViewModel {

    // MARK: - 状态

    enum DigestState: Equatable {
        case idle
        case loading
        case loaded
        /// 404：今日尚未生成
        case empty
        case failed(String)
    }

    private(set) var digestSummary: DigestLatestSummary?
    private(set) var digestState: DigestState = .idle

    private(set) var pulseGroups: [PulseGroup] = []
    private(set) var isLoadingPulse = false
    private(set) var pulseError: String?

    /// 实时快照陈旧条数（stale_count 来自后端单一事实来源）
    private(set) var staleCount: Int = 0

    /// 平台 KPI（GET /stats/overview；失败静默，卡片回落为空态）
    private(set) var overview: StatsOverview?
    private(set) var isLoadingOverview = false

    /// 自选异动（自选快照按 |涨跌幅| 排序前 5）
    private(set) var favoriteMovers: [FavoriteMover] = []
    private(set) var isLoadingMovers = false

    /// 最近一次全量加载成功时间（状态条「上次更新 x 分钟前」）
    private(set) var lastUpdated: Date?

    private var hasLoadedOnce = false

    /// 自选异动行（favorites × market-data/snapshot 合并）
    struct FavoriteMover: Identifiable, Equatable {
        var id: String { code }
        let code: String
        let name: String
        let close: Double?
        /// 百分数（1.23 = +1.23%），直接喂 ChangeText
        let changePct: Double?
    }

    /// 顶部状态条圆点的真实状态（替代原假绿点）
    enum DataStatus: Equatable {
        /// 首屏加载中（灰）
        case loading
        /// 全部就绪（绿）
        case ok
        /// 有陈旧数据（黄）
        case stale
        /// 加载失败且无旧数据（红）
        case failed
    }

    var dataStatus: DataStatus {
        if pulseError != nil && pulseGroups.isEmpty { return .failed }
        if isLoadingPulse && pulseGroups.isEmpty { return .loading }
        if staleCount > 0 { return .stale }
        return .ok
    }

    // MARK: - 脉搏分组定义（镜像 web PULSE_GROUPS 的 macro tile）

    struct PulseTile: Identifiable, Equatable {
        var id: String { code }
        let code: String
        let title: String
        let unit: String
        var value: Double?
        var changePct: Double?
    }

    struct PulseGroup: Identifiable, Equatable {
        let key: String
        let label: String
        var tiles: [PulseTile]

        var id: String { key }
    }

    private static let groupDefinitions: [(key: String, label: String, tiles: [(code: String, title: String, unit: String)])] = [
        ("us_equity", "美股", [
            ("global_sp500", "标普 500", ""),
            ("global_nasdaq", "纳斯达克", ""),
            ("global_dow", "道琼斯", ""),
        ]),
        ("us_bonds_fx", "美债/汇率", [
            ("us_dgs10", "US 10Y", "%"),
            ("usd_cny", "USD/CNY", ""),
            ("usd_eur", "USD/EUR", ""),
            ("us_t10y3m", "T10Y3M", "%"),
        ]),
        ("asia_pacific", "亚太", [
            ("global_shcomp", "上证", ""),
            ("global_hsi", "恒生", ""),
            ("global_n225", "日经", ""),
            ("global_szse", "深证", ""),
            ("global_kospi", "KOSPI", ""),
        ]),
        ("europe", "欧洲", [
            ("global_ftse", "FTSE 100", ""),
            ("global_dax", "DAX", ""),
            ("global_cac", "CAC 40", ""),
        ]),
    ]

    // MARK: - 加载

    /// 首屏加载（幂等：仅首次自动触发）
    func loadIfNeeded() async {
        guard !hasLoadedOnce else { return }
        hasLoadedOnce = true
        await load()
    }

    /// 全量加载：研报摘要 + 脉搏数据 + 平台 KPI + 自选异动 并行
    func load() async {
        async let digestTask: () = loadDigestSummary()
        async let pulseTask: () = loadPulse()
        async let overviewTask: () = loadOverview()
        async let moversTask: () = loadFavoriteMovers()
        _ = await (digestTask, pulseTask, overviewTask, moversTask)
        if pulseError == nil {
            lastUpdated = Date()
        }
    }

    private func loadDigestSummary() async {
        if digestSummary == nil { digestState = .loading }
        do {
            let summary = try await APIClient.shared.send(.digestLatestSummary, as: DigestLatestSummary.self)
            digestSummary = summary
            digestState = .loaded
        } catch let error as APIError {
            if error.isNotFound {
                // 404 = 空态（对齐 web isDigestNotFound）
                digestSummary = nil
                digestState = .empty
            } else if digestSummary != nil {
                // 已有旧数据时静默失败，保留展示
                digestState = .loaded
            } else {
                digestState = .failed(error.userMessage)
            }
        } catch {
            digestState = .failed("加载失败，请稍后重试")
        }
    }

    private func loadPulse() async {
        if pulseGroups.isEmpty { isLoadingPulse = true }
        pulseError = nil
        do {
            // 三路并发：全球宏观 / 美国宏观 / 实时快照（对齐 web lookup 的合并顺序）
            async let globalLatest = APIClient.shared.send(.macroLatest(region: "global"), as: MacroLatestResponse.self)
            async let usLatest = APIClient.shared.send(.macroLatest(region: "us"), as: MacroLatestResponse.self)
            async let realtime = APIClient.shared.send(.macroIndicesGlobal, as: GlobalIndicesRealtimeResponse.self)

            // 逐项容错：实时快照失败不拖垮宏观底数
            let latestGlobal = try await globalLatest
            let latestUs = try await usLatest
            let realtimeResponse = try? await realtime

            var lookup: [String: (value: Double?, changePct: Double?)] = [:]
            for item in latestGlobal.items {
                lookup[item.code] = (item.value, item.changePct)
            }
            for item in latestUs.items where lookup[item.code] == nil {
                lookup[item.code] = (item.value, item.changePct)
            }
            for item in realtimeResponse?.items ?? [] {
                if let value = item.value {
                    lookup[item.code] = (value, item.changePct)
                }
            }
            staleCount = realtimeResponse?.staleCount ?? 0

            pulseGroups = Self.groupDefinitions.map { definition in
                PulseGroup(
                    key: definition.key,
                    label: definition.label,
                    tiles: definition.tiles.map { tile in
                        let entry = lookup[tile.code]
                        return PulseTile(
                            code: tile.code,
                            title: tile.title,
                            unit: tile.unit,
                            value: entry?.value ?? nil,
                            changePct: entry?.changePct ?? nil
                        )
                    }
                )
            }
        } catch let error as APIError {
            pulseError = error.userMessage
        } catch {
            pulseError = "加载失败，请稍后重试"
        }
        isLoadingPulse = false
    }

    /// GET /stats/overview — 平台 KPI 总览（失败静默，保留旧数据）
    private func loadOverview() async {
        if overview == nil { isLoadingOverview = true }
        if let result = try? await APIClient.shared.send(.statsOverview, as: StatsOverview.self) {
            overview = result
        }
        isLoadingOverview = false
    }

    /// 自选异动：favoritesList 取 codes → marketSnapshot 批量快照 →
    /// 按 |changePct| 降序前 5。无自选或全链路失败 → 空数组（横条隐藏）。
    private func loadFavoriteMovers() async {
        if favoriteMovers.isEmpty { isLoadingMovers = true }
        defer { isLoadingMovers = false }
        do {
            let favorites = try await APIClient.shared.send(.favoritesList(), as: FavoriteListResponse.self)
            let codes = favorites.items.map(\.etfCode)
            guard !codes.isEmpty else {
                favoriteMovers = []
                return
            }
            let snapshot = try await APIClient.shared.send(.marketSnapshot(codes: codes), as: MarketSnapshotResponse.self)
            let nameLookup = Dictionary(
                favorites.items.compactMap { fav -> (String, String)? in
                    guard let name = fav.etfName else { return nil }
                    return (fav.etfCode, name)
                },
                uniquingKeysWith: { first, _ in first }
            )
            favoriteMovers = snapshot.items
                .sorted { abs($0.changePct ?? 0) > abs($1.changePct ?? 0) }
                .prefix(5)
                .map { item in
                    FavoriteMover(
                        code: item.etfCode,
                        name: item.etfName ?? nameLookup[item.etfCode] ?? item.etfCode,
                        close: item.close,
                        changePct: item.changePct
                    )
                }
        } catch {
            // 失败保留旧数据；首次失败则隐藏横条
        }
    }
}
