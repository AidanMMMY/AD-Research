import Foundation

/// 评分榜 ViewModel。
///
/// 契约：GET /scores（ETFScoreListResponse: items/total/template_id/trade_date）。
/// 榜单按 rank_overall 升序（best first）；Crypto 后端恒排除。
/// market 取值 cn_a / us（与资讯的 market 不同，勿用 "A股" 中文值）。
@MainActor
@Observable
final class ScoreRankingViewModel {
    enum LoadState: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    enum MarketFilter: String, CaseIterable, Identifiable {
        case all
        case cnA = "cn_a"
        case us

        var id: String { rawValue }

        var label: String {
            switch self {
            case .all: return "全部"
            case .cnA: return "A股"
            case .us: return "美股"
            }
        }

        /// 传参值（all → nil）
        var paramValue: String? { self == .all ? nil : rawValue }
    }

    enum TypeFilter: String, CaseIterable, Identifiable {
        case all
        case etf = "ETF"
        case stock = "STOCK"

        var id: String { rawValue }

        var label: String {
            switch self {
            case .all: return "全部"
            case .etf: return "ETF"
            case .stock: return "个股"
            }
        }

        var paramValue: String? { self == .all ? nil : rawValue }
    }

    var market: MarketFilter = .all {
        didSet { if market != oldValue { Task { await reload() } } }
    }
    var typeFilter: TypeFilter = .all {
        didSet { if typeFilter != oldValue { Task { await reload() } } }
    }

    private(set) var items: [InstrumentScore] = []
    private(set) var tradeDate: String?
    private(set) var total: Int = 0
    private(set) var state: LoadState = .idle

    private var hasLoadedOnce = false

    func loadIfNeeded() async {
        guard !hasLoadedOnce else { return }
        hasLoadedOnce = true
        await reload()
    }

    func reload() async {
        if items.isEmpty { state = .loading }
        do {
            let result = try await APIClient.shared.send(
                .scoresList(market: market.paramValue, instrumentType: typeFilter.paramValue, limit: 100),
                as: ScoreListResponse.self
            )
            items = result.items
            total = result.total
            tradeDate = result.tradeDate
            state = .loaded
        } catch let error as APIError {
            if items.isEmpty { state = .failed(error.userMessage) }
        } catch {
            if items.isEmpty { state = .failed("加载失败，请稍后重试") }
        }
    }
}

/// GET /scores 响应信封（对齐 ETFScoreListResponse）
struct ScoreListResponse: Decodable, Sendable {
    let items: [InstrumentScore]
    let total: Int
    let templateId: Int
    let tradeDate: String?
}
