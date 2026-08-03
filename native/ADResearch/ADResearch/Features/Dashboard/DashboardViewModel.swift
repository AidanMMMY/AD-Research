import Foundation
import Observation

/// Dashboard 数据仓库。
///
/// 数据源（逐一对齐 web Dashboard ``useGlobalPulseData`` + ``DigestSummaryCard``）：
/// - ``GET /digest/latest/summary``：研报摘要卡；404 = 「今日研报生成中」空态
/// - ``GET /macro/latest?region=global`` + ``region=us``：宏观脉搏底数
/// - ``GET /macro/indices/global``：实时快照覆盖（内部 code 与 macro 一致，
///   如 global_sp500；单项失败后端跳过，响应恒 200）
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

    private var hasLoadedOnce = false

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

    /// 全量加载：研报摘要 + 脉搏数据并行
    func load() async {
        async let digestTask: () = loadDigestSummary()
        async let pulseTask: () = loadPulse()
        _ = await (digestTask, pulseTask)
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
}
