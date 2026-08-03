import Foundation

/// 标的库 ViewModel：market 筛选 + 搜索（View 层防抖）+ 分页。
///
/// 契约：GET /etfs（InstrumentListResponse）。
@MainActor
@Observable
final class InstrumentsViewModel {
    enum LoadState: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    /// 市场筛选（DB 值：A股 / US / HK / CRYPTO；nil = 全部）
    var market: String? = nil {
        didSet { Task { await reload() } }
    }
    /// 搜索词（View 层 300ms 防抖后赋值）
    var query: String = "" {
        didSet { Task { await reload() } }
    }

    private(set) var items: [InstrumentInfo] = []
    private(set) var state: LoadState = .idle
    private(set) var page = 1
    private(set) var totalPages = 1
    private(set) var total = 0

    var canLoadMore: Bool { page < totalPages }

    func loadIfNeeded() async {
        guard state == .idle else { return }
        await reload()
    }

    func reload() async {
        page = 1
        state = .loading
        do {
            let response = try await fetch(page: 1)
            items = response.items
            total = response.total
            totalPages = response.totalPages
            state = .loaded
        } catch {
            state = .failed(DigestViewModel.describe(error))
        }
    }

    func loadMore() async {
        guard canLoadMore, state == .loaded else { return }
        let next = page + 1
        do {
            let response = try await fetch(page: next)
            items.append(contentsOf: response.items)
            page = response.page
            totalPages = response.totalPages
            total = response.total
        } catch {
            // 分页失败保留已加载内容，滚动到底会重试
        }
    }

    private func fetch(page: Int) async throws -> InstrumentListResponse {
        try await APIClient.shared.send(
            .instrumentList(
                market: market,
                search: query.isEmpty ? nil : query,
                page: page,
                pageSize: 20
            )
        )
    }
}

/// 标的详情 ViewModel：基本信息 + 区间 sparkline。
///
/// 契约：GET /etfs/{code} + GET /etfs/{code}/sparkline?days=。
@MainActor
@Observable
final class InstrumentDetailViewModel {
    enum LoadState: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    /// 走势图区间（days 上限对齐后端 365）
    enum RangeOption: Int, CaseIterable, Identifiable {
        case m1 = 30
        case m3 = 90
        case m6 = 180
        case y1 = 365

        var id: Int { rawValue }

        var label: String {
            switch self {
            case .m1: return "1月"
            case .m3: return "3月"
            case .m6: return "6月"
            case .y1: return "1年"
            }
        }
    }

    let code: String
    private(set) var info: InstrumentInfo?
    private(set) var infoState: LoadState = .idle

    private(set) var points: [Double] = []
    private(set) var dates: [String] = []
    private(set) var chartState: LoadState = .idle

    var range: RangeOption = .m3 {
        didSet { Task { await loadChart() } }
    }

    init(code: String) {
        self.code = code
    }

    func loadIfNeeded() async {
        async let infoTask: () = loadInfoIfNeeded()
        async let chartTask: () = loadChartIfNeeded()
        _ = await (infoTask, chartTask)
    }

    func reload() async {
        async let infoTask: () = loadInfo()
        async let chartTask: () = loadChart()
        _ = await (infoTask, chartTask)
    }

    private func loadInfoIfNeeded() async {
        guard infoState == .idle else { return }
        await loadInfo()
    }

    private func loadChartIfNeeded() async {
        guard chartState == .idle else { return }
        await loadChart()
    }

    private func loadInfo() async {
        infoState = .loading
        do {
            info = try await APIClient.shared.send(.instrumentDetail(code))
            infoState = .loaded
        } catch {
            infoState = .failed(DigestViewModel.describe(error))
        }
    }

    private func loadChart() async {
        chartState = .loading
        do {
            let response: InstrumentSparklineResponse = try await APIClient.shared.send(
                .instrumentSparkline(code, days: range.rawValue)
            )
            points = response.points
            dates = response.dates
            chartState = .loaded
        } catch {
            chartState = .failed(DigestViewModel.describe(error))
        }
    }
}
