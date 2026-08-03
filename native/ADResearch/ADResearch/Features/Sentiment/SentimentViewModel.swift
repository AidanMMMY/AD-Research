import Foundation

/// 情绪面板 ViewModel：按标的聚合的新闻情绪。
///
/// 契约：GET /research/sentiment-data/aggregate（SentimentAggregateResponse）。
/// 注意 market 取值是 a_share / us / crypto / all（与资讯接口的 cn_a 不同）。
@MainActor
@Observable
final class SentimentViewModel {
    enum LoadState: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    /// 市场筛选（nil = 全部）
    enum MarketFilter: String, CaseIterable, Identifiable {
        case all
        case aShare = "a_share"
        case us
        case crypto

        var id: String { rawValue }

        var label: String {
            switch self {
            case .all: return "全部"
            case .aShare: return "A股"
            case .us: return "美股"
            case .crypto: return "加密"
            }
        }
    }

    /// 回溯窗口
    enum DaysOption: Int, CaseIterable, Identifiable {
        case d7 = 7
        case d14 = 14
        case d30 = 30

        var id: Int { rawValue }
        var label: String { "\(rawValue) 天" }
    }

    var market: MarketFilter = .all {
        didSet { Task { await reload() } }
    }
    var days: DaysOption = .d14 {
        didSet { Task { await reload() } }
    }

    private(set) var items: [SentimentAggregateItem] = []
    private(set) var state: LoadState = .idle

    /// 展示序列：按文章数降序（对齐 web 默认排序）
    var rankedItems: [SentimentAggregateItem] {
        items.sorted { $0.count > $1.count }
    }

    /// 总览统计：（偏多, 中性, 偏空）标的数
    var overview: (positive: Int, neutral: Int, negative: Int) {
        var positive = 0, neutral = 0, negative = 0
        for item in items {
            switch item.label {
            case .positive: positive += 1
            case .negative: negative += 1
            case .neutral: neutral += 1
            }
        }
        return (positive, neutral, negative)
    }

    func loadIfNeeded() async {
        guard state == .idle else { return }
        await reload()
    }

    func reload() async {
        state = .loading
        do {
            let response: SentimentAggregateResponse = try await APIClient.shared.send(
                .sentimentAggregate(
                    market: market == .all ? nil : market.rawValue,
                    days: days.rawValue
                )
            )
            items = response.items
            state = .loaded
        } catch {
            state = .failed(DigestViewModel.describe(error))
        }
    }
}
