import Foundation

/// ⌘K 全局搜索 ViewModel（macOS 优先；视图本身双平台可复用）。
///
/// 策略：客户端聚合两路服务端搜索 ——
/// - 标的：GET /etfs?search=（代码/名称模糊，page_size 8）
/// - 资讯：GET /news?q=（服务端 best-effort 全文，page_size 8）
/// 300ms 防抖 + 代数守卫（旧响应不得覆盖新查询）。
@MainActor
@Observable
final class GlobalSearchViewModel {
    enum LoadState: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    var query: String = "" {
        didSet {
            if query != oldValue { scheduleSearch() }
        }
    }

    private(set) var instruments: [InstrumentInfo] = []
    private(set) var news: [NewsArticle] = []
    private(set) var state: LoadState = .idle

    /// 响应代数守卫：每次发起新搜索 +1，慢响应落地前比对
    private var generation = 0
    private var debounceTask: Task<Void, Never>?

    var hasResults: Bool { !instruments.isEmpty || !news.isEmpty }

    func scheduleSearch() {
        debounceTask?.cancel()
        let trimmed = query.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else {
            generation += 1
            instruments = []
            news = []
            state = .idle
            return
        }
        debounceTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled else { return }
            await self?.search(trimmed)
        }
    }

    func search(_ term: String) async {
        generation += 1
        let gen = generation
        state = .loading

        async let instrumentResult = try? APIClient.shared.send(
            .instrumentList(search: term, page: 1, pageSize: 8),
            as: InstrumentListResponse.self
        )
        var built = NewsListParams()
        built.q = term
        built.page = 1
        built.pageSize = 8
        let params = built
        async let newsResult = try? APIClient.shared.send(
            .newsList(params), as: NewsListResponse.self
        )

        let instrumentsResponse = await instrumentResult
        let newsResponse = await newsResult

        guard gen == generation else { return } // 已有更新的查询
        instruments = instrumentsResponse?.items ?? []
        news = newsResponse?.items ?? []
        if instrumentsResponse == nil && newsResponse == nil {
            state = .failed("搜索失败，请稍后重试")
        } else {
            state = .loaded
        }
    }
}
