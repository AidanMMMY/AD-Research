import Foundation

/// 标的库 ViewModel：market 筛选 + 搜索（View 层防抖）+ 分页
/// + 行情快照 enrich（GET /market-data/snapshot 批量报价）
/// + 行内 sparkline 懒加载缓存（GET /etfs/{code}/sparkline）。
///
/// 契约：GET /etfs（InstrumentListResponse）；
/// 快照 change_pct 已是百分数单位（1.23 = 1.23%），直接喂 ``ChangeText``。
@MainActor
@Observable
final class InstrumentsViewModel {
    enum LoadState: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    /// 客户端排序档（涨/跌幅依赖快照 enrich；无报价的标的排最后）
    enum SortOption: String, CaseIterable, Identifiable {
        case `default`
        case gainers
        case losers
        case code

        var id: String { rawValue }

        var label: String {
            switch self {
            case .default: return "默认"
            case .gainers: return "涨幅"
            case .losers: return "跌幅"
            case .code: return "代码"
            }
        }
    }

    /// 市场筛选（DB 值：A股 / US / HK / CRYPTO；nil = 全部）
    var market: String? = nil {
        didSet { Task { await reload() } }
    }
    /// 搜索词（View 层 300ms 防抖后赋值）
    var query: String = "" {
        didSet { Task { await reload() } }
    }
    /// 排序档（无需重新请求，纯客户端重排）
    var sort: SortOption = .default

    private(set) var items: [InstrumentInfo] = []
    private(set) var state: LoadState = .idle
    private(set) var page = 1
    private(set) var totalPages = 1
    private(set) var total = 0

    /// code → 最新行情快照（缺失报价的标的渲染「—」）
    private(set) var snapshots: [String: MarketSnapshotItem] = [:]
    /// 快照批量 enrich 进行中（行内价格区据此渲染骨架）
    private(set) var isEnriching = false
    /// 已请求过快照的 code（避免翻页/刷新时重复请求同一批）
    private var enrichedCodes: Set<String> = []

    /// code → 30 日收盘序列（懒加载；空数组 = 加载失败/无数据，不再重试）
    private(set) var sparklines: [String: [Double]] = [:]
    private var loadingSparklineCodes: Set<String> = []

    var canLoadMore: Bool { page < totalPages }

    /// 客户端排序后的展示序列
    var displayItems: [InstrumentInfo] {
        switch sort {
        case .default:
            return items
        case .gainers:
            return items.sorted { change(of: $0) > change(of: $1) }
        case .losers:
            return items.sorted { change(of: $0, fallback: .infinity) < change(of: $1, fallback: .infinity) }
        case .code:
            return items.sorted { $0.code.localizedStandardCompare($1.code) == .orderedAscending }
        }
    }

    private func change(of item: InstrumentInfo, fallback: Double = -.infinity) -> Double {
        snapshots[item.code]?.changePct ?? fallback
    }

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
            // 列表先出，报价后台 enrich（行内骨架 → 现价/涨跌幅）
            await enrichSnapshots(for: response.items.map(\.code))
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
            await enrichSnapshots(for: response.items.map(\.code))
        } catch {
            // 分页失败保留已加载内容，滚动到底会重试
        }
    }

    /// 行内 sparkline 懒加载（可见行触发一次，结果含失败态都缓存）
    func loadSparklineIfNeeded(for code: String) {
        guard sparklines[code] == nil, !loadingSparklineCodes.contains(code) else { return }
        loadingSparklineCodes.insert(code)
        Task {
            do {
                let response: InstrumentSparklineResponse = try await APIClient.shared.send(
                    .instrumentSparkline(code, days: 30)
                )
                sparklines[code] = response.points
            } catch {
                sparklines[code] = []
            }
            loadingSparklineCodes.remove(code)
        }
    }

    // MARK: - 私有

    /// 批量报价 enrich（GET /market-data/snapshot）；失败不阻断列表，
    /// 从 enrichedCodes 回滚以便下次翻页/刷新重试。
    private func enrichSnapshots(for codes: [String]) async {
        let pending = codes.filter { !enrichedCodes.contains($0) }
        guard !pending.isEmpty else { return }
        enrichedCodes.formUnion(pending)
        isEnriching = true
        defer { isEnriching = false }
        do {
            let response: MarketSnapshotResponse = try await APIClient.shared.send(
                .marketSnapshot(codes: pending)
            )
            for item in response.items {
                snapshots[item.etfCode] = item
            }
        } catch {
            enrichedCodes.subtract(pending)
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
